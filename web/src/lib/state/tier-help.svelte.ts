// The help card "Which tier?" of the Review tab and of the Ratings tab. The user can close the
// card. The browser keeps this, and the two cards have the same state.
const KEY = 'rinrikun-tier-help';

function saved(): boolean {
	try {
		return localStorage.getItem(KEY) !== 'closed';
	} catch {
		return true;
	}
}

class TierHelp {
	open = $state(saved());

	set(open: boolean) {
		this.open = open;
		try {
			localStorage.setItem(KEY, open ? 'open' : 'closed');
		} catch {
			// The state then stays only until the page closes
		}
	}
}

export const tierHelp = new TierHelp();
