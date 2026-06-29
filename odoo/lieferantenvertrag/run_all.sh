#!/usr/bin/env bash
# Baut das komplette Lieferantenvertrags-Customizing in einem Rutsch auf.
# Alle Schritte sind idempotent (mehrfach ausfuehrbar, keine Duplikate).
# Voraussetzung: .env ist ausgefuellt (siehe .env.example).
set -euo pipefail
cd "$(dirname "$0")"

echo "### 1/7  Discovery";            python3 01_discovery.py
echo "### 2/7  Modell + Felder";      python3 03_model.py
echo "### 3/7  Einkaufs-Verknuepfung";python3 04_purchase_link.py
echo "### 4/7  Mehrsprachigkeit";     python3 05_translations.py
echo "### 5/7  Automatisierungen";    python3 06_mail_and_automations.py
echo "### 6/7  Views/Menue";          python3 07_views.py
echo "### 7/7  Smart-Button Partner"; python3 10_smart_button.py

echo
echo "Fertig. Optional:"
echo "  python3 08_validate.py         # Testdaten anlegen + pruefen"
echo "  python3 09_cleanup_testdata.py # Testdaten wieder entfernen"
