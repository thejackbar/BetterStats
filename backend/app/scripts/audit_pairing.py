"""Cross-check a club's pairings and doubles against grade and against the numbers players see.

Read-only. Run it before and after `fix_wrong_links --apply` and read what it says it cannot prove.
Written because the doubles scan and the repair decide a pairing mostly on batters in common, and
a club that files several grades against one opposition on one day needs a second opinion that
looks at grade, at what is still counted twice, and at what the scan did not offer at all.

    python -m app.scripts.audit_pairing <org-id-or-slug> [--examples N]

Sections (each ends with OK or LOOK; LOOK lists the cards, 8-character ids, to read with explain_card):

  1. Every linked card against the game it is on: grade, batters, day, opposition.
  2. Grade names the grade test cannot read (those cards can never be swapped).
  3. What Possible doubles shows now, split by whether the two copies agree on grade.
  4. Free games the scan offered nothing for: an unlinked card with a free game the same day,
     opposition and grade, which a person would pair by eye.
  5. What a player still sees twice: the same score on the same day in two games.
"""
import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import timedelta

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import card_review as cr
from app.services import card_review_doubles as dbl
from app.services import match_pairing as mp

EXAMPLES = 8

_LINKED = """
    SELECT m.id::text AS mid, m.played_at, COALESCE(m.opposition, '') AS opposition, m.review_pair_ok,
           m.superseded_by_game_id::text AS gid, COALESCE(gr.display_name_override, gr.name) AS grade,
           g.played_at AS g_day, COALESCE(gg.display_name_override, gg.name) AS g_grade,
           CASE WHEN g.home_org_id = CAST(:org AS UUID) THEN g.away_team
                WHEN g.away_org_id = CAST(:org AS UUID) THEN g.home_team
                ELSE COALESCE(g.opp_club_name, g.home_team || ' v ' || g.away_team) END AS g_opp
      FROM manual_games m
      JOIN games g ON g.id = m.superseded_by_game_id
      LEFT JOIN grades gr ON gr.id = m.grade_id
      LEFT JOIN grades gg ON gg.id = g.grade_id
     WHERE m.organisation_id = CAST(:org AS UUID)
"""

_ALL_GRADES = """
    SELECT COALESCE(gr.display_name_override, gr.name) AS name, 'club cards' AS src, count(*) AS n
      FROM manual_games m JOIN grades gr ON gr.id = m.grade_id
     WHERE m.organisation_id = CAST(:org AS UUID) GROUP BY 1
    UNION ALL
    SELECT COALESCE(gr.display_name_override, gr.name), 'synced games', count(*)
      FROM grades gr JOIN seasons s ON s.id = gr.season_id JOIN games g ON g.grade_id = gr.id
     WHERE s.organisation_id = CAST(:org AS UUID) GROUP BY 1
"""

_TWICE = """
    SELECT p.name, e.played_at::date AS day, b.runs, count(DISTINCT b.game_id) AS games,
           array_agg(DISTINCT b.game_id::text) AS ids
      FROM v_effective_batting_innings b
      JOIN players p ON p.id = b.player_id AND p.organisation_id = CAST(:org AS UUID)
      JOIN v_effective_games e ON e.id = b.game_id
     WHERE COALESCE(b.did_not_bat, FALSE) = FALSE AND b.runs IS NOT NULL
     GROUP BY p.id, p.name, e.played_at::date, b.runs, b.innings_number
    HAVING count(DISTINCT b.game_id) > 1
     ORDER BY e.played_at::date DESC, p.name
"""


def _verdict(n: int) -> str:
    return "OK" if n == 0 else f"LOOK ({n})"


def _show(items: list, limit: int, fmt) -> None:
    for it in items[:limit]:
        print("      " + fmt(it))
    if len(items) > limit:
        print(f"      ... and {len(items) - limit} more")


def classify_link(card_grade, game_grade, shared: int, club_n: int, game_n: int, confirmed: bool, person_ok: bool) -> str:
    """One word for a linked pair. Pure, so the suite can drive every branch."""
    gk, hk = dbl.grade_key(card_grade), dbl.grade_key(game_grade)
    differs = bool(gk and hk and gk != hk)
    unreadable = not (gk and hk)
    if person_ok:
        return "person_ok_grade_differs" if differs else "person_ok"
    if confirmed:
        if differs:
            return "proved_grade_names_differ"
        return "proved_grade_unreadable" if unreadable else "proved"
    if club_n and game_n:  # both hold batters and they do not agree
        return "contradicted_grade_differs" if differs else "contradicted"
    if differs:
        return "unproven_grade_differs"
    return "unproven_grade_unreadable" if unreadable else "unproven_same_grade"


async def audit(db, org_id: str, *, examples: int = EXAMPLES) -> dict:
    out: dict = {}
    # 1. linked pairs
    rows = [dict(r) for r in (await db.execute(text(_LINKED), {"org": org_id})).mappings().all()]
    mine = await mp._cards(db, mp._IMPORTED_CARD_SQL, {"ids": [r["mid"] for r in rows]}) if rows else {}
    theirs = await mp._cards(db, mp._SYNCED_CARD_SQL, {"org": org_id, "ids": sorted({r["gid"] for r in rows})}) if rows else {}
    by: dict = defaultdict(list)
    day_off = opp_off = 0
    for r in rows:
        a, b = set(mine.get(r["mid"], ())), set(theirs.get(r["gid"], ()))
        r["shared"], r["club_n"], r["game_n"] = len(a & b), len(a), len(b)
        v = classify_link(r["grade"], r["g_grade"], r["shared"], len(a), len(b), cr.confirms_pair(a, b), bool(r["review_pair_ok"]))
        by[v].append(r)
        if mp._day_gap(r["played_at"], r["g_day"]) not in (0, None):
            day_off += 1
        if not mp.teams_agree(r["opposition"], r["g_opp"] or ""):
            opp_off += 1
    out["links"] = {k: len(v) for k, v in by.items()} | {"total": len(rows), "day_off": day_off, "opp_off": opp_off}
    bad = ["contradicted_grade_differs", "unproven_grade_differs", "person_ok_grade_differs"]
    weak = ["contradicted", "unproven_same_grade", "unproven_grade_unreadable"]
    note = ["proved_grade_names_differ", "proved_grade_unreadable"]
    out["links_bad"] = sum(len(by[k]) for k in bad)
    print(f"\n1. Linked cards against the game they are on ({len(rows)} linked)")
    for k in ("proved", "person_ok") + tuple(note) + tuple(weak) + tuple(bad):
        if by.get(k):
            print(f"   {len(by[k]):>5}  {k}")
    print(f"   {day_off:>5}  on a game dated a different day   {opp_off:>5}  on a game whose opposition name disagrees")
    for k, why in (("contradicted_grade_differs", "both hold batters, they disagree AND the grades differ: almost certainly a wrong link"),
                   ("unproven_grade_differs", "no batters to prove it AND the grades differ: almost certainly a wrong link"),
                   ("person_ok_grade_differs", "a person confirmed it, but the grades differ: worth a second look"),
                   ("contradicted", "same grade, but the batters disagree"),
                   ("unproven_same_grade", "same grade, nothing to prove it either way"),
                   ("proved_grade_names_differ", "batters agree but the grade names differ (a renamed grade, or the wrong grade on the card)")):
        if by.get(k):
            print(f"   {k}: {why}")
            _show(by[k], examples, lambda r: f"[{r['mid'][:8]}] {r['played_at']} {r['grade']} v {r['opposition']}  ->  {r['g_grade']} v {r['g_opp']}"
                                              f"  ({r['shared']} shared; {r['club_n']} v {r['game_n']} batters)")
    print("   " + _verdict(out["links_bad"]) + ("" if not by.get("contradicted") and not by.get("unproven_same_grade") else
                                              f"   (plus {len(by.get('contradicted', [])) + len(by.get('unproven_same_grade', []))} same-grade links nothing proves)"))

    # 2. grade names the test cannot read
    names = Counter()
    for r in (await db.execute(text(_ALL_GRADES), {"org": org_id})).mappings().all():
        if r["name"] and not dbl.grade_key(r["name"]):
            names[(r["name"], r["src"])] += r["n"]
    out["unreadable_grades"] = len(names)
    print(f"\n2. Grade names the grade test cannot read ({len(names)}): cards and games in them are never swapped, and are compared on batters alone")
    _show(sorted(names.items(), key=lambda kv: -kv[1]), examples * 2, lambda kv: f"{kv[1]:>5}  {kv[0][0]!r}  ({kv[0][1]})")
    print("   " + _verdict(len(names)))

    # 3. the doubles list, by grade agreement
    found = await dbl.find_doubles(db, org_id)
    shown = Counter()
    odd = []
    for r in found["rows"]:
        ka, kb = dbl.grade_key(r["a"].get("grade")), dbl.grade_key(r["b"].get("grade"))
        agree = "unreadable" if not (ka and kb) else "agree" if ka == kb else "DIFFER"
        shown[(r["kind"], r["strength"], agree)] += 1
        if agree == "DIFFER":
            odd.append(r)
    out["doubles_grade_differ"] = len(odd)
    out["doubles_total"] = len(found["rows"])
    print(f"\n3. Possible doubles now shows {len(found['rows'])} row(s); by kind, strength and whether the two copies agree on grade")
    for (kind, strength, agree), n in sorted(shown.items()):
        print(f"   {n:>5}  {kind:<7}{strength:<9}grade {agree}")
    _show(odd, examples, lambda r: f"[{r['a']['id'][:8]}] {r['kind']}/{r['strength']}  {r['a'].get('grade')} v {r['a'].get('opposition')} "
                                   f"{r['date']}  vs  {r['b'].get('grade')} v {r['b'].get('opposition')}")
    print("   " + _verdict(len(odd)) + ("   (rows pairing two different grades: the list is showing nonsense)" if odd else ""))

    # 4. free games the scan did not offer
    club_cards = [dict(r) for r in (await db.execute(text(dbl._MANUALS), {"org": org_id})).mappings().all()]
    tokens = mp.team_tokens((await db.execute(text(mp._CLUB_NAME_SQL), {"org": org_id})).scalar() or "")
    offered = {r["a"]["id"] for r in found["rows"]} | {r["b"]["id"] for r in found["rows"]}
    dismissed = {(d["mid"], d["other"]) for d in await dbl.dismissed_pairs(db, org_id)}
    missed = []
    unlinked = [m for m in club_cards if not m["linked"] and m["played_at"]]
    if unlinked:
        days = [m["played_at"] for m in unlinked]
        free = await mp.load_synced(db, org_id, club_tokens=tokens, exclude_twinned=True,
                                    from_day=min(days) - timedelta(days=1), to_day=max(days) + timedelta(days=1))
        grades = {g["gid"]: g["grade_name"] for g in await dbl._all(
            db, dbl._SYNCED_DETAIL, org=org_id, ids=sorted({g.id for g in free}))} if free else {}
        by_day: dict = defaultdict(list)
        for g in free:
            by_day[g.played_at].append(g)
        for m in unlinked:
            if m["mid"] in offered:
                continue
            mk = dbl.grade_key(m["grade_name"])
            ours, opp = mp.split_sides(m["home_team"], m["away_team"], m["opposition"], tokens)
            for g in by_day.get(m["played_at"], ()):
                if mk and mk == dbl.grade_key(grades.get(g.id)) and mp.teams_agree(opp, g.opposition) \
                        and (m["mid"], g.id) not in dismissed:
                    missed.append((m, g, grades.get(g.id)))
    out["missed"] = len(missed)
    print(f"\n4. Unlinked cards with a free game on the same day, opposition and grade that the scan did not offer ({len(unlinked)} unlinked cards)")
    _show(missed, examples, lambda t: f"[{t[0]['mid'][:8]}] {t[0]['played_at']} {t[0]['grade_name']} v {t[0]['opposition']}  could take  game {t[1].id[:8]} ({t[2]})")
    print("   " + _verdict(len(missed)))

    # 5. what a player still sees twice
    twice = [dict(r) for r in (await db.execute(text(_TWICE), {"org": org_id})).mappings().all()]
    out["counted_twice"] = len(twice)
    print(f"\n5. The same score by the same player on the same day in two games (counted twice on a profile) ({len(twice)})")
    _show(twice, examples, lambda r: f"{r['day']}  {r['name']}  {r['runs']} runs in {r['games']} games ({', '.join(i[:8] for i in r['ids'])})")
    print("   " + _verdict(len(twice)) + ("   (a player can score the same in two games on one day only if the club played two matches: check the dates)" if twice else ""))

    print("\nWhat this cannot prove: a pair with no batters on either side and a readable, matching grade is accepted"
          " on grade, day and opposition alone. Section 1 counts those as 'unproven_same_grade'.")
    return out


async def main(target: str, examples: int) -> int:
    async with async_session_maker() as db:
        rows = (await db.execute(text("SELECT id::text, name FROM organisations WHERE id::text = :t OR slug = :t"), {"t": target})).all()
        if not rows:
            print(f"No club '{target}'.")
            return 2
        print(f"AUDIT (read-only): {rows[0][1]}")
        await audit(db, rows[0][0], examples=examples)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Read-only cross-check of a club's pairings and doubles.")
    ap.add_argument("org", help="club id or slug")
    ap.add_argument("--examples", type=int, default=EXAMPLES)
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main(args.org, args.examples)))
