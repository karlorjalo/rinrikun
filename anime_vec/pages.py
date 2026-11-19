"""The pages that the server gives to the browser.

The server has two pages while the new page replaces the old page:
  PageFiles     The old page in ui/: a few files without a build.
  forward_page  The new page at /next. A Node server renders it (node web/build): this server
                passes the requests for /next on to it, thus the browser sees one address.
"""
import urllib.error
import urllib.request

from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

# The browser asks the server each time if a file of the page changed. Without this header a
# browser can use its old copy of one file with the new copy of a different file for some
# minutes after a change, and the page is then wrong: for example a new page with the old style
# sheet. The files have an ETag, thus the answer for a file that did not change is short.
PAGE_HEADERS = {"Cache-Control": "no-cache"}

# The headers of a request that go on to the page server: the cookies have the preferences of
# the user, and the conditions of a request make a short answer for a file that did not change.
REQUEST_HEADERS = ("accept", "accept-language", "cookie", "if-none-match", "if-modified-since", "user-agent")
# The headers of the answer of the page server that come back to the browser
ANSWER_HEADERS = ("content-type", "cache-control", "etag", "last-modified", "location", "set-cookie", "vary")
# Seconds to wait for the page server. A page with a list of recommendations takes about 1 second.
TIMEOUT = 30


class PageFiles(StaticFiles):
    """The files of the old page, with the header that makes the browser ask again each time."""

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        response.headers.update(PAGE_HEADERS)
        return response


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect of the page server goes back to the browser: the address in the browser must change."""

    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def forward_page(server: str, path: str, query: str, headers) -> Response:
    """Pass a request for the new page on to the page server, and give back its answer.

    `server` is the address of the page server, `path` and `query` are the parts of the address
    of the request, and `headers` are the headers of the request. If the page server does not
    answer, the answer is 502 with a short text.
    """
    url = server.rstrip("/") + path + (f"?{query}" if query else "")
    forwarded = {name: headers[name] for name in REQUEST_HEADERS if headers.get(name)}
    # This server compresses the answer itself
    forwarded["Accept-Encoding"] = "identity"
    try:
        with _OPENER.open(urllib.request.Request(url, headers=forwarded), timeout=TIMEOUT) as answer:
            status, body, answer_headers = answer.status, answer.read(), answer.headers
    except urllib.error.HTTPError as error:
        status, body, answer_headers = error.code, error.read(), error.headers
    except (urllib.error.URLError, OSError):
        return Response("The server of the new page does not run. Start it with scripts/restart_servers.ps1.",
                        status_code=502, media_type="text/plain")
    response = Response(content=body, status_code=status)
    for name in ANSWER_HEADERS:
        for value in answer_headers.get_all(name) or []:
            response.headers.append(name, value)
    return response
