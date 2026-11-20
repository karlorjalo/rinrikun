// The detail window of a show. Each list opens it for one of its shows.
import { api } from '#lib/api/client.js';
import type { Show } from '#lib/api/types.js';

class Detail {
	/** The show of the window, or null if the window is closed */
	show = $state<Show | null>(null);
	/**
	 * The number of the last call of `open` or `close`. An answer of the server for an older call
	 * is ignored: the user closed the window or opened a different show in that time.
	 */
	private request = 0;

	/**
	 * Open the window for a show.
	 *
	 * - A show with all its data opens at once.
	 * - A card of a list has all data but the long fields (the overview, the studios, the tag
	 *   ranks). The window opens at once with the data of the card, and the long fields come with
	 *   the answer of the server.
	 * - A show from a short list (the search, a map) has only some titles. The window opens when
	 *   the server gives the full show.
	 */
	async open(show: Show | { id: string }) {
		const request = ++this.request;
		const known = show as Show;
		if (known.overview !== undefined) {
			this.show = known;
			return;
		}
		const card = Array.isArray(known.tags);
		if (card) this.show = known;
		let full: Show | null = null;
		try {
			full = await api.show(show.id);
		} catch {
			// The window shows the data that the list has
		}
		if (request !== this.request) return;
		if (card && this.show) {
			// Only the long fields: the user can have changed the tier in the window in this time
			if (full) Object.assign(this.show, { overview: full.overview, studios: full.studios, tag_ranks: full.tag_ranks });
		} else {
			this.show = full ? { ...known, ...full } : known;
		}
	}

	close() {
		this.request += 1;
		this.show = null;
	}
}

export const detail = new Detail();
