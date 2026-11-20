<script lang="ts">
	// One tooltip for many elements. An element with the attribute data-hint="<text>" gets this
	// tooltip: the pointer on it (after the delay of the other tooltips) or the keyboard focus
	// shows the text. On a touch screen a tap shows it, and a later tap closes it.
	//
	// A list of cards thus has one tooltip component, not one for each card: the tooltip component
	// of each card took about 30% of the time to make the card. Hint.svelte stays for the few
	// elements with a rich tooltip.
	import { afterNavigate } from '$app/navigation';
	import { onMount } from 'svelte';
	import * as Tooltip from '#lib/components/ui/tooltip/index.js';

	/** The id of the box of the text: the element of the tooltip names it in aria-describedby */
	const ID = 'hint-layer';
	/** The delay before the pointer opens the tooltip: the delay of the Tooltip.Provider of the layout */
	const DELAY = 120;
	/** A tap in this time after the open does not close the tooltip: it is the tap that opened it */
	const TAP_KEEP = 500;

	let open = $state(false);
	let anchor = $state<HTMLElement | null>(null);
	let text = $state('');
	/** How the tooltip opened: the pointer closes only a tooltip that the pointer opened */
	let openedBy: 'pointer' | 'focus' | 'touch' = 'pointer';
	let openedAt = 0;
	let timer: ReturnType<typeof setTimeout> | undefined;

	function triggerOf(target: EventTarget | null): HTMLElement | null {
		return target instanceof Element ? target.closest<HTMLElement>('[data-hint]') : null;
	}

	function show(trigger: HTMLElement, by: typeof openedBy) {
		clearTimeout(timer);
		if (!trigger.isConnected) return;
		if (anchor && anchor !== trigger) anchor.removeAttribute('aria-describedby');
		anchor = trigger;
		text = trigger.dataset.hint ?? '';
		trigger.setAttribute('aria-describedby', ID);
		if (!open) openedAt = performance.now();
		openedBy = by;
		open = true;
	}

	function hide() {
		clearTimeout(timer);
		open = false;
	}

	// The tooltip closed (also by a key or a click of bits-ui): the element no longer names it
	$effect(() => {
		if (!open) anchor?.removeAttribute('aria-describedby');
	});

	// A new page: the element of the tooltip can be gone
	afterNavigate(() => hide());

	onMount(() => {
		const over = (event: PointerEvent) => {
			if (event.pointerType === 'touch') return;
			const trigger = triggerOf(event.target);
			if (!trigger || (open && trigger === anchor)) return;
			clearTimeout(timer);
			timer = setTimeout(() => show(trigger, 'pointer'), DELAY);
		};
		const out = (event: PointerEvent) => {
			if (event.pointerType === 'touch') return;
			const trigger = triggerOf(event.target);
			if (!trigger || (event.relatedTarget instanceof Node && trigger.contains(event.relatedTarget))) return;
			clearTimeout(timer);
			if (open && trigger === anchor && openedBy === 'pointer') hide();
		};
		const focusIn = (event: FocusEvent) => {
			const trigger = triggerOf(event.target);
			if (trigger) show(trigger, 'focus');
		};
		const focusOut = (event: FocusEvent) => {
			const trigger = triggerOf(event.target);
			if (trigger && trigger === anchor && openedBy !== 'touch') hide();
		};
		const tap = (event: PointerEvent) => {
			if (event.pointerType !== 'touch') return;
			const trigger = triggerOf(event.target);
			if (!trigger) return;
			if (open && trigger === anchor && performance.now() - openedAt > TAP_KEEP) hide();
			else show(trigger, 'touch');
		};
		document.addEventListener('pointerover', over);
		document.addEventListener('pointerout', out);
		document.addEventListener('focusin', focusIn);
		document.addEventListener('focusout', focusOut);
		document.addEventListener('pointerup', tap);
		return () => {
			clearTimeout(timer);
			document.removeEventListener('pointerover', over);
			document.removeEventListener('pointerout', out);
			document.removeEventListener('focusin', focusIn);
			document.removeEventListener('focusout', focusOut);
			document.removeEventListener('pointerup', tap);
		};
	});
</script>

<Tooltip.Root bind:open disableHoverableContent>
	{#if anchor}
		<!-- role="tooltip": bits-ui gives the box no role; the element names the box in aria-describedby -->
		<Tooltip.Content
			id={ID}
			role="tooltip"
			customAnchor={anchor}
			onInteractOutside={(event) => {
				// A tap on the element of the tooltip: the tap rule above decides
				if (anchor && event.target instanceof Node && anchor.contains(event.target)) event.preventDefault();
			}}>{text}</Tooltip.Content
		>
	{/if}
</Tooltip.Root>
