<script lang="ts">
	// The tier guess of a show without a tier: the tier that a small model predicts from the tags
	// of the rated shows. The guess is weak, and the tooltip says so. The tooltip is the one
	// tooltip of the page for data-hint (HintLayer.svelte).
	import type { Show } from '#lib/api/types.js';
	import { GUESS_ABOUT } from '#lib/format.js';

	let { show }: { show: Pick<Show, 'tier' | 'tier_guess'> } = $props();
</script>

{#if show.tier_guess && !show.tier}
	<button
		type="button"
		data-hint={GUESS_ABOUT}
		class="cursor-help border-0 border-b border-dotted border-muted-foreground bg-transparent p-0 font-[inherit] text-muted-foreground focus-visible:rounded-[2px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose"
		>guess {show.tier_guess}</button
	>
{/if}
