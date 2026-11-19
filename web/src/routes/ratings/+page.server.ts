// The data of the Ratings tab: the rated shows, the shows marked by hand, and the removed shows.
// The filters are in the query of the address; the page filters the lists, thus a new filter
// needs no new request.
import { makeApi } from '#lib/api/client.js';
import { fromApi } from '#lib/api/load.js';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, depends }) => {
	depends('rinrikun:data');
	const api = makeApi(fetch);
	return fromApi(async () => {
		const [rated, manual, dismissed] = await Promise.all([api.ratings(), api.watched(), api.dismissed()]);
		return { rated, manual, dismissed };
	});
};
