// The Similar tab: the show that the user selected, and the shows that are most similar to it.
// The state stays when the user opens a different tab. The detail window sets the show with its
// button "Find similar".
import { api } from '#lib/api/client.js';
import type { Show } from '#lib/api/types.js';

/** The data of the selected show that the tab needs. A show of a list and a title of the search have it. */
export type SimilarSeed = Pick<Show, 'id' | 'title' | 'title_native' | 'owned' | 'manual_watched'>;

class SimilarView {
	show = $state<SimilarSeed | null>(null);
	results = $state<Show[]>([]);
	/** "unowned" hides the shows that the user has */
	filter = $state<'all' | 'unowned'>('all');
	/** The number of the results, as text: it is the value of a group of buttons */
	count = $state<'24' | '48'>('24');
	loaded = $state(false);
	/** The number of the last request. An answer of an older request does not change the list. */
	private request = 0;

	/** Select a show and get its similar shows */
	async run(show: SimilarSeed) {
		this.show = show;
		this.loaded = false;
		await this.load();
	}

	async load() {
		const show = this.show;
		if (!show) return;
		const request = ++this.request;
		let results: Show[] = [];
		try {
			results = await api.similar(show.id, Number(this.count));
		} catch (error) {
			console.error('Failed to load the similar shows', error);
		}
		if (request !== this.request) return;
		this.results = results;
		this.loaded = true;
	}
}

export const similarView = new SimilarView();
