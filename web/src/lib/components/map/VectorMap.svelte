<script lang="ts">
	// A map of the shows, with its title and its legend above it. The canvas and its controls are
	// the work of the map code in lib/map/engine.js. This component makes the box, gives the map
	// its data, and has the buttons above the map: the view (posters or dots) and the match gradient.
	//
	// The map is the card: it has no second frame around it.
	import { onMount, untrack, type Snippet } from 'svelte';
	import '#lib/map/map.css';
	import { createVectorMap, type MapController } from '#lib/map/engine.js';
	import { Toggle } from '#lib/components/ui/toggle/index.js';
	import * as ToggleGroup from '#lib/components/ui/toggle-group/index.js';
	import { detail } from '#lib/state/detail.svelte.js';
	import { mapStore } from '#lib/state/map.svelte.js';
	import { settings } from '#lib/state/settings.svelte.js';

	let {
		title,
		highlight = [],
		highlightLabel = 'Highlighted',
		highlightKind = 'recommended',
		controller = $bindable(null),
		titleSide,
		legend,
		overlay
	}: {
		title: string;
		/** The ids of the shows that are posters also in the far view */
		highlight?: string[];
		highlightLabel?: string;
		highlightKind?: 'recommended' | 'tier';
		/** The map, for a parent that controls it. It is null until the map data is there. */
		controller?: MapController | null;
		/** Controls next to the title */
		titleSide?: Snippet;
		/** More items of the legend, after the items of each map */
		legend?: Snippet;
		/** An element above the map, in its box */
		overlay?: Snippet;
	} = $props();

	let canvas = $state<HTMLCanvasElement | null>(null);
	let tooltip = $state<HTMLDivElement | null>(null);
	let view = $state<'posters' | 'dots'>('posters');

	onMount(() => {
		let map: MapController | null = null;
		let gone = false;
		mapStore.load().then((data) => {
			if (gone || !data || !canvas || !tooltip) return;
			map = createVectorMap(canvas, tooltip, data, {
				highlightIds: untrack(() => highlight),
				highlightLabel,
				highlightKind,
				onOpen: (point) => detail.open(point),
				gradient: () => mapStore.gradientReady
			});
			mapStore.add(map);
			controller = map;
		});
		return () => {
			gone = true;
			if (map) {
				mapStore.remove(map);
				map.destroy();
			}
			controller = null;
		};
	});

	// The highlighted shows change: for example a new list of recommendations
	$effect(() => {
		const ids = highlight;
		controller?.setHighlight(ids);
	});

	// The colors of the theme and the typeface are in the picture of the canvas: draw it again
	$effect(() => {
		void settings.theme;
		void settings.values.font;
		controller?.scheduleDraw();
		if (settings.values.font === 'sans') document.fonts?.load('600 12px "Noto Sans JP"').then(() => controller?.scheduleDraw(), () => {});
	});

	// The match gradient: get the match values when the setting goes on
	$effect(() => {
		if (settings.gradient) untrack(() => mapStore.scheduleMatch());
		controller?.scheduleDraw();
	});

	function setView(next: string) {
		if (next !== 'posters' && next !== 'dots') return;
		view = next;
		controller?.setView(next);
	}

	const failed = $derived(settings.gradient && mapStore.matchState === 'error');
	const dot = 'inline-block size-2 rounded-full';
</script>

<div class="mb-[26px]" data-testid="vector-map">
	<div class="mb-3 flex flex-wrap items-center justify-between gap-2.5">
		<div class="flex items-baseline gap-2 font-serif text-[16px] font-semibold">
			<span>{title}</span>
			{@render titleSide?.()}
		</div>
		<div class="flex flex-wrap items-center gap-x-3.5 gap-y-1.5 text-[12px] text-muted-foreground">
			<div class="flex flex-wrap items-center gap-1.5">
				<ToggleGroup.Root
					type="single"
					size="sm"
					value={view}
					onValueChange={setView}
					aria-label="View"
					class="gap-0.5 rounded-md border bg-[color-mix(in_srgb,var(--hover)_80%,transparent)] p-0.5"
				>
					<ToggleGroup.Item value="posters">Posters</ToggleGroup.Item>
					<ToggleGroup.Item value="dots">Dots</ToggleGroup.Item>
				</ToggleGroup.Root>
				<Toggle
					variant="outline"
					size="sm"
					pressed={settings.gradient}
					onPressedChange={(on) => settings.set('gradient', on ? 'on' : 'off')}
					class="gap-1.5 px-2 py-[3px] {failed ? 'border-tier-d! text-tier-d!' : ''} {settings.gradient && mapStore.matchState === 'loading' ? 'opacity-60' : ''}"
					title={failed ? 'The server did not give the match values. Click two times to try again.' : 'A brighter poster has a higher match.'}
					data-testid="gradient-toggle"
				>
					<i class="h-2 w-5 rounded-[2px] border bg-[linear-gradient(90deg,#231c1f,#f6f0f1)]" aria-hidden="true"></i>Match gradient{failed ? ' · no data' : ''}
				</Toggle>
			</div>
			<span class="flex items-center gap-[5px]"><i class="{dot} bg-[#999] opacity-50"></i> Catalog</span>
			<span class="flex items-center gap-[5px]"><i class="{dot} bg-foreground opacity-70"></i> Your shows</span>
			<span class="flex items-center gap-[5px]" title="A show of yours with a tier has the color of its tier">
				<i class="{dot} bg-tier-s"></i>S <i class="{dot} ml-1 bg-tier-a"></i>A <i class="{dot} ml-1 bg-tier-b"></i>B <i class="{dot} ml-1 bg-tier-c"></i>C
				<i class="{dot} ml-1 bg-tier-d"></i>D
			</span>
			{@render legend?.()}
		</div>
	</div>
	<div class="vector-canvas-box">
		<canvas bind:this={canvas} aria-label="{title}: each show is a point. Scroll to zoom, drag to move."></canvas>
		<div class="vector-map-tooltip" bind:this={tooltip} hidden></div>
		{@render overlay?.()}
	</div>
</div>
