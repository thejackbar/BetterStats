"""Render the club-edited Payneham Archive Summary in the look of the
published 'Payneham Archive Recovery' artifact — a self-contained print HTML.

Content is the club's own edited wording (their uploaded .docx), verbatim.
Only the presentation is the artifact's: Zilla Slab display, Source Sans 3
body, IBM Plex Mono labels, the green/red/amber system, section rules,
stat tiles and colour-coded question cards. Fonts are embedded so the PDF
renders identically with no network.
"""
from __future__ import annotations
import argparse, html, pathlib

def esc(s): return html.escape(s, quote=False)

# ---- content (the club's uploaded summary, verbatim) --------------------
STANDFIRST = ("What we recovered from 97 years of Cricket Statistics for Windows "
    "(CSFW) season files, what the files cannot tell us, and what we need from "
    "you before the import.")

STATS = [("206", "Season files read"), ("1928–2025", "Years covered"),
    ("7,915", "Matches recovered"), ("3,506", "Players in a match"),
    ("3,673", "Names on the lists")]

RECEIVED = [
    "The archive is 206 files ending in <code>.av</code>, plus about forty "
    "spreadsheet exports and a user manual. They were written by Cricket "
    "Statistics for Windows. Each <code>.av</code> file holds one season and is "
    "always exactly 549,871 bytes. CSFW wrote its records in fixed-size blocks, "
    "so nothing inside the file is labelled.",
    "We worked out the layout of the file: which bytes hold a player's runs, "
    "which hold a bowler's overs, where the dates sit. Every figure below was "
    "then extracted from your files."]
RECEIVED_NOTE = ("We checked the decoding against cricket's own arithmetic. For "
    "example, every batsman's boundaries had to fit inside his score. Across "
    "<b>40,742</b> innings that test passed <b>every single time</b>. Where a "
    "wicketkeeper's byes were recorded, they matched the innings total in 99.8% "
    "of cases.")

RECOVERED_KV = [
    ("Per match", "Date, opposition, ground, result, and the winning margin."),
    ("Per batsman", "Runs, balls, minutes, fours, sixes, how they were out, "
        "whether they were captain or keeper."),
    ("Per bowler", "Overs, maidens, runs, wickets, wides, no-balls, and the "
        "order they came on."),
    ("Per fielder", "Catches, catches taken keeping, stumpings, byes conceded."),
    ("Per innings", "Team total, wickets, overs, all five kinds of extras, and "
        "the fall of every wicket.")]
RECOVERED_P = [
    "Two player counts appear above because they answer different questions. "
    "<b>3,506</b> people appear in at least one recorded batting, bowling or "
    "fielding line. The club's player lists hold <b>3,673</b> names (so 167 "
    "players were entered over the years but never appear in a match we can "
    "find). Both numbers are in the workbook.",
    "We extracted <b>93,780 batting innings</b> and <b>64,934 bowling spells</b>. "
    "As a sanity check, the all-time lists fall straight out of it: "
    "<b>J.W. Stagg</b> leads the run scoring with 9,634 at 25.49 from 341 "
    "matches, <b>G.G. Wilson</b> the wickets with 874 at 18.24, and the highest "
    "score in the archive is <b>W.H. Toy's 249 in 1943</b>. If those look wrong "
    "to you, tell us. They are the best test we have that the decoding is right."]

DECADES = [  # decade, matches, batting, bowling, balls-faced
    ("1920s", 6, "0", "0", "—"), ("1930s", 24, "241", "160", "—"),
    ("1940s", 215, "2,982", "1,778", "—"), ("1950s", 454, "6,516", "3,648", "—"),
    ("1960s", 584, "8,560", "3,912", "1%"), ("1970s", 783, "9,780", "4,970", "11%"),
    ("1980s", 938, "10,138", "6,100", "12%"), ("1990s", 949, "10,260", "6,420", "19%"),
    ("2000s", 1333, "15,368", "11,755", "12%"), ("2010s", 1708, "18,244", "15,919", "22%"),
    ("2020s", 921, "11,691", "10,272", "87%")]
DECADE_NOTE = ("Bar length shows matches per decade against the 1,708 of the "
    "2010s. “Balls faced” is the share of batting innings where "
    "somebody wrote down the balls, which is what a strike rate needs. The "
    "2020s are nearly complete; before 1970 it was almost never recorded, so "
    "those eras will show runs and averages but no strike rates.")

LIMITS = [
    ("1. No grade or team is recorded anywhere",
     "This is significant. CSFW had no field for which XI played a match. Worse, "
     "one file per season was used in CSFW for several teams at once: e.g. the "
     "2024 file holds 61 matches and 120 players, and three different sides all "
     "played on 12 October 2024. Unless you can tell us which match belongs to "
     "which grade, every match imports without a grade, so BetterCricket can't "
     "show, say, an A Grade batting average on its own."),
    ("2. The opposition's players are never stored",
     "Only Payneham's team name and their innings total. So something like "
     "“c Smith b Jones” cannot be recovered. We know your batsman was "
     "caught, but not who caught him or who bowled."),
    ("3. Run-outs are not credited to a fielder",
     "The files record that a batsman was run out, but not the name of the "
     "fielder. Catches, stumpings and byes are all there; run-outs are not.")]

# (chip label, css class, heading, body, why-or-None)
Q = [
    ("Changes the import", "block", "Q1. What do the full stops after “Payneham” mean?",
     "163 of the 206 files name the club as <code>Payneham</code>, "
     "<code>Payneham.</code>, <code>Payneham..</code> or <code>Payneham...</code>. "
     "That looks deliberate, like a way of telling teams apart when the program "
     "gave you nowhere else to put it. Is this correct?",
     "if one dot means 2nd XI and two means 3rd XI, that is most of the grade "
     "problem solved."),
    ("Changes the import", "block", "Q2. What are the letter codes on the other files?",
     "We see <code>Payneham W</code>, <code>G</code>, <code>J</code>, "
     "<code>B</code>, <code>S R</code>, <code>S J</code>, <code>S J 12</code>, "
     "<code>S J 14</code> and <code>J 16</code>. Is it Women's, Juniors, "
     "Under-12, Under-14, Under-16 and a senior reserves side? This is just a "
     "guess.",
     "these become the team names shown against every match and every player "
     "record."),
    ("Changes the import", "block", "Q3. Can you supply grades for matches, or do we import without them?",
     "Fixture lists, season handbooks or annual reports would let us attach a "
     "grade to each match by date and opposition. Failing that, we can group "
     "matches by who played in them and ask you to name each group. Or we import "
     "ungraded if that is all we have.",
     "it would be better to determine this now and deal with it in the "
     "spreadsheets than try to manage the changes across 7,915 matches later."),
    ("Changes the import", "block", "Q4. Are seven early seasons missing their data?",
     "1929, 1932, 1933, 1934, 1937, 1938 and 2022's junior file hold three "
     "matches or fewer. For 1938 the file has one match, yet an old spreadsheet "
     "export from the same program shows a full ten-match season of bowling "
     "averages, and it names players who are no longer in the file. It appears "
     "that this data existed once.",
     "if a fuller version survives on another computer or an old backup, could "
     "you send this to us please."),
    ("Affects quality", "qual", "Q5. Is Hectorville/Payneham in 2016 your club?",
     "One file names a combined side. We need to know whether those matches "
     "belong in Payneham's records, and under what name.", None),
    ("Affects quality", "qual", "Q6. Are these the same player, or two people?",
     "225 names differ only by a middle initial. <code>Shah, S</code> and "
     "<code>Shah, SS</code>; <code>Thompson, LA</code> and <code>Thompson, "
     "LE</code>; <code>Clark, BG</code> and <code>Clark, BW</code>. Some might "
     "be one person recorded two ways; some are a father and son. The Name check "
     "tab of the workbook lists every pair.",
     "BetterCricket will merge some of these automatically. Might be good to "
     "check the list first rather than have to undo merges later."),
    ("Affects quality", "qual", "Q7. Should we correct the opposition spellings?",
     "487 club names appear, and 59 pairs are near-identical typos e.g. "
     "<code>Woodville Rechabites</code> and <code>Woodville Rechabite</code>; "
     "<code>Eastern Suburbs White</code> and <code>Easten Suburbs White</code>; "
     "<code>Hope Valley Blue</code> and <code>Hope Valey Blue</code>. Left "
     "alone, each spelling reads as a separate club. The Opposition tab lists "
     "them.", None),
    ("Affects quality", "qual", "Q8. Should the association be recorded against each season?",
     "Your old exports mention ACTA, ETCA and Adelaide Turf, but the season "
     "files themselves never store it. If you can tell us which association each "
     "era played under, we can add it.", None),
    ("Confirm only", "opt", "Q9. Were 2,292 matches genuinely two innings a side?",
     "2,292 matches have your team batting twice, which we have read as "
     "two-day, two-innings fixtures. Please confirm that is normal for these "
     "grades rather than something the program did.", None),
    ("Confirm only", "opt", "Q10. Nine matches appear in two files at once",
     "Same date, same opposition, same ground, recorded in two different season "
     "files, for example Para Hills on 1 February 2026. Either two of your sides "
     "really did play them, or one was entered twice. The Data gaps tab lists "
     "all nine.", None),
    ("Confirm only", "opt", "Q11. We cannot tell who batted first – is that acceptable?",
     "The files record no toss and no batting order, so on a scorecard we will "
     "show your innings first. Every total, average and figure is unaffected; "
     "only the order the two innings appear in is a convention we have chosen.",
     None)]

SENT_KV = [
    ("match_detail.xlsx", "The review copy. Twelve tabs — a summary, every "
        "match, every batting and bowling innings, fielding, the player list, "
        "the 225 name pairs to check, the opposition and ground spellings, and "
        "the gaps we found. This is the one to read and mark up."),
    ("manual_games_scorecards.csv", "The complete record: all 7,915 matches and "
        "184,660 rows in one file, kept as the master copy and for your own "
        "records."),
    ("by_season/", "92 files, one per season, in the same format.")]

NEXT = [
    "All 92 season sheets have been run through the importer's own reader "
    "without a single rejected row, so the conversion itself is stable.",
    "Answers to <b>Q1 to Q4</b> will inform the process. Q1 and Q2 may be a "
    "two-minute conversation with whoever kept the records.",
    "Q5 to Q11 can all be handled after the import, but they are arguably easier "
    "to do in the spreadsheets (before importing)."]


def sect_head(title, sub):
    return (f'<div class="sect-head"><h2>{esc(title)}</h2>'
            f'<p>{esc(sub)}</p></div>')

def build(font_css: str) -> str:
    max_m = max(d[1] for d in DECADES)
    stat_html = "".join(f'<div class="stat"><b>{esc(v)}</b><span>{esc(l)}</span></div>'
                        for v, l in STATS)
    rec_kv = "".join(f"<dt>{esc(k)}</dt><dd>{v}</dd>" for k, v in RECOVERED_KV)
    dec_rows = "".join(
        f'<tr><td>{esc(d[0])}</td>'
        f'<td class="barcell"><span class="bar" style="width:{d[1]/max_m*100:.1f}%"></span></td>'
        f'<td class="n">{d[1]:,}</td><td class="n">{esc(d[2])}</td>'
        f'<td class="n">{esc(d[3])}</td><td class="n">{esc(d[4])}</td></tr>'
        for d in DECADES)
    lim = "".join(f"<h3>{esc(t)}</h3><p>{b}</p>" for t, b in LIMITS)
    qs = ""
    for chip, cls, head, body, why in Q:
        why_html = (f'<p class="why"><b>Why it matters:</b> {why}</p>' if why else "")
        qs += (f'<li class="{cls}"><div class="qbody">'
               f'<span class="chip {cls}">{esc(chip)}</span>'
               f'<h3>{esc(head)}</h3><p>{body}</p>{why_html}</div></li>')
    sent_kv = "".join(f"<dt>{esc(k)}</dt><dd>{v}</dd>" for k, v in SENT_KV)
    nxt = "".join(f"<li>{b}</li>" for b in NEXT)

    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>
{font_css}
:root{{
  --ground:#FFFFFF; --surface:#FFFFFF; --surface-2:#EFEEE8;
  --ink:#16221C; --ink-2:#5C6862; --ink-3:#8A948B;
  --rule:#DEDBD2; --rule-2:#C9C5B9;
  --accent:#1F5C3D; --accent-soft:#E4EDE7;
  --flag:#A33A2B; --flag-soft:#F6E7E4;
  --warn:#8A6414; --warn-soft:#F5EDDC;
  --display:"Zilla Slab",Georgia,serif;
  --body:"Source Sans 3","Segoe UI",Helvetica,Arial,sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;
}}
@page{{ size:A4; margin:15mm 14mm 14mm; }}
*{{box-sizing:border-box}}
html{{-webkit-print-color-adjust:exact; print-color-adjust:exact}}
body{{margin:0; background:#fff; color:var(--ink);
  font-family:var(--body); font-size:10.2pt; line-height:1.5;
  -webkit-font-smoothing:antialiased}}
.eyebrow{{font-family:var(--mono); font-size:8pt; letter-spacing:.14em;
  text-transform:uppercase; color:var(--accent); margin:0 0 6px}}
h1{{font-family:var(--display); font-weight:700; font-size:30pt; line-height:1.05;
  letter-spacing:-.01em; margin:0 0 8px}}
.standfirst{{font-size:12pt; color:var(--ink-2); margin:0; max-width:60ch}}
h2{{font-family:var(--display); font-weight:600; font-size:16pt; line-height:1.15;
  margin:0 0 3px}}
h3{{font-family:var(--display); font-weight:600; font-size:11.5pt; margin:0 0 4px;
  break-after:avoid}}
p{{margin:0 0 9px; max-width:70ch}}
section{{margin-top:22px}}
.sect-head{{border-top:1.5pt solid var(--ink); padding-top:9px; margin-bottom:13px;
  break-after:avoid}}
.sect-head h2{{break-after:avoid}}
.sect-head p{{color:var(--ink-2); margin:1px 0 0; font-size:10pt}}
code{{font-family:var(--mono); font-size:.86em; background:var(--surface-2);
  padding:1px 4px; border-radius:3px; color:var(--ink);
  white-space:nowrap}}

.stats{{display:grid; grid-template-columns:repeat(5,1fr); gap:1px;
  background:var(--rule); border:1px solid var(--rule); margin:20px 0 0;
  break-inside:avoid}}
.stat{{background:var(--surface); padding:11px 10px}}
.stat b{{display:block; font-family:var(--display); font-weight:700;
  font-size:18pt; line-height:1.02; font-variant-numeric:tabular-nums}}
.stat span{{display:block; font-family:var(--mono); font-size:7pt;
  letter-spacing:.08em; text-transform:uppercase; color:var(--ink-2); margin-top:4px}}

table{{width:100%; border-collapse:collapse; font-size:10pt; margin:0}}
th{{font-family:var(--mono); font-size:7.5pt; letter-spacing:.08em;
  text-transform:uppercase; color:var(--ink-2); text-align:left;
  font-weight:500; padding:0 8px 6px 0; border-bottom:1px solid var(--rule-2);
  white-space:nowrap}}
td{{padding:5px 8px 5px 0; border-bottom:1px solid var(--rule);
  font-variant-numeric:tabular-nums; vertical-align:middle}}
td.n{{text-align:right; padding-right:12px}}
.bar{{display:block; height:6px; background:var(--accent); border-radius:1px; min-width:2px}}
.barcell{{width:30%}}
tr{{break-inside:avoid}}

ol.qs{{list-style:none; padding:0; margin:0; display:flex; flex-direction:column; gap:9px}}
ol.qs>li{{background:var(--surface); border:1px solid var(--rule);
  border-left:3px solid var(--rule-2); padding:11px 14px; break-inside:avoid}}
ol.qs>li.block{{border-left-color:var(--flag)}}
ol.qs>li.qual{{border-left-color:var(--warn)}}
.qbody p{{margin:0 0 6px}} .qbody p:last-child{{margin-bottom:0}}
.why{{font-size:9.4pt; color:var(--ink-2)}} .why b{{color:var(--ink); font-weight:600}}
.chip{{display:inline-block; font-family:var(--mono); font-size:7pt;
  letter-spacing:.08em; text-transform:uppercase; padding:2px 6px;
  border-radius:2px; margin-bottom:7px}}
.chip.block{{background:var(--flag-soft); color:var(--flag)}}
.chip.qual{{background:var(--warn-soft); color:var(--warn)}}
.chip.opt{{background:var(--surface-2); color:var(--ink-2)}}

ul.plain{{margin:0; padding-left:18px}}
ul.plain li{{margin-bottom:6px; max-width:66ch}}
.note{{background:var(--accent-soft); border:1px solid var(--rule);
  border-left:3px solid var(--accent); padding:11px 14px; margin:14px 0;
  break-inside:avoid}}
.note p{{margin:0; font-size:10pt}}
.kv{{display:grid; grid-template-columns:auto 1fr; gap:5px 16px; font-size:10pt; margin:0}}
.kv dt{{font-family:var(--mono); font-size:8.5pt; color:var(--ink-2);
  letter-spacing:.03em; padding-top:2px}}
.kv dd{{margin:0}}
footer{{margin-top:26px; padding-top:11px; border-top:1px solid var(--rule);
  font-size:8.5pt; color:var(--ink-3)}}
</style></head><body>
<p class="eyebrow">Report for Payneham Cricket Club</p>
<h1>Payneham Archive Summary</h1>
<p class="standfirst">{esc(STANDFIRST)}</p>
<div class="stats">{stat_html}</div>

<section>{sect_head("What we received","And why it could not simply be opened.")}
{''.join(f'<p>{p}</p>' for p in RECEIVED)}
<div class="note"><p>{RECEIVED_NOTE}</p></div></section>

<section>{sect_head("What we recovered","Full scorecards, not just totals.")}
<dl class="kv">{rec_kv}</dl>
<div style="height:6px"></div>
{''.join(f'<p>{p}</p>' for p in RECOVERED_P)}</section>

<section>{sect_head("How complete each era is","The older seasons were entered as summaries; the recent ones are full scorecards.")}
<table><thead><tr><th>Decade</th><th class="barcell">Matches</th>
<th class="n">Matches</th><th class="n">Batting</th><th class="n">Bowling</th>
<th class="n">Balls faced</th></tr></thead><tbody>{dec_rows}</tbody></table>
<p class="why" style="margin-top:10px">{esc(DECADE_NOTE)}</p></section>

<section>{sect_head("Three things the files do not contain","These are limits of the old program, not gaps in our analysis of it.")}
{lim}</section>

<section>{sect_head("Questions we need answered","Ordered by how much they affect the result. Q1 to Q4 change what we import; the rest is tidying that can happen afterwards.")}
<ol class="qs">{qs}</ol></section>

<section>{sect_head("What you have been sent","Three shapes of the same data, for three different jobs.")}
<dl class="kv">{sent_kv}</dl></section>

<section>{sect_head("What happens next","The data is ready; these answers decide how much of it is useful.")}
<ul class="plain">{nxt}</ul></section>

<footer>Prepared for Payneham Cricket Club &middot; based on 206 Cricket
Statistics for Windows season files, 1928&ndash;2025. Every figure quoted was
read directly from those files.</footer>
</body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--font-css", type=pathlib.Path, required=True)
    ap.add_argument("-o", "--out", type=pathlib.Path, required=True)
    a = ap.parse_args()
    a.out.write_text(build(a.font_css.read_text()))
    print(f"  {a.out}  {a.out.stat().st_size/1024:.0f} KB")

if __name__ == "__main__":
    main()
