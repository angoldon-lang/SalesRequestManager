# SalesRequestManager – SRM

Gestione delle richieste commerciali verso vendor/supplier, integrata con Microsoft 365.

- **Backend:** FastAPI + SQLAlchemy 2 + PostgreSQL 16 (`backend/`)
- **Frontend:** React + Vite + TypeScript (`frontend/`)
- **Worker:** APScheduler — inbound AI (2 min), tracking risposte (10 min), reminder (feriali 09:00 e 15:00)
- **M365:** Microsoft Graph (invio, lettura mailbox, reply-all) — vedi [docs/m365-setup.md](docs/m365-setup.md)
- **AI:** Anthropic Claude con tool use forzato; prompt in `backend/app/services/llm_parser.py`

## Accesso e ruoli
Login con utente e password. Al primo avvio esiste l'utente **`admin`** con password **`ChangeMe!2026`**: il cambio è obbligatorio al primo accesso.
- **Admin / Direzione Sales:** vede tutto, configura, gestisce utenti e ruoli.
- **Backoffice:** vede e gestisce tutto, non configura.
- **Sales (agente commerciale):** vede solo le proprie richieste. L'agente è un utente con ruolo Sales.

Dettagli: [docs/ruoli.md](docs/ruoli.md).

## Funzioni
| Sprint | Contenuto |
|---|---|
| 1 | Schema DB, anagrafiche vendor/supplier/agenti + mapping, configurazione globale, auth Entra ID, **ruoli a 3 livelli** (vedi [docs/ruoli.md](docs/ruoli.md)) |
| 2 | Form richiesta con ramo **DR** dinamico (Cliente finale, Valore stimato, Chiusura prevista obbligatori), invio via Graph, audit |
| 3 | Worker inbound + LLM → bozze, coda di revisione |
| 4 | Reply tracker, reminder automatici (giorni lavorativi IT, max solleciti, escalation), dashboard |
| 5 | Docker Compose, CI, test, hardening |

Regole DR: validazione su 3 livelli (zod nel form → Pydantic/API → `CHECK` nel DB). La **bozza** può essere incompleta, l'**invio** no.

## Installazione (Docker, tutto in container)
```bash
./install.sh                                  # prova: DB + API + worker + web, porta libera da 8088
./install.sh --https --host srm.azienda.it    # rete interna con HTTPS (richiesto dal login Microsoft)
```
Il database vive in un container: nessuna porta del DB/API è esposta sull'host, quindi nessun conflitto con altri
PostgreSQL della VM. Guida completa (porta, reverse proxy, Entra, backup): [docs/docker.md](docs/docker.md).
Le migrazioni partono all'avvio dell'API. **Esegui un solo worker.**

## Sviluppo locale (senza Azure)
```bash
# Backend (PostgreSQL in esecuzione; imposta DATABASE_URL)
cd backend && pip install -r requirements.txt
alembic upgrade head
GRAPH_MODE=dry-run uvicorn app.main:app --reload                         # API su :8000, docs su /docs; admin/ChangeMe!2026

# Frontend
cd frontend && npm install && npm run dev                                # UI su :5173
scripts/seed_demo.sh http://localhost:5173 admin '<password>'            # dati demo
```
`GRAPH_MODE=dry-run` evita gli invii reali (le mail vengono solo loggate). Per i test automatici esiste `AUTH_DISABLED=true` (nessun login, ruolo dal prefisso dell'header `X-Dev-User`: `back*`, `sales*`, altrimenti Admin). **Mai in produzione.**

## Test
```bash
cd backend && TEST_DATABASE_URL=postgresql+psycopg://postgres@localhost/srm_test pytest -q   # DB *_test
cd frontend && npm run build                                                                  # type-check + build
```
I test backend usano un Graph e un LLM finti: coprono login e cambio password obbligatorio, blocco account, regole DR, destinatari/CC, macchina a stati, reminder (weekend, max, fallimenti, risposta vendor), inbound (idempotenza, review, errori), dashboard e i 3 ruoli (visibilità, permessi, collegamento agente).
E2E (Playwright) in `frontend/e2e/`: `auth` (login), `dr-form` (form DR), `roles` (visibilità per ruolo).

## API
Documentazione interattiva: `GET /docs`. Prefisso `/api/v1`: `requests`, `vendors`, `suppliers`, `agents`, `vendor-supplier-map`, `config`, `inbound`, `dashboard`, `users`, `me`.

## Hardening incluso
- Validazione JWT Entra (RS256, issuer, audience); primo login con `INSERT … ON CONFLICT`.
- Graph: retry su 429/503 con `Retry-After`; ImmutableId; accesso ristretto con ApplicationAccessPolicy.
- Worker idempotenti: `graph_message_id UNIQUE`, `FOR UPDATE SKIP LOCKED`, un reminder fallito non cambia stato.
- Output LLM trattato come non fidato (normalizzazione, fuzzy match su anagrafiche, `needs_review`).
- Audit completo in `request_events`; vincoli di integrità nel DB.

## Backup
`scripts/backup.sh` (gzip, ultimi 14 giorni) e `scripts/restore.sh` — vedi docs/docker.md.
