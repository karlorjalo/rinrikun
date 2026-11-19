// The data of the Recommendations tab: the list, and the seed show of a list with a seed.
//
// The seed and the switches "More variety" and "Sequels" are in the address (?seed=...,
// ?variety=1, ?sequels=1). The formula and the crowd links are preferences in cookies (see
// preferences.ts): the page sets the cookie, then loads the data again ("rinrikun:formula").
// "Format" and "Min score" are in the address too, but this function does not read them: the
// page filters the list, and a new filter needs no new list.
import { makeApi } from '#lib/api/client.js';
import { fromApi } from '#lib/api/load.js';
import { FORMULA_KEY, LINKS_KEY } from '#lib/preferences.js';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, url, cookies, depends }) => {
	depends('rinrikun:formula');
	const kinds = cookies.get(FORMULA_KEY) === 'all' ? 'all' : 'usual';
	const links = cookies.get(LINKS_KEY) !== 'off';
	const seed = url.searchParams.get('seed') || null;
	// A list with a seed is in the order of the similarity to the seed: no variety
	const variety = !seed && url.searchParams.get('variety') === '1';
	const sequels = url.searchParams.get('sequels') === '1';
	const api = makeApi(fetch);
	return fromApi(async () => {
		const [list, seedShow] = await Promise.all([
			api.recommend({ k: 40, seed, variety, sequels, kinds, links }),
			seed ? api.show(seed) : Promise.resolve(null)
		]);
		return { list, seed: seedShow, kinds, links, variety, sequels } as const;
	});
};
