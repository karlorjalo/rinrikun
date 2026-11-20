import { expect, numbers, test } from './helpers.js';

test('a key gives a tier, and Backspace takes it back', async ({ page }) => {
	await page.goto('/review');
	const note = page.getByTestId('title-note');
	const card = page.getByTestId('deck-card');
	await expect(card).toBeVisible();
	const [rated, total] = numbers(await note.textContent());
	const first = await card.getAttribute('data-id');

	await page.keyboard.press('5');
	await expect(note).toHaveText(`${rated + 1} of ${total} rated`);
	await expect(card).not.toHaveAttribute('data-id', first!);

	await page.keyboard.press('Backspace');
	await expect(note).toHaveText(`${rated} of ${total} rated`);
	await expect(card).toHaveAttribute('data-id', first!);
});

test('the next card comes before the answer of the server', async ({ page }) => {
	await page.goto('/review');
	const card = page.getByTestId('deck-card');
	await expect(card).toBeVisible();
	const first = await card.getAttribute('data-id');
	await page.request.post('/api/__delay', { data: { ms: 800 } });
	await page.keyboard.press('b');
	await expect(card).not.toHaveAttribute('data-id', first!, { timeout: 300 });
});

test('rate then undo keeps the order', async ({ page }) => {
	await page.goto('/review');
	const card = page.getByTestId('deck-card');
	await expect(card).toBeVisible();
	const first = (await card.getAttribute('data-id'))!;
	const before = (await (await page.request.get(`/api/show/${encodeURIComponent(first)}`)).json()).tier;
	await page.request.post('/api/__delay', { data: { ms: 400 } });
	await page.keyboard.press('a');
	await page.keyboard.press('Backspace');
	await page.waitForTimeout(1500);
	// The card of the show is on the screen again, and the server has the tier of before
	await expect(card).toHaveAttribute('data-id', first);
	const show = await (await page.request.get(`/api/show/${encodeURIComponent(first)}`)).json();
	expect(show.tier).toBe(before);
	const requests: string[] = await (await page.request.get('/api/__requests')).json();
	const changes = requests.filter((r) => r.includes('/api/weights'));
	expect(changes.map((r) => r.split(' ')[0])).toEqual(['POST', 'DELETE']);
});

test('a late answer of the server does not change the tier that the user chose', async ({ page }) => {
	await page.goto('/review');
	const card = page.getByTestId('deck-card');
	const note = page.getByTestId('title-note');
	await expect(card).toBeVisible();
	const start = await note.textContent();
	const first = (await card.getAttribute('data-id'))!;
	const before = (await (await page.request.get(`/api/show/${encodeURIComponent(first)}`)).json()).tier;
	await page.request.post('/api/__delay', { data: { ms: 400 } });
	await page.keyboard.press('a');
	await page.keyboard.press('Backspace');
	// The answer of the tier A is here, the answer of the undo is not
	await page.waitForTimeout(550);
	await page.keyboard.press('b');
	await page.keyboard.press('Backspace');
	await page.waitForTimeout(2500);
	// Each tier was taken back: the show has its tier of before, and the count is the count of the start
	await expect(card).toHaveAttribute('data-id', first);
	await expect(note).toHaveText(start!);
	const show = await (await page.request.get(`/api/show/${encodeURIComponent(first)}`)).json();
	expect(show.tier).toBe(before);
});

test('the deck ends with a message, and "Review all" shows the rated shows', async ({ page }) => {
	await page.goto('/review');
	const card = page.getByTestId('deck-card');
	await expect(card).toBeVisible();
	// Space goes to the next card. The deck of the mock has less than 20 shows without a tier.
	for (let n = 0; n < 20 && !(await page.getByTestId('deck-done').isVisible()); n++) {
		await page.keyboard.press('Space');
	}
	await expect(page.getByTestId('deck-done')).toContainText('Every show has a tier.');
	await page.getByRole('button', { name: 'Review all' }).click();
	await expect(card).toBeVisible();
	await expect(card).toContainText('1 / ');
});
