<script lang="ts">
	// Cherry blossom petals fall behind the page header. The values are fixed, not random, so that
	// the page looks the same each time. The style sheet hides the petals if the setting is off or
	// if the system asks for less motion.
	// position (% of the width), size (px), time of one fall (s), start (s), drift (px), angle (deg), opacity
	const PETALS = [
		[3, 11, 15, 2, 70, 20, 0.7],
		[11, 8, 19, 9, 40, 110, 0.55],
		[18, 12, 13, 5, 90, 200, 0.75],
		[26, 9, 17, 12, 55, 60, 0.6],
		[34, 7, 21, 1, 35, 300, 0.5],
		[42, 10, 14, 7, 80, 150, 0.7],
		[50, 8, 18, 14, 45, 250, 0.55],
		[58, 12, 16, 3, 95, 30, 0.75],
		[66, 9, 20, 10, 50, 180, 0.6],
		[74, 11, 13, 6, 75, 90, 0.7],
		[82, 7, 22, 16, 30, 330, 0.5],
		[89, 10, 15, 11, 65, 130, 0.65],
		[95, 9, 18, 4, 40, 270, 0.6],
		[46, 6, 24, 18, 25, 10, 0.45]
	];
</script>

<div class="petals" aria-hidden="true">
	{#each PETALS as [x, size, time, start, drift, turn, alpha], n (n)}
		<i
			class="petal"
			style="--x:{x}%;--size:{size}px;--time:{time}s;--delay:-{start}s;--drift:{drift}px;--turn:{turn}deg;--alpha:{alpha}"
		></i>
	{/each}
</div>
