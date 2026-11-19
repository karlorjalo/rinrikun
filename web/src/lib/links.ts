// The addresses of the tabs with their state. The server renders a tab from its address, thus
// the seed of a list, the show of the Similar tab and the filters are in the query.
import { resolve } from '$app/paths';

/** The Similar tab for a show */
export const similarHref = (id: string, count?: string) =>
	`${resolve('/similar')}?id=${encodeURIComponent(id)}${count && count !== '24' ? `&count=${count}` : ''}`;

/** The Recommendations tab with a show as the seed */
export const seedHref = (id: string) => `${resolve('/recommendations')}?seed=${encodeURIComponent(id)}`;

/** The Ratings tab for one tier */
export const tierHref = (tier: string) => `${resolve('/ratings')}?tier=${tier}`;

/**
 * The address of the page with other query values. A value of null, or the default value of the
 * parameter, removes the parameter: the address stays short.
 */
export function withQuery(url: { href: string }, changes: Record<string, string | null>, defaults: Record<string, string> = {}): string {
	const next = new URL(url.href);
	for (const [key, value] of Object.entries(changes)) {
		if (value === null || value === '' || value === defaults[key]) next.searchParams.delete(key);
		else next.searchParams.set(key, value);
	}
	return next.pathname + next.search;
}

/** The options of `goto` for a change of a filter: no new entry in the history, no scroll, the focus stays */
export const FILTER_NAVIGATION = { replaceState: true, noScroll: true, keepFocus: true } as const;
