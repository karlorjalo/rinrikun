"""The files of the pages that the server gives to the browser.

The server has two pages while the new page replaces the old page:
  PageFiles   The old page in ui/: a few files without a build.
  NewPage     The new page in web/build: a single-page app that a build makes. See web/README.md.
"""
from fastapi.staticfiles import StaticFiles
# The error of a missing file is the error class of Starlette. The class of FastAPI is a subclass of
# it, thus "except" with the class of FastAPI does not catch it.
from starlette.exceptions import HTTPException
from starlette.types import Scope

# The browser asks the server each time if a file of the page changed. Without this header a
# browser can use its old copy of one file with the new copy of a different file for some
# minutes after a change, and the page is then wrong: for example a new page with the old style
# sheet. The files have an ETag, thus the answer for a file that did not change is short.
PAGE_HEADERS = {"Cache-Control": "no-cache"}

# A file of the new page with a hash of its contents in its name. A change of the file changes
# the name, thus the browser can keep the file for a long time and does not ask again.
HASHED_HEADERS = {"Cache-Control": "public, max-age=31536000, immutable"}
HASHED_FILES = "_app/immutable/"


class PageFiles(StaticFiles):
    """The files of the old page, with the header that makes the browser ask again each time."""

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        response.headers.update(PAGE_HEADERS)
        return response


class NewPage(StaticFiles):
    """The files of the new page.

    The new page is a single-page app: each tab has its own address (for example /next/ratings),
    but the build has one page file for all tabs. Thus the server gives that page file for an
    address that has no file, and the page opens the tab of the address. An address with a file
    ending that has no file is a missing file, and the answer is 404.
    """

    def __init__(self, directory):
        super().__init__(directory=directory, html=True)

    async def get_response(self, path: str, scope: Scope):
        # On Windows the path has backslashes
        path = path.replace("\\", "/")
        try:
            response = await super().get_response(path, scope)
        except HTTPException as error:
            name = path.rsplit("/", 1)[-1]
            if error.status_code != 404 or "." in name:
                raise
            response = await super().get_response("index.html", scope)
        hashed = path.startswith(HASHED_FILES) and response.status_code in (200, 304)
        response.headers.update(HASHED_HEADERS if hashed else PAGE_HEADERS)
        return response
