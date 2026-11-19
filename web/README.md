# rinrikun web

The new page of rinrikun. It uses SvelteKit, Tailwind CSS and components from shadcn-svelte (Bits UI).

The page is a single-page app. The Python server gives the data through `/api`. The old page in
`ui/` stays in use until the new page has all tabs.

## Develop

1. Start the Python server: `python serve.py`. It listens on port 8765.
2. Run `npm install`.
3. Run `npm run dev`.

The development server sends each `/api` request to `http://127.0.0.1:8765`. Set the environment
variable `API_TARGET` to use a different server.

## Check

`npm run check` does the type check.

## Build

`npm run build` writes the page to `build/`.

If the server serves the page below a path, set the environment variable `BASE_PATH` before the
build. For example: `BASE_PATH=/next`.

## Structure

- `src/routes/`: one folder for each tab. The address of a tab is the name of its folder.
- `src/lib/api/`: the requests to the server, and the types of the answers.
- `src/lib/state/`: the state that more than one tab uses.
- `src/lib/components/ui/`: the components from shadcn-svelte, with the look of the app.
- `src/lib/components/`: the components of the app.
- `src/routes/layout.css`: the colors, the corner sizes and the shadows.

## How the project was made

```sh
npx sv@1.5.0 create --template minimal --types ts --add sveltekit-adapter="adapter:static" tailwindcss="plugins:none" vitest="usages:unit" playwright="demo:no" --no-download-check --install npm web
npx shadcn-svelte@1.8.1 init --preset vega
```
