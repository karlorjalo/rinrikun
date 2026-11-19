// The data of the Similar tab. With a show in the address (?id=...&count=48), the show and its
// similar shows. Without a show, five shows of the user at random, as examples.
import { makeApi } from '#lib/api/client.js';
import { fromApi } from '#lib/api/load.js';
import type { PageServerLoad } from './$types';

/** The number of examples below an empty search box */
const EXAMPLES = 5;

type Title = { id: string; title?: string | null; title_native?: string | null };

/** Some items of a list at random */
function pick<T>(items: T[], count: number): T[] {
	const rest = [...items];
	const out: T[] = [];
	while (out.length < count && rest.length) out.push(rest.splice(Math.floor(Math.random() * rest.length), 1)[0]);
	return out;
}

export const load: PageServerLoad = async ({ fetch, url }) => {
	const id = url.searchParams.get('id');
	const count = url.searchParams.get('count') === '48' ? 48 : 24;
	const api = makeApi(fetch);
	return fromApi(async () => {
		if (!id) {
			// The examples come from the rated shows: that list is small (all titles are about 6 MB,
			// which made the tab slow). Only a user without ratings needs the list of all titles.
			const named = (t: Title) => !!(t.title_native || t.title);
			let mine: Title[] = (await api.ratings()).filter(named);
			if (!mine.length) mine = (await api.titles()).filter((t) => t.owned && named(t));
			const examples = pick(mine, EXAMPLES).map(({ id, title, title_native }) => ({ id, title, title_native }));
			return { show: null, results: [], examples, count };
		}
		const [show, results] = await Promise.all([api.show(id), api.similar(id, count)]);
		return { show, results, examples: [], count };
	});
};
