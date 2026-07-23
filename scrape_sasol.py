import re, sys, time
import sheet_writer
from playwright.sync_api import sync_playwright

BASE = "https://jobs.sasol.com"
EMPLOYER = "Sasol"
HEADLESS = True
PER_PAGE = 25
MAX_ROWS = 6000

COLUMNS = sheet_writer.COLUMNS
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

MONTHS = {m[:3].lower():i for i,m in enumerate(
    ["January","February","March","April","May","June","July","August",
     "September","October","November","December"],1)}

PROVINCE = {
 "secunda":"Mpumalanga","sasolburg":"Free State","sandton":"Gauteng","bronkhorstspruit":"Gauteng",
 "johannesburg":"Gauteng","pretoria":"Gauteng","midrand":"Gauteng","centurion":"Gauteng",
 "durban":"KwaZulu-Natal","cape town":"Western Cape","rosebank":"Gauteng","ekandustria":"Gauteng",
}

STOP = ["Equal Opportunity Employer","Sasol (USA) Corporation","Sasol treats work-authorized",
        "For more information about your rights"]

def province_of(loc):
    l=(loc or "").lower()
    for k,v in PROVINCE.items():
        if k in l: return v
    return ""

def to_iso(s):
    m=re.search(r'([A-Za-z]{3,})\s+(\d{1,2}),?\s+(\d{4})', s or "")
    if not m: return ""
    mon,d,y=m.group(1)[:3].lower(),m.group(2),m.group(3)
    return f"{y}-{MONTHS[mon]:02d}-{int(d):02d}" if mon in MONTHS else ""

def iso_from_validthrough(s):
    m=re.search(r'[A-Za-z]{3}\s+([A-Za-z]{3})\s+(\d{1,2})\s+[\d:]+\s+\w+\s+(\d{4})', s or "")
    if m:
        mon,d,y=m.group(1).lower(),m.group(2),m.group(3)
        if mon in MONTHS: return f"{y}-{MONTHS[mon]:02d}-{int(d):02d}"
    return ""

def clean(t, limit=8000):
    if not t: return ""
    out="\n".join(x for x in (re.sub(r'\s+',' ',l).strip() for l in t.split('\n')) if x and len(x)>1)
    return out[:limit].rstrip()

def trim_desc(t):
    if not t: return ""
    low=t.lower(); cut=len(t)
    for s in STOP:
        j=low.find(s.lower())
        if j!=-1: cut=min(cut,j)
    return clean(t[:cut])

def get_detail(detail, url):
    for _ in range(3):
        try:
            detail.goto(url, timeout=45000, wait_until="domcontentloaded")
            detail.wait_for_selector(".jobdescription, #job-title", timeout=15000)
            return detail.evaluate(r"""() => {
                const d=document.querySelector('.jobdescription');
                const segs=[];
                if(d){
                    d.querySelectorAll('h1,h2,h3,h4,p,li').forEach(el=>{
                        let t=(el.innerText||'').trim();
                        if(!t) return;
                        const tag=el.tagName.toLowerCase();
                        const isH = tag.startsWith('h');
                        segs.push({h:isH, li:(tag==='li'), t:t});
                    });
                }
                const vt=document.querySelector('meta[itemprop="validThrough"]');
                const geo=document.querySelector('.jobGeoLocation');
                const sa=document.querySelector('meta[itemprop="streetAddress"]');
                return { segs:segs,
                         validThrough:vt?vt.getAttribute('content'):'',
                         location:(geo?geo.innerText.trim():'') || (sa?sa.getAttribute('content'):'') };
            }""")
        except Exception:
            time.sleep(2)
    return {}


ABOUT_H   = ["purpose of job","introduction","about","overview"]
RESP_H    = ["key accountabilities","accountabilities","responsibilities","key responsibilities","duties","key roles"]
REQ_H     = ["formal education","working experience","work experience","minimum requirements",
             "qualification","education","experience","certification","professional membership"]
SKIP_H    = ["required personal and professional skills","required personal","closing date","job requisition",
             "ome","location"]
SKIP_LINE = ["equal opportunity","affirmative action","our automated process","should you not hear",
             "thank you once","innovating for a better world","preference will be given","reasonable accommodation"]

def split_sasol(segs):
    about=[]; resp=[]; req=[]; bucket="about"
    for s in segs:
        t=(s.get("t") or "").strip()
        if not t: continue
        low=t.lower()
        if s.get("h"):
            hl=low.rstrip(":")
            if any(hl.startswith(k) for k in RESP_H): bucket="resp"; continue
            if any(hl.startswith(k) for k in REQ_H): bucket="req"; continue
            if any(hl.startswith(k) for k in ABOUT_H): bucket="about"; continue
            if any(hl.startswith(k) for k in SKIP_H): bucket="skip"; continue
            bucket="about"; continue
        if bucket=="skip": continue
        if any(k in low for k in SKIP_LINE): continue
        if re.match(r'^(job requisition id|closing date|ome|location)', low): continue
        (about if bucket=="about" else resp if bucket=="resp" else req).append(t)
    j=lambda arr: "; ".join(x.lstrip("• ").strip() for x in arr if len(x)>2)
    return clean("\n".join(about))[:8000], j(resp)[:8000], j(req)[:8000]

def closing_from_segs(segs):
    for i,s in enumerate(segs):
        if (s.get("t") or "").strip().lower().startswith("closing date"):
            for nxt in segs[i:i+2]:
                iso=to_iso(nxt.get("t",""))
                if iso: return iso
    return ""

def scrape():
    total=0; skipped_foreign=0; seen=set()
    with sync_playwright() as p:
        b=p.chromium.launch(headless=HEADLESS)
        ctx=b.new_context(user_agent=UA); page=ctx.new_page(); detail=ctx.new_page()
        start=0
        while start < MAX_ROWS:
            url=f"{BASE}/search/?q=&sortColumn=referencedate&sortDirection=desc&startrow={start}"
            print(f"Loading jobs {start}-{start+PER_PAGE}...", file=sys.stderr)
            ok=False
            for attempt in range(3):
                try:
                    page.goto(url, timeout=60000, wait_until="domcontentloaded")
                    page.wait_for_selector("#job-tile-list, .job-tile, #tile-search-results-label", timeout=20000)
                    ok=True; break
                except Exception:
                    time.sleep(4)
            if not ok:
                print(f"  startrow {start} unreachable - stopping.", file=sys.stderr); break

            tiles=page.evaluate(r"""() => {
                const out=[];
                for (const li of document.querySelectorAll('li.job-tile')){
                    const a=li.querySelector('.jobTitle-link');
                    const url=li.getAttribute('data-url')||'';
                    const id=(li.className.match(/job-id-(\d+)/)||[])[1]||'';
                    const city=(li.querySelector('[id*="-section-city-value"]')||{}).innerText||'';
                    const date=(li.querySelector('[id*="-section-date-value"]')||{}).innerText||'';
                    out.push({id:id, title:a?a.innerText.trim():'', url:url, city:city.trim(), date:date.trim()});
                }
                return out;
            }""")
            if not tiles:
                print("  no more jobs.", file=sys.stderr); break

            rows=[]
            for t in tiles:
                ref="sasol_"+str(t["id"]) if t["id"] else "sasol_"+(t["url"].strip("/").split("/")[-1] if t["url"] else t["title"])
                if not ref or ref in seen: continue
                seen.add(ref)
                full=BASE + t["url"] if t["url"].startswith("/") else t["url"]
                d=get_detail(detail, full)
                locfull=(d.get("location","") or t["city"]).strip()
                if "south africa" not in locfull.lower():
                    skipped_foreign+=1
                    continue
                city=locfull.split(",")[0].strip()
                segs=d.get("segs",[])
                about,resp,req=split_sasol(segs)
                closing=iso_from_validthrough(d.get("validThrough","")) or closing_from_segs(segs)
                row={k:"" for k in COLUMNS}
                row.update({
                    "job_title":t["title"], "employer":EMPLOYER,
                    "province":province_of(city), "location":city,
                    "posted_date":to_iso(t["date"]),
                    "closing_date":closing,
                    "reference_no":ref,
                    "about_role":about, "responsibilities":resp, "requirements":req,
                    "official_apply_url":full, "source_url":full, "status":"live",
                })
                rows.append(row)
                print(f"  NEW (SA): {t['title'][:42]} ({city})", file=sys.stderr)
                time.sleep(0.3)
            if rows:
                sheet_writer.append_jobs(rows); total+=len(rows)
                print(f"  wrote {len(rows)} SA (total {total}, skipped {skipped_foreign} foreign)", file=sys.stderr)
            if len(tiles) < PER_PAGE: break
            start += PER_PAGE
            time.sleep(1)
        b.close()
    return total, skipped_foreign

def main():
    print("Reading sheet...", file=sys.stderr)
    total, foreign = scrape()
    print(f"\nDone: wrote {total} SA Sasol jobs, skipped {foreign} foreign.", file=sys.stderr)

if __name__=="__main__":
    main()
