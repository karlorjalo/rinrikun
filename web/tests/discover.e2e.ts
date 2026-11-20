import { expect, numbers, openTab, test } from './helpers.js';

test('the keys give an answer, and Backspace takes it back', async ({ page }) => {
	await page.goto('/discover');
	const note = page.getByTestId('title-note');
	const card = page.getByTestId('deck-card');
	const count = page.getByTestId('watch-count');
	await expect(card).toBeVisible();
	const [answers, interested, refused] = numbers(await note.textContent());
	const onList = Number(await count.textContent());
	const first = await card.getAttribute('data-id');

	await page.keyboard.press('i');
	await expect(note).toHaveText(`${answers + 1} answers · ${interested + 1} interested · ${refused} not interested`);
	await expect(count).toHaveText(String(onList + 1));
	await expect(card).not.toHaveAttribute('data-id', first!);

	await page.keyboard.press('n');
	await expect(note).toHaveText(`${answers + 2} answers · ${interested + 1} interested · ${refused + 1} not interested`);

	// The deck does one change at a time: the second key comes after the first answer is back
	await page.keyboard.press('Backspace');
	await expect(note).toHaveText(`${answers + 1} answers · ${interested + 1} interested · ${refused} not interested`);
	await page.keyboard.press('Backspace');
	await expect(note).toHaveText(`${answers} answers · ${interested} interested · ${refused} not interested`);
	await expect(count).toHaveText(String(onList));
	await expect(card).toHaveAttribute('data-id', first!);
});

test('"Seen it" shows the tier buttons, and Escape goes back', async ({ page }) => {
	await page.goto('/discover');
	const card = page.getByTestId('deck-card');
	await expect(card).toBeVisible();
	const first = await card.getAttribute('data-id');

	await page.keyboard.press('w');
	await expect(page.getByTestId('tier-buttons')).toBeVisible();
	await page.keyboard.press('Escape');
	await expect(page.getByTestId('answer-yes')).toBeVisible();
	await expect(card).toHaveAttribute('data-id', first!);

	// With a tier the show goes to the shows of the user, and the deck goes to the next card
	await page.getByTestId('answer-seen').click();
	await page.keyboard.press('4');
	await expect(card).not.toHaveAttribute('data-id', first!);
	await openTab(page, 'Ratings');
	await page.getByRole('radio', { name: /Manual/ }).click();
	await expect(page.locator(`[data-testid=show-card][data-id="${first}"]`)).toBeVisible();
});

test('a frame opens the viewer, and the keys of the deck do nothing while it is open', async ({ page }) => {
	await page.goto('/discover');
	const card = page.getByTestId('deck-card');
	const frames = page.getByTestId('deck-frames').getByRole('button');
	await expect(card).toBeVisible();
	// Not each show has more than one frame: go to a card that has
	for (let n = 0; n < 12 && (await frames.count()) < 2; n++) {
		await page.keyboard.press('Space');
		await page.waitForTimeout(150);
	}
	const total = await frames.count();
	expect(total).toBeGreaterThan(1);
	const shown = await card.getAttribute('data-id');

	await frames.first().click();
	const viewer = page.getByTestId('frame-viewer');
	await expect(viewer).toContainText(`1 of ${total}`);
	await page.keyboard.press('ArrowRight');
	await expect(viewer).toContainText(`2 of ${total}`);
	await page.keyboard.press('ArrowLeft');
	await page.keyboard.press('ArrowLeft');
	await expect(viewer).toContainText(`${total} of ${total}`);
	await page.keyboard.press('Escape');
	await expect(viewer).toBeHidden();
	await expect(card).toHaveAttribute('data-id', shown!);
});

test('the watch list takes a show off, puts it back, and stays open behind the detail window', async ({ page }) => {
	await page.goto('/discover');
	const count = page.getByTestId('watch-count');
	await expect(count).not.toHaveText('0');
	const onList = Number(await count.textContent());

	await page.getByTestId('watch-button').click();
	const panel = page.getByTestId('watch-panel');
	const rows = panel.getByRole('listitem');
	await expect(rows).toHaveCount(onList);

	const row = rows.first();
	await row.getByRole('button', { name: /off the watch list/ }).click();
	await expect(count).toHaveText(String(onList - 1));
	await expect(rows).toHaveCount(onList);
	await row.getByRole('button', { name: /back on the watch list/ }).click();
	await expect(count).toHaveText(String(onList));

	await rows.nth(1).getByTitle('Details').click();
	const detail = page.getByTestId('detail');
	await expect(detail).toBeVisible();
	await page.keyboard.press('Escape');
	await expect(detail).toBeHidden();
	await expect(panel).toBeVisible();

	await rows.first().getByRole('button', { name: /off the watch list/ }).click();
	await page.keyboard.press('Escape');
	await expect(panel).toBeHidden();
	await expect(count).toHaveText(String(onList - 1));
	// A show that the user took off the list does not come back after the list closes
	await page.getByTestId('watch-button').click();
	await expect(rows).toHaveCount(onList - 1);
});

test('the deck keeps its card when the user opens a different tab', async ({ page }) => {
	await page.goto('/discover');
	const card = page.getByTestId('deck-card');
	await expect(card).toBeVisible();
	await page.keyboard.press('Space');
	const shown = await card.getAttribute('data-id');

	await openTab(page, 'Settings');
	await expect(card).toBeHidden();
	await openTab(page, 'Discover');
	await expect(card).toHaveAttribute('data-id', shown!);
});
