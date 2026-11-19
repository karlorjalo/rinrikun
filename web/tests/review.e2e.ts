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
