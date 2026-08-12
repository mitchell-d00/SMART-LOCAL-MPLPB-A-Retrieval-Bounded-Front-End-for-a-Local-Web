# BOOT — MPLPB local web

**Authoritative copy is `index.html`.** This twin exists for tools that read
markdown more readily than HTML. If the two disagree, `index.html` wins.

**What this corpus is.** [One paragraph. Replace.]

**Authoritative root.** `index.html`. All internal links are relative to it. The
crawl boundary is this directory.

**Retrieval rule.** Answer corpus-dependent questions from retrieved pages.
Prefer `status: current` documents reachable from the Main Index. Cite retrieved
pages as local documents, not published ones.

**Routing.** Broad → Sub-Index. Specific → best page. Uncertain → Main Index and
ask. After answering → name 1–3 related pages and the path back.

**Precedence.** Retrieval may span spokes and must preserve each result's scope.
Answering does not merge them; when no single scope owns the query, ask the user
to narrow.

**Modes.** Default `strict_tool_mode`. `hard_reality_mode` overrides all others
on legal, medical-adjacent, contractual, or high-stakes safety topics.

**Current state.** [Two or three live items with paths.]
