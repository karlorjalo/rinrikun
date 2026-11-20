<script lang="ts">
	// The five tier buttons of a deck, from D at the left to S at the right. Each button shows
	// the number key that gives its tier. The letter of the tier is a key too.
	import type { Tier } from '#lib/api/types.js';

	let { active, onpick }: { active?: Tier | null; onpick: (tier: Tier) => void } = $props();

	const BUTTONS: { tier: Tier; key: number; label: string; color: string }[] = [
		{ tier: 'D', key: 1, label: 'Disliked', color: 'var(--tier-d)' },
		{ tier: 'C', key: 2, label: 'Meh', color: 'var(--tier-c)' },
		{ tier: 'B', key: 3, label: 'Liked', color: 'var(--tier-b)' },
		{ tier: 'A', key: 4, label: 'Favorite', color: 'var(--tier-a)' },
		{ tier: 'S', key: 5, label: 'Masterpiece', color: 'var(--tier-s)' }
	];
</script>

<div class="grid grid-cols-5 gap-2 max-[680px]:gap-1" role="group" aria-label="Tier" data-testid="tier-buttons">
	{#each BUTTONS as button (button.tier)}
		<button
			type="button"
			style="--tier: {button.color}"
			title="Press {button.key} or {button.tier}"
			aria-pressed={active === button.tier}
			onclick={() => onpick(button.tier)}
			class="flex cursor-pointer flex-col items-center gap-[3px] rounded-md border bg-card px-1.5 py-3 font-sans transition-colors duration-150 select-none hover:border-(--tier) aria-pressed:border-(--tier) aria-pressed:bg-[color-mix(in_srgb,var(--tier)_12%,var(--card))] aria-pressed:shadow-[0_0_0_2px_var(--tier)] max-[680px]:px-0.5 max-[680px]:py-2"
		>
			<span class="text-[15px] font-bold text-(--tier) max-[680px]:text-[13px]">{button.key}</span>
			<span class="text-[11px] font-medium text-muted-foreground max-[680px]:hidden">{button.label}</span>
			<span class="text-[11.5px] font-semibold opacity-85 max-[680px]:text-[10.5px]">{button.tier}</span>
		</button>
	{/each}
</div>
