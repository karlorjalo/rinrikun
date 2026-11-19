// The deck of the Review tab: the shows of the user, one card at a time. The user gives each
// show a tier. The shows without a tier come first. The page makes a deck from its data each
// time the tab opens, thus the deck has the queue of now.
import type { Show, Tier } from '#lib/api/types.js';
import { library } from './library.svelte.js';

export type ReviewMode = 'unrated' | 'all';

/** The data of the Review tab: see routes/review/+page.server.ts */
export interface ReviewData {
	mode: ReviewMode;
	queue: Show[];
	/** The rated shows and all shows of the user */
	rated: number;
	total: number;
}

export class ReviewDeck {
	queue = $state<Show[]>([]);
	index = $state(0);
	rated = $state(0);
	total = $state(0);
	/** The tiers that the user gave in this visit, with the tier that the show had before */
	private undo: { show: Show; before: Tier | null }[] = [];

	constructor(data: ReviewData) {
		this.queue = data.queue;
		this.rated = data.rated;
		this.total = data.total;
	}

	get show(): Show | null {
		return this.queue[this.index] ?? null;
	}

	/** Give the show of the card a tier, and go to the next card */
	async rate(tier: Tier) {
		const show = this.show;
		if (!show) return;
		const before = show.tier;
		this.undo.push({ show, before });
		if (!before) this.rated += 1;
		show.tier = tier;
		try {
			await library.setTier(show, tier);
		} catch (error) {
			console.error('Failed to save the tier', error);
		}
		this.index += 1;
	}

	/** Take the last tier back, and go back to its card */
	async undoLast() {
		const last = this.undo.pop();
		if (!last) return;
		const { show, before } = last;
		if (show.tier && !before && this.rated > 0) this.rated -= 1;
		show.tier = before;
		try {
			await library.setTier(show, before);
		} catch (error) {
			console.error('Failed to take the tier back', error);
		}
		if (this.index > 0) this.index -= 1;
	}

	skip() {
		if (this.index < this.queue.length) this.index += 1;
	}
}
