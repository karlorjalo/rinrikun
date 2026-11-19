// The data of the API: the shapes of the answers of the Rust server (server/src/api.rs).

export type Tier = 'S' | 'A' | 'B' | 'C' | 'D';

/** A show of the catalog or of the library, as the lists of the API give it. */
export interface Show {
	id: string;
	/** "library" for a show from Jellyfin, "anilist" for a show of the AniList catalog */
	source: string;
	title: string;
	title_native: string;
	title_english: string | null;
	year: number | null;
	format: string | null;
	genres: string[];
	tags: string[];
	tag_ranks: number[];
	studios: string[];
	overview: string;
	/** The crowd score of AniList, from 0 to 10 */
	score: number | null;
	/** The rating from Jellyfin, for a library show */
	library_score?: number | null;
	/** 1 if the user has the show: it is in the library, or the user marked it as watched */
	owned: number;
	/** 1 if the user marked the show as watched by hand */
	manual_watched: number;
	anilist_id: number | null;
	poster: string | null;
	status: string | null;
	episodes: string | number | null;
	/** The place in the popularity order of AniList: 1 is the most popular anime */
	popularity_place: number | null;
	tier: Tier | null;
	weight: number;
	/** 1 if the show is never a recommendation: the user removed it, or answered "not interested" */
	dismissed: number;
	/** The answer of the Discover deck: 1 interested, 0 not interested, null no answer */
	interest: number | null;
	/** The match in percent: how near the show is to the taste of the user */
	match?: number | null;
	/** The tier that a small model predicts for a show without a tier */
	tier_guess?: Tier | null;
	/** The similarity to the seed show in percent, in a list with a seed */
	similarity?: number;
	shared_tags?: string[];
	/** The liked show that is nearest to this recommendation */
	matched_favorite?: string;
	/** The liked show that AniList users connect to this recommendation */
	linked_favorite?: string;
	/** 1 if the user has a different show of the franchise */
	franchise_owned?: number;
}

/** A show in the list for the search box: only the data that the search needs. */
export interface Title {
	id: string;
	title: string;
	title_native: string;
	year: number | null;
	poster: string | null;
	owned: number;
	manual_watched: number;
	tier: Tier | null;
	weight: number;
	/** The other titles of the show, for the search */
	aka: string[];
}

export interface Profile {
	tier_summary: Record<Tier | 'unrated', number>;
	owned_count: number;
	library_count: number;
	manual_count: number;
	total_count: number;
}

export interface MatchGroup {
	low: number;
	high: number;
	answers: number;
	interested: number;
}

/** The numbers of the Discover deck, for the Profile tab. */
export interface InterestResults {
	answers: number;
	interested: number;
	not_interested: number;
	groups: MatchGroup[];
	model: { pairs: number; auc: number } | null;
	/** The deck draws only from this number of the most popular anime. null: no popularity data. */
	popular: number | null;
}

export interface InterestCounts {
	interested: number;
	not_interested: number;
}

export interface FormulaCounts {
	shown: number;
	added: number;
	removed: number;
}

/** What the user did with the shows that the lists of recommendations gave. */
export interface RecLog {
	since: string | null;
	shown: number;
	added: number;
	unrated: number;
	removed: number;
	tiers: Record<Tier, number>;
	shows: { id: string; title: string; title_native: string; tier: Tier | null; first_seen: string; best_rank: number }[];
	formulas: { links: FormulaCounts; 'no links': FormulaCounts };
}

export interface Frame {
	small: string;
	large: string;
	label: string;
}

/** The pictures of a show: frames of its episodes and of its trailer. */
export interface Pictures {
	frames: Frame[];
	trailer: string | null;
	banner: string | null;
}

export interface MapPoint {
	id: string;
	x: number;
	y: number;
	gx: number;
	gy: number;
	title: string;
	title_native: string;
	year: number | null;
	poster: string | null;
	genres: string[];
	owned: number;
	tier: Tier | null;
	score: number | null;
	aka?: string[];
	/** The match in percent. The page adds it when the match gradient is on: see state/map.svelte.ts. */
	match?: number | null;
}

export interface MapRegion {
	x: number;
	y: number;
	gx: number;
	gy: number;
	label: string;
	count: number;
	level: number;
}

export interface VectorMap {
	center: { x: number; y: number } | null;
	points: MapPoint[];
	regions: MapRegion[];
	cell: { w: number; h: number };
}

export interface StorySteps {
	kinds: string;
	links: boolean;
	k: number;
	info: { shows: number; franchises: number; removed: number; liked: number; rated: number; sources: number };
	steps: { key: string; count: number; points: number[] | null }[];
}

export type Kinds = 'usual' | 'all';
