"""Hulpscript: haalt URL's op (zoals de scraper dat doet) en slaat de HTML op in out/."""
import sys, time, json, pathlib
from curl_cffi import requests as http
H = {"Accept-Language": "nl-NL,nl;q=0.9", "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"}
out = pathlib.Path("out"); out.mkdir(exist_ok=True)
log = []
for i, item in enumerate(u.strip() for u in sys.argv[1].split() if u.strip()):
    url = item
    try:
        if item.startswith("POST:"):  # POST:<url>::<json zonder spaties>
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
