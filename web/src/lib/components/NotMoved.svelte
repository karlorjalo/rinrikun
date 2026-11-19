<script lang="ts">
	// A tab that the new page does not have yet. The old page has it.
	import PageTitle from './PageTitle.svelte';

	let { title }: { title: string } = $props();
</script>

<PageTitle {title} />
<p class="text-[14px] text-muted-foreground">
	This tab is not in the new page yet. <a class="text-rose underline" href="/">Open the old page</a>.
</p>
