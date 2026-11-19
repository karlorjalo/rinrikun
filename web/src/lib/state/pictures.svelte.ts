// The pictures of a show: frames of its episodes and of its trailer. A card of the Discover
// deck shows them, so that the user sees how a show looks without a visit to AniList. The server
// gets the pictures from AniList: see /api/frames.
import { SvelteMap, SvelteSet } from 'svelte/reactivity';
import { api } from '#lib/api/client.js';
import type { Frame, Pictures } from '#lib/api/types.js';

class PictureStore {
	/** The pictures of a show by its id. The value is null while the request is in progress. */
	private found = new SvelteMap<string, Pictures | null>();
	/** The shows for which the server gave no pictures. The page does not ask for them again. */
	private misses = new SvelteSet<string>();
	/** The frames that did not load, by the address of their small picture */
	private broken = new SvelteSet<string>();

	/** "ready": the pictures are there. "missing": the server gave none. "loading": not there yet. */
	status(id: string): 'ready' | 'missing' | 'loading' {
		if (this.found.get(id)) return 'ready';
		return this.misses.has(id) ? 'missing' : 'loading';
	}

	of(id: string): Pictures | null {
		return this.found.get(id) ?? null;
	}

	/** The frames of a show that the page can show */
	frames(id: string): Frame[] {
		return (this.found.get(id)?.frames ?? []).filter((frame) => !this.broken.has(frame.small));
	}

	/** A frame that does not load goes out of the row */
	drop(frame: Frame) {
		this.broken.add(frame.small);
	}

	/** Get the pictures of some shows with one request */
	async load(ids: string[]) {
		const wanted = ids.filter((id) => !this.found.has(id) && !this.misses.has(id));
		if (!wanted.length) return;
		wanted.forEach((id) => this.found.set(id, null));
		let result: Record<string, Pictures> = {};
		try {
			result = await api.frames(wanted);
		} catch (error) {
			console.error('Failed to load the pictures of the shows', error);
		}
		for (const id of wanted) {
			if (result[id]) {
				this.found.set(id, result[id]);
			} else {
				this.found.delete(id);
				this.misses.add(id);
			}
		}
	}

	/** Get the first frames of a show before its card comes, so that the card shows them immediately */
	preload(id: string | undefined) {
		if (!id) return;
		for (const frame of this.frames(id).slice(0, 4)) {
			const image = new Image();
			image.referrerPolicy = 'no-referrer';
			image.src = frame.small;
		}
	}
}

export const pictures = new PictureStore();

/** YouTube gives a small grey picture, 120 by 90, for a frame that it does not have */
export function isPlaceholder(image: EventTarget | null): boolean {
	return image instanceof HTMLImageElement && image.naturalWidth > 0 && image.naturalWidth <= 120 && image.naturalHeight <= 90;
}
