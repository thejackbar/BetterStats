"""Checks that the CSFW extractor is ONE tool for every club.

What differs between clubs is data - the record layout of the files, and the
club's own team and match-type names - so each check builds a small archive in a
layout and for a club the extractor was never written against, runs the shipped
code over it, and reads the answer back.

Every check reports rather than raising, so run it with a control (an older
extractor, `--module path/to/old.py`) and the missing parts are named instead of
ending the run.

    python3 tools/verify_csfw_extract.py [--module tools/csfw_extract.py]
"""
from __future__ import annotations

import csv
import datetime
import importlib.util
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
args = sys.argv[1:]
MODULE = Path(args[args.index("--module") + 1]) if "--module" in args else HERE / "csfw_extract.py"

PASS = FAIL = 0


def check(label, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label}\n        got  {got!r}\n        want {want!r}")


def refuses(label, fn, needle):
    """`fn` must raise, and the message must say `needle`."""
    try:
        fn()
    except Exception as exc:                                   # noqa: BLE001
        check(label, needle if needle in str(exc) else f"{type(exc).__name__}: {exc}", needle)
        return
    check(label, "no error raised", needle)


def attempt(label, fn, want):
    """Run `fn`; a missing part or an exception is a FAIL that says what."""
    try:
        got = fn()
    except Exception as exc:                                   # noqa: BLE001
        got = f"{type(exc).__name__}: {exc}"
    check(label, got, want)


spec = importlib.util.spec_from_file_location("ext", MODULE)
m = importlib.util.module_from_spec(spec)
sys.modules["ext"] = m          # a dataclass looks its own module up here
spec.loader.exec_module(m)
EPOCH = datetime.date(1899, 12, 30)

# ---------------------------------------------------------------------------
# A layout the extractor has never seen: every table moved and resized, and the
# fields inside the records shifted. Built from the SAME field names the parser
# reads, so a parser that still had an offset hard-wired would read nonsense.
# ---------------------------------------------------------------------------
V2 = dict(
    name="synthetic-v2",
    player_base=400, player_rec=40, player_n=100,
    p_surname=4, p_initial=20, p_first=24,
    fixture_base=4_400, fixture_rec=70, fixture_n=60,
    f_date=4, f_team=30, f_name=34, f_name_len=30,
    match_base=8_600, match_rec=2_100, match_n=60,
    m_type=6, m_round=8, m_ground_idx=30, m_ground=40, m_ground_len=30,
    m_result=600, m_inn_us=610, m_inn_them=690, m_fow=780,
    block_base=830, block_rec=100, block_n=12,
    b_position=4, b_runs=6, b_sixes=10, b_fours=12, b_howout=18,
    b_overs=20, b_maidens=28, b_wickets=30, b_flags=36, b_conceded=38,
    b_wides=40, b_noballs=42, b_catches=44, b_wk_catches=48, b_stumpings=52,
    b_byes=56, b_votes=70,
)
V2["file_len"] = V2["match_base"] + V2["match_n"] * V2["match_rec"]


def build_av(lay, club, year, fixtures, matches, players):
    """A .AV file in `lay`. fixtures: [(slot, date, team, name)] in file order."""
    buf = bytearray(lay.file_len)

    def i16(off, v):
        struct.pack_into("<h", buf, off, v)

    def cur(off, v):
        struct.pack_into("<q", buf, off, int(round(v * 10_000)))

    def txt(off, n, v):
        buf[off:off + n] = v.encode("latin-1").ljust(n)[:n]

    txt(lay.club_at, lay.club_len, club)
    txt(lay.year_at, lay.year_len, str(year))
    for i in range(lay.player_n):
        i16(lay.player_base + i * lay.player_rec, -1)
    for pid, (sur, first) in players.items():
        off = lay.player_base + pid * lay.player_rec
        i16(off, pid)
        txt(off + lay.p_surname, lay.p_surname_len, sur)
        txt(off + lay.p_first, lay.p_first_len, first)
    for i in range(lay.fixture_n):
        i16(lay.fixture_base + i * lay.fixture_rec, -1)
    for pos, (slot, date, team, name) in enumerate(fixtures):
        off = lay.fixture_base + pos * lay.fixture_rec
        i16(off, slot)
        struct.pack_into("<d", buf, off + lay.f_date, float((date - EPOCH).days))
        i16(off + lay.f_team, team)
        txt(off + lay.f_name, lay.f_name_len, name)
    for slot in range(lay.match_n):
        rec = lay.match_base + slot * lay.match_rec
        for inn in (lay.m_inn_us, lay.m_inn_them):
            for o in (lay.i_total, lay.i_wickets, lay.i_number, *lay.i_extras):
                i16(rec + inn + o, -1)
            cur(rec + inn + lay.i_overs, -1)
        for n in range(lay.m_fow_pairs):
            i16(rec + lay.m_fow + n * 4, -1)
        for b in range(lay.block_n):
            off = rec + lay.block_base + b * lay.block_rec
            i16(off + lay.b_player, -1)
            for o in (lay.b_runs, lay.b_sixes, lay.b_fours, lay.b_howout, lay.b_maidens,
                      lay.b_wickets, lay.b_flags, lay.b_conceded, lay.b_wides,
                      lay.b_noballs, lay.b_catches, lay.b_wk_catches,
                      lay.b_stumpings, lay.b_byes):
                i16(off + o, -1)
            i16(off + lay.b_position, lay.did_not_bat)
            cur(off + lay.b_overs, -1)
            cur(off + lay.b_votes, -1)
    for slot, mt in matches.items():
        rec = lay.match_base + slot * lay.match_rec
        buf[rec + lay.m_type] = mt["type"]
        buf[rec + lay.m_result] = mt["result"]
        txt(rec + lay.m_ground, lay.m_ground_len, mt.get("ground", "Home Oval"))
        for inn, key in ((lay.m_inn_us, "us"), (lay.m_inn_them, "them")):
            total, wkts = mt[key]
            i16(rec + inn + lay.i_total, total)
            i16(rec + inn + lay.i_wickets, wkts)
        for b, (pid, pos, runs, howout) in enumerate(mt["bat"]):
            off = rec + lay.block_base + b * lay.block_rec
            i16(off + lay.b_player, pid)
            i16(off + lay.b_position, pos)
            i16(off + lay.b_runs, runs)
            i16(off + lay.b_howout, howout)
    return bytes(buf)


def squad(*pairs):
    return [(pid, pos, runs, 0 if runs % 2 else 11) for pid, pos, runs in pairs]


PLAYERS = {0: ("Smith", "Alan"), 1: ("Jones", "Ben"), 2: ("Patel", "Raj")}
FIXTURES = [  # file order is NOT slot order: the slot a fixture points at is the key
    (2, datetime.date(2025, 10, 25), 3, "Goodwood"),
    (0, datetime.date(2025, 10, 11), 1, "Fulham"),
    (1, datetime.date(2025, 10, 18), 4, "Glenunga"),
]
MATCHES = {
    0: dict(type=4, result=0, us=(263, 7), them=(138, 10), ground="Devitt Oval",
            bat=squad((0, 0, 101), (1, 1, 41), (2, 2, 7))),
    1: dict(type=9, result=1, us=(90, 10), them=(91, 3), ground="Glenunga Oval",
            bat=squad((0, 0, 12), (1, 1, 30), (2, 2, 20))),
    2: dict(type=4, result=4, us=(-1, -1), them=(-1, -1), bat=squad((0, 0, 0))),
}


def archive(folder, lay, files):
    """files: {name: (club, year)}"""
    for name, (club, year) in files.items():
        (folder / name).write_bytes(build_av(lay, club, year, FIXTURES, MATCHES, PLAYERS))


def run(*argv):
    p = subprocess.run([sys.executable, "-I", str(MODULE), *map(str, argv)],
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def read_csv(path):
    return list(csv.DictReader(open(path, encoding="utf-8-sig")))


# ---------------------------------------------------------------------------
# 1. The layout is data
# ---------------------------------------------------------------------------
LAYOUT = getattr(m, "Layout", None)
if LAYOUT is None:
    check("the extractor describes a record layout as data", "no Layout in the module", "Layout")
    lay2 = None
else:
    lay2 = m.layout_from_dict(dict(V2))
    check("the extractor describes a record layout as data", lay2.fixture_rec, 70)

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    if lay2 is not None:
        (td / "DATA2025.AV").write_bytes(build_av(lay2, "Newtown CC", 2025, FIXTURES, MATCHES, PLAYERS))

        def unknown_msg():
            try:
                m.parse_file(td / "DATA2025.AV")
            except Exception as e:                              # noqa: BLE001
                return f"{type(e).__name__}: " + ("--analyse" if "--analyse" in str(e) else str(e))
            return "parsed without a layout"
        attempt("a file no layout describes is refused and points at --analyse",
                unknown_msg, "LayoutError: --analyse")

        # 2. described, then read by it
        lay_json = td / "v2.json"
        lay_json.write_text(json.dumps(V2))
        m.register_layouts(lay_json)
        s = m.parse_file(td / "DATA2025.AV")
        check("with its layout described, the file reads as that layout", s["layout"], "synthetic-v2")
        check("the club name comes from the layout's own header offset", s["club"], "Newtown CC")
        by_opp = {x["opponent"]: x for x in s["matches"]}
        check("fixtures are keyed by the slot they point at, not their position",
              sorted((x["opponent"], x["team"], x["date"].isoformat()) for x in s["matches"]),
              [("Fulham", 1, "2025-10-11"), ("Glenunga", 4, "2025-10-18"),
               ("Goodwood", 3, "2025-10-25")])
        check("the scorecard sits under its own fixture (Fulham 263/7, 101 by Smith)",
              (by_opp["Fulham"]["us"]["total"], by_opp["Fulham"]["blocks"][0]["runs"],
               s["players"][by_opp["Fulham"]["blocks"][0]["player_id"]]["surname"]),
              (263, 101, "Smith"))
        check("the club's result and match type are read at the layout's offsets",
              [(x["opponent"], x["result_code"], x["type_code"]) for x in s["matches"]],
              [("Fulham", 0, 4), ("Glenunga", 1, 9), ("Goodwood", 4, 4)])

        # 3. a layout is checked, not trusted
        refuses("an unknown layout field is refused, not ignored",
                lambda: m.layout_from_dict({**V2, "fixture_recc": 70}), "fixture_recc")
        refuses("a table running past the end of the file is refused",
                lambda: m.layout_from_dict({**V2, "match_n": 600}), "past the end")
        v1_size_garbage = bytearray(m.LAYOUT_V1.file_len)
        (td / "BAD2025.AV").write_bytes(bytes(v1_size_garbage))
        refuses("a file the right size for a layout but not shaped like it is refused",
                lambda: m.parse_file(td / "BAD2025.AV"), "not a year")

        # 4. the analyser finds the fixture table in a file nobody described
        many = [(i, datetime.date(2025, 10, 4) + datetime.timedelta(days=7 * i), (1, 3, 4)[i % 3],
                 f"Club {i}") for i in range(20)]
        info = m.probe_layout(build_av(lay2, "Newtown CC", 2025, many, {}, PLAYERS))
        fx = info["fixtures"] or {}
        check("--analyse finds the fixture table's record size in an unknown file",
              fx.get("record"), 70)
        cols = {c: v for c, v in fx.get("small_columns", [])}
        check("it flags the team column (few distinct values) by its distance from the date",
              {k for k in cols[V2["f_team"] - V2["f_date"]]} if V2["f_team"] - V2["f_date"] in cols else None,
              {1, 3, 4})
        check("it finds the opponent text beside it",
              (fx.get("text_at") or (None, None))[0], V2["f_name"] - V2["f_date"])

# ---------------------------------------------------------------------------
# 5. A club with no profile does not inherit Shoalwater Bay's names
# ---------------------------------------------------------------------------
if hasattr(m, "choose_profile"):
    prof = m.choose_profile("Payneham CC", None)
    m.activate(prof, "DATA")
    check("another club's team number is unnamed, not Shoalwater's grade",
          m.grade_label(18), "Grade #18 (unmapped)")
    check("another club's match type is unnamed, not Shoalwater's 'Two day'",
          m.match_type_label(1), "type 1")
    check("an unnamed match type states no format (never a guess)",
          m.match_format_for(1, set(), 1, 50.0, 0.0), "")
    m.FINALS_TYPES = frozenset({9})
    check("a final in a club whose formats are unknown stays blank, not 'One Day'",
          m.match_format_for(9, set(), 1, 50.0, 0.0), "")
    sh = m.choose_profile("Shoalwater Bay Cricket Club", None)
    m.activate(sh, "DATA")
    check("Shoalwater Bay's own profile is still chosen by its header name",
          (m.grade_label(18), m.match_type_label(4)), ("A grade", "One day"))
else:
    check("a club profile exists", "no choose_profile", "choose_profile")

# ---------------------------------------------------------------------------
# 6. End to end: two file families, an unprofiled club, a described layout
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    src, out = td / "src", td / "out"
    src.mkdir()
    if lay2 is not None:
        archive(src, lay2, {"DATA2025.AV": ("Payneham CC", 2025),
                            "DAT12025.AV": ("Payneham CC", 2025)})
    (td / "layout.json").write_text(json.dumps(V2))
    (td / "profile.json").write_text(json.dumps({
        "name": "payneham-test", "club": "payneham",
        "team_names": {"1": "1st XI", "3": "3rd XI"},
        "match_types": {"4": "Limited Over", "9": "Final"}, "finals_types": [9],
        "format_by_type": {"4": "One Day"},
        "families": {"DAT1": {"1": "Under 11", "3": "Under 13", "4": "Under 15"}}}))
    code, text_out = run("--layout", td / "layout.json", "--analyse", src)
    check("--analyse runs on the folder", code, 0)
    check("--analyse reports both file families and the layout it used",
          all(w in text_out for w in ("family DATA", "family DAT1", "synthetic-v2")), True)
    check("--analyse names the team numbers it found and that none has a name yet",
          "1 = Grade #1 (unmapped)" in text_out, True)
    check("--analyse writes nothing", out.exists(), False)

    code, text_out = run("--layout", td / "layout.json", src, "-o", out)
    check("extraction without a profile still runs and says what is unnamed",
          (code, "NO NAME GIVEN FOR" in text_out), (0, True))
    code, text_out = run("--layout", td / "layout.json", "--profile", td / "profile.json",
                         src, "-o", out)
    check("extraction with a profile runs", code, 0)
    files = sorted(p.name for p in out.glob("manual_games_scorecards*.csv"))
    check("one scorecard CSV per file family, never one mixed file",
          files, ["manual_games_scorecards_dat1.csv", "manual_games_scorecards_data.csv"])
    if len(files) == 2:
        data = read_csv(out / "manual_games_scorecards_data.csv")
        dat1 = read_csv(out / "manual_games_scorecards_dat1.csv")
        check("each family is filed under ITS OWN team names (the Fulham game, team 1)",
              ({r["grade_name"] for r in data if r["opposition"] == "Fulham"},
               {r["grade_name"] for r in dat1 if r["opposition"] == "Fulham"}),
              ({"1st XI"}, {"Under 11"}))
        check("a team the profile did not name is loud, not filed under another's (Glenunga, team 4)",
              ({r["grade_name"] for r in data if r["opposition"] == "Goodwood"},
               {r["grade_name"] for r in data if r["opposition"] == "Glenunga"}),
              ({"3rd XI"}, {"Grade #4 (unmapped)"}))
        check("game keys cannot collide between families",
              (data[0]["game_key"].split("-")[0], dat1[0]["game_key"].split("-")[0]),
              ("data2025", "dat12025"))
        # a final states no format: it is measured (this team played no two-day
        # cricket), and only where the profile knows the club's formats at all
        check("the profile's match types decide format and finals",
              ({(r["opposition"], r["match_format"], r["is_final"]) for r in data}),
              {("Fulham", "One Day", ""), ("Glenunga", "One Day", "true"), ("Goodwood", "One Day", "")})
        check("an abandoned match is blank, and still a match",
              {r["result"] for r in data if r["opposition"] == "Goodwood"}, {""})
        check("the club's result byte reaches the file (Fulham won, Glenunga lost)",
              ({r["result"] for r in data if r["opposition"] == "Fulham"},
               {r["result"] for r in data if r["opposition"] == "Glenunga"}),
              ({"WIN"}, {"LOSS"}))

# A single family keeps the file names and game keys it always had.
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    src, out = td / "src", td / "out"
    src.mkdir()
    if lay2 is not None:
        archive(src, lay2, {"DATA2025.AV": ("Payneham CC", 2025)})
        (td / "layout.json").write_text(json.dumps(V2))
        code, _ = run("--layout", td / "layout.json", "--team-names", "1=1st XI,3=3rd XI,4=4th XI",
                      src, "-o", out)
        rows = read_csv(out / "manual_games_scorecards.csv") if code == 0 else []
        check("one family: the plain file name and the year-based game key",
              (code, rows[0]["game_key"] if rows else None), (0, "2025-001"))
        check("--team-names names the teams with no profile",
              sorted({r["grade_name"] for r in rows}), ["1st XI", "3rd XI", "4th XI"])

# Two layouts in one folder: each file is read with its own.
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    src = td / "src"
    src.mkdir()
    if lay2 is not None:
        (src / "DATA2024.AV").write_bytes(
            build_av(m.LAYOUT_V1, "Payneham CC", 2024, FIXTURES, MATCHES, PLAYERS))
        (src / "DATA2025.AV").write_bytes(build_av(lay2, "Payneham CC", 2025, FIXTURES, MATCHES, PLAYERS))
        (td / "layout.json").write_text(json.dumps(V2))
        code, text_out = run("--layout", td / "layout.json", "--analyse", src)
        check("a folder mixing two layouts reads each file with its own",
              ("csfw-av-v1: 1 file" in text_out, "synthetic-v2: 1 file" in text_out), (True, True))

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
