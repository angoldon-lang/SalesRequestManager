# Utenti, ruoli e accesso

## Accesso (login con password)
- Ogni persona ha un **utente** (nome utente + password) creato da un Admin in **Utenti e ruoli**.
- **Primo avvio:** viene creato l'utente **`admin`** con password **`ChangeMe!2026`** (modificabile prima del primo avvio con
  `./install.sh --admin-password '...'` o `DEFAULT_ADMIN_PASSWORD` in `.env`). Al primo accesso il **cambio password è obbligatorio**:
  finché non lo fai, nient'altro è utilizzabile.
- Le password create o reimpostate da un Admin sono **provvisorie**: l'utente deve cambiarle al primo accesso.
- Password: minimo 10 caratteri, diversa dal nome utente e da quella predefinita. Sono salvate come hash (scrypt), mai in chiaro.
- **Blocco account:** 5 tentativi falliti → bloccato 15 minuti. L'Admin lo sblocca reimpostando la password.
- **Sessione:** 8 ore (`TOKEN_TTL_MINUTES`). Cambiando password o disattivando l'utente le sue sessioni aperte si chiudono subito.
- Le password viaggiano in chiaro su HTTP: in rete interna usa **HTTPS** (`./install.sh --https --host ...`, vedi docker.md).
- Se hai perso l'unico admin: `docker compose exec db psql -U srm srm -c "UPDATE app_users SET password_hash=NULL WHERE role='ADMIN'"`
  poi `docker compose restart api` ricrea `admin` con la password predefinita (da cambiare al primo accesso).
- Microsoft Entra come alternativa: `AUTH_MODE=entra` (vedi m365-setup.md). Le mail via Graph funzionano in entrambi i casi.

## Ruoli

| | **Admin / Direzione Sales** | **Backoffice** | **Sales** (agente commerciale) |
|---|:---:|:---:|:---:|
| Vede le richieste | tutte | tutte | **solo le sue** |
| Crea / modifica bozze, invia, sollecita | ✅ | ✅ (tutte) | ✅ (solo sue, sempre a nome proprio) |
| Chiude e riapre le richieste | ✅ (tutte) | ✅ (tutte) | ✅ (solo sue) |
| Dashboard | globale | globale | solo le sue |
| Coda bozze AI (email in ingresso) | ✅ | ✅ | ❌ |
| Configurazione (mittente, CC, reminder, LLM, vendor, supplier, mapping) | ✅ scrive | 👁 sola lettura | ❌ (vede vendor/supplier, non gli indirizzi) |
| Utenti e ruoli | ✅ | ❌ | ❌ |

## L'agente commerciale è un utente
Non esiste più un elenco separato di agenti: **l'agente commerciale è un utente con ruolo Sales**.
- Il menu "Agente commerciale (in CC)" delle richieste elenca gli utenti **Sales attivi**; la loro email viene messa in CC.
- Per aggiungere un agente: **Utenti e ruoli → + Nuovo utente → ruolo Sales** (l'email è obbligatoria).
- Un Sales crea richieste sempre a proprio nome; un Backoffice/Admin sceglie l'agente.
- Le email in ingresso (AI) vengono attribuite all'utente Sales con quell'indirizzo email.
- "Le sue" richieste = quelle intestate a lui o create da lui. Quelle altrui rispondono **404** (non si rivela che esistono).

## Regole di sicurezza sugli utenti
- Un Admin non può cambiare il proprio ruolo né disattivarsi, e deve restare **almeno un Admin attivo**.
- Gli utenti non si cancellano (le richieste li referenziano): si **disattivano**.

## Migrazione dalle versioni precedenti
`alembic upgrade head` (automatico all'avvio): gli agenti esistenti diventano utenti **Sales senza password** — l'Admin imposta la
password da *Utenti e ruoli → Password* — e le richieste restano collegate. Gli utenti `OPERATOR` diventano `BACKOFFICE`.
