<script lang="ts">
	// The Ratings tab: the shows that the user rated, by tier, the shows that the user marked as
	// watched by hand, and the shows that the user removed from the recommendations. The server
	// renders the lists (+page.server.ts). The filters are in the query of the address.
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import type { Tier } from '#lib/api/types.js';
	import FilterGroup from '#lib/components/FilterGroup.svelte';
	import PageTitle from '#lib/components/PageTitle.svelte';
	import ShowCard from '#lib/components/show/ShowCard.svelte';
	import TierHelp from '#lib/components/TierHelp.svelte';
	import { Button } from '#lib/components/ui/button/index.js';
	import VnWindow from '#lib/components/VnWindow.svelte';
	import { TIERS, countOf, displayTitles } from '#lib/format.js';
	import { FILTER_NAVIGATION, withQuery } from '#lib/links.js';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const { rated, manual, dismissed } = $derived(data);

	type Source = 'rated' | 'manual' | 'dismissed';
	type Sort = 'tier' | 'match' | 'score' | 'title';
	const DEFAULTS = { tier: 'all', show: 'rated', sort: 'tier' };
	/** The filters of the address. A value that is not an option gets its default. */
	const query = (key: keyof typeof DEFAULTS, options: readonly string[]) => {
		const value = page.url.searchParams.get(key) ?? DEFAULTS[key];
		return options.includes(value) ? value : DEFAULTS[key];
	};
	const view = $derived({
		tier: query('tier', ['all', ...TIERS]) as Tier | 'all',
		source: query('show', ['rated', 'manual', 'dismissed']) as Source,
		sort: query('sort', ['tier', 'match', 'score', 'title']) as Sort
	});

	function filter(key: keyof typeof DEFAULTS, value: string) {
		goto(withQuery(page.url, { [key]: value }, DEFAULTS), FILTER_NAVIGATION);
	}

	const counts = $derived(
		Object.fromEntries(TIERS.map((tier) => [tier, rated.filter((s) => s.tier === tier).length])) as Record<Tier, number>
	);
	const source = $derived(view.source === 'manual' ? manual : view.source === 'dismissed' ? dismissed : rated);
	const ORDER: Record<string, number> = { S: 0, A: 1, B: 2, C: 3, D: 4 };
	const shown = $derived(
		source
			.filter((show) => view.tier === 'all' || show.tier === view.tier)
			.toSorted((a, b) => {
				if (view.sort === 'tier') {
					const tiers = (ORDER[a.tier ?? ''] ?? 99) - (ORDER[b.tier ?? ''] ?? 99);
					return tiers || (b.match ?? 0) - (a.match ?? 0);
				}
				if (view.sort === 'match') return (b.match ?? 0) - (a.match ?? 0);
				if (view.sort === 'score') return (b.score ?? 0) - (a.score ?? 0);
				return displayTitles(a).main.localeCompare(displayTitles(b).main);
			})
	);
</script>

<PageTitle title="Ratings">
	<div class="text-[13px] font-medium text-muted-foreground" data-testid="ratings-count">{countOf(rated.length, 'show')}</div>
</PageTitle>

<div
	class="mb-6 flex flex-wrap items-center justify-between gap-4 rounded-md border bg-card px-3.5 py-2.5 max-[680px]:flex-col max-[680px]:items-start max-[680px]:gap-2.5"
>
	<FilterGroup
		label="Tier"
		value={view.tier}
		onchange={(value) => filter('tier', value)}
		options={[{ value: 'all', label: 'All' }, ...TIERS.map((tier) => ({ value: tier, label: tier, count: counts[tier] }))]}
	/>
	<FilterGroup
		label="Show"
		value={view.source}
		onchange={(value) => filter('show', value)}
		options={[
			{ value: 'rated', label: 'Rated' },
			{ value: 'manual', label: 'Manual', count: manual.length, title: 'Shows that you marked as watched and that are not in the library' },
			{ value: 'dismissed', label: 'Not interested', count: dismissed.length, title: 'Shows that you removed from the recommendations' }
		]}
	/>
	<FilterGroup
		label="Sort"
		value={view.sort}
		onchange={(value) => filter('sort', value)}
		options={[
			{ value: 'tier', label: 'Tier' },
			{ value: 'match', label: 'Match' },
			{ value: 'score', label: 'Score' },
			{ value: 'title', label: 'Title' }
		]}
	/>
</div>

<TierHelp />

{#if shown.length}
	<div class="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-3.5 max-[680px]:grid-cols-[minmax(0,1fr)] max-[680px]:gap-2.5" data-testid="ratings-grid">
		{#each shown as show (show.id)}
			<ShowCard {show} ownedBadge={false} />
		{/each}
	</div>
{:else}
	<div class="px-5 py-10 text-center text-muted-foreground" data-testid="ratings-empty">
		{#if view.source === 'dismissed' && view.tier === 'all'}
			<VnWindow line="切り捨てた作品はまだ一つもないのね。優しいのか、優柔不断なのか……。" />
			<p class="m-0">Nothing removed. Use ✕ on a recommendation.</p>
		{:else if view.source === 'manual' && view.tier === 'all'}
			<VnWindow line="ライブラリの外で観た作品があるなら、正直に白状なさい。" />
			<p class="m-0">Nothing added by hand. Use "+ Watched" on a show.</p>
		{:else if !rated.length}
			<VnWindow line="まだ何も評価していないのね。話はそれからよ、倫理君。" />
			<h3 class="m-0 mb-1.5 font-serif text-[18px] text-foreground">No ratings yet</h3>
			<p class="m-0 mb-4 text-[13.5px]">Give a tier in Review, or on any show.</p>
			<Button variant="primary" onclick={() => goto(resolve('/review'))}>Review</Button>
		{:else}
			<p class="m-0">No shows in tier {view.tier}.</p>
		{/if}
	</div>
{/if}
