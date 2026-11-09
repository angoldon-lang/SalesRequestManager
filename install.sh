#!/usr/bin/env bash
# Installer SRM (tutto in container). Uso:
#   ./install.sh                 # interattivo, sceglie da solo una porta web libera
#   ./install.sh --port 9090     # porta precisa (errore se occupata)
#   ./install.sh --demo          # prova senza Microsoft: nessun login, solo 127.0.0.1
#   ./install.sh --no-start      # prepara solo .env e controlla la porta
set -euo pipefail
cd "$(dirname "$0")"

PORT_ARG=""; DEMO=0; START=1
while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT_ARG="${2:?manca il numero di porta}"; shift 2 ;;
    --demo) DEMO=1; shift ;;
    --no-start) START=0; shift ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
    *) echo "Opzione sconosciuta: $1"; exit 1 ;;
  esac
done

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m  %s\n' "$*"; }
die()  { printf '\033[1;31mXX\033[0m  %s\n' "$*" >&2; exit 1; }

port_in_use() {   # vero se qualcosa ascolta sulla porta (qualsiasi processo o container)
  if command -v ss >/dev/null 2>&1; then
    ss -H -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "[:.]$1$"
  else
    (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null
  fi
}
set_env() {       # set_env CHIAVE VALORE  (aggiorna o aggiunge in .env)
  if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else printf '%s=%s\n' "$1" "$2" >> .env; fi
}
get_env() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- | sed 's/[[:space:]]*#.*//'; }

# ---- 1. prerequisiti ----
if [ "$START" = 1 ]; then
  command -v docker >/dev/null || die "Docker non trovato: https://docs.docker.com/engine/install/"
  docker compose version >/dev/null 2>&1 || die "Serve Docker Compose v2 ('docker compose', non 'docker-compose')"
  docker info >/dev/null 2>&1 || die "Il demone Docker non risponde (serve sudo? servizio avviato?)"
fi

# ---- 2. .env (mai sovrascritto se esiste) ----
if [ ! -f .env ]; then
  say "Creo .env"
  cp .env.example .env
  pw="$( (openssl rand -hex 16 2>/dev/null) || head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' )"
  set_env POSTGRES_PASSWORD "$pw"
  chmod 600 .env
else
  say ".env già presente: lo mantengo"
fi

# ---- 3. porta web ----
if [ -n "$PORT_ARG" ]; then
  port_in_use "$PORT_ARG" && die "La porta $PORT_ARG è già occupata. Scegline un'altra con --port."
  PORT="$PORT_ARG"
else
  PORT="$(get_env WEB_PORT)"; PORT="${PORT:-8088}"
  # Se la porta è occupata perché SRM stesso è già in esecuzione, la riuso (aggiornamento).
  if [ "$START" = 1 ] && docker compose ps -q web 2>/dev/null | grep -q .; then
    say "SRM già in esecuzione: riuso la porta $PORT"
  else
    start=$PORT
    while port_in_use "$PORT"; do PORT=$((PORT+1)); [ "$PORT" -lt $((start+100)) ] || die "Nessuna porta libera tra $start e $((start+99))"; done
    [ "$PORT" = "$start" ] || warn "Porta $start occupata: uso la $PORT"
  fi
fi
set_env WEB_PORT "$PORT"

# ---- 4. modalità demo / produzione ----
if [ "$DEMO" = 1 ] || { [ -z "$(get_env AZ_CLIENT_ID)" ] && [ "$(get_env AUTH_DISABLED)" != "true" ]; }; then
  if [ "$DEMO" = 0 ]; then
    warn "Microsoft Entra non configurato (AZ_CLIENT_ID vuoto)."
    if [ -t 0 ]; then read -r -p "    Avvio in modalità DEMO (senza login, solo da questa VM)? [s/N] " a; [ "${a:-n}" = s ] || [ "${a:-n}" = S ] && DEMO=1
    else warn "Modalità non interattiva: compila .env e rilancia, oppure usa --demo."; fi
  fi
  if [ "$DEMO" = 1 ]; then
    set_env AUTH_DISABLED true; set_env WEB_BIND 127.0.0.1; set_env GRAPH_MODE dry-run
    warn "DEMO: nessun login, tutti admin, mail solo simulate. Raggiungibile SOLO da 127.0.0.1."
  fi
fi

[ "$START" = 1 ] || { say "Preparazione completata (--no-start). Porta web: $PORT"; exit 0; }

# ---- 5. avvio ----
say "Costruisco e avvio i container (la prima volta richiede qualche minuto)"
docker compose up -d --build

say "Attendo che l'applicazione risponda…"
url="http://127.0.0.1:$PORT"
for _ in $(seq 1 60); do
  if curl -fsS "$url/health" >/dev/null 2>&1; then ok=1; break; fi; sleep 3
done
[ "${ok:-0}" = 1 ] || { docker compose ps; die "Non risponde. Vedi: docker compose logs api"; }

echo
say "SRM è attivo:  $url$( [ "$(get_env WEB_BIND)" = 127.0.0.1 ] || echo "   (dall'esterno: http://<ip-vm>:$PORT)" )"
echo "    Log:        docker compose logs -f api worker"
echo "    Stop/Start: docker compose stop / docker compose start"
echo "    Backup:     scripts/backup.sh"
[ "$DEMO" = 1 ] && echo "    Dati demo:  scripts/seed_demo.sh $url"
[ "$DEMO" = 1 ] || echo "    Entra: nel redirect URI SPA metti l'URL pubblico con questa porta (vedi docs/docker.md)"
exit 0
