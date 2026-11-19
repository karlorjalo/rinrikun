<script lang="ts">
	// The detail window of a show: its data, its synopsis and its tags, and what the user can do
	// with it: give a tier, mark it as watched, put it on the watch list, remove it from the
	// recommendations, find similar shows, and use it as the seed of a list.
	import { goto } from '$app/navigation';
	import type { Show, Tier } from '#lib/api/types.js';
	import { Button } from '#lib/components/ui/button/index.js';
	import * as Dialog from '#lib/components/ui/dialog/index.js';
	import { TIERS, displayTitles, formatScore, overviewHtml } from '#lib/format.js';
	import { detail } from '#lib/state/detail.svelte.js';
	import { library } from '#lib/state/library.svelte.js';
	import { seedHref, similarHref } from '#lib/links.js';
	import GuessText from './GuessText.svelte';
	import MatchText from './MatchText.svelte';
	import Poster from './Poster.svelte';

	// The window fades out when it closes. In that time it still shows the last show: `last`
	// keeps it until the fade ends (onOpenChangeComplete).
	let last = $state<Show | null>(null);
	$effect.pre(() => {
		if (detail.show) last = detail.show;
	});
	const show = $derived(detail.show ?? last);
	const titles = $derived(show ? displayTitles(show) : { main: '', sub: null });
	const inLibrary = $derived(!!show && (show.source === 'library' || (!!show.owned && !show.manual_watched)));
	let busy = $state(false);
	let content = $state<HTMLElement | null>(null);

	const TIER_COLOR: Record<Tier, string> = {
		S: 'var(--tier-s)',
		A: 'var(--tier-a)',
		B: 'var(--tier-b)',
		C: 'var(--tier-c)',
		D: 'var(--tier-d)'
	};

	/** Do one change. A second click in the time of the request does nothing, and a closed window changes nothing. */
	async function change(action: (show: Show) => Promise<void>) {
		if (!show || !detail.show || busy) return;
		busy = true;
		try {
			await action(show);
		} catch (error) {
			console.error('Failed to change the show', error);
		} finally {
			busy = false;
		}
	}

	const setTier = (tier: Tier | null) =>
		change(async (s) => {
			await library.setTier(s, tier);
			await library.refresh(s);
		});
	const toggleWatched = () =>
		change(async (s) => {
			await library.setWatched(s, !s.manual_watched);
			await library.refresh(s);
		});
	const toggleInterest = () => change((s) => library.setInterest(s, s.interest === 1 ? null : true, 'page'));
	const toggleDismissed = () => change((s) => library.setDismissed(s, !s.dismissed));

	function findSimilar() {
		if (!show) return;
		const id = show.id;
		detail.close();
		goto(similarHref(id));
	}

	function useAsSeed() {
		if (!show) return;
		const id = show.id;
		detail.close();
		goto(seedHref(id));
	}
</script>

<Dialog.Root
	open={!!detail.show}
	onOpenChange={(open) => !open && detail.close()}
	onOpenChangeComplete={(open) => {
		if (!open) last = null;
	}}
>
	{#if show}
		<!-- The window itself gets the focus when it opens. The first control in it is the match
		     text: the focus on that text would show its tooltip above the buttons. -->
		<Dialog.Content
			aria-describedby={undefined}
			data-testid="detail"
			bind:ref={content}
			onOpenAutoFocus={(event) => {
				event.preventDefault();
				content?.focus();
			}}
		>
			<div class="flex gap-[18px] border-b bg-[color-mix(in_srgb,var(--card)_96%,var(--accent))] px-6 pt-6 pb-[18px] max-[680px]:flex-col max-[680px]:items-center max-[680px]:text-center">
				<Poster src={show.poster} title={titles.main} large class="h-[156px] w-[108px]" />
				<div class="min-w-0 flex-1 pr-7 max-[680px]:pr-0">
					<div class="flex flex-wrap items-center gap-1.5 text-[12px] text-muted-foreground max-[680px]:justify-center">
						{#if inLibrary}
							<span class="rounded-sm bg-rose px-1.5 text-[11px] text-rose-ink">library</span>
						{:else if show.manual_watched}
							<span class="rounded-sm border border-rose/35 bg-rose/18 px-1.5 text-[11px] text-rose">watched</span>
						{/if}
						{#each [show.format?.toUpperCase(), show.year, show.genres?.slice(0, 3).join(', ')].filter(Boolean) as part, n (n)}
							{#if n > 0 || inLibrary || show.manual_watched}<span aria-hidden="true">·</span>{/if}
							<span>{part}</span>
						{/each}
					</div>
					<Dialog.Title class="mt-1.5 mb-1 font-serif text-[21px] leading-[1.35] font-bold">{titles.main}</Dialog.Title>
					{#if titles.sub}<div class="mb-1 text-[13px] text-muted-foreground">{titles.sub}</div>{/if}
					{#if show.studios?.length}
						<div class="mb-1.5 text-[12.5px] text-muted-foreground">
							Studio: <b class="font-medium text-foreground">{show.studios.join(', ')}</b>
						</div>
					{/if}
					<div class="mb-3 flex flex-wrap items-center gap-x-1.5 text-[13px] font-medium max-[680px]:justify-center">
						{#if formatScore(show.score)}<span class="text-rose">★ {formatScore(show.score)}</span>{/if}
						{#if show.match != null}<span aria-hidden="true">·</span><MatchText {show} />{/if}
						{#if show.tier_guess && !show.tier}<span aria-hidden="true">·</span><GuessText {show} />{/if}
						{#if show.similarity != null}<span aria-hidden="true">·</span><span>{Math.round(show.similarity)}% similar</span>{/if}
					</div>
					<div class="mt-2.5 flex flex-wrap gap-2 max-[680px]:justify-center">
						<Button variant="primary" onclick={findSimilar}>Find similar</Button>
						<Button onclick={useAsSeed} title="Recommend shows like this show">As seed</Button>
						{#if show.source !== 'library'}
							<Button
								onclick={toggleWatched}
								aria-pressed={!!show.manual_watched}
								class={show.manual_watched ? 'border-rose bg-rose/15 text-rose' : 'border-rose/35'}
								data-testid="toggle-watched">{show.manual_watched ? 'Watched' : '+ Watched'}</Button
							>
						{/if}
						{#if !show.owned}
							<Button
								onclick={toggleInterest}
								aria-pressed={show.interest === 1}
								class={show.interest === 1 ? 'border-rose text-rose' : ''}
								title={show.interest === 1 ? 'Take off the watch list' : 'Put on the watch list. Shows like it move up.'}
								data-testid="toggle-interest">{show.interest === 1 ? '♥ Interested · Undo' : '♥ Interested'}</Button
							>
							<Button
								onclick={toggleDismissed}
								class={show.dismissed ? 'border-tier-d text-tier-d' : ''}
								title={show.dismissed
									? 'Put back in the recommendations'
									: 'Remove from the recommendations. Shows like it move down.'}
								data-testid="toggle-dismissed">{show.dismissed ? '✕ Not interested · Undo' : '✕ Not interested'}</Button
							>
						{/if}
						{#if show.anilist_id}
							<Button href="https://anilist.co/anime/{show.anilist_id}" target="_blank" rel="noopener noreferrer">AniList ↗</Button>
						{/if}
					</div>
					<div class="mt-3.5 flex flex-wrap items-center gap-2.5 border-t border-border/60 pt-3.5 max-[680px]:justify-center">
						<span class="text-[12px] font-medium text-muted-foreground">Tier:</span>
						<div class="flex flex-wrap items-center gap-1.5" role="group" aria-label="Tier">
							{#each TIERS as tier (tier)}
								<button
									type="button"
									onclick={() => setTier(tier)}
									aria-pressed={show.tier === tier}
									style="--tier: {TIER_COLOR[tier]}"
									class="cursor-pointer rounded-sm border bg-card px-2.5 py-1 font-sans text-[12px] font-semibold text-muted-foreground transition-colors duration-100 hover:border-(--tier) hover:text-foreground aria-pressed:border-(--tier) aria-pressed:bg-(--tier) aria-pressed:text-white"
									>{tier}</button
								>
							{/each}
							{#if show.tier}
								<button
									type="button"
									onclick={() => setTier(null)}
									class="cursor-pointer border-0 bg-transparent px-1.5 py-1 font-sans text-[11px] text-muted-foreground hover:text-foreground hover:underline"
									>Clear</button
								>
							{/if}
						</div>
					</div>
				</div>
			</div>
			<div class="overflow-y-auto px-6 pt-5 pb-7">
				<h4 class="m-0 mb-2 font-serif text-[14.5px] font-semibold">Synopsis</h4>
				<div class="mb-[22px] text-[14px] leading-[1.7]">
					{#if show.overview}
						<!-- eslint-disable-next-line svelte/no-at-html-tags -- overviewHtml makes the text safe -->
						{@html overviewHtml(show.overview)}
					{:else}
						<p class="m-0 text-muted-foreground italic">No synopsis.</p>
					{/if}
				</div>
				{#if show.tags?.length}
					<h4 class="m-0 mb-2 font-serif text-[14.5px] font-semibold">Tags</h4>
					<div class="flex flex-wrap gap-1.5">
						{#each show.tags as tag, n (tag)}
							<span class="inline-flex items-center gap-1.5 rounded-sm border bg-muted px-2 py-[3px] text-[12px]">
								{tag}
								{#if show.tag_ranks?.[n]}
									<span class="text-[10.5px] font-medium text-muted-foreground">{show.tag_ranks[n]}%</span>
								{/if}
							</span>
						{/each}
					</div>
				{/if}
			</div>
		</Dialog.Content>
	{/if}
</Dialog.Root>
