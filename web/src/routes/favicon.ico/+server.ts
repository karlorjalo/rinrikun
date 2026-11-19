// The icon at the usual address /favicon.ico. The page names its icon itself (+layout.svelte), but
// some clients ask for this address without the page, for example for a bookmark.
import favicon from '#lib/assets/favicon.svg?raw';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = () =>
	new Response(favicon, { headers: { 'content-type': 'image/svg+xml', 'cache-control': 'max-age=86400' } });
