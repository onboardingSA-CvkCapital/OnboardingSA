import os, re, json, time, base64, subprocess
from playwright.sync_api import sync_playwright
OUT = "probe_out3"; os.makedirs(OUT, exist_ok=True)
FETCH = """async u => { const r = await fetch(u); if (!r.ok) throw new Error('HTTP ' + r.status);
  const b = new Uint8Array(await r.arrayBuffer()); let s = '';
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
  return btoa(s); }"""
log = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page()
    pg.goto("https://www.kznhealth.gov.za/vacancies/", wait_until="load", timeout=150000)
    h = pg.content(); open(f"{OUT}/kzn_vacancies.html", "w").write(h)
    pdfs = []
    for u in re.findall(r'href="(https://www\.kznhealth\.gov\.za/wp-content/uploads/[^"]+\.pdf)"', h):
        if u not in pdfs: pdfs.append(u)
    for u in pdfs[:120]:
        t = time.time()
        try:
            data = base64.b64decode(pg.evaluate(FETCH, u))
            fn = f"{OUT}/" + re.sub(r"[^A-Za-z0-9.]+", "_", u.split("/uploads/")[1])
            open(fn, "wb").write(data)
            subprocess.run(["pdftotext", "-layout", fn, fn + ".txt"])
            log.append({"pdf": u, "bytes": len(data), "secs": round(time.time() - t)})
        except Exception as e:
            log.append({"pdf": u, "error": str(e)[:150]})
    b.close()
json.dump(log, open(f"{OUT}/log.json", "w"), indent=1)
