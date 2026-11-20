<script lang="ts">
	// The Profile tab: the numbers of the user (the ratings, what the user did with the
	// recommendations, the answers of the Discover deck), and the map of all shows.
	//
	// The card has only the numbers. The text about them is in the tooltip of the "i". The server
	// renders the card with its data (+page.server.ts).
	import InfoDot from '#lib/components/InfoDot.svelte';
	import VectorMap from '#lib/components/map/VectorMap.svelte';
	import TierPill from '#lib/components/show/TierPill.svelte';
	import { TIERS, displayTitles } from '#lib/format.js';
	import { mapStore } from '#lib/state/map.svelte.js';
	import { tierHref } from '#lib/links.js';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const { profile, recLog, interest } = $derived(data);

	const number = (value: number) => value.toLocaleString('en-US');

	const counts = $derived.by(() => {
		// A show in the library is not always a show that the user watched. Thus the text does not say "watched" for it.
		const inLibrary = profile.library_count ?? profile.owned_count;
		const marked = profile.owned_count - inLibrary;
		return [`${inLibrary} in library`, marked > 0 ? `${marked} watched` : null, `${number(profile.total_count)} in catalog`].filter(Boolean).join(' · ');
	});

	const since = $derived(
		recLog?.since ? new Date(recLog.since + 'T00:00:00').toLocaleDateString('en-GB', { year: 'numeric', month: 'short', day: 'numeric' }) : ''
	);
	const aboutRecs = $derived.by(() => {
		let text = 'New franchises that the lists showed you, and how many you added or removed later.';
		// The comparison of the two formulas has a use only after the user saw lists of the two
		const formulas = recLog?.formulas;
		if (formulas?.['no links']?.shown && formulas.links) {
			const one = (name: 'links' | 'no links', label: string) =>
				`${label}: ${formulas[name].shown} shown, ${formulas[name].added} added, ${formulas[name].removed} removed.`;
			text += ` ${one('links', 'With crowd links')} ${one('no links', 'Without crowd links')} A show counts for the first list that gave it.`;
		}
		return text;
	});

	/** The groups of the match that have answers, with their names: "99+", "95–99", "below 80" */
	const groups = $derived(
		(interest?.groups ?? [])
			.filter((group) => group.answers)
			.map((group) => {
				const low = Math.round(group.low);
				const high = Math.round(group.high);
				return { ...group, name: high >= 100 ? `${low}+` : low <= 0 ? `below ${high}` : `${low}–${high}` };
			})
	);
	const aboutDiscover = $derived.by(() => {
		let text = 'Your answers in the Discover deck.';
		if (groups.length) text += ' The second row has the "interested" answers of all answers, by match. With a good match, a higher group has a larger part.';
		if (groups.length && interest?.popular) text += ` It counts only cards from the ${number(interest.popular)} most popular anime.`;
		if (interest?.model) {
			text += ` The taste model puts an interested show above a not-interested show in ${Math.round(100 * interest.model.auc)}% of the pairs, for answers that it does not know.`;
		}
		return text;
	});

	// A part of the card. A line divides two parts: a part is not a box in the card.
	const part = 'mt-4 border-t pt-4';
	const partTitle = 'mb-2 flex flex-wrap items-center justify-between gap-1.5 font-serif text-[13.5px] font-semibold';
	const row = 'flex flex-wrap items-center gap-3.5';
</script>

{#snippet stat(count: number, label: string)}
	<span class="flex items-center gap-1.5 text-[12.5px] text-muted-foreground"><span class="font-semibold text-foreground">{number(count)}</span> {label}</span>
{/snippet}

<section class="mb-7 rounded-lg border bg-card p-6 max-[680px]:px-3.5 max-[680px]:py-[18px]" data-testid="profile-card">
	<div class="flex flex-wrap items-start justify-between gap-5 max-[680px]:flex-col max-[680px]:gap-3.5">
		<h2 class="m-0 font-serif text-[24px] font-bold"><span class="petal-mark heading" aria-hidden="true"></span>Taste profile</h2>
		<span class="text-[13px] text-muted-foreground" data-testid="profile-counts">{counts}</span>
	</div>

	<div class={part}>
		<div class={partTitle}><span>Ratings</span></div>
		<div class={row}>
			{#each TIERS as tier (tier)}
				<a
					href={tierHref(tier)}
					class="flex items-center gap-1.5 rounded-sm px-1.5 py-[3px] font-sans text-[12.5px] text-foreground no-underline transition-colors duration-100 hover:bg-muted"
					title="View {tier} tier ratings"
				>
					<TierPill {tier} /> <span class="font-semibold" data-tier-count={tier}>{profile.tier_summary[tier] ?? 0}</span>
				</a>
			{/each}
			<span class="flex items-center gap-1.5 text-[12.5px] text-muted-foreground">
				<span class="text-[11.5px]">Unrated:</span> <span class="font-semibold text-foreground">{profile.tier_summary.unrated ?? 0}</span>
			</span>
		</div>
	</div>

	{#if recLog?.shown}
		<div class={part} data-testid="profile-recs">
			<div class={partTitle}>
				<span>Recommendations<InfoDot text={aboutRecs} label="More about these numbers" /></span>
				<span class="font-sans text-[12px] font-normal text-muted-foreground">since {since}</span>
			</div>
			<div class={row}>
				{@render stat(recLog.shown, 'shown')}
				{@render stat(recLog.added, 'added')}
				{@render stat(recLog.removed || 0, 'removed')}
				{#each TIERS.filter((tier) => recLog?.tiers[tier]) as tier (tier)}
					<span class="flex items-center gap-1.5 text-[12.5px]"><TierPill {tier} /> <span class="font-semibold">{recLog.tiers[tier]}</span></span>
				{/each}
				{#if recLog.unrated}{@render stat(recLog.unrated, 'unrated')}{/if}
			</div>
			{#if recLog.shows.length}
				<div class="mt-2 flex flex-wrap gap-x-3.5 gap-y-1.5 text-[12.5px] text-muted-foreground">
					{#each recLog.shows.slice(0, 6) as show (show.id)}
						<span>{#if show.tier}<TierPill tier={show.tier} />{' '}{/if}{displayTitles(show).main}</span>
					{/each}
				</div>
			{/if}
		</div>
	{/if}

	{#if interest?.answers}
		<div class={part} data-testid="profile-discover">
			<div class={partTitle}><span>Discover<InfoDot text={aboutDiscover} label="More about these numbers" /></span></div>
			<div class={row}>
				{@render stat(interest.answers, 'answers')}
				{@render stat(interest.interested, 'interested')}
				{@render stat(interest.not_interested, 'not interested')}
			</div>
			{#if groups.length}
				<div class="{row} mt-2">
					<span class="text-[12.5px] text-muted-foreground">By match:</span>
					{#each groups as group (group.low)}
						<span class="flex items-center gap-1.5 text-[12.5px]">
							<span class="text-muted-foreground">{group.name}</span> <span class="font-semibold">{group.interested}/{group.answers}</span>
						</span>
					{/each}
				</div>
			{/if}
		</div>
	{/if}
</section>

<!-- The map shows the S-tier shows as posters -->
<VectorMap title="Taste map" highlight={mapStore.topTier()} highlightLabel="S tier" highlightKind="tier" />
