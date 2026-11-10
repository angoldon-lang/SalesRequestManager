// E2E (Playwright): login locale, cambio password obbligatorio, creazione utente Sales. Richiede backend in modalità locale (AUTH_MODE=local, DB vuoto: admin/ChangeMe!2026) + 'npm run dev'.
const { chromium } = require('playwright');
const B = 'http://localhost:5173';
const ok = (c, m) => { console.log((c ? 'OK   ' : 'FAIL ') + m); if (!c) process.exitCode = 1; };
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1300, height: 850 } });
  const p = await ctx.newPage(); const errs = []; p.on('pageerror', e => errs.push(e.message));
  // --- login
  await p.goto(B + '/'); await p.waitForSelector('text=accedi per continuare');
  ok(true, 'senza sessione compare la pagina di login');
  await p.screenshot({ path: 'login.png' });
  await p.fill('input[autocomplete=username]', 'admin'); await p.fill('input[type=password]', 'sbagliata');
  await p.click('button:has-text("Accedi")'); await p.waitForSelector('text=Utente o password non corretti');
  ok(true, 'password errata: messaggio di errore');
  await p.fill('input[type=password]', 'ChangeMe!2026'); await p.click('button:has-text("Accedi")');
  await p.waitForSelector('text=Imposta la tua password');
  ok(true, 'admin predefinito: cambio password obbligatorio');
  await p.goto(B + '/users'); await p.waitForSelector('text=Imposta la tua password');
  ok(true, 'impossibile saltare il cambio password navigando altrove');
  const pw = p.locator('input[type=password]');
  await pw.nth(0).fill('ChangeMe!2026'); await pw.nth(1).fill('breve'); await pw.nth(2).fill('breve');
  ok(await p.locator('text=Almeno 10 caratteri').count() > 0 && await p.locator('button:has-text("Salva password")').isDisabled(), 'password corta: bottone bloccato');
  await pw.nth(1).fill('ChangeMe!2026'); await pw.nth(2).fill('ChangeMe!2026'); await p.click('button:has-text("Salva password")');
  await p.waitForSelector('text=diversa da quella');
  ok(true, 'la password predefinita non è accettata come nuova');
  await pw.nth(1).fill('Admin-Nuova-2026'); await pw.nth(2).fill('Admin-Nuova-2026'); await p.click('button:has-text("Salva password")');
  await p.waitForSelector('text=Utenti e ruoli');
  ok(true, 'password cambiata: accesso alla dashboard con menu admin');
  // --- pagina utenti
  await p.click('text=Utenti e ruoli'); await p.waitForSelector('text=Non c\'è nessun agente commerciale');
  ok(true, 'pagina Utenti: avviso "nessun agente commerciale"');
  await p.click('text=+ Nuovo utente');
  await p.fill('.modal >> label:has-text("Nome utente") input', 'anna.verdi');
  await p.fill('.modal >> label:has-text("Nome e cognome") input', 'Anna Verdi');
  await p.fill('.modal >> label:has-text("Email") input', 'anna.verdi@azienda.it');
  await p.click('.modal >> button:has-text("Genera")');
  await p.waitForFunction(() => document.querySelector('.modal input[autocomplete=off][spellcheck=false]')?.value.length >= 10);
  const tmp = await p.inputValue('.modal input[autocomplete=off][spellcheck=false]');
  await p.click('.modal >> button:has-text("Salva")'); await p.waitForSelector('text=Credenziali per Anna Verdi');
  ok(tmp.length >= 10, 'utente Sales creato con password generata: ' + tmp.replace(/./g, '*'));
  await p.click('text=Ho annotato le credenziali');
  await p.screenshot({ path: 'users.png' });
  // --- crea anagrafica di base via API (token admin) per provare il form
  const tok = await p.evaluate(() => localStorage.getItem('srm_token'));
  const H = { 'Content-Type': 'application/json', Authorization: 'Bearer ' + tok };
  const j = (m, u, d) => fetch(B + '/api/v1' + u, { method: m, headers: H, body: JSON.stringify(d) }).then(r => r.json());
  await j('POST', '/vendors', { name: 'Cisco' }); await j('POST', '/suppliers', { name: 'Arrow' });
  await j('PUT', '/vendor-supplier-map', { vendor_id: 1, supplier_id: 1, to_emails: ['deals@arrow.example'], is_preferred: true });
  // --- il form richiesta: l'agente è nel menu
  await p.goto(B + '/requests/new'); await p.waitForSelector('select[aria-label="Tipo richiesta"]');
  await p.waitForTimeout(500);
  const opts = await p.locator('main select').nth(1).locator('option').allInnerTexts();
  ok(opts.includes('Anna Verdi'), 'form richiesta: "Agente commerciale" elenca Anna Verdi -> ' + opts.join(','));
  await p.screenshot({ path: 'form-agent.png' });
  // --- logout e accesso come Anna
  await p.click('button:has-text("Esci")'); await p.waitForSelector('text=accedi per continuare');
  ok(true, 'logout riporta alla pagina di login');
  await p.fill('input[autocomplete=username]', 'anna.verdi'); await p.fill('input[type=password]', tmp); await p.click('button:has-text("Accedi")');
  await p.waitForSelector('text=Imposta la tua password');
  ok(true, 'nuovo utente: cambio password obbligatorio al primo accesso');
  await pw.nth(0).fill(tmp); await pw.nth(1).fill('Anna-Mia-Pass-1'); await pw.nth(2).fill('Anna-Mia-Pass-1'); await p.click('button:has-text("Salva password")');
  await p.waitForSelector('text=Le mie richieste');
  const nav = (await p.locator('aside nav a').allInnerTexts()).join('|');
  ok(!nav.includes('Utenti') && !nav.includes('Configurazione') && !nav.includes('Bozze da email'), 'Sales: menu ridotto -> ' + nav);
  await p.goto(B + '/users'); await p.waitForTimeout(600);
  ok(!p.url().includes('/users'), 'Sales: /users reindirizza');
  await p.goto(B + '/requests/new'); await p.waitForSelector('select[aria-label="Tipo richiesta"]'); await p.waitForTimeout(500);
  const sel = p.locator('main select').nth(1);
  ok(await sel.isDisabled() && (await sel.locator('option:checked').innerText()) === 'Anna Verdi', 'Sales: agente bloccato su sé stessa');
  // --- sessione invalidata se l'admin reimposta la password: via API
  const r = await fetch(B + '/api/v1/users', { headers: { Authorization: 'Bearer ' + await p.evaluate(() => localStorage.getItem('srm_token')) } });
  ok(r.status === 403, 'Sales: API /users negata (403)');
  ok(errs.length === 0, 'nessun errore JS ' + errs.join('|'));
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
