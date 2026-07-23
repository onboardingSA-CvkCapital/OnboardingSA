import re, sys, time
import sheet_writer
from playwright.sync_api import sync_playwright

START_URL = "https://eskomcareers.ci.hr/applicant/index.php?controller=Page&name=jobsearch"
EMPLOYER  = "Eskom"
HEADLESS  = True

COLUMNS = sheet_writer.COLUMNS

MONTHS = {m.lower():i for i,m in enumerate(
    ["January","February","March","April","May","June","July","August",
     "September","October","November","December"], 1)}

STOP_PHRASES = [
    "If you have not been contacted","Eskom is committed to equality",
    "Eskom is committed to providing a smoke-free","Kindly note if you require",
    "Kindly apply for the position","FOR ASSISTANCE WITH THIS ADVERT","PLEASE EMAIL",
    "recruitment","@eskom.co.za","Candidate support","Candidate.support","Top Employer",
    "Do you require help","Go to Help","Help & FAQ","Privacy Statement","Terms & Conditions",
    "Our website uses cookies","Number of Positions","Ref:",
]

def to_iso(s):
    if not s: return ""
    m=re.search(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', s)
    if not m: return s.strip()
    d,mon,y=m.group(1),m.group(2).lower(),m.group(3)
    return f"{y}-{MONTHS[mon]:02d}-{int(d):02d}" if mon in MONTHS else s.strip()

def map_type(t):
    t=(t or "").lower()
    if "permanent" in t: return "Full-time"
    if "fixed" in t or "contract" in t or "temporary" in t: return "Contract"
    if "intern" in t: return "Internship"
    if "learner" in t: return "Learnership"
    return t.title() if t else ""

def clean_block(t):
    if not t: return ""
    low=t.lower(); cut=len(t)
    for e in STOP_PHRASES:
        j=low.find(e.lower())
        if j!=-1: cut=min(cut,j)
    t=t[:cut]
    parts=[re.sub(r'\s+',' ',p).strip(" :\u00b7-\t") for p in re.split(r'\u00b7|\n', t)]
    return "; ".join(p for p in parts if p and len(p)>2)

def build_row(data, title, url, ref):
    meta=data.get("meta",{}); cards=data.get("cards",{})
    about=cards.get("introduction") or cards.get("position summary") or ""
    resp =cards.get("job description") or cards.get("responsibilities") or ""
    reqs =cards.get("minimum requirements") or cards.get("requirements") or ""
    row={k:"" for k in COLUMNS}
    row.update({
        "job_title":meta.get("title") or title, "employer":EMPLOYER,
        "category":meta.get("category",""), "location":meta.get("location",""),
        "employment_type":map_type(meta.get("employmenttype","")),
        "salary":(data.get("remun") or "").strip(),
        "closing_date":to_iso(data.get("applyby","")), "reference_no":ref,
        "about_role":clean_block(about), "responsibilities":clean_block(resp),
        "requirements":clean_block(reqs),
        "official_apply_url":url, "source_url":url, "status":"live",
    })
    return row

def scrape():
    rows=[]
    with sync_playwright() as p:
        b=p.chromium.launch(headless=HEADLESS)
        page=b.new_page()
        print("Opening Eskom search page...", file=sys.stderr)
        page.goto(START_URL, timeout=60000)
        try: page.wait_for_selector("text=Listing reference", timeout=30000)
        except Exception: print("No listings appeared.", file=sys.stderr)

        listings=[]
        while True:
            found=page.evaluate(r"""() => {
                const out=[]; const seen=new Set();
                for (const a of document.querySelectorAll('a')) {
                    const href=a.getAttribute('href')||'';
                    if(!/method=view/i.test(href)) continue;
                    const txt=a.textContent.trim();
                    if(!txt || txt.toLowerCase()==='view & apply') continue;
                    if(seen.has(a.href)) continue; seen.add(a.href);
                    out.push({title:txt, url:a.href});
                }
                return out;
            }""")
            listings.extend(found)
            nxt=page.query_selector("a[rel='next'], a:has-text('Next'), li.next a")
            if nxt and nxt.is_enabled():
                try: nxt.click(); page.wait_for_timeout(2500)
                except Exception: break
            else: break

        uniq=[]; seen=set()
        for l in listings:
            if l["url"] in seen: continue
            seen.add(l["url"]); uniq.append(l)
        print(f"Found {len(uniq)} jobs. Reading details...", file=sys.stderr)

        for n,l in enumerate(uniq,1):
            try:
                page.goto(l["url"], timeout=45000)
                page.wait_for_selector("#listing-name", timeout=15000)
                data=page.evaluate(r"""() => {
                    const dn=id=>(document.getElementById(id)?.dataset?.name||'').trim();
                    const body=document.body.innerText||'';
                    const grab=re=>{const m=body.match(re);return m?m[1].trim():'';};
                    const cards={};
                    document.querySelectorAll('.dynamic-card').forEach(c=>{
                        const h=c.querySelector('h5'); if(!h) return;
                        const heading=h.innerText.trim().toLowerCase();
                        let t=c.innerText; if(t.startsWith(h.innerText)) t=t.slice(h.innerText.length);
                        cards[heading]=t.trim();
                    });
                    return {meta:{title:dn('listing-name'),category:dn('listing-category'),
                            location:dn('listing-location'),employmenttype:dn('listing-employmenttype')},
                            applyby:grab(/Apply by:\s*([^\n]+)/), remun:grab(/Remuneration:\s*([^\n]+)/), cards};
                }""")
                ref_m=re.search(r'(eskom_\d+)', l["url"], re.I)
                if ref_m:
                    ref=ref_m.group(1).lower()
                else:
                    idm=re.search(r'[?&]id=(\d+)', l["url"], re.I)
                    if idm:
                        ref="eskom_"+idm.group(1)
                    else:
                        ref="eskom_"+re.sub(r'[^a-z0-9]+','-', l["title"].lower()).strip('-')[:60]
                rows.append(build_row(data, l["title"], l["url"], ref))
                print(f"  [{n}/{len(uniq)}] {l['title'][:45]}", file=sys.stderr)
                time.sleep(0.4)
            except Exception as e:
                print(f"  [{n}/{len(uniq)}] skipped ({e})", file=sys.stderr)
        b.close()
    return rows

def main():
    print("Scraping Eskom...", file=sys.stderr)
    rows=scrape()
    n=sheet_writer.append_jobs(rows)
    print(f"\nDone: found {len(rows)} jobs, wrote {n} new to the sheet.", file=sys.stderr)

if __name__=="__main__":
    main()
