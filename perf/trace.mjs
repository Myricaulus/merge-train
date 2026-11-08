const { puppeteer } = await import(process.env.PUPPETEER || '/home/wsl/.npm/_npx/15c61037b1978c83/node_modules/chrome-devtools-mcp/build/src/third_party/index.js');
import fs from 'node:fs';
const exe = process.env.CHROME || '/home/wsl/.cache/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-linux64/chrome-headless-shell';
const browser = await puppeteer.launch({ executablePath: exe, headless: true, args: ['--no-sandbox'] });
const page = await browser.newPage(); await page.setViewport({ width: 1600, height: 1000 });
await page.tracing.start({ path: process.argv[3] });
await page.goto(process.argv[2], { waitUntil: 'load', timeout: 120000 });
await page.tracing.stop(); await browser.close();
const ev = JSON.parse(fs.readFileSync(process.argv[3])).traceEvents.filter(e => e.ph === 'X' && e.dur > 20000);
const sum = {}; for (const e of ev) { sum[e.name] = (sum[e.name] || 0) + e.dur; }
console.log(Object.entries(sum).sort((a, b) => b[1] - a[1]).slice(0, 14).map(([n, d]) => `${(d / 1000).toFixed(0).padStart(6)} ms  ${n}`).join('\n'));
