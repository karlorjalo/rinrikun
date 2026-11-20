// The requests of the page to the server. Each function is one endpoint of the API.
import type {
	InterestCounts,
	InterestResults,
	Kinds,
	MapBase,
	MapUser,
	Pictures,
	Profile,
	RecLog,
	Show,
	StorySteps,
	Tier,
	Title
} from './types';

/** The server answered with an error. */
export class ApiError extends Error {
	constructor(
		public status: number,
		public path: string
	) {
		super(`the server answered ${status} for ${path}`);
	}
}

const id = (value: string) => encodeURIComponent(value);

export interface RecommendOptions {
	k?: number;
	seed?: string | null;
	variety?: boolean;
	sequels?: boolean;
	kinds: Kinds;
	links: boolean;
}

/**
 * The API with a given fetch function. A load function on the server gives its own `fetch`: it
 * sends the request to the API server (see hooks.server.ts). The page in the browser uses `api`.
 */
export function makeApi(fetcher: typeof fetch) {
	async function request<T>(path: string, init?: RequestInit): Promise<T> {
		const response = await fetcher(path, init);
		if (!response.ok) throw new ApiError(response.status, path);
		return response.json() as Promise<T>;
	}

	function send<T>(path: string, body: unknown): Promise<T> {
		return request<T>(path, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(body)
		});
	}

	return {
		profile: () => request<Profile>('/api/profile'),
		titles: () => request<Title[]>('/api/shows'),
		show: (show: string) => request<Show>(`/api/show/${id(show)}`),

		ratings: () => request<Show[]>('/api/ratings'),
		watched: () => request<Show[]>('/api/watched'),
		dismissed: () => request<Show[]>('/api/dismissed'),
		reviewQueue: (unratedOnly: boolean) => request<Show[]>(`/api/review-queue?unrated_only=${unratedOnly}`),

		/** Give a show a tier. A tier of null takes the tier away. */
		setTier: (show: string, tier: Tier | null) =>
			tier
				? send<{
						id: string;
						tier: Tier | null;
						weight: number;
						ids: string[];
					}>('/api/weights', {
						id: show,
						tier
					})
				: request<{ id: string; tier: null; weight: number; ids: string[] }>(`/api/weights?id=${id(show)}`, {
						method: 'DELETE'
					}),
		setWatched: (show: string, watched: boolean) =>
			send<{ id: string; watched: boolean; owned: number }>('/api/watched', {
				id: show,
				watched
			}),
		setDismissed: (show: string, dismissed: boolean) =>
			send<{ id: string; dismissed: boolean }>('/api/dismissed', {
				id: show,
				dismissed
			}),

		/** The cards of the Discover deck, and the numbers of the answers. */
		discover: (count: number) => request<{ cards: Show[]; counts: InterestCounts }>(`/api/discover?count=${count}`),
		/** The watch list: the shows with the answer "interested" that the user does not have. */
		watchList: () => request<Show[]>('/api/interest'),
		interestResults: () => request<InterestResults>('/api/interest/results'),
		/**
		 * Save the answer of the user for a show: true = interested, false = not interested,
		 * null = no answer. `source` is "deck" for the Discover deck and "page" for a button of a page.
		 */
		setInterest: (show: string, value: boolean | null, source: 'deck' | 'page') =>
			send<{
				id: string;
				interest: number | null;
				dismissed: number;
				counts: InterestCounts;
			}>('/api/interest', { id: show, value, source }),
		/** The pictures of some shows, by the id of the show. A show without pictures is not in the answer. */
		frames: (shows: string[]) => request<Record<string, Pictures>>(`/api/frames?ids=${id(shows.join(','))}`),

		similar: (show: string, k: number) => request<Show[]>(`/api/similar?id=${id(show)}&k=${k}`),
		/** A list of recommendations. The server keeps a log of each list without a seed. */
		recommend: (o: RecommendOptions) => {
			const query = new URLSearchParams({
				k: String(o.k ?? 40),
				mode: o.variety ? 'diverse' : 'hybrid',
				kinds: o.kinds,
				links: String(o.links),
				new_only: String(!o.sequels)
			});
			if (o.seed) query.set('seed', o.seed);
			return request<Show[]>(`/api/recommend?${query}`);
		},
		recommendSteps: (o: { k?: number; kinds: Kinds; links: boolean; sequels?: boolean }) =>
			request<StorySteps>(
				`/api/recommend/steps?k=${o.k ?? 40}&new_only=${!o.sequels}&kinds=${o.kinds}&links=${o.links}`
			),
		recLog: () => request<RecLog>('/api/rec-log'),

		/** The fixed part of the map. It is large: the browser keeps it, and the server answers 304 while it is the same. */
		vectorMap: () => request<MapBase>('/api/vector-map'),
		/** The shows of the user on the map */
		mapUser: () => request<MapUser>('/api/vector-map/user'),
		/** The match of each point of the map, in the order of the points */
		mapMatch: () => request<(number | null)[]>('/api/vector-map/match')
	};
}

export type Api = ReturnType<typeof makeApi>;

/** The API for the page in the browser */
export const api = makeApi((input, init) => fetch(input, init));
