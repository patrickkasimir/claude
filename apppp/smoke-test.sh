#!/bin/bash
# Smoke Test für Apppp
# Läuft vor und nach dem Refactoring — alles grün = App funktioniert noch

BASE_URL="http://localhost:3003"
FRONTEND_URL="http://localhost/claudeapps/apppp"
PASS=0
FAIL=0

green="\033[0;32m"
red="\033[0;31m"
reset="\033[0m"

check() {
  local label="$1"
  local result="$2"
  local expect="$3"

  if echo "$result" | grep -q "$expect"; then
    echo -e "${green}✓${reset} $label"
    ((PASS++))
  else
    echo -e "${red}✗${reset} $label"
    echo "    erwartet: '$expect'"
    echo "    erhalten: '$(echo "$result" | head -c 120)'"
    ((FAIL++))
  fi
}

check_status() {
  local label="$1"
  local url="$2"
  local expected_status="$3"

  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" "$url")
  if [ "$status" = "$expected_status" ]; then
    echo -e "${green}✓${reset} $label (HTTP $status)"
    ((PASS++))
  else
    echo -e "${red}✗${reset} $label (erwartet HTTP $expected_status, erhalten HTTP $status)"
    ((FAIL++))
  fi
}

echo ""
echo "=== Apppp Smoke Test ==="
echo ""

echo "--- Frontend ---"
check_status "Landing Page erreichbar"         "$FRONTEND_URL/"        "200"
check_status "index.html liefert 200"          "$FRONTEND_URL/index.html" "200"

echo ""
echo "--- API: Tasks ---"
TASKS=$(curl -s "$BASE_URL/tasks")
check "GET /tasks liefert JSON-Array"          "$TASKS"   "\["
check "Tasks haben id-Feld"                    "$TASKS"   '"id"'
check "Tasks haben title-Feld"                 "$TASKS"   '"title"'
check "Tasks haben status-Feld"                "$TASKS"   '"status"'

echo ""
echo "--- API: Users ---"
USERS=$(curl -s "$BASE_URL/users")
check "GET /users liefert JSON-Array"          "$USERS"   "\["
check "Users haben id-Feld"                    "$USERS"   '"id"'
check "Users haben name-Feld"                  "$USERS"   '"name"'

echo ""
echo "--- API: Incidents ---"
INCIDENTS=$(curl -s "$BASE_URL/incidents")
check "GET /incidents liefert JSON-Array"      "$INCIDENTS" "\["

echo ""
echo "--- API: CRUD Task (POST → GET → DELETE) ---"
NEW=$(curl -s -X POST "$BASE_URL/tasks" \
  -H "Content-Type: application/json" \
  -d '{"title":"__smoke_test__","status":"offen","priority":1}')
check "POST /tasks erstellt Task"              "$NEW"       '"id"'

TASK_ID=$(echo "$NEW" | grep -o '"id":[0-9]*' | head -1 | grep -o '[0-9]*')
if [ -n "$TASK_ID" ]; then
  # GET /tasks/:id existiert nicht im Backend — stattdessen in der Liste suchen
  ALL=$(curl -s "$BASE_URL/tasks")
  check "Task in GET /tasks auffindbar"        "$ALL"      "__smoke_test__"

  DEL=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE_URL/tasks/$TASK_ID")
  if [ "$DEL" = "200" ] || [ "$DEL" = "204" ]; then
    echo -e "${green}✓${reset} DELETE /tasks/$TASK_ID erfolgreich (HTTP $DEL)"
    ((PASS++))
  else
    echo -e "${red}✗${reset} DELETE /tasks/$TASK_ID fehlgeschlagen (HTTP $DEL)"
    ((FAIL++))
  fi
else
  echo -e "${red}✗${reset} Task-ID konnte nicht aus POST-Response gelesen werden"
  ((FAIL++))
fi

echo ""
echo "========================"
echo -e "Ergebnis: ${green}$PASS bestanden${reset} / ${red}$FAIL fehlgeschlagen${reset}"
echo ""

[ "$FAIL" -eq 0 ] && exit 0 || exit 1
