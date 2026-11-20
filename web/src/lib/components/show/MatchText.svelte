<script lang="ts">
	// The match of a show in percent, with a tooltip that tells what the number means. The tooltip
	// is the one tooltip of the page for data-hint (HintLayer.svelte).
	import type { Show } from '#lib/api/types.js';
	import { formatMatch, matchAbout } from '#lib/format.js';

	let { show }: { show: Pick<Show, 'owned' | 'match'> } = $props();
	const text = $derived(formatMatch(show.match));
</script>

{#if text != null}
	<button
		type="button"
		data-hint={matchAbout(show)}
		class="cursor-help border-0 border-b border-dotted border-current/55 bg-transparent p-0 font-[inherit] text-foreground focus-visible:rounded-[2px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose"
		data-testid="match">{text}% match</button
	>
{/if}
