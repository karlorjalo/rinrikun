// The watch list: the shows with the answer "interested" that the user does not have. The
// button "Watch list" of the Discover tab has the number of these shows and opens the list.
import { api } from '#lib/api/client.js';
import type { Show } from '#lib/api/types.js';

class WatchList {
	shows = $state<Show[]>([]);
	/**
	 * The shows that the user took off the list while the list was open. Their rows stay in the
	 * list with a button that puts the show back, so that a wrong click loses nothing.
	 */
	gone = $state<string[]>([]);

	/** The number of the shows on the list */
	get count(): number {
		return this.shows.filter((show) => !this.gone.includes(show.id)).length;
	}

	isGone(show: Show): boolean {
		return this.gone.includes(show.id);
	}

	/** Get the list from the server: it has the correct order and the matches of now */
	async load() {
		try {
			this.shows = await api.watchList();
			this.gone = [];
		} catch (error) {
			console.error('Failed to load the watch list', error);
		}
	}

	/** Keep the list correct after a change of one show */
	note(show: Show) {
		const at = this.shows.findIndex((s) => s.id === show.id);
		const on = show.interest === 1 && !show.owned && !show.dismissed;
		if (on) {
			this.gone = this.gone.filter((id) => id !== show.id);
			if (at < 0) {
				this.shows = [...this.shows, show].sort((a, b) => (b.match ?? 0) - (a.match ?? 0));
			}
		} else if (at >= 0 && !this.gone.includes(show.id)) {
			this.shows = this.shows.filter((s) => s.id !== show.id);
		}
	}

	/** The user takes a show off the list in the open list: its row stays, with an Undo button */
	markGone(show: Show) {
		if (!this.gone.includes(show.id)) this.gone = [...this.gone, show.id];
	}

	unmarkGone(show: Show) {
		this.gone = this.gone.filter((id) => id !== show.id);
	}

	/** The list closes: a show that the user took off the list does not come back */
	forgetGone() {
		this.shows = this.shows.filter((show) => !this.gone.includes(show.id));
		this.gone = [];
	}
}

export const watchList = new WatchList();
