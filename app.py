import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, request

from analyzer import analyze
from fetcher import _empty_result, fetch_source, source_from_text

app = Flask(__name__)

MAX_SOURCES = 6
MAX_PASTE = 60000


def is_public_url(url):
    """Security: refuse localhost / private-network addresses (SSRF protection)."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        for info in socket.getaddrinfo(parsed.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast):
                return False
        return True
    except Exception:
        return False


def build_source(item):
    label = (item.get("label") or "").strip()[:80]

    if item.get("type") == "text":
        text = (item.get("text") or "")[:MAX_PASTE]
        return source_from_text(label or "Pasted text", text)

    url = (item.get("value") or "").strip()
    if not is_public_url(url):
        r = _empty_result(url, label or url)
        r["error"] = "This address is not a valid public web page."
        return r

    r = fetch_source(url, label or None)
    r["label"] = label or (r["title"][:60] if r["title"] else url[:60])
    return r


@app.get("/")
def home():
    return render_template("index.html")


@app.post("/api/analyze")
def api_analyze():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()[:500]
    items = data.get("sources") or []

    if len(question) < 5:
        return jsonify(error="Please enter your research question."), 400
    if not isinstance(items, list) or not (2 <= len(items) <= MAX_SOURCES):
        return jsonify(error=f"Add between 2 and {MAX_SOURCES} sources."), 400

    with ThreadPoolExecutor(max_workers=MAX_SOURCES) as pool:
        records = list(pool.map(build_source, items))

    good = [r for r in records if r["ok"]]
    skipped = [{"label": r["label"], "error": r["error"]} for r in records if not r["ok"]]

    if len(good) < 2:
        return jsonify(
            error="At least 2 readable sources are needed. Paste the text for pages that could not be read.",
            skipped=skipped,
        ), 422

    try:
        result = analyze(question, good)
    except Exception:
        app.logger.exception("analysis failed")
        return jsonify(error="The analysis failed. Please try again in a moment."), 500

    result["source_texts"] = {s["id"]: s["text"] for s in good}
    result["skipped"] = skipped
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True)  # turn debug off if you ever deploy this publicly