<script lang="ts">
	// A message window as in a visual novel: a name plate and one line. The lines are new text in
	// the voice of Utaha Kasumigaoka, who calls the user "倫理君" (rinri-kun). They are not
	// quotations from the series.
	let { line }: { line: string } = $props();
</script>

<div
	class="vn-window relative mx-auto mt-2 mb-6 max-w-[460px] rounded-md border border-[color-mix(in_srgb,var(--accent)_38%,var(--border))] bg-[color-mix(in_srgb,var(--accent)_6%,var(--card))] px-[22px] pt-5 pb-[18px] text-left"
	lang="ja"
>
	<span
		class="absolute -top-[11px] left-4 rounded-sm bg-rose px-3 py-0.5 font-sans text-[11.5px] leading-[1.5] font-semibold tracking-[0.12em] text-rose-ink"
		>霞ヶ丘詩羽</span
	>
	<p class="m-0 font-serif text-[14.5px] leading-[1.85] text-balance [word-break:auto-phrase]">{line}</p>
</div>

<style>
	/* The mark that waits for a click, at the end of the line */
	.vn-window::after {
		content: '';
		position: absolute;
		right: 14px;
		bottom: 9px;
		border: 4px solid transparent;
		border-top: 6px solid var(--accent);
		border-bottom: 0;
		animation: vn-wait 1.1s ease-in-out infinite;
	}
	@keyframes vn-wait {
		50% {
			transform: translateY(3px);
			opacity: 0.45;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.vn-window::after {
			animation: none;
		}
	}
</style>
