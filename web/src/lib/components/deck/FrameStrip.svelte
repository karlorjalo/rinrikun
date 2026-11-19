<script lang="ts">
	// The frames of a show on a card of the Discover deck: one row below the poster and the text.
	// The row has the same height in each state, thus the buttons below the card do not move when
	// the pictures come. The row moves to the side when it has more frames than the card has
	// space for. A click on a frame opens the viewer.
	import { isPlaceholder, pictures } from '#lib/state/pictures.svelte.js';
	import FrameViewer from './FrameViewer.svelte';

	let { show }: { show: { id: string } } = $props();

	const status = $derived(pictures.status(show.id));
	const frames = $derived(pictures.frames(show.id));
	const banner = $derived(pictures.of(show.id)?.banner ?? null);
	let bannerFailed = $state(false);
	/** The position of the frame that the viewer shows, or null if the viewer is closed */
	let viewing = $state<number | null>(null);
	let box = $state<HTMLElement | null>(null);

	$effect(() => {
		// A new card: its row starts at the first frame
		void show.id;
		bannerFailed = false;
		viewing = null;
		if (box) box.scrollLeft = 0;
	});

	$effect(() => {
		// The wheel of the mouse moves the row to the side, when the row has more frames to show.
		// The listener must not be passive, because it stops the scroll of the page.
		const element = box;
		if (!element) return;
		const wheel = (event: WheelEvent) => {
			if (event.ctrlKey || Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
			const end = element.scrollWidth - element.clientWidth;
			if (end <= 0 || (event.deltaY < 0 && element.scrollLeft <= 0) || (event.deltaY > 0 && element.scrollLeft >= end - 1)) return;
			event.preventDefault();
			element.scrollLeft += event.deltaY;
		};
		element.addEventListener('wheel', wheel, { passive: false });
		return () => element.removeEventListener('wheel', wheel);
	});

	const cell = 'relative h-full flex-none aspect-video overflow-hidden rounded-md border bg-muted p-0 font-sans';
	const note = 'm-auto text-[12.5px] text-muted-foreground';
</script>

<div
	bind:this={box}
	class="flex h-[108px] w-full flex-none gap-[9px] overflow-x-auto overflow-y-hidden overscroll-x-contain [scrollbar-width:none] max-[680px]:h-[92px] [&::-webkit-scrollbar]:hidden"
	aria-label="Frames of the show"
	data-testid="deck-frames"
>
	{#if status === 'missing'}
		<p class={note}>Frames did not load.</p>
	{:else if status === 'loading'}
		<div class={cell}></div>
		<div class={cell}></div>
		<div class={cell}></div>
	{:else if frames.length}
		{#each frames as frame, n (frame.small)}
			<button type="button" class="{cell} cursor-zoom-in hover:border-rose focus-visible:border-rose" title="{frame.label}: enlarge" onclick={() => (viewing = n)}>
				<img
					src={frame.small}
					alt="{frame.label}: a frame of the show"
					referrerpolicy="no-referrer"
					decoding="async"
					class="block size-full object-cover"
					onerror={() => pictures.drop(frame)}
					onload={(event) => {
						if (isPlaceholder(event.currentTarget)) pictures.drop(frame);
					}}
				/>
				<span class="pointer-events-none absolute bottom-[5px] left-[5px] rounded-sm bg-black/62 px-1.5 py-px text-[10.5px] leading-[1.5] text-white">{frame.label}</span>
			</button>
		{/each}
	{:else if banner && !bannerFailed}
		<div class="h-full min-w-0 flex-1 overflow-hidden rounded-md border bg-muted">
			<img src={banner} alt="Banner of the show" referrerpolicy="no-referrer" class="block size-full object-cover" onerror={() => (bannerFailed = true)} />
		</div>
	{:else}
		<p class={note}>No frames.</p>
	{/if}
</div>

{#if viewing !== null && frames.length}
	<FrameViewer {frames} bind:index={viewing} onclose={() => (viewing = null)} />
{/if}
