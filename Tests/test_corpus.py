"""Parsing, the three ingestion paths, and the eight structural checks."""

from __future__ import annotations

import unittest

from mplpb.crawl import crawl
from mplpb.page import parse
from mplpb.validate import validate
from tests.support import CorpusTest


class TestPage(CorpusTest):
    def test_metadata_is_read_from_meta_tags(self) -> None:
        page = parse(self.root / "spec/link_discipline.html", self.root)
        self.assertEqual(page.document_id, "LOCAL-SPEC-001")
        self.assertEqual(page.status, "current")
        self.assertEqual(page.supersedes, ["LOCAL-SPEC-OLD-001"])
        self.assertEqual(page.spoke, "spec")
        self.assertEqual(page.version, 2)

    def test_supersedes_splits_on_semicolons(self) -> None:
        path = self.add_page(
            "spec/multi.html", supersedes="A-1; A-2 ;A-3", listed=True
        )
        self.assertEqual(parse(path, self.root).supersedes, ["A-1", "A-2", "A-3"])

    def test_record_card_is_not_indexed_as_text(self) -> None:
        # The card restates metadata already captured; indexing it makes every
        # page match its own field names.
        page = parse(self.root / "spec/link_discipline.html", self.root)
        self.assertNotIn("Document ID", page.text)
        self.assertIn("crawl boundary", page.text)

    def test_external_links_are_not_internal(self) -> None:
        page = parse(self.root / "index.html", self.root)
        self.assertTrue(all(not h.startswith("http") for h in page.internal_hrefs()))


class TestCrawl(CorpusTest):
    def test_graph_and_audit_paths(self) -> None:
        result = crawl(self.root)
        by_path = {r["path"]: r for r in result.records}
        self.assertEqual(by_path["spec/link_discipline.html"]["discovered_by"], "graph")
        retired = by_path["_log/superseded/link_discipline_v1.html"]
        self.assertEqual(retired["discovered_by"], "audit")
        self.assertEqual(retired["status"], "retired")
        self.assertEqual(result.orphans, [])

    def test_orphans_are_reported_not_ingested(self) -> None:
        self.add_page("spec/loose.html", listed=False, document_id="LOCAL-TEST-ORPHAN")
        result = crawl(self.root)
        self.assertIn("spec/loose.html", result.orphans)
        self.assertNotIn("spec/loose.html", [r["path"] for r in result.records])

    def test_every_record_declares_local_substrate(self) -> None:
        # FM-L10: a local page must never be citable as a published one.
        self.assertTrue(all(r["substrate"] == "local" for r in crawl(self.root).records))


class TestValidate(CorpusTest):
    def codes(self) -> set[str]:
        return {f.check for f in validate(self.root).findings}

    def test_example_corpus_is_clean(self) -> None:
        report = validate(self.root)
        self.assertTrue(report.ok, report.summary())
        self.assertEqual(report.retired, 1)

    def test_11_1_broken_link(self) -> None:
        self.edit("spec/_index.html", "./link_discipline.html", "./gone.html")
        self.assertIn("11.1", self.codes())

    def test_11_2_orphan(self) -> None:
        self.add_page("spec/loose.html", listed=False, document_id="LOCAL-TEST-ORPHAN")
        self.assertIn("11.2", self.codes())

    def test_11_3_missing_metadata(self) -> None:
        self.edit(
            "physics/heat_transfer.html",
            '<meta name="mplpb:scope"',
            '<meta name="mplpb:nope"',
        )
        self.assertIn("11.3", self.codes())

    def test_11_4_duplicate_document_id(self) -> None:
        self.add_page("physics/copy.html", document_id="LOCAL-PHYS-001")
        self.assertIn("11.4", self.codes())

    def test_11_5_retired_page_outside_superseded(self) -> None:
        self.add_page("physics/dead.html", document_id="LOCAL-DEAD-1", status="retired")
        self.assertIn("11.5", self.codes())

    def test_11_5_supersedes_a_page_that_is_not_retired(self) -> None:
        self.edit(
            "spec/supersession.html",
            '<meta name="mplpb:supersedes" content="">',
            '<meta name="mplpb:supersedes" content="LOCAL-PHYS-001">',
        )
        self.assertIn("11.5", self.codes())

    def test_11_6_link_escapes_the_root(self) -> None:
        self.edit("physics/heat_transfer.html", 'href="../index.html"',
                  'href="../../outside.html"')
        self.assertIn("11.6", self.codes())

    def test_11_7_page_not_listed_in_its_sub_index(self) -> None:
        self.add_page("physics/unlisted.html", listed=False,
                      document_id="LOCAL-TEST-UNLISTED")
        # linked from the Main Index, so reachable, but not listed by its spoke
        self.edit("index.html", "</ul>", '<li><a href="physics/unlisted.html">x</a></li></ul>')
        self.assertIn("11.7", self.codes())

    def test_11_8_date_without_time_is_rejected(self) -> None:
        # Three revisions in one working day cannot be ordered from a date.
        self.edit("physics/heat_transfer.html", "2026-08-05T18:40Z v1", "2026-08-05 v1")
        self.assertIn("11.8", self.codes())

    def test_findings_name_their_failure_mode(self) -> None:
        self.edit("spec/_index.html", "./link_discipline.html", "./gone.html")
        finding = next(f for f in validate(self.root).findings if f.check == "11.1")
        self.assertEqual(finding.failure_mode, "FM-L1")


if __name__ == "__main__":
    unittest.main()
