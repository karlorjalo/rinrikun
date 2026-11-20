// The keys of a page, such as the keys of a deck.
import type { Tier } from './api/types.js';

/**
 * Tell if a key of the page must do nothing: a window, a menu or a list is open, the user types
 * in a field, or the key is a command of the browser (with Ctrl, Alt or the command key). Each
 * open window, menu and list of the components has one of these roles.
 */
export function keysBusy(event: KeyboardEvent): boolean {
	if (event.ctrlKey || event.metaKey || event.altKey) return true;
	if (document.querySelector('[role="dialog"], [role="menu"], [role="listbox"]')) return true;
	const element = document.activeElement;
	return element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement;
}

const TIER_OF_NUMBER: Record<string, Tier> = { '1': 'D', '2': 'C', '3': 'B', '4': 'A', '5': 'S' };

/** The tier that a key gives in a deck: the numbers 1 to 5 (D to S), or the letter of the tier */
export function tierOfKey(event: KeyboardEvent): Tier | null {
	const key = event.key.toUpperCase();
	if ('SABCD'.includes(key) && key.length === 1) return key as Tier;
	// `code` is the key of the keyboard: it is correct also with a layout that has no digits in its first level
	const digit = /^(?:Digit|Numpad)([1-5])$/.exec(event.code || '')?.[1] ?? key;
	return TIER_OF_NUMBER[digit] ?? null;
}
