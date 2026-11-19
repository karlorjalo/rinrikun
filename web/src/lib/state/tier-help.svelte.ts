// The help card "Which tier?" of the Review tab and of the Ratings tab. The user can close the
// card. The browser keeps this (see preferences.ts), and the two cards have the same state. The
// server renders the card with the state of the cookie.
import { page } from '$app/state';
import { TIER_HELP_KEY, loadPreference, savePreference } from '#lib/preferences.js';

class TierHelp {
	private ready = $state(false);
	private own = $state(true);

	/** Read the state in the browser. The root layout calls it when the page starts. */
	start() {
		this.own = loadPreference(TIER_HELP_KEY) !== 'closed';
		this.ready = true;
	}

	get open(): boolean {
		return this.ready ? this.own : (page.data.preferences?.tierHelp ?? true);
	}

	set(open: boolean) {
		this.own = open;
		this.ready = true;
		savePreference(TIER_HELP_KEY, open ? 'open' : 'closed');
	}
}

export const tierHelp = new TierHelp();
