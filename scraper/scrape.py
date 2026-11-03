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


def fetch(url: str) -> str | None:
    try:
        r = http.get(url, headers=HEADERS, timeout=30, **IMPERSONATE)
    except Exception as e:  # netwerkfout
        log(f"   ! fout bij ophalen {url}: {e}")
        return None
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
        img = it.select_one("img")
        image = None
        if img:
            image = img.get("src") or img.get("data-src")
            if image and image.startswith("data:"):
                image = img.get("data-src")
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
                "image": (img.get("src") or img.get("data-src")) if img else None,
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


def matches(listing: dict, gebied: dict, cfg: dict) -> bool:
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


# ----------------------------------------------------------------- main

def load_existing() -> dict:
    if OUTPUT_PATH.exists():
        try:
            return json.loads(OUTPUT_PATH.read_text())
        except json.JSONDecodeError:
            pass
    return {"listings": []}


def main() -> int:
    cfg = yaml.safe_load(CONFIG_PATH.read_text())
    existing = {l["id"]: l for l in load_existing().get("listings", [])}
    stamp = now_iso()
    found: dict[str, dict] = {}
    status = {}

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
            if results:
                ok = True
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
        # als een bron deze run faalde, gooien we zijn advertenties niet weg
        if old["source"] in failed_sources:
            merged[lid] = old
            continue
        if datetime.fromisoformat(old["last_seen"]) >= cutoff:
            old["active"] = False
            merged[lid] = old

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
    return 0


if __name__ == "__main__":
    sys.exit(main())
