<script lang="ts" module>
	import { type VariantProps, tv } from "tailwind-variants";
	import { cn, type WithElementRef } from "#lib/utils.js";
	import type { HTMLAnchorAttributes, HTMLButtonAttributes } from "svelte/elements";

	// The buttons of the app. A button is a small card: a border, no shadow. The border color
	// shows the pointer. The variant "primary" is for the one main action of a group.
	export const buttonVariants = tv({
		base: "inline-flex shrink-0 cursor-pointer items-center justify-center gap-1.5 rounded-md border font-sans font-medium whitespace-nowrap no-underline transition-colors duration-150 outline-none select-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose disabled:pointer-events-none disabled:opacity-50",
		variants: {
			variant: {
				default: "border-border bg-card text-foreground hover:border-rose hover:bg-muted aria-expanded:border-rose",
				primary: "border-rose bg-rose text-rose-ink hover:opacity-90",
				ghost: "border-transparent bg-transparent text-muted-foreground hover:bg-muted hover:text-foreground",
				link: "border-transparent bg-transparent p-0 text-rose underline-offset-4 hover:underline",
			},
			size: {
				default: "px-3 py-1.5 text-[12.5px]",
				sm: "px-2.5 py-[3px] text-[12px]",
				// The answers of the Discover deck
				lg: "px-3.5 py-3 text-[14px] font-semibold",
				// A round button with one mark
				icon: "size-8 rounded-full p-0 text-[15px] leading-none",
				"icon-sm": "size-[26px] rounded-full p-0 text-[12px] leading-none",
			},
		},
		defaultVariants: {
			variant: "default",
			size: "default",
		},
	});

	export type ButtonVariant = VariantProps<typeof buttonVariants>["variant"];
	export type ButtonSize = VariantProps<typeof buttonVariants>["size"];

	export type ButtonProps = WithElementRef<HTMLButtonAttributes> &
		WithElementRef<HTMLAnchorAttributes> & {
			variant?: ButtonVariant;
			size?: ButtonSize;
		};
</script>

<script lang="ts">
	let {
		class: className,
		variant = "default",
		size = "default",
		ref = $bindable(null),
		href = undefined,
		type = "button",
		disabled,
		children,
		...restProps
	}: ButtonProps = $props();
</script>

{#if href}
	<a
		bind:this={ref}
		data-slot="button"
		class={cn(buttonVariants({ variant, size }), className)}
		href={disabled ? undefined : href}
		aria-disabled={disabled}
		role={disabled ? "link" : undefined}
		tabindex={disabled ? -1 : undefined}
		{...restProps}
	>
		{@render children?.()}
	</a>
{:else}
	<button
		bind:this={ref}
		data-slot="button"
		class={cn(buttonVariants({ variant, size }), className)}
		{type}
		{disabled}
		{...restProps}
	>
		{@render children?.()}
	</button>
{/if}
