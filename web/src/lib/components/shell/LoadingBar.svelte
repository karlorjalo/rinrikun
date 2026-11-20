<script lang="ts">
	// The loading bar: a thin line at the top of the window while the next page or new data
	// loads. A fast load shows no bar: the bar comes after a short wait. While the load runs, the
	// bar moves to the right more and more slowly. When the load ends, it fills the width and
	// fades. With "reduce motion" the bar does not move (layout.css).
	import { untrack } from 'svelte';
	import { navigating } from '$app/state';
	import { progress } from '#lib/state/progress.svelte.js';

	/** The wait before the bar shows */
	const WAIT = 120;

	const busy = $derived(!!navigating.to || progress.busy);
	let shown = $state(false);
	let width = $state(0);
	let opacity = $state(1);
	let transition = $state('none');
	let showTimer: ReturnType<typeof setTimeout> | undefined;
	let hideTimer: ReturnType<typeof setTimeout> | undefined;

	function start() {
		showTimer = undefined;
		clearTimeout(hideTimer);
		shown = true;
		opacity = 1;
		transition = 'none';
		width = 0;
		// Two frames: the bar is on the screen with the width 0 before its width changes
		requestAnimationFrame(() =>
			requestAnimationFrame(() => {
				transition = 'width 8s cubic-bezier(0.05, 0.7, 0.1, 1)';
				width = 88;
			})
		);
	}

	function finish() {
		transition = 'width 160ms ease-out, opacity 240ms ease-out 140ms';
		width = 100;
		opacity = 0;
		hideTimer = setTimeout(() => {
			shown = false;
			width = 0;
		}, 420);
	}

	// The effect depends only on `busy`: the state of the bar changes in it
	$effect(() => {
		const loading = busy;
		untrack(() => {
			if (loading) {
				if (!shown && showTimer === undefined) showTimer = setTimeout(start, WAIT);
				// A new load while the bar fades: the bar starts again
				else if (shown && opacity === 0) start();
			} else {
				clearTimeout(showTimer);
				showTimer = undefined;
				if (shown && opacity === 1) finish();
			}
		});
	});
</script>

{#if shown}
	<div
		class="loading-bar"
		style:width="{width}%"
		style:opacity
		style:transition
		role="progressbar"
		aria-label="Loading"
		data-testid="loading-bar"
		data-done={opacity === 0 ? '' : undefined}
	></div>
{/if}
