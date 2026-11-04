import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scraper"))
import scrape

PARARIUS = """
<ul><li class="search-list__item search-list__item--listing">
<section class="listing-search-item listing-search-item--list listing-search-item--for-rent">
 <div class="listing-search-item__depiction"><img src="https://img/1.jpg"></div>
 <h2 class="listing-search-item__title"><a class="listing-search-item__link listing-search-item__link--title" href="/appartement-te-huur/rotterdam/abc/oudedijk">Appartement Oudedijk</a></h2>
 <div class="listing-search-item__sub-title'">3062 AB Rotterdam (Kralingen-Oost)</div>
 <div class="listing-search-item__price">€ 1.350 per maand</div>
 <ul><li class="illustrated-features__item illustrated-features__item--surface-area">62 m²</li>
 <li class="illustrated-features__item illustrated-features__item--number-of-rooms">3 kamers</li></ul>
</section></li>
<li><section class="listing-search-item listing-search-item--for-rent">
 <h2 class="listing-search-item__title"><a class="listing-search-item__link--title" href="/x/rotterdam/def/zuidplein">Studio Zuidplein</a></h2>
 <div class="listing-search-item__sub-title">3083 CW Rotterdam (Tarwewijk)</div>
 <div class="listing-search-item__price">€ 950 per maand</div>
</section></li></ul>"""

FUNDA = """<div><div class="card"><a href="/detail/huur/gouda/appartement-markt-1/123/"><h2>Markt 1</h2></a>
<p>2801 JE Gouda</p><p>€ 1.100 /maand</p><ul><li>55 m²</li><li>2 kamers</li></ul></div></div>"""

def test_pararius():
    ls = scrape.parse_pararius_like(PARARIUS, "https://www.pararius.nl", "pararius")
    assert len(ls) == 2
    a = ls[0]
    assert a["price"] == 1350 and a["surface"] == 62 and a["rooms"] == 3
    assert a["postcode"] == "3062 AB" and a["wijk"] == "Kralingen-Oost"
    assert a["url"].startswith("https://www.pararius.nl/appartement")

def test_filter():
    import yaml
    cfg = yaml.safe_load(open(scrape.CONFIG_PATH))
    rdam = cfg["gebieden"][0]
    ls = scrape.parse_pararius_like(PARARIUS, "https://www.pararius.nl", "pararius")
    assert scrape.matches(ls[0], rdam, cfg)          # Kralingen 3062 -> ja
    assert not scrape.matches(ls[1], rdam, cfg)      # Tarwewijk 3083 -> nee
    no_pc = {"price": 1000, "postcode": None, "wijk": "Ommoord", "address": "", "title": ""}
    assert scrape.matches(no_pc, rdam, cfg)
    assert not scrape.matches({**ls[0], "price": 2000}, rdam, cfg)

def test_funda():
    ls = scrape.parse_funda(FUNDA, "https://www.funda.nl")
    assert len(ls) == 1 and ls[0]["price"] == 1100 and ls[0]["postcode"] == "2801 JE" and ls[0]["surface"] == 55

def test_lazy_image_and_swap():
    from bs4 import BeautifulSoup
    html = """<section class="listing-search-item"><wc-picture><picture>
      <source srcset="https://casco-media-prod.global.ssl.fastly.net/a?w=300 1x, https://casco-media-prod.global.ssl.fastly.net/a?w=600 2x">
      <img src="data:image/gif;base64,AAA" alt=""></picture></wc-picture></section>"""
    assert scrape.pick_image(BeautifulSoup(html, "html.parser")).endswith("w=600")
    html2 = """<section><noscript><img src="https://img.example.com/foto.jpg"></noscript></section>"""
    assert scrape.pick_image(BeautifulSoup(html2, "html.parser")) == "https://img.example.com/foto.jpg"
    import yaml
    cfg = yaml.safe_load(open(scrape.CONFIG_PATH))
    assert scrape.is_excluded({"title": "x", "image": "https://cdn/x?original_uri=woningruil.nl/1.jpg"}, cfg)
    assert scrape.is_excluded({"title": "x", "detail_text": "Ik wil mijn woning ruilen met..."}, cfg)
    assert not scrape.is_excluded({"title": "Appartement Bergweg", "extra": "3 kamers"}, cfg)


def test_nieuwbouw_area():
    import yaml, sources
    cfg = yaml.safe_load(open(scrape.CONFIG_PATH))
    rdam = cfg["gebieden"][0]
    assert not sources.in_area({"name": "Baljuw", "wijk": "Wijk 02 Rhoon-Noord", "lat": 51.857, "lng": 4.41}, rdam, cfg)
    assert sources.in_area({"name": "Parktoren", "wijk": "Prins Alexander", "lat": 51.952, "lng": 4.553}, rdam, cfg)
    assert sources.in_area({"name": "Woonstad", "text": "Nieuwbouw aan de Gerdesiaweg"}, rdam, cfg)
    assert not sources.in_area({"name": "Atlas Hillesluis", "text": "Colosseumweg"}, rdam, cfg)


def test_coordinate_fallback():
    import yaml
    cfg = yaml.safe_load(open(scrape.CONFIG_PATH))
    rdam = cfg["gebieden"][0]
    base = {"price": 1100, "postcode": None, "title": "Bergweg", "address": "Bergweg, Rotterdam"}
    assert scrape.matches({**base, "lat": 51.935, "lng": 4.475}, rdam, cfg)      # Noord
    assert not scrape.matches({**base, "lat": 51.885, "lng": 4.49}, rdam, cfg)   # Zuid
