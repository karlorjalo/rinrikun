<script lang="ts" module>
	import { getContext, setContext } from "svelte";
	import type { ToggleVariants } from "#lib/components/ui/toggle/index.js";

	export function setToggleGroupCtx(props: ToggleVariants) {
		setContext("toggleGroup", props);
	}

	export function getToggleGroupCtx() {
		return getContext<Required<ToggleVariants>>("toggleGroup");
	}
</script>

<script lang="ts">
	// A group of switches of which one is on (type "single") or more than one (type "multiple").
	// The items get the variant and the size of the group.
	import { ToggleGroup as ToggleGroupPrimitive } from "bits-ui";
	import { cn } from "#lib/utils.js";

	let {
		ref = $bindable(null),
		value = $bindable(),
		class: className,
		size = "default",
		variant = "default",
		...restProps
	}: ToggleGroupPrimitive.RootProps & ToggleVariants = $props();

	setToggleGroupCtx({
		get variant() {
			return variant;
		},
		get size() {
			return size;
		},
	});
</script>

<!--
Discriminated Unions + Destructing (required for bindable) do not
get along, so we shut typescript up by casting `value` to `never`.
-->
<ToggleGroupPrimitive.Root
	bind:value={value as never}
	bind:ref
	data-slot="toggle-group"
	class={cn("flex w-fit flex-row flex-wrap items-center gap-1", className)}
	{...restProps}
/>
