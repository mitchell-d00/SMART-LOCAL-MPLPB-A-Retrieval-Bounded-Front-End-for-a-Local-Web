"""
Crawler — the three ingestion paths of MPLPB-LOCAL-008 v4 §7.1.

    graph    reachable from index.html            -> ingested, status current
    retired  under _log/superseded/, audit-found  -> ingested, status retired
    orphan   unreachable and not superseded       -> NOT ingested, FM-L2

The distinction between the second and third path is the whole point. A page
under _log/superseded/ is deliberately unlinked; a page anywhere else that is
unlinked is an accident. Treating them the same either floods the index with
abandoned drafts or throws away the revision history (FM-L11).
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from .page import ROOT_PAGE, SUPERSEDED_DIR, Page, inside, is_internal, load_all


@dataclass
class CrawlResult:
    """Records that were ingested, plus the defects found on the way."""

    records: list[dict] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)
    root: Path = Path(".")

    @property
    def graph_count(self) -> int:
        return sum(1 for r in self.records if r["discovered_by"] == "graph")

    @property
    def audit_count(self) -> int:
        return sum(1 for r in self.records if r["discovered_by"] == "audit")

    def as_jsonl(self) -> str:
        return "\n".join(json.dumps(r, ensure_ascii=False) for r in self.records)


def to_record(page: Page, discovered_by: str) -> dict:
    """Normalized crawl record (§5.2). The HTML is authoritative; this is
    derived. `substrate` is always 'local' so a downstream citation can say
    the source is a local document rather than a published one (FM-L10)."""
    root = page.root.resolve()
    links = []
    for link in page.links:
        href = link["href"]
        if not is_internal(href):
            continue
        target = page.resolve(href)
        if not inside(target, root):
            continue
        links.append(
            {
                "rel": link["rel"] or "link",
                "target": target.relative_to(root).as_posix(),
            }
        )
    return {
        "document_id": page.document_id,
        "path": page.rel,
        "title": page.title,
        "category": page.category,
        "scope": page.scope,
        "when_to_use": page.when_to_use,
        "updated": page.updated,
        "owner": page.owner,
        "status": page.status or "current",
        "supersedes": page.supersedes,
        "protected": page.protected,
        "spoke": page.spoke,
        "substrate": "local",
        "discovered_by": discovered_by,
        "links": links,
        "text": page.text,
    }


def crawl(root: Path) -> CrawlResult:
    """Walk the declared graph, then audit the filesystem."""
    root = Path(root).resolve()
    entry = root / ROOT_PAGE
    if not entry.exists():
        raise FileNotFoundError(f"no {ROOT_PAGE} at {root}")

    pages = load_all(root)
    result = CrawlResult(root=root)

    # --- path 1: graph crawl from index.html (§6.1) ------------------------
    visited: set[Path] = set()
    queue = deque([entry.resolve()])
    while queue:
        current = queue.popleft()
        if current in visited or not inside(current, root):
            continue
        page = pages.get(current)
        if page is None:
            continue
        visited.add(current)
        result.records.append(to_record(page, "graph"))
        for href in page.internal_hrefs():
            target = page.resolve(href)
            if (
                target.suffix == ".html"
                and target in pages
                and inside(target, root)
                and target not in visited
            ):
                queue.append(target)

    # --- paths 2 and 3: filesystem audit (§6.2, §7.1) ----------------------
    for resolved, page in pages.items():
        if resolved in visited:
            continue
        if SUPERSEDED_DIR in page.path.relative_to(root).parts:
            record = to_record(page, "audit")
            record["status"] = "retired"  # location is authoritative here
            result.records.append(record)
        else:
            result.orphans.append(page.rel)

    result.records.sort(key=lambda r: r["path"])
    result.orphans.sort()
    return result
