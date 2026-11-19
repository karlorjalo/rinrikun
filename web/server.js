// The server of the new page: SvelteKit renders the pages (build/handler.js).
//
//   node server.js
//
// Environment:
//   HOST, PORT   The address of this server (default 127.0.0.1:8780)
//   API_TARGET   The API server (default http://127.0.0.1:8765). The load functions get their
//                data there, and this server passes a request for "/api/..." on to it.
//
// The Python server passes the requests for "/next" on to this server, thus the browser sees one
// address. A request for "/api/..." comes here only if the browser opens this server directly,
// for example in the browser tests.
import http from 'node:http';
import { handler } from './build/handler.js';

const host = process.env.HOST || '127.0.0.1';
const port = Number(process.env.PORT || 8780);
const api = new URL(process.env.API_TARGET || 'http://127.0.0.1:8765');

/** Pass a request on to the API server, and its answer back */
function toApi(request, response) {
	const forward = http.request(
		{
			hostname: api.hostname,
			port: api.port || 80,
			path: request.url,
			method: request.method,
			headers: { ...request.headers, host: api.host }
		},
		(answer) => {
			response.writeHead(answer.statusCode ?? 502, answer.headers);
			answer.pipe(response);
		}
	);
	forward.on('error', () => {
		response.writeHead(502, { 'content-type': 'application/json' });
		response.end(JSON.stringify({ detail: 'the API server does not answer' }));
	});
	request.pipe(forward);
}

const server = http.createServer((request, response) => {
	if (request.url?.startsWith('/api/')) toApi(request, response);
	else handler(request, response);
});
server.listen(port, host, () => console.log(`rinrikun web on http://${host}:${port}, API at ${api.origin}`));
