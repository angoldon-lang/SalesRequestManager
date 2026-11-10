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

Opzioni: `--port 9090` (porta precisa, errore se occupata), `--admin-password '...'` (password iniziale dell'admin), `--no-start`.

### Scegliere la porta a mano
In `.env`: `WEB_PORT=9090`, poi `docker compose up -d`. Per vedere cosa è già occupato: `ss -ltnp | grep LISTEN`.
`WEB_BIND=<ip-interno>` limita l'ascolto a quell'indirizzo; `127.0.0.1` lo rende raggiungibile solo dalla VM (se c'è già un reverse proxy che pubblica verso `127.0.0.1:<WEB_PORT>`).

### Primo accesso
Alla fine dell'installazione lo script stampa le credenziali iniziali: utente **`admin`**, password **`ChangeMe!2026`**
(o quella scelta con `--admin-password`). Al primo login il cambio password è **obbligatorio**. Poi crea utenti e agenti
da **Utenti e ruoli** (vedi [ruoli.md](ruoli.md)). Finché non l'hai cambiata, chi raggiunge la pagina di login conosce la password
iniziale: fai il primo accesso subito dopo l'installazione.

### Solo rete interna — consigliato
L'app non deve essere raggiungibile da internet: basta che gli **utenti la aprano dalla rete aziendale**.
Con il login a password funziona anche in HTTP, ma le **password viaggerebbero in chiaro**: in rete interna usa HTTPS
(l'installer lo prepara). Con `AUTH_MODE=entra` (login Microsoft) l'HTTPS è obbligatorio fuori da `localhost`.

```bash
./install.sh --https --host srm.azienda.it --bind 10.0.0.5
```
- `--host`: nome DNS **interno** con cui gli utenti apriranno SRM. Meglio un nome che un IP, e meglio evitare `.local` (mDNS).
- `--bind`: IP interno della VM. L'app ascolta solo lì: se la VM ha anche un IP pubblico, non è raggiungibile da fuori.
- Porta HTTPS: parte da **8443** e, se occupata, prende la prima libera. Con `--port 9443` la scegli tu.
- Certificato: l'installer crea una **CA interna** (`certs/ca.crt`) e un certificato per `--host` (valido 825 giorni, ricreabile).
  Se avete già una CA aziendale: `--cert fullchain.pem --key chiave.pem`, e non serve distribuire nulla.

**Da fare una volta sola, fuori dalla VM**
1. **DNS interno:** record `srm.azienda.it` → IP della VM.
2. **Firewall della VM:** apri la porta scelta solo verso la rete interna (es. `ufw allow from 10.0.0.0/8 to any port 8443 proto tcp`).
3. **Entra ID:** nell'app SRM, *Authentication → Single-page application → Redirect URI* = `https://srm.azienda.it:8443`
   (l'installer lo stampa alla fine). Un URI https con IP o `.local` può non essere accettato: usa il nome DNS.
4. **Certificato sui PC** (solo con la CA generata): distribuisci `certs/ca.crt` come *Autorità di certificazione radice attendibile*
   (Windows: GPO → Configurazione computer → Criteri di Windows → Impostazioni di protezione → Criteri di chiave pubblica →
   Autorità di certificazione radice attendibili). Senza, i browser mostrano l'avviso e non è la configurazione da tenere.

**Traffico in uscita dalla VM** (non serve nulla in entrata da internet): `login.microsoftonline.com` (validazione token),
`graph.microsoft.com` (mail), `api.anthropic.com` (AI). Al primo `docker compose build` servono anche Docker Hub, `pypi.org` e `registry.npmjs.org`.
Se la VM esce da un proxy aziendale, imposta `HTTP_PROXY`/`HTTPS_PROXY` per Docker.

**Rinnovo certificato:** metti i nuovi `tls.crt`/`tls.key` in `certs/` e `docker compose restart web`.

### Dati di esempio (facoltativo)
```bash
scripts/seed_demo.sh http://127.0.0.1:8088 admin '<la-tua-password-admin>'   # vendor, supplier, mapping e un agente di prova
```

### Mail con Microsoft 365 (Graph)
L'invio e la lettura delle mail usano Microsoft Graph, indipendentemente da come si fa il login. Segui [m365-setup.md](m365-setup.md)
e compila in `.env`: `AZ_TENANT_ID`, `AZ_CLIENT_ID`, `AZ_CLIENT_SECRET`, `GRAPH_MODE=graph`, `ANTHROPIC_API_KEY`; poi `docker compose up -d`.
Per il **login Microsoft** invece di utente/password: `AUTH_MODE=entra` e `docker compose up -d --build`
(`AZ_CLIENT_ID` entra nel frontend in fase di build; redirect URI SPA = URL con cui gli utenti aprono l'app, porta inclusa).

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
