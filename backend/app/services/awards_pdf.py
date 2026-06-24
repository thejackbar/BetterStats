"""Honour-board PDF → draft award rows, with no API tokens.

A club's honour board often arrives as a PDF exported from Word, Excel or Google
Sheets: a table with the season down the rows and an award (or office) per column.
This reads that grid straight from the PDF's text layer with pypdf — locally, no
model, no per-upload cost — and returns the cells as draft achievement rows for the
admin to review and import through the normal bulk-import screen.

It is deliberately literal. It transcribes the grid; it does not guess what each
column *means*. The column header becomes the achievement label and the admin sets
the Category in review (the importer validates Category, not the free-text
subcategory/achievement). Scanned or photographed boards carry no text layer, so this
returns available=False with a clear message rather than inventing data.

The shape mirrors the manual layout-offset method used to convert the first club's
board by hand: tokenise each row into cells, cluster the cell positions into columns,
read the header for labels and the first numeric/season column as the season.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Two columns in a layout-preserved PDF sit ~20+ characters apart; jitter within one
# column (centred names) stays under this. Used to cluster cell start positions.
_COL_GAP = 8

# A cell delimited by two-or-more spaces; single spaces stay inside the cell so
# "Owen Lawton" and "R. Di Vincenzo" survive intact.
_CELL_RE = re.compile(r"\S[\S ]*?(?=\s{2,}|$)")
_SEASON_RE = re.compile(r"(\d{4})\s*[/_-]\s*(\d{2,4})")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _cells(line: str) -> list[tuple[int, str]]:
    return [(m.start(), m.group().strip()) for m in _CELL_RE.finditer(line) if m.group().strip()]


def _season_from_cell(text: str) -> str | None:
    """Return a canonical 'YYYY/YY' (or 'YYYY') if the cell carries a season/year.

    Tolerates a leading row number ('1 1972/73') by reading the year pattern anywhere
    in the cell, not just the start.
    """
    if not text:
        return None
    m = _SEASON_RE.search(text)
    if m:
        start = int(m.group(1))
        return f"{start}/{str((start + 1) % 100).zfill(2)}"
    m = _YEAR_RE.search(text)
    if m:
        return m.group(0)
    return None


def _clean(text: str) -> str:
    s = re.sub(r"\s+", " ", text or "").strip()
    s = re.sub(r"\s+\.", ".", s)  # 'F .Rollin' -> 'F.Rollin' (a common extractor split)
    return s


def _cluster_anchors(offsets: list[int]) -> list[int]:
    """Group nearby cell start positions into column anchors (left edge of each)."""
    anchors: list[list[int]] = []
    for off in sorted(set(offsets)):
        if anchors and off - anchors[-1][-1] <= _COL_GAP:
            anchors[-1].append(off)
        else:
            anchors.append([off])
    return [grp[0] for grp in anchors]


def _assign(off: int, anchors: list[int]) -> int:
    return min(range(len(anchors)), key=lambda i: abs(off - anchors[i]))


def _parse_page(layout: str) -> dict | None:
    """Parse one layout-preserved page into {labels, season_idx, rows}.

    rows is a list of {season, cells: {anchor_idx: text}}. Returns None when the page
    has no detectable season column (so it isn't an honour-board grid we can read).
    """
    lines = [ln for ln in layout.split("\n") if ln.strip()]
    if len(lines) < 2:
        return None

    parsed = [(_cells(ln)) for ln in lines]
    all_offsets = [off for cells in parsed for off, _ in cells]
    if not all_offsets:
        return None
    anchors = _cluster_anchors(all_offsets)
    if len(anchors) < 2:
        return None

    # Place every cell in its column. A row's data is {anchor_idx: text}.
    grid: list[dict[int, str]] = []
    for cells in parsed:
        row: dict[int, str] = {}
        for off, text in cells:
            row[_assign(off, anchors)] = text
        grid.append(row)

    # The first row whose any cell parses as a season starts the data; the rows above
    # it are the header (often wrapped across two lines).
    first_data = None
    for i, row in enumerate(grid):
        if any(_season_from_cell(v) for v in row.values()):
            first_data = i
            break
    if first_data is None:
        return None

    header_rows = grid[:first_data]
    data_rows = grid[first_data:]

    labels: dict[int, str] = {}
    for idx in range(len(anchors)):
        parts = [hr[idx] for hr in header_rows if idx in hr and hr[idx]]
        labels[idx] = _clean(" ".join(parts))

    # The season column is the one that most data rows put their season in.
    from collections import Counter
    season_votes: Counter[int] = Counter()
    for row in data_rows:
        for idx, v in row.items():
            if _season_from_cell(v):
                season_votes[idx] += 1
                break
    if not season_votes:
        return None
    season_idx = season_votes.most_common(1)[0][0]

    # Drop pure index columns (1,2,3,… row numbers) — they aren't awards.
    drop: set[int] = {season_idx}
    for idx in range(len(anchors)):
        if idx == season_idx:
            continue
        vals = [row[idx] for row in data_rows if idx in row and row[idx]]
        if vals and all(re.fullmatch(r"\d{1,4}", v) for v in vals):
            drop.add(idx)

    rows = []
    for row in data_rows:
        season = None
        for idx, v in row.items():
            s = _season_from_cell(v)
            if s and idx == season_idx:
                season = s
                break
        if season is None:
            # fall back to any season-looking cell in the row
            season = next((_season_from_cell(v) for v in row.values() if _season_from_cell(v)), None)
        rows.append({"season": season, "cells": {idx: v for idx, v in row.items() if idx not in drop}})

    keep_labels = {idx: labels[idx] for idx in range(len(anchors)) if idx not in drop}
    return {"labels": keep_labels, "season_idx": season_idx, "rows": rows}


def extract_awards_grid(pdf_bytes: bytes) -> dict:
    """Read an honour-board PDF's text layer into draft award rows.

    Returns one of:
      {available: True, columns: [labels], rows: [{season, label, player_name}], ...}
      {available: False, message: "..."}  when the PDF has no text layer / isn't a grid.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        return {"available": False, "message": "PDF reading isn't installed on this server yet."}

    import io
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception:
        logger.exception("awards_pdf: could not open PDF")
        return {"available": False, "message": "That file couldn't be opened as a PDF."}

    columns: list[str] = []
    out_rows: list[dict] = []
    warnings: list[str] = []
    text_seen = False

    for page_no, page in enumerate(reader.pages, 1):
        try:
            layout = page.extract_text(extraction_mode="layout") or ""
        except Exception:
            # Older pypdf without layout mode — fall back to plain text (no columns).
            layout = page.extract_text() or ""
        if layout.strip():
            text_seen = True
        parsed = _parse_page(layout)
        if not parsed:
            continue
        # Column labels are shared across pages; keep first-seen order.
        for idx, label in parsed["labels"].items():
            if label and label not in columns:
                columns.append(label)
        for row in parsed["rows"]:
            season = row["season"]
            for idx, text in row["cells"].items():
                label = parsed["labels"].get(idx, "")
                name = _clean(text)
                if not name or not label:
                    continue
                out_rows.append({"season": season, "label": label, "player_name": name})

    if not text_seen:
        return {
            "available": False,
            "message": (
                "This PDF has no readable text — it looks scanned or photographed. "
                "Re-export it from the spreadsheet/document as a PDF, or use the CSV template."
            ),
        }
    if not out_rows:
        return {
            "available": False,
            "message": (
                "Couldn't find an honour-board table in this PDF. It works best on a grid "
                "with the season down the rows and an award per column. Try the CSV template."
            ),
        }

    return {
        "available": True,
        "columns": columns,
        "rows": out_rows,
        "row_count": len(out_rows),
        "page_count": len(reader.pages),
        "warnings": warnings,
    }
