"""Write the club-facing archive summary as a Word document.

Same content as the published dossier, in the format a committee can print,
mark up and email round. Arial throughout, no colour that a mono printer
turns to mud.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor, Inches

GREEN = RGBColor(0x1F, 0x5C, 0x3D)
GREY = RGBColor(0x5A, 0x5A, 0x5A)


def style(doc: Document) -> None:
    n = doc.styles["Normal"]
    n.font.name = "Arial"
    n.font.size = Pt(10.5)
    n.paragraph_format.space_after = Pt(8)
    n.paragraph_format.line_spacing = 1.15
    for name, size, colour, before in (
        ("Heading 1", 18, GREEN, 0),
        ("Heading 2", 13, GREEN, 16),
        ("Heading 3", 11, None, 10),
    ):
        s = doc.styles[name]
        s.font.name = "Arial"
        s.font.size = Pt(size)
        s.font.bold = True
        s.font.italic = False
        if colour is not None:
            s.font.color.rgb = colour
        s.paragraph_format.space_before = Pt(before)
        s.paragraph_format.space_after = Pt(4)


def para(doc, text="", *, style_name=None, bold=False, italic=False,
         size=None, colour=None, space_after=None, align=None):
    p = doc.add_paragraph(style=style_name)
    if text:
        r = p.add_run(text)
        r.bold = bold
        r.italic = italic
        if size:
            r.font.size = Pt(size)
        if colour is not None:
            r.font.color.rgb = colour
    if space_after is not None:
        p.paragraph_format.space_after = Pt(space_after)
    if align is not None:
        p.alignment = align
    return p


def rich(doc, parts, *, style_name=None, space_after=None):
    """parts: list of (text, bold) or (text, bold, mono)."""
    p = doc.add_paragraph(style=style_name)
    for part in parts:
        text, bold = part[0], part[1]
        mono = part[2] if len(part) > 2 else False
        r = p.add_run(text)
        r.bold = bold
        if mono:
            r.font.name = "Consolas"
            r.font.size = Pt(9.5)
    if space_after is not None:
        p.paragraph_format.space_after = Pt(space_after)
    return p


def kv(doc, rows):
    t = doc.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.LEFT
    for k, v in rows:
        c = t.add_row().cells
        c[0].width = Inches(1.35)
        c[1].width = Inches(5.15)
        kp = c[0].paragraphs[0]
        kr = kp.add_run(k)
        kr.bold = True
        kp.paragraph_format.space_after = Pt(2)
        vp = c[1].paragraphs[0]
        vp.add_run(v)
        vp.paragraph_format.space_after = Pt(2)
    return t


def question(doc, n, chip, title, paras, why=None):
    rich(doc, [(f"Q{n}. ", True), (title, True)], style_name="Heading 3",
         space_after=2)
    para(doc, chip, italic=True, size=9, colour=GREY, space_after=4)
    for text in paras:
        para(doc, text, space_after=4)
    if why:
        rich(doc, [("Why it matters: ", True), (why, False)], space_after=10)
    else:
        doc.paragraphs[-1].paragraph_format.space_after = Pt(10)


def build(out: Path) -> None:
    doc = Document()
    style(doc)
    for s in doc.sections:
        s.left_margin = s.right_margin = Inches(0.9)
        s.top_margin = s.bottom_margin = Inches(0.8)

    para(doc, "Payneham Archive Summary", style_name="Heading 1")
    para(doc,
         "What we recovered from 97 years of Cricket Statistics for Windows "
         "season files, what the files cannot tell us, and what we need from "
         "the club before the import.",
         italic=True, colour=GREY, space_after=14)

    kv(doc, [
        ("206", "season files read"),
        ("1928–2025", "years covered"),
        ("7,915", "matches recovered"),
        ("3,506", "players who appear in a match"),
        ("3,673", "names in the club's player lists"),
    ])
    para(doc, space_after=6)

    # ---- what we were given -------------------------------------------
    para(doc, "What we were given", style_name="Heading 2")
    para(doc, "And why it could not simply be opened.", italic=True,
         colour=GREY, space_after=6)
    para(doc,
         "The archive is 206 files ending in .av, plus about forty spreadsheet "
         "exports and a user manual. They were written by Cricket Statistics "
         "for Windows, shareware sold by a developer in England from the "
         "1990s. Each .av file holds one season and is always exactly 549,871 "
         "bytes — the program wrote its records in fixed-size blocks, so "
         "nothing inside is labelled.")
    para(doc,
         "There is no export button that produces what BetterCricket needs, "
         "and the program itself is no longer sold. So we worked out the "
         "layout of the file by hand: which bytes hold a player's runs, which "
         "hold a bowler's overs, where the dates sit. Every figure below was "
         "then read straight out of your files.")
    rich(doc, [
        ("Nothing was guessed. ", True),
        ("We checked the decoding against cricket's own arithmetic — for "
         "example, every batsman's boundaries had to fit inside his score. "
         "Across ", False),
        ("40,742", True),
        (" innings that test passed ", False),
        ("every single time", True),
        (". Where a wicketkeeper's byes were recorded, they matched the "
         "innings total in 99.8% of cases.", False),
    ])

    # ---- what we recovered --------------------------------------------
    para(doc, "What we recovered", style_name="Heading 2")
    para(doc, "Full scorecards, not just totals.", italic=True, colour=GREY,
         space_after=6)
    kv(doc, [
        ("Per match", "Date, opposition, ground, result, and the winning margin."),
        ("Per batsman", "Runs, balls, minutes, fours, sixes, how they were out, "
                        "whether they were captain or keeper."),
        ("Per bowler", "Overs, maidens, runs, wickets, wides, no-balls, and the "
                       "order they came on."),
        ("Per fielder", "Catches, catches taken keeping, stumpings, byes conceded."),
        ("Per innings", "Team total, wickets, overs, all five kinds of extras, "
                        "and the fall of every wicket."),
    ])
    para(doc, space_after=4)
    para(doc,
         "Two player counts appear above because they answer different "
         "questions. 3,506 people appear in at least one recorded batting, "
         "bowling or fielding line. The club's player lists hold 3,673 names "
         "— so 167 were entered over the years but never appear in a "
         "match we can find. Both numbers are in the workbook.")
    para(doc, space_after=4)
    rich(doc, [
        ("That comes to ", False), ("93,780 batting innings", True),
        (" and ", False), ("64,934 bowling spells", True),
        (". As a sanity check, the all-time lists fall straight out of it: ", False),
        ("J.W. Stagg", True),
        (" leads the run scoring with 9,634 at 25.49 from 341 matches, ", False),
        ("G.G. Wilson", True), (" the wickets with 874 at 18.24, and the "
                                "highest score in the archive is ", False),
        ("W.H. Toy's 249 in 1943", True),
        (". If those look wrong to you, tell us — they are the best test "
         "we have that the decoding is right.", False),
    ])

    # ---- completeness table -------------------------------------------
    para(doc, "How complete each era is", style_name="Heading 2")
    para(doc, "The older seasons were entered as summaries; the recent ones "
              "are full scorecards.", italic=True, colour=GREY, space_after=6)

    rows = [
        ("1920s", "6", "0", "0", "—"),
        ("1930s", "24", "241", "160", "—"),
        ("1940s", "215", "2,982", "1,778", "—"),
        ("1950s", "454", "6,516", "3,648", "—"),
        ("1960s", "584", "8,560", "3,912", "1%"),
        ("1970s", "783", "9,780", "4,970", "11%"),
        ("1980s", "938", "10,138", "6,100", "12%"),
        ("1990s", "949", "10,260", "6,420", "19%"),
        ("2000s", "1,333", "15,368", "11,755", "12%"),
        ("2010s", "1,708", "18,244", "15,919", "22%"),
        ("2020s", "921", "11,691", "10,272", "87%"),
    ]
    t = doc.add_table(rows=1, cols=5)
    t.style = "Table Grid"
    hdr = ("Decade", "Matches", "Batting", "Bowling", "Balls faced")
    for i, h in enumerate(hdr):
        p = t.rows[0].cells[i].paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        p.paragraph_format.space_after = Pt(2)
        if i:
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            p = cells[i].paragraphs[0]
            p.add_run(v)
            p.paragraph_format.space_after = Pt(2)
            if i:
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    para(doc, space_after=2)
    para(doc,
         "“Balls faced” is the share of batting innings where somebody "
         "wrote down the balls, which is what a strike rate needs. The 2020s "
         "are nearly complete; before 1970 it was almost never recorded, so "
         "those eras will show runs and averages but no strike rates.",
         italic=True, colour=GREY)

    # ---- limitations ---------------------------------------------------
    para(doc, "Three things the files simply do not contain",
         style_name="Heading 2")
    para(doc, "These are limits of the old program, not gaps in our reading "
              "of it.", italic=True, colour=GREY, space_after=6)

    para(doc, "1. No grade or team is recorded anywhere", style_name="Heading 3")
    para(doc,
         "This is the significant one. The program had no field for which XI "
         "played a match. Worse, you used one file per season for several "
         "teams at once: the 2024 file holds 61 matches and 120 players, and "
         "three different sides all played on 12 October 2024. Unless you can "
         "tell us which match belongs to which grade, every match imports "
         "without one — so BetterCricket could not show, say, an A Grade "
         "batting average on its own.")
    para(doc, "2. The opposition's players are never stored",
         style_name="Heading 3")
    para(doc,
         "Only their team name and their innings total. So “c Smith b "
         "Jones” cannot be recovered — we know your batsman was "
         "caught, but not who caught him or who bowled. Nothing can bring "
         "that back.")
    para(doc, "3. Run-outs are not credited to a fielder", style_name="Heading 3")
    para(doc,
         "The files record that a batsman was run out, but not who threw the "
         "stumps down. Catches, stumpings and byes are all there; run-outs "
         "are not.")

    # ---- questions ------------------------------------------------------
    para(doc, "Questions we need answered", style_name="Heading 2")
    para(doc, "Ordered by how much they affect the result. Q1 to Q4 change "
              "what we import; the rest is tidying that can happen "
              "afterwards.", italic=True, colour=GREY, space_after=8)

    B = "Changes the import"
    Q = "Affects quality"
    C = "Confirm only"

    question(doc, 1, B, "What do the full stops after “Payneham” mean?",
             ["163 of the 206 files name the club as Payneham, Payneham., "
              "Payneham.. or Payneham... That looks deliberate — a way of "
              "telling teams apart when the program gave you nowhere else to "
              "put it."],
             "if one dot means 2nd XI and two means 3rd XI, that is most of "
             "the grade problem solved for free.")
    question(doc, 2, B, "What are the letter codes on the other files?",
             ["We see Payneham W, G, J, B, S R, S J, S J 12, S J 14 and J 16. "
              "We would guess Women's, Juniors, Under-12, Under-14, Under-16 "
              "and a senior reserves side, but we are guessing."],
             "these become the team names shown against every match and every "
             "player record.")
    question(doc, 3, B,
             "Can you supply grades for matches, or do we import without them?",
             ["Fixture lists, season handbooks or annual reports would let us "
              "attach a grade to each match by date and opposition. Failing "
              "that, we can group matches by who played in them and ask you to "
              "name each group. Or we import ungraded and you accept the loss."],
             "it is far cheaper to decide this now than to re-import 7,915 "
             "matches later.")
    question(doc, 4, B, "Are seven early seasons missing their data?",
             ["1929, 1932, 1933, 1934, 1937, 1938 and 2022's junior file hold "
              "three matches or fewer. For 1938 the file has one match, yet an "
              "old spreadsheet export from the same program shows a full "
              "ten-match season of bowling averages — and names players "
              "who are no longer in the file. That data existed once."],
             "if a fuller version survives on another computer or an old "
             "backup, we should import that instead.")
    question(doc, 5, Q, "Is Hectorville/Payneham in 2016 your club?",
             ["One file names a combined side. We need to know whether those "
              "matches belong in Payneham's records, and under what name."])
    question(doc, 6, Q, "Are these the same player, or two people?",
             ["225 names differ only by a middle initial — Shah, S and "
              "Shah, SS; Thompson, LA and Thompson, LE; Clark, BG and Clark, "
              "BW. Some are one man recorded two ways; some are a father and "
              "son. The Name check tab of the workbook lists every pair."],
             "BetterCricket will merge some of these automatically. We would "
             "rather you check the list first than unpick it after.")
    question(doc, 7, Q, "Should we correct the opposition spellings?",
             ["487 club names appear, and 59 pairs are near-identical typos "
              "— Woodville Rechabites and Woodville Rechabite; Eastern "
              "Suburbs White and Easten Suburbs White; Hope Valley Blue and "
              "Hope Valey Blue. Left alone, each spelling reads as a separate "
              "club. The Opposition tab lists them."])
    question(doc, 8, Q, "Should the association be recorded against each season?",
             ["Your old exports mention ACTA, ETCA and Adelaide Turf, but the "
              "season files themselves never store it. If you can tell us "
              "which association each era played under, we can add it."])
    question(doc, 9, C, "Were 2,292 matches genuinely two innings a side?",
             ["That many matches have your team batting twice, which we have "
              "read as two-day, two-innings fixtures. Please confirm that is "
              "normal for these grades rather than something the program did."])
    question(doc, 10, C, "Nine matches appear in two files at once",
             ["Same date, same opposition, same ground, recorded in two "
              "different season files — for example Para Hills on 1 "
              "February 2026. Either two of your sides really did play them, "
              "or one was entered twice. The Data gaps tab lists all nine."])
    question(doc, 11, C, "We cannot tell who batted first — is that acceptable?",
             ["The files record no toss and no batting order, so on a scorecard "
              "we will show your innings first. Every total, average and figure "
              "is unaffected; only the order the two innings appear in is a "
              "convention we have chosen."])

    # ---- what you have been sent ---------------------------------------
    para(doc, "What you have been sent", style_name="Heading 2")
    para(doc, "Three shapes of the same data, for three different jobs.",
         italic=True, colour=GREY, space_after=6)
    kv(doc, [
        ("match_detail.xlsx",
         "The review copy. Twelve tabs — a summary, every match, every "
         "batting and bowling innings, fielding, the player list, the 225 "
         "name pairs to check, the opposition and ground spellings, and the "
         "gaps we found. This is the one to read and mark up."),
        ("manual_games_scorecards.csv",
         "The complete record: all 7,915 matches and 184,660 rows in one "
         "file, kept as the master copy and for your own records."),
        ("by_season/",
         "92 files, one per season, in the same format. These are what we "
         "actually load into BetterCricket — the importer takes one "
         "sheet at a time, so a 97-year archive goes in season by season "
         "rather than in a single upload."),
    ])

    # ---- next -----------------------------------------------------------
    para(doc, "What happens next", style_name="Heading 2")
    para(doc, "The data is ready; these answers decide how much of it is "
              "useful.", italic=True, colour=GREY, space_after=6)
    for text in (
        "All 92 season sheets have been run through the importer's own reader "
        "without a single rejected row, so the conversion itself is settled.",
        "Answers to Q1 to Q4 are what we are waiting on. Q1 and Q2 may be a "
        "two-minute conversation with whoever kept the records.",
        "Q5 to Q11 can all be handled after the import, but they are cheaper "
        "before it.",
        "Once loaded, every season becomes searchable in BetterCricket "
        "alongside your current PlayHQ data — career records, milestones "
        "and honour boards across all 97 years.",
    ):
        p = doc.add_paragraph(text, style="List Bullet")
        p.paragraph_format.space_after = Pt(5)

    para(doc, space_after=4)
    para(doc,
         "Prepared for Payneham Cricket Club, based on 206 Cricket Statistics "
         "for Windows season files, 1928–2025. Every figure quoted was "
         "read directly from those files.",
         italic=True, size=9, colour=GREY)

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    print(f"  {out.name}  {out.stat().st_size/1024:.0f} KB")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--out", type=Path,
                    default=Path("Payneham Archive Summary.docx"))
    build(ap.parse_args().out)


if __name__ == "__main__":
    main()
