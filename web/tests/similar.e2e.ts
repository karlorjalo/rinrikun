import { apiRequests, expect, openTab, test } from './helpers.js';

test('the tab without a show gets its examples from the ratings, not from the list of all titles', async ({ page, request }) => {
	await page.goto('/settings');
	// The log of the requests starts here (a body of JSON: see helpers.ts)
	expect((await request.post('/api/__reset', { data: {} })).ok()).toBe(true);
	await openTab(page, 'Similar');
	await expect(page.getByTestId('similar-examples').getByRole('link')).toHaveCount(5);
	expect(await apiRequests(request, '/api/shows')).toHaveLength(0);
	expect(await apiRequests(request, '/api/ratings')).not.toHaveLength(0);
});

test('the search box finds a show, and Enter shows its similar shows', async ({ page }) => {
	await page.goto('/similar');
	const box = page.getByTestId('title-search');
	const list = page.getByTestId('title-list');

	// One Latin letter finds too many shows: the list stays closed
	await box.pressSequentially('k');
	await expect(list).toBeHidden();
	await box.pressSequentially('issaten');
	await expect(list.getByRole('option').first()).toBeVisible();
	const picked = await list.getByRole('option').nth(1).locator('span').first().textContent();

	await page.keyboard.press('ArrowDown');
	await page.keyboard.press('Enter');
	await expect(list).toBeHidden();
	await expect(box).toHaveValue(picked!);
	await expect(page.getByTestId('similar-header')).toContainText(picked!);
	await expect(page.getByTestId('show-card')).toHaveCount(24);

	await page.getByTestId('similar-header').getByRole('radio', { name: '48' }).click();
	await expect(page.getByTestId('show-card')).toHaveCount(48);
});

test('a text without a match shows "No titles"', async ({ page }) => {
	await page.goto('/similar');
	await page.getByTestId('title-search').pressSequentially('zzzz');
	await expect(page.getByTestId('title-list')).toHaveText('No titles');
});

test('"Find similar" of the detail window opens the Similar tab for the show', async ({ page }) => {
	await page.goto('/ratings');
	const card = page.getByTestId('show-card').first();
	const title = await card.getByRole('heading').getByRole('button').textContent();
	await card.getByRole('heading').getByRole('button').click();
	await page.getByTestId('detail').getByRole('button', { name: 'Find similar' }).click();

	await expect(page).toHaveURL(/\/similar\?id=/);
	await expect(page.getByTestId('similar-header')).toContainText(title!);
	await expect(page.getByTestId('show-card').first()).toBeVisible();

	// The results stay when the user opens a different tab
	await openTab(page, 'Settings');
	await openTab(page, 'Similar');
	await expect(page.getByTestId('similar-header')).toContainText(title!);
});
