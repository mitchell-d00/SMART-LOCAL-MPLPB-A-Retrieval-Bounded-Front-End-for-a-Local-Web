# Smart Local MPLPB

A front end for a local web. Standard library only — no `pip install`, no
server, no database, no network, no model.

An [MPLPB local web](#background) is a bounded knowledge corpus that is an
actual website: plain HTML files in a directory, connected by relative links,
starting at `index.html`. This package is the layer that talks to one. You ask
it a question; it routes the question to the spoke whose declared scope owns
it, answers from a retrieved page, cites that page with full provenance, and
names where to go next. When it finds nothing, it says so — and offers to be
taught.

```
$ python3 -m mplpb chat site

[strict tool] > why must links be relative?

Link Discipline — MPLPB Local
  Relative-link rules and the crawl boundary for the local web

  Every internal link in this corpus is relative to the page it appears on.
  Not root-relative, not file:, not absolute. The reason is portability...

  [LOCAL-SPEC-001 · spec/link_discipline.html · v2 · local · current]

  Related:
    Supersession — MPLPB Local  (spec/supersession.html)
  Back to: Main Index > Specification & Architecture > Link Discipline
```

## What makes it "smart"

Four things, each of which is a rule from the specification made into a code
path rather than a paragraph of advice.

**It routes by declared scope.** Retrieval may return results from several
spokes. Answering does not merge them. When no single scope owns a question,
the console reports which spokes were touched and asks you to narrow, instead
of blending two domains into one confident paragraph. `:why` shows the scores.

**It does not answer from outside the corpus.** No mode is configured to
improvise. If nothing matched, you get *Not in this corpus* and a list of what
is here. A front end that answers corpus questions from general knowledge is
the bypass failure the spec calls FM-L8, and it is the one failure that looks
exactly like success.

**It carries provenance everywhere.** Every result names its document ID,
path, version, status, and substrate. Substrate is always `local`, every time,
so a citation can never quietly imply the page was published somewhere.

**It learns by writing pages, not by appending lines.** See below.

## The notebook

This package descends from a BASIC chatbot that remembered by appending
`question:answer` to a text file:

```basic
120 OPEN "data.txt" FOR APPEND AS #1
130 PRINT #1, Q$; ":"; A$
150 PRINT "Got it! I'll remember that."
```

The instinct is right and it is kept. What changes is where the memory goes. An
appended line has no document ID, no timestamp, no scope, no way to be
superseded, and no path from the index — it is the flat-file version of an
orphan. So a taught answer becomes a page instead:

```
[strict tool] > what is a kiln wash?

Not in this corpus.
  Nothing under this root matched, so there is nothing to cite.
  If you know the answer, type it now and I will write it as a page.

[strict tool] > A refractory coating painted onto shelves to stop drips fusing.

  Written.
  LOCAL-NOTE-0001  notebook/what_is_a_kiln_wash.html  v1
  Listed in notebook/_index.html and logged in _log/revisions.html.
  It is recorded, not verified. Supersede it with :revise rather than editing.
```

The page has full metadata, is listed in its Sub-Index, is named in the
revision log, and passes all eight structural checks. Correcting it later
retires the old version to `_log/superseded/` rather than overwriting it, so
`:history LOCAL-NOTE-0001` can still say what it used to say.

## Install

```bash
git clone https://github.com/<you>/smart-local-mplpb.git
cd smart-local-mplpb
python3 -m mplpb chat site        # works immediately, no install step
```

Or install it so `mplpb` is on your path:

```bash
pip install -e .
mplpb chat site
```

Python 3.9 or newer. The only requirement outside the standard library is
`sqlite3` compiled with FTS5, and there is a fallback ranker for when it is
not.

## Commands

```bash
mplpb chat site                       # interactive console
mplpb ask site "why must links be relative?"
mplpb search site "relative link" --status any
mplpb id site LOCAL-SPEC-001 --history
mplpb crawl site -o records.jsonl
mplpb validate site                   # the eight checks; exit 1 on failure
mplpb serve site --port 8000          # browse and search in a browser
mplpb teach site "what is grog?" "Pre-fired clay, ground to a mesh."
mplpb new mycorpus --title "Kiln Notes" --spoke "glazes:Recipes and firing"
```

In the console:

| | |
|---|---|
| `:mode` / `:mode teaching` | show or switch mode |
| `:where` | where the last answer came from |
| `:why` | why it routed that way, with spoke scores |
| `:id` / `:history` | look one document up; follow its supersession chain |
| `:status any` | include retired pages in retrieval |
| `:teach` / `:revise` | write or supersede a taught page |
| `:validate` / `:stats` / `:reload` | check and re-crawl mid-session |

## Modes

Four, from the Mythic-Logic companion architecture, resolved in a fixed order:
an explicit override phrase, then a hard-reality trigger, then any other
implicit trigger, then whatever was already running.

| Mode | What changes |
|---|---|
| `strict_tool_mode` | default. Retrieval, citation, nothing else. |
| `teaching_mode` | scaffolded: where it lives, what it owns, what it says, what next. |
| `mythic_gm_mode` | a symbolic frame over the same retrieved pages. The frame never adds a claim. |
| `hard_reality_mode` | priority 100. No overlay, no improvising, and it will not record taught pages. |

`hard_reality_mode` wins whenever it triggers, which is why it is resolved
before anything else rather than after a conflict has already arisen. It fires
on legal, medical-adjacent, contractual, and safety-adjacent language. It also
refuses to write a taught page: material of that kind should not enter a corpus
because somebody typed it into a chat session.

Every key in `mplpb/data/engine.json` changes observable behaviour. Toggles
from the source paper that this front end does not implement are absent rather
than present and inert.

## Layers

```
page.py                 one parser. Two parsers means two definitions of "link"
crawl.py                three ingestion paths: graph, retired, orphan
validate.py             the eight structural checks, as findings not printout
index.py                FTS5 retrieval, status filtering, supersession chains
router.py               boot-block routing plus scope precedence
cite.py                 provenance that travels with the text
modes.py                the mode controller
notebook.py             taught answers become pages
console.py  server.py   the two front ends
scaffold.py             a new corpus that validates before it contains anything
```

The router decides *where an answer comes from*; it does not write prose. A
language model, a template, or a person can sit on top of it, and the
provenance rules hold in all three cases.

## The eight checks

`mplpb validate` exits 1 on any failure, so it drops into CI as-is
(`.github/workflows/ci.yml` is included).

1. **11.1** every local link target exists
2. **11.2** every current page reachable from `index.html`
3. **11.3** required metadata and `rel="index"` / `rel="up"` present
4. **11.4** no two current pages share a document ID
5. **11.5** supersession, status, and location agree
6. **11.6** no link resolves outside the corpus root
7. **11.7** every current page listed in its Sub-Index
8. **11.8** `updated` values parse and remain orderable

## Tests

```bash
python3 -m unittest discover -s tests -t .
```

52 tests, standard library `unittest`, no fixtures beyond temporary copies of
the example corpus.

## What this does not claim

The console being able to route a question does not establish that the routed
answer is correct, that structure beats a flat pile of files, or that a taught
page is true — a taught page is a record of what someone said, and it says so
on its own face.

Two tests would settle more than any amount of argument, and neither has been
run:

- **Ablation.** Same corpus, same questions, structure removed: does routing by
  declared scope beat flat full-text search? If not, the structure is
  decoration and the storage was doing the work.
- **Bypass rate.** How often does a model given this corpus answer from its own
  weights instead of a retrieved page? The console cannot bypass, but a model
  sitting on top of it can, and that is the interesting number.

## Background

- `docs/lineage.md` — where each idea came from, and what changed on the way
- *Smart Local MPLPB* — the paper describing this implementation
- MPLPB-LOCAL-008 v4 — the local-web specification
- *Continuity Without Memory* (2026) — the collected specifications

## License

Code: MIT. Documentation and specification text: CC BY 4.0. See `LICENSE`.

Mitchell D. McPhetridge
