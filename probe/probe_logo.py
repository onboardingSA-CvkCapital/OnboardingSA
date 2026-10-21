import os, re, base64, json
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright
OUT = "probe_out3"; os.makedirs(OUT, exist_ok=True)
FETCH = """async u => { const r = await fetch(u); if (!r.ok) throw new Error('HTTP ' + r.status);
  const b = new Uint8Array(await r.arrayBuffer()); let s = '';
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
  return [btoa(s), r.headers.get('content-type')]; }"""
log = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1400, "height": 900})
    for site in ["https://www.saps.gov.za/careers/careers.php", "https://erecruitment.saps.gov.za/"]:
        try:
            pg.goto(site, wait_until="load", timeout=240000); pg.wait_for_timeout(4000)
        except Exception as e:
            log.append({"site": site, "error": str(e)[:150]}); continue
        tag = "saps" if "www.saps" in site else "erec"
        pg.screenshot(path=f"{OUT}/{tag}_top.png", clip={"x": 0, "y": 0, "width": 1400, "height": 260})
        urls = pg.evaluate("""() => { const out = new Set();
          document.querySelectorAll('img').forEach(i => out.add(i.currentSrc || i.src));
          document.querySelectorAll('link[rel*=icon]').forEach(l => out.add(l.href));
          document.querySelectorAll('*').forEach(e => { const bg = getComputedStyle(e).backgroundImage;
            (bg.match(/url\\(["']?([^"')]+)/g) || []).forEach(m => out.add(m.replace(/url\\(["']?/, ''))); });
          return [...out]; }""")
        urls = [u for u in urls if u and not u.startswith("data:")][:25]
        log.append({"site": site, "images": urls})
        for i, u in enumerate(urls):
            try:
                b64, ct = pg.evaluate(FETCH, u)
                ext = (re.search(r"\.(png|jpe?g|svg|gif|ico|webp)(?:\?|$)", u, re.I) or [None, "bin"])[1]
                fn = f"{OUT}/{tag}_{i:02d}.{ext}"
                open(fn, "wb").write(base64.b64decode(b64)); log.append({"saved": fn, "url": u, "type": ct})
            except Exception as e:
                log.append({"url": u, "error": str(e)[:120]})
    b.close()
json.dump(log, open(f"{OUT}/log.json", "w"), indent=1)
