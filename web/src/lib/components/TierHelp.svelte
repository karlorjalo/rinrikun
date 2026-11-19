<script lang="ts">
	// The help card with one question for each tier. The questions say what a tier does in the
	// recommender: S, A and B give more shows like the show (with the weights 2, 1.5 and 1), and
	// C and D give fewer. D also blocks a show that is almost the same.
	import type { Tier } from '#lib/api/types.js';
	import * as Collapsible from '#lib/components/ui/collapsible/index.js';
	import { tierHelp } from '#lib/state/tier-help.svelte.js';
	import TierPill from './show/TierPill.svelte';

	const QUESTIONS: [Tier, string][] = [
		['S', 'Would I watch it again, or do I measure other shows by it?'],
		['A', 'Would I be glad if my next show was like this one?'],
		['B', 'Was it worth my time, and is one more show like it fine?'],
		['C', 'Would I be disappointed if the list gave me a show like this?'],
		['D', 'Is a show that is almost the same a certain no?']
	];
</script>

<Collapsible.Root
	open={tierHelp.open}
	onOpenChange={(open) => tierHelp.set(open)}
	class="my-4 rounded-md border bg-card px-4 py-3 text-left text-[13px]"
	data-testid="tier-help"
>
	<Collapsible.Trigger
		class="flex cursor-pointer items-center gap-2 border-0 bg-transparent p-0 font-serif text-[14px] font-semibold text-foreground hover:text-rose"
	>
		<span class="inline-block text-[10px] transition-transform duration-150 {tierHelp.open ? '' : '-rotate-90'}" aria-hidden="true">▼</span>
		Which tier?
	</Collapsible.Trigger>
	<Collapsible.Content>
		<dl class="mt-2.5 mb-0 grid gap-[7px]">
			{#each QUESTIONS as [tier, question] (tier)}
				<div class="flex items-baseline gap-2.5">
					<dt class="flex-none"><TierPill {tier} /></dt>
					<dd class="m-0 leading-[1.5]">{question}</dd>
				</div>
			{/each}
		</dl>
	</Collapsible.Content>
</Collapsible.Root>
