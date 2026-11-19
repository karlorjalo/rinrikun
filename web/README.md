# rinrikun web

The new page of rinrikun. It uses SvelteKit, Tailwind CSS and components from shadcn-svelte (Bits UI).

The server renders each page with its data, and the page then runs in the browser. A small Node
server does the rendering (`server.js`, with the build of `@sveltejs/adapter-node`). It gets the
data from the API server (the Python server; later the Rust server). The API server passes the
requests for `/next` on to the Node server, thus the browser sees one address. The old page in
`ui/` stays in use until the user approves the new page.

How the state of a tab works:

- The data of a tab comes from its load function (`+page.server.ts`, or `+page.ts` for Discover).
- The filters, the seed of a list and the show of the Similar tab are in the query of the address,
  thus the server renders them. A link of the tab bar adds the last query of its tab again.
- The theme, the settings, the help card of the tiers and the formula of the recommendations are
  cookies, thus the server renders them too. The old page keeps the same values in the local
  storage: see `src/lib/preferences.ts`.
- A module of `src/lib/state` must not keep the data of one request on the server: all requests
  share the module. The pages give their data to the components, and the shared state changes
  only in the browser.

## Develop

1. Start the Python server: `python serve.py`. It listens on port 8765.
2. Run `npm install`.
3. Run `npm run dev`.

The development server and the load functions send each `/api` request to `http://127.0.0.1:8765`.
Set the environment variable `API_TARGET` to use a different server.

## Mock API

`node tests/mock/server.mjs` starts a small copy of the API on port 8799. Each show in it is
invented. Use it to work on the page without the data of the real server:

```sh
API_TARGET=http://127.0.0.1:8799 npm run dev
```

`POST /api/__reset` puts the data of the mock back to its start.

## Check and test

- `npm run check` does the type check.
- `npm run test:unit` runs the unit tests (Vitest).
- `npm run test:e2e` runs the browser tests (Playwright). They build the page, and they use the
  mock API, not the real server. Before the first run, get the browser:
  `npx playwright install chromium`.

## Build

`npm run build` writes the page to `build/`. `node server.js` starts the server of the page: see the
comment at its start for its environment variables (`HOST`, `PORT`, `API_TARGET`).

If the page is below a path of the API server, set the environment variable `BASE_PATH` before the
build. For example: `BASE_PATH=/next`. `scripts/build_web.ps1` does this.

## Structure

- `src/routes/`: one folder for each tab. The address of a tab is the name of its folder.
- `src/hooks.server.ts`: the preferences from the cookies, and the address of the API for the load functions.
- `src/lib/api/`: the requests to the server, and the types of the answers.
- `src/lib/state/`: the state of the browser that more than one tab uses.
- `src/lib/components/ui/`: the components from shadcn-svelte, with the look of the app.
- `src/lib/components/`: the components of the app.
- `src/routes/layout.css`: the colors, the corner sizes and the shadows.

## How the project was made

```sh
npx sv@1.5.0 create --template minimal --types ts --add sveltekit-adapter="adapter:static" tailwindcss="plugins:none" vitest="usages:unit" playwright="demo:no" --no-download-check --install npm web
npx shadcn-svelte@1.8.1 init --preset vega
```
