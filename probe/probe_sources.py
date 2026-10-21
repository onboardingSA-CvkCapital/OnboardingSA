import os, re, json, time
from playwright.sync_api import sync_playwright
OUT = "probe_out"; os.makedirs(OUT, exist_ok=True)
SITES = {
  "dcs_home": "https://www.dcs.gov.za/",
  "dcs_vacancies": "https://www.dcs.gov.za/?page_id=208",
  "kzn_health": "https://www.kznhealth.gov.za/vacancies.htm",
  "ec_health": "https://www.echealth.gov.za/",
  "gp_jobcentre": "https://gpgjobcentre.gauteng.gov.za/Public/Jobs.aspx",
  "capetown": "https://www.capetown.gov.za/Work%20and%20business/Careers-at-the-City",
  "joburg": "https://www.joburg.org.za/work_/Pages/Work%20in%20Joburg/Vacancies.aspx",
  "tshwane": "https://www.tshwane.gov.za/?page_id=1100",
}
KEY = re.compile(r"vacanc|career|job|recruit|nurs|traffic|correction|post", re.I)
log = {}
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1366, "height": 900})
    for name, url in SITES.items():
        t = time.time(); entry = {"url": url}
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=120000)
            try: pg.wait_for_load_state("networkidle", timeout=30000)
            except Exception: pass
            entry["final_url"] = pg.url; entry["title"] = pg.title(); entry["secs"] = round(time.time() - t)
            open(f"{OUT}/{name}.html", "w").write(pg.content())
            pg.screenshot(path=f"{OUT}/{name}.png", full_page=False)
            links = pg.eval_on_selector_all("a", "els=>els.map(e=>[e.innerText.trim().replace(/\\s+/g,' ').slice(0,120), e.href])")
            entry["relevant_links"] = [l for l in links if l[1] and (KEY.search(l[0]) or KEY.search(l[1]))][:80]
            entry["pdf_links"] = [l for l in links if l[1] and l[1].lower().split("?")[0].endswith(".pdf")][:60]
        except Exception as e:
            entry["error"] = str(e)[:200]; entry["secs"] = round(time.time() - t)
        log[name] = entry
    b.close()
json.dump(log, open(f"{OUT}/log.json", "w"), indent=1)
