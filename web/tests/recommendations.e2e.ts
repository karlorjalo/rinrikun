import type { Page } from '@playwright/test';
import { expect, test } from './helpers.js';

/** The story of the list plays one time in a new browser. Most tests start after that time. */
async function storySeen(page: Page) {
	await page.addInitScript(() => localStorage.setItem('rinrikun-story-seen', '1'));
}

/** The addresses of the requests for a list, in their order */
function listRequests(page: Page): URL[] {
	const requests: URL[] = [];
	page.on('request', (request) => {
		const url = new URL(request.url());
		if (url.pathname === '/api/recommend') requests.push(url);
	});
	return requests;
}

test('a filter of the page asks for no new list, and a formula option asks for one', async ({ page }) => {
	await storySeen(page);
	const requests = listRequests(page);
	await page.goto('/recommendations');
	const cards = page.getByTestId('show-card');
	const filters = page.getByTestId('recs-filters');
	await expect(cards).toHaveCount(40);
	expect(requests).toHaveLength(1);
	expect(requests[0].searchParams.get('kinds')).toBe('usual');
	expect(requests[0].searchParams.get('links')).toBe('true');
	expect(requests[0].searchParams.get('new_only')).toBe('true');

	await filters.getByRole('radio', { name: 'Movie' }).click();
	await expect(cards).not.toHaveCount(40);
	await filters.getByRole('radio', { name: 'All', exact: true }).click();
	await expect(cards).toHaveCount(40);
	expect(requests).toHaveLength(1);

	await filters.getByRole('radio', { name: 'All kinds' }).click();
	await expect.poll(() => requests.length).toBe(2);
	expect(requests[1].searchParams.get('kinds')).toBe('all');
	await filters.getByRole('radio', { name: 'Off' }).click();
	await expect.poll(() => requests.length).toBe(3);
	expect(requests[2].searchParams.get('links')).toBe('false');
	await page.getByTestId('sequels').click();
	await expect.poll(() => requests.length).toBe(4);
	expect(requests[3].searchParams.get('new_only')).toBe('false');

	// The tooltip of "About" names the formula of the list on the page
	await page.getByTestId('about-button').hover();
	await expect(page.getByTestId('about-text')).toContainText('All kinds.');
	await expect(page.getByTestId('about-text')).toContainText('Crowd links: off.');

	// The browser keeps the formula
	await page.reload();
	await expect(filters.getByRole('radio', { name: 'All kinds' })).toHaveAttribute('data-state', 'on');
	await expect(filters.getByRole('radio', { name: 'Off' })).toHaveAttribute('data-state', 'on');
});

test('the button of a card removes the show, and Undo puts it back in its position', async ({ page }) => {
	await storySeen(page);
	await page.goto('/recommendations');
	const cards = page.getByTestId('show-card');
	await expect(cards).toHaveCount(40);
	const second = await cards.nth(1).getAttribute('data-id');
	const title = await cards.nth(1).getByRole('heading').getByRole('button').textContent();

	await cards.nth(1).hover();
	await cards.nth(1).getByRole('button', { name: 'Not interested' }).click();
	await expect(cards).toHaveCount(39);
	await expect(cards.nth(1)).not.toHaveAttribute('data-id', second!);
	const bar = page.getByTestId('undo-bar');
	await expect(bar).toContainText(`Removed: ${title}`);

	await bar.getByRole('button', { name: 'Undo' }).click();
	await expect(bar).toBeHidden();
	await expect(cards).toHaveCount(40);
	await expect(cards.nth(1)).toHaveAttribute('data-id', second!);
});

test('a seed gives a list near the seed, without the formula options', async ({ page }) => {
	await storySeen(page);
	const requests = listRequests(page);
	await page.goto('/recommendations');
	const cards = page.getByTestId('show-card');
	const filters = page.getByTestId('recs-filters');
	await expect(cards).toHaveCount(40);
	const seed = await cards.nth(2).getAttribute('data-id');
	const title = await cards.nth(2).getByRole('heading').getByRole('button').textContent();

	await cards.nth(2).hover();
	await cards.nth(2).getByRole('button', { name: 'Use as seed' }).click();
	const bar = page.getByTestId('seed-bar');
	await expect(bar).toContainText(title!);
	await expect.poll(() => requests.at(-1)?.searchParams.get('seed')).toBe(seed);
	await expect(cards.first()).toContainText('% similar');
	await expect(filters.getByText('Formula:')).toBeHidden();
	await expect(page.getByTestId('story-button')).toBeHidden();
	await expect(page.getByTestId('variety')).toBeHidden();

	await bar.getByRole('button', { name: 'Clear' }).click();
	await expect(bar).toBeHidden();
	await expect(filters.getByText('Formula:')).toBeVisible();
	await expect.poll(() => requests.at(-1)?.searchParams.get('seed')).toBeNull();
});

test('the story of the list plays one time without a click, and "Steps" plays it again', async ({ page }) => {
	await page.goto('/recommendations');
	const panel = page.getByTestId('story-panel');
	await expect(panel).toHaveAttribute('data-step', 'catalog');
	await expect(panel).toHaveAttribute('data-playing', 'true');
	await expect(page.getByTestId('story-button')).toHaveAttribute('aria-pressed', 'true');

	// A click on a step shows that step and stops the play
	await panel.getByRole('button', { name: /^List/ }).click();
	await expect(panel).toHaveAttribute('data-step', 'list');
	await expect(panel).toHaveAttribute('data-playing', 'false');
	await expect(panel).toContainText('The 40 best shows are your list.');
	await expect(panel.getByRole('button', { name: /Replay/ })).toBeVisible();
	await panel.getByRole('button', { name: 'Close' }).click();
	await expect(panel).toBeHidden();

	await page.reload();
	await expect(page.getByTestId('show-card').first()).toBeVisible();
	await page.waitForTimeout(600);
	await expect(panel).toBeHidden();

	await page.getByTestId('story-button').click();
	await expect(panel).toHaveAttribute('data-step', 'catalog');
	await panel.getByRole('button', { name: /Pause/ }).press('Escape');
	await expect(panel).toBeHidden();
	await expect(page.getByTestId('story-button')).toHaveAttribute('aria-pressed', 'false');
});
