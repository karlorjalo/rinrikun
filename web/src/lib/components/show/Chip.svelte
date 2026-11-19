<script lang="ts">
	// A small tag on a card: a tag of the show, or the reason for a recommendation.
	//   plain    A tag of the show
	//   shared   A tag that the show has in common with the seed show
	//   matched  The liked show that is nearest to a recommendation, with the petal of the app
	//   linked   The liked show that AniList users connect to a recommendation
	import type { Snippet } from 'svelte';

	let {
		kind = 'plain',
		title,
		children
	}: { kind?: 'plain' | 'shared' | 'matched' | 'linked' | 'why'; title?: string; children: Snippet } = $props();

	const LOOK = {
		plain: 'bg-muted text-muted-foreground',
		why: 'bg-muted font-medium text-foreground',
		shared: 'border border-rose/30 bg-rose/14 text-foreground',
		matched: 'border border-rose/28 bg-rose/12 font-medium text-rose',
		linked: 'border bg-transparent font-medium text-foreground'
	};
</script>

<span class="inline-block rounded-sm px-[7px] py-px text-[11.5px] {LOOK[kind]}" {title}>
	{#if kind === 'matched'}<i class="petal-mark mr-[5px]" aria-hidden="true"></i>{/if}{#if kind === 'linked'}<span class="mr-1" aria-hidden="true">⇄</span>{/if}{@render children()}
</span>
