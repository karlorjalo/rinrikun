// The Recommendations tab: the formula that the user selected, the filters, and the list.
//
// The formula has two parts. "kinds": "usual" gives a higher score to the kinds of shows that
// the library has many of, and "all" gives each kind of show the same chance. "links": the crowd
// links are the recommendations of AniList users, and without them the formula uses only the
// ratings of the user and the facts of the shows. The browser keeps the two selections, with the
// keys of the old page.
import { api } from '#lib/api/client.js';
import type { Kinds, Show } from '#lib/api/types.js';
import { library } from './library.svelte.js';
import { seeds } from './seed.svelte.js';

const FORMULA_KEY = 'rinrikun-formula';
const LINKS_KEY = 'rinrikun-links';

/** The formula that made a list. A list with a seed has its own order: "seed". */
export type AppliedFormula = Kinds | 'seed';

function saved(key: string): string | null {
	try {
		return localStorage.getItem(key);
	} catch {
		return null;
	}
}

function save(key: string, value: string) {
	try {
		localStorage.setItem(key, value);
	} catch {
		// The selection then stays only until the page closes
	}
}

class RecommendView {
	kinds = $state<Kinds>(saved(FORMULA_KEY) === 'all' ? 'all' : 'usual');
	links = $state(saved(LINKS_KEY) !== 'off');
	/** Give results that are less similar to each other */
	variety = $state(false);
	/** Also show sequels and side stories of shows that the user has */
	sequels = $state(false);
	/** The filters of the list on the page. They do not ask the server again. */
	format = $state<'all' | 'tv' | 'movie' | 'ova'>('all');
	minScore = $state<'0' | '7.0' | '7.5' | '8.0'>('0');

	list = $state<Show[]>([]);
	loaded = $state(false);
	/** The formula that made the list on the page. The tooltip of the button "About" tells it. */
	applied = $state<{ formula: AppliedFormula; links: boolean }>({ formula: 'usual', links: true });
	/** The last show that the user removed from the list, for the undo bar */
	lastDismissed = $state<{ show: Show; index: number } | null>(null);
	/** The number of the last request for a list */
	private request = 0;

	/** Get the list for the formula and the seed of now */
	async load() {
		const seed = seeds.recommend;
		const applied = { formula: (seed ? 'seed' : this.kinds) as AppliedFormula, links: this.links };
		const request = ++this.request;
		this.lastDismissed = null;
		let list: Show[];
		try {
			list = await api.recommend({ k: 40, seed: seed?.id, variety: !seed && this.variety, sequels: this.sequels, kinds: this.kinds, links: this.links });
		} catch (error) {
			console.error('Failed to load the recommendations', error);
			return;
		}
		// An older request that ends late must not replace the list of a newer request. Thus the
		// tooltip of the button "About" always names the formula of the list that the user sees.
		if (request !== this.request) return;
		this.list = list;
		this.applied = applied;
		this.loaded = true;
	}

	setKinds(kinds: Kinds) {
		this.kinds = kinds;
		save(FORMULA_KEY, kinds);
		return this.load();
	}

	setLinks(links: boolean) {
		this.links = links;
		save(LINKS_KEY, links ? 'on' : 'off');
		return this.load();
	}

	/** The shows of the list that pass the filters of the page */
	get shown(): Show[] {
		const least = Number(this.minScore);
		return this.list.filter((show) => {
			const format = (show.format || '').toLowerCase();
			if (this.format === 'tv' && !format.includes('tv') && format !== 'series') return false;
			if (this.format === 'movie' && !format.includes('movie')) return false;
			if (this.format === 'ova' && !format.includes('ova') && !format.includes('special')) return false;
			return least <= 0 || (show.score != null && show.score >= least);
		});
	}

	/** Remove a show from the recommendations. The other cards stay in their positions. */
	async dismiss(show: Show) {
		try {
			await library.setDismissed(show, true);
		} catch (error) {
			console.error('Failed to remove the recommendation', error);
			return;
		}
		const index = this.list.findIndex((item) => item.id === show.id);
		if (index >= 0) this.list.splice(index, 1);
		this.lastDismissed = { show, index };
	}

	/** Put the last removed show back in its position */
	async restore() {
		const last = this.lastDismissed;
		if (!last) return;
		try {
			await library.setDismissed(last.show, false);
		} catch (error) {
			console.error('Failed to put the recommendation back', error);
			return;
		}
		if (last.index >= 0 && !this.list.some((item) => item.id === last.show.id)) {
			this.list.splice(Math.min(last.index, this.list.length), 0, last.show);
		}
		this.lastDismissed = null;
	}
}

export const recommendView = new RecommendView();
