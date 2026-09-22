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


import html as _html, re as _re

INDEX_FILE = "index.html"
BAKE_N     = 24   # how many jobs to pre-render into the landing page HTML


def esc(s):
    return _html.escape(str(s or "").strip(), quote=True)


def initials(name):
    parts = str(name or "?").split()
    return ("".join(w[0] for w in parts[:2]).upper()) or "?"


def fmt_date(s):
    d = parse_date(s)
    return d.strftime("%-d %b %Y") if d else str(s or "")


def days_left(s):
    d = parse_date(s)
    if not d:
        return None
    return (d.date() - datetime.now(timezone.utc).date()).days


def safe_id(rid):
    return _re.sub(r"[^A-Za-z0-9_\-]", "-", str(rid or ""))


def render_card(j):
    rid = j.get("reference_no") or j.get("id") or ""
    href = f"jobs/{safe_id(rid)}.html"
    gold = " gold" if str(j.get("featured", "")).lower() == "yes" else ""
    badge = '<span class="badge">★ Featured</span>' if gold else ""
    loc = ", ".join([x for x in [j.get("location", ""), j.get("province", "")] if str(x).strip()])
    chips = ""
    if j.get("employment_type"):
        chips += f'<span class="chip">{esc(j.get("employment_type"))}</span>'
    if j.get("salary"):
        chips += f'<span class="chip">{esc(j.get("salary"))}</span>'
    if j.get("closing_date"):
        dl = days_left(j.get("closing_date"))
        soon = dl is not None and dl <= 7
        extra = ""
        if soon:
            extra = " · closed" if (dl is not None and dl < 0) else f" · {dl} days left"
        cls = " close-soon" if soon else ""
        chips += f'<span class="chip{cls}">Closes {esc(fmt_date(j.get("closing_date")))}{extra}</span>'
    return (
        f'<a class="jobcard" href="{href}" aria-label="{esc(j.get("job_title"))} at {esc(j.get("employer"))}">'
        f'{badge}'
        f'<div class="card-head">'
        f'<div class="avatar{gold}">{esc(initials(j.get("employer")))}</div>'
        f'<div class="card-head-txt">'
        f'<h3>{esc(j.get("job_title"))}</h3>'
        f'<div class="emp">{esc(j.get("employer"))}</div>'
        f'<div class="loc">{esc(loc)}</div>'
        f'</div></div>'
        f'<div class="chips">{chips}</div>'
        f'</a>'
    )


def bake_into_index(page1):
    """Replace the content between <!--JOBS_START--> and <!--JOBS_END--> in
    index.html with pre-rendered job cards, so the landing page has real
    content in the HTML before any JavaScript runs. Safe no-op if markers
    or index.html are missing."""
    if not os.path.exists(INDEX_FILE):
        return
    with open(INDEX_FILE, encoding="utf-8") as f:
        html = f.read()
    if "<!--JOBS_START-->" not in html or "<!--JOBS_END-->" not in html:
        return
    cards = "\n      ".join(render_card(j) for j in page1[:BAKE_N]) or \
            '<div class="loading">Loading jobs…</div>'
    block = f"<!--JOBS_START-->\n      {cards}\n      <!--JOBS_END-->"
    new = _re.sub(r"<!--JOBS_START-->.*?<!--JOBS_END-->", lambda _m: block, html, flags=_re.S)
    if new != html:
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            f.write(new)


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

    # ---- pre-render the first jobs into the landing page HTML ----
    bake_into_index(page1)

    mb = lambda p: os.path.getsize(p) / 1048576
    kb = lambda p: os.path.getsize(p) / 1024
    print(f"{len(lite)} jobs  |  {SRC} {mb(SRC):.2f} MB")
    print(f"  -> {OUT_LITE}   {mb(OUT_LITE):.2f} MB  (background)")
    print(f"  -> {OUT_PAGE1}  {kb(OUT_PAGE1):.1f} KB  ({len(page1)} jobs, instant paint)")
    print(f"  -> {INDEX_FILE}  baked {min(len(page1), BAKE_N)} jobs into landing page HTML")


if __name__ == "__main__":
    main()
