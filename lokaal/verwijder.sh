#!/bin/bash
# Haalt de lokale HuurRadar-scan weer van je Mac af (de repo-map laat je zelf staan of gooi je weg).
LABEL="nl.huurradar.scan"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Lokale scan verwijderd."
