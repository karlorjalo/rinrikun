// The titles of all shows, for the search box of the Similar tab. The page gets the list one
// time, when a search box first needs it.
import { api } from '#lib/api/client.js';
import type { Title } from '#lib/api/types.js';
import { searchRank, searchWords, showSearchText } from '#lib/search.js';

class Titles {
	// The list is large and its shows do not change: it is not a deep state
	list = $state.raw<Title[]>([]);
	loaded = $state(false);
	private request: Promise<void> | null = null;
	/** The titles of each show as text for a comparison, by the id of the show */
	private keys = new Map<string, string>();

	load(): Promise<void> {
		this.request ??= api
			.titles()
			.then((list) => {
				this.list = list;
				this.loaded = true;
			})
			.catch((error) => {
				console.error('Failed to load the titles', error);
				this.request = null;
			});
		return this.request;
	}

	/** The shows that have each word of the text in one of their titles, the best first */
	find(value: string, limit: number): Title[] {
		const words = searchWords(value);
		if (!words.length) return [];
		const found: [Title, number, number][] = [];
		this.list.forEach((title, position) => {
			let key = this.keys.get(title.id);
			if (key === undefined) {
				key = showSearchText(title);
				this.keys.set(title.id, key);
			}
			const text = key;
			if (words.every((word) => text.includes(word))) found.push([title, searchRank(text, words, title.owned), position]);
		});
		return found
			.sort((a, b) => a[1] - b[1] || a[2] - b[2])
			.slice(0, limit)
			.map((item) => item[0]);
	}

	/** Some shows of the user at random, as examples below an empty search box */
	examples(count: number): Title[] {
		const mine = this.list.filter((title) => title.owned && (title.title_native || title.title));
		const out: Title[] = [];
		while (out.length < count && mine.length) out.push(mine.splice(Math.floor(Math.random() * mine.length), 1)[0]);
		return out;
	}
}

export const titles = new Titles();
