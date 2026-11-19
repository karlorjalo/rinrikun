// Shared steps of the browser tests.
import { test as base, expect, type Page } from '@playwright/test';

/** A test that starts with the data of the mock server at its start, and fails on an error of the page */
export const test = base.extend<{ pageErrors: string[] }>({
	pageErrors: [
		async ({ page, request }, use) => {
			await request.post('/api/__reset');
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
