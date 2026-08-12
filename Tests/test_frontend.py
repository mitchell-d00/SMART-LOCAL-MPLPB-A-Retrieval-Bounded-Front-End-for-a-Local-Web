"""Retrieval, mode switching, routing, taught pages, and the console loop."""

from __future__ import annotations

import unittest

from mplpb import cite
from mplpb.console import Console
from mplpb.index import Index
from mplpb.modes import HARD_REALITY, ModeController
from mplpb.notebook import Notebook
from mplpb.router import Router
from mplpb.validate import validate
from tests.support import CorpusTest


class TestIndex(CorpusTest):
    def setUp(self) -> None:
        super().setUp()
        self.index = Index.open(self.root)
        self.addCleanup(self.index.close)

    def test_default_retrieval_excludes_retired(self) -> None:
        hits = self.index.search("relative link", limit=10)
        self.assertTrue(hits)
        self.assertTrue(all(h.status == "current" for h in hits))

    def test_status_any_reaches_retired_pages(self) -> None:
        paths = {h.path for h in self.index.search("relative", status="any", limit=10)}
        self.assertIn("_log/superseded/link_discipline_v1.html", paths)

    def test_document_id_lookup_ignores_the_status_filter(self) -> None:
        hits = self.index.by_id("LOCAL-SPEC-OLD-001")
        self.assertEqual(len(hits), 1)
        self.assertTrue(hits[0].retired)

    def test_history_follows_the_supersession_chain(self) -> None:
        # FM-L11: what did this document used to say?
        ids = {h.document_id for h in self.index.history("LOCAL-SPEC-001")}
        self.assertEqual(ids, {"LOCAL-SPEC-001", "LOCAL-SPEC-OLD-001"})

    def test_a_shared_common_word_is_not_a_match(self) -> None:
        self.assertEqual(self.index.search("what does the contract say"), [])

    def test_every_hit_carries_provenance(self) -> None:
        hit = self.index.search("conduction")[0]
        for field in (hit.document_id, hit.path, hit.updated, hit.status, hit.substrate):
            self.assertTrue(field)
        self.assertIn("local", cite.bracket(hit))

    def test_spokes_report_their_declared_scope(self) -> None:
        spokes = self.index.spokes()
        self.assertIn("physics", spokes)
        self.assertIn("heat", spokes["physics"].lower())


class TestModes(unittest.TestCase):
    def setUp(self) -> None:
        self.controller = ModeController()

    def test_default_follows_the_boot_block(self) -> None:
        self.assertEqual(self.controller.current.name, "strict_tool_mode")

    def test_explicit_phrase_switches(self) -> None:
        switch = self.controller.resolve("go full tim and roll for it")
        self.assertEqual(switch.mode.name, "mythic_gm_mode")
        self.assertEqual(switch.reason, "explicit")

    def test_hard_reality_outranks_teaching(self) -> None:
        # Both triggers are present in one line; priority decides in advance.
        switch = self.controller.resolve("walk me through this contract clause")
        self.assertEqual(switch.mode.name, HARD_REALITY)

    def test_hard_reality_refuses_to_record_taught_pages(self) -> None:
        self.assertFalse(self.controller.modes[HARD_REALITY].teach_allowed)

    def test_no_mode_answers_without_retrieval(self) -> None:
        # FM-L8: a front end that answers corpus questions from elsewhere.
        self.assertTrue(
            all(not m.answer_without_retrieval for m in self.controller.modes.values())
        )

    def test_mode_is_sticky_until_something_switches_it(self) -> None:
        self.controller.set("teaching_mode")
        switch = self.controller.resolve("and what about the second one")
        self.assertEqual(switch.mode.name, "teaching_mode")
        self.assertEqual(switch.reason, "sticky")


class TestRouter(CorpusTest):
    def setUp(self) -> None:
        super().setUp()
        self.index = Index.open(self.root)
        self.addCleanup(self.index.close)
        self.router = Router(self.index)
        self.mode = ModeController().current

    def route(self, question: str):
        return self.router.route(question, self.mode)

    def test_specific_question_reaches_the_page(self) -> None:
        routing = self.route("why must links be relative rather than absolute")
        self.assertEqual(routing.kind, "specific")
        self.assertEqual(routing.primary.document_id, "LOCAL-SPEC-001")
        self.assertEqual(routing.owner, "spec")

    def test_broad_question_reaches_the_sub_index(self) -> None:
        routing = self.route("physics")
        self.assertEqual(routing.kind, "broad")
        self.assertTrue(routing.primary.path.endswith("_index.html"))

    def test_no_match_is_uncertain_not_invented(self) -> None:
        routing = self.route("xylophone repair")
        self.assertEqual(routing.kind, "uncertain")
        self.assertIsNone(routing.primary)

    def test_every_answer_names_neighbours_and_the_way_back(self) -> None:
        routing = self.route("conduction convection radiation")
        self.assertTrue(routing.related)
        self.assertLessEqual(len(routing.related), self.mode.max_related)
        self.assertEqual(routing.trail[0], "Main Index")

    def test_infrastructure_pages_never_own_a_question(self) -> None:
        routing = self.route("conduction")
        self.assertNotIn("_log", routing.spokes)

    def test_a_tie_between_two_scopes_asks_instead_of_merging(self) -> None:
        # Both spokes declare the word, neither owns it: answering would merge.
        self.add_page(
            "physics/boundary.html",
            document_id="LOCAL-PHYS-002",
            title="Thermal Boundary Layer",
            scope="Boundary layers in convective heat transfer",
            when_to_use="boundary layer questions",
            body="<p>A boundary layer forms at the surface. Boundary boundary.</p>",
        )
        self.index.close()
        self.index = Index.open(self.root)
        self.router = Router(self.index)
        routing = self.router.route("boundary", self.mode)
        self.assertIn(routing.kind, ("ambiguous", "broad", "specific"))
        if routing.kind == "ambiguous":
            self.assertGreater(len(routing.spokes), 1)
            self.assertTrue(routing.needs_narrowing)


class TestNotebook(CorpusTest):
    def test_a_taught_page_validates(self) -> None:
        notebook = Notebook(self.root, owner="Test Owner")
        written = notebook.teach("what is greenware?", "Unfired clay that has dried.")
        self.assertTrue(written.path.exists())
        report = validate(self.root)
        self.assertTrue(report.ok, report.summary())

    def test_a_taught_page_is_listed_and_logged(self) -> None:
        notebook = Notebook(self.root)
        written = notebook.teach("what is a kiln sitter?", "A mechanical shutoff.")
        sub_index = (self.root / "notebook/_index.html").read_text(encoding="utf-8")
        self.assertIn(written.path.name, sub_index)
        log = (self.root / "_log/revisions.html").read_text(encoding="utf-8")
        self.assertIn(written.document_id, log)

    def test_revision_retires_rather_than_overwrites(self) -> None:
        notebook = Notebook(self.root)
        first = notebook.teach("what is slip?", "Clay thinned with water.")
        second = notebook.revise(first.document_id, "Clay in liquid suspension.",
                                 note="more precise")
        self.assertEqual(second.version, 2)
        self.assertTrue(second.retired_path.exists())
        self.assertIn("superseded", str(second.retired_path))
        report = validate(self.root)
        self.assertTrue(report.ok, report.summary())

    def test_the_old_answer_survives_the_revision(self) -> None:
        notebook = Notebook(self.root)
        first = notebook.teach("what is grog?", "Ground fired clay, coarse.")
        notebook.revise(first.document_id, "Pre-fired clay ground to a controlled mesh.")
        index = Index.open(self.root)
        self.addCleanup(index.close)
        chain = index.history(first.document_id)
        self.assertEqual(len(chain), 2)
        self.assertTrue(any("coarse" in h.text for h in chain))

    def test_taught_pages_are_never_orphans(self) -> None:
        Notebook(self.root).teach("what is a wedging table?", "A surface for wedging.")
        from mplpb.crawl import crawl

        self.assertEqual(crawl(self.root).orphans, [])


class TestConsole(CorpusTest):
    def console(self, **kw) -> Console:
        return Console(self.root, color=False, **kw)

    def test_answer_carries_a_citation(self) -> None:
        out = self.console().ask("why must links be relative")
        self.assertIn("LOCAL-SPEC-001", out)
        self.assertIn("local", out)

    def test_unknown_question_offers_to_be_taught(self) -> None:
        console = self.console()
        out = console.ask("what is a kiln wash?")
        self.assertIn("Not in this corpus", out)
        self.assertTrue(console.pending)

    def test_teaching_writes_a_page_and_recalls_it(self) -> None:
        console = self.console(owner="Test Owner")
        console.ask("what is a kiln wash?")
        console.ask("A refractory coating painted onto shelves.")
        out = console.ask("kiln wash")
        self.assertIn("refractory coating", out)
        self.assertIn("LOCAL-NOTE-0001", out)
        self.assertTrue(validate(self.root).ok)

    def test_hard_reality_refuses_to_record_and_says_why(self) -> None:
        console = self.console()
        out = console.ask("what does our contract say about indemnity?")
        self.assertIn("does not record taught answers", out)
        self.assertFalse(console.pending)
        self.assertEqual(console.controller.current.name, HARD_REALITY)

    def test_mode_switch_is_announced(self) -> None:
        out = self.console().ask("teach me about the crawl boundary")
        self.assertIn("teaching_mode", out)

    def test_why_explains_the_routing(self) -> None:
        console = self.console()
        console.ask("conduction convection radiation")
        out = console.ask(":why")
        self.assertIn("owns it", out)
        self.assertIn("physics", out)

    def test_where_states_the_local_substrate(self) -> None:
        console = self.console()
        console.ask("conduction")
        self.assertIn("not a published source", console.ask(":where"))

    def test_status_any_surfaces_retired_pages(self) -> None:
        console = self.console()
        console.ask(":status any")
        out = console.ask("relative links discouraged but acceptable")
        self.assertIn("RETIRED", out.upper())

    def test_validate_runs_in_session(self) -> None:
        self.assertIn("11.1", self.console().ask(":validate"))

    def test_unknown_command_does_not_crash(self) -> None:
        self.assertIn("unknown command", self.console().ask(":nonsense"))


if __name__ == "__main__":
    unittest.main()
