// The data of the maps. The page gets the map data one time, and all maps use the same data.
//
// A change of a tier or of the watched state changes the points of the loaded data in their
// positions. The page does not get the data again: new data would make the maps again, and the
// user would lose the zoom and the position.
//
// With the setting "Match gradient" on, the points also have the match of their shows. The
// server gives the match of each point in the order of the points. The page gets the values when
// the setting is on, and again after a change that changes the match.
import { api } from '#lib/api/client.js';
import type { MapPoint, Tier, VectorMap } from '#lib/api/types.js';
import type { MapController } from '#lib/map/engine.js';
import { settings } from './settings.svelte.js';

/** A change of some points: the answer of the server to a change of a tier or of the watched state */
interface PointChange {
	ids: string[];
	tier?: Tier | null;
	owned?: number;
}

/** The page asks the server again this number of times when it does not get the match values */
const MATCH_RETRIES = 4;

class MapStore {
	// The data is large and the map code changes its points itself: it is not a deep state
	data = $state.raw<VectorMap | null>(null);
	/** "loading", "ready" or "error": if the page has the match values. "idle" before the first request. */
	matchState = $state<'idle' | 'loading' | 'ready' | 'error'>('idle');
	/** A number that grows with each change of a point. A value that reads it is computed again. */
	version = $state(0);
	private request: Promise<VectorMap | null> | null = null;
	private points = new Map<string, MapPoint>();
	/** The changes that the user makes while the data loads. That data can be older than these changes. */
	private late: PointChange[] = [];
	/** The maps that the page shows now */
	private maps = new Set<MapController>();
	private matchLoaded = false;
	private matchRequest = 0;
	private matchTimer: ReturnType<typeof setTimeout> | undefined;

	/** Get the map data one time */
	load(): Promise<VectorMap | null> {
		if (!this.request) {
			this.late = [];
			this.request = api
				.vectorMap()
				.then((data) => {
					this.points.clear();
					for (const point of data.points) this.points.set(point.id, point);
					this.late.forEach((change) => this.apply(change));
					this.late = [];
					this.data = data;
					return data;
				})
				.catch((error) => {
					console.error('Failed to load the map data', error);
					this.request = null;
					return null;
				});
		}
		return this.request;
	}

	private apply(change: PointChange) {
		for (const id of change.ids) {
			const point = this.points.get(id);
			if (!point) continue;
			if (change.tier !== undefined) point.tier = change.tier;
			if (change.owned !== undefined) point.owned = change.owned;
		}
	}

	/** The user changed a tier or the watched state: the open maps show the change at once */
	change(change: PointChange) {
		if (this.data) this.apply(change);
		else this.late.push(change);
		this.version += 1;
		this.redraw();
		this.matchChanged();
	}

	/** A change of the data of the user changes the match of the shows: get the values again after a short time */
	matchChanged() {
		this.scheduleMatch(1200);
	}

	add(map: MapController) {
		this.maps.add(map);
	}

	remove(map: MapController) {
		this.maps.delete(map);
	}

	/** Draw the open maps again. A map keeps its zoom and its position. */
	redraw() {
		this.maps.forEach((map) => map.scheduleDraw());
	}

	/** The shows of the user with the tier S: the Profile map shows them as posters */
	topTier(): string[] {
		void this.version;
		return (this.data?.points ?? []).filter((point) => point.owned && point.tier === 'S').map((point) => point.id);
	}

	/** The maps draw the match gradient: the setting is on, and the points have their match */
	get gradientReady(): boolean {
		return settings.gradient && this.matchLoaded;
	}

	/** Get the match values after `delay` milliseconds. A new call before that time replaces the old call. */
	scheduleMatch(delay = 0) {
		clearTimeout(this.matchTimer);
		if (settings.gradient) this.matchTimer = setTimeout(() => this.loadMatch(), delay);
	}

	private async loadMatch(attempt = 0) {
		if (!settings.gradient) return;
		const request = ++this.matchRequest;
		if (!this.matchLoaded) this.matchState = 'loading';
		try {
			const data = await this.load();
			const values = await api.mapMatch();
			// An older request that ends late must not replace the values of a newer request
			if (request !== this.matchRequest) return;
			if (!data || !Array.isArray(values) || values.length !== data.points.length) {
				throw new Error('the list of values does not fit the map');
			}
			data.points.forEach((point, n) => (point.match = values[n]));
			this.matchLoaded = true;
			this.matchState = 'ready';
			this.redraw();
		} catch (error) {
			console.error('Failed to load the match of the shows of the map', error);
			if (request !== this.matchRequest) return;
			// The server can be busy, or it can start at this moment: try again some times
			if (attempt < MATCH_RETRIES) {
				clearTimeout(this.matchTimer);
				this.matchTimer = setTimeout(() => this.loadMatch(attempt + 1), 2500 * (attempt + 1));
			} else if (!this.matchLoaded) {
				this.matchState = 'error';
			}
		}
	}
}

export const mapStore = new MapStore();
