"""Extra bronnen voor HuurRadar: Vesteda, Woonstad Rotterdam, VBT/Bouwinvest,
Huispedia en WoningNet Midden-Holland (mijndak). Plus het verzamelen van
nieuwbouwprojecten voor het tabblad Nieuwbouw.

Elke scraper krijgt (gebied, cfg) en geeft een lijst woningen terug in hetzelfde
formaat als scrape.py. Bronnen die één keer voor alle gebieden ophalen (VBT,
Woonstad, mijndak) cachen hun resultaat binnen één run.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import scrape as core  # fetch, helpers

SOURCE_OK: set[str] = set()       # bronnen die deze run bereikbaar waren (ook als ze 0 woningen hadden)
NIEUWBOUW: dict[str, dict] = {}   # projecten voor het nieuwbouw-tabblad
EXISTING: dict[str, dict] = {}    # woningen uit vorige runs (gevuld door scrape.main)
_CACHE: dict[str, object] = {}

# middelpunt per plaats voor zoeken op afstand (Vesteda)
COORDS = {
    "rotterdam": (51.9420, 4.5100, 9),
    "nieuwerkerk-aan-den-ijssel": (51.9667, 4.6125, 4),
    "zevenhuizen": (52.0128, 4.5806, 4),
    "gouda": (52.0115, 4.7104, 5),
    "zoetermeer": (52.0575, 4.4931, 6),
}


def _http_json(method: str, url: str, body: dict | None = None, headers: dict | None = None):
    h = {**core.HEADERS, "Accept": "application/json", **(headers or {})}
    try:
        if method == "POST":
            h["Content-Type"] = "application/json"
            r = core.http.post(url, headers=h, data=json.dumps(body), timeout=30, **core.IMPERSONATE)
        else:
            r = core.http.get(url, headers=h, timeout=30, **core.IMPERSONATE)
    except Exception as e:
        core.log(f"   ! fout bij {url}: {e}")
        return None
    if r.status_code != 200:
        core.log(f"   ! {url} gaf status {r.status_code}")
        return None
    try:
        return r.json()
    except ValueError:
        return None


def _pc(pc: str | None) -> str | None:
    return core.find_postcode((pc or "").upper())


def _listing(source, url, title, price, address, postcode=None, wijk=None, rooms=None, surface=None,
             image=None, extra="", segment=None):
    return {
        "id": core.make_id(source, url), "source": source, "title": title, "url": url,
        "price": int(round(price)) if isinstance(price, (int, float)) and price else core.parse_int(str(price or "")),
        "price_text": "", "address": address, "postcode": postcode or core.find_postcode(address or ""),
        "wijk": wijk, "rooms": rooms, "surface": int(surface) if surface else None,
        "image": image, "extra": extra[:500], "segment": segment,
    }


# ------------------------------------------------------------------ Vesteda

def scrape_vesteda(gebied: dict, cfg: dict) -> list[dict]:
    lat, lng, radius = COORDS.get(gebied["slug"], (None, None, None))
    if lat is None:
        return []
    body = {"filters": [], "latitude": lat, "longitude": lng, "place": gebied["naam"], "placeType": 1,
            "radius": radius, "sorting": 0, "priceFrom": max(500, cfg.get("min_prijs", 0)),
            "priceTo": cfg["max_prijs"], "language": "nl"}
    data = _http_json("POST", "https://www.vesteda.com/api/units/search/facet", body)
    if not data or "results" not in data:
        return []
    SOURCE_OK.add("vesteda")
    res = data["results"]
    out = []
    for o in res.get("objects") or []:
        if o.get("status") not in (1, 5):  # 1 = te huur, 5 = nieuw
            continue
        url = urljoin("https://www.vesteda.com", o.get("url") or "")
        street = f"{o.get('street') or ''} {o.get('houseNumber') or ''}{(' ' + o['houseNumberAddition']) if o.get('houseNumberAddition') else ''}".strip()
        pc = _pc(o.get("postalCode"))
        out.append(_listing("vesteda", url, f"{o.get('entitysubtypelabel') or 'Woning'} {street}", o.get("priceUnformatted"),
                            f"{pc or ''} {o.get('city') or ''} ({o.get('complex') or o.get('district') or ''})".strip(),
                            postcode=pc, wijk=o.get("district") or o.get("complex"), rooms=(o.get("numberOfBedRooms") or 0) + 1 if o.get("numberOfBedRooms") else None,
                            surface=o.get("size"), extra=f"Vesteda complex {o.get('complex') or ''}"))
    # projecten -> nieuwbouw-tabblad
    for kind, items in (("nieuw", res.get("newComplexes") or []), ("complex", res.get("complexes") or [])):
        for c in items:
            url = urljoin("https://www.vesteda.com", c.get("url") or "")
            pmin, pmax = c.get("complexPriceMin") or 0, c.get("complexPriceMax") or 0
            add_project({
                "id": core.make_id("vesteda-p", url), "source": "vesteda", "name": c.get("street") or c.get("alt"),
                "city": c.get("city"), "wijk": c.get("district") or (c.get("location") or "").split(",")[-1].strip(),
                "lat": c.get("latitude"), "lng": c.get("longitude"), "url": url,
                "status": "Binnenkort in verhuur" if kind == "nieuw" else "Complex – woningen komen periodiek vrij",
                "price": f"€ {pmin} – € {pmax}" if pmin else "", "segment": "Middenhuur / vrije sector",
                "text": "Nieuw Vesteda-project, schrijf je in via de projectpagina." if kind == "nieuw"
                        else "Bestaand Vesteda-complex: losse woningen die vrijkomen verschijnen vanzelf in je overzicht.",
            }, gebied, cfg)
    return out


# ------------------------------------------------------------------ Woonstad Rotterdam

WOONSTAD_API = "https://wrf-prod-app-api-gateway.azurewebsites.net/api/portfolio/api/v3/woonstad/offering/vsh?size=200"


def scrape_woonstad(gebied: dict, cfg: dict) -> list[dict]:
    if gebied["slug"] != "rotterdam":
        return []
    data = _http_json("GET", WOONSTAD_API, headers={"Origin": "https://www.woonstadrotterdam.nl"})
    if not data or "items" not in data:
        return []
    SOURCE_OK.add("woonstad")
    out = []
    for it in data["items"]:
        unit = it.get("unit") or {}
        a = unit.get("address") or {}
        rent = (it.get("rentInfo") or {}).get("price")
        slug = (it.get("webSettings") or {}).get("url") or it.get("id")
        url = f"https://www.woonstadrotterdam.nl/aanbod/vrije-sector-huurwoning/{slug}"
        street = f"{a.get('street', '')} {a.get('number', '')}{a.get('houseletter') or ''}{('-' + a['addition']) if a.get('addition') else ''}".strip()
        out.append(_listing("woonstad", url, f"{unit.get('unitType') or 'Woning'} {street}", rent,
                            f"{a.get('zipcode', '')} Rotterdam ({a.get('cbsDistrict') or a.get('district') or ''})",
                            postcode=a.get("zipcode"), wijk=a.get("cbsDistrict"),
                            rooms=(unit.get("roomSpecification") or {}).get("rooms"),
                            surface=(unit.get("propertySpecification") or {}).get("surface"),
                            image=(it.get("image") or {}).get("url"),
                            extra=(it.get("mainContent") or {}).get("intro") or "", segment="vrije sector"))
    return out


def woonstad_nieuwbouw(cfg: dict) -> None:
    """Nieuwbouwprojecten van Woonstad (staan als data in de pagina)."""
    html = core.fetch("https://www.woonstadrotterdam.nl/themas/nieuwbouw")
    if not html:
        return
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', html, re.S)
    data = "".join(json.loads('"' + c + '"') for c in chunks)
    i = data.find('"data":[{"contentType":"nieuwbouwDetailPagina"')
    if i < 0:
        return
    try:
        arr, _ = json.JSONDecoder().raw_decode(data[data.find("[", i):])
    except ValueError:
        return
    rdam = next((g for g in cfg["gebieden"] if g["slug"] == "rotterdam"), None)
    for a in arr:
        p = a.get("properties") or {}
        if "redirect" in p and len(p) == 1:
            continue
        url = "https://www.woonstadrotterdam.nl" + (a.get("route") or {}).get("path", "")
        img = (p.get("headerAfbeelding") or [{}])[0].get("url")
        add_project({
            "id": core.make_id("woonstad-p", url), "source": "woonstad", "name": p.get("titel") or a.get("name"),
            "city": "Rotterdam", "wijk": ", ".join(p.get("buurt") or []), "url": url, "image": img,
            "status": p.get("status") or "Zie projectpagina", "price": "", "segment": _segment_from_text(p.get("introductieTekst") or ""),
            "text": (p.get("introductieTekst") or "").strip(), "updated": a.get("updateDate"),
        }, rdam, cfg)


# ------------------------------------------------------------------ VBT / Bouwinvest

def _vbt_all() -> list[dict]:
    if "vbt" in _CACHE:
        return _CACHE["vbt"]
    items = []
    for page in range(1, 25):
        html = core.fetch(f"https://vbtverhuurmakelaars.nl/woningen/{page}")
        if not html:
            break
        SOURCE_OK.add("vbt")
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("a.property")
        for c in cards:
            status = core.text_of(c.select_one(".status"))
            if "verhuurd" in status.lower():
                continue
            city = core.text_of(c.select_one(".items > div"))
            street = core.text_of(c.select_one(".items > span"))
            rows = {core.text_of(r.select_one("td")): core.text_of(r.select("td")[-1]) for r in c.select("tr") if r.select("td")}
            vis = c.select_one(".visimage")
            img = None
            if vis and "url(" in (vis.get("style") or ""):
                img = urljoin("https://vbtverhuurmakelaars.nl", vis["style"].split("url(")[1].split(")")[0].strip("'\""))
            url = urljoin("https://vbtverhuurmakelaars.nl", c.get("href"))
            items.append(_listing("vbt", url, f"{rows.get('Soort object', 'Woning')} {street}",
                                  core.parse_int(core.text_of(c.select_one(".price")).replace(",-", "")),
                                  f"{street}, {city}", rooms=core.parse_int(rows.get("Kamers")),
                                  surface=core.parse_int(rows.get("Woonoppervlakte")), image=img,
                                  extra=" ".join(f"{k}: {v}" for k, v in rows.items()) + f" status: {status}"))
            items[-1]["city"] = city
        if len(cards) < 12:
            break
    _CACHE["vbt"] = items
    return items


def scrape_vbt(gebied: dict, cfg: dict) -> list[dict]:
    out = []
    for l in _vbt_all():
        if l["city"].lower() != gebied["naam"].lower():
            continue
        l = dict(l)
        if gebied.get("postcodes") and not l.get("postcode"):
            old = EXISTING.get(l["id"])
            if old and old.get("postcode"):
                l["postcode"] = old["postcode"]
            elif l.get("price") is None or l["price"] <= cfg["max_prijs"]:
                html = core.fetch(l["url"])  # postcode staat alleen op de detailpagina
                if html:
                    l["postcode"] = core.find_postcode(core.text_of(BeautifulSoup(html, "html.parser")))
        out.append(l)
    return out


# ------------------------------------------------------------------ Huispedia

def scrape_huispedia(gebied: dict, cfg: dict) -> list[dict]:
    html = core.fetch(f"https://huispedia.nl/huurwoningen/{gebied['slug']}")
    if not html:
        return []
    SOURCE_OK.add("huispedia")
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for art in soup.find_all("article"):
        a = art.select_one("a[href]")
        if not a:
            continue
        txt = core.text_of(art)
        url = urljoin("https://huispedia.nl", a["href"])
        m = re.search(r"€\s?([\d.]+)\s*/mnd", txt)
        if not m:
            continue
        img = art.select_one("img")
        pc = core.find_postcode(txt)
        title = re.sub(r"^(Net op de markt|Nieuw|Uitgelicht|Onder optie)\s+", "", txt.split(pc if pc else "€")[0].strip())
        out.append(_listing("huispedia", url, title[:100] or "Huurwoning", core.parse_int(m.group(1)),
                            txt[:160], postcode=pc,
                            rooms=core.parse_int((re.search(r"(\d+)\s*kamers?", txt) or [None, None])[1]),
                            surface=core.parse_int((re.search(r"(\d+)\s*m²", txt) or [None, None])[1]),
                            image=img.get("src") if img else None, extra=txt))
    return out


# ------------------------------------------------------------------ WoningNet Midden-Holland (mijndak)

MIJNDAK = "https://middenholland.mijndak.nl"
MIJNDAK_CSRF = "T6C+9iB49TLra4jEsMeSckDMNhQ="  # standaard anoniem token van het OutSystems-platform


def _mijndak_all() -> list[dict]:
    if "mijndak" in _CACHE:
        return _CACHE["mijndak"]
    _CACHE["mijndak"] = []
    info = _http_json("GET", f"{MIJNDAK}/DAKWP/moduleservices/moduleversioninfo")
    version = (info or {}).get("versionToken")
    if not version:
        return []
    js = core.fetch(f"{MIJNDAK}/DAKWP/scripts/DAKWP.Overzicht.Woningaanbod.mvc.js")
    m = re.search(r'DataActionHaalUitgelogdAanbod", "screenservices/[^"]+", "([^"]+)"', js or "")
    if not m:
        return []
    data = _http_json("POST", f"{MIJNDAK}/DAKWP/screenservices/DAKWP/Overzicht/Woningaanbod/DataActionHaalUitgelogdAanbod",
                      {"versionInfo": {"moduleVersion": version, "apiVersion": m.group(1)},
                       "viewName": "Overzicht.Woningaanbod", "screenData": {"variables": {}}, "clientVariables": {}},
                      headers={"X-CSRFToken": MIJNDAK_CSRF, "OutSystems-locale": "nl-NL"})
    if not data or "data" not in data:
        return []
    SOURCE_OK.add("mijndak")
    out = []
    for p in ((data["data"].get("PublicatieLijst") or {}).get("List") or []):
        a, e = p.get("Adres") or {}, p.get("Eenheid") or {}
        street = f"{a.get('Straatnaam', '')} {a.get('Huisnummer', '')}{a.get('Huisletter') or ''}{('-' + a['HuisnummerToevoeging']) if a.get('HuisnummerToevoeging') else ''}".strip()
        url = f"{MIJNDAK}/DAKWP/HuisDetails?PublicatieId={p.get('Id')}"
        price = float(e.get("NettoHuur") or e.get("Brutohuur") or 0) or None
        model = (p.get("PublicatieModel") or "").lower()
        seg = "vrije sector" if "vrije" in model else ("middenhuur" if "midden" in model else "sociaal")
        foto = p.get("Foto_Locatie") or None
        out.append(_listing("mijndak", url, f"{e.get('DetailSoort') or 'Woning'} {street}", price,
                            f"{a.get('Postcode', '')} {a.get('Woonplaats', '')} ({a.get('Wijk', '')})", postcode=a.get("Postcode"),
                            wijk=a.get("Wijk"), rooms=e.get("AantalKamers") or None, surface=float(e.get("WoonVertrekkenTotOpp") or 0) or None,
                            image=urljoin(MIJNDAK, foto) if foto else None,
                            extra=f"{p.get('PublicatieModel')} reageren tot {p.get('EinddatumTijd')}", segment=seg))
        out[-1]["city"] = a.get("Woonplaats") or ""
    _CACHE["mijndak"] = out
    return out


def scrape_mijndak(gebied: dict, cfg: dict) -> list[dict]:
    return [l for l in _mijndak_all() if (l.get("city") or "").lower().startswith(gebied["naam"].lower()[:8])]


EXTRA_SCRAPERS = {
    "vesteda": scrape_vesteda,
    "woonstad": scrape_woonstad,
    "vbt": scrape_vbt,
    "huispedia": scrape_huispedia,
    "mijndak": scrape_mijndak,
}


# ------------------------------------------------------------------ nieuwbouw

def _segment_from_text(t: str) -> str:
    t = t.lower()
    segs = [s for s, k in (("Sociale huur", "sociale"), ("Middenhuur", "midden"), ("Vrije sector", "vrije sector"),
                           ("Studenten", "student"), ("Koop", "koop")) if k in t]
    return " / ".join(segs)


def in_area(project: dict, gebied: dict | None, cfg: dict) -> bool:
    """Ligt een project in een van de gekozen gebieden? Op postcode, coördinaten of trefwoorden."""
    if gebied is None:
        return False
    if project.get("postcode") and gebied.get("postcodes"):
        return core.postcode_in_ranges(project["postcode"], gebied["postcodes"])
    hay = " ".join(str(project.get(k) or "") for k in ("name", "wijk", "text", "url")).lower()
    words = [w.lower() for w in gebied.get("wijken", [])] + [w.lower() for w in cfg.get("nieuwbouw_extra_trefwoorden", {}).get(gebied["slug"], [])]
    lat, lng = project.get("lat"), project.get("lng")
    if gebied.get("postcodes"):
        if lat and lng:  # coördinaten bekend: alleen de kaart telt
            return any(b[0] <= lat <= b[2] and b[1] <= lng <= b[3]
                       for b in cfg.get("nieuwbouw_kaartvakken", {}).get(gebied["slug"], []))
        return any(re.search(r"\b" + re.escape(w) + r"\b", hay) for w in words)
    if lat and lng and gebied["slug"] in COORDS:  # hele plaats: binnen ~5 km van het centrum
        c = COORDS[gebied["slug"]]
        return abs(lat - c[0]) < 0.045 and abs(lng - c[1]) < 0.07
    return (project.get("city") or "").lower() == gebied["naam"].lower() or gebied["naam"].lower() in hay


def add_project(p: dict, gebied: dict | None, cfg: dict) -> None:
    if not in_area(p, gebied, cfg):
        return
    p["area"] = gebied["naam"]
    NIEUWBOUW.setdefault(p["id"], p)
