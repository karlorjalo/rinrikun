<script lang="ts" module>
	import { type VariantProps, tv } from "tailwind-variants";

	// A small switch of a filter bar: "Tier", "Usual kinds", "On". The option that is on has a
	// grey background. The variant "accent" marks the option with the rose color: it is for a
	// choice that changes what the page computes, such as the formula.
	export const toggleVariants = tv({
		base: "inline-flex cursor-pointer items-center justify-center gap-1 rounded-sm border border-transparent bg-transparent font-sans text-muted-foreground whitespace-nowrap transition-colors duration-100 outline-none select-none hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-rose disabled:pointer-events-none disabled:opacity-50",
		variants: {
			variant: {
				default: "data-[state=on]:border-border data-[state=on]:bg-muted data-[state=on]:font-medium data-[state=on]:text-foreground",
				accent: "data-[state=on]:border-rose data-[state=on]:font-semibold data-[state=on]:text-rose data-[state=on]:hover:bg-transparent",
				// An option with a visible border in each state: the options of a setting
				outline: "border-border data-[state=on]:border-rose data-[state=on]:font-semibold data-[state=on]:text-rose",
			},
			size: {
				default: "px-[9px] py-[3px] text-[12px]",
				sm: "px-[7px] py-0.5 text-[11px]",
				lg: "px-[9px] py-[3px] text-[12.5px]",
			},
		},
		defaultVariants: {
			variant: "default",
			size: "default",
		},
	});

	export type ToggleVariant = VariantProps<typeof toggleVariants>["variant"];
	export type ToggleSize = VariantProps<typeof toggleVariants>["size"];
	export type ToggleVariants = VariantProps<typeof toggleVariants>;
</script>

<script lang="ts">
	import { Toggle as TogglePrimitive } from "bits-ui";
	import { cn } from "#lib/utils.js";

	let {
		ref = $bindable(null),
		pressed = $bindable(false),
		class: className,
		size = "default",
		variant = "default",
		...restProps
	}: TogglePrimitive.RootProps & {
		variant?: ToggleVariant;
		size?: ToggleSize;
	} = $props();
</script>

<TogglePrimitive.Root
	bind:ref
	bind:pressed
	data-slot="toggle"
	class={cn(toggleVariants({ variant, size }), className)}
	{...restProps}
/>
