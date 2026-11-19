<script lang="ts">
	import './layout.css';
	import favicon from '#lib/assets/favicon.svg';
	import Brand from '#lib/components/shell/Brand.svelte';
	import MobileMenu from '#lib/components/shell/MobileMenu.svelte';
	import Petals from '#lib/components/shell/Petals.svelte';
	import DetailDialog from '#lib/components/show/DetailDialog.svelte';
	import TabBar from '#lib/components/shell/TabBar.svelte';
	import ThemeToggle from '#lib/components/shell/ThemeToggle.svelte';
	import * as Tooltip from '#lib/components/ui/tooltip/index.js';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
</script>

<svelte:head>
	<link rel="icon" type="image/svg+xml" href={favicon} />
</svelte:head>

<Tooltip.Provider delayDuration={120}>
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
		{@render children()}
	</main>
	<MobileMenu />
	<DetailDialog />
</Tooltip.Provider>
