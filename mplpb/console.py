"""
The console: a chat loop over a local web.

    10 PRINT "Welcome to the Simple AI in BASIC!"
    60 INPUT Q$
    80 OPEN "data.txt" FOR INPUT AS #2      ' check what I already know
   190 IF ResponseFound = 0 THEN            ' otherwise, ask to be taught

That is the whole shape, and it is kept. What changes is the substrate. The
BASIC version searched a flat file and answered with a matched line. This one
searches a crawled corpus, routes the question to the spoke whose declared
scope owns it, answers from the retrieved page, cites it with provenance, and
names where to go next. When it finds nothing it says so instead of
improvising, because a front end that answers corpus questions from
elsewhere is the bypass failure the spec calls FM-L8.

`ask()` returns a string and touches no I/O, so the whole loop is testable.
`run()` is the thin part on top.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import cite
from .index import Hit, Index
from .modes import HARD_REALITY, ModeController
from .notebook import Notebook
from .router import Routing, Router
from .validate import validate

BANNER = r"""
+-------------------------------------------------------------+
|  MPLPB CONSOLE  --  a local web you can talk to              |
|  ask a question, ':help' for commands, ':quit' to leave      |
+-------------------------------------------------------------+
"""

HELP = """commands
  :help              this list
  :mode              show the running mode
  :mode <name>       switch mode explicitly
  :modes             all four mode profiles
  :spokes            declared scopes, one per spoke
  :where             where the last answer came from
  :why               why the last answer was routed that way
  :id <DOC-ID>       look up one document, any status
  :history <DOC-ID>  a document and everything it superseded
  :teach             record an answer as a new page
  :revise <DOC-ID>   supersede a taught page, keeping the old one
  :status current|any   include retired pages in retrieval
  :validate          run the eight structural checks now
  :stats             what is in the corpus
  :reload            re-crawl after editing files on disk
  :quit              leave
"""


@dataclass
class Turn:
    question: str
    routing: Routing | None
    mode: str
    answer: str


@dataclass
class Console:
    root: Path
    owner: str = ""
    mode: str | None = None
    style: str = "bracket"
    user: str = ""
    color: bool | None = None
    transcript: list[Turn] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.root = Path(self.root).resolve()
        self.index = Index.open(self.root)
        self.router = Router(self.index)
        self.controller = ModeController(default=self.mode)
        self.notebook = Notebook(self.root, owner=self.owner)
        self.status_override: str | None = None
        self.pending: str = ""  # question waiting to be taught an answer
        if self.color is None:
            self.color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")

    # -- public API --------------------------------------------------------
    def ask(self, line: str) -> str:
        """One turn. Returns what the console would print."""
        line = line.strip()
        if not line:
            return ""
        if line.startswith(":"):
            return self._command(line[1:].strip())
        if self.pending:
            return self._accept_taught_answer(line)

        switch = self.controller.resolve(line)
        mode = switch.mode
        if self.status_override:
            mode = type(mode)(**{**mode.__dict__, "retrieval_status": self.status_override})

        # Words that selected the mode are instructions about *how* to answer,
        # not about *what*. Leaving "walk me through" in the retrieval query
        # drags in every page containing "walk".
        routing = self.router.route(self._strip_trigger(line, switch), mode)
        out: list[str] = []
        if switch.changed:
            out.append(self._dim(f"[{switch.explain()}]"))
        if mode.narrative_frame:
            out.append(self._frame(routing))
        if mode.name == HARD_REALITY and switch.reason == "implicit":
            out.append(self._dim(
                f"  [hard reality: '{switch.trigger}' is legal, medical, "
                "contractual, or safety-adjacent. No overlay, no improvising, "
                "and this corpus is not professional advice.]"
            ))
        out.append(self._render(routing, mode))

        answer = "\n".join(part for part in out if part)
        self.transcript.append(Turn(line, routing, mode.name, answer))
        return answer

    @staticmethod
    def _strip_trigger(line: str, switch) -> str:
        if not switch.trigger or switch.reason == "sticky":
            return line
        if switch.reason == "implicit" and not switch.mode.trigger_is_instruction:
            return line  # "contract" selected the mode *and* is the subject
        lowered, trigger = line.lower(), switch.trigger.lower()
        at = lowered.find(trigger)
        if at == -1:
            return line
        stripped = (line[:at] + line[at + len(trigger):]).strip(" ,.:;-")
        return stripped or line

    def run(self, stream=None) -> int:
        """The loop. Reads lines until EOF or :quit."""
        stream = stream or sys.stdin
        print(BANNER)
        print(self._boot_summary())
        if not self.user and stream is sys.stdin and sys.stdin.isatty():
            try:
                self.user = input("What is your name? ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if self.user:
                print(f"Hello, {self.user}. Ask me something, or ':quit' to leave.\n")
        while True:
            try:
                line = input(self._prompt())
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if line.strip() in (":quit", ":q", "bye", "exit"):
                break
            out = self.ask(line)
            if out == "__QUIT__":
                break
            if out:
                print(out + "\n")
        farewell = f"Goodbye, {self.user}." if self.user else "Goodbye."
        print(farewell)
        return 0

    # -- rendering ---------------------------------------------------------
    def _render(self, routing: Routing, mode) -> str:
        if routing.kind == "ambiguous":
            return self._ambiguous(routing)
        if routing.kind == "uncertain" or not routing.primary:
            return self._nothing_found(routing, mode)
        if routing.kind == "broad":
            return self._broad(routing, mode)
        return self._specific(routing, mode)

    def _specific(self, routing: Routing, mode) -> str:
        hit = routing.primary
        out = []
        if mode.scaffold:
            out.append(self._bold("Where this lives"))
            out.append(f"  {' > '.join(routing.trail)}")
            out.append(self._bold("What the page owns"))
            out.append(f"  {hit.scope}")
            out.append(self._bold("What it says"))
            out.append(f"  {hit.snippet(routing.question, 420)}")
        else:
            out.append(self._bold(hit.title or hit.path))
            out.append(f"  {hit.scope}")
            out.append("")
            out.append(f"  {hit.snippet(routing.question, 420)}")
        out.append("")
        out.append("  " + cite.line(hit, self.style))
        if hit.retired:
            out.append(self._dim("  This page is retired. Its current replacement, "
                                 "if any, is the one to act on."))
        supporting = [h for h in routing.hits[1:4] if h.path != hit.path]
        if supporting:
            out.append("")
            out.append(self._dim("  also matched, same scope:"))
            for other in supporting:
                out.append(self._dim(f"    {cite.line(other, self.style)}"))
        out.append(self._next_steps(routing))
        if mode.scaffold:
            out.append(self._dim("  Next: read the page itself, then ask about one "
                                 "thing it names that you cannot yet explain."))
        return "\n".join(out)

    def _broad(self, routing: Routing, mode) -> str:
        hit = routing.primary
        out = [
            self._bold(f"{hit.title or hit.path}  (Sub-Index)"),
            f"  scope: {hit.scope}",
            "",
            "  Pages in this spoke:",
        ]
        children = self.index.children(hit)
        for child in children:
            out.append(f"    {child.title or child.path}")
            out.append(self._dim(f"      {child.scope}"))
        if not children:
            out.append(self._dim("    (none listed yet)"))
        out.append("")
        out.append("  " + cite.line(hit, self.style))
        out.append(self._next_steps(routing))
        return "\n".join(out)

    def _ambiguous(self, routing: Routing) -> str:
        out = [
            self._bold("Two scopes, no owner."),
            f"  {routing.note}",
            "",
            "  Touched:",
        ]
        for name in self.router.touched_names(routing.spokes):
            out.append(f"    {name}")
        out.append("")
        out.append("  Which one do you mean? Add a word from its scope and ask again.")
        return "\n".join(out)

    def _nothing_found(self, routing: Routing, mode) -> str:
        out = [
            self._bold("Not in this corpus."),
            "  Nothing under this root matched, so there is nothing to cite.",
        ]
        if not mode.answer_without_retrieval:
            out.append(self._dim("  This mode does not answer from outside the corpus."))
        spokes = self.index.spokes()
        if spokes:
            out.append("")
            out.append("  What is here:")
            for spoke, scope in sorted(spokes.items()):
                out.append(f"    {spoke}/  {scope}")
        if mode.teach_allowed:
            out.append("")
            out.append("  If you know the answer, type it now and I will write it as a "
                       "page. Press Enter alone to skip.")
            self.pending = routing.question
        else:
            out.append("")
            out.append(self._dim(
                "  This mode does not record taught answers. Legal, medical, "
                "contractual, and safety-adjacent material should not enter the "
                "corpus as something a session typed in. Consult a qualified "
                "professional, and add the page deliberately if you still want it."
            ))
        return "\n".join(out)

    def _next_steps(self, routing: Routing) -> str:
        out = []
        if routing.related:
            out.append("")
            out.append("  Related:")
            for other in routing.related:
                out.append(f"    {other.title or other.path}  ({other.path})")
        if routing.trail:
            out.append(f"  Back to: {' > '.join(routing.trail)}")
        return "\n".join(out)

    def _frame(self, routing: Routing) -> str:
        """Mythic overlay. The frame is a frame: it decorates the route, it
        does not add a claim, and it never speaks as though the console were
        an entity."""
        symbols = self.controller.symbols
        motifs = symbols.get("motifs", ["Index"])
        motif = motifs[len(self.transcript) % len(motifs)]
        role = (symbols.get("roles") or ["Observer"])[
            len(self.transcript) % len(symbols.get("roles", ["Observer"]))
        ]
        if routing.kind == "ambiguous":
            line = f"Two paths open. The {motif} does not choose for the {role}."
        elif routing.kind == "uncertain":
            line = f"The {motif} is dark here. Nothing is written yet."
        else:
            line = f"The {role} approaches the {motif}. What is written:"
        return self._dim(f"  ~ {line}")

    # -- teaching ----------------------------------------------------------
    def _accept_taught_answer(self, line: str) -> str:
        question, self.pending = self.pending, ""
        if not line.strip():
            return self._dim("  Nothing written.")
        written = self.notebook.teach(question, line, sources=[])
        self.reload()
        return "\n".join(
            [
                self._bold("  Written."),
                "  " + written.describe(self.root).replace("\n", "\n  "),
                self._dim("  Listed in notebook/_index.html and logged in "
                          "_log/revisions.html. Run :validate to confirm."),
                self._dim("  It is recorded, not verified. Supersede it with "
                          f":revise {written.document_id} rather than editing it."),
            ]
        )

    # -- commands ----------------------------------------------------------
    def _command(self, raw: str) -> str:
        name, _, arg = raw.partition(" ")
        arg = arg.strip()
        name = name.lower()

        if name in ("quit", "q"):
            return "__QUIT__"
        if name == "help":
            return HELP
        if name == "modes":
            return self.controller.table()
        if name == "mode":
            if not arg:
                return self.controller.describe()
            try:
                switch = self.controller.set(arg if arg.endswith("_mode") else arg + "_mode")
            except KeyError:
                return f"  no such mode: {arg}. Try :modes."
            return f"  {switch.explain()}\n" + self.controller.describe()
        if name == "spokes":
            spokes = self.index.spokes()
            if not spokes:
                return "  no spokes declared"
            return "\n".join(f"  {s}/  {scope}" for s, scope in sorted(spokes.items()))
        if name == "where":
            return self._where()
        if name == "why":
            return self._why()
        if name == "id":
            return self._lookup(arg)
        if name == "history":
            return self._history(arg)
        if name == "status":
            if arg not in ("current", "any"):
                return "  :status current | :status any"
            self.status_override = arg
            note = ("  retrieval now includes retired pages; every result still "
                    "carries its status") if arg == "any" else "  retrieval limited to current pages"
            return note
        if name == "validate":
            return validate(self.root).summary()
        if name == "stats":
            return self._stats()
        if name == "reload":
            self.reload()
            return "  re-crawled\n" + self._stats()
        if name == "teach":
            return self._teach_command(arg)
        if name == "revise":
            return self._revise_command(arg)
        return f"  unknown command: :{name}. Try :help."

    def _teach_command(self, arg: str) -> str:
        if not self.controller.current.teach_allowed:
            return ("  " + self.controller.current.name + " does not record taught "
                    "pages. Switch mode deliberately if you mean to.")
        question, sep, answer = arg.partition("|")
        if not sep:
            return '  :teach <question> | <answer>'
        written = self.notebook.teach(question.strip(), answer.strip())
        self.reload()
        return "  Written.\n  " + written.describe(self.root).replace("\n", "\n  ")

    def _revise_command(self, arg: str) -> str:
        doc_id, sep, rest = arg.partition(" ")
        answer, _, note = rest.partition("|")
        if not doc_id or not answer.strip():
            return "  :revise <DOC-ID> <new answer> [| revision note]"
        try:
            written = self.notebook.revise(
                doc_id.strip(), answer.strip(), note=note.strip()
            )
        except KeyError as exc:
            return f"  {exc}"
        self.reload()
        return "  Superseded.\n  " + written.describe(self.root).replace("\n", "\n  ")

    def _lookup(self, doc_id: str) -> str:
        if not doc_id:
            return "  :id <DOC-ID>"
        hits = self.index.by_id(doc_id)
        if not hits:
            return f"  no document with ID {doc_id}"
        return "\n".join(self._record(hit) for hit in hits)

    def _history(self, doc_id: str) -> str:
        if not doc_id:
            return "  :history <DOC-ID>"
        chain = self.index.history(doc_id)
        if not chain:
            return f"  no document with ID {doc_id}"
        out = [self._bold(f"  {doc_id}: {len(chain)} version(s) on record")]
        for hit in chain:
            out.append(f"    {cite.line(hit, self.style)}")
            out.append(self._dim(f"      {hit.snippet('', 140)}"))
        out.append(self._dim("  Retired versions are kept, not deleted. That is what "
                             "lets this question be answered at all."))
        return "\n".join(out)

    def _record(self, hit: Hit) -> str:
        return "\n".join(
            [
                self._bold(f"  {hit.title or hit.path}"),
                f"    id       {hit.document_id}",
                f"    path     {hit.path}  ({hit.substrate}, found by {hit.discovered_by})",
                f"    scope    {hit.scope}",
                f"    triggers {hit.when_to_use}",
                f"    version  {hit.updated}",
                f"    status   {hit.status}",
            ]
        )

    def _where(self) -> str:
        if not self.transcript or not self.transcript[-1].routing:
            return "  nothing answered yet"
        routing = self.transcript[-1].routing
        if not routing.primary:
            return "  the last answer came from no page; nothing was found"
        out = [self._record(routing.primary), "", "  " + cite.scope_note(routing.primary)]
        out.append("  " + cite.LOCAL_NOTICE)
        return "\n".join(out)

    def _why(self) -> str:
        if not self.transcript:
            return "  nothing answered yet"
        turn = self.transcript[-1]
        routing = turn.routing
        out = [
            self._bold("  Routing"),
            f"    question   {turn.question}",
            f"    mode       {turn.mode}",
            f"    decision   {routing.kind if routing else 'n/a'}",
        ]
        if routing and routing.spokes:
            out.append("    scores")
            for spoke, score in sorted(routing.spokes.items(), key=lambda kv: -kv[1]):
                mark = "  <- owns it" if spoke == routing.owner else ""
                out.append(f"      {spoke or 'root'}: {score:.2f}{mark}")
            out.append(self._dim(
                "    A spoke owns the question when it leads by 1.5x. Otherwise "
                "the answer would merge two scopes, so you get asked instead."
            ))
        if routing and routing.note:
            out.append(f"    note       {routing.note}")
        return "\n".join(out)

    def _stats(self) -> str:
        counts = self.index.counts()
        out = [
            f"  {counts['pages']} page(s): {counts['current']} current, "
            f"{counts['retired']} retired, across {counts['spokes']} spoke(s)",
        ]
        if counts["orphans"]:
            out.append(self._dim(
                f"  FM-L2  {counts['orphans']} orphan(s) not ingested: "
                + ", ".join(self.index.orphans)
            ))
        return "\n".join(out)

    def _boot_summary(self) -> str:
        counts = self.index.counts()
        spokes = ", ".join(sorted(self.index.spokes())) or "none"
        return (
            f"  root    {self.root}\n"
            f"  corpus  {counts['current']} current, {counts['retired']} retired\n"
            f"  spokes  {spokes}\n"
            f"  mode    {self.controller.current.name}\n"
        )

    def reload(self) -> None:
        self.index.close()
        self.index = Index.open(self.root)
        self.router = Router(self.index)

    # -- formatting --------------------------------------------------------
    def _prompt(self) -> str:
        label = self.controller.current.label
        return f"[{label}] > " if not self.color else f"\033[36m[{label}]\033[0m > "

    def _bold(self, text: str) -> str:
        return f"\033[1m{text}\033[0m" if self.color else text

    def _dim(self, text: str) -> str:
        return f"\033[2m{text}\033[0m" if self.color else text
