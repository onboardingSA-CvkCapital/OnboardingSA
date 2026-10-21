#!/usr/bin/env python3
"""
dedupe_jobs.py  —  OnboardingSA

Removes genuine duplicate job records from jobs.json. A duplicate is a record
whose title + employer + location + province + description text are all
identical to one already kept (this happens when the same vacancy is scraped
from more than one source, or posted repeatedly). The FIRST occurrence is
kept; later identical copies are dropped.

This is a pure-quality step: no unique job is lost, only redundant copies.
It cuts the duplicate/scaled-content signal that hurts AdSense and SEO.

Runs right after build_json.py, before build_lite.py / build_static.py:

    python3 dedupe_jobs.py
"""

import json, os, re, sys

SRC = "jobs.json"


def norm(s):
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def signature(j):
    body = " ".join(str(j.get(k, "")) for k in ("about_role", "responsibilities", "requirements"))
    return (
        norm(j.get("job_title")),
        norm(j.get("employer")),
        norm(j.get("location")),
        norm(j.get("province")),
        norm(body),
    )


REF_LINE = re.compile(r"Reference numbers? to quote:\s*(.+)", re.I)


def quoted_refs(j):
    """Reference numbers an applicant must quote, normalised ('G51/2026' == 'g 51 / 2026')."""
    m = REF_LINE.search(str(j.get("about_role", "")))
    if not m:
        return set()
    return {re.sub(r"[^a-z0-9]", "", r.lower()) for r in m.group(1).split(",") if re.search(r"\d", r)}


def _source(j):
    m = re.search(r"https?://([^/]+)", str(j.get("source_url", "")))
    return m.group(1).lower().replace("www.", "") if m else ""


def _words(t):
    return {w for w in re.findall(r"[a-z]{3,}", str(t).lower()) if w not in {"the", "and", "for", "grade", "post", "posts"}}


def same_post_elsewhere(jobs):
    """The same government post published by two different sources (e.g. KZN Health's own page and the
    DPSA circular) carries the same reference number and title. Keep the first copy. Jobs from the same
    source are never merged (one reference can cover several districts there)."""
    first = {}                                   # (province, ref) -> [(source, title words), ...]
    kept = []
    for j in jobs:
        prov, src, words = norm(j.get("province")), _source(j), _words(j.get("job_title"))
        dup = False
        for r in quoted_refs(j):
            if len(r) < 5:
                continue
            for osrc, owords in first.get((prov, r), []):
                if osrc != src and words and owords and len(words & owords) / len(words | owords) >= 0.5:
                    dup = True
        if dup:
            continue
        for r in quoted_refs(j):
            first.setdefault((prov, r), []).append((src, words))
        kept.append(j)
    return kept


def main():
    if not os.path.exists(SRC):
        sys.exit(f"ERROR: {SRC} not found (run from the repo root).")

    with open(SRC, encoding="utf-8") as f:
        jobs = json.load(f)

    before = len(jobs)
    seen = set()
    kept = []
    for j in jobs:
        sig = signature(j)
        # Never merge records that have no title (leave them for other filters)
        if not sig[0]:
            kept.append(j)
            continue
        if sig in seen:
            continue
        seen.add(sig)
        kept.append(j)

    kept = same_post_elsewhere(kept)
    removed = before - len(kept)
    with open(SRC, "w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False, indent=None)

    print(f"dedupe: {before} -> {len(kept)} jobs ({removed} duplicate copies removed)")


if __name__ == "__main__":
    main()
