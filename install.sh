#!/usr/bin/env bash
# Installer SRM (tutto in container). Uso:
#   ./install.sh                 # interattivo, sceglie da solo una porta web libera
#   ./install.sh --port 9090     # porta precisa (errore se occupata)
#   ./install.sh --https --host srm.azienda.it   # rete interna con HTTPS (CA + certificato generati)
#   ./install.sh --https --host srm.azienda.it --cert c.pem --key k.pem   # certificato aziendale
#   ./install.sh --bind 10.0.0.5 # ascolta solo su quell'IP della VM (consigliato)
#   ./install.sh --admin-password 'Iniziale#2026'  # password iniziale dell'admin (default: ChangeMe!2026)
#   ./install.sh --no-start      # prepara solo .env/certificati e controlla la porta
set -euo pipefail
cd "$(dirname "$0")"

PORT_ARG=""; ADMIN_PW_ARG=""; START=1; HTTPS=0; HOST_ARG=""; CERT_ARG=""; KEY_ARG=""; BIND_ARG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT_ARG="${2:?manca il numero di porta}"; shift 2 ;;
    --admin-password) ADMIN_PW_ARG="${2:?manca la password}"; shift 2 ;;
    --https) HTTPS=1; shift ;;
    --host) HOST_ARG="${2:?manca il nome host}"; shift 2 ;;
    --cert) CERT_ARG="${2:?manca il file certificato}"; shift 2 ;;
    --key) KEY_ARG="${2:?manca il file chiave}"; shift 2 ;;
    --bind) BIND_ARG="${2:?manca indirizzo IP}"; shift 2 ;;
    --no-start) START=0; shift ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
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
set_env() {       # set_env CHIAVE VALORE  (aggiorna o aggiunge in .env; i valori con # $ spazi vanno tra apici singoli)
  local v="$2"
  case "$v" in *\'*) die "Il valore di $1 non può contenere l'apice singolo";; esac
  case "$v" in *[\ \#\$\"\&\|\!]*) v="'$v'";; esac
  local e; e="$(printf '%s' "$v" | sed -e 's/[\\&|]/\\&/g')"
  if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$e|" .env; else printf '%s=%s\n' "$1" "$v" >> .env; fi
}
get_env() {       # valore senza commento finale (" # ...") e senza apici
  { grep -E "^$1=" .env 2>/dev/null || true; } | head -1 | cut -d= -f2- | sed -E "s/[[:space:]]+#.*$//; s/^'(.*)'$/\1/"
}

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

[ -n "$(get_env SECRET_KEY)" ] || set_env SECRET_KEY "$( (openssl rand -hex 32 2>/dev/null) || head -c 48 /dev/urandom | od -An -tx1 | tr -d ' \n' )"
[ -z "$ADMIN_PW_ARG" ] || set_env DEFAULT_ADMIN_PASSWORD "$ADMIN_PW_ARG"
[ -n "$(get_env AUTH_MODE)" ] || set_env AUTH_MODE local
[ -n "$(get_env DEFAULT_ADMIN_PASSWORD)" ] || set_env DEFAULT_ADMIN_PASSWORD 'ChangeMe!2026'

# ---- 2b. HTTPS interno (il login Microsoft richiede HTTPS fuori da localhost) ----
has_tls() { [ -f certs/tls.crt ] && [ -f certs/tls.key ]; }
if [ -n "$CERT_ARG$KEY_ARG" ]; then HTTPS=1; fi
if [ "$HTTPS" = 1 ]; then
  command -v openssl >/dev/null || die "openssl non trovato (serve per i certificati)"
  HOST="${HOST_ARG:-$(get_env WEB_HOST)}"
  [ -n "$HOST" ] || { [ -t 0 ] && read -r -p "Nome DNS interno con cui gli utenti apriranno SRM (es. srm.azienda.it): " HOST || true; }
  HOST="${HOST:-$(hostname -f 2>/dev/null || hostname)}"
  mkdir -p certs
  if [ -n "$CERT_ARG" ]; then
    [ -f "$CERT_ARG" ] && [ -f "$KEY_ARG" ] || die "--cert e --key devono essere file esistenti"
    [ "$(openssl x509 -in "$CERT_ARG" -noout -pubkey | openssl sha256)" = "$(openssl pkey -in "$KEY_ARG" -pubout | openssl sha256)" ] \
      || die "La chiave non corrisponde al certificato"
    cp "$CERT_ARG" certs/tls.crt; cp "$KEY_ARG" certs/tls.key; chmod 600 certs/tls.key
    say "Certificato aziendale installato in certs/"
  elif has_tls; then
    say "Certificati già presenti in certs/: li mantengo"
  else
    say "Genero CA interna + certificato per: $HOST"
    IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
    SAN="DNS:$HOST"; [ -z "$IP" ] || SAN="$SAN,IP:$IP"
    openssl req -x509 -newkey rsa:4096 -nodes -days 3650 -keyout certs/ca.key -out certs/ca.crt \
      -subj "/O=SRM/CN=SRM Internal CA" >/dev/null 2>&1
    openssl req -newkey rsa:2048 -nodes -keyout certs/tls.key -out certs/tls.csr -subj "/O=SRM/CN=$HOST" >/dev/null 2>&1
    printf 'subjectAltName=%s\nbasicConstraints=CA:FALSE\nextendedKeyUsage=serverAuth\n' "$SAN" > certs/san.ext
    openssl x509 -req -in certs/tls.csr -CA certs/ca.crt -CAkey certs/ca.key -CAcreateserial \
      -days 825 -extfile certs/san.ext -out certs/tls.crt >/dev/null 2>&1
    rm -f certs/tls.csr certs/san.ext certs/ca.srl; chmod 600 certs/tls.key certs/ca.key
    say "Certificato valido 825 giorni. Distribuisci certs/ca.crt ai PC (radice attendibile): vedi docs/docker.md"
  fi
  set_env WEB_HOST "$HOST"
fi
if has_tls; then SCHEME=https; else SCHEME=http; fi
[ -z "$BIND_ARG" ] || set_env WEB_BIND "$BIND_ARG"

# ---- 3. porta web ----
if [ -n "$PORT_ARG" ]; then
  port_in_use "$PORT_ARG" && die "La porta $PORT_ARG è già occupata. Scegline un'altra con --port."
  PORT="$PORT_ARG"
else
  PORT="$(get_env WEB_PORT)"; PORT="${PORT:-8088}"
  [ "$SCHEME" = https ] && [ "$PORT" = 8088 ] && PORT=8443
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

[ "$START" = 1 ] || { say "Preparazione completata (--no-start). Porta web: $PORT"; exit 0; }

# ---- 5. avvio ----
say "Costruisco e avvio i container (la prima volta richiede qualche minuto)"
docker compose up -d --build

say "Attendo che l'applicazione risponda…"
url="$SCHEME://127.0.0.1:$PORT"
for _ in $(seq 1 60); do
  if curl -fskS "$url/health" >/dev/null 2>&1; then ok=1; break; fi; sleep 3
done
[ "${ok:-0}" = 1 ] || { docker compose ps; die "Non risponde. Vedi: docker compose logs api"; }

echo
PUB="$(get_env WEB_HOST)"; PUB="${PUB:-<ip-o-nome-vm>}"
say "SRM è attivo sulla VM:  $url"
[ "$(get_env WEB_BIND)" = 127.0.0.1 ] || echo "    Dalla rete interna:  $SCHEME://$PUB:$PORT"
echo "    Log:        docker compose logs -f api worker"
echo "    Stop/Start: docker compose stop / docker compose start"
echo "    Backup:     scripts/backup.sh"
echo
say "Primo accesso:  utente  admin   password  $(get_env DEFAULT_ADMIN_PASSWORD)"
echo "    Al primo login ti verrà chiesto di cambiare la password (obbligatorio)."
echo "    Poi crea gli utenti e gli agenti commerciali da  Utenti e ruoli."
if [ "$SCHEME" != https ]; then
  warn "Sei in HTTP: le password viaggiano in chiaro sulla rete. Consigliato: ./install.sh --https --host <nome-dns>"
fi
[ ! -f certs/ca.crt ] || echo "    Certificato CA da distribuire ai PC: certs/ca.crt"
[ "$(get_env AUTH_MODE)" != entra ] || echo "    Entra: redirect URI SPA = $SCHEME://$PUB:$PORT   (vedi docs/m365-setup.md)"
exit 0
