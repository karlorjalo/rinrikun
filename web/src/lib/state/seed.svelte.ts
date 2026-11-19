// The show that the user selected as the start of a list: the seed of the Recommendations tab,
// and the show of the Similar tab. The detail window and a card set them, and the two tabs read them.
import type { Show } from '#lib/api/types.js';

class Seeds {
	/** The seed of the list of recommendations, or null for the list from the taste of the user */
	recommend = $state<Pick<Show, 'id' | 'title' | 'title_native'> | null>(null);
	/** The show for which the Similar tab shows the nearest shows */
	similar = $state<Pick<Show, 'id' | 'title' | 'title_native' | 'owned' | 'manual_watched'> | null>(null);
}

export const seeds = new Seeds();
