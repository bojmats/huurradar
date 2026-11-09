# Lokale scan op je Mac

Pararius, Huurwoningen.nl en Funda blokkeren de servers van GitHub. Deze drie sites
worden daarom 2x per dag (08:05 en 18:05) vanaf je eigen Mac opgehaald. De resultaten
gaan naar dezelfde repo, dus je ziet alles gewoon op je HuurRadar-site.

## Installeren (eenmalig, ±5 min)

1. **Token maken** (zodat je Mac naar de repo mag pushen):
   github.com → je profielfoto → *Settings* → *Developer settings* → *Personal access tokens*
   → *Fine-grained tokens* → *Generate new token*.
   - Naam: `huurradar-mac`, Expiration: 1 jaar
   - Repository access: *Only select repositories* → `huurradar`
   - Permissions → Repository permissions → **Contents: Read and write**
   - *Generate token* en kopieer hem (begint met `github_pat_`).
2. **Terminal openen** (Cmd + spatie, typ "Terminal") en plak:
   ```
   git clone https://github.com/bojmats/huurradar.git ~/huurradar && bash ~/huurradar/lokaal/installeer.sh
   ```
3. Tijdens de eerste scan vraagt git om inloggegevens:
   - Username: `bojmats`
   - Password: **plak de token** (je ziet niks verschijnen tijdens het plakken, dat is normaal) en druk Enter.
   macOS bewaart dit in je sleutelhanger; daarna gaat alles automatisch.

## Goed om te weten
- Staat je Mac om 08:05 of 18:05 uit of in slaapstand, dan draait de scan zodra hij weer wakker wordt.
- Logboek: `tail -50 ~/Library/Logs/huurradar.log`
- Handmatig scannen: `bash ~/huurradar/lokaal/scan.sh`
- Stoppen: `bash ~/huurradar/lokaal/verwijder.sh`
- De map `~/huurradar` is alleen voor de scan; wijzigingen die je daar zelf maakt worden overschreven.
- Je kunt nog steeds blokkades krijgen (vooral Funda); dan zie je het bolletje op je site rood worden.
