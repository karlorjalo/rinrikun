// The types of the map code in engine.js.
import type { MapPoint, VectorMap } from '#lib/api/types.js';

export interface MapOptions {
	/** The shows that are posters also in the far view */
	highlightIds?: string[];
	/** The text of the mark of a highlighted show in the tooltip */
	highlightLabel?: string;
	/** "recommended": the look of a recommendation. "tier": the look of the tier of the show. */
	highlightKind?: 'recommended' | 'tier';
	/** The user clicked a show */
	onOpen?: (point: MapPoint) => void;
	/** Tell if the map draws the match gradient: the setting is on, and the points have their match */
	gradient?: () => boolean;
}

/** The look of the dots that stay in a step of the story of the list */
export interface StoryLook {
	alpha: number;
	/** The size of a dot, as a factor of the usual size */
	size: number;
	/** The dots have the accent color: the taste of the user counts from this step */
	taste: boolean;
}

/**
 * The story of the list: the map draws the dots of two steps and the change between them.
 * `from` and `to` have 1 for each point of the map that stays in the step.
 */
export interface MapStory {
	from: Uint8Array;
	to: Uint8Array;
	lookFrom: StoryLook;
	lookTo: StoryLook;
	/** The part of the change that is done, from 0 to 1 */
	ease: number;
	/** `to` is the last step: the usual picture of the map comes back */
	last: boolean;
	/** The position of the step `to` */
	step: number;
}

export interface MapController {
	draw(): void;
	/** Draw the map in the next frame */
	scheduleDraw(): void;
	setView(view: 'posters' | 'dots'): void;
	setHighlight(ids: string[]): void;
	setStory(state: MapStory | null): void;
	/** Show the full map. `dx` and `dy` move it, in pixels. */
	resetView(dx?: number, dy?: number): void;
	clearSearch(): void;
	destroy(): void;
}

/**
 * Make a map in a canvas. The parent of the canvas is the box of the map: the map puts its
 * controls in it. `tooltip` is the element in that box for the tooltip of a show.
 */
export function createVectorMap(canvas: HTMLCanvasElement, tooltip: HTMLElement, data: VectorMap, options?: MapOptions): MapController;
