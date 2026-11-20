<script lang="ts">
	import './layout.css';
	import favicon from '#lib/assets/favicon.svg';
	import HintLayer from '#lib/components/HintLayer.svelte';
	import Brand from '#lib/components/shell/Brand.svelte';
	import LoadingBar from '#lib/components/shell/LoadingBar.svelte';
	import MobileMenu from '#lib/components/shell/MobileMenu.svelte';
	import Petals from '#lib/components/shell/Petals.svelte';
	import DetailDialog from '#lib/components/show/DetailDialog.svelte';
	import TabBar from '#lib/components/shell/TabBar.svelte';
	import ThemeToggle from '#lib/components/shell/ThemeToggle.svelte';
	import * as Tooltip from '#lib/components/ui/tooltip/index.js';
	import { appear } from '#lib/motion.js';
	import { library } from '#lib/state/library.svelte.js';
	import { progress } from '#lib/state/progress.svelte.js';
	import { app } from '#lib/state/progressive.svelte.js';
	import { settings } from '#lib/state/settings.svelte.js';
	import { tabSearch } from '#lib/state/tab-search.svelte.js';
	import { tierHelp } from '#lib/state/tier-help.svelte.js';
	import { afterNavigate, invalidate } from '$app/navigation';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();

	// The browser has its own preferences: the first render used the values of the cookies
	onMount(() => {
		settings.start();
		tierHelp.start();
		// The first page is on the screen: the next pages can show a long list in parts
		app.started = true;
	});

	// Each tab keeps its query: see tab-search.svelte.ts
	afterNavigate(({ to }) => {
		if (to) tabSearch.note(to.route.id, to.url.search);
	});

	// A change of a show changes the numbers of the Profile tab and the lists of the Ratings tab.
	// Their load functions depend on "rinrikun:data": get them again a short time after the last change.
	// The other tabs keep their lists: a removed recommendation keeps its place.
	let seen = -1;
	let timer: ReturnType<typeof setTimeout> | undefined;
	$effect(() => {
		const version = library.version;
		if (seen >= 0 && version !== seen) {
			clearTimeout(timer);
			timer = setTimeout(() => progress.track(invalidate('rinrikun:data')), 1500);
		}
		seen = version;
	});
</script>

<svelte:head>
	<link rel="icon" type="image/svg+xml" href={favicon} />
</svelte:head>

<Tooltip.Provider delayDuration={120}>
	<LoadingBar />
	<Petals />
	<header
		class="relative z-[1] mx-auto max-w-[1040px] px-4 pt-[26px] pb-3 text-center max-[680px]:px-3.5 max-[680px]:pt-6 max-[680px]:pb-2"
	>
		<div class="relative mb-4 flex items-center justify-center">
			<Brand />
			<ThemeToggle />
		</div>
		<TabBar />
	</header>
	<main
		class="relative z-[1] mx-auto max-w-[1040px] px-4 pt-[22px] pb-[60px] max-[760px]:pb-[88px] max-[680px]:px-3 max-[680px]:pt-4"
	>
		<!-- A new tab fades in. A new query of the same tab (a filter, a new show of the Similar
		     tab) keeps the page: only its new items fade in (ShowCard). -->
		{#key page.route.id}
			<div in:appear>{@render children()}</div>
		{/key}
	</main>
	<MobileMenu />
	<DetailDialog />
	<HintLayer />
</Tooltip.Provider>
