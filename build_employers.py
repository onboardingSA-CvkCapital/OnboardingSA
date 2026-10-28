"""Build one page per big employer (employers/<slug>.html), an employers index page, the
"Jobs by employer" band on the homepage, and add the pages to sitemap.xml.
Runs after build_static.py (which writes sitemap.xml)."""
import json, os, re, sys, datetime, collections, html as _html
from build_static import HEAD, FOOT, SITE, LOGO_BASE, esc, fmt_date, days_left
from employers_data import GROUPS, group_for

OUT_DIR = "employers"
MIN_JOBS = 5          # fewer live jobs than this: page stays up but is hidden from Google and the homepage
INDEX_FILE = "index.html"

EXTRA_CSS = """
.e-intro p{font-size:15px;margin:0 0 12px;white-space:normal}
.e-stats{font-size:14px;color:var(--muted);margin:10px 0 0}
.e-stats .soon{color:#B23B3B;font-weight:600}
.section ol{margin:0;padding-left:24px}
.section ol li{font-size:14.5px;color:var(--text);margin-bottom:6px;padding-left:4px}
.section ol li::marker{color:var(--muted);font-weight:600}
.detail{background:none;border:0;padding:0}
.e-title{font-family:Poppins;font-weight:700;font-size:28px;color:var(--navy);margin:0;line-height:1.2}
.e-body{margin-top:14px}
ol.e-grid{margin:14px 0 0;padding-left:30px}
ol.e-grid li{border-bottom:1px solid var(--line)}
ol.e-list{margin:4px 0 0;padding-left:30px}
ol.e-list li{margin:0;padding:11px 0 11px 4px;border-bottom:1px solid var(--line-2)}
ol li::marker{color:var(--muted);font-weight:600}
.section ol.e-list{margin:4px 0 0;padding-left:30px}
.section ol.e-list li{margin:0;padding:11px 0 11px 4px;border-bottom:1px solid var(--line-2)}
.section ol.e-list li:last-child{border-bottom:0}
.e-list a{font-weight:600;font-size:15px;color:var(--navy);text-decoration:none}
.e-list a:hover{text-decoration:underline}
.e-list .meta{font-size:13.5px;color:var(--muted);margin-top:2px}
.e-list .soon{color:#B23B3B;font-weight:600}
.e-prov{font-family:Poppins;font-weight:600;font-size:14px;color:var(--navy);margin:22px 0 2px}
.e-empty{font-size:14.5px;color:var(--muted)}
.section ol.e-grid{margin:4px 0 0;padding-left:30px}
.e-grid li{border-bottom:1px solid var(--line)}
.e-grid li:last-child{border-bottom:0}
.e-grid a{display:flex;justify-content:space-between;align-items:baseline;gap:12px;padding:13px 0;text-decoration:none}
.e-grid a:hover b{text-decoration:underline}
.e-grid b{font-family:Poppins;font-weight:600;font-size:15px;color:var(--navy)}
.e-grid span{font-size:13.5px;color:var(--muted);white-space:nowrap}
.nav{display:flex;gap:22px}
"""

PROV_ORDER = ["Eastern Cape", "Free State", "Gauteng", "KwaZulu-Natal", "Limpopo", "Mpumalanga",
              "North West", "Northern Cape", "Western Cape", "National"]


def page_id(jid):
    return re.sub(r"[^A-Za-z0-9_\-]", "-", jid or "")


def loc_line(j):
    l, p = (j.get("location") or "").strip(), (j.get("province") or "").strip()
    if len(l) > 90:
        l = l[:88].rsplit(" ", 1)[0] + "…"
    return l if (p and p.lower() in l.lower()) else ", ".join(x for x in (l, p) if x)


def job_card(j):
    bits = [esc(loc_line(j))] if loc_line(j) else []
    if j.get("salary"):
        bits.append(esc(j["salary"]))
    if j.get("closing_date"):
        dl = days_left(j["closing_date"])
        when = f"Closes {esc(fmt_date(j['closing_date']))}"
        if dl is not None and 0 <= dl <= 7:
            when = f'<span class="soon">{when} ({"today" if dl == 0 else f"{dl} day" + ("s" if dl != 1 else "") + " left"})</span>'
        bits.append(when)
    return (f'<li><a href="../jobs/{page_id(j.get("id"))}.html">{esc(j.get("job_title"))}</a>'
            f'<div class="meta">{" · ".join(bits)}</div></li>')


def month_year():
    return datetime.date.today().strftime("%B %Y")


def head(title, metadesc, canonical, schema, noindex):
    h = HEAD.format(title=esc(title), employer="", metadesc=esc(metadesc), canonical=canonical,
                    schema=json.dumps(schema, ensure_ascii=False),
                    robots='<meta name="robots" content="noindex,follow">\n' if noindex else "")
    h = h.replace(" at  | OnboardingSA</title>", " | OnboardingSA</title>")
    h = h.replace("</style>", EXTRA_CSS + "</style>", 1)
    h = h.replace('<nav class="nav"><a href="../about.html">About</a></nav>',
                  '<nav class="nav"><a href="index.html">Employers</a><a href="../about.html">About</a></nav>')
    return h


def breadcrumb(items):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": u}
                                for i, (n, u) in enumerate(items)]}


def stats_line(jobs):
    provs = {j.get("province") for j in jobs if j.get("province") and j.get("province") != "National"}
    week = sum(1 for j in jobs if (lambda d: d is not None and 0 <= d <= 7)(days_left(j.get("closing_date"))))
    bits = [f'{len(jobs)} open post{"s" if len(jobs) != 1 else ""}']
    if provs:
        bits.append(f'{len(provs)} province{"s" if len(provs) != 1 else ""}')
    if week:
        bits.append(f'<span class="soon">{week} closing this week</span>')
    return '<p class="e-stats">' + " · ".join(bits) + "</p>"


def render_group(g, jobs):
    url = f"{SITE}/{OUT_DIR}/{g['slug']}.html"
    n = len(jobs)
    title = f"{g['short']} Jobs: Current Vacancies {month_year()}"
    metadesc = (f"{n} open {g['name']} vacancies, updated daily, with the official way to apply. "
                + re.sub(r"<[^>]+>", "", g["intro"][0]))[:155]
    logo = (f'<div class="avatar"><img src="{LOGO_BASE}{esc(g["logo"])}.png" alt="{esc(g["name"])} logo" loading="lazy"></div>'
            if g.get("logo") else "")
    parts = [head(title, metadesc, url, breadcrumb([("Home", SITE + "/"), ("Employers", f"{SITE}/{OUT_DIR}/index.html"),
                                                     (f"{g['short']} jobs", url)]), n < MIN_JOBS)]
    parts.append(f'''      <h1 class="e-title">{esc(g["short"])} jobs</h1>
      {stats_line(jobs) if jobs else ""}
      <div class="e-body">''')
    if not jobs:
        parts.append('<p class="e-empty">There are no open posts right now. New posts are added every day, so check back soon.</p>')
    elif g.get("by_province") and len({j.get("province") for j in jobs}) > 1:
        byp = collections.defaultdict(list)
        for j in jobs:
            byp[j.get("province") or "Other"].append(j)
        for p in sorted(byp, key=lambda p: (PROV_ORDER.index(p) if p in PROV_ORDER else 99, p)):
            parts.append(f'<div class="e-prov">{esc(p)} ({len(byp[p])})</div><ol class="e-list">'
                         + "".join(job_card(j) for j in byp[p]) + "</ol>")
    else:
        parts.append('<ol class="e-list">' + "".join(job_card(j) for j in jobs) + "</ol>")
    parts.append("</div>\n")
    parts.append(FOOT.format(year=datetime.date.today().year))
    page = "".join(parts)
    page = page.replace('<a class="back-link" href="../index.html">← All jobs</a>',
                        '<a class="back-link" href="index.html">← All employers</a>')
    return page


def render_index(rows):
    url = f"{SITE}/{OUT_DIR}/index.html"
    title = f"Jobs by Employer: SAPS, Eskom, Health and more ({month_year()})"
    metadesc = "Browse current vacancies by employer: SAPS, Eskom, Sasol, Correctional Services, Health and other government departments. Updated daily."
    cards = "".join(f'<li><a href="{g["slug"]}.html"><b>{esc(g["short"])} jobs</b><span>{n} open post{"s" if n != 1 else ""}</span></a></li>'
                    for g, n in rows)
    body = f'''      <h1 class="e-title">Jobs by employer</h1>
      <ol class="e-grid">{cards}</ol>
'''
    page = head(title, metadesc, url, breadcrumb([("Home", SITE + "/"), ("Employers", url)]), False) + body + \
        FOOT.format(year=datetime.date.today().year)
    return page


def update_homepage(rows, total=None):
    if not os.path.exists(INDEX_FILE):
        return
    h = open(INDEX_FILE, encoding="utf-8").read()
    if "<!--EMPLOYERS_START-->" not in h or "<!--EMPLOYERS_END-->" not in h:
        print("Homepage has no EMPLOYERS markers; skipped.", file=sys.stderr)
        return
    cards = "\n      ".join(f'<li><a href="employers/{g["slug"]}.html"><b>{_html.escape(g["short"])} jobs</b>'
                           f'<span>{n} open post{"s" if n != 1 else ""}</span></a></li>' for g, n in rows)
    block = f"<!--EMPLOYERS_START-->\n      {cards}\n      <!--EMPLOYERS_END-->"
    h = re.sub(r"<!--EMPLOYERS_START-->.*?<!--EMPLOYERS_END-->", lambda _m: block, h, flags=re.S)
    if total is not None:   # live job count in the hero
        h = re.sub(r"<!--LIVECOUNT-->.*?<!--/LIVECOUNT-->", f"<!--LIVECOUNT-->{total:,}<!--/LIVECOUNT-->", h, flags=re.S)
    open(INDEX_FILE, "w", encoding="utf-8").write(h)


def update_sitemap(urls):
    if not os.path.exists("sitemap.xml"):
        return
    sm = open("sitemap.xml", encoding="utf-8").read()
    sm = re.sub(r"\s*<url><loc>[^<]*/employers/[^<]*</loc></url>", "", sm)
    add = "".join(f"\n  <url><loc>{u}</loc></url>" for u in urls)
    sm = sm.replace("\n</urlset>", add + "\n</urlset>") if "\n</urlset>" in sm else sm.replace("</urlset>", add + "\n</urlset>")
    open("sitemap.xml", "w", encoding="utf-8").write(sm)


def main():
    jobs = json.load(open("jobs.json", encoding="utf-8"))
    by = collections.defaultdict(list)
    for j in jobs:
        g = group_for(j.get("employer"))
        if g:
            by[g["slug"]].append(j)
    os.makedirs(OUT_DIR, exist_ok=True)
    for fn in os.listdir(OUT_DIR):
        if fn.endswith(".html"):
            os.remove(os.path.join(OUT_DIR, fn))
    rows, urls = [], [f"{SITE}/{OUT_DIR}/index.html"]
    for g in GROUPS:
        js = sorted(by.get(g["slug"], []), key=lambda j: (j.get("closing_date") or "9999", j.get("job_title", "")))
        open(os.path.join(OUT_DIR, g["slug"] + ".html"), "w", encoding="utf-8").write(render_group(g, js))
        if len(js) >= MIN_JOBS:
            rows.append((g, len(js)))
            urls.append(f"{SITE}/{OUT_DIR}/{g['slug']}.html")
    rows.sort(key=lambda r: -r[1])
    open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8").write(render_index(rows))
    update_homepage(rows, len(jobs))
    update_sitemap(urls)
    print(f"Employer pages: {len(GROUPS)} built, {len(rows)} indexable.", file=sys.stderr)
    for g, n in rows:
        print(f"  {n:4}  {g['short']}", file=sys.stderr)


if __name__ == "__main__":
    main()
