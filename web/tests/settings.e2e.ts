import { expect, test } from './helpers.js';

test('a setting changes the page at once, and the browser keeps it', async ({ page }) => {
	await page.goto('/settings');
	const root = page.locator('html');
	await page.locator('[data-setting=font]').getByRole('radio', { name: 'Sans only' }).click();
	await expect(root).toHaveAttribute('data-font', 'sans');
	await page.locator('[data-setting=petals]').getByRole('radio', { name: 'Off' }).click();
	await expect(root).toHaveAttribute('data-petals', 'off');

	await page.reload();
	await expect(root).toHaveAttribute('data-font', 'sans');
	await expect(page.locator('[data-setting=font]').getByRole('radio', { name: 'Sans only' })).toHaveAttribute('data-state', 'on');
});

test('the theme button changes between the light look and the dark look', async ({ page }) => {
	await page.goto('/settings');
	const root = page.locator('html');
	const before = await root.getAttribute('data-theme');
	await page.getByRole('button', { name: /theme/i }).click();
	await expect(root).toHaveAttribute('data-theme', before === 'dark' ? 'light' : 'dark');
});

test('each tab has its own address, and an address opens its tab', async ({ page }) => {
	for (const [path, heading] of [
		['/review', 'Library review'],
		['/discover', 'Discover'],
		['/ratings', 'Ratings'],
		['/settings', 'Settings']
	]) {
		await page.goto(path);
		await expect(page.getByRole('heading', { level: 2, name: heading })).toBeVisible();
	}
});
