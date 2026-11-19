// The filters of the Ratings tab. They stay when the user opens a different tab, and the Profile
// tab sets the tier when the user clicks the number of a tier.
import type { Tier } from '#lib/api/types.js';

export type RatingsSource = 'rated' | 'manual' | 'dismissed';
export type RatingsSort = 'tier' | 'match' | 'score' | 'title';

class RatingsView {
	tier = $state<Tier | 'all'>('all');
	source = $state<RatingsSource>('rated');
	sort = $state<RatingsSort>('tier');
}

export const ratingsView = new RatingsView();
