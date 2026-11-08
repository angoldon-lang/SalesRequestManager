// E2E (Playwright): visibilità per ruolo. Richiede backend AUTH_DISABLED=true + 'npm run dev' + un agente con email sales-demo@demo.it.
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const ok = (c, m) => { console.log((c ? 'OK   ' : 'FAIL ') + m); if (!c) process.exitCode = 1; };
  async function as(user) {
    const ctx = await b.newContext({ viewport: { width: 1300, height: 800 } });
    await ctx.addInitScript((u) => localStorage.setItem('srm_dev_user', u), user);
    const p = await ctx.newPage(); return p;
  }
  const nav = async (p) => (await p.locator('aside nav a').allInnerTexts()).join(' | ');
  // SALES
  let p = await as('sales-demo@demo.it');
  await p.goto('http://localhost:5173/'); await p.waitForSelector('text=Sales');
  let n = await nav(p); console.log('sales nav:', n);
  ok(!n.includes('Amministrazione') && !n.includes('Bozze da email') && n.includes('Le mie richieste'), 'SALES: niente Admin né coda AI');
  await p.goto('http://localhost:5173/admin'); await p.waitForTimeout(800);
  ok(!p.url().includes('/admin'), 'SALES: /admin reindirizza');
  await p.goto('http://localhost:5173/requests/new'); await p.waitForSelector('main select');
  await p.waitForTimeout(500);
  const agentSel = p.locator('main select').nth(1);
  ok(await agentSel.isDisabled() && (await agentSel.locator('option:checked').innerText()) === 'Sara Sales', 'SALES: agente bloccato su se stessa');
  await p.screenshot({ path: 'sales-form.png' });
  ok(await p.locator('text=Il tuo utente non è ancora collegato').count() === 0, 'SALES: utente collegato automaticamente');
  // BACKOFFICE
  p = await as('back-demo@local');
  await p.goto('http://localhost:5173/'); await p.waitForSelector('text=Backoffice');
  n = await nav(p); console.log('backoffice nav:', n);
  ok(!n.includes('Amministrazione') && n.includes('Bozze da email'), 'BACKOFFICE: coda AI sì, Admin no');
  // ADMIN: utenti
  p = await as('admin@az.it');
  await p.goto('http://localhost:5173/admin'); await p.click('text=Utenti'); await p.waitForSelector('text=Agente collegato');
  ok(await p.locator('option:has-text("Backoffice")').count() > 0, 'ADMIN: gestione ruoli visibile');
  await p.screenshot({ path: 'admin-users.png' });
  await b.close();
})();
