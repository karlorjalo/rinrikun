// The theme and the settings of the look. Each value is also an attribute of the root element
// (data-theme, data-<key>), so that the style sheet can use it. The server sets the attributes
// from the cookies (hooks.server.ts), and the browser keeps the values: see preferences.ts.
//
// The server renders a page with the values of the cookies. In the browser the page starts with
// the same values, thus the first render in the browser is equal to the render of the server.
// Then `start` reads the values of the browser.
import { page } from '$app/state';
import {
	SETTINGS_KEY,
	THEME_KEY,
	defaultSettings,
	loadPreference,
	parseSettings,
	parseTheme,
	savePreference,
	type SettingKey,
	type SettingValues,
	type Theme
} from '#lib/preferences.js';

export { SETTING_OPTIONS, type SettingKey, type SettingValues, type Theme } from '#lib/preferences.js';

class Settings {
	/** The values of the browser are there */
	ready = $state(false);
	private own = $state<SettingValues>(defaultSettings());
	/** The theme that the user selected, or null: the page then follows the system */
	private ownTheme = $state<Theme | null>(null);
	private systemDark = $state(false);

	/** Read the values in the browser. The root layout calls it when the page starts. */
	start() {
		if (this.ready) return;
		this.own = parseSettings(loadPreference(SETTINGS_KEY));
		this.ownTheme = parseTheme(loadPreference(THEME_KEY));
		const media = matchMedia('(prefers-color-scheme: dark)');
		this.systemDark = media.matches;
		media.addEventListener('change', () => (this.systemDark = media.matches));
		const root = document.documentElement;
		if (this.ownTheme) root.dataset.theme = this.ownTheme;
		for (const [key, value] of Object.entries(this.own)) root.dataset[key] = value;
		this.ready = true;
	}

	/** The values that the page shows */
	get values(): SettingValues {
		return this.ready ? this.own : (page.data.preferences?.settings ?? defaultSettings());
	}

	/** The theme that the page shows now */
	get theme(): Theme {
		if (!this.ready) return page.data.preferences?.theme ?? 'light';
		return this.ownTheme ?? (this.systemDark ? 'dark' : 'light');
	}

	toggleTheme() {
		const next: Theme = this.theme === 'dark' ? 'light' : 'dark';
		this.ownTheme = next;
		document.documentElement.dataset.theme = next;
		savePreference(THEME_KEY, next);
	}

	set<K extends SettingKey>(key: K, value: SettingValues[K]) {
		this.own = { ...this.own, [key]: value };
		document.documentElement.dataset[key] = value;
		savePreference(SETTINGS_KEY, JSON.stringify(this.own));
	}

	/** The maps show the match of a show as the brightness of its poster */
	get gradient(): boolean {
		return this.values.gradient === 'on';
	}
}

export const settings = new Settings();
