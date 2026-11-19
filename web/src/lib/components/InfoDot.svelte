<script lang="ts">
	// A small "i" in a circle. The pointer, the focus or a tap on it shows a tooltip. The page has
	// no line of text below a heading: an explanation is in the tooltip of such a mark.
	import type { Snippet } from 'svelte';
	import Hint from './Hint.svelte';

	let {
		text,
		tip,
		rich = false,
		label = 'More about this'
	}: { text?: string; tip?: Snippet; rich?: boolean; label?: string } = $props();
</script>

<Hint {text} {tip} {rich}>
	{#snippet children(props)}
		<button
			{...props}
			type="button"
			class="ml-[7px] inline-flex size-[15px] flex-none cursor-help items-center justify-center rounded-full border border-current bg-transparent p-0 align-[2px] font-sans text-[10px] leading-none font-semibold text-muted-foreground not-italic hover:text-rose focus-visible:text-rose focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose"
			aria-label={label}>i</button
		>
	{/snippet}
</Hint>
