// The data of the Discover tab: the cards of the deck, the numbers of the answers, and the watch
// list. The server renders the first card.
//
// This load function runs on the server for the first visit, and in the browser for the next
// visits. The browser keeps its deck while the deck has a card (see `kept`): then the function
// draws no cards, and the user comes back to the same card.
import { browser } from '$app/env';
import { makeApi } from '#lib/api/client.js';
import { fromApi } from '#lib/api/load.js';
import type { InterestCounts, Show } from '#lib/api/types.js';
import { kept } from '#lib/state/discover.svelte.js';
import type { PageLoad } from './$types';

/** The number of cards of one draw */
const BATCH = 12;

export const load: PageLoad = async ({ fetch }) => {
	const api = makeApi(fetch);
	return fromApi(async (): Promise<{ cards: Show[] | null; counts: InterestCounts | null; watch: Show[] }> => {
		if (browser && kept.deck?.show) return { cards: null, counts: null, watch: await api.watchList() };
		const [deck, watch] = await Promise.all([api.discover(BATCH), api.watchList()]);
		return { cards: deck.cards, counts: deck.counts, watch };
	});
};
