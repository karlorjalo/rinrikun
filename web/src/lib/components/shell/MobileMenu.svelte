<script lang="ts">
	// The menu of a small screen. A small screen has no tab bar: a round button floats at the
	// bottom right of the window, and it opens the list of the tabs above it. A large screen does
	// not show the button.
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import * as DropdownMenu from '#lib/components/ui/dropdown-menu/index.js';
	import { TABS, type TabRoute } from '#lib/nav.js';
	import { tabSearch } from '#lib/state/tab-search.svelte.js';

	let open = $state(false);

	async function show(route: TabRoute) {
		await goto(resolve(route) + tabSearch.of(route));
		// The user opened the menu from some place of a long page. The new tab starts at its top.
		window.scrollTo(0, 0);
	}
</script>

<DropdownMenu.Root bind:open>
	<DropdownMenu.Trigger
		class="fixed right-4 bottom-4 z-[80] flex size-[54px] items-center justify-center rounded-full bg-rose text-rose-ink shadow-control transition-colors duration-150 hover:bg-[color-mix(in_srgb,var(--accent)_86%,#000)] aria-expanded:bg-[color-mix(in_srgb,var(--accent)_86%,#000)] min-[761px]:hidden"
		aria-label="Menu"
		title="Menu"
	>
		<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
			<path
				d="M4 6.5h16M4 12h16M4 17.5h16"
				fill="none"
				stroke="currentColor"
				stroke-width="2"
				stroke-linecap="round"
			/>
		</svg>
	</DropdownMenu.Trigger>
	<DropdownMenu.Content side="top" align="end" sideOffset={12} class="min-w-[216px]" aria-label="Tabs">
		{#each TABS as tab (tab.route)}
			{@const current = page.route.id === tab.route}
			<DropdownMenu.Item
				onSelect={() => show(tab.route)}
				aria-current={current ? 'page' : undefined}
				class={current ? 'bg-muted font-semibold text-rose' : ''}
			>
				{tab.label}
			</DropdownMenu.Item>
		{/each}
	</DropdownMenu.Content>
</DropdownMenu.Root>
