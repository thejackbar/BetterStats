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
  MUTATE=blindlink  the scan only looks at unlinked cards (how the first release missed a card linked to the wrong game)
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

    if mutate == "blindlink":
        real_pairs = dbl.match_pairs_ca

        def unlinked_only(manuals, synced, banned, linked_ids=frozenset()):
            return real_pairs([m for m in manuals if m.id not in linked_ids], synced, banned, frozenset())
        dbl.match_pairs_ca = unlinked_only
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
    async with async_session_maker() as s:
        await act.undo_last(s, ORG, ids["m_wB"], USER)
        out_r = await act.restore_double(s, ORG, ids["m_wB"], ids["g_wA"], "ca", USER)
    check("once the newer change is undone, Put back restores the link", ((await q("SELECT superseded_by_game_id FROM manual_games WHERE id = :m", m=ids["m_wB"]))[0][0], out_r["relinked"]), (ids["g_wA"], True))
    check("and clears the answer, so the pair is not hidden for good",
          (await q("SELECT count(*) FROM card_review_log WHERE manual_game_id = :m AND action = 'not_double' AND undone_at IS NULL", m=ids["m_wB"]))[0][0], 0)
    check("the scan offers the wrong link again", k_wrong in kinds(await scan()), True)
    async with async_session_maker() as s:
        await act.unlink(s, ORG, ids["m_wB"], USER)
        undone = await act.undo_last(s, ORG, ids["m_wB"], USER)
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

    print("\n-- nothing was deleted by any of it --")
    check("every card is still there",
          ((await q("SELECT count(*) FROM manual_games WHERE organisation_id = :o", o=ORG))[0][0],
           (await q("SELECT count(*) FROM games WHERE home_org_id = :o", o=ORG))[0][0]), (23, 12))

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
