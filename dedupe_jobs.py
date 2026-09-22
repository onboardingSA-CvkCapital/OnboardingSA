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

    removed = before - len(kept)
    with open(SRC, "w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False, indent=None)

    print(f"dedupe: {before} -> {len(kept)} jobs ({removed} duplicate copies removed)")


if __name__ == "__main__":
    main()
