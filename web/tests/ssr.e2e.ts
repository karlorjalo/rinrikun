import { expect, test } from './helpers.js';

// The server renders each tab with its data: the page has its content before any script runs.
test.describe('without JavaScript', () => {
	test.use({ javaScriptEnabled: false });

	test('the tabs have their data', async ({ page }) => {
		await page.goto('/');
		await expect(page.getByTestId('profile-counts')).toHaveText(/\d+ in library/);
		await expect(page.getByTestId('profile-discover')).toContainText('answers');

		await page.goto('/ratings');
		const [total] = (await page.getByTestId('ratings-count').textContent())!.match(/\d+/)!.map(Number);
		await expect(page.getByTestId('show-card')).toHaveCount(total);

		await page.goto('/review');
		await expect(page.getByTestId('deck-card')).toBeVisible();
		await expect(page.getByTestId('title-note')).toHaveText(/\d+ of \d+ rated/);

		await page.goto('/discover');
		await expect(page.getByTestId('deck-card')).toBeVisible();
		await expect(page.getByTestId('watch-count')).not.toHaveText('0');

		await page.goto('/recommendations');
		await expect(page.getByTestId('show-card')).toHaveCount(40);

		await page.goto('/similar');
		await expect(page.getByTestId('similar-examples').getByRole('link')).toHaveCount(5);
	});

	test('the filters and the show of a tab come from the address', async ({ page }) => {
		await page.goto('/ratings?tier=A&sort=title');
		const cards = page.getByTestId('show-card');
		await expect(cards.first()).toBeVisible();
		for (const card of await cards.all()) await expect(card.getByTitle('Tier A')).toBeVisible();
		await expect(page.getByRole('radio', { name: /^A \d+$/ })).toHaveAttribute('data-state', 'on');

		await page.goto('/similar');
		const example = page.getByTestId('similar-examples').getByRole('link').first();
		const name = await example.textContent();
		await page.goto((await example.getAttribute('href'))!);
		await expect(page.getByTestId('similar-header')).toContainText(name!.trim());
		await expect(cards).toHaveCount(24);

		await page.goto('/recommendations?format=movie');
		const shown = await cards.count();
		expect(shown).toBeLessThan(40);
		await expect(page.getByTestId('recs-filters').getByRole('radio', { name: 'Movie' })).toHaveAttribute('data-state', 'on');
	});

	test('a show that does not exist gives the page "Not found"', async ({ page }) => {
		const answer = await page.goto('/similar?id=al:0');
		expect(answer?.status()).toBe(404);
		await expect(page.getByRole('heading', { name: 'Not found' })).toBeVisible();
	});
});

test('the server renders the theme and the settings of the cookies', async ({ page, context, baseURL }) => {
	await context.addCookies([
		{ name: 'rinrikun-theme', value: 'dark', url: baseURL! },
		{ name: 'rinrikun-settings', value: encodeURIComponent(JSON.stringify({ font: 'sans', petals: 'off' })), url: baseURL! }
	]);
	const html = await (await page.request.get('/settings')).text();
	expect(html).toMatch(/<html[^>]*data-theme="dark"/);
	expect(html).toMatch(/<html[^>]*data-font="sans"/);
	expect(html).toMatch(/<html[^>]*data-petals="off"/);

	await page.goto('/settings');
	await expect(page.locator('[data-setting=font]').getByRole('radio', { name: 'Sans only' })).toHaveAttribute('data-state', 'on');
	// A change in the page goes into the cookie, thus the next render of the server has it
	await page.locator('[data-setting=font]').getByRole('radio', { name: 'Serif titles' }).click();
	const next = await (await page.request.get('/settings')).text();
	expect(next).toMatch(/<html[^>]*data-font="mixed"/);
});
