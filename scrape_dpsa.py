#!/usr/bin/env python3
"""
scrape_dpsa.py  —  OnboardingSA

Reads the DPSA Public Service Vacancy Circular (published weekly at
https://www.dpsa.gov.za/newsroom/psvc/) and writes one row per post to the
Jobs sheet, in the same columns every other scraper uses.

How it works
  1. Open the circular index and take the newest few circulars
     (older ones have closed; the sheet de-duplicates anything already saved).
  2. On each circular page, collect the per-department PDFs (a.pdf, b.pdf ...).
  3. Convert each PDF to text with `pdftotext -layout` (poppler-utils) and split
     it into posts using the standard field labels (POST, SALARY, CENTRE,
     REQUIREMENTS, DUTIES, ENQUIRIES, APPLICATIONS, NOTE, CLOSING DATE ...).
  4. Map each post to the sheet columns. ENQUIRIES (named officials and their
     direct phone numbers) is deliberately not published.

Runs daily from the GitHub workflow. Test locally against a downloaded PDF:

    python3 scrape_dpsa.py --pdf "PSV CIRCULAR 35 of 2026.pdf" --dry-run
"""

import argparse, datetime, html, json, os, re, subprocess, sys, tempfile, time
from urllib.parse import urljoin

BASE = "https://www.dpsa.gov.za"
INDEX_URL = BASE + "/newsroom/psvc/"
CIRCULARS_TO_CHECK = 3          # newest N circulars; posts usually close within ~2 weeks
UA = {"User-Agent": "Mozilla/5.0 (compatible; OnboardingSA job board; +https://www.onboardingsa.co.za)"}

PROVINCES = ["Eastern Cape", "Free State", "Gauteng", "KwaZulu-Natal", "Limpopo",
             "Mpumalanga", "North West", "Northern Cape", "Western Cape"]

# Towns that often appear in CENTRE lines without a province name.
TOWN_PROVINCE = {
    "pretoria": "Gauteng", "tshwane": "Gauteng", "johannesburg": "Gauteng", "midrand": "Gauteng",
    "centurion": "Gauteng", "soweto": "Gauteng", "germiston": "Gauteng", "benoni": "Gauteng",
    "vereeniging": "Gauteng", "krugersdorp": "Gauteng", "randburg": "Gauteng", "boksburg": "Gauteng",
    "durban": "KwaZulu-Natal", "pietermaritzburg": "KwaZulu-Natal", "richards bay": "KwaZulu-Natal",
    "newcastle": "KwaZulu-Natal", "ladysmith": "KwaZulu-Natal", "ulundi": "KwaZulu-Natal",
    "port shepstone": "KwaZulu-Natal", "empangeni": "KwaZulu-Natal", "ethekwini": "KwaZulu-Natal",
    "cape town": "Western Cape", "bellville": "Western Cape", "george": "Western Cape",
    "stellenbosch": "Western Cape", "paarl": "Western Cape", "worcester": "Western Cape",
    "oudtshoorn": "Western Cape", "elsenburg": "Western Cape", "malmesbury": "Western Cape",
    "gqeberha": "Eastern Cape", "port elizabeth": "Eastern Cape", "east london": "Eastern Cape",
    "mthatha": "Eastern Cape", "bhisho": "Eastern Cape", "makhanda": "Eastern Cape",
    "komani": "Eastern Cape", "queenstown": "Eastern Cape", "middelburg (ec)": "Eastern Cape",
    "bloemfontein": "Free State", "welkom": "Free State", "botshabelo": "Free State",
    "ficksburg": "Free State", "bethlehem": "Free State", "kroonstad": "Free State",
    "polokwane": "Limpopo", "giyani": "Limpopo", "thohoyandou": "Limpopo", "tzaneen": "Limpopo",
    "lephalale": "Limpopo", "makhado": "Limpopo", "mokopane": "Limpopo", "seshego": "Limpopo",
    "lebowakgomo": "Limpopo", "phalaborwa": "Limpopo", "modimolle": "Limpopo",
    "groblersdal": "Limpopo", "jane furse": "Limpopo",
    "mbombela": "Mpumalanga", "nelspruit": "Mpumalanga", "emalahleni": "Mpumalanga",
    "witbank": "Mpumalanga", "secunda": "Mpumalanga", "ermelo": "Mpumalanga",
    "mahikeng": "North West", "mafikeng": "North West", "rustenburg": "North West",
    "klerksdorp": "North West", "potchefstroom": "North West", "vryburg": "North West",
    "kimberley": "Northern Cape", "upington": "Northern Cape", "springbok": "Northern Cape",
    "de aar": "Northern Cape", "kuruman": "Northern Cape",
}

FIELD_LABELS = {
    "SALARY": "salary", "STIPEND": "stipend", "CENTRE": "centre",
    "REQUIREMENTS": "requirements", "DUTIES": "duties", "DUTES": "duties",
    "ENQUIRIES": "enquiries", "EENQUIRIES": "enquiries", "ENQUIRY": "enquiries",
    "APPLICATIONS": "applications", "APPLICATION": "applications",
    "NOTE": "note", "NOTES": "note", "CLOSING DATE": "closing",
    "FOR ATTENTION": "attention", "ATTENTION": "attention",
}
LABEL_RE = re.compile(r"^\s*(" + "|".join(sorted(map(re.escape, FIELD_LABELS), key=len, reverse=True))
                      + r")\s*:\s?(.*)$")
BARE_LABEL_RE = re.compile(r"^\s*(ENQUIRIES|APPLICATIONS|CLOSING DATE|FOR ATTENTION)\s+(?=[A-Z0-9(])(.*)$")
POST_RE = re.compile(r"^\s*POST\s+(\d{1,2})\s*/\s*(\d{1,3})\s*:?\s*(.*)$")
ANNEX_RE = re.compile(r"^\s*ANNEXURE\s+([A-Z]{1,2})\s*$")
PROVADMIN_RE = re.compile(r"^\s*PROVINCIAL ADMINISTRATION\s*:\s*([A-Z][A-Z \-]+?)\s*$")
PAGE_NO_RE = re.compile(r"^\s*\d{1,3}\s*$")
SECTION_RE = re.compile(r"^\s*(OTHER POSTS?|MANAGEMENT ECHELON|SENIOR MANAGEMENT SERVICE|"
                        r"GRADUATE INTERNSHIP PROGRAMME|INTERNSHIP PROGRAMME|LEARNERSHIP.*)\s*$")
DEPT_RE = re.compile(r"^\s*((?:DEPARTMENT|OFFICE|NATIONAL|PROVINCIAL TREASURY|GOVERNMENT|POLICE|"
                     r"INDEPENDENT|STATISTICS|WESTERN CAPE|GAUTENG|COMMISSION|THE PRESIDENCY|"
                     r"STATE|PUBLIC|SOUTH AFRICAN|CIVILIAN|MILITARY)[A-Z ,&()\-'’]*)\s*$")
REF_RE = re.compile(r"\bREF(?:ERENCE)?\.?\s*(?:NO|NUMBER)?\.?\s*:?\s*(?=[^\n]{0,25}\d)"
                    r"([A-Z0-9][A-Z0-9/.\-_]*(?:\s[A-Z0-9/.\-_]*[0-9/][A-Z0-9/.\-_]*)*)", re.I)
REF_LINE_RE = re.compile(r"\b(?:REF(?:ERENCE)?|RE)\.?\s*(?:NO|NUMBER)\.?\s*:?\s*([^()\n]*)", re.I)


def line_refs(lines):
    """Reference numbers written as 'REF NO: XYZ 12/3' at the end of a title or centre line."""
    out = []
    raw = [norm_ws(l) for l in lines if norm_ws(l)]
    lines = []
    for ln in raw:                      # "... REF" / "NO: DD CPS" split over two lines
        if lines and re.search(r"\b(?:REF|RE)\.?$", lines[-1], re.I):
            lines[-1] += " " + ln
        else:
            lines.append(ln)
    for i, ln in enumerate(lines):
        for m in REF_LINE_RE.finditer(ln):
            val = m.group(1).strip(" .:;,“”\"'")
            if not val and i + 1 < len(lines):                 # "REF NO:" wrapped onto the next line
                val = re.split(r"[()]", lines[i + 1])[0].strip(" .:;,")
            if val and i + 1 < len(lines) and len(val) <= 6 and re.fullmatch(r"[A-Z0-9/.\-:]{1,12}", lines[i + 1]):
                val += " " + lines[i + 1]                       # "REF NO: DD" / "CPS"
            val = re.sub(r"\s*:\s*", ": ", val)
            if val and len(val) <= 40:
                out.append(val)
    return out


COUNT_RE = re.compile(r"\(\s*X?\s*(\d+)\s*POSTS?(?:\s+AVAILABLE)?\s*\)", re.I)
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july",
                                      "august", "september", "october", "november", "december"], 1)}

CATEGORY_RULES = [
    ("Internship", r"\bintern|learner|graduate programme|trainee"),
    ("Medical", r"nurse|nursing|medical|doctor|pharmac|clinical|radiograph|physiotherap|dietitian|paramedic|"
                r"psychometr|laborator|"
                r"dental|health|emergency care|psycholog|occupational therap|speech|audiolog|optometr"),
    ("Legal", r"legal|attorney|advocate|prosecutor|magistrate|law\b|litigation|court"),
    ("IT", r"\bict\b|information technology|software|network|systems? admin|programmer|developer|"
           r"\bit\b|cyber|data(base)? |business intelligence"),
    ("Engineering", r"engineer|technician|technologist|artisan|electrician|plumber|mechanic|"
                    r"draughts|surveyor|built environment|infrastructure|architect"),
    ("Finance", r"financ|account|audit|budget|treasury|revenue|supply chain|procurement|sourcing|forensic|"
                r"remuneration|payroll|asset|bookkeep|economist|salar"),
    ("Education", r"educator|teacher|lecturer|principal|education|curriculum|training"),
    ("Social Services", r"social work|social auxiliary|community development|child and youth care|rehabilitation|"
                        r"probation"),
    ("Agriculture", r"agricultur|veterinar|animal|farm|crop|soil|forestry|fisheries|environment|land reform"),
    ("Logistics", r"transport officer|logistic|dock|harbour|fleet|warehouse|stores|driver"),
    ("Security", r"security|safety|correctional|police|traffic|enforcement|inspector|firefight"),
    ("HR", r"human resource|\bhr\b|labour relations|employee relations|recruitment|organisational development|"
           r"skills development|personnel"),
    ("Admin", r"admin|clerk|secretar|registry|receptionist|office aid|messenger|typist|librar|telecom|"
              r"customer|client service|employer services|coordinator|co-ordinator|facilitator|programme officer|"
              r"data captur|personal assistant|executive assistant|records"),
    ("Management", r"director|manager|head of|chief executive|deputy director"),
    ("General Worker", r"cleaner|general worker|household aid|operator|food service|porter|gardener|handyman|"
                       r"groundsman|laundry|housekeep|cook|tradesman aid"),
]


# ----------------------------------------------------------------- helpers

def norm_ws(s):
    return re.sub(r"[ \t\u00a0]+", " ", (s or "").replace("`", " ")).strip()


def join_lines(lines):
    """Join wrapped PDF lines into readable text, fixing hyphenated breaks."""
    out = ""
    for ln in (norm_ws(l) for l in lines):
        if not ln:
            continue
        if not out:
            out = ln
        elif out.endswith("-") and not out.endswith(" -") and ln[:1].islower():
            out = out[:-1] + ln            # "pre-" + "entry"  -> "pre-entry"? keep simple: re-join word
        else:
            out += " " + ln
    return out.strip()


def title_case(s):
    small = {"and", "of", "the", "in", "for", "to", "on", "at", "an", "or", "with", "by"}
    words = []
    for i, w in enumerate(s.lower().split()):
        if w.upper().strip("()[],.:;") in {"MIS", "ECM", "CHC", "CDC", "TVET", "NQF", "ICT", "HR", "IT", "UIF", "SMS", "EE", "PPP", "CEO", "CFO", "SCM", "GIS",
                         "OSD", "PHC", "ICU", "TB", "HIV", "NSG", "SAPS", "ECD", "MEC", "DDG",
                         "IPD", "EMS", "EHP", "PA", "UI"}:
            words.append(w.upper())
        elif i and w in small:
            words.append(w)
        else:
            cap = lambda x: x[:1].upper() + x[1:] if not x[:1] in "(\"'" else x[:2].upper() + x[2:]
            words.append(re.sub(r"(?<=[-–/])([a-z])", lambda m: m.group(1).upper(),
                                "/".join(cap(x) for x in w.split("/"))))
    return " ".join(words)


def parse_date(text):
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([A-Za-z]+)\s+(\d{4})", text or "")
    if not m or m.group(2).lower() not in MONTHS:
        return ""
    try:
        return datetime.date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1))).isoformat()
    except ValueError:
        return ""


def find_province(*texts, default=""):
    for t in texts:
        low = (t or "").lower().replace("kwazulu natal", "kwazulu-natal")
        for p in PROVINCES:
            if p.lower() in low:
                return p
    for t in texts:
        low = (t or "").lower()
        for town, p in TOWN_PROVINCE.items():
            if re.search(r"\b" + re.escape(town) + r"\b", low):
                return p
    return default


def guess_category(title, dept):
    t = (title or "").lower()
    for cat, pat in CATEGORY_RULES:
        if re.search(pat, t):
            return cat
    return "Government"


def employment_type(text):
    t = (text or "").lower()
    if re.search(r"intern|learnership|graduate programme|trainee", t):
        return "Internship"
    if re.search(r"contract|fixed[- ]term|\d+\s*(months|years?)\b", t):
        return "Contract"
    if "part-time" in t or "part time" in t:
        return "Part-time"
    return "Permanent"


def clean_dept(name):
    name = norm_ws(name).strip(" :")
    name = re.sub(r"\s*\((?:[A-Z]{2,8})\)\s*$", "", name)          # "(DOA)"
    return title_case(name)


# ----------------------------------------------------------------- tidy-up (no AI, fixed rules)

ABBREV = r"(?:e\.g|i\.e|etc|No|Nr|incl|approx|Dr|Mr|Mrs|Ms|Prof|St|vs|Ref|Pty|Ltd|cf)"
SENT_SPLIT = re.compile(r"(?<!\b" + "e.g" + r")(?<=[.!?])\s+(?=[A-Z(•\-])")
GROUP_HEAD = re.compile(r"^([A-Z][A-Za-z/&()'’,\- ]{2,60}?)\s*:\s+(.+)$")
FILLER = [
    (r"^(?:applicants|candidates|the candidate|the successful candidate|incumbents?)\s+(?:must|should|will)\s+"
     r"(?:be in possession of|have|possess|hold)\s+", ""),
    (r"^(?:must|should)\s+(?:be in possession of|have|possess|hold)\s+", ""),
    (r"^(?:be in possession of|in possession of)\s+", ""),
    (r"^(?:the )?minimum (?:educational )?(?:qualification|requirement)s?\s*(?:is|are)?\s*:?\s*", ""),
    (r"\b(?:a\s+)?minimum of\s+", "at least "),
    (r"\b(\w+)\s+\(\1\)", r"\1"),                  # "three (three)"
    (r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\s*\(?(\d{1,2})\)?\s+(?=years?|months?)", r"\2 "),
    (r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\s+(?=years?['’]?\s)", lambda m: str(
        ["one","two","three","four","five","six","seven","eight","nine","ten"].index(m.group(1).lower()) + 1) + " "),
    (r"\s+", " "),
]


def _sentences(text):
    text = norm_ws(text.replace("\n", " "))
    # protect abbreviations so "e.g. Excel" does not split
    prot = re.sub(r"\b(" + ABBREV[3:-1] + r")\.", lambda m: m.group(1) + "\u2024", text, flags=re.I)
    prot = re.sub(r"\betc\u2024\s+(?=[A-Z][A-Za-z ,&/'’\-]{2,60}:\s)", "etc. ", prot)
    prot = re.sub(r"\s*/\s+", "/", prot)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(•\-\d])", prot)
    return [x.replace("\u2024", ".").strip(" •-") for x in parts if x.strip(" •-.")]


def _tidy(sentence):
    t = sentence.strip()
    for pat, rep in FILLER:
        t = re.sub(pat, rep, t, flags=re.I)
    t = t.strip()
    return (t[:1].upper() + t[1:]) if t else t


LIST_HEADS = (r"(?:Job[- ]Related |Generic |Technical |Behavioural |Personal )?"
              r"(?:Knowledge|Skills|Competencies|Competency|Attributes|Abilities|Skills and Competencies|"
              r"Knowledge and Skills)")
EMBEDDED_HEAD = re.compile(r"(?<=[a-z0-9)’'.])\s+((?:Essential |Key |Core |Generic |Technical |Behavioural |Personal |Inherent |Job[- ]Related )?"
                           r"(?:Knowledge|Skills|Competenc[a-z]*|Attributes|Requirements)"
                           r"(?:,?\s+(?:and\s+|And\s+)?[A-Za-z]+){0,6}?\s*(?:\([^)]*\))?)\s*:\s")


def _split_list(item):
    """Split 'A, B, C (x, y), D' on top-level commas."""
    out, depth, cur = [], 0, ""
    for ch in item:
        depth += ch == "("
        depth -= ch == ")"
        if ch in ",;" and depth <= 0:
            out.append(cur.strip()); cur = ""
        else:
            cur += ch
    out.append(cur.strip())
    merged = []
    for o in (x for x in out if x):
        if merged and re.match(r"(?:and|or|etc)\b", o, re.I):      # "theory, principles, and practices"
            merged[-1] += ", " + o
        else:
            merged.append(o)
    return merged


def to_bullets(text, max_items_per_group=12, split_lists=False):
    """Turn a long advert paragraph into short bullet lines (one per line).
    'Knowledge: A. B. C.' style runs become one bullet: 'Knowledge: A, B, C.'"""
    if not text:
        return ""
    bullets, head, items = [], None, []

    def close_group():
        nonlocal head, items
        if head and items:
            if split_lists and any(len(i) > 300 for i in items):
                flat = []
                for it in items:
                    parts = _split_list(it.rstrip(".")) if len(it) > 300 else [it]
                    flat.extend(parts if len(parts) >= 5 else [it])
                items = [_tidy(x) for x in flat if x]
            if len(items) == 1:
                bullets.append(f"{head}: {items[0].rstrip('.;, ')}.")
            else:
                bullets.append(f"{head}:")
                bullets.extend(i.rstrip(".;, ") for i in items[:max_items_per_group * 2])
        head, items = None, []

    text = text or ""

    def _brk(m):
        before = text[:m.start()].rstrip()
        return (" " if before.endswith(".") else ". ") + m.group(1) + ": "
    text = EMBEDDED_HEAD.sub(_brk, text)
    if split_lists:     # ", Knowledge:" / ", Skills:" mid-sentence starts a new group
        text = re.sub(r",\s+(?=" + LIST_HEADS + r"\s*(?:\([^)]*\))?\s*:)", ". ", text)
    for sent in _sentences(text):
        m = GROUP_HEAD.match(sent)
        if m and re.fullmatch(LIST_HEADS + r"\s*(?:\([^)]*\))?", m.group(1).strip(), re.I):
            parts = _split_list(m.group(2).rstrip("."))
            if len(parts) >= 3:
                close_group()
                head, items = norm_ws(m.group(1)), [_tidy(x) for x in parts]
                continue
        if m and len(m.group(1).split()) <= 8 and not re.search(r"\d{4}", m.group(1)):
            close_group()
            head = norm_ws(m.group(1))
            items = [_tidy(m.group(2))]
            continue
        if head and len(sent) <= 140:
            items.append(_tidy(sent))
            continue
        close_group()
        t = _tidy(sent)
        if t:
            bullets.append(t if t.endswith((".", "!", "?", ")")) else t + ".")
    close_group()
    # de-duplicate and drop empties
    seen, out = set(), []
    for b in bullets:
        k = b.lower()
        if len(b) > 3 and k not in seen:
            seen.add(k); out.append(b.replace(";", ","))      # ';' would split a bullet on the page
    return "\n".join(out)


def money(salary_text):
    m = re.search(r"R\s?(\d{1,3}(?:[ ,]\d{3})+|\d{4,})(?:\.\d+)?(?:\s*[-–]\s*R?\s?(\d{1,3}(?:[ ,]\d{3})+|\d{4,}))?"
                  r"\s*(per annum|per month|p\.?a\.?|pm)?", salary_text or "", re.I)
    if not m:
        return ""
    fmt = lambda x: "R" + f"{int(re.sub(r'[ ,]', '', x)):,}"
    amt = fmt(m.group(1)) + (f" – {fmt(m.group(2))}" if m.group(2) else "")
    per = (m.group(3) or "").lower()
    return amt + (" a month" if "month" in per or per == "pm" else " a year" if per else "")


def short_salary(text):
    """Card-sized salary: 'R1,885,710 a year (Level 15)'. The full wording stays in the advert."""
    pay = money(text)
    hourly = re.findall(r"R\s?(\d[\d ,]*(?:\.\d+)?)\s*(?:per|an|/)\s*hour", text or "", re.I)
    if not pay and hourly:
        low = min(float(re.sub(r"[ ,]", "", h)) for h in hourly)
        return f"From R{low:,.0f} an hour"
    if not pay:
        return norm_ws(re.split(r"[(.,;]", text or "")[0])[:60]
    lvl = re.search(r"\bLevel\s*(\d{1,2})", text or "", re.I)
    return pay + (f" (Level {int(lvl.group(1))})" if lvl else "")


def summary_line(employer, title, count, location, emp_type, salary, intro):
    the = "The " if re.match(r"(Department|Office|National|Provincial|Government)\b", employer) else ""
    art = "an" if title[:1].lower() in "aeiou" else "a"
    if emp_type == "Internship":
        what = (f"{count} internships" if count > 1 else "an internship") + f" in {title}"
        s = f"{the}{employer} is offering {what}"
    else:
        what = f"{count} {title} posts" if count > 1 else f"{art} {title}"
        s = f"{the}{employer} is hiring {what}"
    unit = re.search(r"(?:Directorate|Chief Directorate|Sub-Directorate|Component|Unit|Branch|Division)\s*:\s*([^.\n(]+)",
                     intro or "", re.I)
    if unit:
        s += f" in {norm_ws(unit.group(1))}"
    if location and len(location) < 80:
        s += f", based in {location}"
    s += "."
    pay = money(salary)
    if emp_type == "Internship":
        if pay:
            s += f" The stipend is {pay}."
    elif emp_type:
        art2 = "an" if emp_type[:1].lower() in "aeiou" else "a"
        s += f" This is {art2} {emp_type.lower()} post" + (f", paying {pay}" if pay else "") + "."
    return s


# ----------------------------------------------------------------- parsing

def split_posts(text):
    """Yield raw post dicts from layout text of a circular or one department PDF."""
    lines = text.splitlines()
    dept = ""
    province_ctx = ""
    dept_fields = {}            # department-level CLOSING DATE / NOTE that apply to all its posts
    post = None
    field = None
    prev_blank = True

    def flush():
        nonlocal post
        if post:
            post["dept"] = post.get("dept") or dept
            post["province_ctx"] = province_ctx
            post["dept_closing"] = dept_fields.get("closing", "")
            for k in ("applications", "attention"):        # department-wide apply instructions
                if not post["fields"].get(k) and dept_fields.get(k):
                    post["fields"][k] = [dept_fields[k]]
            yield_list.append(post)
        post = None

    yield_list = []
    for i, raw in enumerate(lines):
        line = raw.replace("\f", "")
        stripped = line.strip()
        next_blank = (i + 1 >= len(lines)) or not lines[i + 1].strip()

        if not stripped:
            prev_blank = True
            continue
        if PAGE_NO_RE.match(line):
            prev_blank = True
            continue

        m = ANNEX_RE.match(line)
        if m:
            flush(); field = None
            dept, dept_fields = "", {}
            prev_blank = True
            continue
        m = PROVADMIN_RE.match(line)
        if m:
            flush(); field = None
            province_ctx = find_province(title_case(m.group(1)))
            dept, dept_fields = "", {}
            prev_blank = True
            continue
        if SECTION_RE.match(line):
            prev_blank = True
            continue
        # Department heading: an all-caps line standing on its own between blank lines,
        # outside a post's title block.
        if (prev_blank and DEPT_RE.match(line) and not LABEL_RE.match(line)
                and (field not in ("title",)) and stripped == stripped.upper()):
            if len(stripped) < 100 and not stripped.endswith(":"):
                flush(); field = None
                dept = clean_dept(stripped)
                dept_fields = {}
                prev_blank = True
                continue

        m = POST_RE.match(line)
        if m:
            flush()
            post = {"circular": m.group(1), "post_no": m.group(2), "title_lines": [m.group(3)],
                    "fields": {}}
            field = "title"
            prev_blank = False
            continue

        m = LABEL_RE.match(line) or BARE_LABEL_RE.match(line)
        if m:
            key = FIELD_LABELS[m.group(1).strip()]
            if post is None:
                field = ("dept", key)
                dept_fields[key] = m.group(2)
            else:
                field = key
                post["fields"].setdefault(key, [])
                if post["fields"][key]:
                    post["fields"][key].append("")
                post["fields"][key].append(m.group(2))
            prev_blank = False
            continue

        # continuation line
        if post is not None:
            if field == "title":
                post["title_lines"].append(stripped)
            elif field:
                post["fields"].setdefault(field, []).append(stripped)
        elif isinstance(field, tuple):
            dept_fields[field[1]] = dept_fields.get(field[1], "") + " " + stripped
        prev_blank = False

    flush()
    return yield_list


def build_row(p, circular_no, posted_date, source_url, pdf_url):
    f = {k: join_lines(v) for k, v in p["fields"].items()}
    is_stipend = "stipend" in f and "salary" not in f
    if is_stipend:
        f["salary"] = f["stipend"]
    title_block = [norm_ws(x) for x in p["title_lines"] if norm_ws(x)]
    head = " ".join(title_block)

    # Title = upper-case part of the block, before "REF NO" / "(X n POSTS)".
    caps = []
    for ln in title_block:
        if ln.upper() == ln or not caps:
            caps.append(ln)
        else:
            break
    title_raw = " ".join(caps)
    title_raw = re.split(r"[“\"]?\b(?:REF\b(?=\.?\s*(?:NO|NUMBER)?\.?\s*:?\s*[^\n]{0,25}\d)|REF(?:ERENCE)?\.?\s*(?:NO|NUMBER)\b|RE\s+NO\b)",
                         title_raw, flags=re.I)[0]
    title_raw = title_raw.strip(" \"“”'’")
    title_raw = COUNT_RE.sub("", title_raw)
    title_raw = re.sub(r"\(\s*X\s*\d+\s*$", "", title_raw).strip(" :-,")
    title = title_case(re.sub(r"\s+", " ", title_raw))

    extra_lines = [ln for ln in title_block[len(caps):]]
    count = COUNT_RE.search(head)
    count = int(count.group(1)) if count else 1

    refs = line_refs(title_block) or line_refs(p["fields"].get("centre", [])) or REF_RE.findall(head)
    refs = [re.sub(r"\s+", " ", r).strip(" .") for r in refs]
    seen = set()
    refs = [r for r in refs if not (r in seen or seen.add(r))]

    centre = f.get("centre", "")
    centre_clean = "; ".join(norm_ws(x) for x in p["fields"].get("centre", []) if norm_ws(x))
    centre_clean = REF_RE.sub("", centre_clean)
    centre_clean = COUNT_RE.sub("", centre_clean)
    centre_clean = re.sub(r"\(\s*X\s*\d+\s*POSTS?\s*\)|\(\s*\d+\s*POSTS?\s*\)", "", centre_clean, flags=re.I)
    centre_clean = re.sub(r"\s*:\s*(?=\s|$)", " ", centre_clean)
    centre_clean = re.sub(r"\s*;\s*", "; ", norm_ws(centre_clean))
    centre_clean = re.sub(r"(;\s*)+", "; ", centre_clean).strip(" ,;:")
    if len(centre_clean) > 140:
        centre_clean = centre_clean[:137].rsplit(" ", 1)[0] + "…"

    dept = p.get("dept") or "Public Service"
    province = find_province(centre, p.get("province_ctx", ""), f.get("applications", ""),
                             default=p.get("province_ctx", ""))
    if p.get("province_ctx"):
        employer = dept if dept.lower().startswith(p["province_ctx"].lower()) else f"{dept} ({p['province_ctx']})"
    else:
        employer = dept

    closing = parse_date(f.get("closing", "")) or parse_date(p.get("dept_closing", ""))
    if not closing and posted_date:      # no date anywhere: assume the usual ~3 weeks, never "open forever"
        closing = (datetime.date.fromisoformat(posted_date) + datetime.timedelta(days=21)).isoformat()

    # about_role: one-line summary + how to apply. ENQUIRIES (named officials) is left out on purpose.
    emp_type = "Internship" if is_stipend else employment_type(head + " " + f.get("salary", ""))
    intro = join_lines(extra_lines)
    about = [summary_line(employer, title, count, centre_clean, emp_type, f.get("salary", ""), intro)]
    other_intro = [x for x in _sentences(intro)
                   if not re.match(r"(Directorate|Chief Directorate|Sub-Directorate|Component|Unit|Branch|Division)\s*:", x, re.I)]
    if other_intro:
        about.append(" ".join(other_intro))
    about.append("")
    if f.get("applications"):
        about.append("How to apply: " + norm_ws(f["applications"]))
    if f.get("attention"):
        about.append("For attention: " + norm_ws(f["attention"]))
    if refs:
        about.append("Reference number" + ("s" if len(refs) > 1 else "") + " to quote: " + ", ".join(refs))
    if closing:
        cl_txt = f.get("closing") or p.get("dept_closing", "")
        about.append("Closing date: " + norm_ws(cl_txt))
    about.append("Use the new Z83 form and attach a detailed CV.")
    if f.get("note"):
        about.append("Note: " + norm_ws(f["note"]))

    apply_url = pdf_url
    m = re.search(r"(https?://[^\s,;)]+|www\.[^\s,;)]+)", f.get("applications", ""))
    if m:
        u = m.group(1).rstrip(".")
        apply_url = u if u.startswith("http") else "https://" + u

    psv_id = f"PSV-{posted_date[:4] or 'X'}-{circular_no}-{int(p['post_no']):02d}"
    row = {
        "id": psv_id,
        "job_title": title,
        "employer": employer,
        "category": "Internship" if is_stipend else guess_category(title, dept),
        "province": province or "National",
        "location": centre_clean,
        "employment_type": emp_type,
        "salary": short_salary(f.get("salary", "")),
        "posted_date": posted_date,
        "closing_date": closing,
        # The site uses reference_no as the page id, so it must be short, unique and URL-safe.
        # The department's own reference numbers (what applicants must quote) are in about_role.
        "reference_no": psv_id,
        "about_role": "\n".join(about),
        "responsibilities": to_bullets(f.get("duties", "")),
        "requirements": to_bullets(f.get("requirements", ""), split_lists=True),
        "official_apply_url": apply_url,
        "source_url": source_url,
        "featured": "",
        "status": "live",
    }
    return row


def _fill_from_siblings(posts):
    """Some departments state the closing date / how to apply once for a group of posts.
    Give posts that lack them the value most of their department's other posts use."""
    from collections import Counter, defaultdict
    by_dept = defaultdict(list)
    for p in posts:
        by_dept[(p.get("dept"), p.get("province_ctx"))].append(p)
    for group in by_dept.values():
        for key in ("closing", "applications"):
            vals = Counter(join_lines(p["fields"][key]) for p in group if p["fields"].get(key))
            if not vals:
                continue
            common = vals.most_common(1)[0][0]
            for p in group:
                if not p["fields"].get(key) and not (key == "closing" and p.get("dept_closing")):
                    p["fields"][key] = [common]
    return posts


def parse_pdf_text(text, circular_no, posted_date, source_url, pdf_url, dept_hint="", province_hint=""):
    rows = []
    for p in _fill_from_siblings(split_posts(text)):
        if not p.get("dept") and dept_hint:
            p["dept"] = dept_hint
        if not p.get("province_ctx") and province_hint:
            p["province_ctx"] = province_hint
        if not p["fields"].get("requirements") and not p["fields"].get("duties"):
            continue                                  # not a real post (e.g. stray "POST" in a note)
        rows.append(build_row(p, circular_no, posted_date, source_url, pdf_url))
    return rows


def pdf_to_text(path):
    return subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True,
                          text=True, check=True).stdout


# ----------------------------------------------------------------- web

def http_get(url, binary=False):
    import requests
    for attempt in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=60)
            r.raise_for_status()
            return r.content if binary else r.text
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))


def latest_circular_urls(n):
    page = http_get(INDEX_URL)
    links = re.findall(r"href=['\"](/newsroom/psvc/circular-(\d+)-of-(\d{4})/)['\"]", page)
    uniq = {}
    for path, num, yr in links:
        uniq[(int(yr), int(num))] = BASE + path
    return [uniq[k] for k in sorted(uniq, reverse=True)[:n]]


def circular_sections(page_html):
    """Return (circular_no, posted_date, [(name, pdf_url, is_provincial), ...])."""
    title = re.search(r"Circular\s+(\d+)\s+of\s+(\d{4})", page_html)
    circ = title.group(1) if title else ""
    posted = parse_date(re.sub(r"<[^>]+>", " ", (re.search(r"Posting Date:.*?<br", page_html, re.S) or
                                                  re.search(r"Posting Date:.{0,80}", page_html, re.S)).group(0)))
    sections = []
    provincial = False
    for m in re.finditer(r"<h4>(.*?)</h4>|<a href=\"([^\"]+/\d+/[a-z]{1,2}\.pdf)\">(.*?)</a>",
                         page_html, re.S | re.I):
        if m.group(1) is not None:
            provincial = "provincial" in m.group(1).lower()
        else:
            sections.append((html.unescape(re.sub(r"<[^>]+>", "", m.group(3))).strip(),
                             urljoin(BASE, m.group(2)), provincial))
    return circ, posted, sections


def scrape(n=CIRCULARS_TO_CHECK):
    rows = []
    for url in latest_circular_urls(n):
        page = http_get(url)
        circ, posted, sections = circular_sections(page)
        print(f"Circular {circ} ({posted}): {len(sections)} sections", file=sys.stderr)
        for name, pdf_url, provincial in sections:
            try:
                data = http_get(pdf_url, binary=True)
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
                    tf.write(data)
                text = pdf_to_text(tf.name)
                os.unlink(tf.name)
            except Exception as e:
                print(f"  ! {name}: {e}", file=sys.stderr)
                continue
            dept_hint = "" if provincial else clean_dept(name)
            prov_hint = find_province(name) if provincial else ""
            got = parse_pdf_text(text, circ, posted, url, pdf_url, dept_hint, prov_hint)
            print(f"  {name}: {len(got)} posts", file=sys.stderr)
            rows.extend(got)
            time.sleep(1)
    today = datetime.date.today().isoformat()
    return [r for r in rows if not r["closing_date"] or r["closing_date"] >= today]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", help="parse a local circular PDF instead of downloading")
    ap.add_argument("--circular", default="", help="circular number for --pdf")
    ap.add_argument("--posted", default="", help="posting date (YYYY-MM-DD) for --pdf")
    ap.add_argument("--dry-run", action="store_true", help="print rows as JSON, don't write the sheet")
    a = ap.parse_args()

    if a.pdf:
        text = pdf_to_text(a.pdf)
        circ = a.circular or (re.search(r"PUBLICATION NO\s+(\d+)", text) or [None, ""])[1]
        posted = a.posted or parse_date((re.search(r"DATE ISSUED\s+(.+)", text) or [None, ""])[1])
        rows = parse_pdf_text(text, circ, posted, INDEX_URL, INDEX_URL)
    else:
        rows = scrape()

    if a.dry_run:
        json.dump(rows, sys.stdout, ensure_ascii=False, indent=1)
        print(f"\n{len(rows)} posts", file=sys.stderr)
        return
    import sheet_writer
    wrote = sheet_writer.append_jobs(rows)
    print(f"DPSA: parsed {len(rows)} open posts, wrote {wrote} new rows.", file=sys.stderr)


if __name__ == "__main__":
    main()
