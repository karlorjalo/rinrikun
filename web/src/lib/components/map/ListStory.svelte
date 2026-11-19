<script lang="ts" module>
	import type { StorySteps } from '#lib/api/types.js';

	type Step = StorySteps['steps'][number];
	type Info = StorySteps['info'];

	const number = (value: number) => Number(value).toLocaleString('en-US');

	/** The name and the text of each step of the formula */
	const STEPS: Record<string, { name: string; text: (step: Step, info: Info, variety: boolean) => string }> = {
		catalog: {
			name: 'Catalog',
			text: (step) => `Each dot is one show. The catalog has ${number(step.count)} shows.`
		},
		new: {
			name: 'New',
			text: (step, info) =>
				`The ${number(info.shows)} shows that you have go out, with the other shows of their ${number(info.franchises)} franchises. ` +
				`Shows that are not released go out too${info.removed ? `, and the ${number(info.removed)} shows that you removed` : ''}. One show stays for each franchise.`
		},
		content: {
			name: 'Taste',
			text: (step, info) =>
				`The formula learns from the tags and the text of your ${number(info.liked)} liked shows. ` +
				'A show stays if it is like some of them, or if it has what they have and the catalog does not have.'
		},
		links: {
			name: 'Crowd links',
			text: (step, info) =>
				`AniList users who like your shows also recommend other shows. A show moves up if it has many of these links from your ${number(info.sources)} franchises.`
		},
		tier: {
			name: 'Tiers',
			text: (step, info) =>
				`A small model learns from the tags of your ${number(info.rated)} rated shows which tier you will give. A show moves down if the model predicts a low tier for it.`
		},
		kind: {
			name: 'Usual kinds',
			text: () => 'A show moves up if its year, its format and its length are usual for your library.'
		},
		list: {
			name: 'List',
			text: (step, info, variety) => `The formula adds all the parts. The ${number(step.count)} best shows are your list${variety ? ', with more variety' : ''}.`
		}
	};

	/** The browser keeps that the story played one time without a click */
	const SEEN_KEY = 'rinrikun-story-seen';
	/** The time of one step in milliseconds, and the part of it in which the dots change */
	const STEP_MS = 3400;
	const MOVE_MS = 1100;
</script>

<script lang="ts">
	// The story of the list: an animation on the Recommendations map shows how the formula goes
	// from the catalog to the list. Each step is one part of the formula. The dots of the shows
	// that stay are strong, and the other dots are faint. This panel on the map has the number of
	// shows and a short text for each step. The server gives the steps: see /api/recommend/steps.
	import { tick } from 'svelte';
	import { api } from '#lib/api/client.js';
	import type { Kinds, Show } from '#lib/api/types.js';
	import type { MapController, MapStory, StoryLook } from '#lib/map/engine.js';
	import { mapStore } from '#lib/state/map.svelte.js';

	let {
		map,
		list,
		kinds,
		links,
		sequels,
		variety,
		active = $bindable(false)
	}: {
		map: MapController | null;
		/** The list that the page shows: the last step of the story has its shows */
		list: Show[];
		kinds: Kinds;
		links: boolean;
		sequels: boolean;
		variety: boolean;
		/** The story is open */
		active?: boolean;
	} = $props();

	/** The data of the story that is open: for each step the points that stay, and the look of their dots */
	let run = $state.raw<{ steps: Step[]; info: Info; lit: Uint8Array[]; looks: StoryLook[]; variety: boolean } | null>(null);
	let index = $state(-1);
	let playing = $state(false);
	let panel = $state<HTMLElement | null>(null);
	let frame = 0;
	let timer: ReturnType<typeof setTimeout> | undefined;
	/** The number of the last request for the steps */
	let request = 0;

	const step = $derived(run && index >= 0 ? run.steps[index] : null);
	const ended = $derived(!!run && index === run.steps.length - 1);

	/**
	 * The look of the dots that stay in a step. Fewer shows stay in each step, thus the dots get
	 * stronger and larger. `least` is the number of shows of the list.
	 */
	function lookOf(count: number, position: number, total: number, least: number): StoryLook {
		const span = Math.log(Math.max(total, least + 1) / least);
		const part = Math.max(0, Math.min(1, 1 - Math.log(Math.max(count, least) / least) / span));
		// The taste of the user counts from the third step
		return { alpha: 0.26 + 0.6 * part, size: 1 + 1.4 * part, taste: position >= 2 };
	}

	/** Get the steps of the list from the server and play them */
	export async function start() {
		const data = mapStore.data;
		if (!map || !data) return;
		close();
		const asked = ++request;
		let result: StorySteps;
		try {
			result = await api.recommendSteps({ k: Math.max(1, list.length || 40), kinds, links, sequels });
		} catch (error) {
			console.error('Failed to load the steps of the list', error);
			return;
		}
		if (asked !== request || !result.steps || result.steps.length < 3) return;

		const points = data.points;
		const lit = result.steps.map((item) => {
			const flags = new Uint8Array(points.length);
			if (!item.points) flags.fill(1);
			else for (const point of item.points) if (point < flags.length) flags[point] = 1;
			return flags;
		});
		// The last step is the list that the page shows
		const last = result.steps[result.steps.length - 1];
		if (last.key === 'list' && list.length) {
			const position = new Map(points.map((point, n) => [point.id, n]));
			const flags = new Uint8Array(points.length);
			let count = 0;
			for (const show of list) {
				const n = position.get(show.id);
				if (n === undefined) continue;
				flags[n] = 1;
				count += 1;
			}
			lit[lit.length - 1] = flags;
			last.count = count;
		}
		const total = result.steps[0].count;
		const least = Math.max(1, last.count);
		run = { steps: result.steps, info: result.info, lit, looks: result.steps.map((item, n) => lookOf(item.count, n, total, least)), variety };
		index = -1;
		playing = true;
		active = true;
		await tick();
		if (!panel || !map) return;
		// The zoom buttons move away from the panel
		const box = panel.parentElement!;
		box.classList.add('story-open');
		// The panel covers a part of the map box. Move the map so that the panel does not cover it.
		const area = box.getBoundingClientRect();
		const rect = panel.getBoundingClientRect();
		const side = Math.max(1, Math.min(area.width, area.height) - 48);
		let dx = 0;
		let dy = 0;
		if (rect.width < area.width * 0.6) {
			const over = (area.width + side) / 2 - (rect.left - area.left) + 12;
			dx = -Math.max(0, Math.min(over, (area.width - side) / 2 - 8));
		} else {
			const over = (area.height + side) / 2 - (rect.top - area.top) + 12;
			dy = -Math.max(0, Math.min(over, (area.height - side) / 2 - 56));
		}
		map.clearSearch();
		map.resetView(dx, dy);
		show(0);
	}

	/** Go to a step. The dots change from the step that the map shows to this step. */
	function show(next: number) {
		const story = run;
		if (!story || !map) return;
		const target = map;
		cancelAnimationFrame(frame);
		clearTimeout(timer);
		const before = index < 0 ? next : index;
		index = next;
		const last = next === story.steps.length - 1;
		// No animation for a user who asked the system for less motion
		const duration = before === next || matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : MOVE_MS;
		const state: MapStory = { from: story.lit[before], to: story.lit[next], lookFrom: story.looks[before], lookTo: story.looks[next], ease: 0, last, step: next };
		const begin = performance.now();
		const draw = (now: number) => {
			if (run !== story) return;
			const t = duration ? Math.max(0, Math.min(1, (now - begin) / duration)) : 1;
			state.ease = t * t * (3 - 2 * t);
			target.setStory(state);
			target.draw();
			if (t < 1) {
				frame = requestAnimationFrame(draw);
				return;
			}
			if (last) {
				// The story ends with the usual picture of the map: the list as posters
				target.setStory(null);
				target.scheduleDraw();
				playing = false;
			} else if (playing) {
				timer = setTimeout(() => show(next + 1), STEP_MS - duration);
			}
		};
		frame = requestAnimationFrame(draw);
	}

	export function close() {
		request += 1;
		if (!run) return;
		run = null;
		index = -1;
		playing = false;
		active = false;
		cancelAnimationFrame(frame);
		clearTimeout(timer);
		map?.setStory(null);
		map?.scheduleDraw();
		panel?.parentElement?.classList.remove('story-open');
	}

	/** The story plays one time without a click: with the first list of recommendations in this browser */
	export function auto() {
		if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
		try {
			if (localStorage.getItem(SEEN_KEY)) return;
			localStorage.setItem(SEEN_KEY, '1');
		} catch {
			return;
		}
		start();
	}

	function togglePlay() {
		playing = !playing;
		if (!playing) clearTimeout(timer);
		else show(ended ? 0 : index + 1);
	}

	// The component goes away: the map has its usual picture again
	$effect(() => () => close());
</script>

{#if run}
	<!-- The panel gets the Escape key of each of its buttons -->
	<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
	<div
		bind:this={panel}
		class="story-panel"
		role="group"
		aria-label="List steps"
		data-step={step?.key}
		data-playing={playing}
		onkeydown={(event) => event.key === 'Escape' && close()}
		data-testid="story-panel"
	>
		<div class="mb-[7px] flex items-center gap-2">
			<span class="flex-1 font-serif text-[14px] font-semibold">List steps</span>
			<span class="text-[11px] text-muted-foreground tabular-nums">{index + 1} / {run.steps.length}</span>
			<button
				type="button"
				class="flex size-[22px] flex-none cursor-pointer items-center justify-center rounded-sm border-0 bg-transparent text-[12px] text-muted-foreground hover:bg-muted hover:text-foreground"
				aria-label="Close"
				title="Close"
				onclick={close}>✕</button
			>
		</div>
		<div class="flex flex-col gap-0.5">
			{#each run.steps as item, n (item.key)}
				<!-- The bar of a step: the number of its shows, on a logarithmic scale -->
				<button
					type="button"
					class="story-row"
					class:is-done={n <= index}
					class:is-current={n === index}
					aria-current={n === index ? 'step' : undefined}
					style="--w: {Math.max(6, Math.round((100 * Math.log(Math.max(item.count, 2))) / Math.log(Math.max(run.steps[0].count, 3))))}%"
					onclick={() => {
						playing = false;
						show(n);
					}}
				>
					<span>{STEPS[item.key]?.name ?? item.key}</span>
					<span class="tabular-nums">{number(item.count)}</span>
				</button>
			{/each}
		</div>
		<p class="story-text" aria-live="polite">{step ? (STEPS[step.key]?.text(step, run.info, run.variety) ?? '') : ''}</p>
		<div class="flex gap-1.5">
			<button
				type="button"
				class="cursor-pointer rounded-sm border bg-transparent px-2.5 py-[3px] font-sans text-[12px] text-foreground hover:border-rose hover:text-rose"
				onclick={togglePlay}>{playing ? '⏸ Pause' : ended ? '▶ Replay' : '▶ Play'}</button
			>
		</div>
		<p class="story-note">Each step keeps the best shows so far. A later step can bring a show back.</p>
	</div>
{/if}

<style>
	.story-panel {
		position: absolute;
		top: 12px;
		right: 12px;
		z-index: 55;
		width: 264px;
		max-height: calc(100% - 24px);
		overflow: auto;
		padding: 10px 12px;
		font-family: var(--sans-face);
		background: var(--card);
		border: 1px solid var(--border);
		border-radius: var(--radius-m);
		box-shadow: var(--float-shadow);
	}
	.story-row {
		position: relative;
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 8px;
		width: 100%;
		padding: 3px 7px;
		overflow: hidden;
		font-family: var(--sans-face);
		font-size: 12px;
		line-height: 1.5;
		color: var(--muted);
		text-align: left;
		cursor: pointer;
		background: transparent;
		border: 0;
		border-radius: var(--radius-s);
		opacity: 0.5;
		transition:
			opacity 0.3s ease,
			color 0.3s ease;
	}
	.story-row:hover {
		opacity: 1;
	}
	/* The bar grows when the story comes to its step */
	.story-row::before {
		position: absolute;
		top: 0;
		bottom: 0;
		left: 0;
		width: 0;
		content: '';
		background: color-mix(in srgb, var(--accent) 15%, transparent);
		border-radius: var(--radius-s);
		transition:
			width 0.9s cubic-bezier(0.2, 0.7, 0.2, 1),
			background 0.3s ease;
	}
	.story-row.is-done {
		color: var(--text);
		opacity: 1;
	}
	.story-row.is-done::before {
		width: var(--w);
	}
	.story-row.is-current {
		font-weight: 600;
	}
	.story-row.is-current::before {
		background: color-mix(in srgb, var(--accent) 36%, transparent);
	}
	.story-row > span {
		position: relative;
	}
	.story-text {
		min-height: 6em;
		margin: 9px 1px 8px;
		font-size: 12.5px;
		line-height: 1.5;
	}
	.story-note {
		margin: 8px 1px 0;
		font-size: 11px;
		line-height: 1.45;
		color: var(--muted);
	}
	@media (max-width: 680px) {
		/* On a small screen the panel is a strip at the bottom of the map, with only the step of now */
		.story-panel {
			top: auto;
			right: 8px;
			bottom: 8px;
			left: 8px;
			width: auto;
			max-height: 60%;
		}
		.story-row:not(.is-current),
		.story-note {
			display: none;
		}
		.story-text {
			min-height: 0;
			margin: 6px 1px;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.story-row,
		.story-row::before {
			transition: none;
		}
	}
</style>
