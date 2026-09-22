#!/usr/bin/env python3
"""
build-lite.py  —  OnboardingSA

From the full jobs.json this writes TWO files the homepage uses:

  1. jobs-lite.json    — every job, but only the fields the list + search need.
                         Loads in the BACKGROUND so search and filters work.
  2. jobs-page-1.json  — just the first page of jobs (pre-filtered to live and
                         pre-sorted the way the homepage shows them). Tiny, so
                         the homepage paints instantly on startup.

Full job descriptions stay in jobs.json and in the individual job pages
(jobs/<id>.html). Run this whenever jobs.json changes:

    python3 build-lite.py
"""

import json, os, sys
from datetime import datetime, timezone

SRC        = "jobs.json"
OUT_LITE   = "jobs-lite.json"
OUT_PAGE1  = "jobs-page-1.json"

LIST_FIELDS = [
    "id", "job_title", "employer", "category", "province", "location",
    "employment_type", "salary", "posted_date", "closing_date",
    "reference_no", "featured", "logo_url", "status",
]
SNIPPET_LEN   = 120
FIRST_PAGE_N  = 24          # 2 pages' worth at 12 per page

FAR_FUTURE = datetime(2999, 1, 1, tzinfo=timezone.utc)


def snippet(job):
    text = " ".join(str(job.get(k, "")) for k in ("about_role", "requirements"))
    return " ".join(text.split())[:SNIPPET_LEN]


def parse_date(s):
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y",
                "%d %B %Y", "%d %b %Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:len(fmt) + 4], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None  # unparseable -> treat as "no closing date" (not expired)


def is_expired(s):
    d = parse_date(s)
    if d is None:
        return False
    end = d.replace(hour=23, minute=59, second=59)
    return end < datetime.now(timezone.utc)


def closing_sort_key(row):
    d = parse_date(row.get("closing_date"))
    return d or FAR_FUTURE


def main():
    if not os.path.exists(SRC):
        sys.exit(f"ERROR: {SRC} not found (run this from the repo root).")

    with open(SRC, encoding="utf-8") as f:
        jobs = json.load(f)

    # ---- full slim list ----
    lite = []
    for j in jobs:
        row = {k: j.get(k, "") for k in LIST_FIELDS}
        row["snippet"] = snippet(j)
        lite.append(row)

    with open(OUT_LITE, "w", encoding="utf-8") as f:
        json.dump(lite, f, ensure_ascii=False, separators=(",", ":"))

    # ---- first page: same filter + sort the homepage applies ----
    live = [r for r in lite
            if str(r.get("job_title", "")).strip()
            and str(r.get("status", "")).lower() == "live"
            and not is_expired(r.get("closing_date"))]

    live.sort(key=closing_sort_key)
    live.sort(key=lambda r: 0 if str(r.get("featured", "")).lower() == "yes" else 1)

    page1 = live[:FIRST_PAGE_N]
    with open(OUT_PAGE1, "w", encoding="utf-8") as f:
        json.dump(page1, f, ensure_ascii=False, separators=(",", ":"))

    mb = lambda p: os.path.getsize(p) / 1048576
    kb = lambda p: os.path.getsize(p) / 1024
    print(f"{len(lite)} jobs  |  {SRC} {mb(SRC):.2f} MB")
    print(f"  -> {OUT_LITE}   {mb(OUT_LITE):.2f} MB  (background)")
    print(f"  -> {OUT_PAGE1}  {kb(OUT_PAGE1):.1f} KB  ({len(page1)} jobs, instant paint)")


if __name__ == "__main__":
    main()
