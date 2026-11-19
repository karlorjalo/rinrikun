// The tabs of the app. The tab bar of a large screen and the menu of a small screen use this
// one list, thus the two always have the same tabs.
export const TABS = [
	{ route: '/', label: 'Profile' },
	{ route: '/review', label: 'Review' },
	{ route: '/discover', label: 'Discover' },
	{ route: '/ratings', label: 'Ratings' },
	{ route: '/similar', label: 'Similar' },
	{ route: '/recommendations', label: 'Recommendations' },
	{ route: '/settings', label: 'Settings' }
] as const;

export type TabRoute = (typeof TABS)[number]['route'];
