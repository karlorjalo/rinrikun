<script lang="ts">
	// The button of the theme. The style sheet shows the sun in the dark theme and the moon in the
	// light theme: the server does not know the theme of the system, and the icon must be correct
	// before any script runs.
	import { settings } from '#lib/state/settings.svelte.js';
</script>

<button
	type="button"
	class="absolute top-1/2 right-0 flex size-[34px] -translate-y-1/2 items-center justify-center rounded-full border bg-card text-muted-foreground transition-colors duration-150 hover:border-rose hover:bg-muted hover:text-rose"
	aria-label="Toggle theme"
	title="Toggle theme"
	onclick={() => settings.toggleTheme()}
>
	<svg
		width="15"
		height="15"
		viewBox="0 0 24 24"
		fill="none"
		stroke="currentColor"
		stroke-width="2"
		stroke-linecap="round"
		aria-hidden="true"
	>
		<g class="hidden dark:inline">
			<circle cx="12" cy="12" r="4" />
			<path
				d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"
			/>
		</g>
		<path class="dark:hidden" d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
	</svg>
</button>
