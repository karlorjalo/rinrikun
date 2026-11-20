import { matchAbout } from '../src/lib/format.js';
import { expect, numbers, test } from './helpers.js';

test('the tier filter shows only the shows of the tier', async ({ page }) => {
	await page.goto('/ratings');
	const cards = page.getByTestId('show-card');
	await expect(cards.first()).toBeVisible();
	const [total] = numbers(await page.getByTestId('ratings-count').textContent());
	await expect(cards).toHaveCount(total);

	const tierA = page.getByRole('radio', { name: /^A \d+$/ });
	const [inTier] = numbers(await tierA.textContent());
	await tierA.click();
	await expect(cards).toHaveCount(inTier);
	for (const card of await cards.all()) await expect(card.getByTitle('Tier A')).toBeVisible();
});

test('the detail window changes the tier of a show', async ({ page }) => {
	await page.goto('/ratings');
	// The list changes its order after the change, thus the test finds the card by the id of its show
	const id = await page.getByTestId('show-card').first().getAttribute('data-id');
	const card = page.locator(`[data-testid=show-card][data-id="${id}"]`);
	await expect(card.getByTitle('Tier S')).toBeVisible();
	await card.getByRole('heading').getByRole('button').click();

	const detail = page.getByTestId('detail');
	// The window opens without an open tooltip above its buttons
	await expect(page.getByRole('tooltip')).toHaveCount(0);
	await detail.getByRole('group', { name: 'Tier' }).getByRole('button', { name: 'C', exact: true }).click();
	await expect(detail.getByRole('group', { name: 'Tier' }).getByRole('button', { name: 'C', exact: true })).toHaveAttribute('aria-pressed', 'true');
	await page.keyboard.press('Escape');
	await expect(detail).toBeHidden();
	await expect(card.getByTitle('Tier C')).toBeVisible();
});

test('the detail window of a rated show shows the overview', async ({ page }) => {
	await page.goto('/ratings');
	const cards = page.getByTestId('show-card');
	await expect(cards.first()).toBeVisible();
	// A show with an overview. The list does not have the overview: the window gets the full show.
	let id = '';
	for (const card of await cards.all()) {
		const candidate = (await card.getAttribute('data-id'))!;
		const show = await (await page.request.get(`/api/show/${encodeURIComponent(candidate)}`)).json();
		if (show.overview) {
			id = candidate;
			break;
		}
	}
	expect(id).not.toBe('');
	await page.locator(`[data-testid=show-card][data-id="${id}"]`).getByRole('heading').getByRole('button').click();
	await expect(page.getByTestId('detail')).toContainText('An invented show for the tests');
});

test('the match of a card shows its tooltip', async ({ page }) => {
	await page.goto('/ratings');
	const card = page.getByTestId('show-card').first();
	await expect(card).toBeVisible();
	// The cards have no tooltip component of their own: one tooltip of the page serves them all
	await expect(page.getByTestId('ratings-grid').locator('[data-slot="tooltip-trigger"]')).toHaveCount(0);
	const id = (await card.getAttribute('data-id'))!;
	const show = await (await page.request.get(`/api/show/${encodeURIComponent(id)}`)).json();
	const match = card.getByTestId('match');
	await match.hover();
	const tooltip = page.getByRole('tooltip');
	await expect(tooltip).toHaveCount(1);
	await expect(tooltip).toBeVisible();
	await expect(tooltip).toHaveText(matchAbout(show));
	await expect(match).toHaveAttribute('aria-describedby', (await tooltip.getAttribute('id'))!);
	// The pointer leaves: the tooltip closes
	await page.mouse.move(0, 0);
	await expect(tooltip).toHaveCount(0);
});

test('the keyboard focus on a match shows its tooltip, and Escape closes it', async ({ page }) => {
	await page.goto('/ratings');
	const match = page.getByTestId('show-card').first().getByTestId('match');
	await expect(match).toBeVisible();
	await match.focus();
	const tooltip = page.getByRole('tooltip');
	await expect(tooltip).toBeVisible();
	await page.keyboard.press('Escape');
	await expect(tooltip).toHaveCount(0);
	await expect(match).toBeFocused();
});

test('"Not interested" has the shows that the user removed', async ({ page }) => {
	await page.goto('/ratings');
	const option = page.getByRole('radio', { name: /Not interested/ });
	await expect(option).toContainText(/\d/);
	const [removed] = numbers(await option.textContent());
	await option.click();
	await expect(page.getByTestId('show-card')).toHaveCount(removed);
});
