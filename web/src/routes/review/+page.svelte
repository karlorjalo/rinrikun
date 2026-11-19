<script lang="ts">
	// The Review tab: the shows of the user, one card at a time. The user gives each show a tier
	// with a button or with a key. The shows without a tier come first.
	//
	// Keys: 1 to 5 or the letter of a tier give the tier. Backspace or ← takes the last tier back.
	// Space or → goes to the next card.
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import DeckCard from '#lib/components/deck/DeckCard.svelte';
	import TierButtons from '#lib/components/deck/TierButtons.svelte';
	import FilterGroup from '#lib/components/FilterGroup.svelte';
	import PageTitle from '#lib/components/PageTitle.svelte';
	import TierHelp from '#lib/components/TierHelp.svelte';
	import { Button } from '#lib/components/ui/button/index.js';
	import VnWindow from '#lib/components/VnWindow.svelte';
	import { countOf } from '#lib/format.js';
	import { keysBusy, tierOfKey } from '#lib/keys.js';
	import { reviewDeck as deck } from '#lib/state/review.svelte.js';

	// The tab opens: the queue of now, from its first card
	onMount(() => {
		deck.load();
	});

	const progress = $derived(deck.total > 0 ? `${deck.rated} of ${deck.total} rated` : countOf(deck.queue.length, 'show'));

	function keys(event: KeyboardEvent) {
		if (keysBusy(event)) return;
		const tier = tierOfKey(event);
		if (tier) deck.rate(tier);
		else if (event.key === 'Backspace' || event.key === 'ArrowLeft') deck.undoLast();
		else if (event.key === ' ' || event.key === 'ArrowRight') deck.skip();
		else return;
		event.preventDefault();
	}
</script>

<svelte:window onkeydown={keys} />

<div class="mx-auto max-w-[680px]">
	<PageTitle title="Library review" note={progress}>
		<div class="rounded-md border bg-card p-[3px]">
			<FilterGroup
				value={deck.mode}
				options={[
					{ value: 'unrated', label: 'Unrated' },
					{ value: 'all', label: 'All' }
				]}
				onchange={(mode) => deck.setMode(mode)}
			/>
		</div>
	</PageTitle>

	{#if deck.show}
		<DeckCard show={deck.show} label={deck.show.source === 'library' ? 'Library' : 'Watched'} position="{deck.index + 1} / {deck.queue.length}" />
	{:else if deck.failed}
		<div class="mb-5 flex min-h-[230px] items-center justify-center rounded-lg border bg-card px-6 py-12 text-center">
			<p class="m-0 text-[14px] text-muted-foreground">The queue did not load. Is the server running?</p>
		</div>
	{:else if deck.loaded}
		<div class="mb-5 flex min-h-[230px] items-center justify-center rounded-lg border bg-card px-6 py-12 text-center" data-testid="deck-done">
			<div class="max-w-[380px]">
				<VnWindow line={deck.mode === 'unrated' ? 'あら、もう全部に評価をつけたの？ 倫理君にしては仕事が早いじゃない。' : 'これで最後よ。お疲れさま、倫理君。'} />
				<h3 class="m-0 mb-2 font-serif text-[20px]">All done</h3>
				<p class="m-0 mb-5 text-[14px] text-muted-foreground">{deck.mode === 'unrated' ? 'Every show has a tier.' : 'End of the queue.'}</p>
				<div class="flex flex-wrap justify-center gap-2.5">
					{#if deck.mode === 'unrated'}<Button onclick={() => deck.setMode('all')}>Review all</Button>{/if}
					<Button variant="primary" onclick={() => goto(resolve('/'))}>Profile</Button>
				</div>
			</div>
		</div>
	{:else}
		<div class="mb-5 min-h-[230px] rounded-lg border bg-card"></div>
	{/if}

	<div class="flex flex-col gap-2.5">
		<TierButtons active={deck.show?.tier} onpick={(tier) => deck.rate(tier)} />
		<div class="mt-1 flex items-center justify-between">
			<Button title="Backspace or ←" onclick={() => deck.undoLast()}>↺ Undo</Button>
			<Button title="Space or →" onclick={() => deck.skip()}>Skip</Button>
		</div>
	</div>

	<TierHelp />
</div>
