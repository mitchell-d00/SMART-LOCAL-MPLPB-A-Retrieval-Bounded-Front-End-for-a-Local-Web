"""
Retrieval — an in-memory SQLite index over crawl records.

Default retrieval filters to `status = current` (§7.1). Retired pages stay
reachable by explicit status or by document ID, which is what keeps the
corpus able to answer *what did this document used to say* (FM-L11).

Every hit carries its document ID, path, scope, version, status, spoke, and
substrate. A hit that arrives without those is a retrieval-without-provenance
failure (FM-L7) and a local page cited as a published one is FM-L10 — so the
provenance travels with the text, not alongside it.

FTS5 is used when the interpreter's sqlite3 has it, and a LIKE-based ranker
is used when it does not. The corpus should not stop being searchable because
of how someone's Python was compiled.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .crawl import CrawlResult, crawl

_FIELDS = (
    "document_id",
    "path",
    "title",
    "category",
    "scope",
    "when_to_use",
    "updated",
    "status",
    "spoke",
    "substrate",
    "discovered_by",
    "text",
)

_WORD = re.compile(r"[A-Za-z0-9_]+")

#: Words that carry no retrieval signal. Left in an AND query they sink it:
#: "what does the contract say" would require every page to contain "does".
STOPWORDS = frozenset("""
a an and are as at be but by can did do does for from has have how i in is it
its me my of on or should tell that the their them then there these this to
was what when where which who why will with you your about into over under
say says said tell tells told mean means meant just like also very really
thing things get got use used make makes made know knows
""".split())


def content_terms(text: str) -> list[str]:
    """Query terms worth matching on."""
    return [w for w in _WORD.findall(text.lower()) if w not in STOPWORDS and len(w) > 2]


def fts5_available() -> bool:
    db = sqlite3.connect(":memory:")
    try:
        db.execute("CREATE VIRTUAL TABLE _probe USING fts5(a)")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        db.close()


@dataclass(frozen=True)
class Hit:
    """One retrieved page, with the provenance it must never be separated from."""

    document_id: str
    path: str
    title: str
    category: str
    scope: str
    when_to_use: str
    updated: str
    status: str
    spoke: str
    substrate: str
    discovered_by: str
    text: str

    @property
    def retired(self) -> bool:
        return self.status == "retired"

    @property
    def version(self) -> str:
        parts = self.updated.split()
        return parts[-1] if len(parts) > 1 else "v?"

    def snippet(self, query: str = "", width: int = 220) -> str:
        """A window of page text around the first query term, when there is one."""
        text = " ".join(self.text.split())
        if not text:
            return ""
        terms = _WORD.findall(query.lower())
        low = text.lower()
        at = -1
        for term in terms:
            at = low.find(term)
            if at != -1:
                break
        if at == -1:
            return text[:width] + ("..." if len(text) > width else "")
        start = max(0, at - width // 3)
        end = min(len(text), start + width)
        return ("..." if start else "") + text[start:end] + ("..." if end < len(text) else "")


class Index:
    """Queryable index built from crawl records."""

    def __init__(self, result: CrawlResult):
        self.result = result
        self.root = result.root
        self.orphans = result.orphans
        self.records = {r["path"]: r for r in result.records}
        self._fts = fts5_available()
        self.db = sqlite3.connect(":memory:")
        self._build()

    # -- construction ------------------------------------------------------
    @classmethod
    def open(cls, root: Path) -> "Index":
        return cls(crawl(Path(root)))

    def _build(self) -> None:
        cols = ", ".join(_FIELDS)
        if self._fts:
            self.db.execute(f"CREATE VIRTUAL TABLE pages USING fts5({cols})")
        else:
            self.db.execute(f"CREATE TABLE pages ({', '.join(f + ' TEXT' for f in _FIELDS)})")
        self.db.executemany(
            f"INSERT INTO pages ({cols}) VALUES ({', '.join('?' * len(_FIELDS))})",
            [tuple(str(r.get(f, "")) for f in _FIELDS) for r in self.result.records],
        )
        self.db.commit()

    def _rows(self, sql: str, params: tuple) -> list[Hit]:
        cols = ", ".join(_FIELDS)
        return [Hit(*row) for row in self.db.execute(sql.format(cols=cols), params)]

    # -- queries -----------------------------------------------------------
    def search(
        self,
        query: str,
        *,
        status: str = "current",
        spoke: str | None = None,
        limit: int = 5,
    ) -> list[Hit]:
        """Full-text search. `status` is 'current' or 'any' (§7.1)."""
        if not query.strip():
            return []
        # Narrow before broad. Requiring every term keeps a question from
        # dragging in a page that merely shares one common word with it --
        # which is how routing ends up calling two unrelated spokes a tie.
        strict = self._run(query, status, spoke, limit, conjunctive=True)
        if strict:
            return strict
        # The broad pass only earns a result if the question contained a term
        # that is actually distinctive here. Otherwise a page matches because
        # it shares one ordinary word with the question, which is worse than
        # no answer: it looks like retrieval and is not.
        loose = self._run(query, status, spoke, limit, conjunctive=False)
        rare = self.distinctive(content_terms(query))
        if not rare:
            return []
        return [h for h in loose if any(term in _haystack(h) for term in rare)]

    def _run(
        self, query: str, status: str, spoke: str | None, limit: int, conjunctive: bool
    ) -> list[Hit]:
        where, params = [], []
        if self._fts:
            where.append("pages MATCH ?")
            params.append(_fts_query(query, conjunctive))
            order = "ORDER BY rank"
        else:
            terms = content_terms(query)[:8] or [query.lower()]
            joined = []
            for term in terms:
                joined.append(
                    "(lower(text) LIKE ? OR lower(title) LIKE ? OR lower(scope) LIKE ? "
                    "OR lower(when_to_use) LIKE ?)"
                )
                params.extend([f"%{term}%"] * 4)
            where.append("(" + (" AND " if conjunctive else " OR ").join(joined) + ")")
            order = "ORDER BY length(text)"
        if status == "current":
            where.append("status = 'current'")
        if spoke is not None:
            where.append("spoke = ?")
            params.append(spoke)
        sql = f"SELECT {{cols}} FROM pages WHERE {' AND '.join(where)} {order} LIMIT ?"
        params.append(limit)
        try:
            return self._rows(sql, tuple(params))
        except sqlite3.OperationalError:
            # A malformed FTS5 expression is a user typo, not a crash.
            return []

    def distinctive(self, terms: list[str]) -> list[str]:
        """Terms that appear in at most half the corpus. A word every page
        contains cannot tell two pages apart."""
        if not terms:
            return []
        ceiling = max(1, len(self.result.records) // 2)
        out = []
        for term in terms:
            frequency = sum(
                1 for r in self.result.records if term in _haystack_record(r)
            )
            if 0 < frequency <= ceiling:
                out.append(term)
        return out

    def by_id(self, document_id: str) -> list[Hit]:
        """Provenance lookup. Ignores the status filter by design (§7.1)."""
        return self._rows(
            "SELECT {cols} FROM pages WHERE document_id = ? ORDER BY status DESC",
            (document_id.strip(),),
        )

    def by_path(self, path: str) -> Hit | None:
        rows = self._rows("SELECT {cols} FROM pages WHERE path = ? LIMIT 1", (path,))
        return rows[0] if rows else None

    def history(self, document_id: str) -> list[Hit]:
        """The current page for an ID plus every retired page it supersedes,
        transitively. This is the question FM-L11 exists to protect."""
        chain: list[Hit] = []
        seen: set[str] = set()
        frontier = [document_id.strip()]
        while frontier:
            doc_id = frontier.pop(0)
            if doc_id in seen:
                continue
            seen.add(doc_id)
            for hit in self.by_id(doc_id):
                chain.append(hit)
                record = self.records.get(hit.path, {})
                frontier.extend(record.get("supersedes", []))
        return chain

    def spokes(self) -> dict[str, str]:
        """Spoke directory -> declared scope, taken from each Sub-Index."""
        out: dict[str, str] = {}
        for record in self.result.records:
            if record["path"].endswith("_index.html") and record["spoke"]:
                out[record["spoke"]] = record["scope"]
        return out

    def related(self, hit: Hit, limit: int = 3) -> list[Hit]:
        """Pages this one links to, then pages that link to it. Used to name
        one to three neighbours after every answer, per the boot block."""
        record = self.records.get(hit.path, {})
        out: list[Hit] = []
        seen = {hit.path}
        for link in record.get("links", []):
            target = link["target"]
            if target in seen or not target.endswith(".html"):
                continue
            if link["rel"] in ("index", "up") and target == "index.html":
                continue  # the Main Index is the path back, not a neighbour
            neighbour = self.by_path(target)
            if neighbour and neighbour.status == "current":
                seen.add(target)
                out.append(neighbour)
        for path, other in self.records.items():
            if len(out) >= limit:
                break
            if path in seen or other.get("status") != "current":
                continue
            if any(link["target"] == hit.path for link in other.get("links", [])):
                seen.add(path)
                neighbour = self.by_path(path)
                if neighbour:
                    out.append(neighbour)
        return out[:limit]

    def path_back(self, hit: Hit) -> list[str]:
        """Main Index > Sub-Index > page, as titles."""
        trail = ["Main Index"]
        record = self.records.get(hit.path, {})
        for link in record.get("links", []):
            if link["rel"] != "up" or link["target"] in ("index.html", hit.path):
                continue
            parent = self.by_path(link["target"])
            if parent:
                label = parent.title or parent.path
                if label not in trail:
                    trail.append(label)
        label = hit.title or hit.path
        if label not in trail:
            trail.append(label)
        return trail

    def children(self, hit: Hit) -> list[Hit]:
        """Pages a Sub-Index lists from inside its own spoke."""
        record = self.records.get(hit.path, {})
        out = []
        for link in record.get("links", []):
            target = link["target"]
            if not target.endswith(".html") or target == hit.path:
                continue
            if hit.spoke and not target.startswith(hit.spoke + "/"):
                continue
            child = self.by_path(target)
            if child and child.status == "current" and not child.path.endswith("_index.html"):
                if child not in out:
                    out.append(child)
        return out

    def counts(self) -> dict[str, int]:
        current = sum(1 for r in self.result.records if r["status"] == "current")
        retired = sum(1 for r in self.result.records if r["status"] == "retired")
        return {
            "pages": len(self.result.records),
            "current": current,
            "retired": retired,
            "orphans": len(self.orphans),
            "spokes": len(self.spokes()),
        }

    def close(self) -> None:
        self.db.close()


def _haystack(hit: Hit) -> str:
    return " ".join([hit.text, hit.title, hit.scope, hit.when_to_use]).lower()


def _haystack_record(record: dict) -> str:
    return " ".join(
        str(record.get(f, "")) for f in ("text", "title", "scope", "when_to_use")
    ).lower()


def _fts_query(query: str, conjunctive: bool = False) -> str:
    """Turn free text into an FTS5 expression, quoting each term so that
    punctuation in a user's question cannot become operator syntax."""
    query = query.strip()
    if query.startswith('"') or " OR " in query or " AND " in query or "*" in query:
        return query  # caller is writing FTS5 on purpose
    terms = content_terms(query)
    if not terms:
        return '""'
    joiner = " AND " if conjunctive else " OR "
    return joiner.join(f'"{t}"' for t in terms)
