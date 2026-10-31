import re
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; DigitalDarkSpot/1.0; research prototype)"
}
MAX_CHARS = 30000  # keeps AI input size sensible per source

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
        "dates": [],
        "cycles": [],
        "update_hints": [],
        "truncated": False,
    }


def fetch_source(url, label=None):
    """Download a web page and return a clean source record."""
    url = url.strip()
    result = _empty_result(url, label)

    if not url.startswith(("http://", "https://")):
        result["error"] = "URL must start with http:// or https://"
        return result

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        result["error"] = f"Could not fetch this page: {e}"
        return result

    if "pdf" in resp.headers.get("Content-Type", "").lower():
        result["error"] = "PDF sources are not supported yet. Paste the text instead."
        return result

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "aside", "form"]):
        tag.decompose()

    result["title"] = soup.title.get_text(strip=True) if soup.title else ""
    result["http_last_modified"] = resp.headers.get("Last-Modified", "")
    text = soup.get_text(separator=" ")
    _enrich(result, text)

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
    print("HTTP Last-Modified:", r["http_last_modified"] or "none")
    print("Dates found:", r["dates"][:6])
    print("Cycles found:", r["cycles"])
    print("Update hints:", r["update_hints"])
    print("\nFirst 300 characters:\n", r["text"][:300])