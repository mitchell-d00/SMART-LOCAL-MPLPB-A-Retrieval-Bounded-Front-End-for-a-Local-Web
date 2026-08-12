"""
mplpb -- a front end for an MPLPB local web.

Standard library only. No pip install, no server required, no network.

    from mplpb import Console, Index, validate

    index = Index.open("site")
    for hit in index.search("relative link"):
        print(hit.document_id, hit.path, hit.status)

    Console("site").ask("what is a spoke?")

Layers, kept separate on purpose:

    page / crawl / validate   the corpus and its structural rules
    index / router / cite     retrieval, scope precedence, provenance
    modes                     how the front end is allowed to answer
    notebook                  how a taught answer becomes a page
    console / server          the two front ends

Reference specification: MPLPB-LOCAL-008 v4.
"""

from .cite import block as cite_block
from .cite import bracket as cite_bracket
from .console import Console
from .crawl import CrawlResult, crawl
from .index import Hit, Index
from .modes import Mode, ModeController
from .notebook import Notebook
from .page import Page, parse
from .router import Router, Routing
from .validate import Finding, Report, validate

__version__ = "0.1.0"
__spec_version__ = "MPLPB-LOCAL-008 v4"

__all__ = [
    "Console",
    "CrawlResult",
    "Finding",
    "Hit",
    "Index",
    "Mode",
    "ModeController",
    "Notebook",
    "Page",
    "Report",
    "Router",
    "Routing",
    "cite_block",
    "cite_bracket",
    "crawl",
    "parse",
    "validate",
    "__version__",
]
