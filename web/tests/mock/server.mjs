// A small copy of the API of the rinrikun server, with invented shows.
//
// The browser tests and the development of the page use this server. They must not use the real
// server: it has the data of the user, and a test that gives an answer would change that data.
// Each show here is invented. The answers have the same shape as the answers of the real server
// (see src/lib/api/types.ts), but the numbers come from simple rules, not from the real formulas.
//
// Usage: node tests/mock/server.mjs [port]      (the default port is 8799)
// POST /api/__reset puts the data back to its start. GET /api/__requests gives the requests since
// then: a test can check a request that the server of the page sent. POST /api/__delay {"ms": n}
// makes each next answer wait n milliseconds (a slow server, for the loading bar); a reset ends it.
import http from 'node:http';

const PORT = Number(process.argv[2] ?? process.env.MOCK_PORT ?? 8799);
/** The time that each answer waits (POST /api/__delay) */
let delay = 0;

/** A random number generator that gives the same numbers each time */
function generator(seed) {
	let state = seed >>> 0;
	return () => {
		state = (state + 0x6d2b79f5) >>> 0;
		let t = state;
		t = Math.imul(t ^ (t >>> 15), t | 1);
		t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}

const FIRST = [
	['星降る', 'Hoshifuru', 'Starfall'],
	['放課後の', 'Houkago no', 'After-School'],
	['銀色の', "Gin'iro no", 'Silver'],
	['真夜中の', 'Mayonaka no', 'Midnight'],
	['七色', 'Nanairo', 'Seven-Color'],
	['最果ての', 'Saihate no', "World's End"],
	['雨上がりの', 'Ameagari no', 'After-Rain'],
	['恋する', 'Koisuru', 'Lovestruck'],
	['眠れる', 'Nemureru', 'Sleeping'],
	['風待ちの', 'Kazemachi no', 'Windward']
];
const SECOND = [
	['図書館', 'Toshokan', 'Library'],
	['喫茶店', 'Kissaten', 'Cafe'],
	['観測所', 'Kansokujo', 'Observatory'],
	['軽音部', 'Keionbu', 'Light Music Club'],
	['魔法使い', 'Mahoutsukai', 'Magician'],
	['自転車部', 'Jitenshabu', 'Cycling Club'],
	['写真部', 'Shashinbu', 'Photo Club'],
	['探偵団', 'Tanteidan', 'Detectives'],
	['料理人', 'Ryourinin', 'Cook'],
	['飛行士', 'Hikoushi', 'Aviator'],
	['人形師', 'Ningyoushi', 'Puppeteer'],
	['郵便局', 'Yuubinkyoku', 'Post Office'],
	['庭師', 'Niwashi', 'Gardener'],
	['歌姫', 'Utahime', 'Diva']
];
// A kind of show: its genres, its tags, and its place on the map
const KINDS = [
	{ label: 'school life · club activities', genres: ['Comedy', 'Slice of Life'], tags: ['school life', 'club activities', 'cute girls doing cute things', 'iyashikei'], at: [0.25, 0.3] },
	{ label: 'romance · love triangle', genres: ['Romance', 'Drama'], tags: ['romance', 'love triangle', 'coming of age', 'tsundere'], at: [0.7, 0.25] },
	{ label: 'magic · travel', genres: ['Fantasy', 'Adventure'], tags: ['magic', 'travel', 'found family', 'isekai'], at: [0.75, 0.7] },
	{ label: 'detective · time travel', genres: ['Mystery', 'Sci-Fi'], tags: ['detective', 'time travel', 'tragedy', 'urban fantasy'], at: [0.3, 0.75] },
	{ label: 'band · idols', genres: ['Music', 'Drama'], tags: ['band', 'idols', 'coming of age', 'school life'], at: [0.5, 0.5] }
];
const STUDIOS = ['Studio Hinata', 'Aozora Works', 'Kumo Animation', 'Mikan Pictures', 'Tsubame Lab'];
const FORMATS = ['TV', 'TV', 'TV', 'TV', 'MOVIE', 'OVA'];
const TIER_WEIGHTS = { S: 2.0, A: 1.5, B: 1.0, C: 0.5, D: 0.0 };
const TIERS = ['S', 'A', 'B', 'C', 'D'];
const LIBRARY = 28;
const TOTAL = 140;
// A cell of the grid of the close view of the map. It is small, thus the map starts in its far view.
const CELL = { w: 0.03, h: 0.042 };

/** A picture as an address that needs no request: one color and one character */
function picture(width, height, hue, text, size) {
	const svg =
		`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}">` +
		`<rect width="${width}" height="${height}" fill="hsl(${hue} 34% 58%)"/>` +
		`<text x="${width / 2}" y="${height / 2 + size / 3}" font-size="${size}" text-anchor="middle" fill="#fff" font-family="sans-serif">${text}</text></svg>`;
	return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

let rows = [];
let points = [];
let regions = [];
let interestSource = {};
let deckSeed = 1;
/** The requests since the last reset: "GET /api/recommend?k=40..." */
let requests = [];

function makeData() {
	const random = generator(20261119);
	const pick = (list) => list[Math.floor(random() * list.length)];
	rows = [];
	const taken = new Set();
	const cells = new Set();
	for (let n = 0; n < TOTAL; n++) {
		let a, b;
		do {
			a = Math.floor(random() * FIRST.length);
			b = Math.floor(random() * SECOND.length);
		} while (taken.has(`${a}-${b}`));
		taken.add(`${a}-${b}`);
		const kind = n % KINDS.length;
		const library = n < LIBRARY;
		const tags = KINDS[kind].tags.filter(() => random() < 0.8);
		if (random() < 0.4) tags.push(pick(KINDS[(kind + 1) % KINDS.length].tags));
		const format = pick(FORMATS);
		const hue = Math.floor(random() * 360);
		const native = FIRST[a][0] + SECOND[b][0];
		// The match goes down with the number of the show, with some noise
		const match = Math.max(0.5, Math.min(100, 100 - (n / TOTAL) * 92 + (random() - 0.5) * 14));
		const x = Math.min(0.97, Math.max(0.03, KINDS[kind].at[0] + (random() - 0.5) * 0.36));
		const y = Math.min(0.97, Math.max(0.03, KINDS[kind].at[1] + (random() - 0.5) * 0.36));
		// Each show has its own cell of the grid, near its position
		let cx = Math.round(x / CELL.w);
		let cy = Math.round(y / CELL.h);
		for (let radius = 0; cells.has(`${cx},${cy}`); radius++) {
			cx = Math.round(x / CELL.w) + Math.round((random() - 0.5) * 2 * (radius / 3 + 1));
			cy = Math.round(y / CELL.h) + Math.round((random() - 0.5) * 2 * (radius / 3 + 1));
		}
		cells.add(`${cx},${cy}`);
		const tier = library && n % 7 !== 6 ? ['S', 'A', 'B', 'A', 'B', 'C', 'B', 'S', 'A', 'D'][n % 10] : null;
		rows.push({
			id: library ? `jf:${1000 + n}` : `al:${20000 + n}`,
			source: library ? 'library' : 'anilist',
			title: `${FIRST[a][1]} ${SECOND[b][1]}`,
			title_native: library && n % 5 === 0 ? '' : native,
			title_english: `The ${FIRST[a][2]} ${SECOND[b][2]}`,
			year: 2004 + Math.floor(random() * 22),
			format,
			genres: KINDS[kind].genres,
			tags,
			tag_ranks: tags.map(() => 50 + Math.floor(random() * 50)),
			studios: [pick(STUDIOS)],
			overview:
				n % 11 === 3
					? ''
					: `An invented show for the tests: the ${FIRST[a][2].toLowerCase()} ${SECOND[b][2].toLowerCase()} and the people around it.<br><br>` +
						`<i>${KINDS[kind].label}</i>\nA second line of the synopsis, so that the text is long enough for a card with four lines of text and more.`,
			score: n % 13 === 5 ? null : Math.round((5.6 + random() * 3.2) * 10) / 10,
			owned: library ? 1 : 0,
			manual_watched: 0,
			anilist_id: n % 17 === 9 && library ? null : 20000 + n,
			poster: n % 19 === 7 ? null : picture(72, 104, hue, native[0], 40),
			status: 'FINISHED',
			episodes: format === 'MOVIE' ? 1 : pick([12, 12, 13, 24, 25]),
			popularity_place: 1 + Math.floor(random() * 6000),
			tier,
			weight: tier ? TIER_WEIGHTS[tier] : 1.0,
			dismissed: 0,
			interest: null,
			match: Math.round(match * 10) / 10,
			tier_guess: tier ? null : TIERS[Math.min(4, Math.floor((100 - match) / 22))],
			// Not a part of the API: the data that this server needs
			_kind: kind,
			_hue: hue,
			_x: x,
			_y: y,
			_gx: cx * CELL.w,
			_gy: cy * CELL.h
		});
	}
	// Some shows that the user marked as watched by hand, some answers, and some removed shows
	for (const n of [30, 33, 41]) Object.assign(rows[n], { manual_watched: 1, owned: 1 });
	rows[33].tier = 'A';
	rows[33].weight = TIER_WEIGHTS.A;
	interestSource = {};
	for (const n of [36, 44, 52, 61, 75]) {
		rows[n].interest = 1;
		interestSource[rows[n].id] = 'deck';
	}
	for (const n of [58, 90, 117]) {
		rows[n].interest = 0;
		rows[n].dismissed = 1;
		interestSource[rows[n].id] = 'deck';
	}
	for (const n of [66, 101]) rows[n].dismissed = 1;
	points = rows.map((row) => row);
	regions = [];
	KINDS.forEach((kind, k) => {
		const members = rows.filter((row) => row._kind === k);
		regions.push({ x: kind.at[0], y: kind.at[1], gx: kind.at[0], gy: kind.at[1], label: kind.label, count: members.length, level: 0 });
		regions.push({
			x: kind.at[0] + 0.08, y: kind.at[1] - 0.09, gx: kind.at[0] + 0.08, gy: kind.at[1] - 0.09,
			label: kind.tags.slice(2).join(' · '), count: Math.floor(members.length / 2), level: 1
		});
	});
	deckSeed = 1;
}

const byId = (id) => rows.find((row) => row.id === id);
const refused = (row) => row.dismissed === 1;
/** The show as the API gives it: without the data of this server */
function open(row, more = {}) {
	const out = { shared_tags: [], ...row, ...more };
	for (const key of Object.keys(out)) if (key.startsWith('_')) delete out[key];
	return out;
}
/** A show of a list of cards: without the long fields that only the detail window and the deck show */
function card(row, more = {}) {
	const out = open(row, more);
	for (const key of ['overview', 'studios', 'tag_ranks']) delete out[key];
	return out;
}
const byMatch = (a, b) => (b.match ?? 0) - (a.match ?? 0);
const counts = () => ({
	interested: rows.filter((row) => row.interest === 1).length,
	not_interested: rows.filter((row) => row.interest === 0).length
});
const shared = (a, b) => a.tags.filter((tag) => b.tags.includes(tag));

function similarTo(seed, k) {
	return rows
		.filter((row) => row !== seed)
		.map((row) => {
			const tags = shared(seed, row);
			const similarity = Math.min(99, 38 + tags.length * 14 + (row._kind === seed._kind ? 8 : 0) + (row._hue % 7));
			return card(row, { similarity, shared_tags: tags.sort() });
		})
		.sort((a, b) => b.similarity - a.similarity)
		.slice(0, k);
}

function candidates(sequels) {
	return rows.filter((row) => !row.owned && !refused(row) && (sequels || row._hue % 9 !== 0));
}

function recommend(query) {
	const k = Number(query.get('k') ?? 20);
	const seed = query.get('seed') ? byId(query.get('seed')) : null;
	const links = query.get('links') !== 'false';
	const sequels = query.get('new_only') === 'false';
	const liked = rows.filter((row) => row.owned && (row.tier === 'S' || row.tier === 'A'));
	let list = candidates(sequels).map((row) => {
		const favorite = liked.find((other) => other._kind === row._kind) ?? liked[0];
		const more = { matched_favorite: favorite ? favorite.title_native || favorite.title : undefined };
		if (links && row._hue % 4 === 0 && liked.length > 1) more.linked_favorite = liked[1].title_native || liked[1].title;
		if (sequels && row._hue % 9 === 0) more.franchise_owned = 1;
		if (seed) {
			more.shared_tags = shared(seed, row).sort();
			more.similarity = Math.min(99, 38 + more.shared_tags.length * 14 + (row._kind === seed._kind ? 8 : 0) + (row._hue % 7));
		}
		return [row, more];
	});
	const order = (a, b) => (seed ? b[1].similarity - a[1].similarity : 0) || byMatch(a[0], b[0]);
	list.sort(order);
	if (query.get('kinds') === 'usual') list = list.filter(([row]) => row.format !== 'OVA').concat(list.filter(([row]) => row.format === 'OVA'));
	if (query.get('mode') === 'diverse') {
		// One show of each kind in turn
		const groups = KINDS.map((_, kind) => list.filter(([row]) => row._kind === kind));
		list = [];
		for (let n = 0; list.length < groups.reduce((sum, group) => sum + group.length, 0); n++) {
			for (const group of groups) if (group[n]) list.push(group[n]);
		}
	}
	return list.slice(0, k).map(([row, more]) => card(row, more));
}

function steps(query) {
	const k = Number(query.get('k') ?? 40);
	const links = query.get('links') !== 'false';
	const kinds = query.get('kinds') ?? 'all';
	const cand = candidates(query.get('new_only') === 'false').sort(byMatch);
	const index = (row) => points.indexOf(row);
	const keys = ['content', ...(links ? ['links'] : []), 'tier', ...(kinds === 'usual' ? ['kind'] : [])];
	const ratio = Math.min(1, k / cand.length) ** (1 / (keys.length + 1));
	const out = [
		{ key: 'catalog', count: points.length, points: null },
		{ key: 'new', count: cand.length, points: cand.map(index) }
	];
	keys.forEach((key, n) => {
		const size = Math.max(k, Math.round(cand.length * ratio ** (n + 1)));
		out.push({ key, count: Math.min(size, cand.length), points: cand.slice(0, size).map(index) });
	});
	out.push({ key: 'list', count: Math.min(k, cand.length), points: cand.slice(0, k).map(index) });
	const mine = rows.filter((row) => row.owned);
	return {
		kinds, links, k, steps: out,
		info: {
			shows: mine.length, franchises: mine.length - 3, removed: rows.filter(refused).length,
			liked: mine.filter((row) => ['S', 'A', 'B'].includes(row.tier)).length,
			rated: mine.filter((row) => row.tier).length, sources: 9
		}
	};
}

function interestResults() {
	const deck = rows.filter((row) => row.interest != null && interestSource[row.id] === 'deck' && !row.owned);
	const lows = [99, 95, 80, 0];
	let high = null;
	const groups = lows.map((low) => {
		const inside = deck.filter((row) => row.match >= low && (high === null || row.match < high));
		const group = { low, high: high ?? 100, answers: inside.length, interested: inside.filter((row) => row.interest === 1).length };
		high = low;
		return group;
	});
	const all = counts();
	return {
		answers: all.interested + all.not_interested, ...all, groups,
		model: all.interested >= 3 && all.not_interested >= 3 ? { pairs: all.interested * all.not_interested, auc: 0.71 } : null,
		popular: 5000
	};
}

function pictures(ids) {
	const out = {};
	for (const id of ids) {
		const row = byId(id);
		if (!row || row.anilist_id == null) continue;
		const number = row._hue % 5;
		if (number === 4) continue; // AniList gave no answer for this show
		const frames = [];
		for (let n = 0; n < [6, 4, 1, 0][number]; n++) {
			const label = n < 4 ? `Episode ${n + 1}` : 'Trailer';
			const address = picture(320, 180, (row._hue + n * 37) % 360, label, 30);
			frames.push({ small: address, large: address, label });
		}
		out[id] = {
			frames,
			trailer: number === 0 ? 'https://www.youtube.com/watch?v=invented' : null,
			banner: number === 3 ? picture(640, 180, row._hue, row.title_native || row.title, 34) : null
		};
	}
	return out;
}

function recLog() {
	const added = rows.filter((row) => row.manual_watched).slice(0, 2);
	return {
		since: '2026-10-02', shown: 64, added: added.length, unrated: added.filter((row) => !row.tier).length, removed: 3,
		tiers: { S: 0, A: added.filter((row) => row.tier === 'A').length, B: 0, C: 0, D: 0 },
		shows: added.map((row, n) => ({ id: row.id, title: row.title, title_native: row.title_native, tier: row.tier, first_seen: `2026-10-${12 + n}`, best_rank: 3 + n * 4 })),
		formulas: { links: { shown: 40, added: added.length, removed: 2 }, 'no links': { shown: 24, added: 0, removed: 1 } }
	};
}

class Refusal extends Error {
	constructor(status, detail) {
		super(detail);
		this.status = status;
	}
}

function known(id) {
	const row = id ? byId(id) : null;
	if (!row) throw new Refusal(404, 'unknown show id');
	return row;
}

/** Give the answer for one request. `body` is the JSON of a POST request. */
function answer(method, path, query, body) {
	const route = `${method} ${path}`;
	if (route === 'POST /api/__reset') return makeData(), (requests = []), (delay = 0), { ok: true };
	if (route === 'POST /api/__delay') return (delay = Number(body.ms) || 0), { ok: true };
	if (route === 'GET /api/__requests') return requests;
	if (route === 'GET /api/profile') {
		const mine = rows.filter((row) => row.owned);
		const summary = { S: 0, A: 0, B: 0, C: 0, D: 0, unrated: 0 };
		for (const row of mine) summary[row.tier ?? 'unrated'] += 1;
		return {
			tier_summary: summary, owned_count: mine.length, library_count: mine.filter((row) => row.source === 'library').length,
			manual_count: rows.filter((row) => row.manual_watched).length, total_count: rows.length
		};
	}
	if (route === 'GET /api/shows') {
		return rows.map((row) => ({
			id: row.id, title: row.title, title_native: row.title_native, year: row.year, poster: row.poster, owned: row.owned,
			manual_watched: row.manual_watched, tier: row.tier, weight: row.weight, aka: [row.title_english]
		}));
	}
	if (method === 'GET' && path.startsWith('/api/show/')) return open(known(decodeURIComponent(path.slice('/api/show/'.length))));
	if (route === 'GET /api/ratings') {
		return rows.filter((row) => row.owned && row.tier).sort((a, b) => TIERS.indexOf(a.tier) - TIERS.indexOf(b.tier) || byMatch(a, b)).map((row) => card(row));
	}
	if (route === 'GET /api/watched') return rows.filter((row) => row.manual_watched).map((row) => card(row));
	if (route === 'GET /api/dismissed') return rows.filter(refused).map((row) => card(row));
	if (route === 'GET /api/review-queue') {
		const mine = rows.filter((row) => row.owned);
		const unrated = mine.filter((row) => !row.tier).sort(byMatch);
		const rated = query.get('unrated_only') === 'true' ? [] : mine.filter((row) => row.tier).sort(byMatch);
		return [...unrated, ...rated].map((row) => open(row));
	}
	if (route === 'POST /api/weights' || route === 'DELETE /api/weights') {
		const row = known(method === 'POST' ? body.id : query.get('id'));
		const tier = method === 'POST' && body.tier ? String(body.tier).toUpperCase() : null;
		row.tier = tier;
		row.weight = tier ? (TIER_WEIGHTS[tier] ?? 1.0) : 1.0;
		row.tier_guess = tier ? null : 'B';
		return { id: row.id, tier: row.tier, weight: row.weight, ids: [row.id] };
	}
	if (route === 'POST /api/watched') {
		const row = known(body.id);
		const watched = body.watched !== false;
		row.manual_watched = watched ? 1 : 0;
		if (row.source !== 'library') row.owned = watched ? 1 : 0;
		return { id: row.id, watched, owned: row.owned };
	}
	if (route === 'POST /api/dismissed') {
		const row = known(body.id);
		const dismissed = body.dismissed !== false;
		// To remove a show replaces its answer. To put it back deletes the answer "not interested".
		if (dismissed || row.interest === 0) row.interest = null;
		row.dismissed = dismissed ? 1 : 0;
		return { id: row.id, dismissed };
	}
	if (route === 'GET /api/discover') {
		const count = Number(query.get('count') ?? 12);
		const random = generator(deckSeed++);
		const pool = rows.filter((row) => !row.owned && !refused(row) && row.interest == null);
		const cards = [];
		while (cards.length < count && pool.length) cards.push(pool.splice(Math.floor(random() * pool.length), 1)[0]);
		return { cards: cards.map((row) => open(row)), counts: counts() };
	}
	if (route === 'GET /api/interest') return rows.filter((row) => row.interest === 1 && !row.owned).sort(byMatch).map((row) => card(row));
	if (route === 'POST /api/interest') {
		const row = known(body.id);
		if (body.value == null) {
			if (row.interest === 0) row.dismissed = 0;
			row.interest = null;
		} else {
			if (row.owned) throw new Refusal(400, 'the user has this show: it gets a tier, not an answer');
			row.interest = body.value ? 1 : 0;
			row.dismissed = body.value ? 0 : 1;
			interestSource[row.id] = body.source === 'deck' ? 'deck' : 'page';
		}
		return { id: row.id, interest: row.interest, dismissed: row.dismissed, counts: counts() };
	}
	if (route === 'GET /api/interest/results') return interestResults();
	if (route === 'GET /api/frames') return pictures((query.get('ids') ?? '').split(','));
	if (route === 'GET /api/similar') return similarTo(known(query.get('id')), Number(query.get('k') ?? 24));
	if (route === 'GET /api/recommend') {
		if (query.get('seed')) known(query.get('seed'));
		return recommend(query);
	}
	if (route === 'GET /api/recommend/steps') return steps(query);
	if (route === 'GET /api/rec-log') return recLog();
	if (route === 'GET /api/vector-map') {
		return {
			center: { x: 0.32, y: 0.36 },
			points: points.map((row) => ({
				id: row.id, x: row._x, y: row._y, gx: row._gx, gy: row._gy, title: row.title, title_native: row.title_native, year: row.year,
				poster: row.poster, genres: row.genres.slice(0, 2), owned: row.owned, tier: row.tier, score: row.score, aka: [row.title_english]
			})),
			regions,
			cell: CELL
		};
	}
	if (route === 'GET /api/vector-map/match') return points.map((row) => row.match);
	throw new Refusal(404, 'Not Found');
}

makeData();
const server = http.createServer((request, response) => {
	const url = new URL(request.url, 'http://mock');
	let text = '';
	request.on('data', (part) => (text += part));
	request.on('end', () => {
		let status = 200;
		let result;
		if (!url.pathname.startsWith('/api/__')) requests.push(`${request.method} ${url.pathname}${url.search}`);
		try {
			result = answer(request.method, url.pathname, url.searchParams, text ? JSON.parse(text) : {});
		} catch (error) {
			status = error instanceof Refusal ? error.status : 500;
			result = { detail: String(error.message) };
		}
		const send = () => {
			response.writeHead(status, { 'Content-Type': 'application/json' });
			response.end(JSON.stringify(result));
		};
		if (delay > 0 && !url.pathname.startsWith('/api/__')) setTimeout(send, delay);
		else send();
	});
});
server.listen(PORT, '127.0.0.1', () => console.log(`mock API on http://127.0.0.1:${PORT}`));
