<script lang="ts">
	// The Similar tab: the user selects a show, and the tab shows the shows that are most similar
	// to it. The search box finds a show by each of its titles.
	import type { Title } from '#lib/api/types.js';
	import FilterGroup from '#lib/components/FilterGroup.svelte';
	import ShowCard from '#lib/components/show/ShowCard.svelte';
	import StateBadge from '#lib/components/show/StateBadge.svelte';
	import TitleSearch from '#lib/components/TitleSearch.svelte';
	import { Button } from '#lib/components/ui/button/index.js';
	import { displayTitles } from '#lib/format.js';
	import { detail } from '#lib/state/detail.svelte.js';
	import { similarView as view } from '#lib/state/similar.svelte.js';
	import { titles } from '#lib/state/titles.svelte.js';

	const name = $derived(view.show ? displayTitles(view.show).main : '');
	const shown = $derived(view.results.filter((show) => view.filter === 'all' || (!show.owned && !show.manual_watched)));

	// Some shows of the user as examples, while no show is selected
	let examples = $state.raw<Title[]>([]);
	$effect(() => {
		if (titles.loaded && !examples.length) examples = titles.examples(5);
	});
</script>

<div class="mx-auto mb-7 max-w-[620px]">
	<TitleSearch shown={name} onpick={(title) => view.run(title)} />
</div>

{#if view.show}
	{@const seed = view.show}
	<div
		class="mb-6 flex flex-wrap items-center justify-between gap-2.5 rounded-md border bg-[color-mix(in_srgb,var(--card)_95%,var(--accent))] px-[18px] py-3.5"
		data-testid="similar-header"
	>
		<h2 class="m-0 flex min-w-0 items-center gap-2 font-serif text-[18px] font-semibold">
			<span class="overflow-hidden text-ellipsis whitespace-nowrap">{name}</span>
			<StateBadge show={seed} />
		</h2>
		<div class="flex flex-wrap items-center gap-2.5">
			<FilterGroup
				bind:value={view.filter}
				options={[
					{ value: 'all', label: 'All', count: view.results.length },
					{ value: 'unowned', label: 'Unowned', title: 'Only the shows that you do not have' }
				]}
			/>
			<FilterGroup
				bind:value={view.count}
				options={[
					{ value: '24', label: '24' },
					{ value: '48', label: '48' }
				]}
				onchange={() => view.load()}
			/>
			<Button onclick={() => detail.open(seed)}>Details</Button>
		</div>
	</div>
	{#if shown.length}
		<div
			class="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-3.5 max-[680px]:grid-cols-[minmax(0,1fr)] max-[680px]:gap-2.5"
			data-testid="similar-grid"
		>
			{#each shown as show (show.id)}
				<ShowCard {show} />
			{/each}
		</div>
	{:else if view.loaded}
		<p class="m-0 py-10 text-center text-muted-foreground">No match for this filter.</p>
	{/if}
{:else if examples.length}
	<div class="mx-auto flex max-w-[520px] flex-wrap justify-center gap-2 px-5 py-12" data-testid="similar-examples">
		{#each examples as title (title.id)}
			<Button size="sm" class="px-3.5 py-[5px] text-[12.5px] font-normal hover:text-rose" onclick={() => view.run(title)}>
				{displayTitles(title).main}
			</Button>
		{/each}
	</div>
{/if}
