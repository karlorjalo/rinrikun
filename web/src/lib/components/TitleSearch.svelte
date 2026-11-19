<script lang="ts">
	// The search box for a title, with the list of the shows that the text finds. An arrow key
	// moves in the list, Enter selects the show that is marked, and Escape closes the list.
	//
	// Each word of the text must be in one of the titles of a show. The list has the 10 best shows:
	// see `searchRank`.
	import { Combobox } from 'bits-ui';
	import type { Title } from '#lib/api/types.js';
	import { displayTitles } from '#lib/format.js';
	import { longEnough } from '#lib/search.js';
	import { titles } from '#lib/state/titles.svelte.js';
	import Poster from './show/Poster.svelte';
	import StateBadge from './show/StateBadge.svelte';

	let {
		shown = '',
		onpick
	}: {
		/** The title of the show that is selected now. The box shows it until the user types. */
		shown?: string;
		onpick: (title: Title) => void;
	} = $props();

	let text = $state('');
	let open = $state(false);
	// The selection of the list. It is empty again after each selection, so that the user can
	// select the same show a second time.
	let value = $state('');
	let bar = $state<HTMLElement | null>(null);
	let input = $state<HTMLInputElement | null>(null);

	$effect(() => {
		text = shown;
	});
	$effect(() => {
		titles.load();
	});

	const valid = $derived(longEnough(text));
	const found = $derived(valid && open ? titles.find(text, 10) : []);

	function pick(id: string) {
		const title = found.find((item) => item.id === id);
		queueMicrotask(() => (value = ''));
		if (!title) return;
		text = displayTitles(title).main;
		open = false;
		onpick(title);
	}

	function clear() {
		text = '';
		open = false;
		input?.focus();
	}

	/** The second line of a row: the other title of the show, and its year */
	function about(title: Title): string {
		const { sub } = displayTitles(title);
		// A show of the library has one title. The line then has its first other title.
		return [sub ?? title.aka?.[0], title.year].filter(Boolean).join(' · ');
	}
</script>

<Combobox.Root type="single" bind:open bind:value onValueChange={pick} inputValue={text} loop>
	<div
		bind:this={bar}
		class="flex items-center rounded-md border bg-card transition-[border-color,box-shadow] duration-150 focus-within:border-rose focus-within:shadow-[0_0_0_3px_color-mix(in_srgb,var(--accent)_18%,transparent)]"
	>
		<svg class="ml-3.5 flex-none text-muted-foreground" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
			<circle cx="11" cy="11" r="7" /><path d="M21 21l-4.35-4.35" />
		</svg>
		<Combobox.Input
			bind:ref={input}
			placeholder="Search a title…"
			aria-label="Search a title"
			autocomplete="off"
			spellcheck={false}
			class="min-w-0 flex-1 border-0 bg-transparent py-3 pr-3.5 pl-2.5 font-sans text-[15px] text-foreground outline-none placeholder:text-muted-foreground"
			oninput={(event) => {
				text = event.currentTarget.value;
				if (!longEnough(text)) open = false;
			}}
			data-testid="title-search"
		/>
		{#if text}
			<button
				type="button"
				class="mr-2 flex size-[26px] flex-none cursor-pointer items-center justify-center rounded-full border-0 bg-transparent text-[13px] text-muted-foreground hover:bg-muted hover:text-foreground"
				aria-label="Clear search"
				onclick={clear}>✕</button
			>
		{/if}
	</div>
	{#if valid}
		<Combobox.Portal>
			<Combobox.Content
				customAnchor={bar}
				sideOffset={6}
				class="z-[90] max-h-[380px] w-(--bits-combobox-anchor-width) overflow-y-auto rounded-md border bg-card shadow-float"
				data-testid="title-list"
			>
				{#each found as title (title.id)}
					{@const names = displayTitles(title)}
					<Combobox.Item
						value={title.id}
						label={names.main}
						class="flex cursor-pointer items-center gap-3 border-b border-border/60 px-3 py-2 last:border-b-0 data-highlighted:bg-muted"
					>
						<Poster src={title.poster} title={names.main} letter="text-[14px]" class="h-[42px] w-[30px] rounded-sm" />
						<div class="min-w-0 flex-1">
							<div class="flex items-center gap-1.5 text-[14px] leading-[1.3] font-medium">
								<span class="overflow-hidden text-ellipsis whitespace-nowrap">{names.main}</span>
								<StateBadge show={title} />
							</div>
							{#if about(title)}
								<div class="mt-px overflow-hidden text-[12px] text-ellipsis whitespace-nowrap text-muted-foreground">{about(title)}</div>
							{/if}
						</div>
					</Combobox.Item>
				{:else}
					<div class="px-3 py-2 text-[14px] text-muted-foreground">{titles.loaded ? 'No titles' : 'Loading…'}</div>
				{/each}
			</Combobox.Content>
		</Combobox.Portal>
	{/if}
</Combobox.Root>
