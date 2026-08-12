"""
Validator — the eight structural checks of MPLPB-LOCAL-008 v4 §11.

  11.1  link validity            every local target exists
  11.2  root reachability        every current page reachable from index.html
  11.3  required metadata        every page declares the required fields
  11.4  unique document identity no two current pages share a document ID
  11.5  supersession consistency supersedes / status / location agree
  11.6  boundary safety          no link resolves outside the root
  11.7  index consistency        every current page listed in its parent index
  11.8  timestamp ordering       updated values parse and are orderable

The checks return findings instead of printing them, so the console can run
them mid-session and the CLI can format them at the edge. Each finding names
the check that produced it and, where the spec assigns one, the failure mode.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path

from .page import (
    LOG_DIR,
    REQUIRED_META,
    ROOT_PAGE,
    SUPERSEDED_DIR,
    UPDATED_RE,
    VALID_STATUS,
    Page,
    inside,
    is_absolute,
    is_internal,
    load_all,
)

#: Which failure mode each check surfaces, where the spec assigns one.
FAILURE_MODES = {
    "11.1": "FM-L1",
    "11.2": "FM-L2",
    "11.3": "FM-L3",
    "11.6": "FM-L4",
    "11.5": "FM-L6",
    "11.8": "FM-L9",
}


@dataclass(frozen=True)
class Finding:
    check: str
    path: str
    message: str

    @property
    def failure_mode(self) -> str:
        return FAILURE_MODES.get(self.check, "")

    def __str__(self) -> str:
        fm = f" [{self.failure_mode}]" if self.failure_mode else ""
        where = f"{self.path}: " if self.path else ""
        return f"{self.check}{fm}  {where}{self.message}"


@dataclass
class Report:
    findings: list[Finding]
    pages: int
    current: int
    retired: int
    root: Path

    @property
    def ok(self) -> bool:
        return not self.findings

    def by_check(self) -> dict[str, list[Finding]]:
        out: dict[str, list[Finding]] = {}
        for finding in sorted(self.findings, key=lambda f: (f.check, f.path)):
            out.setdefault(finding.check, []).append(finding)
        return out

    def summary(self) -> str:
        head = (
            f"validated {self.pages} page(s) under {self.root}  "
            f"({self.current} current, {self.retired} retired)"
        )
        if self.ok:
            return head + "\n  OK    11.1-11.8 all clean"
        lines = [head] + [f"  FAIL  {f}" for f in sorted(self.findings, key=str)]
        lines.append(f"\n{len(self.findings)} problem(s)")
        return "\n".join(lines)


def validate(root: Path) -> Report:
    root = Path(root).resolve()
    entry = (root / ROOT_PAGE).resolve()
    pages = load_all(root)
    findings: list[Finding] = []

    def fail(check: str, page: Page | None, message: str) -> None:
        findings.append(Finding(check, page.rel if page else "", message))

    if entry not in pages:
        return Report([Finding("11.2", "", f"no {ROOT_PAGE} at {root}")], 0, 0, 0, root)

    # -- 11.1 link validity, 11.6 boundary safety --------------------------
    for page in pages.values():
        for href in page.internal_hrefs():
            if is_absolute(href):
                fail("11.1", page, f"non-relative link -> {href}")
                continue
            target = page.resolve(href)
            if not inside(target, root):
                fail("11.6", page, f"link escapes root -> {href}")
            elif not target.exists():
                fail("11.1", page, f"broken link -> {href}")

    # -- 11.3 required metadata and upward links ---------------------------
    for page in pages.values():
        for field in REQUIRED_META:
            if not page.meta.get(field):
                fail("11.3", page, f"missing {field}")
        if page.status and page.status not in VALID_STATUS:
            fail("11.3", page, f"status must be current|retired, got '{page.status}'")
        if not page.is_root:
            for required in ("index", "up"):
                if required not in page.rels:
                    fail("11.3", page, f'missing rel="{required}"')

    # -- 11.8 timestamp ordering -------------------------------------------
    for page in pages.values():
        if page.updated and not UPDATED_RE.match(page.updated):
            fail(
                "11.8",
                page,
                f"updated '{page.updated}' is not '<ISO8601 with timezone> v<n>'",
            )

    # -- 11.4 unique document identity among current pages -----------------
    holders: dict[str, list[Page]] = {}
    for page in pages.values():
        if page.status == "current" and page.document_id:
            holders.setdefault(page.document_id, []).append(page)
    for doc_id, group in sorted(holders.items()):
        if len(group) > 1:
            joined = ", ".join(p.rel for p in sorted(group, key=lambda p: p.rel))
            findings.append(
                Finding("11.4", "", f"duplicate current document ID {doc_id}: {joined}")
            )

    # -- 11.2 root reachability (current pages only) -----------------------
    seen = {entry}
    queue = deque([entry])
    while queue:
        page = pages[queue.popleft()]
        for href in page.internal_hrefs():
            target = page.resolve(href)
            if target.suffix == ".html" and target in pages and target not in seen:
                seen.add(target)
                queue.append(target)
    for resolved, page in pages.items():
        if page.in_superseded:
            continue  # 11.5 owns these
        if resolved not in seen:
            fail("11.2", page, "orphan, unreachable from index.html")

    # -- 11.5 supersession consistency -------------------------------------
    retired_ids = {p.document_id for p in pages.values() if p.status == "retired"}
    for page in pages.values():
        if page.status == "retired" and not page.in_superseded:
            fail("11.5", page, f"status retired but not under {LOG_DIR}/{SUPERSEDED_DIR}/")
        if page.in_superseded and page.status != "retired":
            fail(
                "11.5",
                page,
                f"under {LOG_DIR}/{SUPERSEDED_DIR}/ but status is '{page.status or 'unset'}'",
            )
        for dead_id in page.supersedes:
            if dead_id not in retired_ids:
                fail("11.5", page, f"supersedes {dead_id}, which is not a retired page")
        if page.is_index:
            for href in page.internal_hrefs():
                target = pages.get(page.resolve(href))
                if target and target.status == "retired":
                    fail("11.5", page, f"active index links retired page {href}")

    # -- 11.7 index consistency --------------------------------------------
    # A page inside a spoke must be listed in that spoke's Sub-Index. A page
    # outside any spoke must be linked from the Main Index instead -- else it
    # has no declared parent at all.
    for resolved, page in pages.items():
        if page.is_index or page.in_superseded or page.status == "retired":
            continue
        sub_index = (page.path.parent / "_index.html").resolve()
        holder = pages.get(sub_index) or pages[entry]
        listed = any(
            holder.resolve(href) == resolved for href in holder.internal_hrefs()
        )
        if not listed:
            fail("11.7", page, f"not listed in {holder.rel}")

    current = sum(1 for p in pages.values() if p.status == "current")
    retired = sum(1 for p in pages.values() if p.status == "retired")
    return Report(findings, len(pages), current, retired, root)
