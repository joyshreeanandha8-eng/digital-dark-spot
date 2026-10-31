import json
import os
import re
import time
import datetime
from email.utils import parsedate_to_datetime

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

SYSTEM = """You are a careful research auditor. You find information gaps,
conflicts and outdated details across the sources you are given.
You use ONLY the provided source text, never outside knowledge.
You never state that something does not exist in the world; you can only say it
was not found in the sources provided. You return only valid JSON."""

INSTRUCTIONS = """
USER QUESTION: {question}

Below are the sources. Analyse them and return ONE JSON object with exactly this shape:

{{
  "topic_type": "short phrase, e.g. scholarship application",
  "required_facts": [
    {{"id": "F1", "name": "short fact name, e.g. Application deadline", "why": "why a person needs this to act on the question"}}
  ],
  "findings": [
    {{"fact_id": "F1", "source_id": "S1", "status": "found" or "not_found",
      "value": "short plain summary of what the source says (empty if not_found)",
      "quote": "exact text copied from the source (empty if not_found)"}}
  ],
  "conflicts": [
    {{"fact_id": "F1", "summary": "what differs",
      "claims": [{{"source_id": "S1", "quote": "exact text"}}, {{"source_id": "S2", "quote": "exact text"}}]}}
  ],
  "outdated_signals": [
    {{"source_id": "S1", "reason": "why this may be out of date", "quote": "exact text"}}
  ],
  "unanswered_questions": ["question the sources do not answer"],
  "checklist": [
    {{"priority": "high" or "medium" or "low", "action": "what the user should verify",
      "reason": "why it matters", "where_to_verify": "kind of official source to check"}}
  ]
}}

RULES:
1. required_facts: choose 6 to 8 facts a person must know to act on the question. Include
   facts likely to matter even if NO source covers them (deadlines, documents, fees,
   renewal or follow-up conditions, official application link, contact point).
2. findings: one entry for EVERY combination of fact and source.
3. Every "found" entry needs a quote copied CHARACTER FOR CHARACTER from that source's text,
   10 to 200 characters, contiguous, with no "..." and no paraphrasing.
   If you cannot quote it exactly, set status to "not_found".
4. conflicts: only when two sources give different values for the same fact. Quote both.
5. outdated_signals: only for visible dates or cycles that look old. Quote the text.
6. checklist: 4 to 8 items, ordered high priority first. Never invent URLs, phone numbers or names.
7. Return ONLY the JSON object, with no markdown fences.

SOURCES:
{sources}
"""


# ---------- quote verification (done by code, not AI) ----------

def _norm(s):
    s = s.lower()
    for a, b in (("\u2019", "'"), ("\u2018", "'"), ("\u201c", '"'), ("\u201d", '"'),
                 ("\u2013", "-"), ("\u2014", "-"), ("\u00a0", " ")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def quote_is_verified(quote, source_text):
    q = _norm(quote or "").strip(" \"'.")
    if len(q) < 8:
        return False
    return q in _norm(source_text)


# ---------- rule-based freshness checks (no AI) ----------

def rule_based_flags(sources):
    today = datetime.date.today()
    flags = []
    for s in sources:
        if s["cycles"]:
            latest_end = max(int(c.split("-")[1]) for c in s["cycles"])
            if latest_end < today.year:
                flags.append({
                    "source_id": s["id"],
                    "message": f"Latest cycle mentioned is {max(s['cycles'])}, which may be an earlier cycle than the current one.",
                })
        lm = s.get("http_last_modified")
        if lm:
            try:
                age = (datetime.datetime.now(datetime.timezone.utc) - parsedate_to_datetime(lm)).days
                if age > 365:
                    flags.append({
                        "source_id": s["id"],
                        "message": f"Page header says it was last modified about {age // 30} months ago ({lm}).",
                    })
            except (TypeError, ValueError):
                pass
        if not s["dates"] and not s["cycles"]:
            flags.append({
                "source_id": s["id"],
                "message": "No dates or application cycle found in this source, so its freshness cannot be checked.",
            })
    return flags


# ---------- Gemini call (with automatic model fallback) ----------

def _call_gemini(prompt):
    key = os.getenv("GEMINI_API_KEY")
    primary = os.getenv("GEMINI_MODEL")
    if not key or not primary:
        raise RuntimeError("Set GEMINI_API_KEY and GEMINI_MODEL in the .env file.")

    fallbacks = [m.strip() for m in os.getenv("GEMINI_FALLBACKS", "").split(",") if m.strip()]
    models = [primary] + [m for m in fallbacks if m != primary]

    client = genai.Client(api_key=key)
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM,
        response_mime_type="application/json",
    )

    last_error = None
    for model in models:
        for attempt in range(2):
            try:
                resp = client.models.generate_content(model=model, contents=prompt, config=config)
                print(f"[model used: {model}]")
                return resp.text
            except Exception as e:
                last_error = e
                msg = str(e)
                busy = any(t in msg for t in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED"))
                if busy and attempt == 0:
                    time.sleep(5)  # short pause, then one retry on the same model
                    continue
                break  # otherwise give up on this model and try the next one
    raise RuntimeError(f"All models failed. Last error: {last_error}")


def _parse_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    return json.loads(text)


# ---------- main entry point ----------

def analyze(question, sources):
    """sources: list of records from fetcher.py (only ok ones). Returns the final analysis."""
    for i, s in enumerate(sources):
        s["id"] = f"S{i + 1}"
    by_id = {s["id"]: s for s in sources}

    blocks = []
    for s in sources:
        blocks.append(
            f"=== SOURCE {s['id']} ===\nLabel: {s['label']}\nTitle: {s['title']}\n"
            f"URL: {s['url'] or 'pasted text'}\nText:\n{s['text']}\n=== END SOURCE {s['id']} ==="
        )
    prompt = INSTRUCTIONS.format(question=question, sources="\n\n".join(blocks))

    raw = _parse_json(_call_gemini(prompt))

    facts = [f for f in raw.get("required_facts", []) if isinstance(f, dict) and f.get("id")]
    matrix = {f["id"]: {s["id"]: {"status": "missing", "value": "", "quote": ""} for s in sources}
              for f in facts}

    for f in raw.get("findings", []):
        fid, sid = f.get("fact_id"), f.get("source_id")
        if fid not in matrix or sid not in by_id:
            continue
        if f.get("status") == "found":
            ok = quote_is_verified(f.get("quote"), by_id[sid]["text"])
            matrix[fid][sid] = {
                "status": "found" if ok else "unverified",
                "value": f.get("value", ""),
                "quote": f.get("quote", ""),
            }

    for f in facts:
        cells = matrix[f["id"]].values()
        f["dark_spot"] = not any(c["status"] == "found" for c in cells)

    conflicts = []
    for c in raw.get("conflicts", []):
        claims = []
        for cl in c.get("claims", []):
            sid = cl.get("source_id")
            if sid in by_id:
                claims.append({**cl, "verified": quote_is_verified(cl.get("quote"), by_id[sid]["text"])})
        verified_sources = {cl["source_id"] for cl in claims if cl["verified"]}
        c["claims"] = claims
        c["verified"] = len(verified_sources) >= 2
        conflicts.append(c)

    outdated = []
    for o in raw.get("outdated_signals", []):
        sid = o.get("source_id")
        if sid in by_id:
            o["verified"] = quote_is_verified(o.get("quote"), by_id[sid]["text"])
            outdated.append(o)

    return {
        "question": question,
        "topic_type": raw.get("topic_type", ""),
        "sources": [{"id": s["id"], "label": s["label"], "title": s["title"], "url": s["url"]} for s in sources],
        "facts": facts,
        "matrix": matrix,
        "conflicts": conflicts,
        "outdated_ai": outdated,
        "outdated_rules": rule_based_flags(sources),
        "unanswered": raw.get("unanswered_questions", []),
        "checklist": raw.get("checklist", []),
    }


# ---------- terminal test with FICTIONAL sample sources ----------

if __name__ == "__main__":
    from fetcher import source_from_text

    sample_a = (
        "Example Merit Scholarship (fictional test page). Official notice. "
        "Applications for the 2023-24 cycle are open until 15 March 2024. "
        "Eligibility: the annual family income must be below Rs 2,50,000. "
        "Documents required: income certificate, community certificate and Aadhaar card. "
        "Applications are submitted through the official scholarship portal. Last updated: 2 January 2024."
    )
    sample_b = (
        "Scholarship guide blog (fictional test page). Students whose family income is "
        "below Rs 3,00,000 can apply for the Example Merit Scholarship. "
        "You will need an income certificate and your bank passbook. "
        "Apply before 10 April, and keep a printout of your application. Posted on 20 February 2024."
    )
    srcs = [source_from_text("Official notice (SAMPLE)", sample_a),
            source_from_text("Blog guide (SAMPLE)", sample_b)]

    result = analyze("What should I verify before applying for this scholarship?", srcs)

    print("\nTOPIC:", result["topic_type"])
    print("\nCOVERAGE MATRIX  (FOUND = verified quote, UNVERIFIED = AI claim without matching quote, ---- = not found)")
    ids = [s["id"] for s in result["sources"]]
    print(f"{'Fact':38}" + "".join(f"{i:12}" for i in ids))
    for f in result["facts"]:
        row = result["matrix"][f["id"]]
        cells = "".join(f"{row[i]['status'].upper().replace('MISSING', '----'):12}" for i in ids)
        mark = "  <== DARK SPOT" if f["dark_spot"] else ""
        print(f"{f['name'][:36]:38}{cells}{mark}")

    print("\nCONFLICTS:")
    for c in result["conflicts"]:
        print(" -", c["summary"], "| verified:", c["verified"])
    print("\nRULE-BASED FLAGS:")
    for r in result["outdated_rules"]:
        print(" -", r["source_id"], r["message"])
    print("\nCHECKLIST:")
    for item in result["checklist"]:
        print(f" [{item['priority']}] {item['action']}")