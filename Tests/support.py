"""Shared fixtures: build small corpora on disk, in a temp directory."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from mplpb.notebook import ENTRY_MARKER, render_page, stamp

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "site"


def page(**kw) -> str:
    kw.setdefault("status", "current")
    kw.setdefault("owner", "Test Owner")
    return render_page(**kw)


class CorpusTest(unittest.TestCase):
    """A throwaway copy of the example corpus, per test."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="mplpb-test-"))
        self.root = self.tmp / "site"
        shutil.copytree(EXAMPLE, self.root)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def add_page(self, rel: str, *, listed: bool = True, **kw) -> Path:
        """Add a page to a spoke, optionally listing it in that Sub-Index."""
        kw.setdefault("title", rel)
        kw.setdefault("document_id", "LOCAL-TEST-001")
        kw.setdefault("category", "Test / Fixture")
        kw.setdefault("scope", "A page that exists for a test to look at")
        kw.setdefault("when_to_use", "Only in tests")
        kw.setdefault("updated", stamp())
        kw.setdefault("depth", 1)
        kw.setdefault("heading", "Fixture")
        kw.setdefault("body", "<p>Fixture page.</p>")
        path = self.write(rel, page(**kw))
        if listed:
            sub = self.root / Path(rel).parent / "_index.html"
            text = sub.read_text(encoding="utf-8")
            entry = f'  <li><a href="./{Path(rel).name}">{kw["title"]}</a></li>'
            sub.write_text(text.replace(ENTRY_MARKER, entry + "\n" + ENTRY_MARKER), "utf-8")
        return path

    def edit(self, rel: str, old: str, new: str) -> None:
        path = self.root / rel
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text, f"fixture text not found in {rel}")
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
