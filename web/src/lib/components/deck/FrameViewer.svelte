<script lang="ts">
	// The viewer of the frames: one large picture on a dark page. The arrow keys and the two
	// buttons go to the other frames.
	import type { Frame } from '#lib/api/types.js';
	import * as Dialog from '#lib/components/ui/dialog/index.js';
	import { isPlaceholder } from '#lib/state/pictures.svelte.js';

	let {
		frames,
		index = $bindable(),
		onclose
	}: { frames: Frame[]; index: number; onclose: () => void } = $props();

	const frame = $derived(frames[index] ?? frames[0]);
	// The large picture is not there for each frame. The small picture then takes its place.
	let small = $state(false);
	let nextButton = $state<HTMLButtonElement | null>(null);
	let closeButton = $state<HTMLButtonElement | null>(null);

	function move(step: number) {
		if (frames.length < 2) return;
		small = false;
		index = (index + step + frames.length) % frames.length;
	}

	function keys(event: KeyboardEvent) {
		if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
		event.preventDefault();
		move(event.key === 'ArrowLeft' ? -1 : 1);
	}

	const round =
		'absolute z-[1] flex size-10 cursor-pointer items-center justify-center rounded-full border border-white/35 bg-black/55 p-0 font-sans leading-none text-white hover:border-white hover:bg-black/80 focus-visible:border-white focus-visible:bg-black/80';
</script>

<Dialog.Root open onOpenChange={(open) => !open && onclose()}>
	<Dialog.Content
		aria-describedby={undefined}
		showCloseButton={false}
		overlayClass="bg-[rgba(14,11,12,0.86)]"
		class="max-h-none w-[min(1100px,calc(100vw-24px))] max-w-none overflow-visible rounded-none border-0 bg-transparent text-white shadow-none"
		onkeydown={keys}
		onOpenAutoFocus={(event) => {
			// The focus is on the button for the next frame, thus Space and Enter show the next frame
			event.preventDefault();
			(frames.length > 1 ? nextButton : closeButton)?.focus();
		}}
		data-testid="frame-viewer"
	>
		<Dialog.Title class="sr-only">Frames of the show</Dialog.Title>
		<button bind:this={closeButton} type="button" class="{round} top-2.5 right-2.5 text-[16px]" aria-label="Close" onclick={onclose}>✕</button>
		{#if frames.length > 1}
			<button type="button" class="{round} top-[calc(50%-36px)] left-2.5 text-[22px]" aria-label="The frame before" onclick={() => move(-1)}>‹</button>
			<button bind:this={nextButton} type="button" class="{round} top-[calc(50%-36px)] right-2.5 text-[22px]" aria-label="The next frame" onclick={() => move(1)}>›</button>
		{/if}
		{#if frame}
			<img
				src={small ? frame.small : frame.large}
				alt="{frame.label}: a frame of the show"
				referrerpolicy="no-referrer"
				class="block aspect-video max-h-[calc(100vh-110px)] w-full rounded-md bg-black object-contain"
				onerror={() => (small = true)}
				onload={(event) => {
					if (isPlaceholder(event.currentTarget)) small = true;
				}}
			/>
			<div class="mt-2.5 text-center text-[13px] text-[#ece6e8]" aria-live="polite">{frame.label} · {index + 1} of {frames.length}</div>
		{/if}
	</Dialog.Content>
</Dialog.Root>
