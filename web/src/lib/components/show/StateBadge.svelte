<script lang="ts">
	// The small mark that tells that the user has a show: "watched" for a show that the user
	// marked by hand, and "owned" for a show of the library. A list that has only shows of the
	// user gives `owned={null}`: the mark "owned" then tells nothing.
	let {
		show,
		owned = 'owned',
		class: className = ''
	}: {
		show: { owned?: number; manual_watched?: number };
		/** The text of the mark of a library show, or null for no mark */
		owned?: string | null;
		class?: string;
	} = $props();

	const base = 'inline-block flex-none rounded-sm px-1.5 font-sans text-[11px] leading-[1.6] font-normal';
</script>

{#if show.manual_watched}
	<span class="{base} border border-rose/35 bg-rose/18 text-rose {className}">watched</span>
{:else if show.owned && owned}
	<span class="{base} bg-rose text-rose-ink {className}">{owned}</span>
{/if}
