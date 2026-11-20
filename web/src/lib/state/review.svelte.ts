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
	/**
	 * The tier requests, in their order. The deck changes at once, and the requests go to the
	 * server one after the other: a tier and its undo reach the server in the order of the keys.
	 */
	private saving: Promise<void> = Promise.resolve();
	/**
	 * The tier that the user wants for each show, by the id of the show. The answer of a request
	 * sets the tier of the show to the tier of that request, and a later key can already have
	 * changed it: after each answer, the show gets the tier that the user wants again.
	 */
	private wanted = new Map<string, Tier | null>();

	/** Send a tier to the server after the requests before it */
	private save(show: Show, tier: Tier | null, failure: string) {
		this.wanted.set(show.id, tier);
		this.saving = this.saving.then(async () => {
			try {
				await library.setTier(show, tier);
			} catch (error) {
				console.error(failure, error);
			}
			show.tier = this.wanted.get(show.id) ?? null;
		});
	}

	/**
	 * Wait until the server has each tier of this deck. A new deck gets its queue from the server,
	 * thus the page waits for this before it asks for a new deck.
	 */
	saved(): Promise<void> {
		return this.saving;
	}

	constructor(data: ReviewData) {
		this.queue = data.queue;
		this.rated = data.rated;
		this.total = data.total;
	}

	get show(): Show | null {
		return this.queue[this.index] ?? null;
	}

	/** Give the show of the card a tier, and go to the next card at once */
	rate(tier: Tier) {
		const show = this.show;
		if (!show) return;
		const before = show.tier;
		this.undo.push({ show, before });
		if (!before) this.rated += 1;
		show.tier = tier;
		this.index += 1;
		this.save(show, tier, 'Failed to save the tier');
	}

	/** Take the last tier back, and go back to its card at once */
	undoLast() {
		const last = this.undo.pop();
		if (!last) return;
		const { show, before } = last;
		if (show.tier && !before && this.rated > 0) this.rated -= 1;
		show.tier = before;
		if (this.index > 0) this.index -= 1;
		this.save(show, before, 'Failed to take the tier back');
	}

	skip() {
		if (this.index < this.queue.length) this.index += 1;
	}
}
