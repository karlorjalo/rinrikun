<script lang="ts">
	// An element with a tooltip. The pointer or the keyboard focus on the element shows the
	// tooltip. On a touch screen a tap shows it and a second tap closes it: a touch screen has no
	// pointer that stays on an element.
	//
	// `text` is a short text. For a text with paragraphs or for pictures, give the snippet `tip`
	// and set `rich`. The element is the snippet `children`: it gets the properties that it must
	// spread on its root element.
	import type { Snippet } from 'svelte';
	import * as Tooltip from '#lib/components/ui/tooltip/index.js';

	let {
		text,
		tip,
		rich = false,
		side = 'bottom',
		open = $bindable(false),
		children
	}: {
		text?: string;
		tip?: Snippet;
		rich?: boolean;
		side?: 'top' | 'bottom' | 'left' | 'right';
		open?: boolean;
		children: Snippet<[Record<string, unknown>]>;
	} = $props();

	// A tap gives the element the focus, which opens the tooltip, and then comes the click. The
	// tooltip that this tap opened must stay: only a later tap closes it.
	let openedAt = 0;
	$effect(() => {
		if (open) openedAt = performance.now();
	});

	function tap(event: PointerEvent) {
		if (event.pointerType !== 'touch') return;
		if (open && performance.now() - openedAt > 500) open = false;
		else open = true;
	}
</script>

<Tooltip.Root bind:open disableCloseOnTriggerClick>
	<Tooltip.Trigger>
		{#snippet child({ props })}
			{@render children({ ...props, onpointerup: (event: PointerEvent) => tap(event) })}
		{/snippet}
	</Tooltip.Trigger>
	<Tooltip.Content {rich} {side}>
		{#if tip}{@render tip()}{:else}{text}{/if}
	</Tooltip.Content>
</Tooltip.Root>
