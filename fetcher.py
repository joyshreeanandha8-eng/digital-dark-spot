import io
import json
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; DigitalDarkSpot/1.0; research prototype)"
}
MAX_CHARS = 30000            # keeps AI input size sensible per source
MAX_PDF_PAGES = 20
MAX_DOWNLOAD_BYTES = 15_000_000

MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec"
)
DATE_PATTERNS = [
    rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})\.?,?\s+\d{{4}}\b",
    rf"\b(?:{MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}\b",
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b",
]
CYCLE_PATTERN = r"\b(20\d{2})\s*[-–/]\s*(20)?(\d{2})\b"
HINT_PATTERN = (
    r"(?:last\s+updated|updated\s+on|last\s+modified|published\s+on|"
    r"posted\s+on|date\s+of\s+publication|notification\s+date).{0,60}"
)

META_PUBLISHED = [
    ("property", "article:published_time"), ("property", "og:article:published_time"),
    ("property", "og:published_time"), ("name", "article:published_time"),
    ("name", "pubdate"), ("name", "publish-date"), ("name", "date"),
    ("name", "dc.date.issued"), ("name", "dcterms.created"), ("itemprop", "datePublished"),
]
META_MODIFIED = [
    ("property", "article:modified_time"), ("property", "og:updated_time"),
    ("name", "last-modified"), ("name", "dcterms.modified"), ("itemprop", "dateModified"),
]


# ---------- text-based date finding ----------

def find_dates(text):
    """Return up to 15 unique date strings found in the text."""
    found = []
    for pattern in DATE_PATTERNS:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            s = m.group(0).strip()
            if s not in found:
                found.append(s)
    return found[:15]


def find_cycles(text):
    """Find academic/application cycles like 2024-25 or 2024-2025."""
    cycles = []
    for m in re.finditer(CYCLE_PATTERN, text):
        start = int(m.group(1))
        end2 = int(m.group(3))
        if (start + 1) % 100 == end2:  # rejects things like 2025-03
            label = f"{start}-{start + 1}"
            if label not in cycles:
                cycles.append(label)
    return cycles


def find_update_hints(text):
    """Snippets such as 'Last updated: 5 March 2024'."""
    hints = []
    for m in re.finditer(HINT_PATTERN, text, flags=re.IGNORECASE):
        s = m.group(0).strip()
        if s not in hints:
            hints.append(s)
    return hints[:5]


# ---------- page-metadata dates (publication / update date) ----------

def _parse_iso(s):
    """Parse an ISO-like date string; return an aware datetime or None."""
    if not s:
        return None
    s = str(s).strip()
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        m = re.search(r"\d{4}-\d{2}-\d{2}", s)
        if not m:
            return None
        try:
            dt = datetime.fromisoformat(m.group(0))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _meta_lookup(soup, keys):
    for attr, value in keys:
        tag = soup.find("meta", attrs={attr: re.compile("^" + re.escape(value) + "$", re.I)})
        if tag and tag.get("content"):
            dt = _parse_iso(tag["content"])
            if dt:
                return dt
    return None


def _jsonld_dates(soup):
    published, modified = None, None
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except (ValueError, TypeError):
            continue
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                if not published and item.get("datePublished"):
                    published = _parse_iso(item["datePublished"])
                if not modified and item.get("dateModified"):
                    modified = _parse_iso(item["dateModified"])
                stack.extend(v for v in item.values() if isinstance(v, (list, dict)))
    return published, modified


def find_page_dates(soup):
    """Return (published, modified) as YYYY-MM-DD strings, or empty strings."""
    pub = _meta_lookup(soup, META_PUBLISHED)
    mod = _meta_lookup(soup, META_MODIFIED)
    jp, jm = _jsonld_dates(soup)
    pub, mod = pub or jp, mod or jm
    if not pub:
        t = soup.find("time", attrs={"datetime": True})
        if t:
            pub = _parse_iso(t["datetime"])
    return (pub.date().isoformat() if pub else ""), (mod.date().isoformat() if mod else "")


# ---------- source records ----------

def _enrich(result, text):
    """Fill in the text and all date information on a source record."""
    text = re.sub(r"\s+", " ", text).strip()
    result["dates"] = find_dates(text)
    result["cycles"] = find_cycles(text)
    result["update_hints"] = find_update_hints(text)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]
        result["truncated"] = True
    result["text"] = text
    return result


def _empty_result(url, label):
    return {
        "url": url,
        "label": label or url,
        "ok": False,
        "error": "",
        "title": "",
        "text": "",
        "http_last_modified": "",
        "published": "",
        "modified": "",
        "dates": [],
        "cycles": [],
        "update_hints": [],
        "truncated": False,
    }


def _fetch_pdf(resp, url, result):
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(resp.content))
        text = " ".join((p.extract_text() or "") for p in reader.pages[:MAX_PDF_PAGES])
    except ImportError:
        result["error"] = "PDF support needs the pypdf library (run: pip install pypdf)."
        return result
    except Exception as e:
        result["error"] = f"Could not read this PDF: {e}"
        return result

    result["title"] = url.split("?")[0].rsplit("/", 1)[-1]
    _enrich(result, text)
    if len(result["text"]) < 200:
        result["error"] = "No readable text in this PDF (it may be a scan). Paste the text instead."
        return result
    result["ok"] = True
    return result


def fetch_source(url, label=None):
    """Download a web page or PDF and return a clean source record."""
    url = url.strip()
    result = _empty_result(url, label)

    if not url.startswith(("http://", "https://")):
        result["error"] = "URL must start with http:// or https://"
        return result

    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        result["error"] = f"Could not fetch this page: {e}"
        return result

    if len(resp.content) > MAX_DOWNLOAD_BYTES:
        result["error"] = "This file is too large. Paste the relevant text instead."
        return result

    result["http_last_modified"] = resp.headers.get("Last-Modified", "")
    ctype = resp.headers.get("Content-Type", "").lower()
    if "pdf" in ctype or url.lower().split("?")[0].endswith(".pdf"):
        return _fetch_pdf(resp, url, result)

    soup = BeautifulSoup(resp.text, "html.parser")
    result["published"], result["modified"] = find_page_dates(soup)  # before scripts are removed

    for tag in soup(["script", "style", "noscript", "svg", "nav", "aside", "form"]):
        tag.decompose()

    result["title"] = soup.title.get_text(strip=True) if soup.title else ""
    _enrich(result, soup.get_text(separator=" "))

    if len(result["text"]) < 200:
        result["error"] = (
            "Very little text found. The page may need JavaScript or may block "
            "scrapers. Paste the text instead."
        )
        return result

    result["ok"] = True
    return result


def source_from_text(label, text):
    """Fallback: build a source record from text the user pasted."""
    result = _empty_result("", label)
    result["title"] = label
    _enrich(result, text)
    result["ok"] = len(result["text"]) >= 50
    if not result["ok"]:
        result["error"] = "Pasted text is too short."
    return result


if __name__ == "__main__":
    url = input("Paste a page URL to test: ").strip()
    r = fetch_source(url)
    print("\nOK:", r["ok"])
    if r["error"]:
        print("Error:", r["error"])
    print("Title:", r["title"])
    print("Characters:", len(r["text"]), "(truncated)" if r["truncated"] else "")
    print("Published (metadata):", r["published"] or "none")
    print("Modified (metadata):", r["modified"] or "none")
    print("HTTP Last-Modified:", r["http_last_modified"] or "none")
    print("Dates found:", r["dates"][:6])
    print("Cycles found:", r["cycles"])
    print("\nFirst 300 characters:\n", r["text"][:300])