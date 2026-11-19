// A long list in parts. After the change of a page in the browser, the page shows the first items
// of a long list at once and the next items one part in each frame. Thus the new page is on the
// screen sooner: 600 cards take about half a second to make.
//
// The first page of a visit comes from the server with all items: the browser must make the same
// items when it takes over the page (hydration), thus that page shows all items at once.

/** The browser runs the page: the root layout sets this after the first page is on the screen */
export const app = { started: false };

/** The number of items that the first frame shows, and the number of items of each next frame */
const FIRST = 36;
const STEP = 36;

/**
 * The number of items of a list to show now. `length` gives the length of the list. Call it
 * in the script of a component: it uses an effect.
 */
export function progressive(length: () => number): { readonly limit: number } {
	let limit = $state(app.started ? FIRST : Infinity);
	$effect(() => {
		if (limit >= length()) return;
		const frame = requestAnimationFrame(() => (limit += STEP));
		return () => cancelAnimationFrame(frame);
	});
	return {
		get limit() {
			return limit;
		}
	};
}
