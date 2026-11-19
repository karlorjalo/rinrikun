import { expect, numbers, test } from './helpers.js';

test('the card has the numbers of the user, and a tier opens its ratings', async ({ page }) => {
	await page.goto('/');
	await expect(page.getByTestId('profile-counts')).toHaveText(/\d+ in library · \d+ watched · \d+ in catalog/);
	await expect(page.getByTestId('profile-recs')).toContainText('shown');
	await expect(page.getByTestId('profile-discover')).toContainText('By match:');

	const tier = page.getByTitle('View A tier ratings');
	await expect(tier).toHaveText(/A\s*\d+/);
	const [inTier] = numbers(await tier.textContent());
	await tier.click();
	await expect(page).toHaveURL(/\/ratings\?tier=A$/);
	await expect(page.getByRole('radio', { name: /^A \d+$/ })).toHaveAttribute('data-state', 'on');
	await expect(page.getByTestId('show-card')).toHaveCount(inTier);
});

test('the map has its controls: zoom, view, and the match gradient', async ({ page }) => {
	const matchRequests: string[] = [];
	page.on('request', (request) => {
		if (request.url().endsWith('/api/vector-map/match')) matchRequests.push(request.url());
	});
	await page.goto('/');
	const map = page.getByTestId('vector-map');
	const zoom = map.locator('.vector-zoom-level');
	await expect(zoom).toHaveText('100%');
	await map.getByLabel('Zoom in').click();
	await expect(zoom).toHaveText('150%');
	await map.getByLabel('Reset view').click();
	await expect(zoom).toHaveText('100%');

	await map.getByRole('radio', { name: 'Dots' }).click();
	await expect(map.locator('canvas')).toHaveAttribute('data-view', 'dots');

	// The page gets the match values only when the gradient is on
	expect(matchRequests).toHaveLength(0);
	await map.getByTestId('gradient-toggle').click();
	await expect(page.locator('html')).toHaveAttribute('data-gradient', 'on');
	await expect.poll(() => matchRequests.length).toBeGreaterThan(0);
});

test('the search of the map finds shows, goes to a show, and a click opens it', async ({ page }) => {
	await page.goto('/');
	const map = page.getByTestId('vector-map');
	const box = map.getByLabel('Find a show on the map');
	const count = map.locator('.vector-search-count');
	await box.fill('kissaten');
	await expect(count).toHaveText(/^\d+ found$/);
	const [found] = numbers(await count.textContent());

	// Enter moves the view to the first found show: it is then in the middle of the map
	await box.press('Enter');
	await expect(count).toHaveText(`1 / ${found}`);
	const canvas = map.locator('canvas');
	await expect.poll(async () => numbers(await map.locator('.vector-zoom-level').textContent())[0]).toBeGreaterThan(300);
	await page.waitForTimeout(700);
	// The map is below the first screen of the page: the pointer can go only to a place in view
	await canvas.scrollIntoViewIfNeeded();
	const area = (await canvas.boundingBox())!;
	await page.mouse.move(area.x + area.width / 2 - 4, area.y + area.height / 2 - 4);
	await page.mouse.move(area.x + area.width / 2, area.y + area.height / 2);
	await expect(map.locator('.vector-map-tooltip')).toContainText('喫茶店');
	await page.mouse.down();
	await page.mouse.up();
	await expect(page.getByTestId('detail')).toContainText('喫茶店');
	await page.keyboard.press('Escape');

	await box.press('Escape');
	await expect(box).toHaveValue('');
	await expect(count).toBeHidden();
});
