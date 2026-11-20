// Small functions that make the texts of a show.
import type { Show, Tier } from './api/types.js';

export const TIERS: Tier[] = ['S', 'A', 'B', 'C', 'D'];

/** The two titles of a show: the Japanese title first, and the romaji title below it if it is different. */
export function displayTitles(show: { title?: string | null; title_native?: string | null }): {
	main: string;
	sub: string | null;
} {
	const native = (show.title_native || '').trim();
	const romaji = (show.title || '').trim();
	if (native) {
		const different = romaji && romaji.toLowerCase() !== native.toLowerCase();
		return { main: native, sub: different ? romaji : null };
	}
	return { main: romaji || 'Unknown', sub: null };
}

/**
 * The match of a show as text. The match tells how near the show is to the taste of the user:
 * it is the part of the franchises that the user does not have, which are less near. A match
 * near 100 has one decimal, because many good shows are between 99 and 100.
 */
export function formatMatch(match: number | null | undefined): string | null {
	if (match == null) return null;
	return match >= 99.95 ? '100' : match >= 99 ? match.toFixed(1) : String(Math.round(match));
}

/** The text of the tooltip of a match */
export function matchAbout(show: Pick<Show, 'owned' | 'match'>): string {
	const text = formatMatch(show.match);
	return show.owned
		? `Without this franchise in your list, this show would be nearer to your taste than ${text}% of the franchises that you do not have`
		: `This show is nearer to your taste than ${text}% of the franchises that you do not have`;
}

export const GUESS_ABOUT =
	'A guess of the tier that you will give, from the tags of the shows that you rated. ' +
	'The guess is weak: in a test, 64% of the shows with the highest guesses were S or A, and 36% of the shows with the lowest guesses.';

/** AniList has a small poster and a larger poster of each show. A large picture uses the larger file. */
export function largePoster(url: string | null | undefined): string | null {
	return url ? url.replace('/cover/small/', '/cover/medium/') : (url ?? null);
}

/** The crowd score with one decimal */
export function formatScore(score: number | null | undefined): string | null {
	return score != null ? Number(score).toFixed(1) : null;
}

const escapeHtml = (text: string) =>
	text.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);

/**
 * The synopsis of a show as safe HTML. The text from AniList has line breaks and the tags <br>
 * and <i>. All other tags stay text.
 */
export function overviewHtml(text: string | null | undefined): string {
	if (!text) return '';
	return escapeHtml(text)
		.replace(/&lt;br\s*\/?&gt;/gi, '<br>')
		.replace(/&lt;i&gt;/gi, '<i>')
		.replace(/&lt;\/i&gt;/gi, '</i>')
		.replace(/\n\n+/g, '<br><br>')
		.replace(/\n/g, '<br>');
}

/** "1 show", "2 shows" */
export function countOf(count: number, one: string, many = one + 's'): string {
	return `${count.toLocaleString('en-US')} ${count === 1 ? one : many}`;
}
