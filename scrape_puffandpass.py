import re, sys, time
import sheet_writer
from playwright.sync_api import sync_playwright

BASE = "https://www.puffandpass.co.za"
SEARCH = BASE + "/?s="
MAX_PAGES = 500
BATCH_PAGES = 8
BATCH_REST = 40
HEADLESS = True

COLUMNS = sheet_writer.COLUMNS

MONTHS = {m[:3].lower():i for i,m in enumerate(
    ["January","February","March","April","May","June","July","August",
     "September","October","November","December"],1)}

PROVINCE = {
 "cape town":"Western Cape","bellville":"Western Cape","stellenbosch":"Western Cape","george":"Western Cape",
 "gqeberha":"Eastern Cape","port elizabeth":"Eastern Cape","east london":"Eastern Cape",
 "johannesburg":"Gauteng","pretoria":"Gauteng","sandton":"Gauteng","centurion":"Gauteng","midrand":"Gauteng",
 "roodepoort":"Gauteng","soweto":"Gauteng","randburg":"Gauteng","vereeniging":"Gauteng","alrode":"Gauteng","isando":"Gauteng",
 "durban":"KwaZulu-Natal","phoenix":"KwaZulu-Natal","pietermaritzburg":"KwaZulu-Natal","newlands":"KwaZulu-Natal",
 "bloemfontein":"Free State","polokwane":"Limpopo","lephalale":"Limpopo","ellisras":"Limpopo",
 "mbombela":"Mpumalanga","nelspruit":"Mpumalanga","rustenburg":"North West","kimberley":"Northern Cape",
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

def clean(t, limit=8000):
    if not t: return ""
    out="\n".join(x for x in (re.sub(r'\s+',' ',l).strip() for l in t.split('\n')) if x and len(x)>1)
    return out[:limit].rstrip()

def get_detail(detail, url):
    for _ in range(3):
        try:
            detail.goto(url, timeout=45000, wait_until="domcontentloaded")
            detail.wait_for_selector(".single-post-title, .entry-content", timeout=15000)
            return detail.evaluate(r"""() => {
                const g=s=>{const e=document.querySelector(s);return e?e.innerText.trim():'';};
                const cell=(label)=>{
                    for (const c of document.querySelectorAll('.single-meta-cell')){
                        const l=c.querySelector('.single-meta-label');
                        if(l && l.innerText.trim().toLowerCase()===label){ const v=c.querySelector('.single-meta-value'); return v?v.innerText.trim():''; }
                    }
                    return '';
                };
                let desc='';
                const ec=document.querySelector('.entry-content');
                if(ec){
                    const clone=ec.cloneNode(true);
                    const apply=clone.querySelector('.how-to-apply-section');
                    if(apply) apply.remove();
                    const parts=[];
                    clone.querySelectorAll('h1,h2,h3,h4,h5,p,li').forEach(el=>{
                        let t=(el.innerText||'').trim();
                        if(!t) return;
                        const tag=el.tagName.toLowerCase();
                        const strong=el.querySelector('strong,b');
                        const isHeading = tag.startsWith('h') ||
                            (tag==='p' && strong && strong.innerText.trim()===t && t.length<45);
                        if(isHeading){ parts.push('\n'+t.replace(/:$/,'').toUpperCase()); }
                        else if(tag==='li'){ parts.push('• '+t); }
                        else { parts.push(t); }
                    });
                    desc=parts.join('\n').trim();
                    if(!desc) desc=clone.innerText.trim();
                }
                let applyUrl='';
                const a=document.querySelector('.how-to-apply-section a[href]');
                if(a) applyUrl=a.href;
                return {
                    title:g('.single-post-title'),
                    employer:g('.single-post-company'),
                    category:g('.cat-pill'),
                    location:cell('location'),
                    closing:cell('closing date'),
                    desc:desc, applyUrl:applyUrl,
                };
            }""")
        except Exception:
            time.sleep(2)
    return {}

def scrape():
    existing=sheet_writer.existing_refs()
    print(f"Sheet has {len(existing)} jobs - skipping those.", file=sys.stderr)
    total=0; seen=set()
    with sync_playwright() as p:
        b=p.chromium.launch(headless=HEADLESS, args=["--disable-http2"])
        UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ctx=b.new_context(user_agent=UA); page=ctx.new_page(); detail=ctx.new_page()
        in_batch=0

        for pg in range(1, MAX_PAGES+1):
            if in_batch>=BATCH_PAGES:
                print(f"--- batch done. Resting {BATCH_REST}s, fresh session... ---", file=sys.stderr)
                try: ctx.close()
                except Exception: pass
                time.sleep(BATCH_REST)
                ctx=b.new_context(user_agent=UA); page=ctx.new_page(); detail=ctx.new_page(); in_batch=0
            in_batch+=1
            url = SEARCH if pg==1 else f"{BASE}/page/{pg}?s"
            print(f"Loading page {pg}...", file=sys.stderr)
            ok=False
            for attempt in range(3):
                try:
                    page.goto(url, timeout=60000, wait_until="domcontentloaded")
                    page.wait_for_selector("article.opportunity-card", timeout=20000); ok=True; break
                except Exception:
                    time.sleep(5)
            if not ok:
                print(f"  page {pg} unreachable - stopping.", file=sys.stderr); break

            links=page.evaluate(r"""() => {
                const out=[];
                for (const a of document.querySelectorAll('article.opportunity-card')){
                    const t=a.querySelector('.card-title a');
                    const meta=Array.from(a.querySelectorAll('.card-meta-item')).map(x=>x.innerText.trim());
                    let cat='';
                    const ic=a.querySelector('.card-icon');
                    if(ic){ const m=(ic.className||'').match(/cat-([a-z0-9-]+)/); if(m) cat=m[1]; }
                    out.push({id:(a.id||'').replace('post-',''), url:t?t.href:'',
                              title:t?t.innerText.trim():'', meta:meta, cat:cat,
                              excerpt:(a.querySelector('.card-excerpt')||{}).innerText||''});
                }
                return out;
            }""")
            if not links:
                print(f"  page {pg} empty - stopping.", file=sys.stderr); break

            rows=[]
            for c in links:
                ref=c["id"] or c["url"]
                if not ref or ref.lower() in existing or ref in seen: continue
                seen.add(ref)
                d=get_detail(detail, c["url"]) or {}
                title=(d.get("title") or "").strip() or c["title"]
                if not title: continue
                # fall back to card data when the detail page didn't load
                loc=d.get("location","")
                closing=d.get("closing","")
                if not loc or not closing:
                    for m in c["meta"]:
                        ml=m.lower()
                        if "clos" in ml and not closing: closing=m
                        elif "ago" not in ml and not loc: loc=m
                CATMAP={"internship":"Internship","learnership":"Learnership","bursary":"Bursary",
                        "grade-12":"Grade 12","inservice":"In-Service Training","apprenticeship":"Apprenticeship"}
                row={k:"" for k in COLUMNS}
                row.update({
                    "job_title":title,
                    "employer":d.get("employer","") or (title.split(":")[0].strip() if ":" in title else ""),
                    "category":d.get("category","") or CATMAP.get(c["cat"],""),
                    "province":province_of(loc), "location":loc,
                    "closing_date":to_iso(closing),
                    "reference_no":ref,
                    "about_role":clean(d.get("desc","") or c["excerpt"]),
                    "official_apply_url":d.get("applyUrl") or c["url"],
                    "source_url":c["url"], "status":"live",
                })
                rows.append(row)
                print(f"  NEW: {row['job_title'][:48]}", file=sys.stderr)
                time.sleep(0.3)
            if rows:
                sheet_writer.append_jobs(rows); total+=len(rows)
                print(f"  page {pg}: wrote {len(rows)} (total {total})", file=sys.stderr)
            time.sleep(1)
        b.close()
    return total

def main():
    print("Reading sheet...", file=sys.stderr)
    total=scrape()
    print(f"\nDone: wrote {total} new Puff & Pass jobs to the sheet.", file=sys.stderr)

if __name__=="__main__":
    main()
