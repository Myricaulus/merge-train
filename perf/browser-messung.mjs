// Ladezeit und Funktionsprobe der merge-train-Seite im Headless-Chromium (nur lesend, legt keine Kommentare an).
const { puppeteer } = await import(process.env.PUPPETEER || '/home/wsl/.npm/_npx/15c61037b1978c83/node_modules/chrome-devtools-mcp/build/src/third_party/index.js');

const url = process.argv[2];
const exe = process.env.CHROME || '/home/wsl/.cache/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-linux64/chrome-headless-shell';
const browser = await puppeteer.launch({ executablePath: exe, headless: true, args: ['--no-sandbox'] });
const page = await browser.newPage();
await page.setViewport({ width: 1600, height: 1000 });
const fehler = [];
page.on('pageerror', e => fehler.push('pageerror: ' + e.message));
page.on('console', m => { if (m.type() === 'error') fehler.push('console: ' + m.text()); });

const t0 = Date.now();
await page.goto(url, { waitUntil: 'load', timeout: 120000 });
const tLoad = Date.now() - t0;
await page.waitForFunction(() => /Kommentar/.test(document.getElementById('rvstand')?.textContent || ''), { timeout: 60000 });
const tReview = Date.now() - t0;
const nav = await page.evaluate(() => { const n = performance.getEntriesByType('navigation')[0];
  return { antwort: Math.round(n.responseEnd), dom: Math.round(n.domContentLoadedEventEnd), load: Math.round(n.loadEventEnd) }; });
const zahlen = await page.evaluate(() => ({
  dateien: document.querySelectorAll('.datei').length, zeilen: document.querySelectorAll('table.sbs tr').length,
  luecken: document.querySelectorAll('table.sbs tr.lu').length, spaet: document.querySelectorAll('.spaet').length,
  hinweiseImDiff: document.querySelectorAll('tr.kr .kbox.hw').length, hinweiseOben: document.querySelectorAll('#allgemein .kbox.hw').length,
  heapMB: Math.round(performance.memory.usedJSHeapSize / 1e6) }));
console.log(`Ladezeit: Antwort ${nav.antwort} ms, DOM fertig ${nav.dom} ms, load ${nav.load} ms (gemessen ${tLoad} ms), Review-Hinweise gezeichnet nach ${tReview} ms`);
console.log('Seite:', JSON.stringify(zahlen));

// Kontext nachladen: erste Lücke ganz aufklappen
const vorher = await page.evaluate(() => document.querySelectorAll('tr.kx').length);
const t1 = Date.now();
await page.evaluate(() => { const b = [...document.querySelector('table.sbs tr.lu').querySelectorAll('button')].pop(); b.click(); });
await page.waitForFunction(v => document.querySelectorAll('tr.kx').length > v, { timeout: 10000 }, vorher);
console.log(`Kontext nachladen: +${await page.evaluate(v => document.querySelectorAll('tr.kx').length - v, vorher)} Zeilen in ${Date.now() - t1} ms`);

// Inline-Ansicht (Taste i)
const t2 = Date.now();
await page.keyboard.press('i');
const inl = await page.evaluate(() => ({ tabellen: document.querySelectorAll('table.inl').length, sichtbar: document.body.classList.contains('inline'),
  kxInline: document.querySelectorAll('table.inl tr.kx').length, luInline: document.querySelectorAll('table.inl tr.lu button').length }));
console.log(`Inline bauen: ${Date.now() - t2} ms`, JSON.stringify(inl));
await page.keyboard.press('i');

// Popup
await page.evaluate(() => popup(document.querySelector('.datei').dataset.pfad, 5, 'Test'));
await page.waitForFunction(() => document.querySelectorAll('#popup tbody tr').length > 0, { timeout: 10000 });
console.log('Popup:', await page.evaluate(() => ({ zeilen: document.querySelectorAll('#popup tbody tr').length,
  ziel: !!document.querySelector('#popup tr.ziel'), kopf: document.querySelector('#popup .pk b').textContent })));
await page.keyboard.press('Escape');
console.log('Popup nach Esc offen:', await page.evaluate(() => !!document.getElementById('popup')));

// Große Datei nachladen
if (await page.$('.spaet button.laden')) {
  const t3 = Date.now();
  await page.click('.spaet button.laden');
  await page.waitForFunction(() => !document.querySelector('.spaet [disabled]'), { timeout: 30000 });
  console.log(`Große Datei nachladen: ${Date.now() - t3} ms, noch ausgelassen: ${await page.evaluate(() => document.querySelectorAll('.spaet').length)}`);
}
// Sprung über die Dateiliste (weit unten) und schwebender Dateikopf mitten in einer großen Datei
const sprung = await page.evaluate(async () => {
  const i = Math.floor(ds.length * 0.8); ls[i].click(); await new Promise(r => setTimeout(r, 600));
  const kh = kopf.offsetHeight, top = ds[i].getBoundingClientRect().top;
  const gross = ds.reduce((a, d) => d.offsetHeight > a.offsetHeight ? d : a, ds[0]);
  gross.scrollIntoView({ block: 'start' }); window.scrollBy(0, gross.offsetHeight / 2); await new Promise(r => setTimeout(r, 300));
  const s = gross.querySelector('summary').getBoundingClientRect().top;
  return { datei: i, abstandOben: Math.round(top - kh), kopfhoehe: kh, summaryTopMitte: Math.round(s), markiert: ls.findIndex(a => a.classList.contains('akt')) };
});
console.log('Sprung/Sticky:', JSON.stringify(sprung));
console.log('JS-Fehler:', fehler.length ? fehler.join(' | ') : 'keine');
await browser.close();
