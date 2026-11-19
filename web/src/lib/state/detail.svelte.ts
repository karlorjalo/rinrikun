// The detail window of a show. Each list opens it for one of its shows.
import { api } from '#lib/api/client.js';
import type { Show } from '#lib/api/types.js';

class Detail {
	/** The show of the window, or null if the window is closed */
	show = $state<Show | null>(null);

	/** Open the window for a show. A show from a short list (the search, a map) gets its full data first. */
	async open(show: Show | { id: string }) {
		let full = show as Show;
		if (full.overview === undefined) {
			try {
				full = { ...full, ...(await api.show(show.id)) };
			} catch {
				// The window shows the data that the list has
			}
		}
		this.show = full;
	}

	close() {
		this.show = null;
	}
}

export const detail = new Detail();
