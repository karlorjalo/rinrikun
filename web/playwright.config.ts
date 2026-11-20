import { defineConfig, devices } from '@playwright/test';

// The browser tests use the page as the build makes it, with the server of the build (node build), and the
// mock of the API. They never use the real server: it has the data of the user, and a test that
// gives an answer would change it.
const MOCK_PORT = 8798;
const PAGE_PORT = 4174;

export default defineConfig({
	testDir: 'tests',
	testMatch: '**/*.e2e.ts',
	// The tests change the data of the one mock server, thus they run one after the other
	workers: 1,
	fullyParallel: false,
	use: { baseURL: `http://127.0.0.1:${PAGE_PORT}` },
	projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
	webServer: [
		{ command: `node tests/mock/server.mjs ${MOCK_PORT}`, port: MOCK_PORT, reuseExistingServer: false },
		{
			command: 'npm run build && node build',
			port: PAGE_PORT,
			// ORIGIN: without it the server of the build takes "https://" as its own origin. The CSRF check
			// of SvelteKit then refuses each DELETE of the page (for example the undo of a tier) with 403.
			// In the live setup the Rust server answers /api itself, thus there this check does not apply.
			env: { API_TARGET: `http://127.0.0.1:${MOCK_PORT}`, HOST: '127.0.0.1', PORT: String(PAGE_PORT), ORIGIN: `http://127.0.0.1:${PAGE_PORT}` },
			reuseExistingServer: false,
			timeout: 180_000
		}
	]
});
