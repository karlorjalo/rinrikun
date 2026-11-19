<script lang="ts">
	// The tab bar of a large screen. A small screen has the menu button in its place: the seven
	// tabs are wider than a phone screen.
	import { page } from '$app/state';
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
		<a
			href={resolve(tab.route) + tabSearch.of(tab.route)}
			aria-current={current ? 'page' : undefined}
			class="rounded-full px-[18px] py-1.5 text-[13.5px] font-medium text-muted-foreground no-underline transition-colors duration-150 hover:text-foreground aria-[current=page]:bg-card aria-[current=page]:font-semibold aria-[current=page]:text-foreground aria-[current=page]:shadow-[inset_0_0_0_1px_var(--border)]"
		>
			{tab.label}
		</a>
	{/each}
</nav>
