#!/usr/bin/env python3
"""
Render docs/Smart_Local_MPLPB.md as a typeset PDF and a plain-text twin.

    python3 tools/make_paper.py [outdir]

Deliberately a small hand-rolled renderer rather than a general Markdown
engine: the paper uses a fixed subset (headings, paragraphs, tables, fenced
code, blockquote rules, bold/italic/code spans), and a renderer that handles
exactly that subset is easier to check than one that handles everything.
"""

from __future__ import annotations

import html
import re
import sys
import textwrap
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "docs" / "Smart_Local_MPLPB.md"

INK = colors.HexColor("#12171C")
DIM = colors.HexColor("#5A6672")
RULE = colors.HexColor("#D3DAE1")
CARD = colors.HexColor("#EFF2F4")
LINK = colors.HexColor("#2E4A7D")

TITLE = "Smart Local MPLPB"
SUBTITLE = "A Retrieval-Bounded Front End for a Local Web"
AUTHOR = "Mitchell D. McPhetridge"


def styles() -> dict:
    base = getSampleStyleSheet()
    made = {
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontName="Times-Bold", fontSize=24,
            leading=28, textColor=INK, spaceAfter=6,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=base["Normal"], fontName="Times-Italic",
            fontSize=13.5, leading=17, alignment=TA_CENTER, textColor=DIM,
            spaceAfter=18,
        ),
        "author": ParagraphStyle(
            "author", parent=base["Normal"], fontName="Times-Roman", fontSize=11.5,
            leading=15, alignment=TA_CENTER, textColor=INK, spaceAfter=2,
        ),
        "affil": ParagraphStyle(
            "affil", parent=base["Normal"], fontName="Times-Italic", fontSize=10,
            leading=13, alignment=TA_CENTER, textColor=DIM, spaceAfter=16,
        ),
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"], fontName="Times-Bold", fontSize=14.5,
            leading=18, textColor=INK, spaceBefore=20, spaceAfter=7,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontName="Times-Bold", fontSize=11.5,
            leading=15, textColor=INK, spaceBefore=13, spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "body", parent=base["BodyText"], fontName="Times-Roman", fontSize=10.5,
            leading=15.2, textColor=INK, alignment=TA_JUSTIFY, spaceAfter=8,
        ),
        "meta": ParagraphStyle(
            "meta", parent=base["BodyText"], fontName="Times-Roman", fontSize=9,
            leading=12.5, textColor=INK, spaceAfter=2,
        ),
        "cell": ParagraphStyle(
            "cell", parent=base["BodyText"], fontName="Times-Roman", fontSize=8.6,
            leading=11.4, textColor=INK, spaceAfter=0,
        ),
        "cellhead": ParagraphStyle(
            "cellhead", parent=base["BodyText"], fontName="Times-Bold", fontSize=8.6,
            leading=11.4, textColor=INK, spaceAfter=0,
        ),
        "code": ParagraphStyle(
            "code", parent=base["Code"], fontName="Courier", fontSize=8.2,
            leading=10.6, textColor=INK, backColor=CARD, borderPadding=6,
            leftIndent=6, spaceBefore=4, spaceAfter=10,
        ),
        "closing": ParagraphStyle(
            "closing", parent=base["BodyText"], fontName="Times-Italic", fontSize=9.5,
            leading=13, textColor=DIM, alignment=TA_JUSTIFY, spaceAfter=8,
        ),
    }
    return made


# --- inline markdown ------------------------------------------------------
def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r'<font face="Courier" size="9">\1</font>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<font color="#2E4A7D">\1</font>', text)
    return text.replace("&amp;nbsp;", "&nbsp;")


def is_table_row(line: str) -> bool:
    return line.startswith("|") and line.endswith("|")


def split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def build_table(rows: list[list[str]], st: dict, width: float) -> Table:
    header, body = rows[0], rows[1:]
    data = [[Paragraph(inline(c or "—"), st["cellhead"]) for c in header]]
    data += [[Paragraph(inline(c or "—"), st["cell"]) for c in row] for row in body]
    columns = len(header)
    if columns == 2:
        widths = [width * 0.28, width * 0.72]
    else:
        widths = [width / columns] * columns
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), CARD),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE),
                ("LINEBELOW", (0, 1), (-1, -2), 0.25, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def wrap_code(block: list[str], limit: int = 88) -> list[str]:
    out = []
    for line in block:
        while len(line) > limit:
            out.append(line[:limit])
            line = "    " + line[limit:]
        out.append(line)
    return out


def render(markdown: str, st: dict, width: float) -> list:
    story: list = []
    lines = markdown.splitlines()
    i = 0
    seen_title = False
    paragraph: list[str] = []

    def flush() -> None:
        nonlocal paragraph
        if not paragraph:
            return
        joined = " ".join(paragraph)
        paragraph = []
        # The author block is set as front matter, not as body text.
        if AUTHOR in joined and "Independent Researcher" in joined and len(joined) < 90:
            return
        story.append(Paragraph(inline(joined), st["body"]))

    while i < len(lines):
        line = lines[i].rstrip()

        if line.startswith("```"):
            flush()
            i += 1
            block = []
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i].rstrip())
                i += 1
            i += 1
            story.append(Preformatted("\n".join(wrap_code(block)), st["code"]))
            continue

        if is_table_row(line):
            flush()
            rows = []
            while i < len(lines) and is_table_row(lines[i].strip()):
                cells = split_row(lines[i].strip())
                if not all(set(c) <= set("-: ") for c in cells):
                    rows.append(cells)
                i += 1
            story.append(Spacer(1, 3))
            story.append(build_table(rows, st, width))
            story.append(Spacer(1, 9))
            continue

        if line.startswith("# "):
            flush()
            if not seen_title:
                seen_title = True
                story.append(Spacer(1, 26))
                story.append(Paragraph(inline(line[2:]), st["title"]))
            else:
                story.append(Paragraph(inline(line[2:]), st["h1"]))
            i += 1
            continue

        if line.startswith("### "):
            flush()
            text = line[4:]
            if not story or len(story) < 3:
                story.append(Paragraph(inline(text), st["subtitle"]))
            else:
                story.append(Paragraph(inline(text), st["h2"]))
            i += 1
            continue

        if line.startswith("## "):
            flush()
            story.append(Paragraph(inline(line[3:]), st["h1"]))
            i += 1
            continue

        if line.strip() in ("---", "***", "___"):
            flush()
            story.append(Spacer(1, 6))
            story.append(HRFlowable(width="100%", thickness=0.6, color=RULE))
            story.append(Spacer(1, 8))
            i += 1
            continue

        if line.startswith("- ") or re.match(r"^\d+\.\s", line):
            flush()
            marker, text = ("\u2022", line[2:]) if line.startswith("- ") else (
                line.split(".", 1)[0] + ".", line.split(". ", 1)[1]
            )
            bullet = ParagraphStyle(
                "bullet", parent=st["body"], leftIndent=16, bulletIndent=4,
                spaceAfter=4,
            )
            story.append(Paragraph(inline(text), bullet, bulletText=marker))
            i += 1
            continue

        if not line.strip():
            flush()
            i += 1
            continue

        paragraph.append(line.strip())
        i += 1

    flush()
    return story


def front_matter(story: list, st: dict) -> list:
    """Insert author block after the title and subtitle."""
    out = []
    inserted = False
    for flowable in story:
        out.append(flowable)
        if not inserted and getattr(flowable, "style", None) is st["subtitle"]:
            out.append(Paragraph(AUTHOR, st["author"]))
            out.append(Paragraph("Independent Researcher", st["affil"]))
            inserted = True
    return out


def page_furniture(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Times-Roman", 8.5)
    canvas.setFillColor(DIM)
    if doc.page > 1:
        canvas.drawString(inch, letter[1] - 0.62 * inch, TITLE)
        canvas.drawRightString(
            letter[0] - inch, letter[1] - 0.62 * inch, "MPLPB-SMART-011 v1"
        )
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.4)
        canvas.line(inch, letter[1] - 0.72 * inch, letter[0] - inch, letter[1] - 0.72 * inch)
    canvas.drawCentredString(letter[0] / 2, 0.62 * inch, str(doc.page))
    canvas.restoreState()


def to_text(markdown: str) -> str:
    """Plain-text twin. Tables become aligned columns; markers are dropped."""
    out: list[str] = []
    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        if is_table_row(line.strip()):
            rows = []
            while i < len(lines) and is_table_row(lines[i].strip()):
                cells = split_row(lines[i].strip())
                if not all(set(c) <= set("-: ") for c in cells):
                    rows.append([strip_inline(c) for c in cells])
                i += 1
            widths = [
                max(len(row[c]) for row in rows if c < len(row))
                for c in range(max(len(r) for r in rows))
            ]
            widths = [min(w, 46) for w in widths]
            for n, row in enumerate(rows):
                # Wrap rather than truncate: a plain-text twin that drops the
                # end of a scope declaration is not a twin.
                wrapped = [
                    textwrap.wrap(row[c] if c < len(row) else "", widths[c]) or [""]
                    for c in range(len(widths))
                ]
                for line_no in range(max(len(w) for w in wrapped)):
                    cells = [
                        (wrapped[c][line_no] if line_no < len(wrapped[c]) else "")
                        .ljust(widths[c])
                        for c in range(len(widths))
                    ]
                    out.append("  " + "  ".join(cells).rstrip())
                if n == 0:
                    out.append("  " + "  ".join("-" * w for w in widths))
            out.append("")
            continue

        if line.startswith("```"):
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                out.append("    " + lines[i].rstrip())
                i += 1
            i += 1
            out.append("")
            continue

        if line.startswith("#"):
            text = strip_inline(line.lstrip("#").strip())
            level = len(line) - len(line.lstrip("#"))
            out.append("")
            if level == 1:
                out.append(text.upper())
                out.append("=" * len(text))
            elif level == 2:
                out.append(text)
                out.append("-" * len(text))
            else:
                out.append(text)
            out.append("")
            i += 1
            continue

        if line.strip() == "---":
            out.append("")
            out.append("-" * 78)
            out.append("")
            i += 1
            continue

        out.append(strip_inline(line))
        i += 1

    text = "\n".join(out)
    return re.sub(r"\n{4,}", "\n\n\n", text).strip() + "\n"


def strip_inline(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", text)
    # Emphasis spanning a line break leaves a lone marker behind; the plain
    # text has no use for one either way.
    return text.replace("*", "")


def main() -> int:
    outdir = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "docs"
    outdir.mkdir(parents=True, exist_ok=True)
    markdown = SOURCE.read_text(encoding="utf-8")

    (outdir / "Smart_Local_MPLPB.txt").write_text(to_text(markdown), encoding="utf-8")
    if outdir != SOURCE.parent:
        (outdir / "Smart_Local_MPLPB.md").write_text(markdown, encoding="utf-8")

    pdf = outdir / "Smart_Local_MPLPB.pdf"
    st = styles()
    doc = BaseDocTemplate(
        str(pdf), pagesize=letter,
        leftMargin=inch, rightMargin=inch, topMargin=0.95 * inch,
        bottomMargin=0.9 * inch,
        title=f"{TITLE}: {SUBTITLE}", author=AUTHOR,
        subject="MPLPB-SMART-011 v1 — reference front end for an MPLPB local web",
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body",
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=page_furniture)])
    story = front_matter(render(markdown, st, doc.width), st)
    doc.build(story)

    print(f"wrote {outdir / 'Smart_Local_MPLPB.md'}")
    print(f"wrote {outdir / 'Smart_Local_MPLPB.txt'}")
    print(f"wrote {pdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
