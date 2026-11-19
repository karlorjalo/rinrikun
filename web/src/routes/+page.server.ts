// The data of the Profile tab: the numbers of the card. The map gets its data in the browser:
// the map data is large, and the canvas draws it there.
import { makeApi } from '#lib/api/client.js';
import { fromApi } from '#lib/api/load.js';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, depends }) => {
	depends('rinrikun:data');
	const api = makeApi(fetch);
	return fromApi(async () => {
		const [profile, recLog, interest] = await Promise.all([
			api.profile(),
			api.recLog().catch(() => null),
			api.interestResults().catch(() => null)
		]);
		return { profile, recLog, interest };
	});
};
