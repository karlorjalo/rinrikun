# Measurement tools

These tools measure the load times of the page in a browser (Playwright, from `node_modules`).
Run them from PowerShell in `web/`: Git Bash changes the path `/` into a Windows path.

| Tool | What it measures |
|---|---|
| `load_probe.mjs <address> [slowdown] [tabs]` | A cold load and a second load of each tab, and the change of each tab with a click |
| `load_trace.mjs <address> <path> [slowdown]` | A CPU profile and a timeline of the load of one page |
| `tab_trace.mjs <address> <tab> [slowdown]` | A CPU profile and a timeline of the change to one tab |
| `map_draws.mjs <address> <path> [slowdown]` | The number of map draws during a load, and the time of each JSON answer |

`slowdown` makes the CPU of the browser slower: 4 is near the speed of a phone.

The times of the API and of the server are in `scripts/perf/api_times.ps1`. Run that script on
the PC against the dev copy.

## Safety

Never load the Recommendations tab (`/recommendations`) or a list without a seed against the live
server: each such list goes into the log of the user. For these, use the dev copy.

The dev copy listens only on the PC. A tunnel gives it to this computer at port 8790:

```sh
ssh -N -L 8790:127.0.0.1:8773 USER@PC_ADDRESS
node perf/load_probe.mjs http://127.0.0.1:8790 1 Recommendations
```

The live page is at `http://PC_ADDRESS:8771`.
