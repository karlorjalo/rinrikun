// What the user does with a show: a tier, "watched", "not interested", "interested". Each
// function sends the change to the server and changes the show object, so that the element that
// shows this object changes at once.
//
// A change of one show changes the match of other shows a little, and it can move a show from
// one list to a different list. Thus each change adds one to `version`. A page that shows a list
// reads `version` and gets its list again a short time after the last change.
import { api } from '#lib/api/client.js';
import type { InterestCounts, Show, Tier } from '#lib/api/types.js';
import { watchList } from './watchlist.svelte.js';

class Library {
	version = $state(0);
	/** The numbers of the answers of the Discover deck */
	counts = $state<InterestCounts>({ interested: 0, not_interested: 0 });

	private changed() {
		this.version += 1;
	}

	async setTier(show: Show, tier: Tier | null) {
		const result = await api.setTier(show.id, tier);
		show.tier = result.tier;
		show.weight = result.weight;
		this.changed();
	}

	/** Mark a show as watched by hand, or take the mark away. A library show has no such mark. */
	async setWatched(show: Show, watched: boolean) {
		const result = await api.setWatched(show.id, watched);
		show.manual_watched = watched ? 1 : 0;
		show.owned = result.owned;
		if (!watched) show.tier = null;
		watchList.note(show);
		this.changed();
	}

	/** Remove a show from the recommendations, or put it back. A removed show has no answer of the deck. */
	async setDismissed(show: Show, dismissed: boolean) {
		await api.setDismissed(show.id, dismissed);
		show.dismissed = dismissed ? 1 : 0;
		if (dismissed || show.interest === 0) show.interest = null;
		watchList.note(show);
		this.changed();
	}

	/**
	 * Save the answer of the user for a show: true = interested, false = not interested, null = no
	 * answer. `source` is "deck" for the Discover deck and "page" for a button of a page.
	 */
	async setInterest(show: Show, value: boolean | null, source: 'deck' | 'page') {
		const result = await api.setInterest(show.id, value, source);
		show.interest = result.interest;
		show.dismissed = result.dismissed;
		this.counts = result.counts;
		watchList.note(show);
		this.changed();
	}

	/** Get the match of a show again, after a change that can move it */
	async refresh(show: Show) {
		try {
			const fresh = await api.show(show.id);
			show.match = fresh.match;
			show.tier_guess = fresh.tier_guess;
		} catch {
			// The show keeps its old match
		}
	}
}

export const library = new Library();
