// The loads that the loading bar shows besides the change of a page (see LoadingBar.svelte):
// for example the new list after a change of the formula. The state changes only in the browser.

class Progress {
	#count = $state(0);

	/** True while a tracked load runs */
	get busy(): boolean {
		return this.#count > 0;
	}

	/** Show the loading bar while the work runs, and give its result */
	async track<T>(work: Promise<T>): Promise<T> {
		this.#count += 1;
		try {
			return await work;
		} finally {
			this.#count -= 1;
		}
	}
}

export const progress = new Progress();
