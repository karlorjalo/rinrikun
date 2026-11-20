<script lang="ts">
	// The picture of one option of a setting, for the tooltip of the setting. The page draws the
	// pictures: they have the colors of the theme and the typefaces of the page, and they show no
	// data of the user.
	import type { SettingKey } from '#lib/state/settings.svelte.js';
	import { MATCH_DARK } from '#lib/settings-list.js';

	let { setting, value, about }: { setting: SettingKey; value: string; about: string } = $props();

	// The petals option: the position, the size and the angle of each petal
	const PETALS = [
		[14, 14, 1, 20],
		[38, 42, 0.8, 110],
		[57, 9, 0.7, 200],
		[100, 44, 1, 60],
		[121, 16, 0.8, 300],
		[141, 54, 0.9, 150],
		[129, 74, 0.6, 250],
		[22, 68, 0.7, 330]
	];
	const LOBES = [0, 72, 144, 216, 288];

	// The match gradient option: posters on a map. With the gradient, a poster is darker if it is
	// farther from the best match. The map makes a poster darker in the same way: with black above it.
	const COLORS = ['#d98a8a', '#8aa9d9', '#93c58d', '#d9b98a', '#b392c5', '#8ac5bf', '#c592ad', '#a9a9a9'];
	const tiles = Array.from({ length: 21 }, (_, n) => {
		const row = Math.floor(n / 7);
		const col = n % 7;
		const far = Math.hypot(col - 2, (row - 1) * 1.3);
		return {
			x: 8 + col * 21,
			y: 7 + row * 26,
			color: COLORS[(col * 3 + row * 5) % 8],
			dark: Math.min(1 - MATCH_DARK, far / 3.4)
		};
	});

	const frame = 'block aspect-video w-[160px] max-w-full overflow-hidden rounded-md border bg-background text-foreground';
</script>

{#if setting === 'font'}
	<div
		class="{frame} flex flex-col justify-center gap-1 px-3 text-left"
		style="--title-font: {value === 'sans' ? 'var(--sans-face)' : `'Noto Serif JP', 'Yu Mincho', serif`}"
		role="img"
		aria-label={about}
	>
		<span class="text-[15px] leading-[1.2] font-bold" style="font-family: var(--title-font)">Taste profile</span>
		<span
			class="overflow-hidden text-[11.5px] leading-[1.3] font-semibold text-ellipsis whitespace-nowrap"
			style="font-family: var(--title-font)"
			lang="ja">冴えない彼女の育てかた</span
		>
		<span class="font-sans text-[10px] text-muted-foreground">2015 · Comedy, Romance</span>
	</div>
{:else if setting === 'petals'}
	<svg
		class={frame}
		style="background: linear-gradient(color-mix(in srgb, var(--accent) 14%, var(--bg)), var(--bg) 75%)"
		viewBox="0 0 160 90"
		role="img"
		aria-label={about}
	>
		{#if value === 'on'}
			{#each PETALS as [x, y, size, turn], n (n)}
				<path
					d="M0 0C5-1 9 2 10 7C4 8 0 5 0 0Z"
					transform="translate({x} {y}) rotate({turn}) scale({size})"
					fill="#f0a6ba"
					opacity="0.9"
				/>
			{/each}
		{/if}
		<g fill="currentColor">
			{#each LOBES as turn (turn)}
				<circle cx="80" cy="18" r="7.5" transform="rotate({turn} 80 26)" />
			{/each}
		</g>
		<text x="80" y="59" text-anchor="middle" font-size="13" font-weight="200" fill="currentColor" lang="ja"
			>りんりくん</text
		>
		<rect x="36" y="69" width="88" height="12" rx="6" fill="none" stroke="currentColor" stroke-opacity="0.28" />
	</svg>
{:else}
	<svg class={frame} viewBox="0 0 160 90" role="img" aria-label={about}>
		{#each tiles as tile, n (n)}
			<rect x={tile.x} y={tile.y} width="18" height="23" rx="2.5" fill={tile.color} />
			{#if value === 'on'}
				<rect x={tile.x} y={tile.y} width="18" height="23" rx="2.5" fill="#000" opacity={tile.dark.toFixed(2)} />
			{/if}
		{/each}
	</svg>
{/if}
