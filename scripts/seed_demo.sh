#!/usr/bin/env bash
# Dati demo per sviluppo (backend con AUTH_DISABLED=true). Uso: scripts/seed_demo.sh [http://localhost:8000]
set -euo pipefail
API="${1:-http://localhost:8000}/api/v1"
H=(-H "X-Dev-User: admin@local" -H "Content-Type: application/json")
post() { curl -fsS "${H[@]}" -X "$1" "$API/$2" -d "$3" >/dev/null && echo "ok $2"; }
post POST vendors   '{"name":"Cisco"}'
post POST vendors   '{"name":"Fortinet"}'
post POST suppliers '{"name":"Arrow"}'
post POST suppliers '{"name":"Ingram Micro"}'
post POST agents    '{"full_name":"Mario Rossi","email":"mario.rossi@azienda.it"}'
post PUT  vendor-supplier-map '{"vendor_id":1,"supplier_id":1,"to_emails":["deals@arrow.example"],"is_preferred":true}'
post PUT  vendor-supplier-map '{"vendor_id":2,"supplier_id":2,"to_emails":["fortinet@ingram.example"],"is_preferred":true}'
