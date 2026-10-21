import json, os, time
from playwright.sync_api import sync_playwright
OUT = "probe_out"; os.makedirs(OUT, exist_ok=True)
log = []
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1366, "height": 900},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36")
    pg = ctx.new_page()
    def on_resp(r):
        u = r.url
        if any(k in u for k in ("_services", "_api", "odata", "entity", "grid", "fetchxml", ".json")):
            try: body = r.text()[:200000]
            except Exception as e: body = f"<err {e}>"
            log.append({"url": u, "status": r.status, "method": r.request.method,
                        "req": (r.request.post_data or "")[:3000], "body": body})
    pg.on("response", on_resp)
    for name, url in [("vacancies", "https://erecruitment.saps.gov.za/SAPS-Vacancies/"),
                      ("trainees", "https://www.saps.gov.za/careers/ptrainees.php")]:
        t = time.time()
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=120000)
            try: pg.wait_for_load_state("networkidle", timeout=90000)
            except Exception: pass
            pg.wait_for_timeout(15000)
        except Exception as e:
            log.append({"page": name, "error": str(e)})
        open(f"{OUT}/{name}.html", "w").write(pg.content())
        pg.screenshot(path=f"{OUT}/{name}.png", full_page=True)
        links = pg.eval_on_selector_all("a", "els=>els.map(e=>[e.innerText.trim().slice(0,120), e.href])")
        json.dump(links, open(f"{OUT}/{name}_links.json", "w"), indent=1)
        log.append({"page": name, "seconds": round(time.time() - t), "final_url": pg.url})
    # open first vacancy detail if any
    try:
        cand = [h for _, h in json.load(open(f"{OUT}/vacancies_links.json")) if h and ("id=" in h.lower() or "vacanc" in h.lower()) and h.rstrip("/") != "https://erecruitment.saps.gov.za/SAPS-Vacancies"]
        if cand:
            pg.goto(cand[0], wait_until="domcontentloaded", timeout=120000)
            try: pg.wait_for_load_state("networkidle", timeout=60000)
            except Exception: pass
            pg.wait_for_timeout(8000)
            open(f"{OUT}/detail.html", "w").write(pg.content())
            pg.screenshot(path=f"{OUT}/detail.png", full_page=True)
            log.append({"detail_url": cand[0]})
    except Exception as e:
        log.append({"detail_error": str(e)})
    b.close()
json.dump(log, open(f"{OUT}/network.json", "w"), indent=1)
