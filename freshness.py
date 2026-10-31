import datetime
import re
from email.utils import parsedate_to_datetime


def _months_between(d, today):
    return (today.year - d.year) * 12 + (today.month - d.month)


def _parse_day(s):
    try:
        return datetime.date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def freshness_flags(sources, today=None):
    """Rule-based (no AI) warnings about old or undated sources."""
    today = today or datetime.date.today()
    flags = []

    for s in sources:
        sid = s["id"]
        known, kind = None, ""

        # 1. Best evidence: a date in the page's own metadata
        for key, name in (("modified", "last updated"), ("published", "published")):
            d = _parse_day(s.get(key))
            if d:
                known, kind = d, name
                break

        # 2. Next best: the server's Last-Modified header
        if not known and s.get("http_last_modified"):
            try:
                known = parsedate_to_datetime(s["http_last_modified"]).date()
                kind = "last modified (server header)"
            except (TypeError, ValueError):
                known = None

        cycles = s.get("cycles", [])
        cycle_ends = [int(c.split("-")[1]) for c in cycles]

        if known:
            months = _months_between(known, today)
            if months >= 12:
                flags.append({
                    "source_id": sid,
                    "message": f"This page was {kind} on {known.isoformat()}, about {months} months ago. "
                               f"Details may have changed since then.",
                })
            if cycle_ends and max(cycle_ends) < today.year:
                flags.append({
                    "source_id": sid,
                    "message": f"The latest application cycle mentioned is {max(cycles)}, which may be an earlier cycle than the current one.",
                })
        else:
            # 3. No metadata: fall back to years mentioned in the text
            years = [int(y) for y in re.findall(r"\b(20\d{2})\b", " ".join(s.get("dates", [])))]
            years += cycle_ends
            if years:
                past = [y for y in years if y <= today.year]
                if past and max(past) < today.year:
                    flags.append({
                        "source_id": sid,
                        "message": f"No publication date was found. The most recent year mentioned in the text is "
                                   f"{max(past)}, so the information may be out of date.",
                    })
            else:
                flags.append({
                    "source_id": sid,
                    "message": "No dates or application cycle found in this source, so its freshness cannot be checked.",
                })
    return flags