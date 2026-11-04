# HuurRadar

Checkt twee keer per dag (08:17 en 18:17) Pararius, Huurwoningen.nl, Funda, Vesteda, Woonstad, vb&t, Huispedia en WoningNet Midden-Holland Pararius, Huurwoningen.nl en Funda op nieuwe huurwoningen
in jouw gebieden en onder jouw maximumprijs, en zet ze in een overzichtspagina.
Draait gratis op GitHub, ook als je laptop uit staat.

## Installeren (±10 minuten)

1. **Repo aanmaken** – ga naar github.com → *New repository* → naam bijv. `huurradar`
   → **Public** (nodig voor gratis GitHub Pages) → *Create repository*.
2. **Bestanden uploaden** – pak de zip uit, klik in je nieuwe repo op
   *uploading an existing file* en sleep **de inhoud** van de map erin
   (dus `config.yaml`, `scraper/`, `docs/`, `.github/` enz.) → *Commit changes*.
   Let op: de map `.github` is op een Mac verborgen; druk in Finder op `Cmd + Shift + .` om hem te zien.
3. **Schrijfrechten aan** – *Settings → Actions → General → Workflow permissions*
   → **Read and write permissions** → *Save*.
4. **Overzichtspagina aan** – *Settings → Pages* → Source: *Deploy from a branch*
   → Branch: `main`, map `/docs` → *Save*. Na een minuut staat je app op
   `https://<jouw-gebruikersnaam>.github.io/huurradar/`.
5. **Eerste run starten** – tab *Actions* → *Huurwoningen checken* → *Run workflow*.
   Daarna draait hij vanzelf om 08:17 en 18:17.

Tip: open de pagina op je telefoon en kies *Zet op beginscherm*, dan heb je hem als app.

## Instellingen aanpassen

Open `config.yaml` op GitHub, klik op het potloodje, pas aan en *Commit*:

- `max_prijs` – maximale huur (nu €1.500)
- `min_kamers`, `min_oppervlakte`
- `gebieden` – plaatsen en (voor Rotterdam) postcodegebieden:
  Noord 3031–3039, Nesselande 3059, Kralingen 3061–3063, Prins Alexander/Ommoord 3064–3069.
  Wil je bijv. ook Hillegersberg, voeg `"3051-3056"` toe.
- `bronnen` – een site aan of uit zetten.

## De overzichtspagina

- Tabblad *Alle woningen* toont alles wat nu online staat.
- Filters op gebied, site, prijs, en zoeken op straat/wijk.
- Bolletjes rechtsboven: groen = site werkte bij de laatste run, rood = geblokkeerd/fout.
- Elke scan krijgt een eigen tabblad met alleen de nieuwe woningen; een oranje stip = nog niet bekeken.

## Goed om te weten

- **Funda** blokkeert verzoeken van servers vaak. Staat het bolletje rood, dan
  werken Pararius en Huurwoningen.nl gewoon door. Je kunt Funda dan uitzetten in `config.yaml`.
- Sites passen soms hun opmaak aan; vindt een bron ineens 0 woningen, dan moet de
  parser in `scraper/scrape.py` worden bijgewerkt.
- Scrapen staat in de gebruiksvoorwaarden van deze sites niet toegestaan. Voor
  persoonlijk gebruik in dit tempo (2× per dag, met pauzes) is het risico klein,
  maar gebruik het niet commercieel.
- GitHub start geplande runs soms een paar minuten later dan gepland.
- Lokaal testen: `pip install -r requirements.txt && python scraper/scrape.py`,
  daarna `docs/index.html` openen via een lokale server (`python -m http.server -d docs`).
