// The search for a title. The search box of the Similar tab and the search box of the map use it.

/**
 * The text of a title for a comparison: one form for each character, small letters, and no
 * spaces or punctuation. Thus "re zero" finds "Re:Zero", and full-width letters find half-width
 * letters.
 */
export function searchText(text: string | null | undefined): string {
	return (text || '')
		.normalize('NFKC')
		.toLowerCase()
		.replace(/[\s\p{P}\p{S}]+/gu, '');
}

/** The words of the text of a search, each as text for a comparison */
export function searchWords(value: string | null | undefined): string[] {
	return (value || '').split(/\s+/).map(searchText).filter(Boolean);
}

/**
 * All titles of a show as text for a comparison, with one title in each line. `aka` has the
 * titles that the page does not show: the English title, and for a show of the library the
 * titles of its AniList entries. A show of the library has only its title from Jellyfin, which
 * is in one language. Without `aka` a search in a different language does not find it.
 */
export function showSearchText(show: { title?: string | null; title_native?: string | null; aka?: string[] }): string {
	return [show.title, show.title_native, ...(show.aka || [])].map(searchText).filter(Boolean).join('\n');
}

/**
 * The place of a found show in the results: a show with a title that starts with the first word
 * is first, then the shows of the user. A lower number is a better place.
 */
export function searchRank(text: string, words: string[], owned: unknown): number {
	const starts = text.startsWith(words[0]) || text.includes(`\n${words[0]}`);
	return (starts ? 0 : 2) + (owned ? 0 : 1);
}

/** One Latin letter finds too many shows. One Japanese character can be a full word. */
export function longEnough(value: string): boolean {
	const text = value.trim();
	// eslint-disable-next-line no-control-regex -- the range of the ASCII characters
	return searchWords(text).length > 0 && !(text.length < 2 && /^[\x00-\x7f]*$/.test(text));
}
