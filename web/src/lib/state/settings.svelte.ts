// The theme and the settings of the look. The browser keeps them, with the keys of the old page.
// Each value is also an attribute of the root element (data-theme, data-<key>), so that the
// style sheet can use it: see src/app.html, which sets the attributes before the page shows.

const THEME_KEY = 'rinrikun-theme';
const SETTINGS_KEY = 'rinrikun-settings';

export type Theme = 'light' | 'dark';

/** The settings of the Settings tab. The first option of a setting is its default. */
export const SETTING_OPTIONS = {
	font: ['mixed', 'sans'],
	petals: ['on', 'off'],
	gradient: ['off', 'on']
} as const;

export type SettingKey = keyof typeof SETTING_OPTIONS;
export type SettingValues = { [K in SettingKey]: (typeof SETTING_OPTIONS)[K][number] };

function systemTheme(): Theme {
	return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function savedValues(): SettingValues {
	const values = { font: 'mixed', petals: 'on', gradient: 'off' } as SettingValues;
	try {
		const saved = JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}') || {};
		for (const key of Object.keys(SETTING_OPTIONS) as SettingKey[]) {
			if ((SETTING_OPTIONS[key] as readonly string[]).includes(saved[key])) {
				(values[key] as string) = saved[key];
			}
		}
	} catch {
		// The browser does not permit the storage: the settings have their defaults
	}
	return values;
}

class Settings {
	/** The theme that the page shows now */
	theme = $state<Theme>((document.documentElement.dataset.theme as Theme) || systemTheme());
	values = $state<SettingValues>(savedValues());

	constructor() {
		// The page follows the system until the user selects a theme
		matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
			if (!document.documentElement.dataset.theme) this.theme = systemTheme();
		});
	}

	toggleTheme() {
		this.theme = this.theme === 'dark' ? 'light' : 'dark';
		document.documentElement.dataset.theme = this.theme;
		try {
			localStorage.setItem(THEME_KEY, this.theme);
		} catch {
			// The theme then stays only until the page closes
		}
	}

	set<K extends SettingKey>(key: K, value: SettingValues[K]) {
		this.values[key] = value;
		document.documentElement.dataset[key] = value;
		try {
			localStorage.setItem(SETTINGS_KEY, JSON.stringify(this.values));
		} catch {
			// The setting then stays only until the page closes
		}
	}

	/** The maps show the match of a show as the brightness of its poster */
	get gradient(): boolean {
		return this.values.gradient === 'on';
	}
}

export const settings = new Settings();
