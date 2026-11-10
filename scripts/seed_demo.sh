#!/usr/bin/env bash
# Dati di esempio (vendor, supplier, mapping, un agente Sales). Uso: scripts/seed_demo.sh <url> <utente-admin> <password-admin>
set -euo pipefail
URL="${1:?uso: seed_demo.sh <url> <utente-admin> <password-admin>   es. http://127.0.0.1:8088 admin 'la-tua-password'}"
USERNAME="${2:?manca utente admin}"; PASSWORD="${3:?manca la password}"
API="${URL%/}/api/v1"; CURL=(curl -fskS -H "Content-Type: application/json")
TOKEN="$("${CURL[@]}" -X POST "$API/auth/login" -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')"
call() { "${CURL[@]}" -H "Authorization: Bearer $TOKEN" -X "$1" "$API/$2" -d "$3" >/dev/null && echo "ok  $2"; }
call POST vendors   '{"name":"Cisco"}'
call POST vendors   '{"name":"Fortinet"}'
call POST suppliers '{"name":"Arrow"}'
call POST suppliers '{"name":"Ingram Micro"}'
call PUT  vendor-supplier-map '{"vendor_id":1,"supplier_id":1,"to_emails":["deals@arrow.example.com"],"is_preferred":true}'
call PUT  vendor-supplier-map '{"vendor_id":2,"supplier_id":2,"to_emails":["fortinet@ingram.example.com"],"is_preferred":true}'
call POST users '{"username":"mario.rossi","full_name":"Mario Rossi","email":"mario.rossi@example.com","role":"SALES","password":"Provvisoria-2026"}'
echo "Agente di esempio: mario.rossi / Provvisoria-2026 (dovrà cambiarla al primo accesso)"
