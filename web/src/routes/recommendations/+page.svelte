<script lang="ts">
	// The Recommendations tab: a list of shows that the user does not have, from the taste of the
	// user or from a seed show. Above the list is the map with the recommended shows as posters.
	// The server renders the list (+page.server.ts).
	//
	// The filters "Formula", "Crowd links", "More variety" and "Sequels" give a new list. "Format"
	// and "Min score" filter the list on the page.
	import { onMount, untrack } from 'svelte';
	import { goto, invalidate } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import type { Kinds, Show } from '#lib/api/types.js';
	import FilterGroup from '#lib/components/FilterGroup.svelte';
	import Hint from '#lib/components/Hint.svelte';
	import ListStory from '#lib/components/map/ListStory.svelte';
	import VectorMap from '#lib/components/map/VectorMap.svelte';
	import ShowCard from '#lib/components/show/ShowCard.svelte';
	import { Button } from '#lib/components/ui/button/index.js';
	import { Toggle } from '#lib/components/ui/toggle/index.js';
	import { displayTitles } from '#lib/format.js';
	import { FILTER_NAVIGATION, withQuery } from '#lib/links.js';
	import type { MapController } from '#lib/map/engine.js';
	import { FORMULA_KEY, LINKS_KEY, loadPreference, savePreference } from '#lib/preferences.js';
	import { library } from '#lib/state/library.svelte.js';
	import { progress } from '#lib/state/progress.svelte.js';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const FORMULAS = {
		usual: {
			name: 'Usual kinds',
			text: 'The kinds that your library has many of move up. A kind is the year, the format and the length. An AniList score below 6.5 moves a show down. A higher score gives no advantage.'
		},
		all: { name: 'All kinds', text: 'The year, the format, the length and the AniList score change nothing.' },
		seed: { name: 'Near the seed', text: 'The shows that are most similar to the seed. The formula and the crowd links have no effect.' }
	};
	const FILTERS = { format: 'all', min: '0' };

	let map = $state<MapController | null>(null);
	let story = $state<ListStory | null>(null);
	let storyOpen = $state(false);

	// The list of the page. A removed show leaves it, and the other cards keep their places. A new
	// list from the server replaces it.
	let list = $derived(data.list);
	let lastDismissed = $derived.by((): { show: Show; index: number } | null => {
		void data.list;
		return null;
	});
	const highlight = $derived(list.map((show) => show.id));

	const format = $derived(page.url.searchParams.get('format') ?? FILTERS.format);
	const minScore = $derived(Number(page.url.searchParams.get('min') ?? FILTERS.min) || 0);
	const shown = $derived(
		list.filter((show) => {
			const kind = (show.format || '').toLowerCase();
			if (format === 'tv' && !kind.includes('tv') && kind !== 'series') return false;
			if (format === 'movie' && !kind.includes('movie')) return false;
			if (format === 'ova' && !kind.includes('ova') && !kind.includes('special')) return false;
			return minScore <= 0 || (show.score != null && show.score >= minScore);
		})
	);

	/** Set a query value of the address. A value that the server reads gives a new list. */
	function setQuery(changes: Record<string, string | null>) {
		goto(withQuery(page.url, changes, { ...FILTERS, variety: '0', sequels: '0' }), FILTER_NAVIGATION);
	}

	/** Keep a preference of the formula, and get the list of the new formula */
	function setFormula(key: string, value: string) {
		story?.close();
		savePreference(key, value);
		progress.track(invalidate('rinrikun:formula'));
	}

	// A new list: the story of the list is for the list that the page showed
	$effect(() => {
		void data.list;
		untrack(() => story?.close());
	});

	onMount(() => {
		// A browser that used the old page of the app has the formula in its local storage, and
		// no cookie yet: the server used the default formula. Then get the list again.
		const kinds: Kinds = loadPreference(FORMULA_KEY) === 'all' ? 'all' : 'usual';
		const links = loadPreference(LINKS_KEY) !== 'off';
		if (kinds !== data.kinds || links !== data.links) progress.track(invalidate('rinrikun:formula'));
		wantsStory = !data.seed;
		return () => story?.close();
	});

	// The story plays one time without a click (see ListStory), when the map is there
	let wantsStory = $state(false);
	$effect(() => {
		if (map && wantsStory) {
			wantsStory = false;
			untrack(() => story?.auto());
		}
	});

	async function dismiss(show: Show) {
		story?.close();
		try {
			await library.setDismissed(show, true);
		} catch (error) {
			console.error('Failed to remove the recommendation', error);
			return;
		}
		const index = list.findIndex((item) => item.id === show.id);
		if (index >= 0) list = list.toSpliced(index, 1);
		lastDismissed = { show, index };
	}

	async function restore() {
		const last = lastDismissed;
		if (!last) return;
		story?.close();
		try {
			await library.setDismissed(last.show, false);
		} catch (error) {
			console.error('Failed to put the recommendation back', error);
			return;
		}
		if (last.index >= 0 && !list.some((item) => item.id === last.show.id)) {
			list = list.toSpliced(Math.min(last.index, list.length), 0, last.show);
		}
		lastDismissed = null;
	}

	const applied = $derived(data.seed ? 'seed' : data.kinds);
</script>

{#if data.seed}
	<div
		class="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-md border bg-[color-mix(in_srgb,var(--card)_95%,var(--accent))] px-[18px] py-3"
		data-testid="seed-bar"
	>
		<div class="flex flex-wrap items-center gap-2.5">
			<span class="rounded-sm bg-rose px-2 py-0.5 text-[11px] font-semibold text-rose-ink">Seed</span>
			<b class="font-serif text-[14.5px]">{displayTitles(data.seed).main}</b>
		</div>
		<Button href={withQuery(page.url, { seed: null }) || resolve('/recommendations')}>✕ Clear</Button>
	</div>
{/if}

<VectorMap title="Recommendation map" {highlight} highlightLabel="Recommended" bind:controller={map}>
	{#snippet titleSide()}
		{#if !data.seed}
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
		<ListStory bind:this={story} bind:active={storyOpen} {map} {list} kinds={data.kinds} links={data.links} sequels={data.sequels} variety={data.variety} />
	{/snippet}
</VectorMap>

<div
	class="mb-[22px] flex flex-wrap items-center gap-5 rounded-md border bg-card px-3.5 py-2 max-[680px]:flex-col max-[680px]:items-start max-[680px]:gap-2.5"
	data-testid="recs-filters"
>
	{#if !data.seed}
		<!-- The formula selection has no effect on a list with a seed: that list is in the order of the similarity to the seed -->
		<FilterGroup
			label="Formula"
			variant="accent"
			value={data.kinds}
			options={[
				{ value: 'usual', label: 'Usual kinds', title: 'Shows of the kinds that your library has many of move up' },
				{ value: 'all', label: 'All kinds', title: 'The kind of a show does not change its position' }
			]}
			onchange={(kinds) => setFormula(FORMULA_KEY, kinds)}
		/>
		<FilterGroup
			label="Crowd links"
			variant="accent"
			value={data.links ? 'on' : 'off'}
			options={[
				{ value: 'on', label: 'On', title: 'The formula also uses the shows that the fans of your shows recommend on AniList' },
				{ value: 'off', label: 'Off', title: 'The formula uses only your ratings, and the tags and the text of the shows' }
			]}
			onchange={(links) => setFormula(LINKS_KEY, links)}
		/>
	{/if}
	<div class="flex flex-wrap items-center gap-1">
		{#if !data.seed}
			<Toggle
				pressed={data.variety}
				onPressedChange={(on) => setQuery({ variety: on ? '1' : null })}
				title="Give results that are less similar to each other"
				data-testid="variety">More variety</Toggle
			>
		{/if}
		<Toggle
			pressed={data.sequels}
			onPressedChange={(on) => setQuery({ sequels: on ? '1' : null })}
			title="Also show sequels and side stories of shows that you own"
			data-testid="sequels">Sequels</Toggle
		>
	</div>
	<FilterGroup
		label="Format"
		value={format}
		options={[
			{ value: 'all', label: 'All' },
			{ value: 'tv', label: 'TV' },
			{ value: 'movie', label: 'Movie' },
			{ value: 'ova', label: 'OVA' }
		]}
		onchange={(value) => setQuery({ format: value })}
	/>
	<FilterGroup
		label="Min score"
		value={page.url.searchParams.get('min') ?? FILTERS.min}
		options={[
			{ value: '0', label: 'Any' },
			{ value: '7.0', label: '★ 7.0+' },
			{ value: '7.5', label: '★ 7.5+' },
			{ value: '8.0', label: '★ 8.0+' }
		]}
		onchange={(value) => setQuery({ min: value })}
	/>
	<Hint rich side="bottom">
		{#snippet tip()}
			{@const formula = FORMULAS[applied]}
			<div class="max-w-[330px] [&_b]:font-semibold [&_b]:text-foreground [&_p]:m-0 [&_p]:text-muted-foreground [&_p+p]:mt-2" data-testid="about-text">
				<p><b>{formula.name}.</b> {formula.text}</p>
				{#if applied !== 'seed'}
					{#if data.links}
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

{#if lastDismissed}
	<div class="mb-3.5 flex flex-wrap items-center justify-between gap-3 rounded-md border bg-muted px-3.5 py-2 text-[13px] text-muted-foreground" data-testid="undo-bar">
		<span>Removed: <b class="font-serif text-foreground">{displayTitles(lastDismissed.show).main}</b></span>
		<Button onclick={restore}>Undo</Button>
	</div>
{/if}

{#if shown.length}
	<div class="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-3.5 max-[680px]:grid-cols-[minmax(0,1fr)] max-[680px]:gap-2.5" data-testid="recs-grid">
		{#each shown as show (show.id)}
			<ShowCard {show} ondismiss={dismiss} />
		{/each}
	</div>
{:else}
	<p class="m-0 py-10 text-center text-muted-foreground">No match for these filters.</p>
{/if}
