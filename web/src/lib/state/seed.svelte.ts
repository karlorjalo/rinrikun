// The show that the user selected as the start of a list of recommendations: the seed. The
// detail window and a card set it, and the Recommendations tab reads it.
import type { Show } from '#lib/api/types.js';

class Seeds {
	/** The seed of the list of recommendations, or null for the list from the taste of the user */
	recommend = $state<Pick<Show, 'id' | 'title' | 'title_native'> | null>(null);
}

export const seeds = new Seeds();
