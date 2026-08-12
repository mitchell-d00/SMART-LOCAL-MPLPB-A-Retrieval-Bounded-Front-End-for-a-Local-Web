"""
Command line entry point.

    python3 -m mplpb chat site
    python3 -m mplpb ask site "what is a spoke?"
    python3 -m mplpb search site "relative link" --status any
    python3 -m mplpb id site LOCAL-SPEC-OLD-001
    python3 -m mplpb crawl site -o records.jsonl
    python3 -m mplpb validate site
    python3 -m mplpb serve site --port 8000
    python3 -m mplpb new mycorpus --title "Kiln Notes" --owner "Your Name"

Exit code 1 on a failed validation or an orphan page, so any of these drops
straight into CI.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, cite
from .console import Console
from .crawl import crawl
from .index import Index
from .notebook import Notebook, render_page, stamp
from .scaffold import new_corpus
from .validate import validate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mplpb", description="Front end for an MPLPB local web."
    )
    parser.add_argument("--version", action="version", version=f"mplpb {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def with_root(p, default="site"):
        p.add_argument("root", nargs="?", default=default, help="corpus root")
        return p

    chat = with_root(sub.add_parser("chat", help="interactive console"))
    chat.add_argument("--mode", help="starting mode, e.g. teaching_mode")
    chat.add_argument("--owner", default="", help="name recorded on taught pages")
    chat.add_argument("--style", choices=["bracket", "dagger"], default="bracket")
    chat.add_argument("--no-color", action="store_true")

    ask = with_root(sub.add_parser("ask", help="one question, then exit"))
    ask.add_argument("question")
    ask.add_argument("--mode")

    search = with_root(sub.add_parser("search", help="full-text search"))
    search.add_argument("query")
    search.add_argument("--status", choices=["current", "any"], default="current")
    search.add_argument("-n", "--limit", type=int, default=5)

    lookup = with_root(sub.add_parser("id", help="look up one document ID"))
    lookup.add_argument("document_id")
    lookup.add_argument("--history", action="store_true", help="include what it superseded")

    crawler = with_root(sub.add_parser("crawl", help="emit crawl records as JSONL"))
    crawler.add_argument("-o", "--out")

    with_root(sub.add_parser("validate", help="run the eight structural checks"))

    server = with_root(sub.add_parser("serve", help="browse and search in a browser"))
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8000)

    teach = with_root(sub.add_parser("teach", help="write a taught page"))
    teach.add_argument("question")
    teach.add_argument("answer")
    teach.add_argument("--owner", default="")

    scaffold = sub.add_parser("new", help="create an empty corpus that validates")
    scaffold.add_argument("root")
    scaffold.add_argument("--title", default="Local Web")
    scaffold.add_argument("--owner", default="")
    scaffold.add_argument("--spoke", action="append", default=[],
                          help="spoke as name:scope, repeatable")

    args = parser.parse_args(argv)
    return _dispatch(args)


def _dispatch(args) -> int:
    if args.command == "new":
        return new_corpus(
            Path(args.root), title=args.title, owner=args.owner, spokes=args.spoke
        )

    root = Path(args.root)
    if args.command != "serve" and not (root / "index.html").exists():
        print(f"no index.html at {root.resolve()}", file=sys.stderr)
        print("run: python3 -m mplpb new <dir>", file=sys.stderr)
        return 1

    if args.command == "chat":
        console = Console(
            root, owner=args.owner, mode=args.mode, style=args.style,
            color=False if args.no_color else None,
        )
        return console.run()

    if args.command == "ask":
        console = Console(root, mode=args.mode, color=False)
        print(console.ask(args.question))
        return 0

    if args.command == "search":
        return _search(root, args)

    if args.command == "id":
        return _lookup(root, args)

    if args.command == "crawl":
        result = crawl(root)
        if args.out:
            Path(args.out).write_text(result.as_jsonl() + "\n", encoding="utf-8")
        else:
            print(result.as_jsonl())
        print(
            f"\ningested {len(result.records)} page(s): {result.graph_count} via graph, "
            f"{result.audit_count} retired via audit",
            file=sys.stderr,
        )
        if result.orphans:
            print(f"FM-L2  {len(result.orphans)} orphan(s) NOT ingested:", file=sys.stderr)
            for orphan in result.orphans:
                print(f"       {orphan}", file=sys.stderr)
            return 1
        return 0

    if args.command == "validate":
        report = validate(root)
        print(report.summary())
        return 0 if report.ok else 1

    if args.command == "serve":
        from .server import serve

        return serve(root, host=args.host, port=args.port)

    if args.command == "teach":
        notebook = Notebook(root, owner=args.owner)
        written = notebook.teach(args.question, args.answer)
        print(written.describe(root.resolve()))
        report = validate(root)
        print(report.summary())
        return 0 if report.ok else 1

    return 1


def _search(root: Path, args) -> int:
    index = Index.open(root)
    try:
        hits = index.search(args.query, status=args.status, limit=args.limit)
        if not hits:
            print("no results")
        for hit in hits:
            flag = "  [RETIRED]" if hit.retired else ""
            print(f"\n{hit.title or hit.path}{flag}")
            print(f"  id       {hit.document_id}")
            print(f"  path     {hit.path}  ({hit.substrate}, {hit.discovered_by})")
            print(f"  scope    {hit.scope}")
            print(f"  version  {hit.updated}")
            print(f"  cite     {cite.bracket(hit)}")
        if index.orphans:
            print(
                f"\nFM-L2  {len(index.orphans)} orphan(s) excluded from the index",
                file=sys.stderr,
            )
        return 0
    finally:
        index.close()


def _lookup(root: Path, args) -> int:
    index = Index.open(root)
    try:
        hits = index.history(args.document_id) if args.history else index.by_id(args.document_id)
        if not hits:
            print(f"no document with ID {args.document_id}")
            return 1
        for hit in hits:
            print(f"\n{hit.title or hit.path}")
            print(f"  {cite.bracket(hit)}")
            print(f"  scope    {hit.scope}")
            print(f"  {hit.snippet('', 200)}")
        return 0
    finally:
        index.close()


if __name__ == "__main__":
    sys.exit(main())
