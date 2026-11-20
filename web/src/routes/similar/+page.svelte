<script lang="ts">
	// The Similar tab: the user selects a show, and the tab shows the shows that are most similar
	// to it. The search box finds a show by each of its titles. The show and the number of the
	// results are in the address, and the server renders the results (+page.server.ts). The filter
	// "Unowned" is in the address too; the page filters the results.
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import FilterGroup from '#lib/components/FilterGroup.svelte';
	import ShowCard from '#lib/components/show/ShowCard.svelte';
	import StateBadge from '#lib/components/show/StateBadge.svelte';
	import TitleSearch from '#lib/components/TitleSearch.svelte';
	import { Button } from '#lib/components/ui/button/index.js';
	import { displayTitles } from '#lib/format.js';
	import { FILTER_NAVIGATION, similarHref, withQuery } from '#lib/links.js';
	import { detail } from '#lib/state/detail.svelte.js';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const count = $derived(String(data.count) as '24' | '48');
	const filter = $derived(page.url.searchParams.get('filter') === 'unowned' ? 'unowned' : 'all');
	const name = $derived(data.show ? displayTitles(data.show).main : '');
	const shown = $derived(data.results.filter((show) => filter === 'all' || (!show.owned && !show.manual_watched)));
</script>

<div class="mx-auto mb-7 max-w-[620px]">
	<TitleSearch shown={name} onpick={(title) => goto(similarHref(title.id, count))} />
</div>

{#if data.show}
	{@const seed = data.show}
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
				value={filter}
				options={[
					{ value: 'all', label: 'All', count: data.results.length },
					{ value: 'unowned', label: 'Unowned', title: 'Only the shows that you do not have' }
				]}
				onchange={(value) => goto(withQuery(page.url, { filter: value }, { filter: 'all' }), FILTER_NAVIGATION)}
			/>
			<FilterGroup
				value={count}
				options={[
					{ value: '24', label: '24' },
					{ value: '48', label: '48' }
				]}
				onchange={(value) => goto(withQuery(page.url, { count: value }, { count: '24' }), FILTER_NAVIGATION)}
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
	{:else}
		<p class="m-0 py-10 text-center text-muted-foreground">No match for this filter.</p>
	{/if}
{:else if data.examples.length}
	<div class="mx-auto flex max-w-[520px] flex-wrap justify-center gap-2 px-5 py-12" data-testid="similar-examples">
		{#each data.examples as title (title.id)}
			<Button href={similarHref(title.id)} size="sm" class="px-3.5 py-[5px] text-[12.5px] font-normal hover:text-rose">
				{displayTitles(title).main}
			</Button>
		{/each}
	</div>
{/if}
