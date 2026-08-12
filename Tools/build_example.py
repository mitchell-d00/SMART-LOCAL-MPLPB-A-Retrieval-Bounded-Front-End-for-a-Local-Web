#!/usr/bin/env python3
"""Regenerate the example corpus under site/. Run from the repo root."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mplpb.notebook import ENTRY_MARKER, render_page  # noqa: E402
from mplpb.validate import validate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "site"
OWNER = "Mitchell D. McPhetridge"
T = "2026-08-05T18:40Z"


def write(rel: str, text: str) -> None:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print("wrote", rel)


def page(**kw) -> str:
    kw.setdefault("owner", OWNER)
    kw.setdefault("status", "current")
    return render_page(**kw)


# --- spec spoke -----------------------------------------------------------
write(
    "spec/_index.html",
    page(
        title="Specification & Architecture — Sub-Index",
        document_id="LOCAL-SPEC-INDEX",
        category="Navigator / Sub-Index",
        scope="How this corpus is built, linked, crawled, and validated",
        when_to_use=(
            "Broad question about structure, links, crawling, validation, or "
            "supersession; unsure which spec page owns it"
        ),
        updated=f"{T} v2",
        depth=1,
        up="../index.html",
        heading="Specification &amp; Architecture",
        eyebrow="MPLPB local web · sub-index",
        body=f"""<p><strong>Scope.</strong> This spoke owns the rules the corpus is
built from: file layout, relative links, the crawl boundary, page metadata,
supersession, and the eight structural checks. It does not own the content of
any other spoke, and it does not get a vote on their questions.</p>

<h2>Pages</h2>
<ul class="map">
  <li><a href="./link_discipline.html">Link Discipline</a>
    <span class="scope">scope: relative links, the crawl boundary, and what makes a corpus portable</span></li>
  <li><a href="./supersession.html">Supersession</a>
    <span class="scope">scope: retiring a page without losing what it said</span></li>
{ENTRY_MARKER}
</ul>""",
        self_link=False,
    ),
)

write(
    "spec/link_discipline.html",
    page(
        title="Link Discipline — MPLPB Local",
        document_id="LOCAL-SPEC-001",
        category="Specification / Architecture",
        scope="Relative-link rules and the crawl boundary for the local web",
        when_to_use=(
            "Adding a page; moving a page; a link broke; a crawl escaped the "
            "root; deciding between a relative and an absolute link"
        ),
        updated=f"{T} v2",
        supersedes="LOCAL-SPEC-OLD-001",
        depth=1,
        heading="Link Discipline",
        eyebrow="MPLPB local web · specification",
        body="""<p>Every internal link in this corpus is relative to the page it
appears on. Not root-relative, not <code>file:</code>, not absolute. The reason
is portability: the corpus has to work when it is copied to another machine,
mounted at a different path, zipped, emailed, or opened straight off a USB
stick with no server running at all. A root-relative link assumes a web root
that a directory on disk does not have.</p>

<h2>The crawl boundary</h2>
<p>The directory containing <code>index.html</code> is the boundary. A link
whose canonical path resolves outside that directory must be rejected rather
than followed. Canonical means resolved: <code>../../../etc/passwd</code> is
caught after resolution, not before, which is why the check compares resolved
paths instead of inspecting the href as a string.</p>

<h2>Upward links</h2>
<p>Every page except the Main Index carries two typed links in its head:
<code>rel="index"</code> pointing at the Main Index, and <code>rel="up"</code>
pointing at its Sub-Index. These are what let a reader who arrives at a page
from a search result find their way back to the map, and what let the crawler
reconstruct the hierarchy without guessing from directory names.</p>

<h2>Failure modes</h2>
<ul class="map">
  <li>FM-L1 — a page points to a file that no longer exists</li>
  <li>FM-L4 — a relative path resolves outside the intended root</li>
  <li>FM-L5 — a page needs JavaScript or a running server to be read</li>
</ul>""",
    ),
)

write(
    "spec/supersession.html",
    page(
        title="Supersession — MPLPB Local",
        document_id="LOCAL-SPEC-002",
        category="Specification / Architecture",
        scope="Retiring a page without losing what it said",
        when_to_use=(
            "Replacing a page; retiring a document; asking what a document used "
            "to say; wondering why a file sits in _log/superseded"
        ),
        updated=f"{T} v1",
        depth=1,
        heading="Supersession",
        eyebrow="MPLPB local web · specification",
        body="""<p>A page is never deleted and never edited into a different
claim. It is superseded. Five things happen together, and if any one of them is
skipped the corpus disagrees with itself:</p>

<ol>
  <li>the old file moves to <code>_log/superseded/</code></li>
  <li>its <code>status</code> flips to <code>retired</code></li>
  <li>it is removed from its Sub-Index</li>
  <li>the replacement names it in <code>supersedes</code></li>
  <li>a line is appended to the revision log</li>
</ol>

<h2>Why retired pages are still indexed</h2>
<p>Retired pages are deliberately unlinked, so a crawl that only follows links
from the Main Index can never reach them. If the filesystem audit is treated as
maintenance-only, they are never indexed at all — and then <em>absent</em> and
<em>excluded by default</em> become indistinguishable. The corpus still
validates, still crawls, still answers current questions, and can no longer say
what a document used to say or when it changed. That is FM-L11, and it is
invisible to every other check.</p>

<p>So retrieval defaults to <code>status = current</code>, and retired pages
stay reachable by explicit status or by document ID, with the status surfaced
on every returned record.</p>""",
    ),
)

write(
    "_log/superseded/link_discipline_v1.html",
    page(
        title="Link Discipline — MPLPB Local (v1)",
        document_id="LOCAL-SPEC-OLD-001",
        category="Specification / Architecture",
        scope="Relative-link rules for the local web",
        when_to_use="Provenance lookup only; superseded by LOCAL-SPEC-001",
        updated="2026-07-02T09:15Z v1",
        status="retired",
        depth=2,
        up="../../spec/_index.html",
        heading="Link Discipline (v1, retired)",
        eyebrow="MPLPB local web · retired",
        body="""<div class="record"><dl><dt>Status</dt><dd>RETIRED &mdash;
superseded by LOCAL-SPEC-001</dd></dl></div>

<p>Internal links should be relative where practical. Absolute paths are
discouraged but acceptable when a corpus is served from a fixed web root.</p>

<p>This is the claim that was later withdrawn. "Discouraged but acceptable"
turned out to mean the corpus stopped being portable the first time it was
copied somewhere else, and the exception quietly became the norm. The current
page states the rule without the escape hatch.</p>""",
    ),
)

# --- physics spoke --------------------------------------------------------
write(
    "physics/_index.html",
    page(
        title="Physics — Sub-Index",
        document_id="LOCAL-PHYS-INDEX",
        category="Navigator / Sub-Index",
        scope="Worked physics notes; heat transfer and thermal behaviour of materials",
        when_to_use=(
            "Broad physics question; unsure which physics page owns it; "
            "example spoke for demonstrating scope precedence"
        ),
        updated=f"{T} v1",
        depth=1,
        up="../index.html",
        heading="Physics",
        eyebrow="MPLPB local web · sub-index",
        body=f"""<p><strong>Scope.</strong> Worked notes on heat transfer and the
thermal behaviour of materials. This spoke is an example: it exists so the
routing rules have two domains to arbitrate between. Replace it with a real
domain or delete it.</p>

<h2>Pages</h2>
<ul class="map">
  <li><a href="./heat_transfer.html">Heat Transfer</a>
    <span class="scope">scope: conduction, convection, and radiation as three transport mechanisms</span></li>
{ENTRY_MARKER}
</ul>""",
        self_link=False,
    ),
)

write(
    "physics/heat_transfer.html",
    page(
        title="Heat Transfer — MPLPB Local",
        document_id="LOCAL-PHYS-001",
        category="Physics / Thermal",
        scope="Conduction, convection, and radiation as three transport mechanisms",
        when_to_use=(
            "Heat moving through a material; why metal feels colder than wood; "
            "choosing between conduction, convection, and radiation"
        ),
        updated=f"{T} v1",
        depth=1,
        heading="Heat Transfer",
        eyebrow="MPLPB local web · physics",
        body="""<p>Heat moves three ways, and most real situations are two of them
at once.</p>

<h2>Conduction</h2>
<p>Energy passes between adjacent particles without the material itself moving.
Metals conduct well because free electrons carry energy through the lattice;
wood and air conduct badly. This is why a metal railing feels colder than a
wooden one at the same temperature — it is pulling heat out of your hand
faster, not sitting at a lower temperature.</p>

<h2>Convection</h2>
<p>The material itself moves and carries its energy with it. Warm fluid rises
because it is less dense, cool fluid sinks to replace it, and the loop keeps
running as long as the temperature difference does.</p>

<h2>Radiation</h2>
<p>Energy leaves as electromagnetic waves and needs no medium at all. Every
body above absolute zero radiates; the rate climbs with the fourth power of
absolute temperature, which is why radiation dominates at high temperatures and
is easy to ignore at room temperature.</p>""",
    ),
)

# --- log ------------------------------------------------------------------
write(
    "_log/revisions.html",
    page(
        title="Revision Log — MPLPB Local",
        document_id="LOCAL-LOG-000",
        category="Log / Revisions",
        scope="Append-only record of changes and supersessions in this corpus",
        when_to_use="Asking what changed; asking when a document was superseded",
        updated=f"{T} v3",
        depth=1,
        up="../index.html",
        heading="Revision Log",
        eyebrow="MPLPB local web · append-only",
        body=f"""<p>Append only. Entries are added, never edited or removed.</p>

<h2>Entries</h2>
<ul class="map">
  <li><code>2026-07-02</code> LOCAL-SPEC-OLD-001 created at spec/link_discipline.html</li>
  <li><code>2026-08-05</code> LOCAL-SPEC-001 supersedes LOCAL-SPEC-OLD-001; old version retired to _log/superseded/link_discipline_v1.html. Reason: "discouraged but acceptable" was not a rule.</li>
  <li><code>2026-08-05</code> LOCAL-SPEC-002 created at spec/supersession.html</li>
  <li><code>2026-08-05</code> LOCAL-PHYS-001 created at physics/heat_transfer.html</li>
{ENTRY_MARKER}
</ul>""",
        self_link=False,
    ),
)

print()
print(validate(ROOT).summary())
