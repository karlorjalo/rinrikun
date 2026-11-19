import { defineConfig } from 'vitest/config';
import tailwindcss from '@tailwindcss/vite';
import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';

// The address below which the server gives the page. During the change from the old page the
// server gives the new page below "/next". An empty text is the root of the site.
const base = (process.env.BASE_PATH ?? '') as '' | `/${string}`;
// The server that answers the "/api" requests while the page runs with "npm run dev"
const api = process.env.API_TARGET ?? 'http://127.0.0.1:8765';

export default defineConfig({
	plugins: [
		tailwindcss(),
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			// The page is a single page app: the server gives the same file for each address, and
			// the page gets its data from the API. No page is made on the server.
			adapter: adapter({ fallback: 'index.html' }),
			paths: { base }
		})
	],
	server: { proxy: { '/api': api } },
	preview: { proxy: { '/api': api } },
	test: {
		expect: { requireAssertions: true },
		projects: [
			{
				extends: './vite.config.ts',
				test: {
					name: 'server',
					environment: 'node',
					include: ['src/**/*.{test,spec}.{js,ts}'],
					exclude: ['src/**/*.svelte.{test,spec}.{js,ts}']
				}
			}
		]
	}
});
