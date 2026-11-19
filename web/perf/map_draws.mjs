// How many times the maps of a page draw during its load, and the time of each large JSON answer
// (the download of the body and the parse). A draw of a map starts with clearRect on a large canvas.
//
//   node perf/map_draws.mjs <page address> <path> [cpu slowdown]
//   node perf/map_draws.mjs http://PC_ADDRESS:8771 / 4
//
// Never give /recommendations for the live server: each list without a seed goes into the log of
// the user. Run it from PowerShell: Git Bash changes the path "/" into a Windows path.
import { chromium } from '../node_modules/playwright/index.mjs';

const [base, path, slowArg] = process.argv.slice(2);
const slow = Number(slowArg ?? 1);
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
await page.goto(`${base}/settings`, { waitUntil: 'networkidle' });
const cdp = await page.context().newCDPSession(page);
if (slow > 1) await cdp.send('Emulation.setCPUThrottlingRate', { rate: slow });
await page.addInitScript(() => {
	window.__draws = [];
	const clear = CanvasRenderingContext2D.prototype.clearRect;
	CanvasRenderingContext2D.prototype.clearRect = function (...args) {
		if (this.canvas.width * this.canvas.height > 100000) window.__draws.push(Math.round(performance.now()));
		return clear.apply(this, args);
	};
	window.__json = [];
	const json = Response.prototype.json;
	Response.prototype.json = async function () {
		const t = performance.now();
		const out = await json.call(this);
		if (this.url.includes('/api/')) window.__json.push([this.url.split('/api/')[1], Math.round(performance.now() - t)]);
		return out;
	};
});
await page.goto(base + path, { waitUntil: 'networkidle', timeout: 120_000 });
await page.waitForTimeout(2000);
const r = await page.evaluate(() => ({ draws: window.__draws, json: window.__json }));
console.log(`${path} at ${slow}x: ${r.draws.length} large canvas draws, at ${r.draws.join(', ')} ms`);
console.log('json answers (address, ms):', JSON.stringify(r.json));
await browser.close();
