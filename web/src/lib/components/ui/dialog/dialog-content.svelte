<script lang="ts">
	// The window of a dialog: a card that floats above a dark page. It has no blur behind it and
	// it does not grow when it opens. The window and the dark page fade in and out ("fades" in
	// layout.css): bits-ui removes them only after the fade.
	import { Dialog as DialogPrimitive } from "bits-ui";
	import { cn, type WithoutChildrenOrChild } from "#lib/utils.js";
	import DialogOverlay from "./dialog-overlay.svelte";
	import DialogPortal from "./dialog-portal.svelte";
	import type { Snippet } from "svelte";
	import type { ComponentProps } from "svelte";

	let {
		ref = $bindable(null),
		class: className,
		overlayClass,
		portalProps,
		children,
		showCloseButton = true,
		...restProps
	}: WithoutChildrenOrChild<DialogPrimitive.ContentProps> & {
		portalProps?: WithoutChildrenOrChild<ComponentProps<typeof DialogPortal>>;
		children: Snippet;
		showCloseButton?: boolean;
		overlayClass?: string;
	} = $props();
</script>

<DialogPortal {...portalProps}>
	<DialogOverlay class={overlayClass} />
	<DialogPrimitive.Content
		bind:ref
		data-slot="dialog-content"
		class={cn(
			"fades fixed top-1/2 left-1/2 z-[100] flex max-h-[85vh] w-[calc(100%-32px)] max-w-[640px] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-lg border bg-card text-foreground shadow-float outline-none",
			className
		)}
		{...restProps}
	>
		{@render children?.()}
		{#if showCloseButton}
			<DialogPrimitive.Close
				data-slot="dialog-close"
				aria-label="Close"
				class="absolute top-3.5 right-3.5 z-10 flex size-8 cursor-pointer items-center justify-center rounded-full border bg-card text-[15px] leading-none text-muted-foreground transition-colors duration-150 hover:border-rose hover:bg-muted hover:text-foreground"
			>
				✕
			</DialogPrimitive.Close>
		{/if}
	</DialogPrimitive.Content>
</DialogPortal>
