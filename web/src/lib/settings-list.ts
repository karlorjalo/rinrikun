// The settings of the Settings tab: the title of each setting, and the label and a short
// description of each option. The first option of a setting is its default. The values and the
// storage are in state/settings.svelte.ts.
import type { SettingKey } from './state/settings.svelte.js';

export interface SettingOption {
	value: string;
	label: string;
	/** What the picture of the option shows, for a screen reader */
	about: string;
}

export const SETTINGS: { key: SettingKey; title: string; options: SettingOption[] }[] = [
	{
		key: 'font',
		title: 'Typeface',
		options: [
			{ value: 'mixed', label: 'Serif titles', about: 'Serif headings' },
			{ value: 'sans', label: 'Sans only', about: 'Noto Sans JP only' }
		]
	},
	{
		key: 'petals',
		title: 'Petals',
		options: [
			{ value: 'on', label: 'On', about: 'Petals fall' },
			{ value: 'off', label: 'Off', about: 'No petals' }
		]
	},
	{
		key: 'gradient',
		title: 'Match gradient',
		options: [
			{ value: 'off', label: 'Off', about: 'Full brightness' },
			{ value: 'on', label: 'On', about: 'Brighter for a higher match' }
		]
	}
];

/** The brightness of a poster with the lowest match, when the match gradient is on (1 = full) */
export const MATCH_DARK = 0.12;
