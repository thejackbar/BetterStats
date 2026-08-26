"""Build the BetterCricket flyer as an editable Word document.

Rebuilds the two-page PDF flyer as real Word content -- paragraphs, runs and
tables -- so the copy can be edited and the file exported back to PDF.

The dark page colour is painted TWICE on purpose: as the document background
(what Word shows on screen, and what LibreOffice exports) and as a full-page
VML rectangle anchored behind the text in the page header (what Word actually
prints, since Word leaves the document background out of print and PDF export
unless the reader has switched that option on).

    python3 docs/flyer/build_flyer_docx.py [out.docx]
"""

import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Pt, RGBColor

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------- palette ---
BG      = "0B1220"   # page
CARD    = "101828"   # card fill
TINT    = "0A1D26"   # accent-tinted card fill
HAIR    = "1D2331"   # borders and rules
ACCENT  = "16C784"
BRIGHT  = "E6E8EF"   # headings
BODY    = "A3AAB9"   # body copy
DIM     = "8A90A2"   # captions
FAINT   = "5F6577"   # small print
INK     = "06231A"   # text on an accent fill

FONT = "Arial"

# Page geometry, in points, taken from the PDF.
PAGE_W, PAGE_H = 595.92, 842.88
MARGIN = 42.75
CONTENT = PAGE_W - 2 * MARGIN          # 510.4pt


# ------------------------------------------------------------- xml helpers --
# WordprocessingML property elements are a strict sequence, and both Word and
# LibreOffice refuse a file that puts them in the wrong order, so every insert
# goes through _ordered_insert with its element's own sequence.
TBL_PR_ORDER = (
    "tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize",
    "tblStyleColBandSize", "tblW", "tblJc", "tblCellSpacing", "tblInd",
    "tblBorders", "shd", "tblLayout", "tblCellMar", "tblLook",
)
TC_PR_ORDER = (
    "cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd",
    "noWrap", "tcMar", "textDirection", "tcFitText", "vAlign", "hideMark",
)
P_PR_ORDER = (
    "pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr",
    "widowControl", "numPr", "suppressLineNumbers", "pBdr", "shd", "tabs",
    "suppressAutoHyphens", "kinsoku", "wordWrap", "overflowPunct",
    "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi", "adjustRightInd",
    "snapToGrid", "spacing", "ind", "contextualSpacing", "mirrorIndents",
    "suppressOverlap", "jc", "textDirection", "textAlignment",
    "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr", "sectPr",
)
R_PR_ORDER = (
    "rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike",
    "dstrike", "outline", "shadow", "emboss", "imprint", "noProof",
    "snapToGrid", "vanish", "webHidden", "color", "spacing", "w", "kern",
    "position", "sz", "szCs", "highlight", "u", "effect", "bdr", "shd",
    "fitText", "vertAlign", "rtl", "cs", "em", "lang",
)


def _el(tag, **attrs):
    e = OxmlElement(tag)
    for k, v in attrs.items():
        e.set(qn("w:" + k), str(v))
    return e


def _local(tag):
    return tag.split("}")[-1]


def _ordered_insert(parent, element, order):
    """Insert element into parent at its schema position, replacing any twin."""
    name = _local(element.tag)
    for existing in parent.findall(qn("w:" + name)):
        parent.remove(existing)
    rank = order.index(name)
    for child in parent:
        child_name = _local(child.tag)
        if child_name not in order or order.index(child_name) > rank:
            child.addprevious(element)
            return element
    parent.append(element)
    return element


def shade(props, fill, order):
    _ordered_insert(props, _el("w:shd", val="clear", color="auto", fill=fill), order)


def cell_bg(cell, fill):
    shade(cell._tc.get_or_add_tcPr(), fill, TC_PR_ORDER)


def cell_borders(cell, color=HAIR, size=6, sides=("top", "left", "bottom", "right")):
    """size is in eighths of a point (6 = 0.75pt, matching the PDF)."""
    borders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        borders.append(
            _el("w:" + side, val="single" if side in sides else "nil",
                sz=size if side in sides else 0, space=0, color=color)
        )
    _ordered_insert(cell._tc.get_or_add_tcPr(), borders, TC_PR_ORDER)


def cell_pad(cell, top=6, left=8, bottom=6, right=8):
    """Padding in points."""
    mar = OxmlElement("w:tcMar")
    for side, val in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        mar.append(_el("w:" + side, w=int(val * 20), type="dxa"))
    _ordered_insert(cell._tc.get_or_add_tcPr(), mar, TC_PR_ORDER)


def cell_width(cell, pts):
    _ordered_insert(cell._tc.get_or_add_tcPr(),
                    _el("w:tcW", w=int(pts * 20), type="dxa"), TC_PR_ORDER)


def drop(paragraph):
    paragraph._p.getparent().remove(paragraph._p)


def clear(container):
    """Empty a cell of the placeholder paragraph the grid seeded it with."""
    for paragraph in list(container.paragraphs):
        drop(paragraph)
    return container


# ------------------------------------------------------------ text helpers --
def run(paragraph, text, size=7.4, color=BODY, bold=False, italic=False,
        track=None, highlight=None):
    r = paragraph.add_run(text)
    r.font.name = FONT
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.italic = italic
    r.font.color.rgb = RGBColor.from_string(color)
    rPr = r._r.get_or_add_rPr()
    # East-Asian / complex-script font names, so Word does not substitute.
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = _ordered_insert(rPr, _el("w:rFonts"), R_PR_ORDER)
    for attr in ("ascii", "hAnsi", "cs", "eastAsia"):
        rFonts.set(qn("w:" + attr), FONT)
    if track:                                   # letter spacing, in points
        _ordered_insert(rPr, _el("w:spacing", val=int(track * 20)), R_PR_ORDER)
    if highlight:                               # run-level background fill
        shade(rPr, highlight, R_PR_ORDER)
    return r


def para(container, space_before=0, space_after=0, line=None, align=None,
         keep_with_next=False, page_break=False):
    p = container.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(space_before)
    pf.space_after = Pt(space_after)
    if line:
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf.line_spacing = Pt(line)
    if align is not None:
        pf.alignment = align
    pf.keep_with_next = keep_with_next
    pf.page_break_before = page_break
    return p


def text_para(container, text, size=7.4, color=BODY, bold=False, italic=False,
              line=11.2, space_before=0, space_after=0, align=None, track=None,
              keep_with_next=False):
    p = para(container, space_before, space_after, line, align, keep_with_next)
    run(p, text, size, color, bold, italic, track)
    return p


def rule(container, color=HAIR, space_before=6, space_after=6, size=6):
    """A hairline rule drawn as a paragraph bottom border."""
    p = para(container, space_before, space_after, line=1)
    borders = OxmlElement("w:pBdr")
    borders.append(_el("w:bottom", val="single", sz=size, space=1, color=color))
    _ordered_insert(p._p.get_or_add_pPr(), borders, P_PR_ORDER)
    run(p, "", 1)
    return p


# ---------------------------------------------------------------- tables ----
def grid(doc, widths, gap, rows=1):
    """A fixed-layout, borderless table: content columns separated by spacers.

    Returns the list of content cells.
    """
    n = len(widths)
    cols = []
    for i, w in enumerate(widths):
        cols.append(w)
        if i < n - 1:
            cols.append(gap)

    table = doc.add_table(rows=rows, cols=len(cols))
    table.autofit = False

    # LibreOffice and Word both size a fixed-layout table from w:tblGrid, not
    # from the per-cell widths, so the grid has to be rewritten or the columns
    # come out evenly divided.
    grid_el = table._tbl.find(qn("w:tblGrid"))
    if grid_el is not None:
        table._tbl.remove(grid_el)
    grid_el = OxmlElement("w:tblGrid")
    for w in cols:
        grid_el.append(_el("w:gridCol", w=int(w * 20)))
    table._tbl.insert(list(table._tbl).index(table._tbl.tblPr) + 1, grid_el)

    tblPr = table._tbl.tblPr
    _ordered_insert(tblPr, _el("w:tblW", w=int(sum(cols) * 20), type="dxa"), TBL_PR_ORDER)
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        borders.append(_el("w:" + side, val="nil"))
    _ordered_insert(tblPr, borders, TBL_PR_ORDER)
    _ordered_insert(tblPr, _el("w:tblInd", w=0, type="dxa"), TBL_PR_ORDER)
    _ordered_insert(tblPr, _el("w:tblLayout", type="fixed"), TBL_PR_ORDER)
    mar = OxmlElement("w:tblCellMar")
    for side in ("top", "left", "bottom", "right"):
        mar.append(_el("w:" + side, w=0, type="dxa"))
    _ordered_insert(tblPr, mar, TBL_PR_ORDER)

    out = []
    for row in table.rows:
        for cell, w in zip(row.cells, cols):
            cell_width(cell, w)
            cell_pad(cell, 0, 0, 0, 0)
            pf = cell.paragraphs[0].paragraph_format
            pf.space_after = Pt(0)
            pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
            pf.line_spacing = Pt(1)
            run(cell.paragraphs[0], "", 1)
        out.append([row.cells[i * 2] for i in range(n)])
    return out[0] if rows == 1 else out


def card(cell, fill=CARD, border=HAIR, pad=(7, 9, 7, 9), border_sides=("top", "left", "bottom", "right"), border_size=6):
    cell_bg(cell, fill)
    cell_borders(cell, border, border_size, border_sides)
    cell_pad(cell, *pad)
    clear(cell)   # drop the placeholder paragraph the grid seeded
    return cell


def spacer(doc, height=6):
    para(doc, 0, 0, line=height)


# ------------------------------------------------------- page background ----
def paint_background(doc):
    """Dark page colour: document background + a printable header rectangle."""
    body = doc.element.body
    background = OxmlElement("w:background")
    background.set(qn("w:color"), BG)
    doc.element.insert(0, background)

    settings = doc.settings.element
    display = OxmlElement("w:displayBackgroundShape")
    settings.append(display)

    for section in doc.sections:
        header = section.header
        header.is_linked_to_previous = False
        p = header.paragraphs[0]
        pf = p.paragraph_format
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf.line_spacing = Pt(1)
        r = p.add_run()
        r.font.size = Pt(1)
        style = (
            "position:absolute;margin-left:0;margin-top:0;"
            f"width:{PAGE_W}pt;height:{PAGE_H}pt;z-index:-251658752;"
            "mso-position-horizontal:left;mso-position-horizontal-relative:page;"
            "mso-position-vertical:top;mso-position-vertical-relative:page"
        )
        pict = parse_xml(
            f'<w:pict {nsdecls("w")} xmlns:v="urn:schemas-microsoft-com:vml">'
            f'<v:rect style="{style}" fillcolor="#{BG}" stroked="f"/>'
            "</w:pict>"
        )
        r._r.append(pict)


def add_footer(doc):
    for section in doc.sections:
        footer = section.footer
        footer.is_linked_to_previous = False
        p = footer.paragraphs[0]
        pf = p.paragraph_format
        pf.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)

        def field(instr):
            r = p.add_run()
            r.font.name = FONT
            r.font.size = Pt(6)
            r.font.color.rgb = RGBColor.from_string("4D5364")
            begin = OxmlElement("w:fldChar")
            begin.set(qn("w:fldCharType"), "begin")
            instr_el = OxmlElement("w:instrText")
            instr_el.set(qn("xml:space"), "preserve")
            instr_el.text = instr
            end = OxmlElement("w:fldChar")
            end.set(qn("w:fldCharType"), "end")
            r._r.append(begin)
            r._r.append(instr_el)
            r._r.append(end)

        field(" PAGE ")
        run(p, " / ", 6, "4D5364")
        field(" NUMPAGES ")


# ------------------------------------------------------------- components ---
def masthead(doc, tagline, contact, page_break=False):
    if page_break:
        # The break sits on its own paragraph rather than inside the table:
        # page-break-before on a paragraph in a cell leaves a blank page behind.
        para(doc, 0, 0, line=1, page_break=True)

    cells = grid(doc, [250, CONTENT - 250 - 8], 8)
    left, right = cells

    clear(left)
    # The exact line has to clear the logo, or its top is clipped.
    p = para(left, 0, 0, line=24)
    logo = HERE / "logo.png"
    if logo.exists():
        p.add_run().add_picture(str(logo), height=Pt(22))
    run(p, "  ", 15.8, BRIGHT)
    run(p, "Better", 15.8, BRIGHT, bold=True)
    run(p, "Cricket", 15.8, ACCENT, bold=True)

    clear(right)
    text_para(right, tagline, 7.6, DIM, line=10, align=WD_ALIGN_PARAGRAPH.RIGHT)
    text_para(right, contact, 7.9, ACCENT, bold=True, line=11,
              align=WD_ALIGN_PARAGRAPH.RIGHT)

    rule(doc, HAIR, space_before=8, space_after=0)


def eyebrow(doc, text, space_before=14):
    text_para(doc, text, 7.4, ACCENT, bold=True, line=10,
              space_before=space_before, space_after=2, track=1.1,
              keep_with_next=True)


# ------------------------------------------------------------------ page 1 --
def page_one(doc):
    masthead(doc, "The platform Australian cricket clubs run on", "betterat.cricket")

    p = para(doc, space_before=14, space_after=8, line=30)
    run(p, "We do cricket", 26.2, BRIGHT, bold=True)
    run(p, "… ", 26.2, DIM, bold=True)
    run(p, "Better.", 26.2, ACCENT, bold=True)

    p = para(doc, space_after=12, line=14.2)
    run(p, "One platform for an Australian cricket club, built so the season takes "
           "less volunteer time to run. ", 8.9, BODY)
    run(p, "Your match history arrives on its own and keeps itself current",
        8.9, BRIGHT, bold=True)
    run(p, ", so the stats, records, ladders, milestones and the season yearbook all "
           "update without anyone typing a scorecard. On top of that sit the parts "
           "that run the rest of the club: availability, selection and best-player "
           "votes, match-day posts, fees and member emails, and analytics most clubs "
           "never get near.", 8.9, BODY)

    # Four stat cards.
    stats = [
        ("Under 1 hr", "From first sync to a live, branded club site"),
        ("Overnight", "Each round's results are in by Sunday morning"),
        ("Decades", "Of history brought in, with no migration fee"),
        ("14 days", "Free trial of every module, no card needed"),
    ]
    cells = grid(doc, [122.3] * 4, 6.7)
    for cell, (head, note) in zip(cells, stats):
        card(cell, pad=(7, 8, 7, 8))
        text_para(cell, head, 11.6, ACCENT, bold=True, line=13, space_after=3)
        text_para(cell, note, 6.9, DIM, line=9)

    spacer(doc, 10)

    # Accent-tinted band.
    band = card(grid(doc, [CONTENT], 0)[0], fill=TINT, border=ACCENT,
                pad=(8, 10, 8, 10), border_sides=("left",), border_size=11)
    p = para(band, 0, 0, line=11.5)
    run(p, "The weekend scores itself.  ", 8.4, ACCENT, bold=True)
    run(p, "BetterCricket pulls each round overnight, then updates every average, "
           "record, ladder, leaderboard, milestone and player profile behind it. "
           "No re-keying a scorecard, and nothing waiting on the one volunteer who "
           "knows how the spreadsheet works.", 7.4, BODY)

    eyebrow(doc, "WHAT THE CLUB GETS")
    text_para(doc, "Every club starts with BetterStats. Add only the modules you want, "
                   "and add them whenever you like.", 8.0, DIM, line=11, space_after=6,
              keep_with_next=True)

    # BetterStats, the included module.
    stats_card = card(grid(doc, [CONTENT], 0)[0], fill=TINT, border=ACCENT, pad=(8, 10, 8, 10))
    head = grid(stats_card, [330, CONTENT - 20 - 330 - 8], 8)
    clear(head[0])
    p = para(head[0], 0, 0, line=12)
    run(p, "BetterStats", 9.1, BRIGHT, bold=True)
    run(p, "   ", 9.1, BRIGHT)
    run(p, "  INCLUDED  ", 6.8, INK, bold=True, track=0.6, highlight=ACCENT)
    clear(head[1])
    text_para(head[1], "$399 / year", 9.1, ACCENT, bold=True, line=12,
              align=WD_ALIGN_PARAGRAPH.RIGHT)
    text_para(stats_card, "Every batting, bowling and fielding stat your club has, "
              "turned into a public, club-branded website: a profile for every player, "
              "leaderboards and all-time records, partnership records, the honour board, "
              "and scorecards going back as far as the records do. Filter any of it by "
              "grade type (men's, women's, juniors, masters) and match type (Two Day, "
              "One Day, T20). The season yearbook writes itself, and Club Room Mode puts "
              "the lot on the TV at the clubhouse.", 7.4, BODY, line=11.2, space_before=4)

    spacer(doc, 6)

    modules = [
        ("BetterSelect", "$149 / yr",
         "Players set their own availability from a link, with no app and no account. "
         "Name the XI on a numbered batting order with each player's form beside them, "
         "run Thursday nets off the rotation timer, and collect 3-2-1 votes through that "
         "same link. The count keeps itself: podium, race chart, and a presentation mode "
         "for awards night."),
        ("BetterSocials", "$149 / yr",
         "A full-screen post designer of the kind your socials volunteer already knows: "
         "blocks dragged around a canvas, layers, undo and redo, carousels and a club "
         "photo library. The difference is the data. Drop in a match link, or a live "
         "block for fixtures, results or a player's career, and the card fills itself in "
         "your colours. Plus a real club website."),
        ("BetterAdmin", "$149 / yr",
         "One directory for everyone at the club, fed from your player list rather than "
         "a CSV somebody re-imports. Match fees and memberships settle themselves as "
         "payments land, bulk email goes to that same list, and there's stock and "
         "canteen, the volunteer roster with hours logged for grants, and committee "
         "meetings with minutes and motions."),
        ("BetterIQ", "$249 / yr",
         "An opposition dossier for any upcoming opponent, built from your own scorecards "
         "without anyone requesting it: danger players named before the toss and a "
         "printable captain's cheat sheet. Plus a best-available XI, player trends and "
         "milestone forecasts, and team analysis on partnerships, collapses and par "
         "scores."),
    ]
    # Three rows: cards, a 6pt spacer, cards. A shaded cell fills its padding,
    # so the gap between card rows has to be a row of its own.
    module_rows = grid(doc, [251.3, 252], 6, rows=3)
    for c in module_rows[1]:
        cell_pad(c, 0, 0, 6, 0)
    for pair, cells in zip((modules[:2], modules[2:]),
                           (module_rows[0], module_rows[2])):
        for cell, (name, price, body) in zip(cells, pair):
            card(cell, pad=(7, 9, 7, 9))
            inner = grid(cell, [150, 251.3 - 18 - 150 - 6], 6)
            clear(inner[0])
            text_para(inner[0], name, 8.5, BRIGHT, bold=True, line=11)
            clear(inner[1])
            text_para(inner[1], price, 8.1, ACCENT, bold=True, line=11,
                      align=WD_ALIGN_PARAGRAPH.RIGHT)
            text_para(cell, body, 7.4, BODY, line=11.2, space_before=2)

    spacer(doc, 6)

    eyebrow(doc, "THE JOBS IT TAKES OFF YOUR VOLUNTEERS", space_before=8)
    text_para(doc, "Every one of these is a real thing a club secretary told us they "
                   "were spending weekends on.", 8.0, DIM, line=11, space_after=6,
              keep_with_next=True)

    jobs = [
        ("01", "The same player, recorded three times",
         "Split careers are normal, and BetterCricket goes looking for them rather than "
         "waiting to be told. It flags the pairs, down to \"Brad K Mant\" against "
         "\"Bradley Mant\". One click merges them, keeps every innings, spell, catch and "
         "partnership, and can be undone."),
        ("02", "Fifty years in a filing cabinet",
         "Spreadsheets, CSVs, PDFs and photographed scorebook pages all go in. The reader "
         "lifts the figures off the page, reconciles them against the live feed and lands "
         "one career per player. No separate migration fee, no cap on seasons."),
        ("03", "Under-14 seasons flattering senior averages",
         "Juniors, women's and masters are each their own thing, and so are Two Day, One "
         "Day and T20. Every stats screen filters on both, so a senior average isn't "
         "padded by Under-14s and a T20 record only counts T20s."),
        ("04", "Five tools and five bills",
         "A spreadsheet, a site builder, Canva, Mailchimp and a group chat, none of which "
         "talk to each other. One subscription and one match feed behind the lot, so the "
         "season only gets entered once."),
        ("05", "Saturday's \"who's in?\" scramble",
         "Availability comes in from the players themselves, on a link they open on their "
         "phone with nothing to install. Selection already knows their form, grade and "
         "skills, and it warns you about a side with no keeper or a short attack."),
        ("06", "The best-player count on an envelope",
         "3-2-1 votes arrive through the link players already use, and the ladder adds "
         "itself up round by round. Chase the stragglers with one button, then reveal the "
         "season on the screen at the awards night."),
    ]
    job_rows = grid(doc, [251, 251], 8, rows=3)
    for pair, cells in zip((jobs[0:2], jobs[2:4], jobs[4:6]), job_rows):
        for cell, (num, title, body) in zip(cells, pair):
            cell_pad(cell, 0, 0, 5, 0)
            clear(cell)
            inner = grid(cell, [16, 235], 0)
            clear(inner[0])
            text_para(inner[0], num, 7.4, ACCENT, bold=True, line=11)
            clear(inner[1])
            text_para(inner[1], title, 7.9, BRIGHT, bold=True, line=11)
            text_para(inner[1], body, 7.3, BODY, line=10.5, space_before=2)


# ------------------------------------------------------------------ page 2 --
def page_two(doc):
    masthead(doc, "Pricing, setup and the questions clubs ask",
             "support@bettersports.com.au", page_break=True)

    eyebrow(doc, "WHAT IT COSTS", space_before=8)
    text_para(doc, "An annual licence, billed once a year and paid by card through "
                   "Stripe. Flat per club: one team or fifty, juniors and seniors, "
                   "men's and women's, the price is the same.", 8.0, DIM, line=11.2,
              space_after=6, keep_with_next=True)

    cells = grid(doc, [295.5, 204.8], 9.4)

    # Left: the price list.
    left = card(cells[0], pad=(9, 10, 9, 10))
    text_para(left, "Build your own subscription", 9.1, BRIGHT, bold=True, line=12,
              space_after=6)

    rows = [
        ("BetterStats", " · included in every plan", "$399", BRIGHT),
        ("BetterSelect", "", "$149", BRIGHT),
        ("BetterSocials", "", "$149", BRIGHT),
        ("BetterAdmin", "", "$149", BRIGHT),
        ("BetterIQ", "", "$249", BRIGHT),
        ("BetterFantasyCricket", " · optional add-on", "$49", BRIGHT),
        ("Bundle discount on the full set", "", "−$146", ACCENT),
    ]
    price_w = 275.5
    body_rows = grid(left, [price_w - 70, 70], 0, rows=len(rows))
    for (name, note, amount, colour), (label_cell, amount_cell) in zip(rows, body_rows):
        for c in (label_cell, amount_cell):
            cell_borders(c, HAIR, 6, ("bottom",))
            cell_pad(c, 2, 0, 2, 0)
            clear(c)
        p = para(label_cell, 0, 0, line=10)
        run(p, name, 7.9, BODY)
        if note:
            run(p, note, 7.9, DIM)
        text_para(amount_cell, amount, 7.9, colour, bold=True, line=10,
                  align=WD_ALIGN_PARAGRAPH.RIGHT)

    total = grid(left, [price_w - 90, 90], 0)
    for c in total:
        cell_pad(c, 4, 0, 1, 0)
        clear(c)
    text_para(total[0], "BetterStats plus every module", 8.9, BRIGHT, bold=True, line=12)
    text_para(total[1], "$949 / year", 8.9, ACCENT, bold=True, line=12,
              align=WD_ALIGN_PARAGRAPH.RIGHT)

    text_para(left, "Bundling saves $48 on two modules, $97 on three and $146 on all "
                    "four. Every price covers unlimited players, seasons and teams.",
              7.2, DIM, line=10.5, space_before=6)

    # Right: the comparison.
    right = card(cells[1], fill=TINT, border=ACCENT, pad=(9, 10, 9, 10))
    text_para(right, "Against the usual stack", 9.1, BRIGHT, bold=True, line=12,
              space_after=4)
    text_para(right, "$955", 25.5, ACCENT, bold=True, line=29, space_after=8)
    text_para(right, "Saved a year against paying for the same jobs separately: a "
                     "cricket stats platform, a website builder, an email tool, a design "
                     "app and a membership app come to about $1,904 on their own "
                     "published prices. BetterCricket does the lot for $949.",
              7.2, DIM, line=11.2, space_after=8)
    text_para(right, "The nearest cricket rival also charges a one-off historical import "
                     "fee, from $499 up to about $1,000 for a big club. Ours is included.",
              7.2, DIM, line=11.2)

    eyebrow(doc, "GETTING STARTED", space_before=9)

    steps = [
        ("01 · 5 MINUTES", "We start your first sync",
         "Give us your club details and we pull every scrap of available history in "
         "automatically. No spreadsheets to hand over."),
        ("02 · 30 MINUTES", "Tidy it up together",
         "Merge duplicate players, add your awards and fill the gaps with the admin "
         "tools. Up to two hours of our time is included in year one."),
        ("03 · LIVE", "Your site goes public",
         "Fully branded and ready for members, parents and sponsors. From here it keeps "
         "itself current every round, with no ongoing data entry."),
    ]
    cells = grid(doc, [164.3, 165, 165], 7.5)
    for cell, (label, title, body) in zip(cells, steps):
        card(cell, pad=(7, 9, 7, 9))
        text_para(cell, label, 7.0, ACCENT, bold=True, line=9.5, track=0.7, space_after=3)
        text_para(cell, title, 8.4, BRIGHT, bold=True, line=11, space_after=3)
        text_para(cell, body, 7.3, BODY, line=10.5)

    spacer(doc, 7)

    # Testimonial.
    quote = card(grid(doc, [CONTENT], 0)[0], fill=BG, border=ACCENT,
                 pad=(6, 12, 6, 8), border_sides=("left",), border_size=11)
    text_para(quote, "\"At last we have a complete stats package that lets us view the "
                     "club's entire history across every statistic imaginable, even ones "
                     "we never thought possible. It brings together tools to merge player "
                     "profiles, add honours, fill in missing data and build out individual "
                     "player profiles. It's made pretty much every spreadsheet we had "
                     "redundant, and we had a lot.\"", 8.1, BRIGHT, italic=True, line=12.5)
    text_para(quote, "Tristram Fletcher · Secretary, Applecross Cricket Club",
              7.2, DIM, line=11, space_before=6)

    eyebrow(doc, "QUESTIONS CLUBS ALWAYS ASK", space_before=8)

    faqs = [
        ("Do we have to change how we score or register?",
         "No. BetterCricket sits on top of however you already run match day. Nothing "
         "about your scoring or registration changes, and the stats turn up on your site "
         "on their own."),
        ("How much of it is actually automatic?",
         "Results sync overnight after each round, and averages, records, ladders, "
         "milestones and profiles follow on their own. Posts, fee allocation and the "
         "yearbook build off the same data. What's left for a person is the judgement: "
         "merging a duplicate, approving an award."),
        ("Where does the data come from?",
         "Your match history imports automatically and stays current after every game. "
         "Anything not already online comes in through our CSV templates, or by "
         "photographing the scorebook page."),
        ("How far back does the history go?",
         "As far back as you can go. We bring across whatever is available, and you layer "
         "your own records on top of that."),
        ("What if our scorers haven't been perfect?",
         "Duplicate players are found for you and merged in a click, keeping every innings "
         "and spell. Mis-attributed innings and name changes are handled the same way. "
         "Minutes of work, not a weekend."),
        ("Can we keep junior seasons out of senior averages?",
         "Yes. Every stats page filters by grade type (men's, women's, juniors, masters) "
         "and match type (Two Day, One Day, T20), and you set what your club's default "
         "view leaves out."),
        ("Does the price change with club size?",
         "No. It is a flat rate per club, with no per-team, per-player or per-grade "
         "pricing."),
        ("Do we own the data?",
         "Always. It belongs to your club, and you can export all of it to CSV whenever "
         "you want."),
        ("Can we add modules later?",
         "Yes. Add one at any time and it switches on straight away. Each module is an "
         "annual commitment."),
        ("How do we pay?",
         "An annual invoice, paid by card, Apple Pay or Google Pay through Stripe, with "
         "GST handled at checkout. Bank transfer or PayID still works if your treasurer "
         "would rather do it that way."),
    ]
    faq_rows = grid(doc, [251, 248], 11, rows=(len(faqs) + 1) // 2)
    for pair, cells in zip([faqs[i:i + 2] for i in range(0, len(faqs), 2)], faq_rows):
        for cell, (question, answer) in zip(cells, pair):
            cell_pad(cell, 0, 0, 3, 0)
            clear(cell)
            text_para(cell, question, 7.9, BRIGHT, bold=True, line=10.5,
                      keep_with_next=True)
            text_para(cell, answer, 7.2, BODY, line=10.2, space_before=1.5)

    rule(doc, HAIR, space_before=7, space_after=7)

    cells = grid(doc, [380, CONTENT - 380 - 10], 10)
    left = cells[0]
    clear(left)
    text_para(left, "Get your club on BetterCricket.", 12.4, BRIGHT, bold=True,
              line=15, space_after=4)
    p = para(left, 0, 0, line=11.5)
    run(p, "Start the 14-day free trial of every module at ", 7.8, DIM)
    run(p, "betterat.cricket/trial", 7.8, ACCENT, bold=True)
    run(p, ", or email us and we'll walk your committee through it on a "
           "15-minute call.", 7.8, DIM)

    button = cells[1]
    clear(button)
    inner = grid(button, [110], 0)[0]
    card(inner, fill=ACCENT, border=ACCENT, pad=(7, 8, 7, 8))
    text_para(inner, "Start the free trial →", 8.1, INK, bold=True, line=11,
              align=WD_ALIGN_PARAGRAPH.CENTER)

    text_para(doc, "BetterCricket is the cricket platform from BetterSports · "
                   "ABN 32 624 335 397 · betterat.cricket · "
                   "support@bettersports.com.au", 6.6, FAINT, line=10,
              space_before=8, align=WD_ALIGN_PARAGRAPH.CENTER)


def close_cells(doc):
    """A table cell must end with a paragraph.

    Several cells here hold nothing but a nested table (the numbered jobs, the
    call-to-action button). OOXML requires a trailing w:p, and a file without
    one is rejected outright rather than merely rendered oddly, so give each
    such cell a 1pt paragraph that takes up no visible room.
    """
    for tc in doc.element.body.iter(qn("w:tc")):
        children = list(tc)
        if children and _local(children[-1].tag) != "p":
            p = OxmlElement("w:p")
            pPr = OxmlElement("w:pPr")
            spacing = _el("w:spacing", after=0, line=20, lineRule="exact")
            pPr.append(spacing)
            rPr = OxmlElement("w:rPr")
            rPr.append(_el("w:sz", val=2))
            pPr.append(rPr)
            p.append(pPr)
            tc.append(p)


# -------------------------------------------------------------------- main --
def build(out_path):
    doc = Document()

    section = doc.sections[0]
    section.page_width = Pt(PAGE_W)
    section.page_height = Pt(PAGE_H)
    section.left_margin = Pt(MARGIN)
    section.right_margin = Pt(MARGIN)
    section.top_margin = Pt(34)
    section.bottom_margin = Pt(25)
    section.header_distance = Pt(14)
    section.footer_distance = Pt(14)

    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(7.4)
    normal.font.color.rgb = RGBColor.from_string(BODY)
    normal.paragraph_format.space_after = Pt(0)

    paint_background(doc)
    add_footer(doc)

    # The default template may open with an empty paragraph; the flyer supplies
    # its own content, so drop it.
    if doc.paragraphs:
        first = doc.paragraphs[0]
        first._p.getparent().remove(first._p)

    page_one(doc)
    page_two(doc)
    close_cells(doc)

    doc.save(out_path)
    print("wrote", out_path)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else str(HERE / "BetterCricket_Flyer.docx")
    build(out)
