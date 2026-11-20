// The query of the address of each tab, the last time the user had the tab open. The filters
// of a tab, its seed and its show are in the address. The links of the tab bar and of the menu
// add the query again, thus a tab keeps its state when the user opens a different tab.
class TabSearch {
	private search = $state<Record<string, string>>({});

	/** Remember the query of a tab. The root layout calls it after each navigation. */
	note(route: string | null, search: string) {
		if (route) this.search = { ...this.search, [route]: search };
	}

	/** The query for the link of a tab: "" or "?..." */
	of(route: string): string {
		return this.search[route] ?? '';
	}
}

export const tabSearch = new TabSearch();
