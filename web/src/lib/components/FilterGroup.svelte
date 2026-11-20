<script lang="ts" generics="V extends string">
	// One group of a filter bar: a label and its options, of which one is on. An option can have
	// a number (for example the number of the shows of a tier) and a tooltip.
	import * as ToggleGroup from '#lib/components/ui/toggle-group/index.js';

	let {
		label,
		value = $bindable(),
		options,
		variant = 'default',
		onchange
	}: {
		label?: string;
		value: V;
		options: { value: V; label: string; count?: number; title?: string }[];
		variant?: 'default' | 'accent' | 'outline';
		onchange?: (value: V) => void;
	} = $props();

	function select(next: string) {
		// A click on the option that is on gives an empty value: the option stays on
		if (!next || next === value) return;
		value = next as V;
		onchange?.(value);
	}
</script>

<div class="flex flex-wrap items-center gap-2">
	{#if label}<span class="text-[12px] font-medium text-muted-foreground">{label}:</span>{/if}
	<ToggleGroup.Root type="single" {variant} {value} onValueChange={select} aria-label={label}>
		{#each options as option (option.value)}
			<ToggleGroup.Item value={option.value} title={option.title}>
				{option.label}
				{#if option.count != null}<span class="ml-0.5 text-[10.5px] font-semibold opacity-75">{option.count}</span>{/if}
			</ToggleGroup.Item>
		{/each}
	</ToggleGroup.Root>
</div>
