<script lang="ts">
	// The watch list: the shows with the answer "Interested" that the user does not have. The
	// button has the name of the list and the number of its shows. The list opens below the button.
	//
	// A click on a row opens the detail window of the show. The button of a row takes the show
	// off the list. The row then stays until the list closes, with a button that puts the show back.
	import type { Show } from '#lib/api/types.js';
	import Poster from '#lib/components/show/Poster.svelte';
	import { buttonVariants } from '#lib/components/ui/button/index.js';
	import * as Popover from '#lib/components/ui/popover/index.js';
	import { countOf, displayTitles, formatMatch } from '#lib/format.js';
	import { detail } from '#lib/state/detail.svelte.js';
	import { library } from '#lib/state/library.svelte.js';
	import { watchList } from '#lib/state/watchlist.svelte.js';

	let { initial }: { /** The list from the data of the page: the server renders its number */ initial?: Show[] } = $props();

	let open = $state(false);
	const count = $derived(watchList.loaded ? watchList.count : (initial?.length ?? 0));

	// The list of the page data, or the list of the server if the page has none
	$effect(() => {
		if (initial) watchList.set(initial);
		else watchList.load();
	});

	function changed(next: boolean) {
		// The server has the correct order and the matches of now. A show that the user took off
		// the list does not come back after the list closes.
		if (next) watchList.load();
		else watchList.forgetGone();
	}

	/** Take a show off the watch list, or put it back */
	async function toggle(show: Show) {
		const back = watchList.isGone(show);
		if (!back) watchList.markGone(show);
		try {
			await library.setInterest(show, back ? true : null, 'page');
		} catch (error) {
			console.error('Failed to change the watch list', error);
			if (!back) watchList.unmarkGone(show);
		}
	}

	function meta(show: Show): string {
		const match = formatMatch(show.match);
		return [show.format?.toUpperCase().replace('_', ' '), show.year, match != null ? `${match}% match` : null].filter(Boolean).join(' · ');
	}

	/** The detail window and the viewer of the frames are not "outside" the list: a click in them does not close it */
	function outside(event: Event) {
		const target = event.target;
		if (target instanceof Element && target.closest('[data-slot="dialog-content"], [data-slot="dialog-overlay"]')) event.preventDefault();
	}
</script>

<Popover.Root bind:open onOpenChange={changed}>
	<Popover.Trigger
		class="{buttonVariants()} gap-2 py-[5px] pr-2 pl-3 text-[13px]"
		aria-label="Watch list: {countOf(count, 'show')}"
		data-testid="watch-button"
	>
		Watch list
		<span class="box-border h-5 min-w-6 rounded-full bg-rose px-[7px] text-center text-[11.5px] leading-5 font-semibold text-rose-ink" data-testid="watch-count"
			>{count}</span
		>
	</Popover.Trigger>
	<Popover.Content
		align="end"
		sideOffset={8}
		collisionPadding={12}
		aria-label="Watch list"
		class="max-h-[min(64vh,600px,var(--bits-popover-content-available-height))] w-[min(380px,calc(100vw-24px))] font-sans"
		onInteractOutside={outside}
		onFocusOutside={outside}
		data-testid="watch-panel"
	>
		<div class="flex items-baseline gap-2 border-b py-3 pr-2.5 pb-2.5 pl-4">
			<span class="font-serif text-[16px] font-semibold">Watch list</span>
			<span class="flex-1 text-[12.5px] text-muted-foreground">{countOf(watchList.count, 'show')}</span>
			<Popover.Close
				class="flex size-7 cursor-pointer items-center justify-center self-center rounded-md border-0 bg-transparent p-0 text-[13px] leading-none text-muted-foreground hover:bg-muted hover:text-foreground"
				aria-label="Close the watch list"
				title="Close">✕</Popover.Close
			>
		</div>
		<ul class="m-0 list-none overflow-y-auto overscroll-contain p-1.5">
			{#each watchList.shows as show (show.id)}
				{@const titles = displayTitles(show)}
				{@const gone = watchList.isGone(show)}
				<li class="flex items-center gap-0.5 rounded-md focus-within:bg-muted hover:bg-muted" data-id={show.id} data-gone={gone || undefined}>
					<button
						type="button"
						class="flex min-w-0 flex-1 cursor-pointer items-center gap-2.5 rounded-md border-0 bg-transparent py-1.5 pr-1 pl-2 text-left font-sans text-inherit {gone
							? 'opacity-45'
							: ''}"
						title="Details"
						onclick={() => detail.open(show)}
					>
						<Poster src={show.poster} title={titles.main} letter="text-[15px]" class="h-[54px] w-[38px] rounded-sm" />
						<span class="flex min-w-0 flex-col gap-px">
							<span class="overflow-hidden text-[13.5px] font-semibold text-ellipsis whitespace-nowrap {gone ? 'line-through' : ''}">{titles.main}</span>
							{#if titles.sub}<span class="overflow-hidden text-[11.5px] text-ellipsis whitespace-nowrap text-muted-foreground">{titles.sub}</span>{/if}
							<span class="overflow-hidden text-[11.5px] text-ellipsis whitespace-nowrap text-muted-foreground">{meta(show)}</span>
						</span>
					</button>
					<button
						type="button"
						class="mr-1 h-[30px] min-w-[30px] flex-none cursor-pointer rounded-md border bg-transparent px-[7px] font-sans text-[12px] hover:bg-card {gone
							? 'border-border text-rose'
							: 'border-transparent text-muted-foreground hover:border-border hover:text-tier-d'}"
						title={gone ? 'Put back' : 'Remove'}
						aria-label="{gone ? 'Put' : 'Take'} {titles.main} {gone ? 'back on' : 'off'} the watch list"
						onclick={() => toggle(show)}>{gone ? 'Undo' : '✕'}</button
					>
				</li>
			{:else}
				<li class="px-[18px] py-7 text-center text-[13px] text-muted-foreground">Empty. Answer "Interested" to add a show.</li>
			{/each}
		</ul>
	</Popover.Content>
</Popover.Root>
