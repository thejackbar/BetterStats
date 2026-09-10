"""Build the Payneham Archive Summary as a styled .docx in the look of the
'Payneham Archive Recovery' artifact.

Content is imported from build_summary_html (one source of truth, the club's
own edited wording). Presentation mirrors the artifact as closely as Word
allows: Zilla Slab display, Source Sans 3 body, IBM Plex Mono labels, the
green/red/amber system, section rules, stat tiles and colour-coded question
cards. Fonts are embedded (see embed_fonts) so it renders the same on a
machine that has none of them installed.
"""
from __future__ import annotations
import argparse, re, pathlib
from docx import Document
from docx.shared import Pt, RGBColor, Twips, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

import build_summary_html as C

# ---- palette (artifact tokens) ------------------------------------------
INK   = RGBColor(0x16, 0x22, 0x1C)
INK2  = RGBColor(0x5C, 0x68, 0x62)
INK3  = RGBColor(0x8A, 0x94, 0x8B)
RULE  = "DEDBD2"; RULE2 = "C9C5B9"
ACC   = RGBColor(0x1F, 0x5C, 0x3D); ACC_SOFT = "E4EDE7"
FLAG  = RGBColor(0xA3, 0x3A, 0x2B); FLAG_SOFT = "F6E7E4"
WARN  = RGBColor(0x8A, 0x64, 0x14); WARN_SOFT = "F5EDDC"
SURF2 = "EFEEE8"

DISPLAY  = "Zilla Slab"           # bold face (700) — use with bold=True
DISPLAY6 = "Zilla Slab SemiBold"  # 600 — use with bold=False
BODY     = "Source Sans 3"
BODYB    = "Source Sans 3 SemiBold"
MONO     = "IBM Plex Mono"

CHIP = {  # css class -> (bg fill, text color, mono)
    "block": (FLAG_SOFT, FLAG), "qual": (WARN_SOFT, WARN),
    "opt": (SURF2, INK2)}
CARD_BORDER = {"block": FLAG, "qual": WARN, "opt": RGBColor(0xC9,0xC5,0xB9)}


def _el(tag, **attrs):
    e = OxmlElement(tag)
    for k, v in attrs.items():
        e.set(qn(k), v)
    return e

def shade(el, fill):
    el.append(_el("w:shd", **{"w:val": "clear", "w:color": "auto", "w:fill": fill}))

def set_borders(el, edges):
    """edges: {side: (size_eighths, color_hex)}; el is pPr or tcPr."""
    pbdr = _el("w:pBdr") if el.tag == qn("w:pPr") else _el("w:tcBorders")
    for side, (sz, color) in edges.items():
        pbdr.append(_el(f"w:{side}", **{"w:val": "single", "w:sz": str(sz),
                                        "w:space": "0", "w:color": color}))
    el.append(pbdr)

def no_space(p, before=0, after=0, line=None):
    pf = p.paragraph_format
    pf.space_before = Pt(before); pf.space_after = Pt(after)
    if line: pf.line_spacing = line

def run(p, text, *, font=BODY, size=10.5, color=INK, bold=False, italic=False,
        caps=False, spacing=None):
    r = p.add_run(text)
    r.font.name = font; r.font.size = Pt(size); r.font.color.rgb = color
    r.bold = bold; r.italic = italic
    rpr = r._element.get_or_add_rPr()
    if caps: rpr.append(_el("w:caps", **{"w:val": "true"}))
    if spacing is not None: rpr.append(_el("w:spacing", **{"w:val": str(spacing)}))
    # ensure east-asian/complex also use the font
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = _el("w:rFonts"); rpr.append(rf)
    for a in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rf.set(qn(a), font)
    return r

INLINE = re.compile(r"(<code>.*?</code>|<b>.*?</b>)")
def rich(p, text, *, size=10.5, color=INK, base_font=BODY):
    """Render a string with <code>/<b> spans into runs."""
    for part in INLINE.split(text):
        if not part: continue
        if part.startswith("<code>"):
            inner = part[6:-7]
            r = run(p, inner, font=MONO, size=size-1.2, color=color)
            shade(r._element.get_or_add_rPr(), SURF2)
        elif part.startswith("<b>"):
            run(p, part[3:-4], font=BODYB, size=size, color=color)
        else:
            run(p, part.replace("&amp;","&"), font=base_font, size=size, color=color)


def set_grid(table, widths_in):
    """Force fixed layout so columns honour our widths (Writer autofits otherwise)."""
    total = int(sum(widths_in) * 1440)
    tblPr = table._tbl.tblPr
    for tag in ("w:tblLayout", "w:tblW"):
        e = tblPr.find(qn(tag))
        if e is not None: tblPr.remove(e)
    tblPr.append(_el("w:tblLayout", **{"w:type": "fixed"}))
    tblPr.append(_el("w:tblW", **{"w:w": str(total), "w:type": "dxa"}))
    grid = table._tbl.find(qn("w:tblGrid"))
    if grid is not None:
        table._tbl.remove(grid)
    grid = _el("w:tblGrid")
    for w in widths_in:
        grid.append(_el("w:gridCol", **{"w:w": str(int(w * 1440))}))
    table._tbl.insert(list(table._tbl).index(tblPr) + 1, grid)
    for row in table.rows:
        for j, cell in enumerate(row.cells):
            cell.width = Emu(int(widths_in[j] * 914400))

def no_split(row):
    trPr = row._tr.get_or_add_trPr()
    trPr.append(_el("w:cantSplit", **{"w:val": "true"}))


def sect_head(doc, title, sub):
    p = doc.add_paragraph(); no_space(p, before=17, after=1)
    set_borders(p.paragraph_format._element.get_or_add_pPr(),
                {"top": (12, "16221C")})
    run(p, title, font=DISPLAY6, size=16, color=INK)
    s = doc.add_paragraph(); no_space(s, after=10)
    run(s, sub, font=BODY, size=10, color=INK2)


def kv_table(doc, rows, label_w=1.4, total=6.4):
    t = doc.add_table(rows=0, cols=2); t.alignment = WD_TABLE_ALIGNMENT.LEFT
    t.autofit = False
    for k, v in rows:
        c = t.add_row().cells
        lp = c[0].paragraphs[0]; no_space(lp, after=4)
        run(lp, k, font=MONO, size=8.6, color=INK2)
        vp = c[1].paragraphs[0]; no_space(vp, after=4, line=1.12)
        rich(vp, v, size=10)
    set_grid(t, [label_w, total - label_w])
    return t


_PPR_ORDER = ["w:pStyle","w:keepNext","w:keepLines","w:pageBreakBefore","w:framePr",
  "w:widowControl","w:numPr","w:suppressLineNumbers","w:pBdr","w:shd","w:tabs",
  "w:suppressAutoHyphens","w:kinsoku","w:wordWrap","w:overflowPunct","w:topLinePunct",
  "w:autoSpaceDE","w:autoSpaceDN","w:bidi","w:adjustRightInd","w:snapToGrid",
  "w:spacing","w:ind","w:contextualSpacing","w:mirrorIndents","w:suppressOverlap",
  "w:jc","w:textDirection","w:textAlignment","w:textboxTightWrap","w:outlineLvl",
  "w:divId","w:cnfStyle","w:rPr","w:sectPr","w:pPrChange"]
_RPR_ORDER = ["w:rStyle","w:rFonts","w:b","w:bCs","w:i","w:iCs","w:caps","w:smallCaps",
  "w:strike","w:dstrike","w:outline","w:shadow","w:emboss","w:imprint","w:noProof",
  "w:snapToGrid","w:vanish","w:webHidden","w:color","w:spacing","w:w","w:kern",
  "w:position","w:sz","w:szCs","w:highlight","w:u","w:effect","w:bdr","w:shd",
  "w:fitText","w:vertAlign","w:rtl","w:cs","w:em","w:lang","w:eastAsianLayout",
  "w:specVanish","w:oMath"]

def _reorder(el, order):
    idx = {qn(t): i for i, t in enumerate(order)}
    kids = list(el)
    kids.sort(key=lambda c: idx.get(c.tag, 999))
    for c in kids:
        el.remove(c); el.append(c)

def _dedupe_spacing(ppr):
    sps = ppr.findall(qn("w:spacing"))
    if len(sps) > 1:
        keep = sps[0]
        for extra in sps[1:]:
            for k, v in extra.attrib.items():
                keep.set(k, v)
            ppr.remove(extra)

def normalise(doc):
    from docx.oxml.ns import qn as _qn
    body = doc.element.body
    for ppr in body.iter(qn("w:pPr")):
        _dedupe_spacing(ppr); _reorder(ppr, _PPR_ORDER)
    for rpr in body.iter(qn("w:rPr")):
        _reorder(rpr, _RPR_ORDER)


def build(out: pathlib.Path):
    doc = Document()
    # page geometry
    for s in doc.sections:
        s.left_margin = s.right_margin = Emu(int(0.85*914400))
        s.top_margin = Emu(int(0.7*914400)); s.bottom_margin = Emu(int(0.7*914400))
    # kill default paragraph spacing baseline
    normal = doc.styles["Normal"]
    normal.font.name = BODY; normal.font.size = Pt(10.5)
    normal.paragraph_format.space_after = Pt(9); normal.paragraph_format.line_spacing = 1.32

    # ---- masthead --------------------------------------------------------
    eb = doc.add_paragraph(); no_space(eb, after=5)
    run(eb, "REPORT FOR PAYNEHAM CRICKET CLUB", font=MONO, size=8, color=ACC, spacing=22)
    h1 = doc.add_paragraph(); no_space(h1, after=8, line=1.02)
    run(h1, "Payneham Archive Summary", font=DISPLAY, size=30, color=INK, bold=True)
    sf = doc.add_paragraph(); no_space(sf, after=6, line=1.2)
    run(sf, C.STANDFIRST, font=BODY, size=12, color=INK2)

    # ---- stat tiles ------------------------------------------------------
    st = doc.add_table(rows=2, cols=5); st.alignment = WD_TABLE_ALIGNMENT.LEFT
    st.autofit = False
    for j, (val, lab) in enumerate(C.STATS):
        top = st.cell(0, j); bot = st.cell(1, j)
        for cell in (top, bot):
            cell.width = Emu(int(1.32*914400))
            shade(cell._tc.get_or_add_tcPr(), "FFFFFF")
            set_borders(cell._tc.get_or_add_tcPr(),
                        {s: (4, RULE) for s in ("top","left","bottom","right")})
        vp = top.paragraphs[0]; no_space(vp, before=3, after=0)
        run(vp, val, font=DISPLAY, size=16, color=INK, bold=True)
        lp = bot.paragraphs[0]; no_space(lp, before=0, after=3)
        run(lp, lab.upper(), font=MONO, size=7, color=INK2, spacing=12)
    set_grid(st, [1.28] * 5)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)

    # ---- What we received ------------------------------------------------
    sect_head(doc, "What we received", "And why it could not simply be opened.")
    for para in C.RECEIVED:
        p = doc.add_paragraph(); no_space(p, after=9, line=1.32); rich(p, para)
    # accent note box (single-cell table)
    nt = doc.add_table(rows=1, cols=1); nt.alignment = WD_TABLE_ALIGNMENT.LEFT
    cell = nt.cell(0, 0); cell.width = Emu(int(6.4*914400))
    shade(cell._tc.get_or_add_tcPr(), ACC_SOFT)
    set_borders(cell._tc.get_or_add_tcPr(),
                {"left": (24, "1F5C3D"), "top": (4, RULE),
                 "bottom": (4, RULE), "right": (4, RULE)})
    np = cell.paragraphs[0]; no_space(np, after=0, line=1.3); rich(np, C.RECEIVED_NOTE, size=10)
    set_grid(nt, [6.4])
    doc.add_paragraph().paragraph_format.space_after = Pt(2)

    # ---- What we recovered ----------------------------------------------
    sect_head(doc, "What we recovered", "Full scorecards, not just totals.")
    kv_table(doc, C.RECOVERED_KV, label_w=1.15)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    for para in C.RECOVERED_P:
        p = doc.add_paragraph(); no_space(p, after=9, line=1.32); rich(p, para)

    # ---- How complete each era is ---------------------------------------
    sect_head(doc, "How complete each era is",
              "The older seasons were entered as summaries; the recent ones are full scorecards.")
    max_m = max(d[1] for d in C.DECADES)
    dt = doc.add_table(rows=1, cols=6); dt.alignment = WD_TABLE_ALIGNMENT.LEFT
    dt.autofit = False
    hdr = ["Decade", "Matches", "Matches", "Batting", "Bowling", "Balls faced"]
    widths = [0.8, 1.7, 0.9, 0.9, 0.95, 1.15]
    for j, h in enumerate(hdr):
        c = dt.rows[0].cells[j]; c.width = Emu(int(widths[j]*914400))
        p = c.paragraphs[0]; no_space(p, after=5)
        if j >= 2: p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        run(p, h.upper(), font=MONO, size=7.5, color=INK2, spacing=10)
        set_borders(c._tc.get_or_add_tcPr(), {"bottom": (8, RULE2)})
    for d in C.DECADES:
        cells = dt.add_row().cells
        for j in range(6): cells[j].width = Emu(int(widths[j]*914400))
        # decade
        p = cells[0].paragraphs[0]; no_space(p, before=2, after=2); run(p, d[0], size=10)
        # bar as green block glyphs, ~ proportional (cap 22)
        nblk = max(1, round(d[1]/max_m*13))
        p = cells[1].paragraphs[0]; no_space(p, before=2, after=2)
        run(p, "█"*nblk, font=MONO, size=7, color=ACC)
        # numbers
        for j, val in ((2, f"{d[1]:,}"), (3, d[2]), (4, d[3]), (5, d[4])):
            p = cells[j].paragraphs[0]; no_space(p, before=2, after=2)
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT; run(p, val, size=10)
        for j in range(6):
            set_borders(cells[j]._tc.get_or_add_tcPr(), {"bottom": (4, RULE)})
    set_grid(dt, widths)
    nn = doc.add_paragraph(); no_space(nn, before=8, after=6, line=1.3)
    run(nn, C.DECADE_NOTE, font=BODY, size=9.4, color=INK2)

    # ---- Three things ----------------------------------------------------
    sect_head(doc, "Three things the files do not contain",
              "These are limits of the old program, not gaps in our analysis of it.")
    for title, body in C.LIMITS:
        h = doc.add_paragraph(); no_space(h, before=8, after=4)
        run(h, title, font=DISPLAY6, size=11.5, color=INK)
        p = doc.add_paragraph(); no_space(p, after=9, line=1.32); rich(p, body)

    # ---- Questions -------------------------------------------------------
    sect_head(doc, "Questions we need answered",
              "Ordered by how much they affect the result. Q1 to Q4 change what we import; "
              "the rest is tidying that can happen afterwards.")
    for chip, cls, head, body, why in C.Q:
        card = doc.add_table(rows=1, cols=1); card.alignment = WD_TABLE_ALIGNMENT.LEFT
        cell = card.cell(0, 0); cell.width = Emu(int(6.4*914400))
        shade(cell._tc.get_or_add_tcPr(), "FFFFFF")
        bc = CARD_BORDER[cls]; bhex = "%02X%02X%02X" % (bc[0], bc[1], bc[2])
        set_borders(cell._tc.get_or_add_tcPr(),
                    {"left": (24, bhex), "top": (4, RULE),
                     "bottom": (4, RULE), "right": (4, RULE)})
        # chip
        fill, tcol = CHIP[cls]
        cp = cell.paragraphs[0]; no_space(cp, before=1, after=6)
        cr = run(cp, "  " + chip.upper() + "  ", font=MONO, size=7, color=tcol, spacing=10)
        shade(cr._element.get_or_add_rPr(), fill)
        # heading
        hp = cell.add_paragraph(); no_space(hp, after=4, line=1.1)
        run(hp, head, font=DISPLAY6, size=11.5, color=INK)
        # body
        bp = cell.add_paragraph(); no_space(bp, after=(6 if why else 1), line=1.3)
        rich(bp, body, size=10.2)
        if why:
            wp = cell.add_paragraph(); no_space(wp, after=1, line=1.3)
            run(wp, "Why it matters: ", font=BODYB, size=9.6, color=INK)
            run(wp, why, font=BODY, size=9.6, color=INK2)
        set_grid(card, [6.4]); no_split(card.rows[0])
        doc.add_paragraph().paragraph_format.space_after = Pt(3)

    # ---- What you have been sent ----------------------------------------
    sect_head(doc, "What you have been sent",
              "Three shapes of the same data, for three different jobs.")
    kv_table(doc, C.SENT_KV, label_w=2.0)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)

    # ---- What happens next ----------------------------------------------
    sect_head(doc, "What happens next",
              "The data is ready; these answers decide how much of it is useful.")
    for b in C.NEXT:
        p = doc.add_paragraph(style="List Bullet"); no_space(p, after=6, line=1.3)
        rich(p, b)

    # ---- footer ----------------------------------------------------------
    fp = doc.add_paragraph(); no_space(fp, before=16, after=0)
    set_borders(fp.paragraph_format._element.get_or_add_pPr(), {"top": (4, RULE)})
    run(fp, "Prepared for Payneham Cricket Club · based on 206 Cricket "
            "Statistics for Windows season files, 1928–2025. Every figure "
            "quoted was read directly from those files.",
        font=BODY, size=8.6, color=INK3)

    normalise(doc)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    print(f"  {out.name}  {out.stat().st_size/1024:.0f} KB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", type=pathlib.Path, required=True)
    build(ap.parse_args().out)

if __name__ == "__main__":
    main()
