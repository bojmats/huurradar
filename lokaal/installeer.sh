#!/bin/bash
# HuurRadar – installeert de lokale scan op je Mac (2x per dag, 08:05 en 18:05).
set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="nl.huurradar.scan"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/huurradar.log"

echo "1/4  Python controleren..."
if ! /usr/bin/python3 -c "import sys; assert sys.version_info >= (3, 9)" 2>/dev/null; then
  echo "     Python 3.9+ ontbreekt. Er verschijnt nu een venster om de Command Line Tools te installeren;"
  echo "     klik op Installeer en draai dit script daarna opnieuw."
  xcode-select --install || true
  exit 1
fi

echo "2/4  Benodigde pakketten installeren (eenmalig, ±1 minuut)..."
/usr/bin/python3 -m venv "$REPO/.venv"
"$REPO/.venv/bin/pip" install -q --upgrade pip
"$REPO/.venv/bin/pip" install -q -r "$REPO/requirements.txt"

echo "3/4  Planning instellen (08:05 en 18:05; gemist door slaapstand = zodra je Mac wakker wordt)..."
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$REPO/lokaal/scan.sh</string></array>
  <key>StartCalendarInterval</key><array>
    <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>5</integer></dict>
    <dict><key>Hour</key><integer>18</integer><key>Minute</key><integer>5</integer></dict>
  </array>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "4/4  Eerste scan draaien (±1-2 minuten)..."
bash "$REPO/lokaal/scan.sh"

echo
echo "Klaar! HuurRadar scant nu elke dag om 08:05 en 18:05 Pararius, Huurwoningen.nl en Funda vanaf deze Mac."
echo "Logboek bekijken:  tail -50 $LOG"
echo "Verwijderen:       bash $REPO/lokaal/verwijder.sh"
