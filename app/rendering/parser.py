"""Convert generated section text into structured document blocks."""

from __future__ import annotations

import re

from app.schemas.document import (
    BulletListBlock,
    DocumentBlock,
    HeadingBlock,
    PageBreakBlock,
    ParagraphBlock,
    TableBlock,
)

_PAGE_BREAK_MARKERS = {
    "\f",
    "<!-- pagebreak -->",
    "<!-- page break -->",
    "[[pagebreak]]",
    "[pagebreak]",
}
_HEADING_RE = re.compile(r"^(#{2,4})\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^\s*[-*+•]\s+(.+?)\s*$")
_SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")


def blocks_from_text(text: str) -> list[DocumentBlock]:
    """Parse paragraphs, bullets, tables, headings, and page breaks from text.

    The parser intentionally supports a small Markdown-like subset: ``##``
    through ``####`` headings, ``-``/``*`` bullets, pipe tables with a
    separator row, and explicit page-break markers. Everything else is retained
    as ordinary paragraph text.
    """

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\f", "\n\f\n")
    lines = normalized.split("\n")
    blocks: list[DocumentBlock] = []
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        paragraph = " ".join(part.strip() for part in paragraph_lines if part.strip())
        if paragraph:
            blocks.append(ParagraphBlock(text=paragraph))
        paragraph_lines.clear()

    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            index += 1
            continue

        if stripped.lower() in _PAGE_BREAK_MARKERS:
            flush_paragraph()
            blocks.append(PageBreakBlock())
            index += 1
            continue

        heading_match = _HEADING_RE.match(stripped)
        if heading_match:
            flush_paragraph()
            blocks.append(
                HeadingBlock(
                    level=min(len(heading_match.group(1)), 4),
                    text=heading_match.group(2),
                )
            )
            index += 1
            continue

        bullet_match = _BULLET_RE.match(line)
        if bullet_match:
            flush_paragraph()
            items: list[str] = []
            while index < len(lines):
                current = _BULLET_RE.match(lines[index])
                if current is None:
                    break
                items.append(current.group(1))
                index += 1
            blocks.append(BulletListBlock(items=items))
            continue

        table_lines: list[str] = []
        while index < len(lines) and _looks_like_table_row(lines[index]):
            table_lines.append(lines[index])
            index += 1
        table = _parse_table(table_lines)
        if table is not None:
            flush_paragraph()
            blocks.append(table)
            continue
        if table_lines:
            paragraph_lines.extend(table_lines)
            continue

        paragraph_lines.append(stripped)
        index += 1

    flush_paragraph()
    return blocks


def _looks_like_table_row(line: str) -> bool:
    stripped = line.strip()
    return "|" in stripped and len(stripped.split("|")) >= 2


def _parse_table(lines: list[str]) -> TableBlock | None:
    if len(lines) < 2:
        return None

    rows = [_split_table_row(line) for line in lines]
    if not rows or any(not row for row in rows):
        return None

    header: list[str] | None
    separator_index = next(
        (index for index, row in enumerate(rows) if _is_separator_row(row)),
        None,
    )
    if separator_index is None:
        header = rows[0]
        data_rows = rows[1:]
    else:
        header_rows = rows[:separator_index]
        header = header_rows[0] if header_rows else None
        data_rows = rows[separator_index + 1 :]

    if not data_rows:
        return None

    column_count = len(header) if header is not None else len(data_rows[0])
    if column_count == 0:
        return None
    if any(len(row) != column_count for row in data_rows):
        return None
    if header is not None and len(header) != column_count:
        return None

    return TableBlock(headers=header, rows=data_rows)


def _split_table_row(line: str) -> list[str]:
    sentinel = "\x00"
    prepared = line.strip().replace("\\|", sentinel)
    if prepared.startswith("|"):
        prepared = prepared[1:]
    if prepared.endswith("|"):
        prepared = prepared[:-1]
    return [cell.strip().replace(sentinel, "|") for cell in prepared.split("|")]


def _is_separator_row(row: list[str]) -> bool:
    return bool(row) and all(_SEPARATOR_CELL_RE.match(cell.strip()) for cell in row)


__all__ = ["blocks_from_text"]
