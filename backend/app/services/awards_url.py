"""Honour board from a web page → draft award rows, with no API tokens.

Many clubs publish their honour rolls as an HTML table on the club website
(WordPress, Squarespace, a static page). This fetches the page server-side and
reads its ``<table>`` elements into the same draft-row shape as the PDF/photo
reader (:mod:`app.services.awards_pdf`), so the admin reviews and imports them
through the same screen. Local only: no model, no per-upload cost.

It reads the raw HTML the server returns; it does not run the page's JavaScript.
A board drawn by a client-side widget (a live-scores embed, a JS grid) carries no
table in the HTML, so the reader says so rather than inventing data.

Only public ``http(s)`` URLs are read, and every hop is checked against
internal/private addresses first so the fetch can't be pointed at the box's own
network (SSRF). It transcribes the table; it does not guess what each column
*means* — the column header becomes the achievement label and the admin sets the
Category in review, exactly like the PDF reader.
"""
from __future__ import annotations

import ipaddress
import logging
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from app.services.awards_pdf import _clean, _season_from_cell

logger = logging.getLogger(__name__)

MAX_BYTES = 4 * 1024 * 1024        # stop reading a page past this — an honour table is tiny
MAX_REDIRECTS = 4
FETCH_TIMEOUT = 15.0
_UA = "BetterCricketAwardsBot/1.0 (+https://betterat.cricket)"

_INT_RE = re.compile(r"^\d{1,4}$")


# ── SSRF guard: only reach public http(s) hosts ────────────────────────────────

def _host_is_public(host: str) -> bool:
    """True only if every address `host` resolves to is a public, routable IP.

    Blocks loopback/private/link-local/reserved/multicast so a crafted URL can't
    make the server read its own metadata endpoint or a neighbour on the box.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr.split("%")[0])  # strip any zone id
        except ValueError:
            return False
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            return False
    return True


def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Enter a web address starting with http:// or https://")
    if not parsed.hostname:
        raise ValueError("That web address doesn't look right.")
    if not _host_is_public(parsed.hostname):
        raise ValueError("That address points to a private or internal host, so it can't be read.")
    return url


# ── HTML → tables ──────────────────────────────────────────────────────────────

class _TableExtractor(HTMLParser):
    """Pull every ``<table>`` into a grid of rows, each row a list of ``(is_header, text)``.

    Handles nested tables with a stack and joins text across inline tags inside a
    cell (``<td><a>Ross Leipold</a></td>`` reads as one cell), turning ``<br>`` into
    a space so a two-line cell doesn't glue together.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[tuple[bool, str]]]] = []
        self._stack: list[list[list[tuple[bool, str]]]] = []  # open tables (nesting)
        self._cell: list[str] | None = None
        self._cell_is_header = False
        self._skip = 0  # depth inside <script>/<style>

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
            return
        if self._skip:
            return
        if tag == "table":
            table: list[list[tuple[bool, str]]] = []
            self.tables.append(table)
            self._stack.append(table)
        elif tag == "tr" and self._stack:
            self._stack[-1].append([])
        elif tag in ("td", "th") and self._stack and self._stack[-1]:
            self._cell = []
            self._cell_is_header = tag == "th"
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_startendtag(self, tag, attrs):
        if tag == "br" and self._cell is not None and not self._skip:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if tag in ("td", "th") and self._cell is not None and self._stack and self._stack[-1]:
            self._stack[-1][-1].append((self._cell_is_header, _clean("".join(self._cell))))
            self._cell = None
        elif tag == "table" and self._stack:
            self._close_cell()
            self._stack.pop()

    def _close_cell(self):
        if self._cell is not None and self._stack and self._stack[-1]:
            self._stack[-1][-1].append((self._cell_is_header, _clean("".join(self._cell))))
            self._cell = None

    def handle_data(self, data):
        if not self._skip and self._cell is not None:
            self._cell.append(data)


def _table_to_rows(table: list[list[tuple[bool, str]]], labels_out: list[str]) -> list[dict]:
    """Turn one parsed table into ``{season, label, player_name}`` draft rows.

    Finds the season column (most seasony), forward-fills a blank season down the
    rows (clubs leave the season cell empty after the first entry of each season),
    drops the season and any pure row-number/index column, and emits one row per
    remaining non-empty cell keyed by its column header.
    """
    grid = [r for r in table if r]
    if len(grid) < 2:
        return []
    ncols = max(len(r) for r in grid)
    if ncols < 2:
        return []

    first = grid[0]
    has_th = any(is_h for is_h, _ in first)
    first_is_data = (not has_th) and any(_season_from_cell(t) for _, t in first)
    if has_th or not first_is_data:
        header = [t for _, t in first]
        data = grid[1:]
    else:
        header = []
        data = grid

    def cell(row, i):
        return row[i][1] if i < len(row) else ""

    labels = [(header[i] if i < len(header) and header[i] else f"Column {i + 1}") for i in range(ncols)]

    # Season column: the one whose data cells most often parse as a season/year.
    votes = [0] * ncols
    for row in data:
        for i in range(ncols):
            if _season_from_cell(cell(row, i)):
                votes[i] += 1
    season_idx = max(range(ncols), key=lambda i: votes[i]) if any(votes) else None

    drop = set()
    if season_idx is not None:
        drop.add(season_idx)
    for i in range(ncols):
        if i == season_idx:
            continue
        vals = [cell(row, i).strip() for row in data if cell(row, i).strip()]
        if vals and all(_INT_RE.match(v) for v in vals):
            drop.add(i)  # a bare row-number / sequential index column

    rows: list[dict] = []
    carried = None
    for row in data:
        season = None
        if season_idx is not None:
            season = _season_from_cell(cell(row, season_idx))
        if season is None:
            season = next((_season_from_cell(cell(row, i)) for i in range(ncols)
                           if i != season_idx and _season_from_cell(cell(row, i))), None)
        if season:
            carried = season
        else:
            season = carried  # forward-fill: blank season cell inherits the group's season
        for i in range(ncols):
            if i in drop:
                continue
            name = cell(row, i).strip()
            if not name:
                continue
            label = labels[i]
            if label not in labels_out:
                labels_out.append(label)
            rows.append({"season": season, "label": label, "player_name": name})
    return rows


def _rows_from_html(html: str) -> dict:
    parser = _TableExtractor()
    try:
        parser.feed(html)
    except Exception:
        logger.exception("awards_url: HTML parse failed")
    tables = [t for t in parser.tables if len([r for r in t if r]) >= 2]
    if not tables:
        return {"available": False, "message": (
            "No table was found on that page. The reader needs a real HTML table (season, "
            "award and player in columns). If the board is an image, a PDF, or drawn by a "
            "script, save it and use the PDF/photo reader or the CSV template instead."
        )}

    multi = len(tables) > 1
    columns: list[str] = []
    out_rows: list[dict] = []
    for n, table in enumerate(tables, 1):
        labels: list[str] = []
        table_rows = _table_to_rows(table, labels)
        if not table_rows:
            continue
        prefix = f"Table {n}: " if multi else ""
        for r in table_rows:
            label = f"{prefix}{r['label']}"
            if label not in columns:
                columns.append(label)
            out_rows.append({"season": r["season"], "label": label, "player_name": r["player_name"]})

    if not out_rows:
        return {"available": False, "message": (
            "Found a table but couldn't read any award rows from it. It works best on a grid "
            "with a season column and an award/player column. Try the CSV template."
        )}

    warnings = [
        "Read straight from the web page's HTML tables. Check the seasons and column "
        "categories before importing. A season left blank inherits the one above it, and "
        "any plain number column is treated as a row index and dropped."
    ]
    return {
        "available": True,
        "columns": columns,
        "rows": out_rows,
        "row_count": len(out_rows),
        "source": "url",
        "warnings": warnings,
    }


async def parse_awards_url(url: str) -> dict:
    """Fetch a public web page and read its HTML tables into draft award rows.

    Returns ``{available: True, columns, rows, source, ...}`` on success, or
    ``{available: False, message}`` when there's nothing readable. Raises
    ``ValueError`` for a bad or private URL (the caller maps it to a 400).
    """
    import httpx

    _validate_url(url)

    async with httpx.AsyncClient(
        follow_redirects=False, timeout=FETCH_TIMEOUT,
        headers={"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml"},
    ) as client:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            _validate_url(current)  # re-check every hop, incl. after a redirect
            async with client.stream("GET", current) as resp:
                if resp.is_redirect and "location" in resp.headers:
                    current = urljoin(current, resp.headers["location"])
                    continue
                resp.raise_for_status()
                ctype = resp.headers.get("content-type", "")
                if ctype and "html" not in ctype.lower() and "xml" not in ctype.lower():
                    return {"available": False, "message": (
                        f"That address returned {ctype.split(';')[0] or 'a non-web-page'}, not a web page. "
                        "Paste the link to the honour-board page itself."
                    )}
                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    chunks.append(chunk)
                    total += len(chunk)
                    if total >= MAX_BYTES:
                        break  # an honour table is tiny; don't pull an unbounded body
                raw = b"".join(chunks)[:MAX_BYTES]
                html = raw.decode(resp.encoding or "utf-8", errors="replace")
                return _rows_from_html(html)

    return {"available": False, "message": "That address redirected too many times to read."}
