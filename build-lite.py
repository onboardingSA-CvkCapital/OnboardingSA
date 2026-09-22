#!/usr/bin/env python3
"""
build-lite.py  —  OnboardingSA

Reads the full jobs.json and writes a slim jobs-lite.json that the homepage
uses for its list + search. Full job descriptions stay in jobs.json and in the
individual static job pages (jobs/<id>.html) — the homepage no longer needs to
download all of them, which is what makes it load fast.

Run it any time jobs.json changes:
    python3 build-lite.py
"""

import json, os, sys

SRC = "jobs.json"
OUT = "jobs-lite.json"

# Only the fields the homepage list + cards actually need.
LIST_FIELDS = [
    "id", "job_title", "employer", "category", "province", "location",
    "employment_type", "salary", "posted_date", "closing_date",
    "reference_no", "featured", "logo_url", "status",
]

# How many characters of description to keep for search matching.
SNIPPET_LEN = 120


def snippet(job):
    text = " ".join(str(job.get(k, "")) for k in ("about_role", "requirements"))
    return " ".join(text.split())[:SNIPPET_LEN]


def main():
    if not os.path.exists(SRC):
        sys.exit(f"ERROR: {SRC} not found (run this from the repo root).")

    with open(SRC, encoding="utf-8") as f:
        jobs = json.load(f)

    lite = []
    for j in jobs:
        row = {k: j.get(k, "") for k in LIST_FIELDS}
        row["snippet"] = snippet(j)
        lite.append(row)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(lite, f, ensure_ascii=False, separators=(",", ":"))

    src_mb = os.path.getsize(SRC) / 1048576
    out_mb = os.path.getsize(OUT) / 1048576
    print(f"{len(lite)} jobs  |  {SRC} {src_mb:.2f} MB  ->  {OUT} {out_mb:.2f} MB")


if __name__ == "__main__":
    main()
