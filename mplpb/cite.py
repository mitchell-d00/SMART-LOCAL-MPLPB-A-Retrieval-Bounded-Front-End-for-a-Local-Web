"""
Citations.

Two rules from the spec drive this module and neither is cosmetic.

FM-L7, retrieval without provenance: a returned fragment that does not carry
its document ID, path, version, and status is not usable, because nothing
downstream can tell whether it is current.

FM-L10, local/public confusion: a local page cited as though it were
published invents an authority the corpus does not have. Every citation
here says `local`, every time, including when it is inconvenient.

Two formats are offered. `bracket` is the default and is meant to be read.
`dagger` follows the citation format in the Mythic-Logic paper's document
engine (message:index+title+lines) for callers already using it.
"""

from __future__ import annotations

from .index import Hit

LOCAL_NOTICE = (
    "Local corpus document, not a published source. Cite it as a local page."
)


def bracket(hit: Hit) -> str:
    """[LOCAL-SPEC-001 · spec/link_discipline.html · v2 · local · current]"""
    parts = [
        hit.document_id or "NO-ID",
        hit.path,
        hit.version,
        hit.substrate,
        hit.status,
    ]
    return "[" + " \u00b7 ".join(parts) + "]"


def dagger(hit: Hit) -> str:
    """local:<path>+<title>+<document-id> v<n>, after the document engine."""
    return f"local:{hit.path}\u2020{hit.title or 'untitled'}\u2020{hit.document_id} {hit.version}"


def line(hit: Hit, style: str = "bracket") -> str:
    citation = dagger(hit) if style == "dagger" else bracket(hit)
    flag = "  RETIRED - superseded, kept for provenance" if hit.retired else ""
    return citation + flag


def block(hits: list[Hit], style: str = "bracket") -> str:
    """A citation list for an answer drawn from several pages."""
    if not hits:
        return ""
    lines = ["Sources (all local):"]
    lines += [f"  {line(hit, style)}" for hit in hits]
    return "\n".join(lines)


def scope_note(hit: Hit) -> str:
    """What the cited page claims to own -- the boundary on its answer."""
    return f"{hit.path} owns: {hit.scope}" if hit.scope else f"{hit.path} declares no scope (FM-L3)"
