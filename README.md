# SalesRequestManager – SRM

Gestione delle richieste commerciali verso vendor/supplier, integrata con Microsoft 365.

- **Backend:** FastAPI + SQLAlchemy 2 + PostgreSQL 16 (`backend/`)
- **Frontend:** React + Vite + TypeScript (`frontend/`)
- **Worker:** APScheduler — inbound AI (2 min), tracking risposte (10 min), reminder (feriali 09:00 e 15:00)
- **M365:** Microsoft Graph (invio, lettura mailbox, reply-all) — vedi [docs/m365-setup.md](docs/m365-setup.md)
- **AI:** Anthropic Claude con tool use forzato; prompt in `backend/app/services/llm_parser.py`

## Ruoli
- **Admin / Direzione Sales:** vede tutto e configura.
- **Backoffice:** vede e gestisce tutto, non configura.
- **Sales:** vede solo le proprie richieste.

Dettaglio permessi e collegamento utente→agente: [docs/ruoli.md](docs/ruoli.md).

## Funzioni
| Sprint | Contenuto |
|---|---|
| 1 | Schema DB, anagrafiche vendor/supplier/agenti + mapping, configurazione globale, auth Entra ID, **ruoli a 3 livelli** (vedi [docs/ruoli.md](docs/ruoli.md)) |
| 2 | Form richiesta con ramo **DR** dinamico (Cliente finale, Valore stimato, Chiusura prevista obbligatori), invio via Graph, audit |
| 3 | Worker inbound + LLM → bozze, coda di revisione |
| 4 | Reply tracker, reminder automatici (giorni lavorativi IT, max solleciti, escalation), dashboard |
| 5 | Docker Compose, CI, test, hardening |

Regole DR: validazione su 3 livelli (zod nel form → Pydantic/API → `CHECK` nel DB). La **bozza** può essere incompleta, l'**invio** no.

## Avvio in produzione (Docker)
```bash
cp .env.example .env     # compila i valori
docker compose up -d --build
# UI su http://localhost:8080 (metti un reverse proxy TLS davanti)
```
Le migrazioni (`alembic upgrade head`) partono all'avvio dell'API. **Esegui un solo worker.**

## Sviluppo locale (senza Azure)
```bash
# Backend (PostgreSQL in esecuzione; imposta DATABASE_URL)
cd backend && pip install -r requirements.txt
alembic upgrade head
AUTH_DISABLED=true GRAPH_MODE=dry-run uvicorn app.main:app --reload     # API su :8000, docs su /docs

# Frontend
cd frontend && npm install && npm run dev                                # UI su :5173
scripts/seed_demo.sh                                                     # dati demo
```
In sviluppo il ruolo dipende dal prefisso dell'utente (`X-Dev-User`): `back*` = Backoffice, `sales*` = Sales, altrimenti Admin; il selettore in basso a sinistra nella UI li alterna. Un Sales viene collegato all'agente con la stessa email.

`AUTH_DISABLED` e `GRAPH_MODE=dry-run` evitano login e invii reali (le mail vengono solo loggate). **Mai in produzione.**

## Test
```bash
cd backend && TEST_DATABASE_URL=postgresql+psycopg://postgres@localhost/srm_test pytest -q   # DB *_test
cd frontend && npm run build                                                                  # type-check + build
```
I test backend usano un Graph e un LLM finti: coprono regole DR, destinatari/CC, macchina a stati, reminder (weekend, max, fallimenti, risposta vendor), inbound (idempotenza, review, errori), dashboard e i 3 ruoli (visibilità, permessi, collegamento agente).
E2E del form DR: `frontend/e2e/dr-form.e2e.cjs` (Playwright).

## API
Documentazione interattiva: `GET /docs`. Prefisso `/api/v1`: `requests`, `vendors`, `suppliers`, `agents`, `vendor-supplier-map`, `config`, `inbound`, `dashboard`, `users`, `me`.

## Hardening incluso
- Validazione JWT Entra (RS256, issuer, audience); primo login con `INSERT … ON CONFLICT`.
- Graph: retry su 429/503 con `Retry-After`; ImmutableId; accesso ristretto con ApplicationAccessPolicy.
- Worker idempotenti: `graph_message_id UNIQUE`, `FOR UPDATE SKIP LOCKED`, un reminder fallito non cambia stato.
- Output LLM trattato come non fidato (normalizzazione, fuzzy match su anagrafiche, `needs_review`).
- Audit completo in `request_events`; vincoli di integrità nel DB.

## Backup consigliato
`pg_dump` giornaliero del DB (`docker compose exec db pg_dump -U srm srm > srm.sql`).
