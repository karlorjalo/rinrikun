// A page that shows lists gets them when it opens, and again after the user changes a show.
import { library } from './library.svelte.js';

/**
 * Run `load` when the component starts, and a short time after the last change of a show.
 * A change moves a show from one list to a different list, and it changes the match of other
 * shows. The wait makes one request for some fast changes. Call this in the script of a component.
 */
export function loadWithChanges(load: () => void, delay = 1500) {
	let timer: ReturnType<typeof setTimeout> | undefined;
	let seen = -1;
	$effect(() => {
		const version = library.version;
		clearTimeout(timer);
		if (seen < 0) load();
		else if (version !== seen) timer = setTimeout(load, delay);
		seen = version;
		return () => clearTimeout(timer);
	});
}
