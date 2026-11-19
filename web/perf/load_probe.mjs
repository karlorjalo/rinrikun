// The load times of the page in a browser:
// 1. A cold load of each tab (an empty cache): the time to the first byte, to the first paint,
//    to the end of the load, the requests and the bytes, the fonts, and the main-thread work
//    (long tasks).
// 2. A second load with the cache.
// 3. The change of a tab with a click from Settings (3 runs): the time to the new page, and the
//    part of the data request.
//
//   node perf/load_probe.mjs <page address> [cpu slowdown] [tab,tab,...]
//   node perf/load_probe.mjs http://PC_ADDRESS:8771 4 Profile,Discover,Ratings,Review,Settings
//
// Never give the Recommendations tab for the live server: each list without a seed goes into the
// log of the user. Use the dev copy for it (see README.md). Run it from PowerShell.
import { chromium } from '../node_modules/playwright/index.mjs';

const base = process.argv[2];
const slow = Number(process.argv[3] ?? 1);
const tabs = (process.argv[4] ?? 'Profile,Discover,Ratings,Review,Similar,Settings').split(',');
const paths = { Profile: '/', Discover: '/discover', Ratings: '/ratings', Review: '/review', Similar: '/similar', Recommendations: '/recommendations', Settings: '/settings' };
const browser = await chromium.launch();

async function newPage(context) {
	const page = await context.newPage();
	if (slow > 1) {
		const cdp = await context.newCDPSession(page);
		await cdp.send('Emulation.setCPUThrottlingRate', { rate: slow });
	}
	await page.addInitScript(() => {
		window.__long = [];
		new PerformanceObserver((list) => {
			for (const e of list.getEntries()) window.__long.push([Math.round(e.startTime), Math.round(e.duration)]);
		}).observe({ type: 'longtask', buffered: true });
		window.__lcp = 0;
		new PerformanceObserver((list) => {
			for (const e of list.getEntries()) window.__lcp = Math.round(e.startTime);
		}).observe({ type: 'largest-contentful-paint', buffered: true });
	});
	return page;
}

async function loadOnce(page, path) {
	const requests = [];
	const onFinished = async (r) => {
		const sizes = await r.sizes().catch(() => null);
		requests.push({ url: r.url(), bytes: sizes ? sizes.responseBodySize + sizes.responseHeadersSize : 0 });
	};
	page.on('requestfinished', onFinished);
	await page.goto(base + path, { waitUntil: 'networkidle', timeout: 120_000 });
	await page.waitForTimeout(300);
	page.off('requestfinished', onFinished);
	const m = await page.evaluate(() => {
		const nav = performance.getEntriesByType('navigation')[0];
		const paint = performance.getEntriesByName('first-contentful-paint')[0];
		return {
			ttfb: Math.round(nav.responseStart),
			dcl: Math.round(nav.domContentLoadedEventEnd),
			load: Math.round(nav.loadEventEnd),
			fcp: paint ? Math.round(paint.startTime) : null,
			lcp: window.__lcp,
			long: window.__long
		};
	});
	const fonts = requests.filter((r) => /fonts\.(googleapis|gstatic)/.test(r.url));
	const api = requests.filter((r) => r.url.includes('/api/'));
	const kb = (list) => Math.round(list.reduce((s, r) => s + r.bytes, 0) / 1024);
	const longSum = m.long.reduce((s, [, d]) => s + d, 0);
	const longMax = m.long.reduce((s, [, d]) => Math.max(s, d), 0);
	return { ...m, n: requests.length, kb: kb(requests), fonts: `${fonts.length} req ${kb(fonts)} KB`, api: api.map((r) => `${new URL(r.url).pathname} ${r.bytes >> 10} KB`).join(', '), longSum, longMax };
}

console.log(`CPU slowdown ${slow}x, ${base}`);
console.log('== cold load (empty cache), then a second load with the cache');
for (const tab of tabs) {
	const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
	const page = await newPage(context);
	const cold = await loadOnce(page, paths[tab]);
	const warm = await loadOnce(page, paths[tab]);
	const line = (r) => `ttfb ${r.ttfb} | fcp ${r.fcp} | lcp ${r.lcp} | dcl ${r.dcl} | load ${r.load} | ${r.n} req ${r.kb} KB | fonts ${r.fonts} | long tasks ${r.long.length}, sum ${r.longSum}, max ${r.longMax}`;
	console.log(`${tab.padEnd(16)} cold: ${line(cold)}`);
	console.log(`${''.padEnd(16)} warm: ${line(warm)}`);
	if (cold.api) console.log(`${''.padEnd(16)} api in the browser: ${cold.api}`);
	await context.close();
}

console.log('== change of the tab (click), from Settings; 3 runs each');
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await newPage(context);
for (const tab of tabs.filter((t) => t !== 'Settings')) {
	const runs = [];
	for (let k = 0; k < 3; k++) {
		await page.goto(`${base}/settings`, { waitUntil: 'networkidle' });
		let dataStart = 0;
		let dataEnd = 0;
		const onRequest = (r) => r.url().includes('__data.json') && (dataStart = Date.now());
		const onDone = (r) => r.url().includes('__data.json') && (dataEnd = Date.now());
		page.on('request', onRequest);
		page.on('requestfinished', onDone);
		const before = await page.evaluate(() => window.__long.length);
		const link = page.getByRole('navigation', { name: 'Tabs' }).getByRole('link', { name: tab, exact: true });
		const url = page.url();
		const start = Date.now();
		await link.click();
		await page.waitForURL((u) => u.href !== url, { timeout: 60_000 });
		await page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))));
		const shown = Date.now() - start;
		const long = await page.evaluate((n) => window.__long.slice(n).reduce((s, [, d]) => s + d, 0), before);
		runs.push({ shown, data: dataEnd && dataStart ? dataEnd - dataStart : 0, after: dataEnd ? Date.now() - dataEnd : 0, long });
		page.off('request', onRequest);
		page.off('requestfinished', onDone);
	}
	const avg = (key) => String(Math.round(runs.reduce((s, r) => s + r[key], 0) / runs.length)).padStart(5);
	console.log(`${tab.padEnd(16)} click to page ${avg('shown')} ms | data ${avg('data')} ms | after the data ${avg('after')} ms | long tasks ${avg('long')} ms`);
}
await browser.close();
