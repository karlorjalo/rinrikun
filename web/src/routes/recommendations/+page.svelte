<script lang="ts">
	// The Recommendations tab: a list of shows that the user does not have, from the taste of the
	// user or from a seed show. Above the list is the map with the recommended shows as posters.
	//
	// The filters "Formula", "Crowd links", "More variety" and "Sequels" ask the server for a new
	// list. "Format" and "Min score" filter the list on the page.
	import { onMount, untrack } from 'svelte';
	import FilterGroup from '#lib/components/FilterGroup.svelte';
	import Hint from '#lib/components/Hint.svelte';
	import ListStory from '#lib/components/map/ListStory.svelte';
	import VectorMap from '#lib/components/map/VectorMap.svelte';
	import ShowCard from '#lib/components/show/ShowCard.svelte';
	import { Button } from '#lib/components/ui/button/index.js';
	import { Toggle } from '#lib/components/ui/toggle/index.js';
	import { displayTitles } from '#lib/format.js';
	import type { MapController } from '#lib/map/engine.js';
	import { recommendView as view } from '#lib/state/recommend.svelte.js';
	import { seeds } from '#lib/state/seed.svelte.js';

	const FORMULAS = {
		usual: {
			name: 'Usual kinds',
			text: 'The kinds that your library has many of move up. A kind is the year, the format and the length. An AniList score below 6.5 moves a show down. A higher score gives no advantage.'
		},
		all: { name: 'All kinds', text: 'The year, the format, the length and the AniList score change nothing.' },
		seed: { name: 'Near the seed', text: 'The shows that are most similar to the seed. The formula and the crowd links have no effect.' }
	};

	let map = $state<MapController | null>(null);
	let story = $state<ListStory | null>(null);
	let storyOpen = $state(false);

	const seed = $derived(seeds.recommend);
	const highlight = $derived(view.list.map((show) => show.id));

	/** Get a new list. The story of the list is for the list that the page showed. */
	function load() {
		story?.close();
		return view.load();
	}

	// The tab opens, or the seed changes: get the list. A card of this tab can set the seed.
	let first = true;
	$effect(() => {
		void seeds.recommend;
		untrack(() => {
			const start = first;
			first = false;
			load().then(() => {
				if (start) autoStory();
			});
		});
	});

	// The story plays one time without a click, when the map is there
	let wantsStory = false;
	function autoStory() {
		wantsStory = !seeds.recommend;
		if (map && wantsStory) {
			wantsStory = false;
			story?.auto();
		}
	}
	$effect(() => {
		if (map && wantsStory) {
			wantsStory = false;
			untrack(() => story?.auto());
		}
	});

	onMount(() => () => story?.close());

	async function dismiss(show: Parameters<typeof view.dismiss>[0]) {
		story?.close();
		await view.dismiss(show);
	}

	async function restore() {
		story?.close();
		await view.restore();
	}
</script>

{#if seed}
	<div
		class="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-md border bg-[color-mix(in_srgb,var(--card)_95%,var(--accent))] px-[18px] py-3"
		data-testid="seed-bar"
	>
		<div class="flex flex-wrap items-center gap-2.5">
			<span class="rounded-sm bg-rose px-2 py-0.5 text-[11px] font-semibold text-rose-ink">Seed</span>
			<b class="font-serif text-[14.5px]">{displayTitles(seed).main}</b>
		</div>
		<Button onclick={() => (seeds.recommend = null)}>✕ Clear</Button>
	</div>
{/if}

<VectorMap title="Recommendation map" {highlight} highlightLabel="Recommended" bind:controller={map}>
	{#snippet titleSide()}
		{#if !seed}
			<Toggle
				variant="outline"
				size="sm"
				pressed={storyOpen}
				onPressedChange={(on) => (on ? story?.start() : story?.close())}
				class="ml-1 self-center px-2.5 py-[3px] text-[11.5px]"
				title="An animation shows how the formula goes from the catalog to your list"
				data-testid="story-button">▶ Steps</Toggle
			>
		{/if}
	{/snippet}
	{#snippet legend()}
		<span class="flex items-center gap-[5px]"><i class="petal-mark text-rose" aria-hidden="true"></i> Recommended</span>
	{/snippet}
	{#snippet overlay()}
		<ListStory bind:this={story} bind:active={storyOpen} {map} list={view.list} kinds={view.kinds} links={view.links} sequels={view.sequels} variety={view.variety} />
	{/snippet}
</VectorMap>

<div
	class="mb-[22px] flex flex-wrap items-center gap-5 rounded-md border bg-card px-3.5 py-2 max-[680px]:flex-col max-[680px]:items-start max-[680px]:gap-2.5"
	data-testid="recs-filters"
>
	{#if !seed}
		<!-- The formula selection has no effect on a list with a seed: that list is in the order of the similarity to the seed -->
		<FilterGroup
			label="Formula"
			variant="accent"
			value={view.kinds}
			options={[
				{ value: 'usual', label: 'Usual kinds', title: 'Shows of the kinds that your library has many of move up' },
				{ value: 'all', label: 'All kinds', title: 'The kind of a show does not change its position' }
			]}
			onchange={(kinds) => {
				story?.close();
				view.setKinds(kinds);
			}}
		/>
		<FilterGroup
			label="Crowd links"
			variant="accent"
			value={view.links ? 'on' : 'off'}
			options={[
				{ value: 'on', label: 'On', title: 'The formula also uses the shows that the fans of your shows recommend on AniList' },
				{ value: 'off', label: 'Off', title: 'The formula uses only your ratings, and the tags and the text of the shows' }
			]}
			onchange={(links) => {
				story?.close();
				view.setLinks(links === 'on');
			}}
		/>
	{/if}
	<div class="flex flex-wrap items-center gap-1">
		{#if !seed}
			<Toggle
				bind:pressed={view.variety}
				onPressedChange={load}
				title="Give results that are less similar to each other"
				data-testid="variety">More variety</Toggle
			>
		{/if}
		<Toggle bind:pressed={view.sequels} onPressedChange={load} title="Also show sequels and side stories of shows that you own" data-testid="sequels"
			>Sequels</Toggle
		>
	</div>
	<FilterGroup
		label="Format"
		bind:value={view.format}
		options={[
			{ value: 'all', label: 'All' },
			{ value: 'tv', label: 'TV' },
			{ value: 'movie', label: 'Movie' },
			{ value: 'ova', label: 'OVA' }
		]}
	/>
	<FilterGroup
		label="Min score"
		bind:value={view.minScore}
		options={[
			{ value: '0', label: 'Any' },
			{ value: '7.0', label: '★ 7.0+' },
			{ value: '7.5', label: '★ 7.5+' },
			{ value: '8.0', label: '★ 8.0+' }
		]}
	/>
	<Hint rich side="bottom">
		{#snippet tip()}
			{@const formula = FORMULAS[view.applied.formula]}
			<div class="max-w-[330px] [&_b]:font-semibold [&_b]:text-foreground [&_p]:m-0 [&_p]:text-muted-foreground [&_p+p]:mt-2" data-testid="about-text">
				<p><b>{formula.name}.</b> {formula.text}</p>
				{#if view.applied.formula !== 'seed'}
					{#if view.applied.links}
						<p><b>Crowd links: on.</b> The formula also uses the shows that the fans of your shows recommend on AniList.</p>
					{:else}
						<p><b>Crowd links: off.</b> The formula uses only your ratings, and the tags and the text of the shows.</p>
					{/if}
					<p>
						<b>Match:</b> how near a show is to your taste. Your predicted tier has a small part in it. The match does not use the formula, thus the list
						is not always in the order of the match.
					</p>
					<p>The button <b>Steps</b>, above the map, shows each step.</p>
				{/if}
			</div>
		{/snippet}
		{#snippet children(props)}
			<button
				{...props}
				type="button"
				class="group ml-auto inline-flex cursor-help items-center border-0 bg-transparent px-1 py-[3px] font-sans text-[12px] text-muted-foreground hover:text-rose focus-visible:text-rose max-[680px]:ml-0"
				data-testid="about-button"
			>
				<span class="mr-1.5 inline-flex size-[15px] items-center justify-center rounded-full border border-current text-[10px] leading-none font-semibold" aria-hidden="true"
					>i</span
				>About
			</button>
		{/snippet}
	</Hint>
</div>

{#if view.lastDismissed}
	<div class="mb-3.5 flex flex-wrap items-center justify-between gap-3 rounded-md border bg-muted px-3.5 py-2 text-[13px] text-muted-foreground" data-testid="undo-bar">
		<span>Removed: <b class="font-serif text-foreground">{displayTitles(view.lastDismissed.show).main}</b></span>
		<Button onclick={restore}>Undo</Button>
	</div>
{/if}

{#if view.shown.length}
	<div class="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-3.5 max-[680px]:grid-cols-[minmax(0,1fr)] max-[680px]:gap-2.5" data-testid="recs-grid">
		{#each view.shown as show (show.id)}
			<ShowCard {show} ondismiss={dismiss} />
		{/each}
	</div>
{:else if view.loaded}
	<p class="m-0 py-10 text-center text-muted-foreground">No match for these filters.</p>
{/if}
