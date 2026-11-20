// The motion of the app, with the times of the style sheet (layout.css, "Motion"): a new page
// fades in, a new item of a list fades in, and a picture fades in when it arrives. The system
// setting "reduce motion" turns each of them off.
import { fade } from 'svelte/transition';

/** The times of the style sheet, in milliseconds */
export const FADE = 180;
export const FADE_FAST = 120;

/** True if the system asks for less motion. On the server there is no motion. */
export function reducedMotion(): boolean {
	return typeof matchMedia !== 'function' || matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * The transition of a new page or a new item: a short fade in. Svelte plays it only for an
 * element that comes after the first render: the first page of a visit does not fade.
 */
export function appear(node: Element, { fast = false }: { fast?: boolean } = {}) {
	return fade(node, { duration: reducedMotion() ? 0 : fast ? FADE_FAST : FADE });
}

/**
 * An action for a picture: a picture that is not on the screen yet fades in when it arrives. A
 * picture that the browser has already (from its cache, or before the script ran) shows at once.
 */
export function fadeOnLoad(img: HTMLImageElement) {
	if (img.complete || reducedMotion()) return;
	img.style.opacity = '0';
	img.style.transition = 'opacity var(--fade) var(--ease-out)';
	const show = () => {
		img.style.opacity = '';
	};
	img.addEventListener('load', show, { once: true });
	img.addEventListener('error', show, { once: true });
	return {
		destroy() {
			img.removeEventListener('load', show);
			img.removeEventListener('error', show);
		}
	};
}
