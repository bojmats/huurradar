"""Hulpscript: haalt URL's op (zoals de scraper dat doet) en slaat de HTML op in out/."""
import sys, time, json, pathlib
from curl_cffi import requests as http
H = {"Accept-Language": "nl-NL,nl;q=0.9", "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"}
out = pathlib.Path("out"); out.mkdir(exist_ok=True)
log = []
for i, item in enumerate(u.strip() for u in sys.argv[1].split() if u.strip()):
    url = item
    try:
        if item.startswith("BROWSER:"):  # echte (headless) browser, wacht tot JS klaar is
            from playwright.sync_api import sync_playwright
            url = item[8:]
            with sync_playwright() as pw:
                b = pw.chromium.launch()
                pg = b.new_page(locale="nl-NL", user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
                calls = []
                pg.on("response", lambda resp: calls.append({"url": resp.url, "status": resp.status, "type": resp.request.resource_type,
                       "body": (resp.text()[:200000] if resp.request.resource_type in ("xhr", "fetch") else None)}) if resp.request.resource_type in ("xhr", "fetch") else None)
                resp = pg.goto(url, wait_until="networkidle", timeout=60000)
                pg.wait_for_timeout(6000)
                (out / f"{i:02d}.html").write_text(pg.content())
                (out / f"{i:02d}.calls.json").write_text(json.dumps(calls)[:5000000])
                log.append({"i": i, "url": url, "final": pg.url, "status": resp.status if resp else None, "bytes": len(pg.content()), "xhr": len(calls)})
                b.close()
            continue
        if item.startswith("REQ64:"):  # base64 van {"url","method","body","headers"}
            import base64
            spec = json.loads(base64.b64decode(item[6:]))
            url = spec["url"]
            r = http.request(spec.get("method", "POST"), url, headers={**H, **spec.get("headers", {})},
                             data=spec.get("body"), timeout=30, impersonate="chrome")
        elif item.startswith("POST:"):  # POST:<url>::<json zonder spaties>
            url, body = item[5:].split("::", 1)
            r = http.post(url, headers={**H, "Content-Type": "application/json", "Accept": "application/json"},
                          data=body, timeout=30, impersonate="chrome")
        else:
            r = http.get(url, headers=H, timeout=30, impersonate="chrome", allow_redirects=True)
        (out / f"{i:02d}.html").write_text(r.text)
        log.append({"i": i, "url": url, "final": str(r.url), "status": r.status_code, "bytes": len(r.text)})
    except Exception as e:
        log.append({"i": i, "url": url, "error": str(e)})
    time.sleep(2)
(out / "log.json").write_text(json.dumps(log, indent=1))
print(json.dumps(log, indent=1))
