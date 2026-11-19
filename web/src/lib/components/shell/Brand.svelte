<script lang="ts">
	// The title of the app, in the style of the later logo of the circle "blessing software" (6
	// years later, in Saekano Fine): a round blossom with pinwheel cuts above the name, the name
	// in thin upright letters, and a line of small spaced capitals. The blossom is a new drawing.
	const turns = [72, 144, 216, 288];
</script>

<h1
	class="m-0 inline-flex flex-col items-center gap-[9px] font-sans text-[40px] leading-none font-extralight tracking-[0.05em] text-foreground max-[480px]:gap-[7px] max-[480px]:text-[32px]"
	aria-label="りんりくん"
>
	<svg class="size-14 flex-none max-[480px]:size-[50px]" viewBox="0 0 100 100" aria-hidden="true">
		<defs>
			<mask id="brand-cut">
				<g fill="#fff">
					<circle id="brand-lobe" cx="50" cy="26" r="24" />
					{#each turns as turn (turn)}
						<use href="#brand-lobe" transform="rotate({turn} 50 50)" />
					{/each}
				</g>
				<g fill="none" stroke="#000" stroke-width="2.6" stroke-linecap="round">
					<path id="brand-arc" d="M50 50 A24 24 0 0 0 72.83 18.58" />
					{#each turns as turn (turn)}
						<use href="#brand-arc" transform="rotate({turn} 50 50)" />
					{/each}
				</g>
			</mask>
		</defs>
		<rect width="100" height="100" fill="currentColor" mask="url(#brand-cut)" />
	</svg>
	<span class="flex flex-col items-stretch" aria-hidden="true">
		<span class="mr-[-0.05em] whitespace-nowrap" lang="ja">りんりくん</span>
		<span class="mt-[9px] flex justify-between px-1 text-[9.5px] font-medium tracking-normal">
			{#each 'RINRIKUN' as letter, n (n)}
				<i class="not-italic">{letter}</i>
			{/each}
		</span>
	</span>
</h1>
