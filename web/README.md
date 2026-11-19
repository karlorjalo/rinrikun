# rinrikun web

The page of rinrikun. It uses SvelteKit, Tailwind CSS and components from shadcn-svelte (Bits UI).

The server renders each page with its data, and the page then runs in the browser. The load
function of each tab is in its `+page.server.ts`: it gets the data from the API server (the Rust
server in `../server`). The Node server of the build of `@sveltejs/adapter-node` (`node build`)
runs the load functions and renders the pages. The API server passes each request that is not
for `/api/...` on to the Node server, thus the browser sees one address.

How the state of a tab works:

- The data of a tab comes from its load function (`+page.server.ts`). On the first visit the
  server renders the page with it. On a later visit the browser gets only the data from the server.
  A tab gets its data when the pointer is on its link (Recommendations: at the press, because a
  list goes into the log of the recommendations).
- The Discover deck stays in the browser when the user opens a different tab. When the user comes
  back, the page shows the same card, and the new cards of the load go to the end of the deck.
- The filters, the seed of a list and the show of the Similar tab are in the query of the address,
  thus the server renders them. A link of the tab bar adds the last query of its tab again.
- The theme, the settings, the help card of the tiers and the formula of the recommendations are
  cookies, thus the server renders them too: see `src/lib/preferences.ts`.
- A module of `src/lib/state` must not keep the data of one request on the server: all requests
  share the module. The pages give their data to the components, and the shared state changes
  only in the browser.
- The motion (the loading bar, the fades) has its times in `src/routes/layout.css` ("Motion") and
  in `src/lib/motion.ts`. The system setting "reduce motion" turns it off.

## Develop

1. Start the API server: `rinrikun serve anime_vec.db` (see `../server/README.md`). It listens on
   port 8775 by default.
2. Run `npm install`.
3. Run `API_TARGET=http://127.0.0.1:8775 npm run dev`.

The development server and the load functions send each `/api` request to `API_TARGET` (default
`http://127.0.0.1:8765`, the port of the live server).

## Mock API

`node tests/mock/server.mjs` starts a small copy of the API on port 8799. Each show in it is
invented. Use it to work on the page without the data of the real server:

```sh
API_TARGET=http://127.0.0.1:8799 npm run dev
```

`POST /api/__reset` puts the data of the mock back to its start. `POST /api/__delay {"ms": n}`
makes each next answer wait n milliseconds (a slow server).

## Check and test

- `npm run check` does the type check.
- `npm run test:unit` runs the unit tests (Vitest).
- `npm run test:e2e` runs the browser tests (Playwright). They build the page, and they use the
  mock API, not the real server. Before the first run, get the browser:
  `npx playwright install chromium`.

## Build

`npm run build` writes the page to `build/`. `node build` starts the server of the page. Its
environment variables:

- `HOST` and `PORT`: the address of the server (the default of adapter-node is `0.0.0.0:3000`;
  `scripts/restart_servers.ps1` gives `127.0.0.1:8780`).
- `API_TARGET`: the API server (default `http://127.0.0.1:8765`). The load functions get their data
  there. A request for `/api/...` that comes to this server goes on to it too (the browser tests
  use this): see `src/hooks.server.ts`.

## Structure

- `src/routes/`: one folder for each tab. The address of a tab is the name of its folder.
- `src/hooks.server.ts`: the preferences from the cookies, the address of the API for the load
  functions, and the requests for `/api/...` that come to the page server.
- `src/lib/api/`: the requests to the server, and the types of the answers.
- `src/lib/state/`: the state of the browser that more than one tab uses.
- `src/lib/components/ui/`: the components from shadcn-svelte, with the look of the app.
- `src/lib/components/`: the components of the app.
- `src/lib/map/`: the map canvas (one module) and its style.
- `src/routes/layout.css`: the colors, the corner sizes, the shadows and the motion.

## How the project was made

```sh
npx sv@1.5.0 create --template minimal --types ts --add sveltekit-adapter="adapter:static" tailwindcss="plugins:none" vitest="usages:unit" playwright="demo:no" --no-download-check --install npm web
npx shadcn-svelte@1.8.1 init --preset vega
```
