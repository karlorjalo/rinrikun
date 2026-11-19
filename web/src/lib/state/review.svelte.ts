// The deck of the Review tab: the shows of the user, one card at a time. The user gives each
// show a tier. The shows without a tier come first.
import { api } from '#lib/api/client.js';
import type { Show, Tier } from '#lib/api/types.js';
import { library } from './library.svelte.js';

export type ReviewMode = 'unrated' | 'all';

class ReviewDeck {
	/** "unrated": only the shows without a tier. "all": then also the rated shows. */
	mode = $state<ReviewMode>('unrated');
	queue = $state<Show[]>([]);
	index = $state(0);
	/** The numbers of the title row: the rated shows and all shows of the user */
	rated = $state(0);
	total = $state(0);
	loaded = $state(false);
	/** The server did not give the queue */
	failed = $state(false);
	/** The tiers that the user gave in this visit, with the tier that the show had before */
	private undo: { show: Show; before: Tier | null }[] = [];

	get show(): Show | null {
		return this.queue[this.index] ?? null;
	}

	/** Get the queue of the mode from the server, and start at its first card */
	async load() {
		const mode = this.mode;
		try {
			const [queue, profile] = await Promise.all([api.reviewQueue(mode === 'unrated'), api.profile()]);
			// The user went to the other mode in the time of the request
			if (this.mode !== mode) return;
			this.queue = queue;
			this.index = 0;
			this.undo = [];
			const summary = profile.tier_summary;
			this.rated = summary.S + summary.A + summary.B + summary.C + summary.D;
			this.total = this.rated + summary.unrated;
			this.failed = false;
		} catch (error) {
			console.error('Failed to load the review queue', error);
			this.failed = true;
		}
		this.loaded = true;
	}

	setMode(mode: ReviewMode) {
		if (this.mode === mode) return;
		this.mode = mode;
		this.loaded = false;
		this.load();
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

export const reviewDeck = new ReviewDeck();
