<script lang="ts">
	// The title row of a tab: the heading with the petal of the app, a short text next to it (for
	// example the numbers of a deck), and controls at the right. On a small screen the short text
	// and the controls go below the heading.
	import type { Snippet } from 'svelte';

	let {
		title,
		note,
		children
	}: { title: string; note?: string; children?: Snippet } = $props();
</script>

<div class="mb-5 flex flex-wrap items-center justify-between gap-3">
	<div class="flex flex-wrap items-baseline gap-x-3">
		<h2 class="m-0 flex-none font-serif text-[22px] font-semibold">
			<span class="petal-mark heading" aria-hidden="true"></span>{title}
		</h2>
		{#if note}
			<div class="text-[13px] font-medium text-muted-foreground" data-testid="title-note">{note}</div>
		{/if}
	</div>
	{@render children?.()}
</div>
