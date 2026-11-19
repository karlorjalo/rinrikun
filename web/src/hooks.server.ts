// The hooks of the server that renders the pages. The server is the server of adapter-node
// (`node build`): the load functions in the `+page.server.ts` files get the data of each page.
//
// handle       Read the preferences of the user from the cookies. The root element of the page
//              gets the theme and the settings as attributes, so that the page has its look
//              before any script runs. The browser asks again each time for a page: its data
//              changes. A request for "/api/..." goes on to the API server.
// handleFetch  A load function asks "/api/..." on the server too. The API is a different server:
//              the Python server or the Rust server, at the address API_TARGET.
import type { Handle, HandleFetch } from '@sveltejs/kit/hooks';
import { parsePreferences, rootAttributes } from '#lib/preferences.js';

/** The API server, without a "/" at the end */
const API_TARGET = (process.env.API_TARGET || 'http://127.0.0.1:8765').replace(/\/+$/, '');

/** The headers of a request that do not go on to the API server */
const LOCAL_HEADERS = ['host', 'connection', 'accept-encoding', 'content-length'];

/**
 * Pass a request for "/api/..." on to the API server, and give its answer back. In the live
 * setup the API server gets these requests itself and passes only "/next" on to this server.
 * This server gets "/api/..." only if the browser opens it directly, for example in the tests.
 */
async function toApi(request: Request, url: URL): Promise<Response> {
	const headers = new Headers(request.headers);
	for (const name of LOCAL_HEADERS) headers.delete(name);
	// Without compression: fetch unpacks a compressed answer, and the header would then be wrong
	headers.set('accept-encoding', 'identity');
	const hasBody = request.method !== 'GET' && request.method !== 'HEAD';
	try {
		const answer = await fetch(API_TARGET + url.pathname + url.search, {
			method: request.method,
			headers,
			body: hasBody ? await request.arrayBuffer() : undefined,
			redirect: 'manual'
		});
		const back = new Headers(answer.headers);
		for (const name of ['connection', 'transfer-encoding', 'keep-alive']) back.delete(name);
		return new Response(answer.body, { status: answer.status, headers: back });
	} catch {
		return Response.json({ detail: 'the API server does not answer' }, { status: 502 });
	}
}

export const handle: Handle = async ({ event, resolve }) => {
	if (event.url.pathname.startsWith('/api/')) return toApi(event.request, event.url);
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
