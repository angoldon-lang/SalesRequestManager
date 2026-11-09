# Installazione con Docker (pacchetto unico)

Un solo `docker-compose.yml` avvia **database + API + worker + web**. Pensato per una VM con altre installazioni.

## Isolamento (niente conflitti)
| Cosa | Come |
|---|---|
| Database | PostgreSQL 16 **dentro** un container. **Nessuna porta pubblicata**: non tocca 5432/5433 né i Postgres già presenti |
| API / worker | nessuna porta pubblicata, comunicano solo sulla rete interna del progetto |
| Web | **unica porta pubblicata**: `WEB_PORT` (default **8088**) |
| Rete e dati | rete `srm_default` e volume `srm_pgdata` dedicati (prefisso del progetto `srm`) |

## Installazione
```bash
git clone https://github.com/angoldon-lang/SalesRequestManager.git
cd SalesRequestManager
git checkout claude/focused-sagan-5wglk0
./install.sh
```
`install.sh`:
1. verifica Docker e Compose v2;
2. crea `.env` con una password DB casuale (se non esiste, non lo sovrascrive mai);
3. **cerca una porta web libera** a partire da 8088 e la scrive in `.env`;
4. costruisce e avvia i container, poi attende che l'app risponda e stampa l'URL.

Opzioni: `--port 9090` (porta precisa, errore se occupata), `--demo` (prova senza Microsoft: nessun login, solo `127.0.0.1`), `--no-start`.

### Scegliere la porta a mano
In `.env`: `WEB_PORT=9090`, poi `docker compose up -d`. Per vedere cosa è già occupato: `ss -ltnp | grep LISTEN`.
`WEB_BIND=127.0.0.1` rende l'app raggiungibile solo dalla VM: usalo se c'è già un reverse proxy (nginx/Caddy/Traefik) che pubblica `https://srm.azienda.it` verso `127.0.0.1:<WEB_PORT>`.

### Prova rapida (senza Azure)
```bash
./install.sh --demo        # poi: scripts/seed_demo.sh http://127.0.0.1:<porta>
```
In demo non c'è login e tutti sono admin: per questo resta legato a 127.0.0.1. Da un altro PC: `ssh -L 8088:127.0.0.1:8088 utente@vm`.

### Produzione (con Microsoft 365)
1. Segui [m365-setup.md](m365-setup.md) e compila in `.env`: `AZ_TENANT_ID`, `AZ_CLIENT_ID`, `AZ_CLIENT_SECRET`, `ADMIN_EMAILS`, `GRAPH_MODE=graph`, `ANTHROPIC_API_KEY`.
2. **Redirect URI SPA su Entra** = l'URL con cui gli utenti aprono l'app, **porta inclusa** (es. `http://10.0.0.5:8088` oppure `https://srm.azienda.it` se c'è il proxy). Se cambi porta o dominio va aggiornato su Entra.
3. `AZ_CLIENT_ID` è incorporato nel frontend in fase di build: dopo averlo cambiato esegui `docker compose up -d --build`.
4. Usa HTTPS (reverse proxy): il login Microsoft lo richiede fuori da `localhost`.

## Uso quotidiano
```bash
docker compose ps                         # stato
docker compose logs -f api worker         # log
docker compose stop / start               # ferma / riavvia (i dati restano)
git pull && docker compose up -d --build  # aggiornamento (le migrazioni partono da sole)
docker compose exec db psql -U srm srm    # shell SQL
```
`docker compose down` ferma e rimuove i container **ma non i dati**. `docker compose down -v` cancella anche il database: non usarlo.

## Backup e ripristino
```bash
scripts/backup.sh               # backups/srm-AAAA-MM-GG_HHMM.sql.gz, conserva gli ultimi 14 giorni
scripts/restore.sh backups/srm-….sql.gz
```
Cron giornaliero: `0 2 * * * cd /percorso/SalesRequestManager && scripts/backup.sh >> backups/backup.log 2>&1`

## Problemi frequenti
- **`port is already allocated` / `address already in use`:** cambia `WEB_PORT` in `.env` e rilancia `docker compose up -d`.
- **L'app non parte, l'API non è `healthy`:** `docker compose logs api` (di solito password DB cambiata dopo il primo avvio: il volume conserva la vecchia; ripristina la password originale in `.env`).
- **`permission denied` su docker:** usa `sudo ./install.sh` oppure aggiungi l'utente al gruppo `docker`.
- **Due installazioni SRM sulla stessa VM:** clona in cartelle diverse e usa `COMPOSE_PROJECT_NAME=srm2 docker compose …` con un `WEB_PORT` diverso.
