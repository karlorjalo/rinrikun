<script lang="ts">
	// The Discover tab: shows that the user does not have, one card at a time, with frames of
	// each show. The answers are "Interested", "Not interested" and "Seen it". A show with the
	// answer "Interested" goes on the watch list.
	//
	// Keys: N or ← not interested, I or → interested, W seen it, Space next card, Backspace takes
	// the last answer back. After "Seen it" the keys of the tiers give a tier, and Escape goes back.
	import { untrack } from 'svelte';
	import { browser } from '$app/env';
	import DeckCard from '#lib/components/deck/DeckCard.svelte';
	import FrameStrip from '#lib/components/deck/FrameStrip.svelte';
	import TierButtons from '#lib/components/deck/TierButtons.svelte';
	import WatchList from '#lib/components/deck/WatchList.svelte';
	import PageTitle from '#lib/components/PageTitle.svelte';
	import { Button } from '#lib/components/ui/button/index.js';
	import { keysBusy, tierOfKey } from '#lib/keys.js';
	import type { Show } from '#lib/api/types.js';
	import { DiscoverDeck, kept } from '#lib/state/discover.svelte.js';
	import { library } from '#lib/state/library.svelte.js';
	import { pictures } from '#lib/state/pictures.svelte.js';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	/** The deck of the page: the kept deck of the browser, or a new deck with the cards of the data */
	function deckFor(cards: Show[] | null): DiscoverDeck {
		if (!browser) return new DiscoverDeck(cards ?? []);
		if (cards === null && kept.deck) return kept.deck;
		kept.deck = new DiscoverDeck(cards ?? []);
		return kept.deck;
	}
	const deck = $derived(deckFor(data.cards));

	// In the browser: the pictures of the cards, and new cards if the deck is empty
	$effect(() => {
		const current = deck;
		untrack(() => current.prepare());
	});
	$effect(() => {
		if (data.counts) library.counts = data.counts;
	});

	const counts = $derived(library.counts ?? data.counts ?? { interested: 0, not_interested: 0 });
	const progress = $derived(
		`${counts.interested + counts.not_interested} answers · ${counts.interested} interested · ${counts.not_interested} not interested`
	);
	const trailer = $derived(deck.show ? pictures.of(deck.show.id)?.trailer : null);

	function keys(event: KeyboardEvent) {
		if (keysBusy(event)) return;
		const key = event.key.toUpperCase();
		if (!deck.seen) {
			if (key === 'N' || event.key === 'ArrowLeft') deck.answer(false);
			else if (key === 'I' || event.key === 'ArrowRight') deck.answer(true);
			else if (key === 'W') deck.markSeen();
			else if (event.key === ' ') deck.skip();
			else if (event.key === 'Backspace') deck.undoLast();
			else return;
		} else {
			const tier = tierOfKey(event);
			if (tier) deck.rateSeen(tier);
			else if (event.key === 'Escape' || event.key === 'Backspace' || event.key === 'ArrowLeft') deck.undoLast();
			else if (event.key === ' ' || event.key === 'ArrowRight') deck.skip();
			else return;
		}
		event.preventDefault();
	}
</script>

<svelte:window onkeydown={keys} />

<div class="mx-auto max-w-[680px]">
	<PageTitle title="Discover" note={progress}>
		<WatchList initial={data.watch} />
	</PageTitle>

	{#if deck.show}
		{@const show = deck.show}
		<DeckCard {show} label="New">
			{#snippet links()}
				{#if trailer}<Button href={trailer} target="_blank" rel="noopener noreferrer">Trailer ↗</Button>{/if}
				{#if show.anilist_id}
					<Button href="https://anilist.co/anime/{show.anilist_id}" target="_blank" rel="noopener noreferrer">AniList ↗</Button>
				{/if}
			{/snippet}
			{#snippet below()}
				<FrameStrip {show} />
			{/snippet}
		</DeckCard>
	{:else}
		<div class="mb-5 flex min-h-[230px] items-center justify-center rounded-lg border bg-card px-6 py-12 text-center" data-testid="deck-empty">
			<p class="m-0 text-[14px] text-muted-foreground">{deck.loading ? 'Loading…' : 'No more shows.'}</p>
		</div>
	{/if}

	<div class="flex flex-col gap-2.5">
		{#if deck.seen}
			<TierButtons onpick={(tier) => deck.rateSeen(tier)} />
		{:else}
			<div class="grid grid-cols-[1fr_auto_1fr] gap-2">
				<Button size="lg" class="text-muted-foreground hover:border-tier-d hover:text-tier-d" title="Press N or ←" onclick={() => deck.answer(false)} data-testid="answer-no"
					>✕ Not interested</Button
				>
				<Button size="lg" title="Press W" onclick={() => deck.markSeen()} data-testid="answer-seen">Seen it</Button>
				<Button
					size="lg"
					class="border-[color-mix(in_srgb,var(--accent)_45%,var(--border))] text-rose hover:bg-[color-mix(in_srgb,var(--accent)_12%,var(--card))]"
					title="Press I or →"
					onclick={() => deck.answer(true)}
					data-testid="answer-yes">♥ Interested</Button
				>
			</div>
		{/if}
		<div class="text-center text-[11.5px] text-muted-foreground">
			{deck.seen ? 'Give a tier, or Skip for none. Esc goes back.' : 'N no · I yes · W seen · Space skip · Backspace undo'}
		</div>
		<div class="mt-1 flex items-center justify-between">
			<Button title="Backspace" onclick={() => deck.undoLast()}>↺ Undo</Button>
			<Button title="Space" onclick={() => deck.skip()}>Skip</Button>
		</div>
	</div>
</div>
