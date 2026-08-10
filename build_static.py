import json, os, sys, html, re, datetime

SITE = "https://www.onboardingsa.co.za"
OUT_DIR = "jobs"
LOGO_BASE = "https://raw.githubusercontent.com/onboardingSA-CvkCapital/OnboardingSA/main/"

def esc(s):
    return html.escape((s or "").strip(), quote=True)

def slug_logo(name):
    return re.sub(r'[^A-Za-z0-9]+','-', (name or "").strip().replace("&","and")).strip('-')

def initials(name):
    parts = (name or "?").split()
    return "".join(w[0] for w in parts[:2]).upper() or "?"

def fmt_date(d):
    d=(d or "").strip()
    if not d: return ""
    try:
        t=datetime.date.fromisoformat(d[:10])
        return t.strftime("%-d %b %Y")
    except Exception:
        return d

def days_left(d):
    d=(d or "").strip()
    if not d: return None
    try:
        t=datetime.date.fromisoformat(d[:10])
        return (t - datetime.date.today()).days
    except Exception:
        return None

def to_list(text):
    if not text: return []
    parts = re.split(r'[\n;]|•', text)
    return [p.strip() for p in parts if p.strip()]

def emptype_schema(t):
    t=(t or "").upper()
    if "PERMANENT" in t or "FULL" in t: return "FULL_TIME"
    if "PART" in t: return "PART_TIME"
    if "CONTRACT" in t: return "CONTRACTOR"
    if "TEMP" in t: return "TEMPORARY"
    if "INTERN" in t: return "INTERN"
    return None

HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — {employer} | OnboardingSA</title>
<meta name="description" content="{metadesc}">
<link rel="canonical" href="{canonical}">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 240 240'%3E%3Crect x='20' y='20' width='200' height='200' rx='46' fill='%2312294D'/%3E%3Cpath d='M120 56 L160 112 L133 112 L133 168 L107 168 L107 112 L80 112 Z' fill='%23E8A33D'/%3E%3Crect x='76' y='176' width='88' height='14' rx='7' fill='%23E8A33D'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@500;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<script type="application/ld+json">{schema}</script>
<style>
:root{{--navy:#12294D;--gold:#E8A33D;--gold-600:#C9891F;--bg:#F4F6FA;--card:#FFFFFF;--line:#E4E9F1;--line-2:#EEF2F8;--text:#16213A;--muted:#5B6B85;--tint:#F0F4FB;--radius:14px;}}
*{{box-sizing:border-box}}
html,body{{margin:0;padding:0;overflow-x:hidden}}
body{{font-family:Inter,system-ui,sans-serif;color:var(--text);background:var(--bg);line-height:1.5}}
a{{color:inherit}}
.wrap{{max-width:820px;margin:0 auto;padding:0 20px}}
header.site{{position:sticky;top:0;z-index:40;background:#fff;border-bottom:1px solid var(--line)}}
.site .wrap{{max-width:1160px;display:flex;align-items:center;justify-content:space-between;height:64px}}
.brand svg{{height:34px;width:auto;display:block}}
.nav a{{font-family:Inter;font-weight:500;font-size:15px;color:var(--muted);text-decoration:none}}
.nav a:hover{{color:var(--navy)}}
main{{padding:22px 0 60px}}
.back-link{{display:inline-flex;align-items:center;gap:6px;font-family:Poppins;font-weight:600;font-size:14px;color:var(--navy);text-decoration:none;margin-bottom:16px}}
.back-link:hover{{text-decoration:underline}}
.detail{{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);padding:28px 30px}}
.d-head{{display:flex;gap:14px;align-items:flex-start}}
.avatar{{width:52px;height:52px;border-radius:12px;background:var(--navy);color:#fff;font-family:Poppins;font-weight:700;display:flex;align-items:center;justify-content:center;font-size:18px;flex:none;overflow:hidden}}
.avatar.gold{{background:var(--gold);color:var(--navy)}}
.avatar img{{width:100%;height:100%;object-fit:contain;background:#fff}}
.d-head h1{{font-family:Poppins;font-weight:700;font-size:26px;color:var(--navy);margin:0 0 6px;line-height:1.2}}
.d-emp{{font-size:15px;font-weight:600;color:var(--text)}}
.d-loc{{font-size:14px;color:var(--muted);margin-top:2px}}
.chips{{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0 4px}}
.chip{{font-size:12.5px;color:var(--text);background:var(--tint);border:1px solid var(--line-2);border-radius:6px;padding:5px 10px;white-space:nowrap}}
.close-soon{{color:#B23B3B;font-weight:600}}
.actions{{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0 6px}}
.apply{{display:inline-flex;align-items:center;gap:8px;font-family:Poppins;font-weight:600;font-size:15px;background:var(--gold);color:var(--navy);border-radius:10px;padding:13px 24px;text-decoration:none}}
.apply:hover{{background:var(--gold-600);color:#fff}}
.apply svg{{width:16px;height:16px}}
.handoff{{font-size:12.5px;color:var(--muted);margin:2px 0 20px}}
.section{{border-top:1px solid var(--line);padding-top:18px;margin-top:18px}}
.section h2{{font-family:Poppins;font-weight:600;font-size:15px;color:var(--navy);margin:0 0 8px}}
.section p{{margin:0;font-size:14.5px;color:var(--text);white-space:pre-line}}
.section ul{{margin:0;padding-left:18px}}
.section li{{font-size:14.5px;color:var(--text);margin-bottom:6px}}
.d-foot{{display:flex;justify-content:space-between;gap:12px;font-size:13px;color:var(--muted);margin-top:20px;flex-wrap:wrap}}
@media(max-width:640px){{.detail{{padding:22px 18px}}.d-head h1{{font-size:22px}}.actions .apply{{flex:1 1 100%;justify-content:center}}}}
footer.site{{border-top:1px solid var(--line);background:#fff;padding:24px 0;font-size:13px;color:var(--muted)}}
footer.site .wrap{{max-width:1160px;display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}}
footer.site a{{color:var(--navy);text-decoration:none;font-weight:500}}
</style>
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-5134977183220630" crossorigin="anonymous"></script>
</head>
<body>
<header class="site">
  <div class="wrap">
    <a class="brand" href="../index.html" aria-label="OnboardingSA home">
      <svg viewBox="0 0 640 160" xmlns="http://www.w3.org/2000/svg">
        <svg viewBox="0 0 240 240" x="8" y="20" width="120" height="120">
          <rect x="20" y="20" width="200" height="200" rx="46" fill="#12294D"/>
          <path d="M120 56 L160 112 L133 112 L133 168 L107 168 L107 112 L80 112 Z" fill="#E8A33D"/>
          <rect x="76" y="176" width="88" height="14" rx="7" fill="#E8A33D"/>
        </svg>
        <text x="150" y="101" font-family="Poppins,Arial,sans-serif" font-size="60" font-weight="600" letter-spacing="-0.5"><tspan fill="#12294D">Onboarding</tspan><tspan fill="#E8A33D">SA</tspan></text>
      </svg>
    </a>
    <nav class="nav"><a href="../about.html">About</a></nav>
  </div>
</header>
<main>
  <div class="wrap">
    <a class="back-link" href="../index.html">← All jobs</a>
    <div class="detail">
"""

FOOT = """    </div>
  </div>
</main>
<footer class="site">
  <div class="wrap">
    <span>© {year} OnboardingSA · onboardingsa.co.za</span>
    <span><a href="../about.html">About</a> &nbsp;·&nbsp; <a href="../contact.html">Contact</a> &nbsp;·&nbsp; <a href="../privacy.html">Privacy</a> &nbsp;·&nbsp; <a href="../terms.html">Terms</a></span>
  </div>
</footer>
</body>
</html>
"""

def render(j):
    title=esc(j.get("job_title"))
    employer=esc(j.get("employer"))
    jid=j.get("id","")
    canonical=f"{SITE}/{OUT_DIR}/{jid}.html"
    loc_line=", ".join([x for x in [j.get("location",""),j.get("province","")] if x])
    dl=days_left(j.get("closing_date"))
    soon = dl is not None and dl<=7
    # avatar
    base=slug_logo(j.get("employer"))
    gold=" gold" if j.get("featured","").lower()=="yes" else ""
    ini=esc(initials(j.get("employer")))
    if base:
        logo_img=(f'<img src="{LOGO_BASE}{esc(base)}.png" alt="{employer} logo" loading="lazy" '
                  f'onerror="this.onerror=null;this.replaceWith(document.createTextNode(\'{ini}\'))">')
        avatar=f'<div class="avatar{gold}">{logo_img}</div>'
    else:
        avatar=f'<div class="avatar{gold}">{ini}</div>'
    # meta description
    body_txt=(j.get("about_role","") or j.get("responsibilities","") or j.get("requirements",""))
    metadesc=esc((f"{j.get('job_title','')} at {j.get('employer','')}. " + body_txt)[:155])
    # schema
    schema={
        "@context":"https://schema.org/","@type":"JobPosting",
        "title":j.get("job_title",""),
        "description":(j.get("about_role","")+" "+j.get("responsibilities","")+" "+j.get("requirements","")).strip() or j.get("job_title",""),
        "datePosted":j.get("posted_date","") or None,
        "validThrough":j.get("closing_date","") or None,
        "employmentType":emptype_schema(j.get("employment_type","")),
        "hiringOrganization":{"@type":"Organization","name":j.get("employer","")},
        "jobLocation":{"@type":"Place","address":{"@type":"PostalAddress",
            "addressLocality":j.get("location","") or j.get("province",""),
            "addressRegion":j.get("province",""),"addressCountry":"ZA"}},
        "directApply":False,
    }
    schema={k:v for k,v in schema.items() if v is not None}
    schema_json=json.dumps(schema, ensure_ascii=False)

    head=HEAD.format(title=title, employer=employer, metadesc=metadesc,
                     canonical=canonical, schema=schema_json)

    chips=""
    if j.get("employment_type"): chips+=f'<span class="chip">{esc(j.get("employment_type"))}</span>'
    if j.get("salary"): chips+=f'<span class="chip">{esc(j.get("salary"))}</span>'
    if j.get("category"): chips+=f'<span class="chip">{esc(j.get("category"))}</span>'
    if j.get("closing_date"):
        cd=esc(fmt_date(j.get("closing_date")))
        extra=f" · {dl} days left" if (soon and dl is not None and dl>=0) else ""
        chips+=f'<span class="chip {"close-soon" if soon else ""}">Closes {cd}{extra}</span>'

    apply=""
    apply_url=j.get("official_apply_url","")
    if apply_url:
        apply=(f'<a class="apply" href="{esc(apply_url)}" target="_blank" rel="noopener">'
               f"Apply on {employer}'s official site "
               f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 17L17 7M17 7H8M17 7v9"/></svg></a>')
    handoff=(f'<p class="handoff">You\'ll be taken to {employer}\'s official careers page to apply. '
             f'OnboardingSA never charges you and never collects your application.</p>') if apply_url else ""

    sections=""
    if j.get("about_role"):
        sections+=f'<div class="section"><h2>About the role</h2><p>{esc(j.get("about_role"))}</p></div>'
    resp=to_list(j.get("responsibilities"))
    if resp:
        sections+='<div class="section"><h2>Responsibilities</h2><ul>'+"".join(f"<li>{esc(r)}</li>" for r in resp)+'</ul></div>'
    reqs=to_list(j.get("requirements"))
    if reqs:
        sections+='<div class="section"><h2>Requirements</h2><ul>'+"".join(f"<li>{esc(r)}</li>" for r in reqs)+'</ul></div>'

    foot_meta=""
    if j.get("reference_no"): foot_meta+=f'<span>Ref: {esc(j.get("reference_no"))}</span>'
    else: foot_meta+="<span></span>"
    if j.get("posted_date"): foot_meta+=f'<span>Posted {esc(fmt_date(j.get("posted_date")))}</span>'

    featured_badge=('<div style="font-family:Poppins;font-weight:600;font-size:11px;color:var(--gold-600);margin-bottom:4px">★ FEATURED</div>'
                    if j.get("featured","").lower()=="yes" else "")

    body=f"""      <div class="d-head">
        {avatar}
        <div>
          {featured_badge}
          <h1>{title}</h1>
          <div class="d-emp">{employer}</div>
          <div class="d-loc">{esc(loc_line)}</div>
        </div>
      </div>
      <div class="chips">{chips}</div>
      <div class="actions">{apply}</div>
      {handoff}
      {sections}
      <div class="d-foot">{foot_meta}</div>
"""
    foot=FOOT.format(year=datetime.date.today().year)
    return head+body+foot

def main():
    with open("jobs.json","r",encoding="utf-8") as f:
        jobs=json.load(f)
    os.makedirs(OUT_DIR, exist_ok=True)
    # clear old pages
    for fn in os.listdir(OUT_DIR):
        if fn.endswith(".html"):
            os.remove(os.path.join(OUT_DIR, fn))
    urls=[]
    for j in jobs:
        jid=j.get("id","")
        if not jid: continue
        safe=re.sub(r'[^A-Za-z0-9_\-]', '-', jid)
        path=os.path.join(OUT_DIR, safe+".html")
        with open(path,"w",encoding="utf-8") as f:
            f.write(render(j))
        urls.append(f"{SITE}/{OUT_DIR}/{safe}.html")
    print(f"Wrote {len(urls)} static job pages.", file=sys.stderr)
    # sitemap with main pages + all job pages
    main_pages=["/","/index.html","/about.html","/contact.html","/privacy.html","/terms.html",
               "/guide-index.html","/guide-ats-friendly-cv.html","/guide-z83-form-explained.html",
               "/guide-learnerships.html","/guide-bursaries.html","/guide-job-scams.html",
               "/guide-first-interview.html"]
    sm=['<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for p in main_pages:
        sm.append(f"  <url><loc>{SITE}{p}</loc></url>")
    for u in urls:
        sm.append(f"  <url><loc>{u}</loc></url>")
    sm.append("</urlset>")
    with open("sitemap.xml","w",encoding="utf-8") as f:
        f.write("\n".join(sm))
    print(f"Wrote sitemap.xml with {len(main_pages)+len(urls)} urls.", file=sys.stderr)

if __name__=="__main__":
    main()
