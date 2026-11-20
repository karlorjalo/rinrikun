<script lang="ts">
	// The card of a deck: one show with its poster, its data, its synopsis and some tags. The
	// Review deck and the Discover deck use it.
	import type { Snippet } from 'svelte';
	import type { Show } from '#lib/api/types.js';
	import Chip from '#lib/components/show/Chip.svelte';
	import GuessText from '#lib/components/show/GuessText.svelte';
	import MatchText from '#lib/components/show/MatchText.svelte';
	import Poster from '#lib/components/show/Poster.svelte';
	import TierPill from '#lib/components/show/TierPill.svelte';
	import { Button } from '#lib/components/ui/button/index.js';
	import { displayTitles, formatScore, overviewHtml } from '#lib/format.js';
	import { appear } from '#lib/motion.js';
	import { detail } from '#lib/state/detail.svelte.js';

	let {
		show,
		label,
		position,
		links,
		below
	}: {
		show: Show;
		/** The kind of the card: "Library", "Watched" or "New" */
		label: string;
		/** The place of the card in its deck, for example "3 / 20" */
		position?: string;
		/** Links of the card, before the button "Details" */
		links?: Snippet;
		/** A row below the poster and the text: the frames of the show */
		below?: Snippet;
	} = $props();

	const titles = $derived(displayTitles(show));
	const score = $derived(formatScore(show.score));
</script>

<!-- Each new card of the deck fades in, fast: the next answer does not wait for it -->
{#key show.id}
<article
	in:appear={{ fast: true }}
	class="relative mb-5 flex min-h-[230px] gap-5 rounded-lg border bg-card p-[22px] max-[680px]:flex-col max-[680px]:gap-3.5 max-[680px]:p-4 {below
		? 'flex-wrap max-[680px]:flex-nowrap'
		: ''}"
	data-testid="deck-card"
	data-id={show.id}
>
	<Poster
		src={show.poster}
		title={titles.main}
		large
		letter="text-[40px]"
		class="h-[190px] w-[130px] max-[680px]:mx-auto max-[680px]:h-[146px] max-[680px]:w-[100px]"
	/>
	<div class="flex min-w-0 flex-1 flex-col">
		<div class="mb-1.5 flex items-center justify-between gap-2 text-[12px] text-muted-foreground">
			<span>{label}</span>
			<div class="flex items-center gap-1.5">
				{#if show.tier}<TierPill tier={show.tier} />{/if}
				{#if position}<span class="text-[11.5px]">{position}</span>{/if}
			</div>
		</div>
		<h3 class="m-0 mb-1 font-serif text-[21px] leading-[1.35] font-bold">{titles.main}</h3>
		{#if titles.sub}<div class="mb-2 text-[13px] text-muted-foreground">{titles.sub}</div>{/if}
		<div class="mb-3 flex flex-wrap items-center gap-x-1.5 text-[12.5px] text-muted-foreground">
			{#each [show.format?.toUpperCase(), show.year].filter(Boolean) as part, n (n)}
				{#if n > 0}<span aria-hidden="true">·</span>{/if}<span>{part}</span>
			{/each}
			{#if show.studios?.length}
				<span aria-hidden="true">·</span><span>Studio: <b class="font-medium text-foreground">{show.studios.slice(0, 2).join(', ')}</b></span>
			{/if}
			{#if score}<span aria-hidden="true">·</span><span>★ {score}</span>{/if}
			{#if show.match != null}<span aria-hidden="true">·</span><MatchText {show} />{/if}
			{#if show.tier_guess && !show.tier}<span aria-hidden="true">·</span><GuessText {show} />{/if}
		</div>
		<div class="mb-3.5 line-clamp-4 flex-1 text-[13.5px] leading-[1.6]">
			<!-- eslint-disable-next-line svelte/no-at-html-tags -- overviewHtml makes the text safe -->
			{@html overviewHtml(show.overview)}
		</div>
		{#if show.tags?.length}
			<div class="mb-3 flex flex-wrap gap-[5px]">
				{#each show.tags.slice(0, 5) as tag (tag)}<Chip>{tag}</Chip>{/each}
			</div>
		{/if}
		<div class="flex flex-wrap justify-end gap-2">
			{@render links?.()}
			<Button onclick={() => detail.open(show)}>Details</Button>
		</div>
	</div>
	{@render below?.()}
</article>
{/key}
