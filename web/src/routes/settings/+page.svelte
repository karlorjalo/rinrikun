<script lang="ts">
	// The Settings tab: choices for the look of the app. A setting has no text below its title.
	// The "i" of a setting, and the pointer on its options, show a picture of each option.
	import Hint from '#lib/components/Hint.svelte';
	import InfoDot from '#lib/components/InfoDot.svelte';
	import PageTitle from '#lib/components/PageTitle.svelte';
	import SettingPicture from '#lib/components/settings/SettingPicture.svelte';
	import * as ToggleGroup from '#lib/components/ui/toggle-group/index.js';
	import { SETTINGS } from '#lib/settings-list.js';
	import { settings, type SettingKey, type SettingValues } from '#lib/state/settings.svelte.js';

	function select(key: SettingKey, value: string) {
		// A click on the option that is on gives an empty value: the option stays on
		if (value) settings.set(key, value as SettingValues[typeof key]);
	}
</script>

{#snippet pictures(key: SettingKey)}
	{@const setting = SETTINGS.find((s) => s.key === key)!}
	<div class="flex gap-2.5">
		{#each setting.options as option (option.value)}
			{@const current = settings.values[key] === option.value}
			<figure class="m-0 min-w-0 flex-1 text-center" data-current={current}>
				<div class="rounded-md {current ? 'outline-2 outline-rose' : ''}">
					<SettingPicture setting={key} value={option.value} about={option.about} />
				</div>
				<figcaption
					class="mt-1.5 text-[11.5px] leading-[1.3] {current ? 'font-semibold text-rose' : 'text-muted-foreground'}"
				>
					{option.label}
				</figcaption>
			</figure>
		{/each}
	</div>
{/snippet}

<PageTitle title="Settings" />

<div class="rounded-lg border bg-card px-5 py-1">
	{#each SETTINGS as setting, n (setting.key)}
		<div
			class="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 py-4 {n ? 'border-t' : ''}"
			data-setting={setting.key}
		>
			<div class="flex items-center">
				<span class="font-serif text-[15.5px] font-semibold">{setting.title}</span>
				<InfoDot rich label="Show a picture of each option">
					{#snippet tip()}{@render pictures(setting.key)}{/snippet}
				</InfoDot>
			</div>
			<Hint rich>
				{#snippet tip()}{@render pictures(setting.key)}{/snippet}
				{#snippet children(props)}
					<div {...props}>
						<ToggleGroup.Root
							type="single"
							variant="outline"
							size="lg"
							value={settings.values[setting.key]}
							onValueChange={(value) => select(setting.key, value)}
							aria-label={setting.title}
						>
							{#each setting.options as option (option.value)}
								<ToggleGroup.Item value={option.value}>{option.label}</ToggleGroup.Item>
							{/each}
						</ToggleGroup.Root>
					</div>
				{/snippet}
			</Hint>
		</div>
	{/each}
</div>
