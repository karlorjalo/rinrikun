// The hooks of the server that renders the pages.
//
// handle       Read the preferences of the user from the cookies. The root element of the page
//              gets the theme and the settings as attributes, so that the page has its look
//              before any script runs. The browser asks again each time for a page: its data
//              changes.
// handleFetch  A load function asks "/api/..." on the server too. The API is a different server:
//              the Python server (later the Rust server), at the address API_TARGET.
import type { Handle, HandleFetch } from '@sveltejs/kit/hooks';
import { parsePreferences, rootAttributes } from '#lib/preferences.js';

/** The API server, without a "/" at the end */
const API_TARGET = (process.env.API_TARGET || 'http://127.0.0.1:8765').replace(/\/+$/, '');

export const handle: Handle = async ({ event, resolve }) => {
	const preferences = parsePreferences((key) => event.cookies.get(key));
	event.locals.preferences = preferences;
	const attributes = rootAttributes(preferences.theme, preferences.settings);
	const response = await resolve(event, {
		transformPageChunk: ({ html }) => html.replace('%rinrikun.root%', attributes)
	});
	if (!response.headers.has('cache-control')) response.headers.set('cache-control', 'no-cache');
	return response;
};

export const handleFetch: HandleFetch = async ({ event, request, fetch }) => {
	const url = new URL(request.url);
	if (url.origin === event.url.origin && url.pathname.startsWith('/api/')) {
		request = new Request(API_TARGET + url.pathname + url.search, request);
	}
	return fetch(request);
};
