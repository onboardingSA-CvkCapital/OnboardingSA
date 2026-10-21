#!/usr/bin/env python3
"""
scrape_kznhealth.py  —  OnboardingSA

KwaZulu-Natal Department of Health vacancies from its own vacancy page
(https://www.kznhealth.gov.za/vacancies/): tables of
  Circular Number | Vacancy | Hospital / District Office / CHC ... | Closing Date
each linking to the advert PDF.

Every hospital writes its own advert layout, so the PDF is read by what its
headings say ("MINIMUM REQUIREMENTS", "KEY PERFORMANCE AREAS", "DUTIES" ...),
not by a fixed template. Scanned adverts (images, no text) are read with OCR.
A PDF can hold several posts; each becomes its own job.

A job is only published when its requirements and duties were both read;
anything else is skipped for the day and tried again on the next run.
Officers' names and phone numbers are not published.

Posts that are also in the DPSA circular are merged later by dedupe_jobs.py
(same reference number).

    python3 scrape_kznhealth.py             # scrape and write new rows to the sheet
    python3 scrape_kznhealth.py --dry-run   # print rows as JSON instead
"""

import argparse, base64, datetime, hashlib, html, json, os, re, subprocess, sys, tempfile

from scrape_dpsa import title_case, guess_category, find_province, short_salary, summary_line, norm_ws
from scrape_saps import (to_items, clean_apply, fallback_sections, retry, FETCH_JS, nice_date, strip_comments,
                         cell_text)

EMPLOYER = "Department of Health (KwaZulu-Natal)"
LIST_URL = "https://www.kznhealth.gov.za/vacancies/"
TODAY = datetime.date.today().isoformat()


# ----------------------------------------------------------------- vacancy tables

def parse_tables(page_html):
    rows = []
    for table in re.findall(r"<table.*?</table>", strip_comments(page_html), re.S | re.I):
        head = [cell_text(c).lower() for c in re.findall(r"<th[^>]*>(.*?)</th>", table, re.S | re.I)]
        trs = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S | re.I)
        if not head and trs:
            head = [cell_text(c).lower() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", trs[0], re.S | re.I)]
            trs = trs[1:]
        if not any("closing" in h for h in head):
            continue
        place_col = next((i for i, h in enumerate(head) if not re.search(r"circular|vacancy|description|closing", h)), None)
        for tr in trs:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)
            if len(cells) < len(head) or len(cells) < 3:
                continue
            pdf = re.search(r'href="([^"]+\.pdf)"', tr, re.I)
            date = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", cell_text(cells[-1]))
            if not pdf or not date:
                continue
            rows.append({
                "ref": cell_text(cells[0]),
                "vacancy": cell_text(cells[1]),
                "place": cell_text(cells[place_col]) if place_col is not None and place_col < len(cells) else "",
                "closing": f"{date.group(3)}-{int(date.group(2)):02d}-{int(date.group(1)):02d}",
                "pdf": pdf.group(1).replace(" ", "%20"),
            })
    return rows


# ----------------------------------------------------------------- reading adverts

def pdf_to_text(data, force_ocr=False):
    """Text layer of a PDF; scanned PDFs (no text) go through OCR."""
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "a.pdf")
        open(f, "wb").write(data)
        txt = subprocess.run(["pdftotext", "-layout", f, "-"], capture_output=True, text=True).stdout
        if len(re.sub(r"\s", "", txt)) >= 300 and not force_ocr:
            return txt
        subprocess.run(["pdftoppm", "-r", "300", "-gray", "-png", f, os.path.join(d, "p")], capture_output=True)
        pages = sorted(x for x in os.listdir(d) if x.startswith("p") and x.endswith(".png"))
        out = []
        for pth in pages:
            out.append(subprocess.run(["tesseract", os.path.join(d, pth), "-", "--psm", "6"],
                                      capture_output=True, text=True).stdout)
        return "\n\f".join(out)


LABEL = r"^[ \t\f]*{}\s*(?::\s*|\s{{3,}}|\s+[-–]\s+)(.*)$"   # "POST : X" / "POST    X" / "POST - X", not "Post-operative"
TITLE_LABELS = r"(?:POST(?:\s+TITLE)?|JOB\s+TITLE|DESIGNATION|POSITION)"
POST_SPLIT = re.compile(LABEL.format(TITLE_LABELS), re.M | re.I)


def field(block, names, multiline=False):
    m = re.search(LABEL.format("(?:" + names + ")"), block, re.M | re.I)
    if not m:
        return ""
    val = m.group(1).strip()
    if multiline or not val:                                 # value continues on the next lines
        rest = block[m.end():].splitlines()
        for l in rest[:6]:
            if not l.strip() or re.match(r"^\s*[A-Z][A-Z /&().]{3,40}\s*(?::|\s{3,})", l):
                if val: break
                continue
            val += " " + l.strip()
    return norm_ws(val)


def split_posts(text):
    """[(cover_text, [post_block, ...])]. Several posts per PDF are common."""
    starts = [m.start() for m in POST_SPLIT.finditer(text)]
    if not starts:
        return text, [text]
    blocks = [text[s:e] for s, e in zip(starts, starts[1:] + [len(text)])]
    return text[:starts[0]], blocks


# the sentence that says WHERE applications go (not the letterhead, not the general directions)
APPLY_RE = re.compile(r"(?:all\s+)?(?:applications?|documents)\s+(?:\w+\s+){0,3}?be\s+(?:\w+\s+){0,1}?"
                      r"(?:posted|forwarded|delivered|hand[- ]?delivered|e-?mailed|sent|directed|couriered|submitted)"
                      r"(?:\s+[\w/]+){0,6}?\s+(?:to|at|via|for\s+attention)\b"
                      r"|(?:please\s+)?(?:forward|direct|send|post)\s+(?:your\s+|all\s+)?applications?\s+to\b"
                      r"|courier\s+services?\s+or\s+hand[- ]?delivered\s+to\b", re.I)
PHONE = re.compile(r"(?:Tel(?:ephone)?|Fax|Cell|Contact(?:\s+No)?)\.?\s*(?:No\.?)?\s*:?\s*[\d()\s/\-]{7,}|\(?\b0\d{2}\)?[\s-]?\d{3}[\s-]?\d{4}\b", re.I)
PERSON = re.compile(r"\(?\s*(?:Attention|Attn|For the attention of)?\s*:?\s*\b(?:Mr|Mrs|Ms|Miss|Dr|Prof)\.?\s+(?:[A-Z]{1,3}\.?\s*){0,3}[A-Z][a-zA-Z'’-]+\)?", re.I)


def apply_text(text):
    m = APPLY_RE.search(text)
    if not m:
        return ""
    chunk = "\n".join(text[m.start():].splitlines()[:8])
    chunk = re.split(r"\n\s*\n\s*\n|\n\s*(?:Original copy signed|SIGNED COPY|_{5,}|(?:Acting\s+)?Chief Executive Officer|"
                     r"ASIBE HEALTHY|GROWING KWAZULU|CLOSING DATE|ENQUIRIES|NB\b|NOTE\b|\d+\.\s)", chunk, flags=re.I)[0]
    chunk = PERSON.sub("", PHONE.sub("", chunk))
    out = clean_apply(chunk)
    out = re.sub(r"\b(?:OR\s+)?(?:Email|E-mail)\s*:?\s*(?=OR\b|$)", "", out, flags=re.I)   # "Email:" left empty
    out = re.sub(r"\s{2,}", " ", out).strip(" ,;:-")
    return out[:500]


def ocr_fix(t):
    return t.replace("}", ")").replace("{", "(").replace("|", " ").strip()


def read_post(block, cover, row, full=""):
    title = ocr_fix(field(block, TITLE_LABELS))
    title = re.split(r"\s{3,}|\bREF(?:ERENCE)?\s*NO\b", title, flags=re.I)[0].strip(" :-")
    ref = field(block, r"REF(?:ERENCE)?\.?\s*(?:NO|NUMBER)\.?") or row["ref"]
    ref = re.split(r"\s{2,}|\(", ref)[0].strip(" .:")
    salary = field(block, r"SALARY(?:\s+(?:NOTCH|LEVEL|SCALE|RANGE|PACKAGE))?|REMUNERATION|PACKAGE|STIPEND", multiline=True)
    if not re.search(r"R\s?\d", salary):
        m = re.search(r"R\s?\d{1,3}(?:[ ,]\d{3})+(?:\.\d{2})?[^\n]{0,60}?(?:per\s+(?:annum|month)|p\.?a\.?)", block, re.I)
        salary = m.group(0) if m else salary
    place = field(block, r"CENTRE|FACILITY|INSTITUTION|STATION") or row["place"]
    fb = fallback_sections(block)
    return {"title": title, "ref": ref, "salary": salary, "place": place,
            "requirements": fb["req"], "duties": fb["duty"],
            "apply": apply_text(block) or apply_text(cover) or apply_text(full)}


def read_advert(text, row):
    cover, blocks = split_posts(text)
    posts = [read_post(b, cover, row, text) for b in blocks]
    if len(posts) == 1 and not posts[0]["title"]:
        posts[0]["title"] = row["vacancy"]
    return [p for p in posts if p["title"]]


# ----------------------------------------------------------------- rows

def job_id(ref, title):
    key = re.sub(r"[^A-Za-z0-9]+", "-", ref or "").strip("-")
    tkey = hashlib.sha1(title.lower().encode()).hexdigest()[:5]
    return f"KZNH-{key.upper() or 'X'}-{tkey}"


def build_row(row, post):
    title = title_case(post["title"]) if post["title"].isupper() else norm_ws(post["title"])
    place = post["place"] or row["place"]
    emp_type = "Contract" if re.search(r"contract|sessional|locum", title + " " + post["salary"], re.I) else "Permanent"
    pay = short_salary(post["salary"]) or norm_ws(post["salary"])[:60]
    about = [summary_line(EMPLOYER, title, 1, place, emp_type, post["salary"], ""), ""]
    if post["apply"]:
        about.append("How to apply: " + post["apply"])
    else:
        about.append("How to apply: as set out in the official advert (PDF).")
    about.append("Reference number to quote: " + post["ref"])
    about.append("Closing date: " + nice_date(row["closing"]))
    about.append("Use the new Z83 form and attach a detailed CV.")
    jid = job_id(post["ref"], title)
    return {
        "id": jid, "job_title": title, "employer": EMPLOYER,
        "category": guess_category(title, EMPLOYER) if guess_category(title, EMPLOYER) != "Government" else "Medical",
        "province": "KwaZulu-Natal", "location": place[:140], "employment_type": emp_type, "salary": pay,
        "posted_date": TODAY, "closing_date": row["closing"], "reference_no": jid,
        "about_role": "\n".join(about), "responsibilities": "\n".join(post["duties"]),
        "requirements": "\n".join(post["requirements"]), "official_apply_url": row["pdf"],
        "source_url": LIST_URL, "featured": "", "status": "live",
    }


def advert_rows(data, row):
    """Read the text layer; if posts are missing sections (images pasted into the PDF), read it again with OCR."""
    text = pdf_to_text(data)
    rows, ok = rows_from_advert(text, row, quiet=True)
    if not ok:
        rows2, ok2 = rows_from_advert(pdf_to_text(data, force_ocr=True), row, quiet=True)
        if len(rows2) > len(rows):
            rows, ok = rows2, ok2
    if not ok:
        rows_from_advert(text, row)                         # log what was skipped
    return rows


def rows_from_advert(text, row, quiet=False):
    out, complete = [], True
    for post in read_advert(text, row):
        if not post["requirements"] or not post["duties"]:
            complete = False
            if not quiet:
                print(f"  skipped (could not read requirements/duties): {post['title'][:60]} — {row['pdf']}", file=sys.stderr)
            continue
        out.append(build_row(row, post))
    if quiet:
        return out, complete and bool(out)
    return out


# ----------------------------------------------------------------- run

def scrape():
    from playwright.sync_api import sync_playwright
    out = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        def load():
            pg.goto(LIST_URL, wait_until="load", timeout=180000)
            return pg.content()
        h = retry(load) or ""
        rows = [r for r in parse_tables(h) if r["closing"] >= TODAY]
        print(f"  KZN Health: {len(rows)} open adverts", file=sys.stderr)
        for r in rows:
            try:
                b64 = retry(lambda: pg.evaluate(FETCH_JS, r["pdf"]))
                if not b64:
                    print(f"  skipped (advert would not download): {r['vacancy'][:60]}", file=sys.stderr)
                    continue
                out += advert_rows(base64.b64decode(b64), r)
            except Exception as e:
                print(f"  skipped (error): {r['vacancy'][:60]}: {str(e)[:150]}", file=sys.stderr)
        b.close()
    seen, final = set(), []
    for r in out:
        if r["id"] not in seen:
            seen.add(r["id"]); final.append(r)
    return final


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    rows = scrape()
    if a.dry_run:
        json.dump(rows, sys.stdout, ensure_ascii=False, indent=1)
        print(f"\n{len(rows)} KZN Health posts", file=sys.stderr)
        return
    import sheet_writer
    wrote, updated = sheet_writer.upsert_jobs(rows, update_fields=("closing_date", "about_role"))
    print(f"KZN Health: {len(rows)} open posts, {wrote} new rows, {updated} updated.", file=sys.stderr)


if __name__ == "__main__":
    main()
