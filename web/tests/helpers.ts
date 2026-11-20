// Shared steps of the browser tests.
import { test as base, expect, type APIRequestContext, type Page } from '@playwright/test';

/** A test that starts with the data of the mock server at its start, and fails on an error of the page */
export const test = base.extend<{ pageErrors: string[] }>({
	pageErrors: [
		async ({ page, request }, use) => {
			// A body of JSON: SvelteKit refuses a POST without a content type and without an origin (its
			// check of form submissions), and the data of the mock then stayed from the test before
			const reset = await request.post('/api/__reset', { data: {} });
			expect(reset.ok(), 'the reset of the mock data').toBe(true);
			const errors: string[] = [];
			page.on('pageerror', (error) => errors.push(String(error)));
			await use(errors);
			expect(errors, 'errors of the page').toEqual([]);
		},
		{ auto: true }
	]
});

export { expect };

/** Go to a tab with its link in the tab bar: the page does not load again */
export async function openTab(page: Page, name: string) {
	await page.getByRole('navigation').getByRole('link', { name, exact: true }).click();
}

/** The numbers in a text, in their order */
export function numbers(text: string | null): number[] {
	return (text ?? '').match(/\d+/g)?.map(Number) ?? [];
}

/**
 * The requests that the mock API got since the start of the test: "GET /api/recommend?k=40...".
 * The server of the page sends the requests of its load functions, the browser sends the others:
 * the mock sees the two.
 */
export async function apiRequests(request: APIRequestContext, path: string): Promise<URL[]> {
	const all: string[] = await (await request.get('/api/__requests')).json();
	return all
		.map((line) => new URL(line.split(' ')[1], 'http://mock'))
		.filter((url) => url.pathname === path);
}
