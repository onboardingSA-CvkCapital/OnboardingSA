"""build_guides.py  -  OnboardingSA

Builds the career guides from guides/src/<slug>.html (a META json block + the article body)
into <slug>.html pages, the guide-index.html page, and adds them to sitemap.xml.
The guides are OnboardingSA's own writing, written once by hand. Their design is deliberately
different from job pages: a reading layout (serif text, contents list, key points), no job-style cards.
Usage:  python build_guides.py
"""
import re, json, glob, html, datetime, os

SITE = "https://www.onboardingsa.co.za"
ADS = '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-5134977183220630" crossorigin="anonymous"></script>'

CATEGORY_ORDER = ["Government jobs", "Company and graduate jobs", "CVs and applications", "Interviews",
                  "Learnerships and training", "Studying and bursaries", "Money and rights", "Staying safe", "Career advice"]

LOGO = """<svg viewBox="0 0 640 160" xmlns="http://www.w3.org/2000/svg">
        <svg viewBox="0 0 240 240" x="8" y="20" width="120" height="120">
          <rect x="20" y="20" width="200" height="200" rx="46" fill="#12294D"/>
          <path d="M120 56 L160 112 L133 112 L133 168 L107 168 L107 112 L80 112 Z" fill="#E8A33D"/>
          <rect x="76" y="176" width="88" height="14" rx="7" fill="#E8A33D"/>
        </svg>
        <text x="150" y="101" font-family="Poppins,Arial,sans-serif" font-size="60" font-weight="600" letter-spacing="-0.5"><tspan fill="#12294D">Onboarding</tspan><tspan fill="#E8A33D">SA</tspan></text>
      </svg>"""

CSS = """
:root{--navy:#12294D;--gold:#E8A33D;--gold-600:#B9781A;--paper:#FFFFFF;--sand:#FBF6EC;--sand-2:#F3EADA;--ink:#1D2433;
--muted:#5E6675;--line:#E8E2D6;--tint:#F7F3EA}
*{box-sizing:border-box}
html,body{margin:0;padding:0;overflow-x:hidden}
body{font-family:'Source Serif 4',Georgia,serif;color:var(--ink);background:var(--paper);line-height:1.75}
a{color:var(--navy)}
.wrap{max-width:1120px;margin:0 auto;padding:0 20px}
header.site{position:sticky;top:0;z-index:40;background:#fff;border-bottom:1px solid var(--line)}
.site .wrap{display:flex;align-items:center;justify-content:space-between;height:64px}
.brand>svg{height:34px;width:auto;display:block}
.nav{display:flex;gap:22px}
.nav a{font-family:Inter,system-ui,sans-serif;font-weight:500;font-size:15px;color:var(--muted);text-decoration:none}
.nav a:hover,.nav a.on{color:var(--navy)}
.hero{background:var(--sand);border-bottom:1px solid var(--line)}
.hero .wrap{padding-top:40px;padding-bottom:36px;max-width:860px}
.crumbs{font-family:Inter,system-ui,sans-serif;font-size:13px;color:var(--muted);margin-bottom:18px}
.crumbs a{color:var(--muted);text-decoration:none}.crumbs a:hover{text-decoration:underline}
.kicker{font-family:Inter,system-ui,sans-serif;font-size:12.5px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--gold-600);margin:0 0 10px}
.hero h1{font-family:Lora,Georgia,serif;font-weight:700;font-size:42px;line-height:1.15;color:var(--navy);margin:0 0 14px;letter-spacing:-.01em}
.hero .lede{font-size:20px;line-height:1.6;color:#3A4252;margin:0 0 18px;max-width:720px}
.byline{font-family:Inter,system-ui,sans-serif;font-size:13.5px;color:var(--muted)}
.layout{display:grid;grid-template-columns:240px minmax(0,700px);gap:56px;justify-content:center;padding-top:40px;padding-bottom:70px}
.toc{position:sticky;top:88px;align-self:start;font-family:Inter,system-ui,sans-serif}
.toc p{font-size:12px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 10px}
.toc ol{list-style:none;margin:0;padding:0;counter-reset:t;border-left:2px solid var(--line)}
.toc li{counter-increment:t;margin:0}
.toc a{display:block;padding:6px 0 6px 14px;font-size:14px;line-height:1.4;color:var(--muted);text-decoration:none}
.toc a::before{content:counter(t) ". ";color:var(--gold-600);font-weight:600}
.toc a:hover{color:var(--navy)}
.article{font-size:18.5px}
.article p{margin:0 0 20px}
.article h2{font-family:Lora,Georgia,serif;font-weight:700;font-size:28px;line-height:1.25;color:var(--navy);margin:46px 0 14px;scroll-margin-top:84px}
.article h3{font-family:Lora,Georgia,serif;font-weight:600;font-size:21px;line-height:1.3;color:var(--navy);margin:30px 0 8px}
.article ul,.article ol{margin:0 0 22px;padding-left:24px}
.article li{margin-bottom:9px}
.article strong,.article b{color:var(--navy)}
.inshort{background:var(--sand);border-radius:14px;padding:22px 26px;margin:0 0 34px}
.inshort p.t{font-family:Inter,system-ui,sans-serif;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--gold-600);margin:0 0 8px}
.inshort ul{margin:0;padding-left:20px}.inshort li{font-size:17px;margin-bottom:6px}
.callout{background:var(--tint);border:1px solid var(--line);border-radius:14px;padding:18px 22px;margin:26px 0;font-size:17px}
.callout b{display:block;font-family:Inter,system-ui,sans-serif;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--gold-600);margin-bottom:4px}
.steps{list-style:none;padding:0;counter-reset:s;margin:0 0 24px}
.steps li{counter-increment:s;position:relative;padding:0 0 0 52px;margin:0 0 18px}
.steps li::before{content:counter(s);position:absolute;left:0;top:2px;width:34px;height:34px;border-radius:50%;background:var(--navy);color:#fff;
font-family:Inter,system-ui,sans-serif;font-weight:700;font-size:15px;display:flex;align-items:center;justify-content:center}
.tick li,.cross li{list-style:none;position:relative}
.tick li::before{content:"\\2713";position:absolute;left:-22px;color:#2E7D4F;font-weight:700}
.cross li::before{content:"\\2715";position:absolute;left:-22px;color:#B23B3B;font-weight:700}
.cmp-wrap{overflow-x:auto;margin:0 0 24px}
.cmp{width:100%;border-collapse:collapse;font-family:Inter,system-ui,sans-serif;font-size:15px;line-height:1.5}
.cmp th,.cmp td{text-align:left;padding:11px 12px;border-bottom:1px solid var(--line);vertical-align:top}
.cmp th{font-weight:600;color:var(--navy);border-bottom:2px solid var(--navy)}
blockquote{margin:28px 0;padding:0 0 0 22px;border-left:3px solid var(--navy);font-family:Lora,Georgia,serif;font-style:italic;font-size:21px;color:var(--navy)}
.faq{margin:10px 0 30px}
.faq details{border-bottom:1px solid var(--line);padding:14px 0}
.faq summary{cursor:pointer;font-family:Lora,Georgia,serif;font-weight:600;font-size:19px;color:var(--navy);list-style:none}
.faq summary::-webkit-details-marker{display:none}
.faq summary::after{content:"+";float:right;font-family:Inter,system-ui,sans-serif;color:var(--gold-600)}
.faq details[open] summary::after{content:"\\2212"}
.faq details p{margin:10px 0 0}
.endnote{border-top:1px solid var(--line);margin-top:40px;padding-top:22px;font-family:Inter,system-ui,sans-serif;font-size:14px;color:var(--muted)}
.endnote a{font-weight:600}
.more{background:var(--sand);border-top:1px solid var(--line)}
.more .wrap{max-width:860px;padding-top:36px;padding-bottom:44px}
.more h2{font-family:Lora,Georgia,serif;font-size:26px;color:var(--navy);margin:0 0 14px}
.more ol{list-style:none;margin:0;padding:0}
.more li{border-bottom:1px solid var(--sand-2)}
.more a{display:block;padding:14px 0;text-decoration:none}
.more a span{display:block;font-family:Inter,system-ui,sans-serif;font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--gold-600)}
.more a b{font-family:Lora,Georgia,serif;font-size:20px;color:var(--navy);font-weight:600}
.more a:hover b{text-decoration:underline}
footer.site{border-top:1px solid var(--line);background:#fff;padding:24px 0;font-family:Inter,system-ui,sans-serif;font-size:13px;color:var(--muted)}
footer.site .wrap{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
footer.site a{color:var(--navy);text-decoration:none;font-weight:500}
.gi-cat{margin:0 0 40px}
.gi-cat h2{font-family:Inter,system-ui,sans-serif;font-size:12.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--gold-600);margin:0 0 6px;border-bottom:2px solid var(--navy);padding-bottom:8px}
.gi-cat ol{list-style:none;margin:0;padding:0}
.gi-cat li{border-bottom:1px solid var(--line)}
.gi-cat a{display:block;padding:16px 0;text-decoration:none}
.gi-cat a b{display:block;font-family:Lora,Georgia,serif;font-size:22px;line-height:1.3;color:var(--navy)}
.gi-cat a span{display:block;font-size:16.5px;color:var(--muted);margin-top:4px}
.gi-cat a em{font-style:normal;font-family:Inter,system-ui,sans-serif;font-size:12.5px;color:var(--muted)}
.gi-cat a:hover b{text-decoration:underline}
.gi{max-width:860px;padding-top:40px;padding-bottom:60px}
@media(max-width:900px){.layout{grid-template-columns:minmax(0,1fr);gap:0}.toc{position:static;margin-bottom:30px;background:var(--tint);border-radius:14px;padding:18px 20px}
.toc ol{border-left:0}.toc a{padding-left:0}}
@media(max-width:640px){.hero h1{font-size:31px}.hero .lede{font-size:18px}.article{font-size:17.5px}.article h2{font-size:24px}.hero .wrap{padding-top:28px}}
"""

HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} | OnboardingSA</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{canonical}">
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" type="image/png" sizes="96x96" href="/favicon-96x96.png">
<link rel="icon" type="image/png" sizes="192x192" href="/favicon-192x192.png">
<link rel="icon" type="image/svg+xml" href="/onboardingsa-icon.svg">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Lora:wght@600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=Inter:wght@400;500;600;700&family=Poppins:wght@600&display=swap" rel="stylesheet">
{schema}
<style>{css}</style>
{ads}
</head>
<body>
<header class="site">
  <div class="wrap">
    <a class="brand" href="index.html" aria-label="OnboardingSA home">
      {logo}
    </a>
    <nav class="nav"><a href="employers/index.html">Employers</a><a class="on" href="guide-index.html">Guides</a><a href="about.html">About</a></nav>
  </div>
</header>
"""

FOOT = """<footer class="site">
  <div class="wrap">
    <span>&copy; {year} OnboardingSA &middot; onboardingsa.co.za</span>
    <span><a href="about.html">About</a> &nbsp;&middot;&nbsp; <a href="contact.html">Contact</a> &nbsp;&middot;&nbsp; <a href="privacy.html">Privacy</a> &nbsp;&middot;&nbsp; <a href="terms.html">Terms</a></span>
  </div>
</footer>
</body>
</html>
"""


def esc(s):
    return html.escape(s or "", quote=True)


def slugify(t):
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"<[^>]+>", "", t).lower()).strip("-")[:60]


def load():
    guides = []
    for f in sorted(glob.glob("guides/src/*.html")):
        raw = open(f, encoding="utf-8").read()
        m = re.match(r"<!--META\s*(\{.*?\})\s*META-->\s*(.*)$", raw, re.S)
        meta = json.loads(m.group(1))
        meta["body"] = m.group(2).strip()
        text = re.sub(r"<[^>]+>", " ", meta["body"]) + " " + " ".join(q["q"] + " " + re.sub(r"<[^>]+>", " ", q["a"]) for q in meta.get("faq", []))
        meta["words"] = len(text.split())
        meta["minutes"] = max(3, round(meta["words"] / 220))
        guides.append(meta)
    return guides


def add_ids(body):
    toc = []
    def rep(m):
        inner = m.group(2)
        i = slugify(inner)
        toc.append((i, re.sub(r"<[^>]+>", "", inner)))
        return f'<h2 id="{i}"{m.group(1)}>{inner}</h2>'
    body = re.sub(r"<h2([^>]*)>(.*?)</h2>", rep, body, flags=re.S)
    return body, toc


def nice_date(iso):
    d = datetime.date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%B %Y')}"


def render(g, all_guides):
    body, toc = add_ids(g["body"])
    canonical = f"{SITE}/{g['slug']}.html"
    faq = g.get("faq") or []
    schema = [{"@context": "https://schema.org", "@type": "Article", "headline": g["title"], "description": g["description"],
               "dateModified": g["updated"], "datePublished": g.get("published", g["updated"]),
               "author": {"@type": "Organization", "name": "OnboardingSA", "url": SITE + "/"},
               "publisher": {"@type": "Organization", "name": "OnboardingSA", "logo": {"@type": "ImageObject", "url": SITE + "/favicon-512x512.png"}},
               "mainEntityOfPage": canonical}]
    if faq:
        schema.append({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q["q"], "acceptedAnswer": {"@type": "Answer", "text": re.sub(r"<[^>]+>", "", q["a"])}} for q in faq]})
    schema_html = "\n".join(f'<script type="application/ld+json">{json.dumps(s, ensure_ascii=False)}</script>' for s in schema)
    out = [HEAD.format(title=esc(g.get("seo_title") or g["title"]), desc=esc(g["description"]), canonical=canonical,
                       schema=schema_html, css=CSS, ads=ADS, logo=LOGO)]
    out.append(f"""<section class="hero">
  <div class="wrap">
    <div class="crumbs"><a href="index.html">Home</a> &rsaquo; <a href="guide-index.html">Career guides</a> &rsaquo; {esc(g['category'])}</div>
    <p class="kicker">{esc(g['category'])}</p>
    <h1>{esc(g['title'])}</h1>
    <p class="lede">{esc(g['lede'])}</p>
    <div class="byline">By the OnboardingSA team &middot; Updated {nice_date(g['updated'])} &middot; {g['minutes']} min read</div>
  </div>
</section>
<div class="wrap layout">
  <nav class="toc" aria-label="In this guide"><p>In this guide</p><ol>
    {''.join(f'<li><a href="#{i}">{esc(t)}</a></li>' for i, t in toc)}{'<li><a href="#faq">Questions people ask</a></li>' if faq else ''}
  </ol></nav>
  <article class="article">
""")
    if g.get("keypoints"):
        out.append('    <div class="inshort"><p class="t">In short</p><ul>' + "".join(f"<li>{k}</li>" for k in g["keypoints"]) + "</ul></div>\n")
    out.append(body + "\n")
    if faq:
        out.append('<h2 id="faq">Questions people ask</h2>\n<div class="faq">' +
                   "".join(f"<details><summary>{esc(q['q'])}</summary><p>{q['a']}</p></details>" for q in faq) + "</div>\n")
    out.append("""    <p class="endnote">This guide is written by OnboardingSA to help South African job seekers. Rules and forms change, so always follow
      the official advert and the employer's own instructions. <a href="index.html">Browse current jobs &rarr;</a></p>
  </article>
</div>
""")
    rel = [x for x in (g.get("related") or []) if x != g["slug"]]
    pool = [x for x in all_guides if x["slug"] != g["slug"]]
    picks = [x for s in rel for x in pool if x["slug"] == s]
    picks += [x for x in pool if x["category"] == g["category"] and x not in picks]
    picks += [x for x in pool if x not in picks]
    out.append('<section class="more"><div class="wrap"><h2>Keep reading</h2><ol>' +
               "".join(f'<li><a href="{x["slug"]}.html"><span>{esc(x["category"])}</span><b>{esc(x["title"])}</b></a></li>' for x in picks[:4]) +
               "</ol></div></section>\n")
    out.append(FOOT.format(year=datetime.date.today().year))
    return "".join(out)


def render_index(guides):
    canonical = f"{SITE}/guide-index.html"
    schema = {"@context": "https://schema.org", "@type": "CollectionPage", "name": "Career guides for South African job seekers",
              "url": canonical, "hasPart": [{"@type": "Article", "headline": g["title"], "url": f"{SITE}/{g['slug']}.html"} for g in guides]}
    out = [HEAD.format(title="Career Guides for South African Job Seekers",
                       desc="Free, practical guides for South African job seekers: government applications and the Z83, SAPS, Eskom and "
                            "Transnet hiring, CVs, interviews, learnerships, bursaries, UIF and avoiding job scams.",
                       canonical=canonical, schema=f'<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>',
                       css=CSS, ads=ADS, logo=LOGO)]
    out.append("""<section class="hero"><div class="wrap">
    <div class="crumbs"><a href="index.html">Home</a> &rsaquo; Career guides</div>
    <p class="kicker">Career guides</p>
    <h1>Practical help for South African job seekers</h1>
    <p class="lede">How government and company hiring really works, how to fill in the forms, what to expect at interviews,
      and how to stay safe from scams. Written in plain language, free to read.</p>
  </div></section>
<div class="wrap gi">
""")
    cats = sorted({g["category"] for g in guides}, key=lambda c: (CATEGORY_ORDER.index(c) if c in CATEGORY_ORDER else 99, c))
    for c in cats:
        items = [g for g in guides if g["category"] == c]
        out.append(f'<section class="gi-cat"><h2>{esc(c)}</h2><ol>' + "".join(
            f'<li><a href="{g["slug"]}.html"><b>{esc(g["title"])}</b><span>{esc(g["lede"])}</span><em>{g["minutes"]} min read</em></a></li>'
            for g in items) + "</ol></section>\n")
    out.append("</div>\n")
    out.append(FOOT.format(year=datetime.date.today().year))
    return "".join(out)


def update_sitemap(slugs):
    if not os.path.exists("sitemap.xml"):
        return
    sm = open("sitemap.xml", encoding="utf-8").read()
    sm = re.sub(r"\s*<url><loc>[^<]*/guide-[^<]*</loc></url>", "", sm)
    add = "".join(f"\n  <url><loc>{SITE}/{s}.html</loc></url>" for s in ["guide-index"] + slugs)
    sm = sm.replace("\n</urlset>", add + "\n</urlset>")
    open("sitemap.xml", "w", encoding="utf-8").write(sm)


def update_homepage(guides):
    """Homepage 'Career guides' band: newest six guides."""
    if not os.path.exists("index.html"):
        return
    h = open("index.html", encoding="utf-8").read()
    if "<!--GUIDES_START-->" not in h:
        return
    pick = sorted(guides, key=lambda g: g.get("published", g["updated"]), reverse=True)[:6]
    cards = "\n      ".join(f'<a class="gcard" href="{g["slug"]}.html"><h3>{esc(g["title"])}</h3><p>{esc(g["lede"][:120])}</p></a>' for g in pick)
    h = re.sub(r"<!--GUIDES_START-->.*?<!--GUIDES_END-->", lambda _m: f"<!--GUIDES_START-->\n      {cards}\n      <!--GUIDES_END-->", h, flags=re.S)
    open("index.html", "w", encoding="utf-8").write(h)


def main():
    guides = load()
    for g in guides:
        open(g["slug"] + ".html", "w", encoding="utf-8").write(render(g, guides))
    open("guide-index.html", "w", encoding="utf-8").write(render_index(guides))
    update_sitemap([g["slug"] for g in guides])
    update_homepage(guides)
    total = sum(g["words"] for g in guides)
    print(f"Built {len(guides)} guides ({total:,} words) + guide index.")
    for g in guides:
        print(f"  {g['words']:5}  {g['slug']}")


if __name__ == "__main__":
    main()
