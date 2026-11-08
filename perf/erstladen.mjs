const { puppeteer } = await import(process.env.PUPPETEER || '/home/wsl/.npm/_npx/15c61037b1978c83/node_modules/chrome-devtools-mcp/build/src/third_party/index.js');
import fs from 'node:fs';
const [quelle, ordner] = process.argv.slice(2);
const html = fs.readFileSync(quelle, 'utf8');
const m = html.match(/<script>([\s\S]*)<\/script><\/body>/);
const varianten = {
  aktuell: html,
  ohneSkript: html.replace(m[0], '</body>'),
  skriptNachFrame: html.replace(m[0], '<script>requestAnimationFrame(()=>setTimeout(()=>{' + m[1] + '\n},0))</script></body>'),
};
const exe = process.env.CHROME || '/home/wsl/.cache/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-linux64/chrome-headless-shell';
for (const [name, text] of Object.entries(varianten)) {
  fs.writeFileSync(`${ordner}/${name}.html`, text);
  const z = [];
  for (let i = 0; i < 2; i++) {
    const browser = await puppeteer.launch({ executablePath: exe, headless: true, args: ['--no-sandbox'] });
    const page = await browser.newPage(); await page.setViewport({ width: 1600, height: 1000 });
    await page.goto(`file://${ordner}/${name}.html`, { waitUntil: 'load', timeout: 120000 });
    await new Promise(r => setTimeout(r, 300));
    z.push(await page.evaluate(() => { const n = performance.getEntriesByType('navigation')[0]; const p = performance.getEntriesByType('paint')[0];
      return `DCL ${Math.round(n.domContentLoadedEventEnd)} / paint ${p ? Math.round(p.startTime) : '-'}`; }));
    await browser.close();
  }
  console.log(name.padEnd(16), z.join('   '));
}
