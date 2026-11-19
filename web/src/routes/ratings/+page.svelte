<script lang="ts">
	// The Ratings tab: the shows that the user rated, by tier, the shows that the user marked as
	// watched by hand, and the shows that the user removed from the recommendations.
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { api } from '#lib/api/client.js';
	import type { Show, Tier } from '#lib/api/types.js';
	import FilterGroup from '#lib/components/FilterGroup.svelte';
	import PageTitle from '#lib/components/PageTitle.svelte';
	import ShowCard from '#lib/components/show/ShowCard.svelte';
	import TierHelp from '#lib/components/TierHelp.svelte';
	import { Button } from '#lib/components/ui/button/index.js';
	import VnWindow from '#lib/components/VnWindow.svelte';
	import { TIERS, countOf, displayTitles } from '#lib/format.js';
	import { library } from '#lib/state/library.svelte.js';
	import { ratingsView as view } from '#lib/state/ratings.svelte.js';

	let rated = $state<Show[]>([]);
	let manual = $state<Show[]>([]);
	let dismissed = $state<Show[]>([]);
	let loaded = $state(false);

	async function load() {
		try {
			[rated, manual, dismissed] = await Promise.all([api.ratings(), api.watched(), api.dismissed()]);
			loaded = true;
		} catch (error) {
			console.error('Failed to load the ratings', error);
		}
	}

	// Get the lists when the tab opens, and a short time after the last change of a show: a
	// change moves a show from one list to a different list, and it changes the match of other shows.
	let timer: ReturnType<typeof setTimeout> | undefined;
	let seen = -1;
	$effect(() => {
		const version = library.version;
		clearTimeout(timer);
		if (seen < 0) load();
		else if (version !== seen) timer = setTimeout(load, 1500);
		seen = version;
		return () => clearTimeout(timer);
	});

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
		bind:value={view.tier}
		options={[{ value: 'all', label: 'All' }, ...TIERS.map((tier) => ({ value: tier, label: tier, count: counts[tier] }))]}
	/>
	<FilterGroup
		label="Show"
		bind:value={view.source}
		options={[
			{ value: 'rated', label: 'Rated' },
			{ value: 'manual', label: 'Manual', count: manual.length, title: 'Shows that you marked as watched and that are not in the library' },
			{ value: 'dismissed', label: 'Not interested', count: dismissed.length, title: 'Shows that you removed from the recommendations' }
		]}
	/>
	<FilterGroup
		label="Sort"
		bind:value={view.sort}
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
{:else if loaded}
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
