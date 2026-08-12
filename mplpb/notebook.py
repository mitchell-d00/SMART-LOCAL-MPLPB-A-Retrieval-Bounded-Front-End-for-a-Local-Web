"""
The notebook: where a taught answer goes.

The BASIC program this front end descends from remembered by appending
`question:answer` to data.txt and grepping it later. That works, and it is
the right instinct -- memory and association are most of what makes a system
feel like it knows you. But in a local web, an appended line is invisible to
the crawler, has no document ID, no scope, no timestamp, and no way to be
superseded. It is the flat-file version of an orphan (FM-L2).

So the same move, done in the corpus's own terms: a taught answer becomes an
HTML page with full metadata, linked from its Sub-Index, recorded in the
revision log, and reachable from the Main Index. It validates. It gets
crawled. It can be cited with provenance, and later superseded rather than
overwritten -- which means the corpus can still answer what it used to say.

    120 OPEN "data.txt" FOR APPEND AS #1
    130 PRINT #1, Q$; ":"; A$

    ->  notebook/what_is_a_spoke.html    LOCAL-NOTE-0003    v1    current
"""

from __future__ import annotations

import html
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .page import LOG_DIR, SUPERSEDED_DIR, load_all, parse

ENTRY_MARKER = "<!-- mplpb:entries -->"
NOTE_ID = re.compile(r"^LOCAL-NOTE-(\d+)$")


def stamp(version: int = 1) -> str:
    """ISO 8601 with timezone, a space, then a version token (§5.1). The time
    component is not decoration: three revisions in one working day cannot be
    ordered from a date alone."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    return f"{now} v{version}"


def slug(text: str, limit: int = 48) -> str:
    out = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return (out[:limit].rstrip("_") or "note")


@dataclass
class Written:
    """What a teach or revise call changed on disk."""

    document_id: str
    path: Path
    version: int
    superseded: str = ""
    retired_path: Path | None = None

    def describe(self, root: Path) -> str:
        rel = self.path.relative_to(root).as_posix()
        line = f"{self.document_id}  {rel}  v{self.version}"
        if self.superseded and self.retired_path:
            old = self.retired_path.relative_to(root).as_posix()
            line += f"\n  supersedes {self.superseded} -> {old} (retired, kept)"
        return line


class Notebook:
    """Writes taught pages into a spoke of a local web."""

    def __init__(self, root: Path, spoke: str = "notebook", owner: str = ""):
        self.root = Path(root).resolve()
        self.spoke = spoke
        self.owner = owner
        self.dir = self.root / spoke
        self.sub_index = self.dir / "_index.html"
        self.revisions = self.root / LOG_DIR / "revisions.html"
        self.superseded = self.root / LOG_DIR / SUPERSEDED_DIR

    # -- setup -------------------------------------------------------------
    def ensure(self) -> None:
        """Create the spoke, its Sub-Index, and the Main Index entry."""
        self.dir.mkdir(parents=True, exist_ok=True)
        self.superseded.mkdir(parents=True, exist_ok=True)
        if not self.sub_index.exists():
            self.sub_index.write_text(self._sub_index_html(), encoding="utf-8")
        self._link_from_main_index()

    def _sub_index_html(self) -> str:
        return render_page(
            title="Notebook Sub-Index",
            document_id="LOCAL-NOTE-INDEX",
            category="Navigator / Sub-Index",
            scope="Answers taught to the console during a session, one page each",
            when_to_use=(
                "Looking for something taught rather than authored; "
                "auditing what the console has been told"
            ),
            updated=stamp(),
            owner=self.owner,
            status="current",
            depth=1,
            up="../index.html",
            heading="Notebook",
            eyebrow="MPLPB local web \u00b7 taught pages",
            body=(
                "<p>Each page below was taught to the console in a session and "
                "written here as a document, with an ID, a timestamp, and a "
                "version. Nothing here is authored knowledge; it is recorded "
                "knowledge, and it is only as good as whoever typed it.</p>\n"
                f'<h2>Entries</h2>\n<ul class="map">\n{ENTRY_MARKER}\n</ul>'
            ),
            self_link=False,
        )

    def _link_from_main_index(self) -> None:
        index = self.root / "index.html"
        if not index.exists():
            return
        text = index.read_text(encoding="utf-8")
        href = f"{self.spoke}/_index.html"
        if href in text:
            return
        entry = (
            f'  <li><a href="{href}">Notebook</a>\n'
            f'    <span class="scope">scope: answers taught to the console, '
            f"one page each</span></li>\n"
        )
        match = re.search(r'(<ul class="map">)(.*?)(</ul>)', text, re.S)
        if match:
            text = text[: match.end(2)] + entry + text[match.end(2) :]
        else:  # no category map to join -- add one rather than fail silently
            text = text.replace(
                "</main>",
                f'<h2>Category map</h2>\n<ul class="map">\n{entry}</ul>\n</main>',
            )
        index.write_text(text, encoding="utf-8")

    # -- writing -----------------------------------------------------------
    def teach(
        self,
        question: str,
        answer: str,
        *,
        title: str = "",
        category: str = "Notebook / Taught",
        sources: list[str] | None = None,
        protected: bool = False,
    ) -> Written:
        """Record one taught answer as a new page."""
        self.ensure()
        document_id = self._next_id()
        name = self._free_name(slug(title or question))
        path = self.dir / name
        path.write_text(
            self._note_html(
                document_id=document_id,
                title=title or _headline(question),
                question=question,
                answer=answer,
                version=1,
                updated=stamp(1),
                supersedes="",
                sources=sources or [],
                protected=protected,
            ),
            encoding="utf-8",
        )
        self._add_entry(path, title or question)
        self._log(f"{document_id} created at {self._rel(path)} (taught)")
        return Written(document_id, path, 1)

    def revise(
        self,
        document_id: str,
        answer: str,
        *,
        question: str = "",
        title: str = "",
        note: str = "",
    ) -> Written:
        """Supersede a taught page. The old version is retired, never deleted.

        Retiring means: move to _log/superseded/, flip status to retired,
        remove it from the Sub-Index, name it in the replacement's
        `supersedes`, and log the change. All five, or the corpus disagrees
        with itself and check 11.5 says so."""
        self.ensure()
        old_path = self._find(document_id)
        if old_path is None:
            raise KeyError(f"no current page with document ID {document_id}")

        old = parse(old_path, self.root)
        old_question = question or _extract(old_path, "question") or old.title
        new_title = title or old.title
        version = old.version + 1
        dead_id = f"{document_id}-R{old.version}"

        # 1. retire the old page
        self.superseded.mkdir(parents=True, exist_ok=True)
        retired_path = self.superseded / self._free_name(
            old_path.stem + f"_v{old.version}.html", self.superseded
        )
        shutil.move(str(old_path), str(retired_path))
        self._retire_in_place(retired_path, dead_id, note)

        # 2. remove it from the Sub-Index
        self._remove_entry(old_path)

        # 3. write the replacement
        new_path = self.dir / self._free_name(slug(new_title or old_question))
        new_path.write_text(
            self._note_html(
                document_id=document_id,
                title=new_title,
                question=old_question,
                answer=answer,
                version=version,
                updated=stamp(version),
                supersedes=dead_id,
                sources=[],
                protected=old.protected,
                note=note,
            ),
            encoding="utf-8",
        )
        self._add_entry(new_path, new_title)
        self._log(
            f"{document_id} revised to v{version} at {self._rel(new_path)}; "
            f"{dead_id} retired to {self._rel(retired_path)}"
            + (f" -- {note}" if note else "")
        )
        return Written(document_id, new_path, version, dead_id, retired_path)

    # -- html --------------------------------------------------------------
    def _note_html(
        self,
        *,
        document_id: str,
        title: str,
        question: str,
        answer: str,
        version: int,
        updated: str,
        supersedes: str,
        sources: list[str],
        protected: bool,
        note: str = "",
    ) -> str:
        body = [
            '<div class="boot">',
            f"<p><strong>Question.</strong> {html.escape(question)}</p>",
            "</div>",
            "<h2>Answer</h2>",
        ]
        body += [f"<p>{html.escape(para)}</p>" for para in _paragraphs(answer)]
        if note:
            body.append(f"<h2>Revision note</h2>\n<p>{html.escape(note)}</p>")
        if sources:
            body.append("<h2>Consulted</h2>\n<ul class=\"map\">")
            body += [f"  <li>{html.escape(s)}</li>" for s in sources]
            body.append("</ul>")
        body.append(
            "<h2>Provenance</h2>\n<p>Taught to the console in a session and "
            "recorded here verbatim. This page is a record of what someone "
            "said, not a verified claim. Supersede it rather than editing it "
            "in place.</p>"
        )
        return render_page(
            title=title,
            document_id=document_id,
            category="Notebook / Taught",
            scope=f"The taught answer to: {question.strip()}",
            when_to_use=f"{question.strip()}; recall of a taught answer",
            updated=updated,
            owner=self.owner,
            status="current",
            supersedes=supersedes,
            protected=protected,
            depth=1,
            up="./_index.html",
            heading=title,
            eyebrow="MPLPB local web \u00b7 taught page",
            body="\n".join(body),
            question=question,
        )

    # -- sub-index maintenance --------------------------------------------
    def _add_entry(self, path: Path, label: str) -> None:
        text = self.sub_index.read_text(encoding="utf-8")
        href = f"./{path.name}"
        if f'href="{href}"' in text:
            return
        entry = f'  <li><a href="{href}">{html.escape(label)}</a></li>'
        if ENTRY_MARKER in text:
            text = text.replace(ENTRY_MARKER, f"{entry}\n{ENTRY_MARKER}")
        else:
            text = re.sub(r"(</ul>)", entry + r"\n\1", text, count=1)
        self.sub_index.write_text(_bump(text), encoding="utf-8")

    def _remove_entry(self, path: Path) -> None:
        text = self.sub_index.read_text(encoding="utf-8")
        text = re.sub(
            rf'\s*<li><a href="\./{re.escape(path.name)}">.*?</li>', "", text, flags=re.S
        )
        self.sub_index.write_text(_bump(text), encoding="utf-8")

    def _retire_in_place(self, path: Path, dead_id: str, note: str) -> None:
        """Rewrite a moved page so its metadata and its links still agree with
        where it now lives."""
        text = path.read_text(encoding="utf-8")
        text = _set_meta(text, "mplpb:status", "retired")
        text = _set_meta(text, "mplpb:document-id", dead_id)
        text = text.replace('href="../index.html"', 'href="../../index.html"')
        text = text.replace('href="./_index.html"', f'href="../../{self.spoke}/_index.html"')
        text = text.replace('href="../style.css"', 'href="../../style.css"')
        banner = (
            '<div class="record"><dl><dt>Status</dt><dd>RETIRED &mdash; superseded'
            + (f"; {html.escape(note)}" if note else "")
            + "</dd></dl></div>"
        )
        text = text.replace("<h1>", banner + "\n<h1>", 1)
        path.write_text(text, encoding="utf-8")

    def _log(self, message: str) -> None:
        if not self.revisions.exists():
            self.revisions.parent.mkdir(parents=True, exist_ok=True)
            self.revisions.write_text(_revisions_html(self.owner), encoding="utf-8")
        text = self.revisions.read_text(encoding="utf-8")
        entry = f"  <li><code>{stamp().split()[0]}</code> {html.escape(message)}</li>"
        if ENTRY_MARKER in text:
            text = text.replace(ENTRY_MARKER, f"{entry}\n{ENTRY_MARKER}")
        else:
            text = re.sub(r"(</ul>)", entry + r"\n\1", text, count=1)
        self.revisions.write_text(_bump(text), encoding="utf-8")

    # -- helpers -----------------------------------------------------------
    def _next_id(self) -> str:
        highest = 0
        for page in load_all(self.root).values():
            match = NOTE_ID.match(page.document_id)
            if match:
                highest = max(highest, int(match.group(1)))
        return f"LOCAL-NOTE-{highest + 1:04d}"

    def _find(self, document_id: str) -> Path | None:
        for page in load_all(self.root).values():
            if page.document_id == document_id and page.status == "current":
                return page.path
        return None

    def _free_name(self, base: str, folder: Path | None = None) -> str:
        folder = folder or self.dir
        stem = base[:-5] if base.endswith(".html") else base
        name, n = f"{stem}.html", 2
        while (folder / name).exists():
            name = f"{stem}_{n}.html"
            n += 1
        return name

    def _rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()


# -- page template ---------------------------------------------------------
def render_page(
    *,
    title: str,
    document_id: str,
    category: str,
    scope: str,
    when_to_use: str,
    updated: str,
    status: str,
    heading: str,
    body: str,
    owner: str = "",
    supersedes: str = "",
    protected: bool = False,
    depth: int = 1,
    up: str = "./_index.html",
    eyebrow: str = "MPLPB local web",
    question: str = "",
    self_link: bool = True,
) -> str:
    """One page template, used for every page this package writes.

    `depth` is how many directories down from the root the page sits, which
    is what the relative links are built from. Relative, always: a
    root-relative or file: link is what stops the corpus being portable."""
    up_path = "../" * depth
    esc = html.escape
    meta = [
        f'<meta name="mplpb:document-id" content="{esc(document_id)}">',
        f'<meta name="mplpb:category" content="{esc(category)}">',
        f'<meta name="mplpb:updated" content="{esc(updated)}">',
        f'<meta name="mplpb:scope" content="{esc(scope)}">',
        f'<meta name="mplpb:when-to-use" content="{esc(when_to_use)}">',
        f'<meta name="mplpb:status" content="{esc(status)}">',
        f'<meta name="mplpb:supersedes" content="{esc(supersedes)}">',
    ]
    if owner:
        meta.insert(4, f'<meta name="mplpb:owner" content="{esc(owner)}">')
    if protected:
        meta.append('<meta name="mplpb:protected" content="true">')
    if question:
        meta.append(f'<meta name="mplpb:question" content="{esc(question)}">')

    record = [
        "<dt>Document ID</dt><dd>" + esc(document_id) + "</dd>",
        "<dt>Category</dt><dd>" + esc(category) + "</dd>",
        "<dt>Updated</dt><dd>" + esc(updated) + "</dd>",
    ]
    if owner:
        record.append("<dt>Owner</dt><dd>" + esc(owner) + "</dd>")
    record.append("<dt>Scope</dt><dd>" + esc(scope) + "</dd>")
    record.append("<dt>Status</dt><dd>" + esc(status) + "</dd>")
    if supersedes:
        record.append("<dt>Supersedes</dt><dd>" + esc(supersedes) + "</dd>")

    related = ""
    if self_link:
        related = (
            '<nav class="related">\n'
            f'  <a href="{up}">Up to the Sub-Index</a>\n'
            f'  <a href="{up_path}index.html">Back to the Main Index</a>\n'
            "</nav>"
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
{chr(10).join(meta)}
<link rel="stylesheet" href="{up_path}style.css">
<link rel="index" href="{up_path}index.html">
<link rel="up" href="{up}">
</head>
<body>
<main>
<p class="eyebrow">{esc(eyebrow)}</p>
<h1>{esc(heading)}</h1>

<div class="record"><dl>
  {chr(10).join('  ' + r for r in record)}
</dl></div>

{body}

{related}
</main>
</body>
</html>
"""


def _revisions_html(owner: str = "") -> str:
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
        eyebrow="MPLPB local web \u00b7 append-only",
        body=(
            "<p>Append only. Entries are added, never edited or removed.</p>\n"
            f'<h2>Entries</h2>\n<ul class="map">\n{ENTRY_MARKER}\n</ul>'
        ),
        self_link=False,
    )


def _headline(question: str) -> str:
    text = question.strip().rstrip("?").strip()
    return text[:1].upper() + text[1:] if text else "Taught note"


def _paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    return parts or [text.strip()]


def _set_meta(text: str, name: str, value: str) -> str:
    pattern = rf'(<meta name="{re.escape(name)}" content=")[^"]*(">)'
    if re.search(pattern, text):
        return re.sub(pattern, rf"\g<1>{html.escape(value)}\g<2>", text)
    return text.replace("</head>", f'<meta name="{name}" content="{html.escape(value)}">\n</head>')


def _bump(text: str) -> str:
    """Advance an index page's own `updated` field when its listing changes."""
    match = re.search(r'<meta name="mplpb:updated" content="[^"]*v(\d+)">', text)
    version = int(match.group(1)) + 1 if match else 1
    text = _set_meta(text, "mplpb:updated", stamp(version))
    return re.sub(
        r"(<dt>Updated</dt><dd>)[^<]*(</dd>)", rf"\g<1>{stamp(version)}\g<2>", text
    )


def _extract(path: Path, field: str) -> str:
    page = parse(path, path.parent)
    return page.meta.get(f"mplpb:{field}", "")
