<script lang="ts">
	// The page of an error: a missing show, or an API server that does not answer.
	import { page } from '$app/state';
	import PageTitle from '#lib/components/PageTitle.svelte';
	import { Button } from '#lib/components/ui/button/index.js';
</script>

<PageTitle title={page.status === 404 ? 'Not found' : 'No data'} />
<p class="m-0 mb-4 text-[14px] text-muted-foreground" data-testid="error-text">
	{page.status === 404 ? 'This page or this show does not exist.' : `${page.error?.message ?? 'The server gave an error'}. Try again in a moment.`}
</p>
<Button onclick={() => location.reload()}>Try again</Button>
