"""
Browser front end.

The corpus is already a website -- that is the point of it -- so opening
index.html in a browser works with no server at all. This adds the one thing
a file:// browse cannot do: search across pages, with each result carrying
its document ID, version, status, and scope.

Read-only and bound to localhost by default. Nothing here writes to the
corpus; teaching happens in the console, where a person is present to be
asked what they mean.
"""

from __future__ import annotations

import html
import urllib.parse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import cite
from .index import Index
from .validate import validate

SEARCH_PATH = "/_search"
REPORT_PATH = "/_report"


class Handler(SimpleHTTPRequestHandler):
    """Serves the corpus, plus /_search and /_report."""

    def __init__(self, *args, root: Path, **kwargs):
        self.root = root
        super().__init__(*args, directory=str(root), **kwargs)

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == SEARCH_PATH:
            return self._search(urllib.parse.parse_qs(parsed.query))
        if parsed.path == REPORT_PATH:
            return self._report()
        return super().do_GET()

    def log_message(self, fmt, *args) -> None:
        pass  # quiet by default; the console is the interesting output

    # -- pages -------------------------------------------------------------
    def _search(self, query: dict) -> None:
        term = (query.get("q") or [""])[0]
        status = (query.get("status") or ["current"])[0]
        status = status if status in ("current", "any") else "current"
        index = Index.open(self.root)
        try:
            hits = index.search(term, status=status, limit=25) if term else []
            body = [
                _form(term, status),
                f"<p class='eyebrow'>{len(hits)} result(s) · status filter: {status}</p>",
            ]
            for hit in hits:
                flag = " <strong>[RETIRED]</strong>" if hit.retired else ""
                body.append(
                    "<div class='record'><dl>"
                    f"<dt>Document ID</dt><dd>{html.escape(hit.document_id)}</dd>"
                    f"<dt>Path</dt><dd><a href='/{html.escape(hit.path)}'>"
                    f"{html.escape(hit.path)}</a>{flag}</dd>"
                    f"<dt>Scope</dt><dd>{html.escape(hit.scope)}</dd>"
                    f"<dt>Updated</dt><dd>{html.escape(hit.updated)}</dd>"
                    f"<dt>Substrate</dt><dd>{html.escape(hit.substrate)} · "
                    f"{html.escape(hit.status)}</dd>"
                    "</dl>"
                    f"<p>{html.escape(hit.snippet(term))}</p>"
                    f"<p><code>{html.escape(cite.bracket(hit))}</code></p>"
                    "</div>"
                )
            if term and not hits:
                body.append(
                    "<p>Nothing in this corpus matched, so there is nothing to "
                    "cite. Try a term from a spoke's declared scope.</p>"
                )
            body.append(_spokes(index))
            self._send(_shell("Search", "\n".join(body)))
        finally:
            index.close()

    def _report(self) -> None:
        report = validate(self.root)
        rows = [
            "<p>The eight structural checks of §11, run against this corpus "
            "right now.</p>"
        ]
        if report.ok:
            rows.append("<div class='record'><dl><dt>Result</dt><dd>11.1–11.8 all "
                        "clean</dd></dl></div>")
        else:
            for check, findings in report.by_check().items():
                rows.append(f"<h2>{html.escape(check)}</h2><ul class='map'>")
                for finding in findings:
                    rows.append(f"<li>{html.escape(str(finding))}</li>")
                rows.append("</ul>")
        self._send(_shell("Structural report", "\n".join(rows)))

    def _send(self, page: str) -> None:
        payload = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _shell(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} — MPLPB</title>
<link rel="stylesheet" href="/style.css"></head>
<body><main>
<p class="eyebrow">MPLPB local web · front end</p>
<h1>{html.escape(title)}</h1>
{body}
<nav class="related">
  <a href="/index.html">Main Index</a>
  <a href="{SEARCH_PATH}">Search</a>
  <a href="{REPORT_PATH}">Structural report</a>
</nav>
</main></body></html>
"""


def _form(term: str, status: str) -> str:
    any_checked = " checked" if status == "any" else ""
    return f"""<form method="get" action="{SEARCH_PATH}">
<p><input name="q" value="{html.escape(term)}" size="40" autofocus>
<button type="submit">Search</button></p>
<p class="eyebrow"><label><input type="checkbox" name="status" value="any"
{any_checked}> include retired pages</label></p>
</form>"""


def _spokes(index: Index) -> str:
    spokes = index.spokes()
    if not spokes:
        return ""
    items = "\n".join(
        f"<li><a href='/{html.escape(s)}/_index.html'>{html.escape(s)}</a>"
        f"<span class='scope'>scope: {html.escape(scope)}</span></li>"
        for s, scope in sorted(spokes.items())
    )
    return f"<h2>Spokes</h2><ul class='map'>{items}</ul>"


def serve(root: Path, host: str = "127.0.0.1", port: int = 8000) -> int:
    root = Path(root).resolve()
    if not (root / "index.html").exists():
        raise FileNotFoundError(f"no index.html at {root}")
    handler = partial(Handler, root=root)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"serving {root} at http://{host}:{port}/index.html")
    print(f"  search   http://{host}:{port}{SEARCH_PATH}")
    print(f"  report   http://{host}:{port}{REPORT_PATH}")
    print("  ctrl-c to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0
