"""
Routing, from the boot block and from "Separate, Allowed to Chat, and
Overridden by Scope".

Boot block routing:

    broad     -> the relevant Sub-Index
    specific  -> the best operational page
    uncertain -> the Main Index, and ask the user to narrow
    always    -> name one to three related pages and the path back

Precedence: retrieval may return results from several spokes and must
preserve each result's source scope. Answering does not merge them. When no
single scope cleanly owns the query, the router reports which spokes were
touched and asks the user to narrow, rather than silently blending two
domains into one answer -- the slow version of the false-merger failure.

The router decides *where an answer comes from*. It does not write prose.
That separation is deliberate: a language model, a template, or a person can
sit on top of it, and the provenance rules hold in all three cases.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .index import STOPWORDS, Hit, Index
from .modes import Mode

_WORD = re.compile(r"[a-z0-9]+")
_STOP = STOPWORDS

#: A spoke owns the query when it leads the runner-up by this factor.
OWNERSHIP_MARGIN = 1.5


def terms(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 2]


@dataclass
class Routing:
    """Where an answer should come from, and what it must not claim."""

    question: str
    kind: str  # 'specific' | 'broad' | 'ambiguous' | 'uncertain'
    hits: list[Hit] = field(default_factory=list)
    primary: Hit | None = None
    spokes: dict[str, float] = field(default_factory=dict)
    owner: str | None = None
    related: list[Hit] = field(default_factory=list)
    trail: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def answerable(self) -> bool:
        return self.kind in ("specific", "broad") and self.primary is not None

    @property
    def needs_narrowing(self) -> bool:
        return self.kind in ("ambiguous", "uncertain")

    @property
    def touched(self) -> list[str]:
        return [s for s, _ in sorted(self.spokes.items(), key=lambda kv: -kv[1])]


class Router:
    def __init__(self, index: Index):
        self.index = index
        self.scopes = index.spokes()

    def route(self, question: str, mode: Mode, limit: int = 6) -> Routing:
        hits = self.index.search(
            question, status=mode.retrieval_status, limit=limit
        )
        if not hits:
            return Routing(
                question,
                "uncertain",
                note="Nothing in the corpus matched. Start at the Main Index, "
                "or narrow the question to a spoke.",
            )

        scores = self._score(question, hits)
        owner = self._owner(scores)

        if not scores:
            # Hits, but all from infrastructure pages. Route to the best one
            # and let the trail explain where it sits.
            primary = self._primary(question, hits)
            return Routing(
                question,
                "broad" if primary.path.endswith("_index.html") else "specific",
                hits=hits,
                primary=primary,
                related=self.index.related(primary, limit=mode.max_related),
                trail=self.index.path_back(primary),
            )

        if owner is None and len(scores) > 1:
            return Routing(
                question,
                "ambiguous",
                hits=hits,
                spokes=scores,
                note=(
                    "Results span "
                    + ", ".join(self.touched_names(scores))
                    + " and no single declared scope owns the question. "
                    "Answering would merge two scopes; narrow it to one."
                ),
            )

        in_scope = [h for h in hits if h.spoke == owner] or hits
        primary = self._primary(question, in_scope)
        kind = "broad" if primary.path.endswith("_index.html") else "specific"
        if kind == "specific" and self._looks_broad(question, primary, owner):
            sub_index = self.index.by_path(f"{owner}/_index.html") if owner else None
            if sub_index:
                primary, kind = sub_index, "broad"

        return Routing(
            question,
            kind,
            hits=in_scope,
            primary=primary,
            spokes=scores,
            owner=owner,
            related=self.index.related(primary, limit=mode.max_related),
            trail=self.index.path_back(primary),
        )

    # -- scoring -----------------------------------------------------------
    def _score(self, question: str, hits: list[Hit]) -> dict[str, float]:
        """Rank-decayed hit weight per spoke, plus a bonus when the spoke's
        own declared scope names the query's terms. Declared scope is given
        weight because that is what precedence is decided by -- not size,
        age, confidence, or link count."""
        wanted = set(terms(question))
        scores: dict[str, float] = {}
        for position, hit in enumerate(hits):
            # Only a directory that declares a scope in its Sub-Index can own
            # a question. The Main Index and _log hold pages but claim no
            # domain, so they never contend -- otherwise the revision log
            # would win arguments about physics.
            if hit.spoke not in self.scopes:
                continue
            weight = 1.0 / (1 + position)
            scores[hit.spoke] = scores.get(hit.spoke, 0.0) + weight
        for spoke, scope in self.scopes.items():
            declared = set(terms(scope))
            overlap = wanted & declared
            if overlap:
                scores[spoke] = scores.get(spoke, 0.0) + 0.5 * len(overlap)
        return scores

    @staticmethod
    def _owner(scores: dict[str, float]) -> str | None:
        if not scores:
            return None
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        if len(ranked) == 1:
            return ranked[0][0]
        top, second = ranked[0], ranked[1]
        if second[1] <= 0 or top[1] >= second[1] * OWNERSHIP_MARGIN:
            return top[0]
        return None

    @staticmethod
    def _primary(question: str, hits: list[Hit]) -> Hit:
        """Prefer the page whose declared when-to-use triggers match, then
        the page whose scope matches, then search rank."""
        wanted = set(terms(question))

        def key(item: tuple[int, Hit]) -> tuple:
            position, hit = item
            triggers = len(wanted & set(terms(hit.when_to_use)))
            scope = len(wanted & set(terms(hit.scope)))
            title = len(wanted & set(terms(hit.title)))
            return (-triggers, -scope, -title, position)

        return sorted(enumerate(hits), key=key)[0][1]

    def _looks_broad(self, question: str, primary: Hit, owner: str | None) -> bool:
        """Few content words and no trigger match means the user is asking
        about a domain, not a document."""
        wanted = set(terms(question))
        if len(wanted) > 3 or owner is None:
            return False
        named = set(terms(primary.when_to_use)) | set(terms(primary.title)) | set(
            terms(primary.scope)
        )
        return not (wanted & named)

    def touched_names(self, scores: dict[str, float]) -> list[str]:
        out = []
        for spoke, _ in sorted(scores.items(), key=lambda kv: -kv[1]):
            scope = self.scopes.get(spoke)
            out.append(f"{spoke or 'root'} ({scope})" if scope else (spoke or "root"))
        return out
