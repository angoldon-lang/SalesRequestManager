# Setup Microsoft 365 / Entra ID

SRM usa **due** registrazioni logiche nella stessa app Entra: login utenti (delegato, SPA) e Graph (applicativo, backend).

## 1. App registration
1. Entra ID → App registrations → *New registration* → `SRM`. Single tenant.
2. **Expose an API**: imposta Application ID URI `api://<CLIENT_ID>` e aggiungi lo scope `access_as_user`.
   Nel **Manifest** imposta `"accessTokenAcceptedVersion": 2` (il backend valida token v2 con `aud` = `AZ_CLIENT_ID`;
   se preferisci `aud = api://<CLIENT_ID>` imposta `API_AUDIENCE` di conseguenza).
3. **Authentication → Single-page application**: redirect URI `https://<tuo-host>` (e `http://localhost:5173` in sviluppo).
4. **Certificates & secrets**: crea un client secret (o certificato) → `AZ_CLIENT_SECRET`.
5. **API permissions → Microsoft Graph → Application**: `Mail.Send` e `Mail.ReadWrite`. Poi *Grant admin consent*.
6. Annota `AZ_TENANT_ID` e `AZ_CLIENT_ID` nel file `.env`.

## 2. Limitare l'accesso alle sole 2 mailbox (obbligatorio)
Senza questo passaggio i permessi applicativi valgono per **tutte** le caselle del tenant.
```powershell
New-DistributionGroup -Name "SRM-Mailboxes" -Type Security `
  -Members richieste@azienda.it,srm-inbound@azienda.it
New-ApplicationAccessPolicy -AppId <CLIENT_ID> `
  -PolicyScopeGroupId SRM-Mailboxes@azienda.it -AccessRight RestrictAccess -Description "SRM"
Test-ApplicationAccessPolicy -Identity richieste@azienda.it -AppId <CLIENT_ID>   # AccessCheckResult: Granted
```
(La policy può impiegare fino a 30 minuti per propagarsi.)

## 3. Mailbox
- `richieste@azienda.it` — **mittente** (shared mailbox va bene). Le risposte dei vendor arrivano qui.
- `srm-inbound@azienda.it` — **inbound AI**: gli agenti commerciali scrivono qui. Crea la cartella `SRM-Processed`.

## 4. Configurazione applicativa
1. `.env`: `GRAPH_MODE=graph`, `ANTHROPIC_API_KEY`, `ADMIN_EMAILS`.
2. `docker compose up -d --build`.
3. In **Amministrazione → Configurazione** imposta mittente, mailbox inbound, CC di default, giorni di reminder.
4. Usa **Invia mail di prova** per verificare permessi e policy.

## Come funziona
| Funzione | Meccanismo |
|---|---|
| Invio | crea bozza (`POST /users/{sender}/messages`) → `/send`; salva `id` e `conversationId` |
| Reminder | `createReplyAll` sul messaggio originale: stesso thread, stessi To/CC |
| Risposte vendor | ogni 10 min cerca nella mailbox mittente messaggi della stessa `conversationId` non inviati da noi |
| Inbound | ogni 2 min legge i non letti dell'Inbox, estrae i dati con l'LLM, crea una **bozza**, marca come letto e sposta in `SRM-Processed` |

Gli id messaggio usano `Prefer: IdType="ImmutableId"`, così non cambiano quando Exchange sposta la bozza in *Posta inviata*.

## Sicurezza e privacy
- Le email degli agenti vengono inviate all'API LLM: verifica DPA/contratto del provider. Gli allegati non vengono inviati.
- L'AI crea solo `DRAFT`: l'invio ai vendor è sempre un'azione umana.
- Segreti solo in `.env`/vault, mai nel repository.
