// The map data comes in two parts (see MapBase and MapUser in api/types.ts): the large fixed part
// that the browser keeps, and the small part of the user. This function makes the map of the
// page from them.
import type { MapBase, MapPoint, MapUser, VectorMap } from '../api/types.js';

/**
 * Put the data of the user into the points of the fixed part. A point that is not in the part
 * of the user is a catalog show: the user does not have it, and it has no tier. The function
 * changes the points of `base` and gives them back: the fixed part has about 20 000 points, and
 * a copy of each point would cost time for nothing.
 */
export function mergeMap(base: MapBase, user: MapUser): VectorMap {
	const points = base.points as MapPoint[];
	for (const point of points) {
		const mine = user.shows[point.id];
		point.owned = mine?.owned ?? 0;
		point.tier = mine?.tier ?? null;
	}
	return { points, regions: base.regions, cell: base.cell };
}
