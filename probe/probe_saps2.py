import os, re, subprocess, time, json, base64
from playwright.sync_api import sync_playwright
OUT = "probe_out2"; os.makedirs(OUT, exist_ok=True)
B = "https://www.saps.gov.za/careers/"
log = []
def load(pg, url):
    for i in range(3):
        t = time.time()
        try:
            pg.goto(url, wait_until="load", timeout=240000)
            log.append({"url": url, "ok": True, "secs": round(time.time()-t), "bytes": len(pg.content())})
            return pg.content()
        except Exception as e:
            log.append({"url": url, "error": str(e)[:200], "secs": round(time.time()-t)})
            time.sleep(10)
    return None
def fetch_pdf(pg, url):
    for i in range(3):
        t = time.time()
        try:
            b64 = pg.evaluate("""async u => { const r = await fetch(u); if(!r.ok) throw new Error('HTTP '+r.status);
                const b = new Uint8Array(await r.arrayBuffer()); let s=''; for (let i=0;i<b.length;i+=0x8000) s+=String.fromCharCode.apply(null,b.subarray(i,i+0x8000)); return btoa(s); }""", url)
            data = base64.b64decode(b64)
            log.append({"pdf": url, "bytes": len(data), "secs": round(time.time()-t)})
            return data
        except Exception as e:
            log.append({"pdf": url, "error": str(e)[:200], "secs": round(time.time()-t)})
            time.sleep(10)
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.set_default_timeout(240000)
    names = ["careers.php", "ptrainees.php", "publicact.php", "ls.php"]
    seen = set()
    while names:
        n = names.pop(0)
        if n in seen: continue
        seen.add(n)
        h = load(pg, B + n)
        if not h: continue
        open(f"{OUT}/page_{n}.html", "w").write(h)
        clean = re.sub(r"<!--.*?-->", "", h, flags=re.S)
        log.append({"page": n, "pdfs": re.findall(r'href="([^"]+\.pdf)"', clean)[:40],
                    "php_links": sorted(set(re.findall(r'href="([^"#?]+\.php)"', clean)))})
        if n == "careers.php":
            for l in re.findall(r'href="([^"#?]+\.php)"', clean):
                l = l.replace("../careers/", "").replace("/careers/", "")
                if "/" not in l and l not in seen: names.append(l)
    load(pg, B + "ptrainees.php")
    for path in ["downloads/2026/trainee/Police-Trainee-Advert-2026-2027.pdf",
                 "downloads/2026/polact/214 2026.pdf", "downloads/2026/SMS/SMS1.pdf"]:
        data = fetch_pdf(pg, B + path.replace(" ", "%20"))
        if data:
            fn = f"{OUT}/" + re.sub(r"[^A-Za-z0-9.]+", "_", path)
            open(fn, "wb").write(data)
            subprocess.run(["pdftotext", "-layout", fn, fn + ".txt"])
    b.close()
json.dump(log, open(f"{OUT}/log.json", "w"), indent=1)
