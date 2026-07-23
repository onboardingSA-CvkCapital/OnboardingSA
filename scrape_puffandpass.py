import re, sys, time, html, json
import requests
import sheet_writer

# Your Cloudflare Worker relay URL (set after deploying worker.js).
# Example: https://puff-relay.YOURNAME.workers.dev
RELAY = "https://puffandpass.onboardingsa2.workers.dev"

API = "https://www.puffandpass.co.za/wp-json/wp/v2/posts"
PER_PAGE = 100
MAX_PAGES = 100

COLUMNS = sheet_writer.COLUMNS
HEADERS = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

def fetch(session, url):
    relay_url = RELAY + "/?url=" + requests.utils.quote(url, safe="")
    for attempt in range(3):
        try:
            r = session.get(relay_url, headers=HEADERS, timeout=60)
            if r.status_code == 200 and r.text.strip().startswith("["):
                return r.json()
            if r.status_code == 400:
                return []
        except Exception:
            time.sleep(2)
    return None

MONTHS = {m[:3].lower():i for i,m in enumerate(
    ["January","February","March","April","May","June","July","August",
     "September","October","November","December"],1)}

CAT = {71:"Commerce",63:"Finance",91:"Human Resources",75:"IT",25:"Internship",
       333:"Learnership",234:"Grade 12",1439:"Communications",1172:"Government"}
CAT_NAME = {"internships":"Internship","learnerships":"Learnership","bursaries":"Bursary",
            "grade-12":"Grade 12","in-service-training":"In-Service Training",
            "apprenticeship":"Apprenticeship"}

PROVINCE = {
 "cape town":"Western Cape","bellville":"Western Cape","stellenbosch":"Western Cape","george":"Western Cape",
 "gqeberha":"Eastern Cape","port elizabeth":"Eastern Cape","east london":"Eastern Cape",
 "johannesburg":"Gauteng","pretoria":"Gauteng","sandton":"Gauteng","centurion":"Gauteng","midrand":"Gauteng",
 "roodepoort":"Gauteng","soweto":"Gauteng","randburg":"Gauteng","vereeniging":"Gauteng","mbombela":"Mpumalanga",
 "durban":"KwaZulu-Natal","phoenix":"KwaZulu-Natal","pietermaritzburg":"KwaZulu-Natal",
 "bloemfontein":"Free State","polokwane":"Limpopo","lephalale":"Limpopo","nelspruit":"Mpumalanga",
 "rustenburg":"North West","kimberley":"Northern Cape","gauteng":"Gauteng",
}

def province_of(loc):
    l=(loc or "").lower()
    for k,v in PROVINCE.items():
        if k in l: return v
    if any(w in l for w in ("countrywide","nationwide","national")): return "National"
    return ""

def to_iso(s):
    m=re.search(r'(\d{1,2})\s+([A-Za-z]{3,})\s+(\d{4})', s or "")
    if not m: return ""
    d,mon,y=m.group(1),m.group(2)[:3].lower(),m.group(3)
    return f"{y}-{MONTHS[mon]:02d}-{int(d):02d}" if mon in MONTHS else ""

def strip_tags(h):
    h=re.sub(r'(?is)<h[1-6][^>]*>', '\n', h)
    h=re.sub(r'(?is)</h[1-6]>', '\n', h)
    h=re.sub(r'(?is)<li[^>]*>', '\n• ', h)
    h=re.sub(r'(?is)<br\s*/?>', '\n', h)
    h=re.sub(r'(?is)</p>', '\n', h)
    h=re.sub(r'(?is)<[^>]+>', '', h)
    return html.unescape(h)

def clean(t, limit=8000):
    if not t: return ""
    out="\n".join(x for x in (re.sub(r'[ \t]+',' ',l).strip() for l in t.split('\n')) if x)
    return out[:limit].rstrip()

def parse_content(content_html):
    apply_url=""
    m=re.search(r'(?is)<h3[^>]*>\s*How to Apply\s*</h3>(.*)$', content_html)
    body=content_html
    if m:
        apply_block=m.group(1)
        body=content_html[:m.start()]
        am=re.search(r'href="([^"]+)"', apply_block)
        if am: apply_url=html.unescape(am.group(1))
    return clean(strip_tags(body)), apply_url

def meta_from_text(txt):
    loc=""; closing=""
    lm=re.search(r'Location:\s*([^\n]+)', txt, re.I)
    if lm: loc=lm.group(1).strip()
    cm=re.search(r'Clos\w*\s*Date:\s*([^\n]+)', txt, re.I)
    if cm: closing=cm.group(1).strip()
    return loc, closing

def category_of(post):
    for c in post.get("class_list",[]):
        if c.startswith("category-"):
            key=c.replace("category-","")
            if key in CAT_NAME: return CAT_NAME[key]
    return ""

def scrape():
    total=0
    with requests.Session() as s:
        for pg in range(1, MAX_PAGES+1):
            url = f"{API}?per_page={PER_PAGE}&page={pg}&orderby=date&order=desc"
            posts = fetch(s, url)
            if posts is None:
                print(f"page {pg}: all relays failed - stopping.", file=sys.stderr); break
            if not posts:
                break
            print(f"Page {pg}: {len(posts)} posts", file=sys.stderr)
            rows=[]
            for post in posts:
                title=html.unescape(post.get("title",{}).get("rendered","")).strip()
                if not title: continue
                content_html=post.get("content",{}).get("rendered","")
                desc, apply_url = parse_content(content_html)
                loc, closing = meta_from_text(desc)
                if not closing:
                    ex=html.unescape(strip_tags(post.get("excerpt",{}).get("rendered","")))
                    _, closing = meta_from_text(ex)
                link=post.get("link","")
                row={k:"" for k in COLUMNS}
                row.update({
                    "job_title":title,
                    "employer":title.split(":")[0].strip() if ":" in title else "",
                    "category":category_of(post),
                    "province":province_of(loc), "location":loc,
                    "closing_date":to_iso(closing),
                    "reference_no":"pp_"+str(post.get("id","")),
                    "about_role":desc,
                    "official_apply_url":apply_url or link,
                    "source_url":link, "status":"live",
                })
                rows.append(row)
            if rows:
                wrote=sheet_writer.append_jobs(rows); total+=wrote
                print(f"  wrote {wrote} new (total {total})", file=sys.stderr)
            if len(posts) < PER_PAGE: break
            time.sleep(0.5)
    return total

def main():
    print("Puff & Pass via WordPress API...", file=sys.stderr)
    total=scrape()
    print(f"\nDone: wrote {total} new Puff & Pass jobs.", file=sys.stderr)

if __name__=="__main__":
    main()
