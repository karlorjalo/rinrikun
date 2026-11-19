import { defineConfig } from 'vitest/config';
import tailwindcss from '@tailwindcss/vite';
import adapter from '@sveltejs/adapter-node';
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
			// The Node server of the build renders the pages (node build). The load functions in
			// the +page.server.ts files get the data from the API server: see src/hooks.server.ts.
			adapter: adapter(),
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
