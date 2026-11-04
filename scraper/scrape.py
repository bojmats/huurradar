"""HuurRadar scraper.

Haalt huurwoningen op van Pararius, Huurwoningen.nl en Funda, filtert ze op
de instellingen in config.yaml en schrijft het resultaat naar docs/listings.json,
dat de overzichtspagina (docs/index.html) inleest.

Draaien:  python scraper/scrape.py
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin

import yaml
from bs4 import BeautifulSoup

try:  # curl_cffi doet zich voor als een echte Chrome-browser -> minder vaak geblokkeerd
    from curl_cffi import requests as http

    IMPERSONATE = {"impersonate": "chrome"}
except ImportError:  # pragma: no cover
    import requests as http

    IMPERSONATE = {}

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
OUTPUT_PATH = ROOT / "docs" / "listings.json"
NIEUWBOUW_PATH = ROOT / "docs" / "nieuwbouw.json"
NIEUWBOUW_HANDMATIG = ROOT / "nieuwbouw.yaml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

POSTCODE_RE = re.compile(r"\b([1-9]\d{3})\s?([A-Z]{2})\b")
NUMBER_RE = re.compile(r"\d[\d.]*")


# ----------------------------------------------------------------- helpers

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def log(msg: str) -> None:
    print(msg, flush=True)


LAST_STATUS = {"code": None}


def fetch(url: str) -> str | None:
    LAST_STATUS["code"] = None
    try:
        r = http.get(url, headers=HEADERS, timeout=30, **IMPERSONATE)
    except Exception as e:  # netwerkfout
        log(f"   ! fout bij ophalen {url}: {e}")
        return None
    LAST_STATUS["code"] = r.status_code
    if r.status_code != 200:
        log(f"   ! {url} gaf status {r.status_code}")
        return None
    time.sleep(random.uniform(1.5, 3.5))  # beleefd blijven
    return r.text


def parse_int(text: str | None) -> int | None:
    if not text:
        return None
    m = NUMBER_RE.search(text.replace("\xa0", " "))
    if not m:
        return None
    digits = m.group(0).replace(".", "")
    return int(digits) if digits.isdigit() else None


def find_postcode(text: str) -> str | None:
    m = POSTCODE_RE.search(text or "")
    return f"{m.group(1)} {m.group(2)}" if m else None


def make_id(source: str, url: str) -> str:
    return source + "-" + hashlib.sha1(url.encode()).hexdigest()[:12]


def text_of(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


# ----------------------------------------------------------------- foto's

IMG_URL_RE = re.compile(r"https?://[^\s\"'<>,]+?(?:\.(?:jpe?g|png|webp)|casco-media[^\s\"'<>,]+)[^\s\"'<>,]*", re.I)
BAD_IMG = ("placeholder", "logo", "icon", "sprite", "avatar", ".svg")


def pick_image(el) -> str | None:
    """Zoekt de eerste echte foto: src, data-src, srcset, <source>, <noscript>..."""
    if el is None:
        return None
    cands = []
    for tag in el.find_all(["img", "source"]):
        for attr in ("src", "data-src", "data-lazy-src", "srcset", "data-srcset"):
            v = tag.get(attr)
            if not v or v.startswith("data:"):
                continue
            # srcset: "url 1x, url 2x" -> pak de laatste (grootste)
            parts = [p.strip().split(" ")[0] for p in v.split(",") if p.strip()]
            cands += reversed(parts) if "srcset" in attr else parts
    cands += IMG_URL_RE.findall(str(el))  # ook in <noscript>/<template>/data-attributen
    for c in cands:
        c = c.replace("&amp;", "&")
        if c.startswith("//"):
            c = "https:" + c
        if c.startswith("http") and not any(b in c.lower() for b in BAD_IMG):
            return c
    return None


def og_image(soup) -> str | None:
    for sel in ("meta[property='og:image']", "meta[name='twitter:image']"):
        m = soup.select_one(sel)
        if m and m.get("content", "").startswith("http"):
            return m["content"]
    return pick_image(soup.select_one("main") or soup)


# ----------------------------------------------------------------- parsers

def parse_pararius_like(html: str, base_url: str, source: str) -> list[dict]:
    """Pararius en Huurwoningen.nl gebruiken (vrijwel) dezelfde opmaak."""
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select("section.listing-search-item") or soup.select("[class*='listing-search-item--']")
    out = []
    for it in items:
        link = it.select_one("a[class*='listing-search-item__link--title']") or it.select_one(
            "h2 a[href], [class*='listing-search-item__title'] a[href]"
        )
        if not link or not link.get("href"):
            continue
        url = urljoin(base_url, link["href"])
        subtitle = text_of(it.select_one("[class*='listing-search-item__sub-title']"))
        price_txt = text_of(it.select_one("[class*='listing-search-item__price']"))
        area_txt = text_of(it.select_one("[class*='surface-area']"))
        rooms_txt = text_of(it.select_one("[class*='number-of-rooms']"))
        image = pick_image(it)
        wijk = None
        m = re.search(r"\(([^)]+)\)", subtitle)
        if m:
            wijk = m.group(1)
        out.append(
            {
                "id": make_id(source, url),
                "source": source,
                "title": text_of(link),
                "url": url,
                "price": parse_int(price_txt),
                "price_text": price_txt,
                "address": subtitle,
                "postcode": find_postcode(subtitle),
                "wijk": wijk,
                "rooms": parse_int(rooms_txt),
                "surface": parse_int(area_txt),
                "image": image,
                "extra": text_of(it)[:500],
            }
        )
    return out


def parse_funda(html: str, base_url: str) -> list[dict]:
    """Funda: best effort. Zoekt kaartjes met een link naar /detail/huur/."""
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    for a in soup.select("a[href*='/detail/huur/']"):
        url = urljoin(base_url, a["href"].split("?")[0])
        if url in seen:
            continue
        # zoek het omringende kaartje
        card = a
        for _ in range(8):
            if card.parent is None:
                break
            card = card.parent
            if card.find(string=re.compile(r"€")) and len(text_of(card)) > 40:
                break
        txt = text_of(card)
        if "€" not in txt:
            continue
        seen.add(url)
        price_m = re.search(r"€\s?([\d.]+)", txt)
        surf_m = re.search(r"(\d+)\s?m²", txt)
        rooms_m = re.search(r"(\d+)\s?(?:kamers?|slaapkamers?)", txt)
        title_el = card.find(["h2", "h3"]) or a
        img = card.find("img")
        out.append(
            {
                "id": make_id("funda", url),
                "source": "funda",
                "title": text_of(title_el)[:120],
                "url": url,
                "price": parse_int(price_m.group(1)) if price_m else None,
                "price_text": price_m.group(0) if price_m else "",
                "address": txt[:160],
                "postcode": find_postcode(txt),
                "wijk": None,
                "rooms": int(rooms_m.group(1)) if rooms_m else None,
                "surface": int(surf_m.group(1)) if surf_m else None,
                "image": pick_image(card),
                "extra": txt[:500],
            }
        )
    return out


# ----------------------------------------------------------------- bronnen

def scrape_pararius(gebied: dict, cfg: dict) -> list[dict]:
    lo, hi = cfg.get("min_prijs", 0), cfg["max_prijs"]
    res = []
    for page in range(1, cfg.get("max_paginas", 3) + 1):
        url = f"https://www.pararius.nl/huurwoningen/{gebied['slug']}/{lo}-{hi}"
        if page > 1:
            url += f"/page-{page}"
        html = fetch(url)
        if not html:
            break
        found = parse_pararius_like(html, "https://www.pararius.nl", "pararius")
        res += found
        if len(found) < 10:
            break
    return res


def scrape_huurwoningen(gebied: dict, cfg: dict) -> list[dict]:
    lo, hi = cfg.get("min_prijs", 0), cfg["max_prijs"]
    res = []
    for page in range(1, cfg.get("max_paginas", 3) + 1):
        url = f"https://www.huurwoningen.nl/in/{gebied['slug']}/?price={lo}-{hi}"
        if page > 1:
            url += f"&page={page}"
        html = fetch(url)
        if not html:
            break
        found = parse_pararius_like(html, "https://www.huurwoningen.nl", "huurwoningen")
        res += found
        if len(found) < 10:
            break
    return res


def scrape_funda(gebied: dict, cfg: dict) -> list[dict]:
    lo, hi = cfg.get("min_prijs", 0), cfg["max_prijs"]
    res = []
    for page in range(1, cfg.get("max_paginas", 3) + 1):
        url = (
            "https://www.funda.nl/zoeken/huur?"
            f'selected_area=["{gebied["slug"]}"]&price="{lo}-{hi}"&sort="date_down"'
        )
        if page > 1:
            url += f"&search_result={page}"
        html = fetch(url)
        if not html:
            break
        found = parse_funda(html, "https://www.funda.nl")
        res += found
        if len(found) < 5:
            break
    return res


SCRAPERS = {"pararius": scrape_pararius, "huurwoningen": scrape_huurwoningen, "funda": scrape_funda}


# ----------------------------------------------------------------- filter

def postcode_in_ranges(pc: str, ranges: list[str]) -> bool:
    num = int(pc[:4])
    for r in ranges:
        r = str(r).strip()
        if "-" in r:
            a, b = r.split("-", 1)
            if int(a) <= num <= int(b):
                return True
        elif num == int(r):
            return True
    return False


def is_excluded(listing: dict, cfg: dict) -> bool:
    words = [w.lower() for w in cfg.get("uitsluiten_woorden", [])]
    if not words:
        return False
    hay = " ".join(str(listing.get(k) or "") for k in ("title", "address", "extra", "url", "image", "detail_text")).lower()
    return any(w in hay for w in words)


def matches(listing: dict, gebied: dict, cfg: dict) -> bool:
    if is_excluded(listing, cfg):
        return False
    p = listing.get("price")
    if p is not None and not (cfg.get("min_prijs", 0) <= p <= cfg["max_prijs"]):
        return False
    if cfg.get("min_kamers") and listing.get("rooms") is not None and listing["rooms"] < cfg["min_kamers"]:
        return False
    if cfg.get("min_oppervlakte") and listing.get("surface") is not None and listing["surface"] < cfg["min_oppervlakte"]:
        return False
    ranges = gebied.get("postcodes")
    if not ranges:
        return True  # hele plaats
    if listing.get("postcode"):
        return postcode_in_ranges(listing["postcode"], ranges)
    # geen postcode bekend: probeer wijknaam
    hay = f"{listing.get('wijk') or ''} {listing.get('address') or ''} {listing.get('title') or ''}".lower()
    return any(w.lower() in hay for w in gebied.get("wijken", []))


# ----------------------------------------------------------------- detailpagina

def enrich(l: dict) -> bool:
    html = fetch(l["url"])
    if not html:
        return False  # volgende scan opnieuw proberen
    l["detail_checked"] = True
    soup = BeautifulSoup(html, "html.parser")
    if not l.get("image"):
        l["image"] = og_image(soup)
    desc = soup.select_one("meta[name='description'], meta[property='og:description']")
    body = text_of(soup.select_one("[class*='listing-detail-description'], [class*='description'], main"))
    l["detail_text"] = ((desc.get("content", "") if desc else "") + " " + body)[:1500]
    return True


# ----------------------------------------------------------------- main

def write_nieuwbouw(cfg: dict, sources, stamp: str) -> None:
    if cfg.get("bronnen", {}).get("woonstad"):
        sources.woonstad_nieuwbouw(cfg)
    projects = dict(sources.NIEUWBOUW)
    if NIEUWBOUW_HANDMATIG.exists():
        for p in yaml.safe_load(NIEUWBOUW_HANDMATIG.read_text()).get("projecten", []) or []:
            pid = make_id("handmatig", p.get("link") or p["naam"])
            projects[pid] = {"id": pid, "source": "handmatig", "name": p["naam"], "city": p.get("plaats"),
                             "wijk": p.get("wijk"), "area": p.get("plaats"), "url": p.get("link"), "status": p.get("status"),
                             "segment": p.get("type"), "price": p.get("prijs", ""), "text": p.get("notitie", ""),
                             "image": p.get("foto")}
    old = {}
    if NIEUWBOUW_PATH.exists():
        try:
            old = {p["id"]: p for p in json.loads(NIEUWBOUW_PATH.read_text()).get("projecten", [])}
        except json.JSONDecodeError:
            pass
    fetched = 0
    for pid, p in projects.items():
        o = old.get(pid, {})
        p["first_seen"] = o.get("first_seen", stamp)
        p["last_seen"] = stamp
        if not p.get("image"):
            p["image"] = o.get("image")
        if not p.get("image") and p.get("url") and p["source"] != "handmatig" and fetched < 10:
            fetched += 1
            html = fetch(p["url"])
            if html:
                p["image"] = og_image(BeautifulSoup(html, "html.parser"))
    # projecten die even niet terugkwamen (bron tijdelijk onbereikbaar) 30 dagen bewaren
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    for pid, o in old.items():
        if pid not in projects and o.get("source") != "handmatig" and datetime.fromisoformat(o["last_seen"]) >= cutoff:
            projects[pid] = o
    out = sorted(projects.values(), key=lambda p: (p.get("area") or "", p.get("name") or ""))
    NIEUWBOUW_PATH.write_text(json.dumps({"updated": stamp, "projecten": out}, ensure_ascii=False, indent=1))
    log(f"Nieuwbouw: {len(out)} projecten in je gebieden")


def load_existing() -> dict:
    if OUTPUT_PATH.exists():
        try:
            return json.loads(OUTPUT_PATH.read_text())
        except json.JSONDecodeError:
            pass
    return {"listings": []}


def main() -> int:
    sys.modules.setdefault("scrape", sys.modules[__name__])  # sources.py gebruikt dezelfde module
    sys.path.insert(0, str(Path(__file__).parent))
    import sources
    SCRAPERS.update(sources.EXTRA_SCRAPERS)

    cfg = yaml.safe_load(CONFIG_PATH.read_text())
    existing = {l["id"]: l for l in load_existing().get("listings", [])}
    sources.EXISTING.update(existing)
    stamp = now_iso()
    found: dict[str, dict] = {}
    status = {}
    scanned: set[tuple[str, str]] = set()  # (bron, gebied) die deze run echt resultaten gaven

    for source, enabled in cfg.get("bronnen", {}).items():
        if not enabled or source not in SCRAPERS:
            continue
        count, ok = 0, False
        for gebied in cfg["gebieden"]:
            log(f"> {source}: {gebied['naam']}")
            try:
                results = SCRAPERS[source](gebied, cfg)
            except Exception as e:
                log(f"   ! {source}/{gebied['naam']} mislukt: {e}")
                continue
            if results or source in sources.SOURCE_OK:
                ok = True
            if results:
                scanned.add((source, gebied["naam"]))
            for l in results:
                if matches(l, gebied, cfg):
                    l["area"] = gebied["naam"]
                    found[l["id"]] = l
                    count += 1
            log(f"   {len(results)} gevonden, {sum(1 for l in results if l['id'] in found)} binnen criteria")
        status[source] = {"ok": ok, "count": count}

    # samenvoegen met eerdere runs
    merged = {}
    for lid, l in found.items():
        old = existing.get(lid)
        l["first_seen"] = old["first_seen"] if old else stamp
        l["last_seen"] = stamp
        l["active"] = True
        l["missed"] = 0
        merged[lid] = l

    cutoff = datetime.now(timezone.utc) - timedelta(days=cfg.get("bewaar_dagen_offline", 14))
    failed_sources = {s for s, st in status.items() if not st["ok"]}
    gebied_by_name = {g["naam"]: g for g in cfg["gebieden"]}
    for lid, old in existing.items():
        if lid in merged:
            continue
        # past niet meer bij de (aangepaste) instellingen -> weg
        g = gebied_by_name.get(old.get("area"))
        if g is None or not matches(old, g, cfg):
            continue
        # bron/gebied niet (volledig) gescand, bijv. geblokkeerd: niets veranderen
        if old["source"] in failed_sources or (old["source"], old.get("area")) not in scanned:
            merged[lid] = old
            continue
        # pas offline na 2 geslaagde scans waarin hij ontbrak (blokkades op losse pagina's)
        old["missed"] = old.get("missed", 0) + 1
        if old["missed"] >= 2:
            old["active"] = False
        if datetime.fromisoformat(old["last_seen"]) >= cutoff:
            merged[lid] = old

    # detailpagina's: foto ophalen en controleren op woningruil (max N per scan)
    todo = [l for l in merged.values() if l.get("active") and not l.get("detail_checked")]
    todo.sort(key=lambda l: (l["first_seen"] != stamp, l["first_seen"]))  # nieuwste eerst
    limit = cfg.get("max_detailpaginas", 15)
    blocked: dict[str, int] = {}
    done = 0
    for l in todo:
        if done >= limit:
            break
        if blocked.get(l["source"], 0) >= 2:  # site blokkeert: deze scan niet verder proberen
            continue
        if not enrich(l) and LAST_STATUS["code"] in (403, 429):
            blocked[l["source"]] = blocked.get(l["source"], 0) + 1
        done += 1
    for lid in [lid for lid, l in merged.items() if is_excluded(l, cfg)]:
        log(f"   - uitgesloten: {merged[lid]['title']}")
        del merged[lid]

    listings = sorted(merged.values(), key=lambda l: l["first_seen"], reverse=True)
    new_count = sum(1 for l in listings if l["first_seen"] == stamp)
    scans = load_existing().get("scans")
    if scans is None:  # oudere data: eerdere scans afleiden
        scans = [{"time": t, "new": sum(1 for l in listings if l["first_seen"] == t)}
                 for t in sorted({l["first_seen"] for l in listings if l["first_seen"] != stamp})]
    scans.append({"time": stamp, "new": new_count})
    scans = scans[-cfg.get("bewaar_scans", 30):]
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(
            {
                "updated": stamp,
                "criteria": {
                    "max_prijs": cfg["max_prijs"],
                    "min_kamers": cfg.get("min_kamers", 0),
                    "gebieden": [g["naam"] for g in cfg["gebieden"]],
                },
                "status": status,
                "scans": scans,
                "listings": listings,
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    log(f"\nKlaar: {len(listings)} woningen in overzicht, {new_count} nieuw. Status: {status}")
    try:
        write_nieuwbouw(cfg, sources, stamp)
    except Exception as e:  # nieuwbouw mag de rest nooit breken
        log(f"   ! nieuwbouw mislukt: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
