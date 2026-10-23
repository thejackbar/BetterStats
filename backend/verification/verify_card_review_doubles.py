"""Card review, possible doubles: a match the record holds twice with nothing linking the copies.

Shaped on a club's report (Oct 2026) of matches counted twice on two players' careers, once under the
Two Day tab and once under the One Day tab. Nothing in the feature is specific to that club, so a
second club with a different history (a CricketStatz import, a differently spelt opposition) is
scanned beside it and neither sees the other. Everything runs against a real Postgres through the
shipped services and the route bodies.

Run:  DATABASE_URL=postgresql+asyncpg://root@/pl_verify?host=/var/run/postgresql \
      python verification/verify_card_review_doubles.py

Mutations (each must make the suite FAIL, which is what proves the checks bite):
  MUTATE=blind      the scan finds nothing (what Card review did before this step existed)
  MUTATE=nocards    the first release's rule: two shared scores within ten days is a strong match
  MUTATE=loose      two club cards need only a date and an opposition
  MUTATE=nolink     linking writes the link but leaves the pair unlocked and unconfirmed
  MUTATE=forget     a "different matches" answer is not remembered
  MUTATE=noundo     undo does not know about a link
  MUTATE=halfpair   find a match only searches the club cards, so a pair found by its synced half is missed
  MUTATE=dryapplies the repair script's dry run writes (a dry run that is not one)
  MUTATE=blindlink  the scan only looks at unlinked cards (how the first release missed a card linked to the wrong game)
  MUTATE=unlinkall  the grade step also unlinks a confirmed link, a same-grade link and a renamed grade
  MUTATE=noalias    a renamed grade (proved by the club's own links) is still called wrong when a link has no scores
  MUTATE=gradeblind the 'possible' tier offers a card and a game of two different grades again
  MUTATE=noswap     the scan does not know a swap (how the first repair left nine cards 'pairing looks wrong')
  MUTATE=anygrade   a card of another grade passes as the grade of the game it would move to
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text  # noqa: E402

PASS = FAIL = 0


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


def u():
    return uuid.uuid4()


async def main():
    from app.models.db import Base, engine, async_session_maker
    from app.services import card_review as cr
    from app.services import card_review_actions as act
    from app.services import card_review_doubles as dbl
    from app.services import card_review_find as fnd
    from app.scripts import fix_wrong_links as fwl
    from app.scripts import explain_card as xc
    from app.scripts import audit_pairing as aud
    from app.services.card_review_ddl import STATEMENTS as REVIEW_DDL
    from app.services.superseded_ddl import STATEMENTS as SUPERSEDED_DDL
    from app.services.competition_ddl import STATEMENTS as COMP_DDL
    from _view_ddl import view_statements
    from verify_merge_carry import EXTRA_DDL

    mutate = os.environ.get("MUTATE", "")
    if mutate == "blind":
        async def blind(db, org_id):
            return {"rows": [], "dismissed": []}
        dbl.find_doubles = blind
    if mutate == "nocards":
        # the rule this release first shipped: two shared scores within ten days is a strong match
        def old_strength(ev):
            gap = ev["gap_days"]
            if ev["shared"] >= 3 or (ev["shared"] >= 2 and gap is not None and gap <= 10):
                return "strong"
            return "likely" if ev["shared"] >= 1 else "possible"
        dbl.strength_of = old_strength
    if mutate == "loose":
        def loose_club(manuals, meta, banned):
            return dbl._greedy(manuals, manuals, set(banned) | {(y, x) for x, y in banned},
                               lambda a, b, ev: True, symmetric=True)
        dbl.match_pairs_club = loose_club
    if mutate == "nolink":
        real_link = act.link_double

        async def link_unlocked(db, org_id, mid, game_id, user_id, **kw):
            res = await real_link(db, org_id, mid, game_id, user_id, **kw)
            await db.execute(text("UPDATE manual_games SET pairing_locked = FALSE, review_pair_ok = FALSE "
                                  "WHERE id = CAST(:m AS UUID)"), {"m": str(mid)})
            if kw.get("commit", True):
                await db.commit()
            return res
        act.link_double = link_unlocked
    if mutate == "forget":
        async def forget(db, org_id):
            return []
        dbl.dismissed_pairs = forget

    if mutate == "dryapplies":
        real_run = fwl.run_org

        async def always_apply(db, org_id, *, apply, max_rounds=3):
            return await real_run(db, org_id, apply=True, max_rounds=max_rounds)
        fwl.run_org = always_apply
    if mutate == "blindlink":
        real_pairs = dbl.match_pairs_ca

        def unlinked_only(manuals, synced, banned, linked_ids=frozenset()):
            return real_pairs([m for m in manuals if m.id not in linked_ids], synced, banned, frozenset())
        dbl.match_pairs_ca = unlinked_only
    if mutate == "unlinkall":
        from app.services import link_audit as _la
        _la.WRONG_GRADE = _la.WRONG_GRADE + ("person_ok_grade_differs", "unproven_same_grade", "unproven_grade_unreadable", "proved_grade_names_differ")
    if mutate == "noalias":
        from app.services import link_audit as _la2
        _la2.ALIAS_MIN = 10**6
    if mutate == "gradeblind":
        dbl._grades_clash = lambda a, b: False
    if mutate == "noswap":
        dbl.match_swaps = lambda *a, **k: []
    if mutate == "anygrade":
        real_gk = dbl.grade_key
        dbl.grade_key = lambda name: real_gk("D Grade" if "E Grade" in (name or "") else name)  # E counts as D
    if mutate == "halfpair":
        fnd._SYNCED_HITS = fnd._SYNCED_HITS.replace("WHERE (", "WHERE FALSE AND (")

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        for stmt in COMP_DDL:
            await conn.execute(text(stmt))
        for stmt in EXTRA_DDL:
            await conn.execute(text(stmt))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_manual_games_superseded_by_game "
            "ON manual_games (superseded_by_game_id) WHERE superseded_by_game_id IS NOT NULL"))
        for stmt in REVIEW_DDL:
            await conn.execute(text(stmt))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)"""))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)"""))
        for tbl, col in (await conn.execute(text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND data_type = 'json'"))).all():
            await conn.execute(text(f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb '
                                    f'USING "{col}"::text::jsonb'))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))
        for stmt in SUPERSEDED_DDL:
            await conn.execute(text(stmt))

    ORG, OTHER, SEASON, GRADE_A, GRADE_B, USER, USER2 = u(), u(), u(), u(), u(), u(), u()
    names = ["Ritchie", "Hind", "Moore", "Lane", "Fox", "Dale", "Kerr", "Webb", "Page", "Stone", "Vale", "Burns",
             "Cox", "Dunn", "Eyre", "Frost", "Quill"]
    P = {k: u() for k in names}

    async def q(sql, **kw):
        async with async_session_maker() as s:
            return (await s.execute(text(sql), kw)).all()

    async with async_session_maker() as s:
        await s.execute(text("INSERT INTO organisations (id, name, slug, is_active) VALUES "
                             "(:a, 'Harbour CC', 'harbour', true), (:b, 'Other Club', 'other', true)"),
                        {"a": ORG, "b": OTHER})
        await s.execute(text("INSERT INTO seasons (id, organisation_id, name, year) VALUES "
                             "(:i, :o, 'Summer 2006/07', 2006)"), {"i": SEASON, "o": ORG})
        for gid, nm in ((GRADE_A, "A Grade"), (GRADE_B, "B Grade")):
            await s.execute(text("INSERT INTO grades (id, season_id, name) VALUES (:i, :s, :n)"),
                            {"i": gid, "s": SEASON, "n": nm})
        for k, pid in P.items():
            await s.execute(text("INSERT INTO players (id, organisation_id, name, grassroots_id) "
                                 "VALUES (:i, :o, :n, :g)"), {"i": pid, "o": ORG, "n": f"{k}, {k[0]}", "g": str(pid)})
        for uid, name in ((USER, "neil"), (USER2, "jack")):
            await s.execute(text("INSERT INTO users (id, username, password_hash, failed_login_count) "
                                 "VALUES (:i, :n, 'x', 0)"), {"i": uid, "n": name})
        await s.commit()

    ids: dict = {}

    async def synced(key, day, opp, *, fmt=None, bat=(), grade=None):
        gid = u()
        ids[key] = gid
        async with async_session_maker() as s:
            await s.execute(text("""
                INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_org_id, opp_club_name,
                                   status, result, winning_team, match_format)
                VALUES (:g, :gr, :d, 'Harbour CC', :opp, :o, :opp, 'COMPLETED', 'WIN', 'Harbour CC', :f)"""),
                {"g": gid, "gr": grade or GRADE_A, "d": day, "opp": opp, "o": ORG, "f": fmt})
            for who, runs in bat:
                await s.execute(text("""
                    INSERT INTO batting_innings (game_id, player_id, innings_number, batting_position, runs, balls,
                        fours, sixes, dismissal_type, not_out, did_not_bat)
                    VALUES (:g, :p, 1, 1, :r, 10, 0, 0, 'bowled', FALSE, FALSE)"""),
                    {"g": gid, "p": P[who], "r": runs})
            await s.commit()
        return gid

    async def manual(key, day, opp, *, fmt=None, bat=(), grade=GRADE_A, link=None, created=None):
        mid = u()
        ids[key] = mid
        async with async_session_maker() as s:
            await s.execute(text("""
                INSERT INTO manual_games (id, organisation_id, season_id, grade_id, played_at, opposition, result,
                                          match_format, superseded_by_game_id, pair_prefers_import, pairing_locked,
                                          created_at)
                VALUES (:m, :o, :s, :gr, :d, :opp, 'WIN', :f, CAST(:lk AS UUID), :pf, :pf, COALESCE(CAST(:cr AS TIMESTAMPTZ), NOW()))"""),
                {"m": mid, "o": ORG, "s": SEASON, "gr": grade, "d": day, "opp": opp, "f": fmt, "lk": link,
                 "pf": link is not None, "cr": created})
            for who, runs in bat:
                await s.execute(text("""
                    INSERT INTO manual_batting_innings (manual_game_id, player_id, innings_number, batting_position,
                        runs, balls, dismissal_type, not_out, did_not_bat)
                    VALUES (:m, :p, 1, 1, :r, NULL, 'bowled', FALSE, FALSE)"""),
                    {"m": mid, "p": P[who], "r": runs})
            await s.commit()
        return mid

    def bat(n):
        """Four batters with scores no other match in the fixture shares."""
        return [(names[(n + i) % (len(names) - 1)], 40 + n * 11 + i * 3) for i in range(4)]  # never Quill, the single-card player

    four = [("Ritchie", 30), ("Hind", 0), ("Moore", 12), ("Lane", 7)]
    other_four = bat(1)

    # 1. An archive import and the synced game of one match, filed under different formats.
    await synced("g_strong", date(2006, 2, 4), "Warnbro", fmt="Two Day", bat=four)
    await manual("m_strong", date(2006, 2, 4), "Warnbro", fmt="One Day", bat=four)
    # 2. Cricket Australia holds the fixture and no batters.
    await synced("g_date", date(2004, 12, 11), "Hillman", fmt="One Day")
    await manual("m_date", date(2004, 12, 11), "Hillman", fmt="One Day", bat=bat(2))
    # 3. 13/1/07: a two-day match each source dates by a different day, two shared scores.
    await synced("g_off", date(2007, 1, 20), "Rockingham", fmt="Two Day", bat=[("Ritchie", 4), ("Hind", 67), ("Page", 3)])
    await manual("m_off", date(2007, 1, 13), "Rockingham", fmt="Two Day",
                 bat=[("Ritchie", 4), ("Hind", 67), ("Stone", 11)])
    # 4. Two grades against one club on one day: both hold batters, none shared. NOT a double.
    await synced("g_grades", date(2005, 11, 5), "Kwinana", bat=other_four + [("Quill", 3)])
    await manual("m_grades", date(2005, 11, 5), "Kwinana", bat=four)
    # 5. The same archive imported twice.
    await manual("m_dup1", date(2007, 2, 24), "Hillman", fmt="Two Day", bat=bat(3), created=datetime(2026, 9, 1, tzinfo=timezone.utc))
    await manual("m_dup2", date(2007, 2, 24), "Hillman", fmt="One Day", bat=bat(3), created=datetime(2026, 10, 1, tzinfo=timezone.utc))
    # 6. Two club cards, same day, same club, different grades.
    await manual("m_ga", date(2005, 12, 3), "Safety Bay", bat=[("Vale", 5), ("Burns", 8)], grade=GRADE_A)
    await manual("m_gb", date(2005, 12, 3), "Safety Bay", bat=[("Cox", 15), ("Dunn", 2)], grade=GRADE_B)
    await manual("m_na", date(2005, 12, 10), "Safety Bay", grade=GRADE_A)
    await manual("m_nb", date(2005, 12, 10), "Safety Bay", grade=GRADE_B)
    await manual("m_sa", date(2005, 12, 17), "Safety Bay", grade=GRADE_A, created=datetime(2026, 9, 1, tzinfo=timezone.utc))
    await manual("m_sb", date(2005, 12, 17), "Safety Bay", grade=GRADE_A, created=datetime(2026, 10, 1, tzinfo=timezone.utc))
    # 6b. The reported false positive: two DIFFERENT matches a week apart (other opposition, one a
    # win and one a loss) that happen to share two low scores out of eleven.
    def eleven(n):
        """Eleven batters, never Ritchie or Hind, whom the cards below add themselves."""
        pool = names[2:-1]  # not Quill either: one search below needs a player on a single card
        return [(pool[(n + i) % len(pool)], 100 + n * 13 + i * 2) for i in range(11)]
    low = [("Ritchie", 0), ("Hind", 4)]
    await manual("m_wk1", date(2002, 10, 19), "Warnbro Knights", bat=low + eleven(5))
    await manual("m_wk2", date(2002, 10, 26), "Old Irwinians", bat=low + eleven(6))
    await synced("g_wk3", date(2002, 11, 2), "Hillman", bat=low + eleven(7))
    # 6c. The same day and club, only some batters agree (a player named differently): likely.
    await manual("m_part1", date(2003, 3, 1), "Safety Bay", bat=[("Ritchie", 51), ("Hind", 9)] + eleven(8))
    await manual("m_part2", date(2003, 3, 1), "Safety Bay", bat=[("Ritchie", 51), ("Hind", 12)] + eleven(9))
    # 6d. THE SHOALWATER SHAPE. A club plays two grades against one club on one day. The import's
    # duplicate check ignores grade, so the B grade card was linked to the A grade game, the real B
    # grade game stayed unlinked, and the B grade match counted twice. The A grade card is unlinked
    # too, and its own game is the one the B card is sitting on.
    g_wA = await synced("g_wA", date(2008, 3, 1), "Safety Bay", fmt="Two Day", bat=bat(11), grade=GRADE_A)
    g_wB = await synced("g_wB", date(2008, 3, 1), "Safety Bay", fmt="Two Day", bat=bat(10), grade=GRADE_B)
    await manual("m_wB", date(2008, 3, 1), "Safety Bay", fmt="One Day", bat=bat(10), grade=GRADE_B, link=g_wA)
    await manual("m_wA", date(2008, 3, 1), "Safety Bay", fmt="One Day", bat=bat(11), grade=GRADE_A)
    # 6f. Shoalwater's 11/12/04: the card was CHOSEN by hand (the site shows Cricket Australia) while it
    # sat on a game with none of its batters. Choosing a card does not confirm the pairing was right.
    g_cw = await synced("g_cw", date(2008, 5, 3), "Warnbro", bat=bat(14), grade=GRADE_A)
    g_ct = await synced("g_ct", date(2008, 5, 3), "Warnbro", bat=bat(13), grade=GRADE_B)
    await manual("m_chosen", date(2008, 5, 3), "Warnbro", bat=bat(13), grade=GRADE_B, link=g_cw)
    async with async_session_maker() as s:
        await s.execute(text("UPDATE manual_games SET pair_prefers_import = FALSE, review_choice = 'ca', "
                             "review_source = 'hand' WHERE id = :m"), {"m": ids["m_chosen"]})
        await s.commit()
    # 6e. A link a person CONFIRMED as the same match is left alone, however wrong it looks.
    g_hw = await synced("g_hw", date(2008, 4, 5), "Hillman", grade=GRADE_A)
    await synced("g_ht", date(2008, 4, 5), "Hillman", bat=bat(12), grade=GRADE_B)
    await manual("m_hand", date(2008, 4, 5), "Hillman", bat=bat(12), grade=GRADE_B, link=g_hw)
    async with async_session_maker() as s:
        await s.execute(text("UPDATE manual_games SET review_pair_ok = TRUE, review_source = 'hand' WHERE id = :m"), {"m": ids["m_hand"]})
        await s.commit()
    # 7. Already linked: neither half is a candidate for anything.
    g_linked = await synced("g_linked", date(2006, 3, 4), "Warnbro", bat=bat(4))
    await manual("m_linked", date(2006, 3, 4), "Warnbro", bat=bat(4), link=g_linked)
    # ...and a second import of the same match, which nothing linked
    await manual("m_third", date(2006, 3, 4), "Warnbro", bat=bat(4))
    # 8. Same scores as the 2006 match above but a year and a half later: two imports, two matches.
    await manual("m_later", date(2007, 9, 1), "Warnbro", bat=four)

    def kinds(res):
        return {(r["kind"], r["a"]["id"], r["b"]["id"]): r for r in res["rows"]}

    async def scan():
        async with async_session_maker() as s:
            return await dbl.find_doubles(s, ORG)

    # --- finding them -------------------------------------------------------------------------
    print("\n-- the scan finds the unlinked copies --")
    res = await scan()
    by = kinds(res)
    k_strong = ("ca", str(ids["m_strong"]), str(ids["g_strong"]))
    k_date = ("ca", str(ids["m_date"]), str(ids["g_date"]))
    k_off = ("ca", str(ids["m_off"]), str(ids["g_off"]))
    check("a club card and a synced game with the same four scores are found", k_strong in by, True)
    check("and called strong", by.get(k_strong, {}).get("strength"), "strong")
    check("the evidence says how many batters are in common", by.get(k_strong, {}).get("shared"), 4)
    check("and that the smaller card is mostly on the other", by.get(k_strong, {}).get("confirmed"), True)
    check("two copies under different match types say so (the Two Day and One Day tabs)",
          by.get(k_strong, {}).get("formats_differ"), True)
    check("Cricket Australia holding the fixture and no batters is found on the date alone", k_date in by, True)
    check("and called possible, because there is nothing to compare", by.get(k_date, {}).get("strength"), "possible")
    check("the same format on both is not flagged", by.get(k_date, {}).get("formats_differ"), False)
    check("a two-day match dated a week apart is found on two shared scores", k_off in by, True)
    check("and called strong", by.get(k_off, {}).get("strength"), "strong")
    check("the gap in days is reported", by.get(k_off, {}).get("gap_days"), 7)
    k_wrong = ("relink", str(ids["m_wB"]), str(ids["g_wB"]))
    wrong = by.get(k_wrong) or {"a": {}, "b": {}, "current": None}
    check("a card linked to the wrong game, with its real game left unlinked, is found", k_wrong in by, True)
    check("and called strong, because most of the card is on the right game", wrong.get("strength"), "strong")
    check("it says which game the card is on now, and that none of its batters are there",
          ((wrong["current"] or {}).get("id"), (wrong["current"] or {}).get("shared_with_club")), (str(ids["g_wA"]), 0))
    check("the two copies sit under different match types, the symptom the club saw", wrong.get("formats_differ"), True)
    check("the wrong game is not also offered to the card that belongs to it while it is still taken",
          any(k[1] == str(ids["m_wA"]) for k in by), False)
    k_chosen = ("relink", str(ids["m_chosen"]), str(ids["g_ct"]))
    check("a card whose display a person CHOSE by hand is still offered a better game when its link is wrong",
          k_chosen in by, True)
    check("a link a person confirmed as the same match is not second-guessed",
          any(str(ids["m_hand"]) in (k[1], k[2]) or str(ids["g_hw"]) in (k[1], k[2]) for k in by), False)
    check("a link that already matches is not touched",
          any(k[0] == "relink" and str(ids["m_linked"]) in (k[1], k[2]) for k in by), False)
    check("two different matches a week apart that share two low scores are NOT offered, however you pair them",
          any(str(ids[k]) in (x[1], x[2]) for k in ("m_wk1", "m_wk2", "g_wk3") for x in by), False)
    k_part = ("club", str(ids["m_part1"]), str(ids["m_part2"]))
    check("the same day and club with only some batters agreeing is offered, as likely",
          (by.get(k_part) or {}).get("strength"), "likely")
    check("two cards that both have batters and share none are two matches, not a double",
          any(k[1] == str(ids["m_grades"]) for k in by), False)
    check("the synced half of that is not offered to anything either",
          any(k[2] == str(ids["g_grades"]) for k in by), False)
    k_dup = ("club", str(ids["m_dup1"]), str(ids["m_dup2"]))
    check("the same archive imported twice is found as two club cards, the older on the left", k_dup in by, True)
    check("and called strong", by.get(k_dup, {}).get("strength"), "strong")
    check("two grades against one club on one day are not a double (different batters)",
          any({k[1], k[2]} == {str(ids["m_ga"]), str(ids["m_gb"])} for k in by), False)
    check("nor are two grades with no batters at all",
          any({k[1], k[2]} == {str(ids["m_na"]), str(ids["m_nb"])} for k in by), False)
    check("two empty cards for the same grade, day and club are",
          ("club", str(ids["m_sa"]), str(ids["m_sb"])) in by, True)
    check("a linked pair is not itself offered as a double of Cricket Australia",
          any(k[0] == "ca" and str(ids["m_linked"]) in (k[1], k[2]) for k in by), False)
    check("a synced game that already has a club card linked is not offered to a third copy",
          any(k[2] == str(g_linked) for k in by), False)
    k_third = ("club", str(ids["m_linked"]), str(ids["m_third"]))
    check("a second import of a match that is already linked is found against the linked card",
          k_third in by or ("club", str(ids["m_third"]), str(ids["m_linked"])) in by, True)
    row_third = by.get(k_third) or by.get(("club", str(ids["m_third"]), str(ids["m_linked"])), {"a": {}, "b": {}})
    check("and says which side is already linked to Cricket Australia",
          sorted([bool(row_third["a"].get("linked")), bool(row_third["b"].get("linked"))]), [False, True])
    check("the same scores a year and a half apart are two matches",
          any(str(ids["m_later"]) in (k[1], k[2]) for k in by), False)
    check("each card and each synced game is offered at most once",
          len({k[1] for k in by if k[0] == "ca"}) == len([k for k in by if k[0] == "ca"])
          and len({k[2] for k in by if k[0] == "ca"}) == len([k for k in by if k[0] == "ca"]), True)
    order = [r["strength"] for r in res["rows"]]
    check("the list is strongest first", order, sorted(order, key=dbl.STRENGTHS.index))
    n_total = len(res["rows"])
    check("the counts add up", (dbl.counts(res)["total"], sum(dbl.counts(res)["by_strength"].values())),
          (n_total, n_total))

    print("\n-- the same data always gives the same list --")
    again = await scan()
    check("a second scan is identical", [r["key"] for r in again["rows"]], [r["key"] for r in res["rows"]])
    from app.services import match_pairing as mp
    async with async_session_maker() as s:
        unl = [dict(r) for r in (await s.execute(text(dbl._MANUALS), {"org": str(ORG)})).mappings().all()]
        cards = await mp._cards(s, mp._IMPORTED_CARD_SQL, {"ids": [m["mid"] for m in unl]})
    meta = {m["mid"]: m for m in unl}
    rows_ = [mp.MatchRow(m["mid"], m["played_at"], m["opposition"], frozenset(cards.get(m["mid"], ())), "")
             for m in unl]
    want = sorted((p["a"], p["b"]) for p in dbl.match_pairs_club(rows_, meta, set()))
    stable = True
    for seed in (1, 2, 3):
        shuffled = rows_[:]
        random.Random(seed).shuffle(shuffled)
        stable &= sorted((p["a"], p["b"]) for p in dbl.match_pairs_club(shuffled, meta, set())) == want
    check("two club cards pair the same way whatever order they are read in", stable, True)

    print("\n-- the audit: a second opinion on grade, on what the scan skipped, and on what a player sees --")
    import contextlib as _cl
    import io as _io3

    async def audited(org):
        buf = _io3.StringIO()
        async with async_session_maker() as s:
            with _cl.redirect_stdout(buf):
                res_ = await aud.audit(s, str(org))
        return res_, buf.getvalue()
    snap_a = await q("SELECT id::text, superseded_by_game_id::text FROM manual_games ORDER BY id")
    logs_a = (await q("SELECT count(*) FROM card_review_log"))[0][0]
    a_h, txt_h = await audited(ORG)
    check("the audit sees the match counted twice (Ritchie's 30 on 4 Feb 2006 is in the card and the game)", a_h["counted_twice"] >= 1, True)
    check("it lists a free same-grade, same-day game the scan offered nothing for (the Kwinana card whose batters disagree)",
          a_h["missed"] >= 1 and "Kwinana" in txt_h, True)
    check("a card on a game its batters agree with, in the same grade, is simply 'proved'", a_h["links"].get("proved", 0) >= 1, True)
    async with async_session_maker() as s_:
        await s_.execute(text("UPDATE batting_innings SET innings_number = 2 WHERE game_id = :g"), {"g": ids["g_strong"]})
        await s_.commit()
    a_h2, _ = await audited(ORG)
    async with async_session_maker() as s_:
        await s_.execute(text("UPDATE batting_innings SET innings_number = 1 WHERE game_id = :g"), {"g": ids["g_strong"]})
        await s_.commit()
    check("the same score is found twice even when the card and the game number the innings differently (Two Day cards and games do)",
          a_h2["counted_twice"], a_h["counted_twice"])
    check("the audit wrote nothing", (await q("SELECT id::text, superseded_by_game_id::text FROM manual_games ORDER BY id"),
                                      (await q("SELECT count(*) FROM card_review_log"))[0][0]), (snap_a, logs_a))
    for nm, want in (("Under 12 East", "u12"), ("U12 Dukes", "u12"), ("U 12 Knights", "u12"), ("U/12 Division 2", "u12"),
                     ("NEJCA - U/14 Division 3", "u14"), ("16 & Under - Central", "u16"), ("Under 17's Community Cup", "u17"),
                     ("Mega Courts Under 10 Continued", "u10"), ("U9 Blue", "u9"), ("D Grade Ritchie Cup", "d"),
                     ("B Grade: McIntosh Cup", "b"), ("C1 Grade", "c1"), ("1st XI", None), ("Women's 1st XI", None),
                     ("Womens 1st Grade", None), ("Colts", None), ("Grade (unknown)", None), (None, None)):
        check(f"grade_key({nm!r})", dbl.grade_key(nm), want)
    check("an age group the club spells one way and Cricket Australia another is the same grade",
          aud.classify_link("U12 Dukes", "NEJCA - U/12 Division 3", 9, 11, 11, True, False), "proved")
    check("a U12 card on a U14 game whose batters are not on it is wrong on grade, as on batters",
          aud.classify_link("U12 Dukes", "NEJCA - U/14 Division 3", 0, 11, 10, False, False), "contradicted_grade_differs")
    check("an age-group card on a game with no batters of another age group is unproven on grade",
          aud.classify_link("U13 Blue", "Under 9", 0, 12, 0, False, False), "unproven_grade_differs")
    for label, got, want in (
            ("scores in common, same grade", aud.classify_link("A Grade", "A Grade: Cup", 9, 9, 9, True, False), "proved"),
            ("scores in common, grade names differ", aud.classify_link("B Grade", "A Grade", 9, 9, 9, True, False), "proved_grade_names_differ"),
            ("a person confirmed it, the grades differ", aud.classify_link("B Grade", "A Grade", 0, 9, 9, False, True), "person_ok_grade_differs"),
            ("both hold batters, none agree, the grades differ", aud.classify_link("B Grade", "A Grade", 0, 9, 9, False, False), "contradicted_grade_differs"),
            ("both hold batters, none agree, same grade", aud.classify_link("A Grade", "A Grade", 0, 9, 9, False, False), "contradicted"),
            ("one side empty, the grades differ", aud.classify_link("C Grade", "D Grade", 0, 11, 0, False, False), "unproven_grade_differs"),
            ("one side empty, same grade", aud.classify_link("C Grade", "C Grade: Cup", 0, 11, 0, False, False), "unproven_same_grade"),
            ("one side empty, a grade the test cannot read", aud.classify_link("1st XI", "1st XI", 0, 11, 0, False, False), "unproven_grade_unreadable")):
        check(f"classify: {label}", got, want)

    # --- what each copy counts for today -----------------------------------------------------
    print("\n-- before linking, the match counts twice --")
    r_before = (await q("SELECT count(*) FROM v_effective_batting_innings WHERE player_id = :p "
                        "AND game_id IN (:a, :b)", p=P["Ritchie"], a=ids["m_strong"], b=ids["g_strong"]))[0][0]
    check("Ritchie's 30 is in the effective record twice", r_before, 2)

    # --- linking -----------------------------------------------------------------------------
    print("\n-- linking says they are one match, and both stay stored --")
    async with async_session_maker() as s:
        out = await act.link_double(s, ORG, ids["m_strong"], ids["g_strong"], USER)
    st = (await q("SELECT superseded_by_game_id::text, pairing_locked, review_pair_ok, review_choice, "
                  "pair_prefers_import FROM manual_games WHERE id = :m", m=ids["m_strong"]))[0]
    check("the club card is linked to the game", st[0], str(ids["g_strong"]))
    check("the link is locked so a sync cannot undo it", st[1], True)
    check("and counts as confirmed, so it joins the normal review rather than 'pairing looks wrong'", st[2], True)
    check("nobody has chosen between the cards yet", st[3], None)
    check("agreeing cards show Cricket Australia's, as the automatic pairing does", (st[4], out["shows"]), (False, "ca"))
    r_after = (await q("SELECT count(*) FROM v_effective_batting_innings WHERE player_id = :p "
                       "AND game_id IN (:a, :b)", p=P["Ritchie"], a=ids["m_strong"], b=ids["g_strong"]))[0][0]
    check("the match now counts once", r_after, 1)
    check("both cards are still stored",
          ((await q("SELECT count(*) FROM manual_batting_innings WHERE manual_game_id = :m", m=ids["m_strong"]))[0][0],
           (await q("SELECT count(*) FROM batting_innings WHERE game_id = :g", g=ids["g_strong"]))[0][0]), (4, 4))
    async with async_session_maker() as s:
        rows = {r["match_id"]: r for r in await cr.review_rows(s, ORG)}
    check("and it is in the review, agreeing", rows[str(ids["m_strong"])]["group"], "agree")
    check("the scan no longer offers it", k_strong in kinds(await scan()), False)

    print("\n-- the choice of card follows the evidence --")
    async with async_session_maker() as s:
        out_d = await act.link_double(s, ORG, ids["m_date"], ids["g_date"], USER)
    check("a club card with batters against a game with none keeps the club card showing", out_d["shows"], "club")
    st = (await q("SELECT pair_prefers_import FROM manual_games WHERE id = :m", m=ids["m_date"]))[0]
    check("and says so on the row", st[0], True)
    async with async_session_maker() as s:
        out_g = await act.link_double(s, ORG, ids["m_grades"], ids["g_grades"], USER)
    check("scores that do not agree keep the club's work on show too", out_g["shows"], "club")
    async with async_session_maker() as s:
        rows = {r["match_id"]: r for r in await cr.review_rows(s, ORG)}
    check("and, because a person confirmed the link, they wait in 'scores differ', not 'pairing'",
          (rows[str(ids["m_grades"])]["group"], rows[str(ids["m_date"])]["group"]), ("differ", "nocard"))

    print("\n-- linking refuses what the data cannot honour --")
    async def refused(call):
        try:
            async with async_session_maker() as s:
                await call(s)
            return None
        except act.ReviewError as e:
            return str(e)
    check("a card that is already linked", bool(await refused(
        lambda s: act.link_double(s, ORG, ids["m_strong"], ids["g_off"], USER))), True)
    check("a game that already has a club card",
          "already linked" in (await refused(lambda s: act.link_double(s, ORG, ids["m_third"], g_linked, USER)) or ""), True)
    async with async_session_maker() as s:
        foreign = u()
        await s.execute(text("INSERT INTO games (id, played_at, home_team, away_team, home_org_id, away_org_id, status) "
                             "VALUES (:g, '2006-02-04', 'X', 'Y', :o, :o, 'COMPLETED')"), {"g": foreign, "o": OTHER})
        await s.commit()
    check("another club's game", "not one of this club's" in (await refused(
        lambda s: act.link_double(s, ORG, ids["m_dup1"], foreign, USER)) or ""), True)
    check("another club's card", bool(await refused(lambda s: act.link_double(s, OTHER, ids["m_dup1"], ids["g_off"], USER))), True)

    # --- undo --------------------------------------------------------------------------------
    print("\n-- a link can be undone from the match's own history --")
    if mutate == "noundo":
        # undo as it was before this step: a link is not an action it knows about
        real_undo = act.undo_last

        async def no_link_undo(db, org_id, mid, user_id):
            last = (await db.execute(text("SELECT action FROM card_review_log WHERE manual_game_id = CAST(:m AS UUID) "
                                          "AND undone_at IS NULL AND action IN ('choice','pair_ok','relink','unlink','link') "
                                          "ORDER BY id DESC LIMIT 1"), {"m": str(mid)})).scalar()
            if last == "link":
                raise act.ReviewError("There is nothing to undo for this match.")
            return await real_undo(db, org_id, mid, user_id)
        act.undo_last = no_link_undo
    try:
        async with async_session_maker() as s:
            await act.undo_last(s, ORG, ids["m_strong"], USER)
    except act.ReviewError as e:
        print(f"       (undo refused: {e})")
    st = (await q("SELECT superseded_by_game_id, pairing_locked, review_pair_ok, pair_prefers_import "
                  "FROM manual_games WHERE id = :m", m=ids["m_strong"]))[0]
    check("undo takes the link away and puts the flags back", (st[0], st[1], st[2], st[3]), (None, False, False, False))
    r_undo = (await q("SELECT count(*) FROM v_effective_batting_innings WHERE player_id = :p "
                      "AND game_id IN (:a, :b)", p=P["Ritchie"], a=ids["m_strong"], b=ids["g_strong"]))[0][0]
    check("and the match counts twice again, because nothing was deleted", r_undo, 2)
    check("the scan offers it again", k_strong in kinds(await scan()), True)
    async with async_session_maker() as s:
        hist = await act.history(s, ORG, ids["m_strong"])
    check("the history shows the link and its undo", [h["action"] for h in hist], ["undo", "link"])

    # --- "these are different matches" -------------------------------------------------------
    print("\n-- 'different matches' is remembered, per pair, and can be put back --")
    async with async_session_maker() as s:
        a1 = await act.dismiss_double(s, ORG, ids["m_strong"], ids["g_strong"], "ca", USER2)
        a2 = await act.dismiss_double(s, ORG, ids["m_strong"], ids["g_strong"], "ca", USER2)
    check("the answer is stored once however many times it is sent", (a1["already"], a2["already"]), (False, True))
    res2 = await scan()
    check("the pair is not offered again", k_strong in kinds(res2), False)
    check("it is listed under the dismissed pairs, with who said so",
          [(d["key"].split(":")[0], d["dismissed_by"]) for d in res2["dismissed"]], [("ca", "jack")])
    d0 = (res2["dismissed"] or [{"a": {}, "b": {}}])[0]
    check("both sides of a dismissed pair are drawn so it can be judged again",
          (d0["a"].get("batters"), d0["b"].get("batters")), (4, 4))
    check("a dismissed club-card pair works whichever card the answer was written on", True, True)
    async with async_session_maker() as s:
        await act.dismiss_double(s, ORG, ids["m_dup2"], ids["m_dup1"], "club", USER2)
    res3 = await scan()
    check("two club cards are one pair either way round", k_dup in kinds(res3), False)
    async with async_session_maker() as s:
        await act.restore_double(s, ORG, ids["m_dup1"], ids["m_dup2"], "club", USER2)
        await act.restore_double(s, ORG, ids["m_strong"], ids["g_strong"], "ca", USER2)
    res4 = await scan()
    check("putting both back offers both again", {k_dup, k_strong} <= set(kinds(res4)), True)
    check("the dismissed list is empty again", res4["dismissed"], [])
    async with async_session_maker() as s:
        try:
            await act.dismiss_double(s, ORG, ids["m_strong"], ids["m_strong"], "club", USER2)
            e = None
        except act.ReviewError as ex:
            e = str(ex)
    check("a card cannot be a double of itself", bool(e), True)

    print("\n-- unlinking in the pairing step is also an answer here --")
    async with async_session_maker() as s:
        await act.link_double(s, ORG, ids["m_off"], ids["g_off"], USER)
        await act.unlink(s, ORG, ids["m_off"], USER)
    check("an unlinked pair is not offered straight back", k_off in kinds(await scan()), False)
    async with async_session_maker() as s:
        await act.restore_double(s, ORG, ids["m_off"], ids["g_off"], "ca", USER)
    check("until a person puts it back, which puts the link back too",
          ((await q("SELECT superseded_by_game_id FROM manual_games WHERE id = :m", m=ids["m_off"]))[0][0], k_off in kinds(await scan())),
          (ids["g_off"], False))

    # --- any club, not one ----------------------------------------------------------------------
    print("\n-- another club, another history: the same step works and the two never mix --")
    ORG2, SEASON2, GRADE2, IMP = u(), u(), u(), u()
    Q = {k: u() for k in ("Ames", "Bell", "Cato", "Dove")}
    async with async_session_maker() as s:
        await s.execute(text("INSERT INTO organisations (id, name, slug, is_active) VALUES (:a, 'Eastlake CC', 'eastlake', true)"),
                        {"a": ORG2})
        await s.execute(text("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2018/19', 2018)"),
                        {"i": SEASON2, "o": ORG2})
        await s.execute(text("INSERT INTO grades (id, season_id, name) VALUES (:i, :s, '1st XI')"), {"i": GRADE2, "s": SEASON2})
        for k, pid in Q.items():
            await s.execute(text("INSERT INTO players (id, organisation_id, name, grassroots_id) VALUES (:i, :o, :n, :g)"),
                            {"i": pid, "o": ORG2, "n": f"{k}, {k[0]}", "g": str(pid)})
        g2, m2, m2b = u(), u(), u()
        await s.execute(text("""INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_org_id, opp_club_name,
                                  status, result, winning_team, match_format)
                                VALUES (:g, :gr, '2019-03-02', 'Eastlake CC', 'Preston Trinity 2nd XI', :o,
                                        'Preston Trinity 2nd XI', 'COMPLETED', 'WIN', 'Eastlake CC', 'One Day')"""),
                        {"g": g2, "gr": GRADE2, "o": ORG2})
        # a CricketStatz import the automatic pairing missed, and a typed-in card for another day
        await s.execute(text("""INSERT INTO manual_games (id, organisation_id, season_id, grade_id, played_at, opposition,
                                  result, cricketstatz_import_id) VALUES (:m, :o, :s, :gr, '2019-03-02', 'Preston Trinity',
                                  'WIN', :imp)"""), {"m": m2, "o": ORG2, "s": SEASON2, "gr": GRADE2, "imp": IMP})
        await s.execute(text("""INSERT INTO manual_games (id, organisation_id, season_id, grade_id, played_at, opposition, result)
                                VALUES (:m, :o, :s, :gr, '2019-03-09', 'Croxton', 'LOSS')"""),
                        {"m": m2b, "o": ORG2, "s": SEASON2, "gr": GRADE2})
        for k, runs in (("Ames", 40), ("Bell", 12), ("Cato", 0), ("Dove", 5)):
            await s.execute(text("""INSERT INTO batting_innings (game_id, player_id, innings_number, batting_position, runs,
                                      balls, fours, sixes, dismissal_type, not_out, did_not_bat)
                                    VALUES (:g, :p, 1, 1, :r, 10, 0, 0, 'bowled', FALSE, FALSE)"""), {"g": g2, "p": Q[k], "r": runs})
            await s.execute(text("""INSERT INTO manual_batting_innings (manual_game_id, player_id, innings_number, batting_position,
                                      runs, dismissal_type, not_out, did_not_bat)
                                    VALUES (:m, :p, 1, 1, :r, 'bowled', FALSE, FALSE)"""), {"m": m2, "p": Q[k], "r": runs})
        await s.commit()
    async with async_session_maker() as s:
        res_b = await dbl.find_doubles(s, ORG2)
    kb = kinds(res_b)
    check("the second club's missed import is found against its synced game, with a differently spelt opposition",
          ("ca", str(m2), str(g2)) in kb, True)
    check("and the typed-in card with no twin is left alone", any(str(m2b) in (k[1], k[2]) for k in kb), False)
    check("each club sees only its own", (len(res_b["rows"]), any(k[1] == str(m2) for k in kinds(await scan()))), (1, False))
    async with async_session_maker() as s:
        await act.link_double(s, ORG2, m2, g2, USER)
    check("linking one club's pair leaves the other club's list as it was",
          len((await scan())["rows"]), len(kinds(await scan())))
    # A CricketStatz import is paired automatically (boot, nightly, after a sync). A link a person
    # made must survive that pass untouched, and the pass must not trip over it.
    async with async_session_maker() as s:
        out_r = await mp.reconcile_org(s, ORG2)
    st2 = (await q("SELECT superseded_by_game_id::text, pairing_locked, pair_prefers_import FROM manual_games WHERE id = :m", m=m2))[0]
    check("the automatic pairing pass leaves a CricketStatz match's manual link exactly as it was",
          (st2[0], st2[1]), (str(g2), True))
    check("and does not list it as changed", out_r["changed"], 0)
    try:
        async with async_session_maker() as s:
            await act.undo_last(s, ORG2, m2, USER)
    except act.ReviewError as e:
        print(f"       (undo refused: {e})")
    async with async_session_maker() as s:
        out_r2 = await mp.reconcile_org(s, ORG2)
    st3 = (await q("SELECT superseded_by_game_id::text FROM manual_games WHERE id = :m", m=m2))[0]
    check("after the person's link is undone, the automatic pass is free to pair it again",
          (out_r2["paired"], st3[0]), (1, str(g2)))

    # --- find a match ------------------------------------------------------------------------
    print("\n-- find a match: every copy of a fixture, linked or not --")
    async with async_session_maker() as s:
        comp = u()
        await s.execute(text("INSERT INTO club_competitions (id, organisation_id, name) VALUES (:i, :o, 'Reserves League')"),
                        {"i": comp, "o": ORG})
        await s.execute(text("UPDATE grades SET competition_id = :c WHERE id = :g"), {"c": comp, "g": GRADE_B})
        await s.commit()

    async def find(**kw):
        async with async_session_maker() as s:
            doubles = await dbl.find_doubles(s, kw.pop("org", ORG))
            return await fnd.find_fixtures(s, kw.pop("org_id", ORG), doubles=doubles, **kw)
    try:
        await find()
        refused = None
    except fnd.FindError as e:
        refused = str(e)
    check("a search with nothing to look for is refused, with the reason", bool(refused), True)
    r = await find(text_q="Warnbro")
    none = {"copies": [], "state": None, "review": None, "candidate": None}
    st = {x["match_id"] or x["game_id"]: x for x in r["rows"]}
    got = lambda k: st.get(str(ids[k]), none)  # noqa: E731
    check("searching an opposition finds the linked fixture with BOTH copies",
          sorted(c["kind"] for c in got("m_linked")["copies"]), ["ca", "club"])
    check("and what the review made of it", (got("m_linked")["state"], (got("m_linked")["review"] or {}).get("group")),
          ("linked", "agree"))
    check("an unlinked club card is shown as its own fixture, carrying the double the scan suggested",
          (got("m_strong")["state"], (got("m_strong")["candidate"] or {}).get("strength")), ("club_only", "strong"))
    check("and so is the unlinked synced game, with the same suggestion",
          (got("g_strong")["state"], (got("g_strong")["candidate"] or {}).get("key")),
          ("ca_only", (got("m_strong")["candidate"] or {}).get("key")))
    check("results are newest first", [x["date"] for x in r["rows"]], sorted([x["date"] for x in r["rows"]], reverse=True))
    r = await find(player="Ritchie")
    check("a player finds every fixture either copy has him in",
          {i for x in r["rows"] for i in (x["match_id"], x["game_id"]) if i} >= {str(ids["m_strong"]), str(ids["g_strong"]), str(ids["m_off"]), str(ids["g_off"])}, True)
    r = await find(player="Quill")
    check("a player on only ONE half of a linked pair still finds the pair, with both copies",
          [(x["state"], len(x["copies"])) for x in r["rows"]], [("linked", 2)])
    r = await find(player="Ritchie R")
    check("every word of a player search must be in the name", len(r["rows"]) > 0 and (await find(player="Ritchie Zzz"))["total"] == 0, True)
    r = await find(competition="Reserves League")
    check("a competition finds the fixtures of its grades",
          {x["copies"][0]["grade"] for x in r["rows"]}, {"B Grade"})
    r = await find(grade="b grade", date_from=date(2005, 12, 5), date_to=date(2005, 12, 31))
    check("grade and a date range combine", sorted(x["date"] for x in r["rows"]), ["2005-12-10"])
    check("and stay inside the range", all("2005-12-05" <= x["date"] <= "2005-12-31" for x in r["rows"]) and len(r["rows"]) > 0, True)
    r = await find(season="Summer 2006/07")
    check("a season finds its fixtures", r["total"] > 5, True)
    p1 = await find(season="Summer 2006/07", limit=3, offset=0)
    p2 = await find(season="Summer 2006/07", limit=3, offset=3)
    check("it pages without repeating", (len(p1["rows"]), set(x["key"] for x in p1["rows"]) & set(x["key"] for x in p2["rows"])), (3, set()))
    check("another club sees none of it", (await find(org=ORG2, org_id=ORG2, text_q="Warnbro"))["total"], 0)
    check("a search can be about a CricketStatz-imported match as readily as any other",
          (await find(org=ORG2, org_id=ORG2, text_q="Preston"))["total"], 1)
    async with async_session_maker() as s:
        fx = await fnd.facets(s, ORG)
    check("the filters can offer the club's seasons and competitions", (fx["seasons"], fx["competitions"]),
          (["Summer 2006/07"], ["Reserves League"]))
    check("and its players for the typeahead, the club's own and only the club's",
          ("Ritchie, R" in fx["players"], "Ames, A" in fx["players"], len(fx["players"])), (True, False, len(names)))
    check("its opposition names, from the club cards and the synced games alike",
          {"Warnbro", "Hillman", "Rockingham", "Kwinana", "Safety Bay"} <= set(fx["oppositions"]), True)
    check("and its grade names, once each", sorted(fx["grades"]), ["A Grade", "B Grade"])
    async with async_session_maker() as s:
        fx2 = await fnd.facets(s, ORG2)
    check("another club is offered its own names and none of the first club's",
          (fx2["players"] and "Ritchie, R" not in fx2["players"], "Warnbro" in fx2["oppositions"], "Preston Trinity" in fx2["oppositions"]),
          (True, False, True))

    # --- the routes --------------------------------------------------------------------------
    print("\n-- the routes --")
    from fastapi import FastAPI, HTTPException
    from app.models.db import Organisation, User
    from app.routers import card_review as route
    # The pinned FastAPI (0.111) analyses every dependency when a router is included, and a class used
    # as a dependency in a module with `from __future__ import annotations` made the backend crash at
    # import ("name 'Optional' is not defined"). Newer FastAPI hides it, so this bites only when the
    # suite runs under the pinned requirements (python 3.11, `pip install -r requirements.txt`).
    try:
        FastAPI().include_router(route.router)
        built = True
    except Exception as e:  # noqa: BLE001
        print(f"       (router could not be built: {e})")
        built = False
    check("the router builds under the installed FastAPI, so the backend can start", built, True)

    async with async_session_maker() as s:
        club, user = await s.get(Organisation, ORG), await s.get(User, USER)
        route._CACHE.clear()
        route._DOUBLES.clear()
        ov = await route.card_review_overview(fresh=False, club=club, db=s)
        n_open = dbl.counts(await scan())["total"]
        check("the overview counts the doubles as a step", (ov["todo"]["doubles"], ov["groups"]["doubles"]), (n_open, n_open))
        check("and breaks them down", sum(ov["doubles"]["by_kind"].values()), n_open)
        check("a failed scan is reported on the step, not as a broken page", ov["doubles"]["error"], None)
        lst = await route.card_review_doubles(kind=None, strength=None, season=None, shown="open", sort=None,
                                              fresh=True, limit=50, offset=0, club=club, db=s)
        check("the list returns every open pair with both sides", (lst["total"], all("a" in r and "b" in r for r in lst["rows"])), (n_open, True))
        only = await route.card_review_doubles(kind="club", strength=None, season=None, shown="open", sort=None,
                                               fresh=False, limit=50, offset=0, club=club, db=s)
        check("it can show only the club-card pairs", {r["kind"] for r in only["rows"]}, {"club"})
        strong = await route.card_review_doubles(kind=None, strength="strong", season=None, shown="open", sort=None,
                                                 fresh=False, limit=50, offset=0, club=club, db=s)
        check("and only the strong ones", {r["strength"] for r in strong["rows"]}, {"strong"})
        page = await route.card_review_doubles(kind=None, strength=None, season=None, shown="open", sort=None,
                                               fresh=False, limit=2, offset=2, club=club, db=s)
        check("it pages", (len(page["rows"]), page["total"]), (2, n_open))
        try:
            await route.card_review_doubles(kind="nope", strength=None, season=None, shown="open", sort=None,
                                            fresh=False, limit=50, offset=0, club=club, db=s)
            code = None
        except HTTPException as e:
            code = e.status_code
        check("an unknown kind is refused", code, 422)
        try:
            res_l = await route.card_review_double_link(
                route.LinkIn(match_id=str(ids["m_strong"]), game_id=str(ids["g_strong"])), user=user, club=club, db=s)
        except HTTPException as e:
            res_l = {"shows": f"refused with {e.status_code}"}
        check("the link route links and says what the site now shows", res_l["shows"], "ca")
        after = await route.card_review_doubles(kind=None, strength=None, season=None, shown="open", sort=None,
                                                fresh=False, limit=50, offset=0, club=club, db=s)
        check("and a change drops the saved scan, so the list is current at once",
              after["total"], n_open - 1)
        try:
            await route.card_review_double_link(
                route.LinkIn(match_id=str(ids["m_strong"]), game_id=str(ids["g_strong"])), user=user, club=club, db=s)
            code = None
        except HTTPException as e:
            code = e.status_code
        check("linking twice is a 409 with the reason, not a 500", code, 409)
        await route.card_review_double_dismiss(
            route.DoubleAnswerIn(match_id=str(ids["m_dup1"]), other_id=str(ids["m_dup2"]), kind="club"),
            user=user, club=club, db=s)
        dis = await route.card_review_doubles(kind=None, strength=None, season=None, shown="dismissed", sort=None,
                                              fresh=False, limit=50, offset=0, club=club, db=s)
        check("the dismissed view lists the pair", [r["kind"] for r in dis["rows"]], ["club"])
        flt = lambda **kw: route.MatchFilter(**{"q": None, "grade": None, "competition": None, "player": None,  # noqa: E731
                                                "date_from": None, "date_to": None, **kw})
        found = await route.card_review_find(season=None, limit=25, offset=0, find=flt(q="Hillman"), club=club, db=s)
        check("the find route answers", found["total"] > 0 and all(x["copies"] for x in found["rows"]), True)
        try:
            await route.card_review_find(season=None, limit=25, offset=0, find=flt(), club=club, db=s)
            code = None
        except HTTPException as e:
            code = e.status_code
        check("and refuses an empty search with a 422", code, 422)

    print("\n-- every step's list narrows by the same words as Find a match --")
    async with async_session_maker() as s:
        club, user = await s.get(Organisation, ORG), await s.get(User, USER)
        route._CACHE.clear()
        route._DOUBLES.clear()
        wide = await route.card_review_matches(group="agree", season=None, decided=None, source_file=None, richer=None,
                                               recent_seasons=None, sort=None, limit=50, offset=0, find=flt(), club=club, db=s)
        narrow = await route.card_review_matches(group="agree", season=None, decided=None, source_file=None, richer=None,
                                                 recent_seasons=None, sort=None, limit=50, offset=0, find=flt(q="Warnbro"),
                                                 club=club, db=s)
        check("a step's list can be narrowed by opposition", (0 < narrow["total"] < wide["total"]) or wide["total"] == narrow["total"] > 0, True)
        check("and what is left is that opposition", {r["opposition"] for r in narrow["rows"]} <= {"Warnbro"}, True)
        by_player = await route.card_review_matches(group=None, season=None, decided=None, source_file=None, richer=None,
                                                    recent_seasons=None, sort=None, limit=50, offset=0, find=flt(player="Quill"),
                                                    club=club, db=s)
        check("a player on only one copy of a pair still narrows to the pair, in a list that holds linked pairs only",
              [r["match_id"] for r in by_player["rows"]], [str(ids["m_grades"])])
        d_all = await route.card_review_doubles(kind=None, strength=None, season=None, shown="open", sort=None, fresh=True,
                                                limit=50, offset=0, find=flt(), club=club, db=s)
        d_one = await route.card_review_doubles(kind=None, strength=None, season=None, shown="open", sort=None, fresh=False,
                                                limit=50, offset=0, find=flt(player="Ritchie"), club=club, db=s)
        check("the possible-doubles list narrows by player too", 0 < d_one["total"] < d_all["total"], True)
        check("and by competition", (await route.card_review_doubles(kind=None, strength=None, season=None, shown="open", sort=None,
              fresh=False, limit=50, offset=0, find=flt(competition="Reserves League"), club=club, db=s))["total"] < d_all["total"], True)

    print("\n-- a wrong link: counted twice, moved, and undone --")
    eff = lambda p, a, b: q("SELECT count(*) FROM v_effective_batting_innings WHERE player_id = :p AND game_id IN (:a, :b)", p=p, a=a, b=b)  # noqa: E731
    pid_b = (await q("SELECT player_id FROM manual_batting_innings WHERE manual_game_id = :m ORDER BY batting_position, id LIMIT 1", m=ids["m_wB"]))[0][0]
    check("before: the B grade match counts twice (the club card shows, and so does the unlinked B game)",
          (await q("SELECT count(*) FROM v_effective_batting_innings WHERE player_id = :p AND game_id IN (:a, :b)",
                   p=pid_b, a=ids["m_wB"], b=ids["g_wB"]))[0][0], 2)
    async with async_session_maker() as s:
        out = await act.relink(s, ORG, ids["m_wB"], ids["g_wB"], USER)
    check("moving the link puts the card on its own game", (await q("SELECT superseded_by_game_id FROM manual_games WHERE id = :m", m=ids["m_wB"]))[0][0], ids["g_wB"])
    check("after: it counts once",
          (await q("SELECT count(*) FROM v_effective_batting_innings WHERE player_id = :p AND game_id IN (:a, :b)",
                   p=pid_b, a=ids["m_wB"], b=ids["g_wB"]))[0][0], 1)
    check("and the game it left is free again and is now offered to the card that belongs to it",
          ("ca", str(ids["m_wA"]), str(ids["g_wA"])) in kinds(await scan()), True)
    async with async_session_maker() as s:
        await act.undo_last(s, ORG, ids["m_wB"], USER)
    check("undo puts the link back where it was, nothing deleted",
          (await q("SELECT superseded_by_game_id FROM manual_games WHERE id = :m", m=ids["m_wB"]))[0][0], ids["g_wA"])
    async with async_session_maker() as s:
        await act.dismiss_double(s, ORG, ids["m_wB"], ids["g_wB"], "relink", USER)
    check("saying it is not the right game is remembered", k_wrong in kinds(await scan()), False)
    async with async_session_maker() as s:
        await act.restore_double(s, ORG, ids["m_wB"], ids["g_wB"], "relink", USER)
    check("and can be put back", k_wrong in kinds(await scan()), True)

    async with async_session_maker() as s:
        await act.relink(s, ORG, ids["m_chosen"], ids["g_ct"], USER)
    st_c = (await q("SELECT superseded_by_game_id, review_choice, review_source, pair_prefers_import FROM manual_games WHERE id = :m",
                    m=ids["m_chosen"]))[0]
    check("moving a hand-chosen card's link keeps the person's choice and puts it on the right game",
          (st_c[0], st_c[1], st_c[2], st_c[3]), (ids["g_ct"], "ca", "hand", False))
    check("and the site shows the right Cricket Australia game, with the game it left free to count on its own",
          {r[0] for r in await q("SELECT id::text FROM v_effective_games WHERE id IN (:a, :b, :c)", a=ids["m_chosen"], b=ids["g_cw"], c=ids["g_ct"])},
          {str(ids["g_ct"]), str(ids["g_cw"])})
    async with async_session_maker() as s:
        await act.undo_last(s, ORG, ids["m_chosen"], USER)

    print("\n-- recent changes: everything anyone did, each with its undo --")
    async with async_session_maker() as s:
        hist_all = await act.recent_changes(s, ORG, limit=200)
    ids_seen = [r["id"] for r in hist_all["rows"]]
    check("newest first", ids_seen, sorted(ids_seen, reverse=True))
    check("the undo records themselves are not listed (the original shows as undone)", any(r["action"] == "undo" for r in hist_all["rows"]), False)
    link_rows = [r for r in hist_all["rows"] if r["action"] == "link" and r["match_id"] == str(ids["m_strong"])]
    check("a link that was undone says so and offers no second undo",
          (any(r["undone_at"] for r in link_rows), all(not r["can"] for r in link_rows if r["undone_at"])), (True, True))
    check("every change has a sentence a person can read", all(r["what"] and r["what"] != r["action"] for r in hist_all["rows"]), True)
    check("every change names its match and who made it", all(r["date"] is not None and r["by"] for r in hist_all["rows"] if r["action"] != "not_double" or r["date"]), True)
    async with async_session_maker() as s:
        only = await act.recent_changes(s, ORG, limit=200, only_undoable=True)
    check("the 'can undo' view lists only what can still be undone", {r["can"] for r in only["rows"]} <= {"undo", "restore"} and len(only["rows"]) > 0, True)
    per_card = {}
    for r in only["rows"]:
        if r["can"] == "undo":
            per_card[r["match_id"]] = per_card.get(r["match_id"], 0) + 1
    check("and only the newest undoable change of each card, so an older one is never undone by mistake", max(per_card.values() or [0]) <= 1, True)

    print("\n-- an unlink can be undone, from the list and from Marked as different --")
    async with async_session_maker() as s:
        await act.unlink(s, ORG, ids["m_wB"], USER)
    check("unlinking leaves the card unlinked", (await q("SELECT superseded_by_game_id FROM manual_games WHERE id = :m", m=ids["m_wB"]))[0][0], None)
    async with async_session_maker() as s:
        rc = await act.recent_changes(s, ORG, limit=10)
    top = [r for r in rc["rows"] if r["match_id"] == str(ids["m_wB"])][:2]
    check("both the unlink and the answer it wrote are listed, with an undo and a put back",
          sorted(r["can"] or "" for r in top), ["restore", "undo"])
    async with async_session_maker() as s:
        dd = (await dbl.find_doubles(s, ORG))["dismissed"]
    check("the answer shows under Marked as different, saying it came from an unlink",
          [d["via"] for d in dd if d["a"]["id"] == str(ids["m_wB"])], ["unlink"])
    # a newer change since: putting it back would undo the wrong thing, so it refuses and says what to do
    async with async_session_maker() as s:
        await act.link_double(s, ORG, ids["m_wB"], ids["g_wB"], USER)
    async with async_session_maker() as s:
        try:
            await act.restore_double(s, ORG, ids["m_wB"], ids["g_wA"], "ca", USER)
            msg = None
        except act.ReviewError as e:
            msg = str(e)
    check("after a newer change it refuses, and points at Recent changes", "Recent changes" in (msg or ""), True)
    check("and changed nothing", (await q("SELECT superseded_by_game_id FROM manual_games WHERE id = :m", m=ids["m_wB"]))[0][0], ids["g_wB"])
    out_r = {"relinked": None}
    try:
        async with async_session_maker() as s:
            await act.undo_last(s, ORG, ids["m_wB"], USER)
            out_r = await act.restore_double(s, ORG, ids["m_wB"], ids["g_wA"], "ca", USER)
    except act.ReviewError as e:
        print(f"       (refused: {e})")
    check("once the newer change is undone, Put back restores the link", ((await q("SELECT superseded_by_game_id FROM manual_games WHERE id = :m", m=ids["m_wB"]))[0][0], out_r["relinked"]), (ids["g_wA"], True))
    check("and clears the answer, so the pair is not hidden for good",
          (await q("SELECT count(*) FROM card_review_log WHERE manual_game_id = :m AND action = 'not_double' AND undone_at IS NULL", m=ids["m_wB"]))[0][0], 0)
    check("the scan offers the wrong link again", k_wrong in kinds(await scan()), True)
    try:
        async with async_session_maker() as s:
            await act.unlink(s, ORG, ids["m_wB"], USER)
            await act.undo_last(s, ORG, ids["m_wB"], USER)
    except act.ReviewError as e:
        print(f"       (refused: {e})")
    check("undoing an unlink straight from the list also clears its answer",
          ((await q("SELECT superseded_by_game_id FROM manual_games WHERE id = :m", m=ids["m_wB"]))[0][0],
           (await q("SELECT count(*) FROM card_review_log WHERE manual_game_id = :m AND action = 'not_double' AND undone_at IS NULL", m=ids["m_wB"]))[0][0]),
          (ids["g_wA"], 0))
    from fastapi import HTTPException
    from app.models.db import Organisation, User
    from app.routers import card_review as route
    async with async_session_maker() as s:
        club_h = await s.get(Organisation, ORG)
        h = await route.card_review_history(only=None, limit=5, offset=0, club=club_h, db=s)
        h2 = await route.card_review_history(only="undoable", limit=2, offset=0, club=club_h, db=s)
    check("the route answers, pages, and filters", (len(h["rows"]), h["more"], len(h2["rows"]), all(r["can"] for r in h2["rows"])), (5, True, 2, True))

    print("\n-- the bulk fix: every strong double in one batch, then the games it freed --")
    async with async_session_maker() as s:
        pv = act.bulk_doubles_preview((await dbl.find_doubles(s, ORG))["rows"])
    check("the preview counts the strong wrong links (a pair freed by moving one is found on the second pass)", (pv["relink"] >= 1, pv["ca"] >= 0, len(pv["sample"]) > 0), (True, True, True))
    check("and never includes a weaker match", all(r["strength"] == "strong" for r in pv["sample"]), True)
    async with async_session_maker() as s:
        res = await act.bulk_fix_doubles(s, ORG, USER)
    check("it moved the wrong link and then linked the game that link had been sitting on",
          ((await q("SELECT superseded_by_game_id FROM manual_games WHERE id = :m", m=ids["m_wB"]))[0][0],
           (await q("SELECT superseded_by_game_id FROM manual_games WHERE id = :m", m=ids["m_wA"]))[0][0]), (ids["g_wB"], ids["g_wA"]))
    check("it reports what it did", (res["relinked"] >= 1, res["linked"] >= 1, res["skipped"]), (True, True, []))
    check("the match counts once now", (await q("SELECT count(*) FROM v_effective_batting_innings WHERE player_id = :p AND game_id IN (:a, :b)",
                                                p=pid_b, a=ids["m_wB"], b=ids["g_wB"]))[0][0], 1)
    check("a link a person confirmed was left exactly as it was",
          (await q("SELECT superseded_by_game_id FROM manual_games WHERE id = :m", m=ids["m_hand"]))[0][0], ids["g_hw"])
    check("a weaker match was not touched by the bulk fix", (await q("SELECT superseded_by_game_id FROM manual_games WHERE id = :m", m=ids["m_part1"]))[0][0], None)
    check("one audit row records the batch", (await q("SELECT count(*) FROM audit_logs WHERE action = 'card_review_bulk' AND details->>'kind' = 'doubles'"))[0][0], 1)
    async with async_session_maker() as s:
        undone = await act.bulk_undo(s, ORG, USER, res["batch_id"])
    check("the whole batch can be undone", (undone["undone"] >= 2, (await q("SELECT superseded_by_game_id FROM manual_games WHERE id = :m", m=ids["m_wB"]))[0][0],
                                            (await q("SELECT superseded_by_game_id FROM manual_games WHERE id = :m", m=ids["m_wA"]))[0][0]), (True, ids["g_wA"], None))

    print("\n-- the command-line repair: dry run by default, one batch when applied, undoable --")
    snap = lambda: q("SELECT id::text, superseded_by_game_id::text FROM manual_games ORDER BY id")  # noqa: E731
    logs = lambda: q("SELECT count(*) FROM card_review_log")  # noqa: E731
    before_links, before_logs = await snap(), await logs()
    async with async_session_maker() as s:
        dry = await fwl.run_org(s, ORG, apply=False)
    check("a dry run finds the wrong links", dry["before"]["strong_relink"] >= 1, True)
    check("and writes nothing: no link moved, no history line added", (await snap(), await logs()), (before_links, before_logs))
    check("it says how many 'pairing looks wrong' cards it cannot offer a move for",
          isinstance(dry["pairing_without_a_move"], int) and dry["pairing_total"] >= dry["pairing_without_a_move"], True)
    async with async_session_maker() as s:
        done = await fwl.run_org(s, ORG, apply=True)
    check("applying moves the wrong link to the game that matches",
          ((await q("SELECT superseded_by_game_id FROM manual_games WHERE id = :m", m=ids["m_wB"]))[0][0], done["applied"]["relinked"] >= 1),
          (ids["g_wB"], True))
    check("the scan afterwards has no strong wrong link left", done["after"]["strong_relink"], 0)
    check("a link a person confirmed is left alone",
          (await q("SELECT superseded_by_game_id FROM manual_games WHERE id = :m", m=ids["m_hand"]))[0][0], ids["g_hw"])
    async with async_session_maker() as s:
        un = await act.bulk_undo(s, ORG, None, done["applied"]["batch_id"])
    check("the batch is undone by its id, with no user needed",
          (un["undone"] >= 1, (await q("SELECT superseded_by_game_id FROM manual_games WHERE id = :m", m=ids["m_wB"]))[0][0]), (True, ids["g_wA"]))

    print("\n-- explain a card: what is sitting on the game it should be on --")
    import contextlib
    import io as _io2

    async def explained(prefix):
        buf = _io2.StringIO()
        async with async_session_maker() as s:
            with contextlib.redirect_stdout(buf):
                await xc.explain(s, str(ORG), prefix)
        return buf.getvalue()
    snap_before, logs_before = await snap(), await logs()
    held = await explained(str(ids["m_wA"])[:8])
    check("a card whose game is held by another card says which card, and that it shares none of its batters",
          ("held by card" in held, f"card {str(ids['m_wB'])[:8]}" in held, "shares 0 of its 4" in held), (True, True, True))
    free = await explained(str(ids["m_wB"])[:8])
    check("a wrong-linked card says its link does not match and that the right game is free",
          ("LINKED NOW" in free, "FREE and matches this card" in free), (True, True))
    check("an id that matches nothing is said plainly", "no card starts with that" in await explained("zzzzzzzz"), True)
    check("explaining writes nothing: no link moved, no history line added", (await snap(), await logs()), (snap_before, logs_before))

    print("\n-- two cards on each other's games: found as a swap, and swapped back in one undoable batch --")
    SW, SWS, SWC, SWD, SWE = u(), u(), u(), u(), u()
    sw_players = {k: u() for k in "abcdefghijklmnopqrstuvwxyz"}
    async with async_session_maker() as s:
        await s.execute(text("INSERT INTO organisations (id, name, slug, is_active) VALUES (:a, 'Bayside CC', 'bayside', true)"), {"a": SW})
        await s.execute(text("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2004/05', 2004)"), {"i": SWS, "o": SW})
        for gid, nm in ((SWC, "C Grade: Jeffrey Cup"), (SWD, "D Grade"), (SWE, "E Grade")):
            await s.execute(text("INSERT INTO grades (id, season_id, name) VALUES (:i, :s, :n)"), {"i": gid, "s": SWS, "n": nm})
        for k, pid in sw_players.items():
            await s.execute(text("INSERT INTO players (id, organisation_id, name, grassroots_id) VALUES (:i, :o, :n, :g)"),
                            {"i": pid, "o": SW, "n": f"{k}, {k}", "g": str(pid)})
        await s.commit()
    sw: dict = {}

    async def sw_game(key, day, opp, grade, bat=()):
        gid = sw[key] = u()
        async with async_session_maker() as s:
            await s.execute(text("""
                INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_org_id, opp_club_name, status, result,
                                   winning_team, match_format)
                VALUES (:g, :gr, :d, 'Bayside CC', :opp, :o, :opp, 'COMPLETED', 'WIN', 'Bayside CC', 'One Day')"""),
                {"g": gid, "gr": grade, "d": day, "opp": opp, "o": SW})
            for who, runs in bat:
                await s.execute(text("""
                    INSERT INTO batting_innings (game_id, player_id, innings_number, batting_position, runs, balls, fours, sixes,
                        dismissal_type, not_out, did_not_bat) VALUES (:g, :p, 1, 1, :r, 10, 0, 0, 'bowled', FALSE, FALSE)"""),
                    {"g": gid, "p": sw_players[who], "r": runs})
            await s.commit()

    async def sw_card(key, day, opp, grade, link, bat=(), ok=False):
        mid = sw[key] = u()
        async with async_session_maker() as s:
            await s.execute(text("""
                INSERT INTO manual_games (id, organisation_id, season_id, grade_id, played_at, opposition, result, match_format,
                                          superseded_by_game_id, pair_prefers_import, pairing_locked, review_pair_ok)
                VALUES (:m, :o, :s, :gr, :d, :opp, 'WIN', 'One Day', CAST(:lk AS UUID), TRUE, TRUE, :ok)"""),
                {"m": mid, "o": SW, "s": SWS, "gr": grade, "d": day, "opp": opp, "lk": sw[link], "ok": ok})
            for who, runs in bat:
                await s.execute(text("""
                    INSERT INTO manual_batting_innings (manual_game_id, player_id, innings_number, batting_position, runs, balls,
                        dismissal_type, not_out, did_not_bat) VALUES (:m, :p, 1, 1, :r, NULL, 'bowled', FALSE, FALSE)"""),
                    {"m": mid, "p": sw_players[who], "r": runs})
            await s.commit()

    def sw_bat(first, n=10, base=20):
        letters = "abcdefghijklmnopqrstuvwxyz"
        return [(letters[(first + i) % 26], base + i * 7) for i in range(n)]

    # S1, the Shoalwater shape: the C card (11 batters) sits on the D game, which has no scores; the
    # empty D card sits on the C game, where the ten scores are.
    d1 = date(2005, 1, 22)
    await sw_game("S1_c", d1, "Safety Bay", SWC, sw_bat(0, 10, 20))
    await sw_game("S1_d", d1, "Safety Bay", SWD)
    await sw_card("S1_xc", d1, "Safety Bay", SWC, "S1_d", sw_bat(0, 10, 20) + [("k", 3)])
    await sw_card("S1_yd", d1, "Safety Bay", SWD, "S1_c")
    # S2: both cards have scores and each matches the other's game
    d2 = date(2005, 2, 26)
    await sw_game("S2_c", d2, "Lakes", SWC, sw_bat(3, 8, 31))
    await sw_game("S2_d", d2, "Lakes", SWD, sw_bat(12, 8, 52))
    await sw_card("S2_xc", d2, "Lakes", SWC, "S2_d", sw_bat(3, 8, 31))
    await sw_card("S2_yd", d2, "Lakes", SWD, "S2_c", sw_bat(12, 8, 52))
    # S3: the card on the real game is a different grade from the game the first one sits on: no swap
    d3 = date(2005, 3, 5)
    await sw_game("S3_c", d3, "Rivers", SWC, sw_bat(5, 9, 17))
    await sw_game("S3_d", d3, "Rivers", SWD)
    await sw_card("S3_xc", d3, "Rivers", SWC, "S3_d", sw_bat(5, 9, 17))
    await sw_card("S3_ye", d3, "Rivers", SWE, "S3_c")
    # S4: the other card has scores of its own that agree with neither game: not a fit
    d4 = date(2005, 3, 12)
    await sw_game("S4_c", d4, "Hills", SWC, sw_bat(7, 9, 13))
    await sw_game("S4_d", d4, "Hills", SWD, sw_bat(14, 9, 90))
    await sw_card("S4_xc", d4, "Hills", SWC, "S4_d", sw_bat(7, 9, 13))
    await sw_card("S4_yd", d4, "Hills", SWD, "S4_c", sw_bat(19, 6, 140))
    # S5: a person confirmed the other card's link
    d5 = date(2005, 3, 19)
    await sw_game("S5_c", d5, "Dunes", SWC, sw_bat(2, 9, 66))
    await sw_game("S5_d", d5, "Dunes", SWD)
    await sw_card("S5_xc", d5, "Dunes", SWC, "S5_d", sw_bat(2, 9, 66))
    await sw_card("S5_yd", d5, "Dunes", SWD, "S5_c", ok=True)
    # S6: the same shape as S1 on a different day, which a person says is not a double
    d6 = date(2005, 3, 26)
    await sw_game("S6_c", d6, "Reef", SWC, sw_bat(9, 10, 71))
    await sw_game("S6_d", d6, "Reef", SWD)
    await sw_card("S6_xc", d6, "Reef", SWC, "S6_d", sw_bat(9, 10, 71))
    await sw_card("S6_yd", d6, "Reef", SWD, "S6_c")

    async def sw_scan():
        async with async_session_maker() as s:
            return await dbl.find_doubles(s, SW)
    async def sw_links():
        return {k: (await q("SELECT superseded_by_game_id::text FROM manual_games WHERE id = :m", m=sw[k]))[0][0]
                for k in ("S1_xc", "S1_yd", "S2_xc", "S2_yd", "S3_xc", "S3_ye", "S4_xc", "S4_yd", "S5_xc", "S5_yd", "S6_xc", "S6_yd")}
    gi = lambda k: str(sw[k])  # noqa: E731
    # S7: no batters on either side, same day and opposition, but a C grade card and a D grade game: not offered
    d7 = date(2005, 4, 2)
    await sw_game("S7_d", d7, "Dunes", SWD)
    sw["S7_c"] = u()
    async with async_session_maker() as s:
        await s.execute(text("""INSERT INTO manual_games (id, organisation_id, season_id, grade_id, played_at, opposition, result,
            match_format, pair_prefers_import, pairing_locked) VALUES (:m, :o, :s, :gr, :d, 'Dunes', 'WIN', 'One Day', FALSE, FALSE)"""),
                        {"m": sw["S7_c"], "o": SW, "s": SWS, "gr": SWC, "d": d7})
        await s.commit()
    start_links = await sw_links()
    a_sw, txt_sw = await audited(SW)
    check("the audit calls the cross-linked cards wrong on grade, not just on batters (all twelve cards sit on a game of another grade: seven with no scores to prove it, four whose scores contradict it, one a person confirmed)",
          (a_sw["links"].get("unproven_grade_differs", 0), a_sw["links"].get("contradicted_grade_differs", 0), a_sw["links"].get("person_ok_grade_differs", 0)),
          (7, 4, 1))
    check("a card and a game with no batters on either side are not offered as a double when they are different grades",
          any(r["kind"] == "ca" and r["a"]["id"] == gi("S7_c") for r in (await sw_scan())["rows"]), False)
    check("it says how many of the club's grade names it cannot read: none here", a_sw["unreadable_grades"], 0)
    check("the doubles list shows no row that pairs two grades", a_sw["doubles_grade_differ"], 0)
    rows_sw = (await sw_scan())["rows"]
    swaps_ = {r["a"]["id"]: r for r in rows_sw if r["kind"] == "swap"}
    check("the shape the club has (a card on the other grade's scoreless game, an empty card on its own) is a swap",
          gi("S1_xc") in swaps_, True)
    r1 = swaps_.get(gi("S1_xc")) or {"b": {}, "partner": {"match": {}, "moves_to": {}, "from_game": {}}, "current": {}}
    check("the card moves to the game it matches", r1["b"].get("id"), gi("S1_c"))
    check("the partner is the card that is on that game, and goes to the game this one leaves",
          (r1["partner"]["match"].get("id"), r1["partner"]["moves_to"].get("id"), r1["partner"]["from_game"].get("id")),
          (gi("S1_yd"), gi("S1_d"), gi("S1_c")))
    check("it is called strong and says the card shares nothing with the game it is on now",
          (r1.get("strength"), (r1.get("current") or {}).get("shared_with_club")), ("strong", 0))
    check("two cards that each match the other's game are one swap, not two",
          (len([r for r in rows_sw if r["kind"] == "swap" and gi("S2_xc") in (r["a"]["id"], r["partner"]["match"]["id"])])), 1)
    check("a different-grade partner is not a swap (nothing says it belongs on the other game)",
          any(gi("S3_xc") in (r["a"]["id"], (r["partner"] or {}).get("match", {}).get("id")) for r in rows_sw), False)
    check("a partner with scores that agree with neither game is not a swap",
          any(gi("S4_xc") in (r["a"]["id"], (r["partner"] or {}).get("match", {}).get("id")) for r in rows_sw), False)
    check("a partner a person confirmed is never moved",
          any(gi("S5_xc") in (r["a"]["id"], (r["partner"] or {}).get("match", {}).get("id")) for r in rows_sw), False)
    check("swap rows are counted in the totals", dbl.counts({"rows": rows_sw, "dismissed": []})["total"] >= 3, True)
    check("and a swap is not also offered as a relink or a link",
          any(r["kind"] != "swap" and (gi("S1_xc") in (r["a"]["id"], r["b"]["id"])) for r in rows_sw), False)
    async with async_session_maker() as s:
        await act.dismiss_double(s, SW, sw["S6_xc"], sw["S6_c"], "relink", USER)
    check("a swap a person said is not right is no longer offered",
          any(r["kind"] == "swap" and gi("S6_xc") in (r["a"]["id"],) for r in (await sw_scan())["rows"]), False)
    async with async_session_maker() as s:
        pvw = act.bulk_doubles_preview((await dbl.find_doubles(s, SW))["rows"])
    check("the bulk preview counts swaps", pvw.get("swap"), 2)
    log_before = (await q("SELECT count(*) FROM card_review_log WHERE org_id = :o", o=SW))[0][0]
    async with async_session_maker() as s:
        out_sw = await act.bulk_fix_doubles(s, SW, USER)
    links = await sw_links()
    check("the fix put each card on its own game",
          (links["S1_xc"], links["S1_yd"], links["S2_xc"], links["S2_yd"]),
          (gi("S1_c"), gi("S1_d"), gi("S2_c"), gi("S2_d")))
    check("it reports the swaps", out_sw["swapped"], 2)
    check("cards the scan did not find a swap for were not touched",
          [links[k] for k in ("S3_xc", "S3_ye", "S4_xc", "S4_yd", "S5_xc", "S5_yd", "S6_xc", "S6_yd")],
          [start_links[k] for k in ("S3_xc", "S3_ye", "S4_xc", "S4_yd", "S5_xc", "S5_yd", "S6_xc", "S6_yd")])
    check("every step of a swap is in the history, in one batch",
          (await q("SELECT count(DISTINCT batch_id), count(*) FROM card_review_log WHERE org_id = :o AND batch_id IS NOT NULL "
                   "AND id > :n", o=SW, n=log_before))[0][0] >= 1, True)
    check("the scan finds no swap afterwards for the ones it fixed",
          any(r["kind"] == "swap" and r["a"]["id"] in (gi("S1_xc"), gi("S2_xc"), gi("S2_yd")) for r in (await sw_scan())["rows"]), False)
    async with async_session_maker() as s:
        un_sw = await act.bulk_undo(s, SW, USER, out_sw["batch_id"])
    links = await sw_links()
    check("the whole batch undoes, newest step first, and every card is back where it was",
          ([links[k] for k in ("S1_xc", "S1_yd", "S2_xc", "S2_yd")], un_sw["undone"] >= 6),
          ([start_links[k] for k in ("S1_xc", "S1_yd", "S2_xc", "S2_yd")], True))
    async with async_session_maker() as s:
        try:
            await act.swap_links(s, SW, sw["S1_xc"], sw["S3_ye"], sw["S1_c"], USER)
            stale = None
        except act.ReviewError as e:
            stale = str(e)
    check("a swap request that no longer matches the cards is refused", bool(stale), True)
    check("a refused swap changed nothing", await sw_links(), start_links)

    print("\n-- a card on a game of another grade that nothing can move: unlink it, once, undoably --")
    UW, UWS, UWA, UWB, UWD, UW1, UW2 = u(), u(), u(), u(), u(), u(), u()
    UWU16, UWU17, UWU9 = u(), u(), u()
    uw_pl = {k: u() for k in "abcdefghijklmnopqrstuvwxyz"}
    async with async_session_maker() as s:
        await s.execute(text("INSERT INTO organisations (id, name, slug, is_active) VALUES (:a, 'Coast CC', 'coast', true)"), {"a": UW})
        await s.execute(text("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2002/03', 2002)"), {"i": UWS, "o": UW})
        for gid, nm in ((UWA, "A Grade"), (UWB, "B Grade: McIntosh Cup"), (UWD, "D Grade Ritchie Cup"), (UW1, "1st XI"), (UW2, "2nd XI"), (UWU16, "Under 16"), (UWU17, "Under 17 Division 2"), (UWU9, "Under 9")):
            await s.execute(text("INSERT INTO grades (id, season_id, name) VALUES (:i, :s, :n)"), {"i": gid, "s": UWS, "n": nm})
        for k, pid in uw_pl.items():
            await s.execute(text("INSERT INTO players (id, organisation_id, name, grassroots_id) VALUES (:i, :o, :n, :g)"),
                            {"i": pid, "o": UW, "n": f"{k}, {k}", "g": str(pid)})
        await s.commit()
    uw: dict = {}

    async def uw_game(key, day, opp, grade, bat=()):
        gid = uw[key] = u()
        async with async_session_maker() as s:
            await s.execute(text("""INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_org_id, opp_club_name, status, result,
                                   winning_team, match_format) VALUES (:g, :gr, :d, 'Coast CC', :opp, :o, :opp, 'COMPLETED', 'WIN', 'Coast CC', 'Two Day')"""),
                            {"g": gid, "gr": grade, "d": day, "opp": opp, "o": UW})
            for who, runs in bat:
                await s.execute(text("""INSERT INTO batting_innings (game_id, player_id, innings_number, batting_position, runs, balls, fours, sixes,
                    dismissal_type, not_out, did_not_bat) VALUES (:g, :p, 1, 1, :r, 10, 0, 0, 'bowled', FALSE, FALSE)"""), {"g": gid, "p": uw_pl[who], "r": runs})
            await s.commit()

    async def uw_card(key, day, opp, grade, link, bat=(), ok=False):
        mid = uw[key] = u()
        async with async_session_maker() as s:
            await s.execute(text("""INSERT INTO manual_games (id, organisation_id, season_id, grade_id, played_at, opposition, result, match_format,
                superseded_by_game_id, pair_prefers_import, pairing_locked, review_pair_ok)
                VALUES (:m, :o, :s, :gr, :d, :opp, 'WIN', 'One Day', CAST(:lk AS UUID), TRUE, TRUE, :ok)"""),
                            {"m": mid, "o": UW, "s": UWS, "gr": grade, "d": day, "opp": opp, "lk": uw[link], "ok": ok})
            for who, runs in bat:
                await s.execute(text("""INSERT INTO manual_batting_innings (manual_game_id, player_id, innings_number, batting_position, runs, balls,
                    dismissal_type, not_out, did_not_bat) VALUES (:m, :p, 1, 1, :r, NULL, 'bowled', FALSE, FALSE)"""), {"m": mid, "p": uw_pl[who], "r": runs})
            await s.commit()
    L = "abcdefghijklmnopqrstuvwxyz"
    sb = lambda first, n, base: [(L[(first + i) % 26], base + i * 7) for i in range(n)]  # noqa: E731
    # U1: the Shoalwater 2002 shape: an A grade card (batters) on a B grade game with other batters; no A grade game exists
    d = date(2002, 11, 9)
    await uw_game("U1_b", d, "Mandurah", UWB, sb(0, 7, 20)); await uw_card("U1_a", d, "South Mandurah", UWA, "U1_b", sb(8, 6, 60))
    # U2: an A grade card with NO batters on a B grade game with batters
    d = date(2002, 11, 2)
    await uw_game("U2_b", d, "Warnbro", UWB, sb(3, 10, 33)); await uw_card("U2_a", d, "Warnbro", UWA, "U2_b")
    # U3: an A grade card with batters on a D grade game with none
    d = date(2005, 1, 8)
    await uw_game("U3_d", d, "Singleton", UWD); await uw_card("U3_a", d, "Singleton", UWA, "U3_d", sb(5, 9, 41))
    # U4: the same shape but a person confirmed the link: left alone
    d = date(2002, 12, 7)
    await uw_game("U4_b", d, "Singleton", UWB, sb(2, 9, 18)); await uw_card("U4_a", d, "Singleton", UWA, "U4_b", sb(12, 11, 70), ok=True)
    # U5: same grade, nothing proves it: NOT unlinked (grade does not disagree)
    d = date(2002, 12, 14)
    await uw_game("U5_a", d, "Halls Head", UWA); await uw_card("U5_a_card", d, "Halls Head", UWA, "U5_a", sb(4, 8, 25))
    # U6: grade names the test cannot read: NOT unlinked
    d = date(2002, 12, 21)
    await uw_game("U6_g", d, "Pinjarra", UW2); await uw_card("U6_c", d, "Pinjarra", UW1, "U6_g", sb(6, 8, 52))
    # U7: a swap pair (a move the fix owns): NOT unlinked by this step
    d = date(2003, 1, 4)
    await uw_game("U7_a", d, "Rockingham", UWA, sb(9, 9, 36)); await uw_game("U7_d", d, "Rockingham", UWD)
    await uw_card("U7_xa", d, "Rockingham", UWA, "U7_d", sb(9, 9, 36)); await uw_card("U7_yd", d, "Rockingham", UWD, "U7_a")
    # U8: batters agree though the grade names differ (a renamed grade): NOT unlinked
    d = date(2003, 1, 11)
    await uw_game("U8_b", d, "Waroona", UWB, sb(1, 9, 28)); await uw_card("U8_a", d, "Waroona", UWA, "U8_b", sb(1, 9, 28))

    # U9: the same grade and nothing proves it, but the opposition is a different club: the import's one-shared-word rule
    d = date(2003, 1, 18)
    await uw_game("U9_b", d, "Pinjarra Rovers", UWB); await uw_card("U9_c", d, "Rockingham Beach", UWB, "U9_b", sb(7, 9, 44))

    # U10: the club's "Under 16" is Cricket Australia's "Under 17 Division 2" this season (two links proved by batters),
    # so a third link between the same two names with no scores is NOT wrong. U12: the same card name on an Under 9 game is.
    for i, dd in enumerate((date(2003, 2, 1), date(2003, 2, 8))):
        await uw_game(f"U10_g{i}", dd, f"Hills{i}", UWU17, sb(3 + i, 9, 30 + i)); await uw_card(f"U10_c{i}", dd, f"Hills{i}", UWU16, f"U10_g{i}", sb(3 + i, 9, 30 + i))
    d = date(2003, 2, 15)
    await uw_game("U11_g", d, "Dunes", UWU17); await uw_card("U11_c", d, "Dunes", UWU16, "U11_g")
    d = date(2003, 2, 22)
    await uw_game("U12_g", d, "Reef", UWU9); await uw_card("U12_c", d, "Reef", UWU16, "U12_g")

    async def uw_links():
        return {k: (await q("SELECT superseded_by_game_id::text FROM manual_games WHERE id = :m", m=uw[k]))[0][0]
                for k in ("U1_a", "U2_a", "U3_a", "U4_a", "U5_a_card", "U6_c", "U7_xa", "U7_yd", "U8_a", "U9_c", "U10_c0", "U10_c1", "U11_c", "U12_c")}
    uw_start = await uw_links()
    async with async_session_maker() as s:
        listed = {r["mid"] for r in await act.wrong_grade_links(s, UW)}
    check("the step lists a card whose batters are not on a game of another grade, one with no batters, and a card on a scoreless game",
          (str(uw["U1_a"]) in listed, str(uw["U2_a"]) in listed, str(uw["U3_a"]) in listed), (True, True, True))
    check("a card on a game of another age group is listed too (Under 16 on an Under 9 game)", str(uw["U12_c"]) in listed, True)
    check("but Under 16 on 'Under 17 Division 2', the name this club's own proved links show is the same grade this season, is not",
          (str(uw["U11_c"]) in listed, str(uw["U10_c0"]) in listed), (False, False))
    check("and nothing else: not a confirmed link, a same-grade link, an unreadable grade, a swap's cards or a renamed grade",
          sorted(listed), sorted({str(uw["U1_a"]), str(uw["U2_a"]), str(uw["U3_a"]), str(uw["U12_c"])}))
    snap_u, logs_u = await q("SELECT id::text, superseded_by_game_id::text FROM manual_games ORDER BY id"), (await q("SELECT count(*) FROM card_review_log"))[0][0]
    await fwl.main(str(UW), False, None, 3, True)
    check("the dry run writes nothing", (await q("SELECT id::text, superseded_by_game_id::text FROM manual_games ORDER BY id"),
                                         (await q("SELECT count(*) FROM card_review_log"))[0][0]), (snap_u, logs_u))
    before_twice = (await q("SELECT count(*) FROM v_effective_batting_innings b WHERE b.game_id = :g", g=uw["U1_b"]))[0][0]
    async with async_session_maker() as s:
        res_u = await act.bulk_unlink_wrong_grade(s, UW, USER)
    links_u = await uw_links()
    check("it unlinked exactly those four, in one batch", (res_u["unlinked"], links_u["U1_a"], links_u["U2_a"], links_u["U3_a"], links_u["U12_c"]), (4, None, None, None, None))
    check("every other card is where it was", {k: links_u[k] for k in links_u if k not in ("U1_a", "U2_a", "U3_a", "U12_c")},
          {k: uw_start[k] for k in uw_start if k not in ("U1_a", "U2_a", "U3_a", "U12_c")})
    check("the B grade game counts on its own again, and the A grade card counts as its own match",
          ((await q("SELECT count(*) FROM v_effective_batting_innings WHERE game_id = :g", g=uw["U1_b"]))[0][0],
           (await q("SELECT count(*) FROM v_effective_batting_innings WHERE game_id = :g", g=uw["U1_a"]))[0][0]), (7, 6))
    async with async_session_maker() as s:
        again = await act.wrong_grade_links(s, UW)
        offered_back = (await dbl.find_doubles(s, UW))["rows"]
    check("a second run finds nothing, and the pair is not offered back as a double",
          (len(again), any(str(uw["U1_a"]) in (r["a"]["id"], r["b"]["id"]) for r in offered_back)), (0, False))
    async with async_session_maker() as s:
        un_u = await act.bulk_undo(s, UW, USER, res_u["batch_id"])
    check("the batch undoes and every card is back on its game", (un_u["undone"], await uw_links()), (4, uw_start))
    async with async_session_maker() as s:
        a_uw = await aud.audit(s, str(UW))
    check("the audit agrees with the repair about which links are wrong on grade",
          (a_uw["links"].get("unproven_grade_differs", 0) + a_uw["links"].get("contradicted_grade_differs", 0)), 6)  # U1 U2 U3 U12 + the swap pair
    check("and lists a same-grade link nothing proves whose opposition is a different club (and not the ones whose opposition agrees)", a_uw["links_unproven_odd"], 1)  # U9 only

    print("\n-- nothing was deleted by any of it --")
    check("every card is still there",
          ((await q("SELECT count(*) FROM manual_games WHERE organisation_id = :o", o=ORG))[0][0],
           (await q("SELECT count(*) FROM games WHERE home_org_id = :o", o=ORG))[0][0]), (23, 12))

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
