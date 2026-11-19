<script lang="ts">
	// The poster of a show. If the picture does not load, the box shows the first letter of the
	// title. `large` asks for the larger file of AniList, and uses the small file if that fails.
	import { largePoster } from '#lib/format.js';

	let {
		src,
		title,
		large = false,
		class: className = ''
	}: { src: string | null | undefined; title: string; large?: boolean; class?: string } = $props();

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
		<img src={address} alt={title} loading="lazy" class="block size-full object-cover" {onerror} />
	{:else}
		<div
			class="flex size-full items-center justify-center font-serif text-2xl font-semibold text-muted-foreground select-none"
			aria-hidden="true"
		>
			{title[0] || '?'}
		</div>
	{/if}
</div>
