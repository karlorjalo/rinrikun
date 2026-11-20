<script lang="ts">
	// The poster of a show. If the picture does not load, the box shows the first letter of the
	// title. `large` asks for the larger file of AniList, and uses the small file if that fails.
	// `letter` is the size of that letter, for a box that is smaller or larger than a card poster.
	// A picture that is not there yet fades in when it arrives (fadeOnLoad).
	import { largePoster } from '#lib/format.js';
	import { fadeOnLoad } from '#lib/motion.js';

	let {
		src,
		title,
		large = false,
		letter = 'text-2xl',
		class: className = ''
	}: { src: string | null | undefined; title: string; large?: boolean; letter?: string; class?: string } = $props();

	let failed = $state(false);
	let small = $state(false);
	const address = $derived(large && !small ? largePoster(src) : src);

	$effect(() => {
		// A new show: try its picture again
		void src;
		failed = false;
		small = false;
	});

	function onerror() {
		if (large && !small) small = true;
		else failed = true;
	}
</script>

<div class="relative flex-none overflow-hidden rounded-md border bg-muted {className}">
	{#if address && !failed}
		<img use:fadeOnLoad src={address} alt={title} loading="lazy" class="block size-full object-cover" {onerror} />
	{:else}
		<div
			class="flex size-full items-center justify-center font-serif {letter} font-semibold text-muted-foreground select-none"
			aria-hidden="true"
		>
			{title[0] || '?'}
		</div>
	{/if}
</div>
