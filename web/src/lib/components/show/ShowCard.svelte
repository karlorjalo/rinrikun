<script lang="ts">
	// The card of a show in a list: the poster, the titles, the numbers and some tags. A click on
	// the card opens the detail window. The button with the petal uses the show as the seed of a
	// list of recommendations. A list of recommendations also has the button that removes the show.
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import type { Show } from '#lib/api/types.js';
	import { displayTitles, formatScore } from '#lib/format.js';
	import { detail } from '#lib/state/detail.svelte.js';
	import { seeds } from '#lib/state/seed.svelte.js';
	import Chip from './Chip.svelte';
	import GuessText from './GuessText.svelte';
	import MatchText from './MatchText.svelte';
	import Poster from './Poster.svelte';
	import TierPill from './TierPill.svelte';

	let {
		show,
		why,
		ownedBadge = true,
		ondismiss
	}: {
		show: Show;
		/** A text in place of the tags: why the show is in the list */
		why?: string;
		/** Show the badge "owned". A list that has only shows of the user turns it off. */
		ownedBadge?: boolean;
		/** The list can remove the show: the card gets the button for it */
		ondismiss?: (show: Show) => void;
	} = $props();

	const titles = $derived(displayTitles(show));
	const meta = $derived([titles.sub, show.year, show.genres?.slice(0, 2).join(', ')].filter(Boolean).join(' · '));
	const score = $derived(formatScore(show.score));
	const similarity = $derived(show.similarity != null ? Math.round(show.similarity) : null);

	function useAsSeed() {
		seeds.recommend = show;
		goto(resolve('/recommendations'));
	}

	const round =
		'absolute top-2 z-[2] flex size-[26px] cursor-pointer items-center justify-center rounded-full border bg-card opacity-0 transition-[opacity,border-color] duration-150 group-hover:opacity-100 focus-visible:opacity-100 hover:bg-muted [@media(hover:none)]:opacity-100';
</script>

<article
	class="group relative flex gap-3 rounded-md border bg-card p-3 transition-colors duration-150 hover:border-rose"
	data-id={show.id}
	data-testid="show-card"
>
	<Poster src={show.poster} title={titles.main} class="h-[104px] w-[72px]" />
	<div class="min-w-0 flex-1">
		<h3 class="m-0 line-clamp-2 font-serif text-[15.5px] leading-[1.4] font-semibold">
			<!-- The button covers the card, thus a click at each place of the card opens the window -->
			<button
				type="button"
				class="cursor-pointer border-0 bg-transparent p-0 text-left font-[inherit] text-inherit after:absolute after:inset-0 after:content-[''] focus-visible:outline-none focus-visible:after:rounded-md focus-visible:after:outline-2 focus-visible:after:outline-rose"
				onclick={() => detail.open(show)}>{titles.main}</button
			>
			{#if show.tier}<TierPill tier={show.tier} />{/if}
			{#if show.manual_watched}
				<span class="mr-1 inline-block rounded-sm border border-rose/35 bg-rose/18 px-1.5 align-[1px] font-sans text-[11px] font-normal text-rose">watched</span>
			{:else if show.owned && ownedBadge}
				<span class="mr-1 inline-block rounded-sm bg-rose px-1.5 align-[1px] font-sans text-[11px] font-normal text-rose-ink">owned</span>
			{:else if show.franchise_owned}
				<span
					class="mr-1 inline-block rounded-sm border bg-muted px-1.5 align-[1px] font-sans text-[11px] font-normal text-muted-foreground"
					title="You own another show of this franchise">franchise owned</span
				>
			{/if}
		</h3>
		<div class="mt-0.5 overflow-hidden text-[12px] text-ellipsis whitespace-nowrap text-muted-foreground">{meta}</div>
		<div class="relative z-[1] mt-0.5 flex w-fit flex-wrap items-center gap-x-1.5 text-[12px] font-medium text-muted-foreground">
			{#if show.match != null}<MatchText {show} />{/if}
			{#if show.tier_guess && !show.tier}<span aria-hidden="true">·</span><GuessText {show} />{/if}
			{#if similarity != null}<span aria-hidden="true">·</span><span title="The similarity to the seed show">{similarity}% similar</span>{/if}
			{#if score}<span aria-hidden="true">·</span><span class="text-rose">★ {score}</span>{/if}
		</div>
		{#if similarity != null}
			<div class="mt-1.5 h-[3px] overflow-hidden rounded-[2px] bg-border" title="{similarity}% similar to the seed show">
				<i class="block h-full bg-rose" style="width: {Math.max(0, Math.min(100, similarity))}%"></i>
			</div>
		{/if}
		<div class="mt-1.5 flex flex-wrap gap-1">
			{#if why}
				<Chip kind="why">{why}</Chip>
			{:else if show.matched_favorite}
				<Chip kind="matched" title="Matches your favorite: {show.matched_favorite}">{show.matched_favorite}</Chip>
				{#if show.linked_favorite}
					<Chip kind="linked" title="AniList users recommend this show to people who like: {show.linked_favorite}"
						>{show.linked_favorite}</Chip
					>
				{/if}
				{#each (show.tags ?? []).slice(0, show.linked_favorite ? 1 : 2) as tag (tag)}<Chip>{tag}</Chip>{/each}
			{:else if show.shared_tags?.length}
				{#each show.shared_tags.slice(0, 3) as tag (tag)}<Chip kind="shared" title="Shared tag">{tag}</Chip>{/each}
			{:else}
				{#each (show.tags ?? []).slice(0, 3) as tag (tag)}<Chip>{tag}</Chip>{/each}
			{/if}
		</div>
	</div>
	{#if ondismiss}
		<button
			type="button"
			class="{round} right-10 text-[11px] text-muted-foreground hover:border-tier-d hover:text-tier-d"
			title="Not interested"
			aria-label="Not interested"
			onclick={() => ondismiss(show)}>✕</button
		>
	{/if}
	<button type="button" class="{round} right-2 text-rose hover:border-rose" title="Use as seed" aria-label="Use as seed" onclick={useAsSeed}>
		<i class="petal-mark" aria-hidden="true"></i>
	</button>
</article>
