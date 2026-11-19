// A CPU profile and a timeline of the full load of one page: the time of the script, of the
// style and of the layout, the script functions with the most self time, the time of each script
// file, and the long events. The static files are in the cache first, thus the profile shows the
// work of the page and not the network.
//
//   node perf/load_trace.mjs <page address> <path> [cpu slowdown]
//   node perf/load_trace.mjs http://PC_ADDRESS:8771 /ratings 4
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
await cdp.send('Profiler.enable');
await cdp.send('Profiler.setSamplingInterval', { interval: 200 });
const events = [];
cdp.on('Tracing.dataCollected', (e) => events.push(...e.value));
await cdp.send('Tracing.start', { categories: 'devtools.timeline', transferMode: 'ReportEvents' });
await cdp.send('Profiler.start');
await page.goto(base + path, { waitUntil: 'networkidle', timeout: 120_000 });
await page.waitForTimeout(1500);
const { profile } = await cdp.send('Profiler.stop');
const done = new Promise((resolve) => cdp.once('Tracing.tracingComplete', resolve));
await cdp.send('Tracing.end');
await done;

const NAMES = ['Layout', 'UpdateLayoutTree', 'Paint', 'FunctionCall', 'EvaluateScript', 'ParseHTML', 'RecalculateStyles', 'PrePaint', 'Layerize', 'TimerFire', 'FireAnimationFrame', 'v8.compile', 'v8.parseOnBackground'];
const sum = {};
for (const e of events) {
	if (e.ph === 'X' && e.dur && NAMES.includes(e.name)) sum[e.name] = (sum[e.name] ?? 0) + e.dur / 1000;
}
console.log(`${path} at ${slow}x, timeline (ms):`, Object.fromEntries(Object.entries(sum).map(([k, v]) => [k, Math.round(v)])));

const byId = new Map(profile.nodes.map((n) => [n.id, n]));
const self = new Map();
const dt = profile.timeDeltas;
for (let k = 0; k < profile.samples.length; k++) {
	const f = byId.get(profile.samples[k]).callFrame;
	if (f.functionName === '(idle)' || f.functionName === '(program)') continue;
	const key = `${f.functionName || '(anonymous)'} ${f.url.split('/').pop()}:${f.lineNumber}`;
	self.set(key, (self.get(key) ?? 0) + (dt[k] ?? 0) / 1000);
}
for (const [k, v] of [...self.entries()].sort((a, b) => b[1] - a[1]).slice(0, 18)) console.log(`${v.toFixed(0).padStart(6)} ms  ${k}`);
const files = new Map();
for (const [k, v] of self) {
	const file = k.split(' ').pop().split(':')[0] || '(native)';
	files.set(file, (files.get(file) ?? 0) + v);
}
console.log('by file:', [...files].sort((a, b) => b[1] - a[1]).slice(0, 8).map(([f, v]) => `${f} ${Math.round(v)}`).join(', '));
const t0 = Math.min(...events.filter((e) => e.ts).map((e) => e.ts));
for (const e of events.filter((e) => e.ph === 'X' && e.dur > 30000).sort((a, b) => a.ts - b.ts).slice(0, 14)) {
	console.log(`  ${String(Math.round((e.ts - t0) / 1000)).padStart(5)} ms +${Math.round(e.dur / 1000)} ms ${e.name} ${e.args?.data?.url?.split('/').pop() ?? ''} ${e.args?.data?.functionName ?? ''}`);
}
await browser.close();
