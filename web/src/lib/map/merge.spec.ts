import { describe, expect, it } from 'vitest';
import type { MapBase, MapUser } from '../api/types.js';
import { mergeMap } from './merge.js';

function base(): MapBase {
	const point = (id: string, x: number) => ({ id, x, y: 0.5, gx: x, gy: 0.5, title: id, title_native: id, year: 2020, poster: null, genres: [], score: 7 });
	return {
		points: [point('al:1', 0.1), point('jf:2', 0.2), point('al:3', 0.3)],
		regions: [{ x: 0.5, y: 0.5, gx: 0.5, gy: 0.5, label: 'Drama', count: 3, level: 0 }],
		cell: { w: 0.01, h: 0.02 }
	};
}

describe('mergeMap', () => {
	it('gives each point without data of the user the values of a catalog show', () => {
		const map = mergeMap(base(), { shows: {} });
		expect(map.points.map((p) => [p.id, p.owned, p.tier])).toEqual([
			['al:1', 0, null],
			['jf:2', 0, null],
			['al:3', 0, null]
		]);
	});

	it('gives the shows of the user their state and their tier', () => {
		const user: MapUser = { shows: { 'jf:2': { owned: 1, tier: 'S' }, 'al:3': { owned: 1, tier: null } } };
		const map = mergeMap(base(), user);
		expect(map.points.map((p) => [p.id, p.owned, p.tier])).toEqual([
			['al:1', 0, null],
			['jf:2', 1, 'S'],
			['al:3', 1, null]
		]);
	});

	it('keeps the order and the other data of the points, the areas and the cell', () => {
		const fixed = base();
		const map = mergeMap(fixed, { shows: { 'al:1': { owned: 1, tier: 'B' } } });
		expect(map.points.map((p) => p.x)).toEqual([0.1, 0.2, 0.3]);
		expect(map.points[0].title).toBe('al:1');
		expect(map.regions).toEqual(fixed.regions);
		expect(map.cell).toEqual({ w: 0.01, h: 0.02 });
	});

	it('ignores a show of the user that is not a point of the map', () => {
		const map = mergeMap(base(), { shows: { 'al:999': { owned: 1, tier: 'A' } } });
		expect(map.points).toHaveLength(3);
		expect(map.points.every((p) => p.owned === 0 && p.tier === null)).toBe(true);
	});
});
