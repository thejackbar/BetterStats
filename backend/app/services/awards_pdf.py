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


def _grid_from_layouts(layouts: list[str], source: str) -> dict | None:
    """Run the column parser over one-or-more page layouts and aggregate the rows.

    source is 'text' (read from a PDF text layer) or 'ocr' (rebuilt from OCR word
    boxes); the latter carries an accuracy warning. Returns None when no rows came out.
    """
    columns: list[str] = []
    out_rows: list[dict] = []
    for layout in layouts:
        parsed = _parse_page(layout)
        if not parsed:
            continue
        # Fall back to a generic column name when a header was blank or OCR missed it,
        # so the column's data still comes through for the admin to label in review
        # (an empty header used to silently drop the whole column).
        page_labels: dict[int, str] = {}
        for idx in parsed["labels"]:
            label = parsed["labels"][idx] or f"Column {idx + 1}"
            page_labels[idx] = label
            if label not in columns:
                columns.append(label)
        for row in parsed["rows"]:
            for idx, text in row["cells"].items():
                label = page_labels.get(idx) or f"Column {idx + 1}"
                name = _clean(text)
                if name:
                    out_rows.append({"season": row["season"], "label": label, "player_name": name})
    if not out_rows:
        return None
    warnings: list[str] = []
    if source == "ocr":
        warnings.append(
            "Read by OCR from a photo or scan, so check the names, seasons and columns "
            "before importing. A column whose heading couldn't be read is shown as "
            "'Column N' for you to label. For a clean import, export the board to PDF from "
            "Word, Excel or Google Sheets, or use the CSV template."
        )
    return {
        "available": True,
        "columns": columns,
        "rows": out_rows,
        "row_count": len(out_rows),
        "source": source,
        "warnings": warnings,
    }


# ── Local OCR (Tesseract) for scanned/photographed boards — still no API tokens ──

def _ocr_available() -> bool:
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _clean_token(text: str) -> str:
    """Strip OCR'd table rules from a word so grid lines don't corrupt the cell.

    A bordered table (the common honour-board look) makes Tesseract read the vertical
    rules as ``|`` and the horizontal ones as ``_``/dashes, often glued to a real word
    ("Camarda_|") or standing alone ("_|"). We turn internal pipes into spaces and trim
    rule characters off the ends, keeping real hyphens inside names (Westphal-Groves).
    A token left with no letter or digit is pure rule noise and is dropped.
    """
    t = (text or "").replace("|", " ")
    t = re.sub(r"\s+", " ", t).strip()
    t = t.strip("_│─—–•· ")  # box-draw, underscores, bullets, em/en dashes
    if not re.search(r"[A-Za-z0-9]", t):
        return ""
    return t


def _detect_columns(boxes: list[dict], min_gap: float) -> list[list[float]]:
    """Find table columns by projection profile.

    Merge every word's horizontal span [left, right]; a gutter wider than `min_gap`
    that no word crosses separates two columns. Unlike clustering word left-edges,
    this keeps a multi-word cell ("Steve Camarda") in one column because the words sit
    flush against each other, while still cutting on the real whitespace gutter before
    the next column. Works for bordered and borderless boards alike.
    """
    spans = sorted((w["left"], w["left"] + max(w.get("width", 1), 1)) for w in boxes)
    cols: list[list[float]] = []
    for lo, hi in spans:
        if cols and lo - cols[-1][1] < min_gap:
            cols[-1][1] = max(cols[-1][1], hi)
        else:
            cols.append([lo, hi])
    return cols


def _layout_from_words(words: list[dict]) -> str:
    """Rebuild an aligned monospace layout string from OCR word boxes.

    Detect columns by the whitespace gutters between them (`_detect_columns`), drop each
    word into the column its centre falls in, then lay the columns out at fixed character
    offsets with a clear gap. That guarantees the 2+ space column separation `_cells`
    needs regardless of OCR spacing jitter, and reuses the same downstream parser as the
    PDF text layer.
    """
    import statistics
    boxes = [w for w in words if _clean_token(w.get("text", ""))]
    if not boxes:
        return ""

    char_widths = [w["width"] / max(len(w["text"].strip()), 1) for w in boxes if w.get("width", 0) > 0]
    char_w = max(statistics.median(char_widths) if char_widths else 8.0, 1.0)
    # A column gutter is wider than a normal inter-word space (~0.3 char); 1.5 chars
    # cleanly clears word spacing without merging genuinely separate columns.
    cols = _detect_columns(boxes, char_w * 1.5)

    centres = [(lo + hi) / 2 for lo, hi in cols]

    def col_of(w: dict) -> int:
        c = w["left"] + max(w.get("width", 1), 1) / 2
        for i, (lo, hi) in enumerate(cols):
            if lo <= c <= hi:
                return i
        return min(range(len(centres)), key=lambda i: abs(c - centres[i]))

    lines: dict = {}
    for w in boxes:
        lines.setdefault(w["line"], []).append(w)
    ordered = sorted(lines.values(), key=lambda ws: min(x["top"] for x in ws))

    # First pass: place each line's words into columns; measure each column's width.
    rows_cells: list[dict[int, str]] = []
    colw = [0] * len(cols)
    for ws in ordered:
        cells: dict[int, str] = {}
        for w in sorted(ws, key=lambda x: x["left"]):
            tok = _clean_token(w.get("text", ""))
            if not tok:
                continue
            ci = col_of(w)
            cells[ci] = f"{cells[ci]} {tok}" if ci in cells else tok
        if not cells:
            continue
        rows_cells.append(cells)
        for ci, tok in cells.items():
            colw[ci] = max(colw[ci], len(tok))

    # Second pass: emit columns at consistent start offsets so the grid stays aligned.
    GAP = 3
    starts, acc = [0] * len(cols), 0
    for ci in range(len(cols)):
        starts[ci] = acc
        acc += colw[ci] + GAP

    out_lines = []
    for cells in rows_cells:
        buf = ""
        for ci in sorted(cells):
            if starts[ci] > len(buf):
                buf += " " * (starts[ci] - len(buf))
            elif buf and not buf.endswith("  "):
                buf += "  "
            buf += cells[ci]
        out_lines.append(buf)
    return "\n".join(out_lines)


def _ocr_image_to_layout(image) -> str:
    import pytesseract
    from pytesseract import Output
    data = pytesseract.image_to_data(image, output_type=Output.DICT)
    words = []
    for i in range(len(data["text"])):
        text = (data["text"][i] or "").strip()
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1
        if not text or conf < 0:
            continue
        words.append({
            "text": text,
            "left": data["left"][i],
            "top": data["top"][i],
            "width": data["width"][i],
            "line": (data["block_num"][i], data["par_num"][i], data["line_num"][i]),
        })
    return _layout_from_words(words)


def _pdf_to_images(pdf_bytes: bytes) -> list:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(pdf_bytes)
    images = []
    try:
        for i in range(len(pdf)):
            page = pdf[i]
            images.append(page.render(scale=3).to_pil())  # ~216 DPI, good for OCR
    finally:
        pass
    return images


def extract_awards_grid(pdf_bytes: bytes) -> dict:
    """Read an honour-board PDF into draft award rows.

    Reads the text layer first (free, no model). If the PDF is scanned (no text layer)
    and local OCR is installed, falls back to OCR. Returns one of:
      {available: True, columns, rows, source, ...}
      {available: False, message}  when there is no grid to read.
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

    layouts: list[str] = []
    text_seen = False
    for page in reader.pages:
        try:
            layout = page.extract_text(extraction_mode="layout") or ""
        except Exception:
            layout = page.extract_text() or ""  # older pypdf without layout mode
        if layout.strip():
            text_seen = True
        layouts.append(layout)

    if text_seen:
        grid = _grid_from_layouts(layouts, "text")
        if grid:
            grid["page_count"] = len(reader.pages)
            return grid

    # No usable text layer (a scanned PDF): try local OCR if it's installed.
    if _ocr_available():
        try:
            images = _pdf_to_images(pdf_bytes)
            ocr_layouts = [_ocr_image_to_layout(im) for im in images]
        except Exception:
            logger.exception("awards_pdf: OCR rasterise/read failed")
            ocr_layouts = []
        grid = _grid_from_layouts(ocr_layouts, "ocr")
        if grid:
            grid["page_count"] = len(reader.pages)
            return grid

    if not text_seen:
        if not _ocr_available():
            return {"available": False, "message": (
                "This PDF has no readable text, so it looks scanned or photographed, and OCR "
                "isn't enabled on this server. Re-export it from the document, or use the CSV template."
            )}
        return {"available": False, "message": (
            "This looks scanned and the OCR couldn't find an honour-board table in it. "
            "Try a sharper, straight-on scan, or use the CSV template."
        )}
    return {"available": False, "message": (
        "Couldn't find an honour-board table in this PDF. It works best on a grid with the "
        "season down the rows and an award per column. Try the CSV template."
    )}


def extract_awards_image(image_bytes: bytes) -> dict:
    """Read a photographed/scanned honour-board image into draft award rows via OCR."""
    if not _ocr_available():
        return {"available": False, "message": (
            "Reading photos isn't enabled on this server. Upload a PDF exported from the "
            "document, or use the CSV template."
        )}
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes))
        layout = _ocr_image_to_layout(img)
    except Exception:
        logger.exception("awards_pdf: image OCR failed")
        return {"available": False, "message": (
            "That image couldn't be read. Try a sharper, straight-on photo, or use the CSV template."
        )}
    grid = _grid_from_layouts([layout], "ocr")
    if grid:
        grid["page_count"] = 1
        return grid
    return {"available": False, "message": (
        "Couldn't find an honour-board table in that photo. It works best on a clear, "
        "straight-on shot of a grid with the season down the rows and an award per column."
    )}
