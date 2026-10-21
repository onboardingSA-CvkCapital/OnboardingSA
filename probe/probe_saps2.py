import os, re, subprocess, time, json, requests
OUT = "probe_out2"; os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141.0 Safari/537.36"}
B = "https://www.saps.gov.za/careers/"
log = []
def get(url, binary=False):
    for i in range(4):
        t = time.time()
        try:
            r = requests.get(url, headers=UA, timeout=(30, 240))
            log.append({"url": url, "status": r.status_code, "bytes": len(r.content), "secs": round(time.time()-t)})
            if r.ok: return r.content if binary else r.text
        except Exception as e:
            log.append({"url": url, "error": str(e)[:200], "secs": round(time.time()-t)})
        time.sleep(10)
    return None
pages = {}
html = get(B + "careers.php")
if html:
    open(f"{OUT}/careers.html", "w").write(html)
    for h in sorted(set(re.findall(r'href="([^"#]+\.php)"', html))):
        if "/" not in h.strip("./") or h.startswith("../careers/") or h.startswith("/careers/"):
            pages[h] = None
for name in ["ptrainees.php", "publicact.php", "ls.php"] + list(pages):
    u = requests.compat.urljoin(B, name)
    h = get(u)
    if h:
        fn = re.sub(r"[^A-Za-z0-9.]+", "_", name)
        open(f"{OUT}/page_{fn}.html", "w").write(h)
        log.append({"page": u, "pdfs": re.findall(r'href="([^"]+\.pdf)"', re.sub(r"<!--.*?-->", "", h, flags=re.S))[:40]})
for p in ["downloads/2026/trainee/Police-Trainee-Advert-2026-2027.pdf",
          "downloads/2026/polact/214 2026.pdf",
          "downloads/2026/SMS/SMS1.pdf"]:
    data = get(B + p.replace(" ", "%20"), binary=True)
    if data:
        fn = f"{OUT}/" + re.sub(r"[^A-Za-z0-9.]+", "_", p)
        open(fn, "wb").write(data)
        subprocess.run(["pdftotext", "-layout", fn, fn + ".txt"])
json.dump(log, open(f"{OUT}/log.json", "w"), indent=1)
