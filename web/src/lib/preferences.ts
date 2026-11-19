// The preferences of the user: the theme, the settings of the Settings tab, the help card of the
// tiers, and the formula of the recommendations. The browser keeps each of them in a cookie, so
// that the server can render the page with them, and in the local storage with the keys of the
// old page, so that the two pages have the same preferences.

export const THEME_KEY = 'rinrikun-theme';
export const SETTINGS_KEY = 'rinrikun-settings';
export const TIER_HELP_KEY = 'rinrikun-tier-help';
export const FORMULA_KEY = 'rinrikun-formula';
export const LINKS_KEY = 'rinrikun-links';

export type Theme = 'light' | 'dark';

/** The settings of the Settings tab. The first option of a setting is its default. */
export const SETTING_OPTIONS = {
	font: ['mixed', 'sans'],
	petals: ['on', 'off'],
	gradient: ['off', 'on']
} as const;

export type SettingKey = keyof typeof SETTING_OPTIONS;
export type SettingValues = { [K in SettingKey]: (typeof SETTING_OPTIONS)[K][number] };

export function defaultSettings(): SettingValues {
	return { font: 'mixed', petals: 'on', gradient: 'off' };
}

/** The theme from the text of a cookie, or null if the user did not select one: the page then follows the system */
export function parseTheme(text: string | null | undefined): Theme | null {
	return text === 'light' || text === 'dark' ? text : null;
}

/** The settings from the JSON text of a cookie. A value that is not an option gets its default. */
export function parseSettings(text: string | null | undefined): SettingValues {
	const values = defaultSettings();
	try {
		const saved = JSON.parse(text || '{}') || {};
		for (const key of Object.keys(SETTING_OPTIONS) as SettingKey[]) {
			if ((SETTING_OPTIONS[key] as readonly string[]).includes(saved[key])) {
				(values[key] as string) = saved[key];
			}
		}
	} catch {
		// A cookie that is not JSON: the defaults
	}
	return values;
}

/** The attributes of the root element for the style sheet: data-theme and data-<setting> */
export function rootAttributes(theme: Theme | null, values: SettingValues): string {
	const parts = Object.entries(values).map(([key, value]) => `data-${key}="${value}"`);
	if (theme) parts.unshift(`data-theme="${theme}"`);
	return parts.join(' ');
}

/** The preferences that the server reads from the cookies, for the first render of a page */
export interface Preferences {
	theme: Theme | null;
	settings: SettingValues;
	/** The help card "Which tier?" is open */
	tierHelp: boolean;
}

export function parsePreferences(get: (key: string) => string | null | undefined): Preferences {
	return {
		theme: parseTheme(get(THEME_KEY)),
		settings: parseSettings(get(SETTINGS_KEY)),
		tierHelp: get(TIER_HELP_KEY) !== 'closed'
	};
}

/** Read a cookie in the browser */
export function readCookie(key: string): string | null {
	for (const part of document.cookie.split(';')) {
		const [name, ...rest] = part.trim().split('=');
		if (name === key) {
			try {
				return decodeURIComponent(rest.join('='));
			} catch {
				return null;
			}
		}
	}
	return null;
}

/**
 * Keep a preference in the browser: in a cookie for the server, and in the local storage for the
 * old page. The cookie is for the full site, thus the old page and the new page share it.
 */
export function savePreference(key: string, value: string) {
	document.cookie = `${key}=${encodeURIComponent(value)}; path=/; max-age=31536000; samesite=lax`;
	try {
		localStorage.setItem(key, value);
	} catch {
		// The browser does not permit the storage: the cookie keeps the value
	}
}

/**
 * Read a preference in the browser: the cookie, or the value that the old page keeps. A value
 * from the old page also goes into the cookie, so that the server knows it the next time.
 */
export function loadPreference(key: string): string | null {
	const cookie = readCookie(key);
	let stored: string | null = null;
	try {
		stored = localStorage.getItem(key);
	} catch {
		// No storage
	}
	if (stored !== null && stored !== cookie) {
		// The old page changed the value after the last visit of the new page
		savePreference(key, stored);
		return stored;
	}
	return cookie;
}
