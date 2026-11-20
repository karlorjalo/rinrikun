<script lang="ts">
	// The tab bar of a large screen. A small screen has the menu button in its place: the seven
	// tabs are wider than a phone screen.
	//
	// A tab gets its data when the pointer is on its link, thus the data is often there at the
	// click. The Recommendations tab gets it only at the press of the button: each list without a
	// seed goes into the log of the recommendations, and a list that the user did not open must
	// not be in that log. While a tab loads, its link has the dark text at once (data-pending).
	import { navigating, page } from '$app/state';
	import { resolve } from '$app/paths';
	import { TABS } from '#lib/nav.js';
	import { tabSearch } from '#lib/state/tab-search.svelte.js';
</script>

<nav
	class="inline-flex justify-center gap-[3px] rounded-full border bg-[color-mix(in_srgb,var(--card)_92%,var(--hover))] p-1 max-[760px]:hidden"
	aria-label="Tabs"
>
	{#each TABS as tab (tab.route)}
		{@const current = page.route.id === tab.route}
		{@const pending = !current && navigating.to?.route.id === tab.route}
		<a
			href={resolve(tab.route) + tabSearch.of(tab.route)}
			data-sveltekit-preload-data={tab.route === '/recommendations' ? 'tap' : 'hover'}
			aria-current={current ? 'page' : undefined}
			data-pending={pending ? '' : undefined}
			class="rounded-full px-[18px] py-1.5 text-[13.5px] font-medium text-muted-foreground no-underline transition-colors duration-150 hover:text-foreground data-pending:text-foreground aria-[current=page]:bg-card aria-[current=page]:font-semibold aria-[current=page]:text-foreground aria-[current=page]:shadow-[inset_0_0_0_1px_var(--border)]"
		>
			{tab.label}
		</a>
	{/each}
</nav>
