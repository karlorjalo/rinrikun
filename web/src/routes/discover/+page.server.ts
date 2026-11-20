// The data of the Discover tab: new cards of the deck, the numbers of the answers, and the watch
// list. The server renders the first card.
//
// The browser keeps its deck when the user opens a different tab (see `kept`). When the user
// comes back, the page shows the same card, and the new cards go to the end of the deck.
import { makeApi } from '#lib/api/client.js';
import { fromApi } from '#lib/api/load.js';
import type { PageServerLoad } from './$types';

/** The number of cards of one draw */
const BATCH = 12;

export const load: PageServerLoad = async ({ fetch }) => {
	const api = makeApi(fetch);
	return fromApi(async () => {
		const [deck, watch] = await Promise.all([api.discover(BATCH), api.watchList()]);
		return { cards: deck.cards, counts: deck.counts, watch };
	});
};
