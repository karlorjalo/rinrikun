// The data of the Similar tab. With a show in the address (?id=...&count=48), the show and its
// similar shows. Without a show, five shows of the user at random, as examples.
import { makeApi } from '#lib/api/client.js';
import { fromApi } from '#lib/api/load.js';
import type { PageServerLoad } from './$types';

/** The number of examples below an empty search box */
const EXAMPLES = 5;

export const load: PageServerLoad = async ({ fetch, url }) => {
	const id = url.searchParams.get('id');
	const count = url.searchParams.get('count') === '48' ? 48 : 24;
	const api = makeApi(fetch);
	return fromApi(async () => {
		if (!id) {
			const mine = (await api.titles()).filter((t) => t.owned && (t.title_native || t.title));
			const examples = [];
			while (examples.length < EXAMPLES && mine.length) {
				const { id, title, title_native } = mine.splice(Math.floor(Math.random() * mine.length), 1)[0];
				examples.push({ id, title, title_native });
			}
			return { show: null, results: [], examples, count };
		}
		const [show, results] = await Promise.all([api.show(id), api.similar(id, count)]);
		return { show, results, examples: [], count };
	});
};
