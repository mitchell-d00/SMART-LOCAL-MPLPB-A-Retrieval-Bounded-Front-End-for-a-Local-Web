"""
Page parsing — the one place that knows what an MPLPB page looks like.

MPLPB-LOCAL-008 v4 §5 (page metadata), §5.1 (field formats).

Both the crawler and the validator used to carry their own HTMLParser
subclass. Two parsers means two definitions of "what counts as a link",
which is exactly the metadata-trust failure the spec names as FM-L9. There
is one parser here and everything else imports it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

#: Fields every page must declare (§5). Order is the order they are reported.
REQUIRED_META = (
    "mplpb:document-id",
    "mplpb:category",
    "mplpb:updated",
    "mplpb:scope",
    "mplpb:when-to-use",
    "mplpb:status",
)

#: Fields a page may declare.
OPTIONAL_META = ("mplpb:owner", "mplpb:supersedes", "mplpb:protected")

VALID_STATUS = ("current", "retired")

SUPERSEDED_DIR = "superseded"
LOG_DIR = "_log"
SUB_INDEX = "_index.html"
ROOT_PAGE = "index.html"

#: ISO 8601 with timezone, a space, then a version token: 2026-08-05T18:40Z v2
UPDATED_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:?\d{2})\s+v(\d+)$"
)

_NON_LOCAL = ("http://", "https://", "mailto:", "#", "data:", "javascript:")


class _PageParser(HTMLParser):
    """Extract mplpb metadata, typed links, title, and visible text."""

    SKIP = {"script", "style", "head", "title"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.links: list[dict[str, str]] = []
        self.title = ""
        self._chunks: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._card_depth = 0

    def handle_starttag(self, tag, attrs) -> None:
        a = dict(attrs)
        # The record card restates metadata already captured as meta tags.
        # Indexing it twice makes every page look like a match for its own
        # field names, so it is skipped as display, not content.
        if self._card_depth:
            if tag == "div":
                self._card_depth += 1
        elif tag == "div" and "record" in (a.get("class") or "").split():
            self._card_depth = 1
        name = (a.get("name") or "").strip()
        if tag == "meta" and name.startswith("mplpb:"):
            self.meta[name] = (a.get("content") or "").strip()
        if tag in ("link", "a") and a.get("href"):
            rels = (a.get("rel") or "").split() or [""]
            for r in rels:
                self.links.append({"rel": r.lower(), "href": a["href"].strip()})
        if tag == "title":
            self._in_title = True
        if tag in self.SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag) -> None:
        if self._card_depth and tag == "div":
            self._card_depth -= 1
            return
        if tag == "title":
            self._in_title = False
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data) -> None:
        if self._card_depth:
            return
        if self._in_title:
            self.title += data.strip()
        elif not self._skip_depth:
            text = data.strip()
            if text:
                self._chunks.append(text)

    @property
    def text(self) -> str:
        return " ".join(self._chunks)


@dataclass
class Page:
    """A parsed page. The HTML is authoritative; this is derived (§5.2)."""

    path: Path
    root: Path
    meta: dict[str, str] = field(default_factory=dict)
    links: list[dict[str, str]] = field(default_factory=list)
    title: str = ""
    text: str = ""

    # -- declared fields ---------------------------------------------------
    @property
    def document_id(self) -> str:
        return self.meta.get("mplpb:document-id", "")

    @property
    def category(self) -> str:
        return self.meta.get("mplpb:category", "")

    @property
    def scope(self) -> str:
        return self.meta.get("mplpb:scope", "")

    @property
    def when_to_use(self) -> str:
        return self.meta.get("mplpb:when-to-use", "")

    @property
    def updated(self) -> str:
        return self.meta.get("mplpb:updated", "")

    @property
    def owner(self) -> str:
        return self.meta.get("mplpb:owner", "")

    @property
    def status(self) -> str:
        return self.meta.get("mplpb:status", "")

    @property
    def supersedes(self) -> list[str]:
        return split_ids(self.meta.get("mplpb:supersedes", ""))

    @property
    def protected(self) -> bool:
        """Owner-declared sensitivity flag. A retrieval filter, not access
        control -- see mplpb.guard and docs/lineage.md."""
        return self.meta.get("mplpb:protected", "").lower() in ("1", "true", "yes")

    # -- derived -----------------------------------------------------------
    @property
    def rel(self) -> str:
        return self.path.relative_to(self.root).as_posix()

    @property
    def rels(self) -> set[str]:
        return {link["rel"] for link in self.links if link["rel"]}

    @property
    def is_sub_index(self) -> bool:
        return self.path.name == SUB_INDEX

    @property
    def is_root(self) -> bool:
        return self.path.resolve() == (self.root / ROOT_PAGE).resolve()

    @property
    def is_index(self) -> bool:
        return self.is_root or self.is_sub_index

    @property
    def spoke(self) -> str:
        """Directory that owns this page, '' for pages at the root."""
        parts = self.path.relative_to(self.root).parts
        return parts[0] if len(parts) > 1 else ""

    @property
    def in_superseded(self) -> bool:
        return SUPERSEDED_DIR in self.path.relative_to(self.root).parts

    @property
    def version(self) -> int:
        """Version number parsed out of `updated`; 0 when unparseable."""
        m = UPDATED_RE.match(self.updated)
        return int(m.group(3)) if m else 0

    @property
    def timestamp(self) -> str:
        """ISO portion of `updated`; '' when unparseable."""
        return self.updated.split()[0] if UPDATED_RE.match(self.updated) else ""

    def internal_hrefs(self) -> list[str]:
        return [link["href"] for link in self.links if is_internal(link["href"])]

    def resolve(self, href: str) -> Path:
        """Resolve an href against this page's directory."""
        return (self.path.parent / href.split("#")[0]).resolve()


def is_internal(href: str) -> bool:
    """True for links that address a file inside this corpus."""
    return not href.lower().startswith(_NON_LOCAL)


def is_absolute(href: str) -> bool:
    """Root-relative or file: links break portability (§4.2)."""
    return href.startswith("/") or href.lower().startswith("file:")


def inside(target: Path, root: Path) -> bool:
    """§4.3 crawl boundary: the canonical path must stay inside the root."""
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def split_ids(value: str) -> list[str]:
    """`supersedes` is a semicolon-separated list of document IDs (§5.1)."""
    return [part.strip() for part in value.split(";") if part.strip()]


def split_triggers(value: str) -> list[str]:
    """`when-to-use` is semicolon-separated trigger conditions (§5.1)."""
    return [part.strip() for part in value.split(";") if part.strip()]


def parse(path: Path, root: Path) -> Page:
    """Read and parse one page."""
    p = _PageParser()
    p.feed(path.read_text(encoding="utf-8", errors="replace"))
    p.close()
    return Page(
        path=path,
        root=root,
        meta=p.meta,
        links=p.links,
        title=p.title,
        text=p.text,
    )


def load_all(root: Path) -> dict[Path, Page]:
    """Parse every .html file beneath root, keyed by resolved path."""
    return {p.resolve(): parse(p, root) for p in sorted(root.rglob("*.html"))}
