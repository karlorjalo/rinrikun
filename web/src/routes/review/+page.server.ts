// The data of the Review tab: the queue of the mode in the address (?mode=all, or the shows
// without a tier), and the numbers of the title row. The server renders the first card.
import { makeApi } from '#lib/api/client.js';
import { fromApi } from '#lib/api/load.js';
import type { ReviewData } from '#lib/state/review.svelte.js';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, url }): Promise<ReviewData> => {
	const mode = url.searchParams.get('mode') === 'all' ? 'all' : 'unrated';
	const api = makeApi(fetch);
	return fromApi(async () => {
		const [queue, profile] = await Promise.all([api.reviewQueue(mode === 'unrated'), api.profile()]);
		const s = profile.tier_summary;
		const rated = s.S + s.A + s.B + s.C + s.D;
		return { mode, queue, rated, total: rated + s.unrated };
	});
};
