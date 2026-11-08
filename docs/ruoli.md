# Utenti e ruoli

| | **Admin / Direzione Sales** | **Backoffice** | **Sales** |
|---|:---:|:---:|:---:|
| Vede le richieste | tutte | tutte | **solo le sue** |
| Crea / modifica bozze, invia, sollecita | ✅ | ✅ (tutte) | ✅ (solo sue, sempre a nome proprio) |
| Chiude le richieste | ✅ | ✅ | ❌ |
| Riapre richieste chiuse | ✅ | ❌ | ❌ |
| Dashboard | globale | globale | solo le sue |
| Coda bozze AI (email in ingresso) | ✅ | ✅ | ❌ |
| Configurazione (mittente, CC, reminder, LLM) | ✅ scrive | 👁 sola lettura | ❌ |
| Anagrafiche vendor/supplier/agenti/mapping | ✅ scrive | 👁 lettura | vendor/supplier sì; agenti: solo sé stesso; **indirizzi dei vendor nascosti** |
| Gestione utenti e ruoli | ✅ | ❌ | ❌ |

## "Le sue" richieste (Sales)
Una richiesta è del Sales se è intestata al **suo agente commerciale** oppure l'ha **creata lui**.
Le bozze create dall'AI dalle sue email sono quindi sue (l'agente si riconosce dall'indirizzo del mittente).
Una richiesta altrui risponde **404** (non 403): non si rivela nemmeno che esiste.

## Collegamento utente → agente
- Al primo login un Sales viene collegato in automatico all'agente con **la stessa email**.
- Se l'email differisce, l'Admin sceglie l'agente in *Amministrazione → Utenti*.
- Un Sales senza agente collegato non vede nulla e non può creare richieste (la UI lo segnala).

## Assegnazione dei ruoli
- Nuovi utenti: ruolo `DEFAULT_ROLE` (default **SALES**, privilegio minimo).
- Email in `ADMIN_EMAILS`: **Admin** al primo login (serve per il bootstrap).
- Poi l'Admin cambia ruoli e attiva/disattiva utenti da *Amministrazione → Utenti* (non può modificare sé stesso).

## Migrazione
`alembic upgrade head` rinomina `OPERATOR` → `BACKOFFICE` (gli utenti esistenti mantengono i loro permessi),
aggiunge `SALES` e il collegamento `app_users.sales_agent_id`. Idempotente sulle installazioni nuove.
