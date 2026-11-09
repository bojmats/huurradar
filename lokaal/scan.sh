#!/bin/bash
# HuurRadar – scan van Pararius, Huurwoningen.nl en Funda vanaf je eigen Mac.
# Wordt 2x per dag gestart door launchd (zie installeer.sh). Handmatig: bash lokaal/scan.sh
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO" || exit 1
echo "=== $(date '+%Y-%m-%d %H:%M') HuurRadar lokale scan ==="

# niet scannen zonder internet (bijv. net uit slaapstand)
for i in 1 2 3 4 5 6; do
  /usr/bin/curl -s -o /dev/null --max-time 5 https://github.com && break
  echo "wacht op internet..."; sleep 20
done

for poging in 1 2 3; do
  git fetch -q origin main && git reset -q --hard origin/main || { echo "git fetch mislukt"; exit 1; }
  "$REPO/.venv/bin/python" scraper/scrape.py --modus lokaal || { echo "scraper mislukt"; exit 1; }
  git add docs/listings.json
  if git diff --cached --quiet; then echo "geen wijzigingen"; exit 0; fi
  git -c user.name="huurradar-mac" -c user.email="huurradar-mac@users.noreply.github.com" \
      commit -q -m "Lokale scan $(date '+%d-%m %H:%M')"
  if git push -q origin HEAD:main; then echo "gepusht"; exit 0; fi
  echo "push botste met een GitHub-scan, opnieuw ($poging)"; sleep 30
done
echo "push 3x mislukt"; exit 1
