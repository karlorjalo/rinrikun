import { describe, expect, it } from 'vitest';
import { longEnough, searchRank, searchText, searchWords, showSearchText } from './search.js';

describe('searchText', () => {
	it('ignores case, spaces and punctuation', () => {
		expect(searchText('Re:Zero')).toBe(searchText('re zero'));
		expect(searchText('K-On!')).toBe('kon');
	});

	it('gives full-width letters the form of half-width letters', () => {
		expect(searchText('ＡＢＣ１２３')).toBe('abc123');
	});
});

describe('showSearchText', () => {
	it('has each title of the show in its own line', () => {
		const text = showSearchText({ title: 'Kimi no Na wa.', title_native: '君の名は。', aka: ['Your Name.'] });
		expect(text.split('\n')).toEqual(['kiminonawa', '君の名は', 'yourname']);
	});

	it('finds a show by a title that the page does not show', () => {
		const text = showSearchText({ title: 'Kimi no Na wa.', title_native: '君の名は。', aka: ['Your Name.'] });
		expect(searchWords('your name').every((word) => text.includes(word))).toBe(true);
	});
});

describe('searchRank', () => {
	it('puts a title that starts with the first word before the other titles', () => {
		const starts = showSearchText({ title: 'Hibike! Euphonium' });
		const inside = showSearchText({ title: 'Gekijouban Hibike! Euphonium' });
		const words = searchWords('hibike');
		expect(searchRank(starts, words, 0)).toBeLessThan(searchRank(inside, words, 0));
	});

	it('uses each title of the show, not only the first title', () => {
		const text = showSearchText({ title: 'Kimi no Na wa.', aka: ['Your Name.'] });
		expect(searchRank(text, searchWords('your'), 0)).toBe(1);
	});

	it('puts a show of the user before a show that the user does not have', () => {
		const text = showSearchText({ title: 'Hibike! Euphonium' });
		const words = searchWords('hibike');
		expect(searchRank(text, words, 1)).toBeLessThan(searchRank(text, words, 0));
	});
});

describe('longEnough', () => {
	it('refuses one Latin letter and accepts one Japanese character', () => {
		expect(longEnough('k')).toBe(false);
		expect(longEnough('ke')).toBe(true);
		expect(longEnough('君')).toBe(true);
		expect(longEnough('  ')).toBe(false);
	});
});
