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


def tidy_title(t):
    """'Professional Nurse- Specialty' / 'A - B' -> 'A – B' (leaves 'Pre-Audit' and 'Grade 1 -3' alone)."""
    t = re.sub(r"(?<=[A-Za-z)])-\s+(?=[A-Za-z])|(?<=\w)\s+-\s+(?=\w)", " – ", str(t or ""))
    return re.sub(r"\s{2,}", " ", t).strip()


PLACE_WORDS = re.compile(r"hospital|clinic|\bCHC\b|centre|center|college|campus|office|station|court|registry|"
                         r"academy|laboratory|depot|prison|correctional|school|ward|unit|theatre|department", re.I)


def _parts(loc):
    loc = re.sub(r"Kwa\s*Zulu\s*-\s*Natal", "KwaZulu\u2011Natal", loc, flags=re.I)        # keep the province name whole
    parts = [p.strip(" )") for p in re.split(r"\s*[,;(]\s*|\s*[-–]\s*(?=[A-Z])", loc) if p.strip(" )")]
    return [p.replace("\u2011", "-") for p in parts]


def _short(label, n=40):
    return label if len(label) <= n else label[:n].rsplit(" ", 1)[0]


def _labels(locs):
    """What tells several locations apart. Within one hospital/town: the ward or unit
    ('Port Shepstone Regional Hospital-Orthopaedics' -> 'Orthopaedics'); otherwise the hospital/town."""
    parts = [_parts(l) for l in locs]
    firsts = [p[0].lower() if p else "" for p in parts]
    out = []
    for p, f in zip(parts, firsts):
        if not p:
            out.append(""); continue
        if firsts.count(f) > 1 and len(p) > 1:
            out.append(_short(" ".join(p[1:])))
        else:
            named = [x for x in p if PLACE_WORDS.search(x)]      # prefer the part that names the hospital/office
            out.append(_short(named[0] if named else p[0]))
    return out


def distinguish_titles(jobs):
    """Several posts from one employer with the same title look like duplicates on the site.
    Add what tells them apart (unit, ward or town) to each title."""
    groups = {}
    for j in jobs:
        j["job_title"] = tidy_title(j.get("job_title"))
        key = (norm(j.get("employer")), re.sub(r"[^a-z0-9]", "", j["job_title"].lower().replace("speciality", "specialty")))
        groups.setdefault(key, []).append(j)
    for group in groups.values():
        if len(group) < 2:
            continue
        locs = [str(j.get("location") or "").strip() for j in group]
        labels = _labels(locs) if len(set(locs)) > 1 and all(locs) else [""] * len(group)
        if len(set(labels)) < 2:
            # same place: use the unit named in the summary ("... is hiring a X in Operating Theatre, based in ...")
            units = []
            for j in group:
                m = re.search(r"is (?:hiring|offering) .+? in (.+?)(?:, based in|\. )", str(j.get("about_role", "")).split("\n")[0])
                units.append(_short(m.group(1).strip()) if m else "")
            labels = units
        if len(set(labels)) < 2:
            continue
        for j, d in zip(group, labels):
            if d and d.lower() not in j["job_title"].lower():
                j["job_title"] = f"{j['job_title']} ({d})"
    return jobs


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
    kept = distinguish_titles(kept)
    removed = before - len(kept)
    with open(SRC, "w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False, indent=None)

    print(f"dedupe: {before} -> {len(kept)} jobs ({removed} duplicate copies removed)")


if __name__ == "__main__":
    main()
