# Lineage

Three documents fold into this package. This note records what was carried
over unchanged, what was changed and why, and what was deliberately left out.
It exists so that a reader of any of the three source documents can find the
line where their idea ended up — and so that the places where the
implementation departs from the paper are stated by the author rather than
discovered by a reader.

---

## 1. B.A.S.I.C. AI (2025)

**Carried over unchanged: the loop.**

```
 60 INPUT Q$
 80 OPEN "data.txt" FOR INPUT AS #2      ' check what I already know
190 IF ResponseFound = 0 THEN            ' otherwise, ask to be taught
```

Ask, recall first, and when recall fails, ask to be taught and remember the
answer. The v2 "smarter memory" revision — check before asking — is the
behaviour `console.py` implements. The BASIC program's own conclusion holds:
*memory and association are powerful; even the simplest system can appear
smart if it remembers what you told it last time.*

**Changed: where the memory goes.**

`data.txt` is a flat append log. In a local web it would be invisible to the
crawler, carry no document ID, no scope, no timestamp, no status, and no way
to be superseded. It is the flat-file form of an orphan page (FM-L2).

So the taught answer is written as an HTML page instead: full metadata, listed
in its Sub-Index, logged in `_log/revisions.html`, reachable from the Main
Index, and passing all eight structural checks. See `mplpb/notebook.py`.

**Changed: substring matching.**

`IF INSTR(DATA$, Q$)` matches any line containing the question as a substring.
Retrieval here is a SQLite FTS5 index with an AND-first query, a fallback to
OR, and a distinctive-term guard that rejects a match earned by one ordinary
shared word. See `mplpb/index.py`.

---

## 2. MPLPB as a Local Web (MPLPB-LOCAL-008 v4)

**Carried over: essentially all of it.**

- §5 page metadata and §5.1 field formats — `mplpb/page.py`
- §5.2 crawl record, including `substrate` and `discovered_by` — `mplpb/crawl.py`
- §6.1 minimal crawl algorithm and §6.2 crawl modes — `mplpb/crawl.py`
- §7.1 three ingestion paths — `mplpb/crawl.py`, and the reason the filesystem
  audit is not maintenance-only
- §11.1–11.8, the eight checks — `mplpb/validate.py`
- §12 failure-mode index — findings name their FM-L code

**Changed: one parser, not two.**

The reference `crawl.py` and `validate.py` each carried their own
`HTMLParser` subclass. Two parsers means two definitions of what counts as a
link, which is the metadata-trust failure the spec itself names as FM-L9.
There is now one parser in `mplpb/page.py` and everything imports it.

**Changed: the record card is not indexed as page text.**

Every page restates its metadata in a visible `<div class="record">`. Indexing
that card makes every page a strong match for its own field names — search for
"scope" and the whole corpus answers. The parser skips it as display, not
content. The `<meta>` tags remain authoritative.

**Added: `mplpb:protected`.**

An optional owner-declared sensitivity flag. It filters retrieval. It is not
access control, and is documented as not being access control.

---

## 3. A Modular Mode-Switching Architecture for a Mythic-Logic Companion (MPLPB-MODE-008)

**Carried over: the four modes and the priority override.**

`strict_tool_mode`, `teaching_mode`, `mythic_gm_mode`, `hard_reality_mode`,
with hard reality at priority 100 and resolved before any other implicit
trigger, so that "walk me through this contract clause" lands in hard reality
rather than teaching. Explicit override phrases and implicit topic triggers
both come straight from §6 of the paper.

**Changed: the default mode.**

The paper defaults to `mythic_gm_mode`. The MPLPB boot block defaults to
`strict_tool_mode`. A corpus front end follows the boot block. The default is
configurable in `mplpb/data/engine.json` and by `--mode`.

**Changed: only toggles with observable effects are in the config.**

The paper's engine JSON carries module toggles that this front end has no
implementation for. A config key that changes nothing is a claim the software
does not honour, so those keys are absent rather than present and inert. Every
key in `engine.json` changes what the console does. `docs/` records the full
original engine for anyone wiring it into a system that has those modules.

**Added: `teach_allowed`, false in hard reality.**

Legal, medical-adjacent, contractual, and safety topics should not enter a
corpus as something a session typed in and a later session will read back as
a document. The mode that exists to be careful is the mode that declines to
write.

**Added: `trigger_is_instruction`.**

Teaching triggers ("walk me through", "explain") are instructions about *how*
to answer and are stripped from the retrieval query. Hard-reality triggers
("contract", "dosage") are the subject of the question and are kept. Without
the distinction, "walk me through supersession" retrieves every page
containing the word "walk".

**Not implemented: `identity_gatekeeping`.**

The paper's own caveat is that this is a conversational deterrent, not a real
access-control boundary — a system cannot cryptographically verify who it is
talking to from style and recall. Implementing it in code would dress that
caveat up as a mechanism. The honest subset is a metadata flag and a retrieval
filter, which is what `mplpb:protected` is.

**Not implemented: `web_mode`, `fractal_flux_game_engine`, `surprise_generator`.**

Out of scope for a front end whose defining property is that it answers only
from a bounded local corpus with no network access. `mythic_gm_mode` retains
the symbolic framing layer — applied to the presentation of a retrieved page,
never to its content, and never speaking as though the console were an entity.

---

## 4. Separate, Allowed to Chat, and Overridden by Scope (MPLPB-SEP-007)

**Carried over: domain precedence, as executable code.**

`mplpb/router.py` scores each spoke by rank-decayed hit weight plus a bonus
when the spoke's declared scope names the query's terms. A spoke owns the
question when it leads the runner-up by 1.5×. Below that margin the router
returns `ambiguous`: it names the spokes it touched and asks the user to
narrow, rather than merging two scopes into one answer.

Only a directory that declares a scope in its Sub-Index can contend. The Main
Index and `_log/` hold pages but claim no domain, so the revision log never
wins an argument about physics.

The 1.5× margin is a chosen number, not a derived one. It is the most
arbitrary constant in the package and the first thing to tune against a real
corpus.
