<script lang="ts">
	// The box of a tooltip. The usual box is dark with one short text. The variant "rich" is a
	// card for a text with paragraphs or for pictures.
	import { Tooltip as TooltipPrimitive } from "bits-ui";
	import { cn } from "#lib/utils.js";
	import type { WithoutChildrenOrChild } from "#lib/utils.js";
	import TooltipPortal from "./tooltip-portal.svelte";
	import type { ComponentProps } from "svelte";

	let {
		ref = $bindable(null),
		class: className,
		sideOffset = 8,
		side = "bottom",
		rich = false,
		children,
		portalProps,
		...restProps
	}: TooltipPrimitive.ContentProps & {
		rich?: boolean;
		portalProps?: WithoutChildrenOrChild<ComponentProps<typeof TooltipPortal>>;
	} = $props();
</script>

<TooltipPortal {...portalProps}>
	<TooltipPrimitive.Content
		bind:ref
		data-slot="tooltip-content"
		{sideOffset}
		{side}
		collisionPadding={8}
		class={cn(
			"fades-fast z-[1000] w-fit rounded-md text-left font-sans text-[12px] leading-[1.55] font-normal",
			rich
				? "max-w-[min(372px,calc(100vw-16px))] border bg-card p-3 text-foreground shadow-float"
				: "max-w-[290px] bg-foreground px-[11px] py-2 text-background shadow-control",
			className
		)}
		{...restProps}
	>
		{@render children?.()}
	</TooltipPrimitive.Content>
</TooltipPortal>
