import os, re, json, time
from playwright.sync_api import sync_playwright
OUT = "probe_out2"; os.makedirs(OUT, exist_ok=True)
START = {
  "dcs": "http://careers.dcs.gov.za/",
  "kzn_health": "https://www.kznhealth.gov.za/vacancies/",
  "kzn_health_careers": "https://www.kznhealth.gov.za/career-opportunities/",
  "tshwane": "https://www.tshwane.gov.za/?page_id=59256",
  "gauteng": "https://gpgjobcentre.gauteng.gov.za/Public/Jobs.aspx",
  "joburg": "https://joburg.org.za/work_/Pages/default.aspx",
  "capetown": "https://www.capetown.gov.za/",
  "ethekwini": "https://www.durban.gov.za/",
  "ec_health": "https://www.echealth.gov.za/",
}
KEY = re.compile(r"vacanc|career|recruit|jobs?\b|employment opportunit", re.I)
log = {}
def visit(pg, name, url, depth):
    t = time.time(); e = {"url": url}
    feeds = []
    pg.on("response", lambda r: feeds.append(r.url) if any(k in r.url.lower() for k in ("json", "ajax", "webmethod", ".asmx", "api/")) else None)
    try:
        pg.goto(url, wait_until="domcontentloaded", timeout=150000)
        try: pg.wait_for_load_state("networkidle", timeout=45000)
        except Exception: pass
        pg.wait_for_timeout(8000)
        e.update(final_url=pg.url, title=pg.title(), secs=round(time.time() - t), feeds=feeds[:20])
        open(f"{OUT}/{name}.html", "w").write(pg.content())
        pg.screenshot(path=f"{OUT}/{name}.png", full_page=False)
        links = pg.eval_on_selector_all("a", "els=>els.map(e=>[e.innerText.trim().replace(/\\s+/g,' ').slice(0,140), e.href])")
        e["relevant_links"] = [l for l in links if l[1] and (KEY.search(l[0]) or KEY.search(l[1]))][:60]
        e["pdf_links"] = [l for l in links if l[1] and re.search(r"\\.pdf($|\\?)", l[1], re.I)][:80]
        e["tables"] = pg.eval_on_selector_all("table", "ts=>ts.map(t=>t.rows.length)")
    except Exception as ex:
        e.update(error=str(ex)[:200], secs=round(time.time() - t))
    log[name] = e
    if depth and "relevant_links" in e:
        seen = set()
        for txt, href in e["relevant_links"]:
            if href in seen or href.rstrip("/#") == url.rstrip("/#") or href.lower().endswith(".pdf") or "login" in href.lower():
                continue
            seen.add(href)
            if len(seen) > 3: break
            visit(pg, f"{name}__{len(seen)}", href, depth - 1)
with sync_playwright() as p:
    b = p.chromium.launch()
    for name, url in START.items():
        pg = b.new_page(viewport={"width": 1366, "height": 900})
        visit(pg, name, url, 1)
        pg.close()
    b.close()
json.dump(log, open(f"{OUT}/log.json", "w"), indent=1)
