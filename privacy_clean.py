#!/usr/bin/env python3
"""
privacy_clean.py  —  OnboardingSA

Strips personal contact details out of scraped job text before it is published.

Job ads copied from recruiters often contain individual people's email
addresses, cellphone / WhatsApp numbers and named contact persons. Publishing
those on an ad-supported page is what triggers AdSense "privacy" / personal-
information flags, and it is also personal information under POPIA.

Every job on the site already has an official "Apply" link, so applicants
lose nothing: any sentence that contains an email address, phone number or
SA ID number is replaced with a short pointer to that link.

Exception: official government adverts (DPSA circular). Their application
mailboxes, office landlines and helplines ARE the way to apply, so only
cellphone numbers are removed (the named "Enquiries" contact is never
scraped in the first place — see scrape_dpsa.py).

Used in two places:
  * sheet_writer.append_jobs()  — new rows are cleaned before they hit the sheet
  * build_json.py               — everything is cleaned again before the site is
                                  built (covers rows already in the sheet)

Run on its own to clean the existing JSON files in place:

    python3 privacy_clean.py jobs.json jobs-lite.json jobs-page-1.json
"""

import json, re, sys

NOTE = "[Contact details removed — please apply using the official Apply link.]"

# Long free-text fields: whole sentences/lines containing contact data are dropped.
TEXT_FIELDS = ("about_role", "responsibilities", "requirements", "snippet")
# Fields that are never touched (identifiers and links).
SKIP_FIELDS = ("id", "reference_no", "official_apply_url", "source_url",
               "posted_date", "closing_date", "status", "featured", "logo_url", "_rawid")

EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+\-]+\s*(?:@|\[at\]|\(at\))\s*[A-Za-z0-9\-]+(?:\s*(?:\.|\[dot\]|\(dot\))\s*[A-Za-z0-9\-]+)+",
    re.I)

# South African phone numbers: +27 / 0027 / 0 prefix, 9 further digits,
# with optional spaces, dashes, dots or brackets between groups.
PHONE_RE = re.compile(
    r"(?<![\d])(?:\+\s?27|0027|\(?0)\s?\(?\d{2}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}(?!\d)")

# International numbers written with a + prefix (e.g. +44 20 7946 0958).
INTL_PHONE_RE = re.compile(r"(?<![\w])\+\d{1,3}[\s.\-]?(?:\(?\d{1,4}\)?[\s.\-]?){2,4}\d{2,4}(?!\d)")

# 13-digit SA ID numbers (validated with the date + Luhn check to avoid false hits).
ID_RE = re.compile(r"(?<!\d)\d{13}(?!\d)")

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9•\-(\"'])")


def _luhn_ok(num):
    total = 0
    for i, ch in enumerate(reversed(num)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _is_sa_id(num):
    mm, dd = int(num[2:4]), int(num[4:6])
    return 1 <= mm <= 12 and 1 <= dd <= 31 and num[10] in "01" and _luhn_ok(num)


def has_contact(text):
    if not text:
        return False
    if EMAIL_RE.search(text) or PHONE_RE.search(text) or INTL_PHONE_RE.search(text):
        return True
    return any(_is_sa_id(m.group()) for m in ID_RE.finditer(text))


def scrub_tokens(text):
    """Replace just the contact tokens (for short fields like title/location)."""
    if not text or not has_contact(text):
        return text
    text = EMAIL_RE.sub("", text)
    text = PHONE_RE.sub("", text)
    text = INTL_PHONE_RE.sub("", text)
    text = ID_RE.sub(lambda m: "" if _is_sa_id(m.group()) else m.group(), text)
    return re.sub(r"\s{2,}", " ", text).strip(" ,;:-–—")


def scrub_text(text):
    """Drop every sentence/line that contains contact details; keep the rest."""
    if not text or not has_contact(text):
        return text
    out_lines = []
    removed = False
    for line in text.split("\n"):
        if not has_contact(line):
            out_lines.append(line)
            continue
        kept = [s for s in SENTENCE_SPLIT.split(line) if not has_contact(s)]
        removed = True
        if kept:
            out_lines.append(" ".join(kept))
    cleaned = "\n".join(l for l in out_lines if l.strip() or not removed)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if removed and NOTE not in cleaned:
        cleaned = (cleaned + "\n" + NOTE).strip() if cleaned else NOTE
    return cleaned


# Official public-service adverts (DPSA circular): application mailboxes, office landlines and
# helplines are the official way to apply, so they stay. Only cellphone numbers are removed.
OFFICIAL_SOURCES = ("dpsa.gov.za",)
MOBILE_RE = re.compile(r"(?:Tel\.?\s*(?:No\.?)?\s*:?\s*|Cell\.?\s*(?:No\.?)?\s*:?\s*)?"
                       r"(?<!\d)(?:\+\s?27\s?|0027\s?|0)(?:6\d|7\d|8[1-4])[\s.\-]?\d{3}[\s.\-]?\d{4}(?!\d)",
                       re.I)


def clean_official_text(text):
    if not text:
        return text
    text = MOBILE_RE.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", text)


def clean_job(job):
    """Return the job dict with personal contact details removed."""
    if any(src in (job.get("source_url") or "") for src in OFFICIAL_SOURCES):
        for k, v in list(job.items()):
            if isinstance(v, str) and k not in SKIP_FIELDS:
                job[k] = clean_official_text(v)
        return job
    for k, v in list(job.items()):
        if not isinstance(v, str) or k in SKIP_FIELDS:
            continue
        job[k] = scrub_text(v) if k in TEXT_FIELDS else scrub_tokens(v)
    return job


def clean_jobs(jobs):
    return [clean_job(j) for j in jobs]


def _clean_file(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    before = sum(1 for j in data if any(has_contact(str(v)) for k, v in j.items() if k not in SKIP_FIELDS))
    data = clean_jobs(data)
    after = sum(1 for j in data if any(has_contact(str(v)) for k, v in j.items() if k not in SKIP_FIELDS))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{path}: {before} jobs had contact details, {after} remain.", file=sys.stderr)


if __name__ == "__main__":
    for p in sys.argv[1:] or ["jobs.json"]:
        _clean_file(p)
