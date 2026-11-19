// The deck of the Discover tab: shows that the user does not have, one card at a time. The
// answers are "interested", "not interested" and "seen it". The server draws the cards at random.
//
// The deck keeps its cards when the user opens a different tab. Thus the user comes back to the
// same card, and the deck does not draw a card again that the user did not answer.
import { api } from '#lib/api/client.js';
import type { Show, Tier } from '#lib/api/types.js';
import { library } from './library.svelte.js';
import { pictures } from './pictures.svelte.js';

/** The number of cards of one request */
const BATCH = 12;

type Step = { show: Show; kind: 'answer' } | { show: Show; kind: 'seen'; tier: Tier | null };

class DiscoverDeck {
	queue = $state<Show[]>([]);
	index = $state(0);
	/** The user said "Seen it" for the card: the deck shows the tier buttons */
	seen = $state(false);
	loading = $state(false);
	/** A request that changes data is in progress: a second answer does nothing */
	private busy = false;
	private undo: Step[] = [];

	get show(): Show | null {
		return this.queue[this.index] ?? null;
	}

	/** The tab opens: keep the card of now, or start a new deck */
	async start() {
		if (this.show) return;
		this.queue = [];
		this.index = 0;
		this.undo = [];
		this.seen = false;
		await this.loadCards();
	}

	/** Get the next cards and put them at the end of the queue */
	private async loadCards() {
		if (this.loading) return;
		this.loading = true;
		try {
			const result = await api.discover(BATCH);
			const have = new Set(this.queue.map((show) => show.id));
			const cards = result.cards.filter((show) => !have.has(show.id));
			library.counts = result.counts;
			this.queue.push(...cards);
			// One request gets the pictures of all new cards. The deck does not wait for it.
			pictures.load(cards.map((show) => show.id)).then(() => pictures.preload(this.queue[this.index + 1]?.id));
		} catch (error) {
			console.error('Failed to load the Discover deck', error);
		}
		this.loading = false;
	}

	private next() {
		this.seen = false;
		this.index += 1;
		// Get more cards before the deck is empty
		if (this.index >= this.queue.length - 2) this.loadCards();
		pictures.preload(this.queue[this.index + 1]?.id);
	}

	/** The answer "interested" (true) or "not interested" (false) for the card */
	async answer(value: boolean) {
		const show = this.show;
		if (!show || this.seen || this.busy) return;
		this.busy = true;
		try {
			await library.setInterest(show, value, 'deck');
		} catch (error) {
			console.error('Failed to save the answer', error);
			return;
		} finally {
			this.busy = false;
		}
		this.undo.push({ show, kind: 'answer' });
		this.next();
	}

	/** "Seen it": the deck shows the tier buttons for the card */
	markSeen() {
		if (this.show) this.seen = true;
	}

	/** After "Seen it": the show goes to the watched shows of the user, with a tier or without one */
	async rateSeen(tier: Tier | null) {
		const show = this.show;
		if (!show || !this.seen || this.busy) return;
		this.busy = true;
		try {
			await library.setWatched(show, true);
			if (tier) await library.setTier(show, tier);
		} catch (error) {
			console.error('Failed to save the watched show', error);
			return;
		} finally {
			this.busy = false;
		}
		this.undo.push({ show, kind: 'seen', tier });
		this.next();
	}

	/** Go back from the tier buttons, or take the last answer back */
	async undoLast() {
		if (this.seen) {
			this.seen = false;
			return;
		}
		if (this.busy) return;
		const last = this.undo.pop();
		if (!last) return;
		const show = last.show;
		this.busy = true;
		try {
			if (last.kind === 'answer') {
				await library.setInterest(show, null, 'deck');
			} else {
				if (last.tier) await library.setTier(show, null);
				await library.setWatched(show, false);
			}
		} catch (error) {
			console.error('Failed to take the answer back', error);
		} finally {
			this.busy = false;
		}
		this.index = Math.max(
			0,
			this.queue.findIndex((card) => card.id === show.id)
		);
	}

	/** Go to the next card without an answer. After "Seen it", save the show as watched without a tier. */
	skip() {
		if (this.seen) this.rateSeen(null);
		else if (this.show) this.next();
	}
}

export const discoverDeck = new DiscoverDeck();
