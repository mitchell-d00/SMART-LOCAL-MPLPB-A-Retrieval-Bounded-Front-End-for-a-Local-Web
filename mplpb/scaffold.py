"""
Scaffolding: create a corpus that validates before it contains anything.

An empty corpus that passes 11.1-11.8 on the first run is worth more than a
rich one that has never been checked, because from then on every failure is
something you just did rather than something you inherited.
"""

from __future__ import annotations

import html
import shutil
from pathlib import Path

from .notebook import ENTRY_MARKER, Notebook, render_page, stamp
from .validate import validate

STYLE = Path(__file__).parent / "data" / "style.css"


def new_corpus(
    root: Path,
    *,
    title: str = "Local Web",
    owner: str = "",
    spokes: list[str] | None = None,
) -> int:
    root = Path(root).resolve()
    if (root / "index.html").exists():
        print(f"refusing to overwrite an existing corpus at {root}")
        return 1
    root.mkdir(parents=True, exist_ok=True)
    (root / "_log" / "superseded").mkdir(parents=True, exist_ok=True)

    declared = [_split_spoke(s) for s in (spokes or [])]
    for name, scope in declared:
        (root / name).mkdir(parents=True, exist_ok=True)
        (root / name / "_index.html").write_text(
            _sub_index(name, scope, owner), encoding="utf-8"
        )

    shutil.copyfile(STYLE, root / "style.css")
    (root / "index.html").write_text(_main_index(title, owner, declared), encoding="utf-8")
    (root / "BOOT.md").write_text(_boot_md(title), encoding="utf-8")
    (root / "_log" / "revisions.html").write_text(_revisions(owner), encoding="utf-8")
    Notebook(root, owner=owner).ensure()

    report = validate(root)
    print(f"created {root}")
    print(report.summary())
    print(
        "\nnext:\n"
        f"  python3 -m mplpb chat {root}\n"
        f"  python3 -m mplpb serve {root}\n"
        "  fill in the boot block in index.html and BOOT.md"
    )
    return 0 if report.ok else 1


def _split_spoke(raw: str) -> tuple[str, str]:
    name, _, scope = raw.partition(":")
    return name.strip() or "spoke", scope.strip() or "[Declare what this spoke owns.]"


def _main_index(title: str, owner: str, spokes: list[tuple[str, str]]) -> str:
    entries = [
        f'  <li><a href="{html.escape(name)}/_index.html">{html.escape(name)}</a>\n'
        f'    <span class="scope">scope: {html.escape(scope)}</span></li>'
        for name, scope in spokes
    ]
    entries.append(
        '  <li><a href="_log/revisions.html">Revision log</a>\n'
        '    <span class="scope">scope: append-only record of changes and '
        "supersessions</span></li>"
    )
    body = f"""<h2>Boot block</h2>
<div class="boot">
<p><strong>What this corpus is.</strong> [One paragraph: project, purpose,
current phase. Replace this.]</p>

<p><strong>Authoritative root.</strong> This file. Every internal link is
relative to it. The crawl boundary is this directory; a link resolving outside
it must be rejected.</p>

<p><strong>Retrieval rule.</strong> Answer corpus-dependent questions from
retrieved pages, not from memory of a previous session. Prefer documents with
<code>status: current</code> reachable from this index. Cite retrieved pages as
local documents, never as published ones.</p>

<p><strong>Routing.</strong> Broad request &rarr; the relevant Sub-Index.
Specific request &rarr; the best operational page. Uncertain &rarr; this index,
and ask the user to narrow. After answering &rarr; name one to three related
pages and the path back.</p>

<p><strong>Precedence.</strong> The spoke whose declared scope owns a question
answers it. Retrieval may return results from several spokes and must preserve
each result's source scope. Answering does not merge them.</p>

<p><strong>Modes.</strong> Default <code>strict_tool_mode</code>.
<code>hard_reality_mode</code> overrides all others on legal, medical-adjacent,
contractual, or high-stakes safety topics.</p>

<p><strong>Current state / open questions.</strong> [Two or three live items
with paths. Replace this.]</p>
</div>

<h2>Category map</h2>
<ul class="map">
{chr(10).join(entries)}
</ul>

<h2>Maintenance</h2>
<p><code>python3 -m mplpb validate .</code> runs the eight checks;
<code>python3 -m mplpb chat .</code> opens the console;
<code>python3 -m mplpb serve .</code> opens it in a browser.</p>

<nav class="related">
  <a href="BOOT.md">BOOT.md &mdash; plain-text twin of this boot block</a>
</nav>"""
    return render_page(
        title=f"Main Index — {title}",
        document_id="LOCAL-MAIN-000",
        category="Navigator / Main Index",
        scope="Entry point, crawl root, and routing map for this corpus",
        when_to_use=(
            "First page read in any session; crawl entry point; "
            "uncertain which spoke owns a query"
        ),
        updated=stamp(),
        owner=owner,
        status="current",
        depth=0,
        up="./index.html",
        heading="Main Index",
        eyebrow="MPLPB local web · crawl root",
        body=body,
        self_link=False,
    ).replace('<link rel="index" href="index.html">\n<link rel="up" href="./index.html">\n', "")


def _sub_index(name: str, scope: str, owner: str) -> str:
    return render_page(
        title=f"{name} Sub-Index",
        document_id=f"LOCAL-{name.upper().replace('_', '-')}-INDEX",
        category="Navigator / Sub-Index",
        scope=scope,
        when_to_use=f"Broad question about {name}; unsure which page in {name} owns it",
        updated=stamp(),
        owner=owner,
        status="current",
        depth=1,
        up="../index.html",
        heading=f"{name} Sub-Index",
        eyebrow="MPLPB local web · sub-index",
        body=(
            f"<p><strong>Scope.</strong> {html.escape(scope)}</p>\n"
            f'<h2>Pages</h2>\n<ul class="map">\n{ENTRY_MARKER}\n</ul>'
        ),
        self_link=False,
    )


def _revisions(owner: str) -> str:
    return render_page(
        title="Revision Log",
        document_id="LOCAL-LOG-000",
        category="Log / Revisions",
        scope="Append-only record of changes and supersessions in this corpus",
        when_to_use="Asking what changed; asking when a document was superseded",
        updated=stamp(),
        owner=owner,
        status="current",
        depth=1,
        up="../index.html",
        heading="Revision Log",
        eyebrow="MPLPB local web · append-only",
        body=(
            "<p>Append only. Entries are added, never edited or removed. A "
            "retired page is moved to <code>_log/superseded/</code> and named "
            "here; it is never deleted.</p>\n"
            f'<h2>Entries</h2>\n<ul class="map">\n{ENTRY_MARKER}\n</ul>'
        ),
        self_link=False,
    )


def _boot_md(title: str) -> str:
    return f"""# BOOT — {title}

**Authoritative copy is `index.html`.** This twin exists for tools that read
markdown more readily than HTML. If the two disagree, `index.html` wins.

**What this corpus is.** [One paragraph. Replace.]

**Authoritative root.** `index.html`. All internal links are relative to it. The
crawl boundary is this directory.

**Retrieval rule.** Answer corpus-dependent questions from retrieved pages.
Prefer `status: current` documents reachable from the Main Index. Cite retrieved
pages as local documents, not published ones.

**Routing.** Broad → Sub-Index. Specific → best page. Uncertain → Main Index and
ask. After answering → name 1–3 related pages and the path back.

**Precedence.** Retrieval may span spokes and must preserve each result's scope.
Answering does not merge them; when no single scope owns the query, ask the user
to narrow.

**Modes.** Default `strict_tool_mode`. `hard_reality_mode` overrides all others
on legal, medical-adjacent, contractual, or high-stakes safety topics.

**Current state.** [Two or three live items with paths.]
"""
