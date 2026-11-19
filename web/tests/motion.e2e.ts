import { expect, openTab, test } from './helpers.js';

// The loading bar, the fades, and the change of a tab with a long list

test('a slow tab shows the loading bar, and the bar goes when the page is there', async ({ page, request }) => {
	await page.goto('/settings');
	await request.post('/api/__delay', { data: { ms: 900 } });
	await openTab(page, 'Ratings');
	const bar = page.getByTestId('loading-bar');
	await expect(bar).toBeVisible();
	await expect(page.getByTestId('ratings-grid')).toBeVisible();
	await expect(bar).toBeHidden();
	await request.post('/api/__delay', { data: { ms: 0 } });
});

test('the detail window fades in and out', async ({ page }) => {
	await page.goto('/ratings');
	// A long fade, thus the test sees the window while it fades
	await page.addStyleTag({ content: ':root { --fade: 1500ms !important; }' });
	await page.getByTestId('show-card').first().getByRole('button').first().click();
	const detail = page.getByTestId('detail');
	await expect(detail).toBeVisible();
	// The window fades in. A window that closes while it is still almost invisible goes without a
	// fade, thus the test waits until it is half visible.
	await expect.poll(() => detail.evaluate((node) => Number(getComputedStyle(node).opacity))).toBeGreaterThan(0.4);
	await page.keyboard.press('Escape');
	// The window stays on the page while it fades, with the mark of the fade
	await expect(detail).toHaveAttribute('data-ending-style', '');
	await expect(detail).toBeHidden();
});

test('the Ratings tab shows all its cards after a change of the tab', async ({ page }) => {
	await page.goto('/ratings');
	const cards = page.getByTestId('show-card');
	const total = await cards.count();
	expect(total).toBeGreaterThan(0);
	await openTab(page, 'Settings');
	await openTab(page, 'Ratings');
	await expect(cards).toHaveCount(total);
});

test('the help card of the tiers closes and opens', async ({ page }) => {
	await page.goto('/ratings');
	const help = page.getByTestId('tier-help');
	const questions = help.getByText('Would I watch it again');
	const trigger = help.getByRole('button', { name: 'Which tier?' });
	const open = await questions.isVisible();
	await trigger.click();
	await expect(questions).toBeVisible({ visible: !open });
	await trigger.click();
	await expect(questions).toBeVisible({ visible: open });
});
