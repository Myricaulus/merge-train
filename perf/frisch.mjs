const { puppeteer } = await import(process.env.PUPPETEER || '/home/wsl/.npm/_npx/15c61037b1978c83/node_modules/chrome-devtools-mcp/build/src/third_party/index.js');
const exe = process.env.CHROME || '/home/wsl/.cache/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-linux64/chrome-headless-shell';
for (const name of process.argv.slice(3)) { const z = [];
  for (let i = 0; i < 2; i++) {
    const browser = await puppeteer.launch({ executablePath: exe, headless: true, args: ['--no-sandbox'] });
    const page = await browser.newPage(); await page.setViewport({ width: 1600, height: 1000 });
    await page.goto(`file://${process.argv[2]}/${name}.html`, { waitUntil: 'load' }); await new Promise(r => setTimeout(r, 500));
    z.push(await page.evaluate(() => { const n = performance.getEntriesByType('navigation')[0], p = performance.getEntriesByType('paint')[0];
      return `DCL ${Math.round(n.domContentLoadedEventEnd)} paint ${p ? Math.round(p.startTime) : '-'}`; }));
    const t = Date.now(); await page.evaluate(() => { window.scrollTo(0, document.body.scrollHeight * 0.6); return document.body.offsetHeight; });
    z[z.length - 1] += ` scroll60% ${Date.now() - t}ms`;
    await browser.close(); }
  console.log(name.padEnd(12), z.join('  |  ')); }
