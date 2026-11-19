<script lang="ts">
	// The mark of a tier: its letter on the color of the tier.
	import type { Tier } from '#lib/api/types.js';

	let { tier, class: className = '' }: { tier: Tier; class?: string } = $props();

	const COLOR: Record<Tier, string> = {
		S: 'bg-tier-s',
		A: 'bg-tier-a',
		B: 'bg-tier-b',
		C: 'bg-tier-c',
		D: 'bg-tier-d'
	};
</script>

<span
	class="inline-flex flex-none items-center justify-center rounded-sm px-1.5 py-0.5 align-[1px] font-sans text-[11px] leading-none font-bold tracking-[0.02em] text-white {COLOR[tier]} {className}"
	title="Tier {tier}">{tier}</span
>
