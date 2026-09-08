"""Verification for suggested duplicate grades, against a real Postgres.

Asked for on Manage Grades: suggest the grades that look like duplicates, and
find out whether Cricket Australia's own grade id can help.

TWO MEASUREMENTS DECIDED THE DESIGN, AND BOTH ARE PINNED HERE.

1. **A CA GRADE GUID IS MINTED FRESH EVERY SEASON**, so it can never link two
   spellings of one grade. Queried live against a real club before anything was
   built: across 2023/24, 2024/25 and 2025/26, **0 of 43** grade guids repeated,
   while the same grade NAME carried three different guids. The ASSOCIATION guid
   on the very same payload IS stable across all three seasons, and is already
   stored (migration 283) — so that is the CA id this feature uses.

2. **EDIT DISTANCE IS BACKWARDS ON GRADE NAMES.** Genuinely different grades
   score HIGHER than real duplicates ('One Day Grade 2'/'... 4' = 0.933 against
   'A Grade'/'A Grade (Gatorade)' = 0.560), so the player matcher's 0.90
   threshold would offer to merge a club's 5th Grade into its 6th. The whole
   calibration table is re-run below as checks.

Runs the SHIPPED service and route bodies — never a re-implementation.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_grade_duplicates.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import Base

# Behind a guard so a CONTROL RUN against a build without the feature REPORTS it
# as one failed check rather than dying on an ImportError and saying nothing at
# all about the other checks.
MISSING: list[str] = []
try:
    from app.services import grade_duplicates
except ImportError as exc:  # pragma: no cover - control run only
    grade_duplicates = None
    MISSING.append(f"services.grade_duplicates ({exc})")

try:
    from app.services.grade_ignore_ddl import STATEMENTS as IGNORE_DDL
except ImportError as exc:  # pragma: no cover - control run only
    IGNORE_DDL = []
    MISSING.append(f"services.grade_ignore_ddl ({exc})")

try:
    from app.routers.admin import get_grade_merge_candidates, ignore_grade_pair, IgnoreGradePairRequest
except ImportError as exc:  # pragma: no cover - control run only
    get_grade_merge_candidates = ignore_grade_pair = IgnoreGradePairRequest = None
    MISSING.append(f"admin route bodies ({exc})")

HAVE = not MISSING

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


ORG = uuid.uuid4()
OTHER = uuid.uuid4()

# Three seasons, so a rename can be shown as non-overlapping and two real
# grades can be shown coexisting.
S23, S24, S25 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
SEASONS = {S23: ("Summer 2023/24", 2023), S24: ("Summer 2024/25", 2024), S25: ("Summer 2025/26", 2025)}

WASTCA = "f5ab258e-b1dc-eb11-a7ad-501ac52e1bf9"
PSWL = "93af5915-5c32-ec11-981f-501ac52e1666"

# (season, name, association_id, association_name, category, games)
# Every name here is a real one off a live club's grade list.
GRADES = [
    # The sponsor case — the same grade, one season carrying a sponsor.
    (S24, "A Grade", WASTCA, "WASTCA", "senior", 12),
    (S25, "A Grade (Gatorade)", WASTCA, "WASTCA", "senior", 10),
    # The rename case — punctuation changed, and the two never coexist.
    (S23, "PSWL South", PSWL, "Perth Scorchers Women's League", "womens", 8),
    (S25, "PSWL: South", PSWL, "Perth Scorchers Women's League", "womens", 9),
    # Two REAL grades that differ by one digit and coexist every season. The
    # player matcher would score these 0.889 and offer to merge them.
    (S25, "5th Grade", WASTCA, "WASTCA", "senior", 14),
    (S25, "6th Grade", WASTCA, "WASTCA", "senior", 13),
    # Two REAL grades differing by a colour — 0.829 by edit distance.
    (S25, "One Day Grade 5 Black", WASTCA, "WASTCA", "senior", 7),
    (S25, "One Day Grade 5 Gold", WASTCA, "WASTCA", "senior", 6),
    # A format word is identity, not decoration: these are two competitions.
    (S25, "1st Grade", WASTCA, "WASTCA", "senior", 16),
    (S25, "One Day Grade 1", WASTCA, "WASTCA", "senior", 11),
    # The documented junior-cup-into-senior-grade case: suggested, with the
    # classification clash raised as a caution rather than a veto.
    (S24, "F Grade", WASTCA, "WASTCA", "senior", 9),
    (S23, "F Grade Colts Cup", WASTCA, "WASTCA", "junior", 4),
    # Same name, two associations we KNOW to be different — never one grade.
    (S24, "Division 2", WASTCA, "WASTCA", "senior", 5),
    (S25, "Div 2", PSWL, "Perth Scorchers Women's League", "womens", 5),
]

# Another club holding the very pair this club would be offered, so the
# suggestions can be shown never to reach across clubs.
OTHER_GRADES = [(S23, "B Grade", 3), (S25, "B Grade (Solo Energy)", 3)]


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        # `games.raw_payload` is JSON on the ORM model and JSONB in the database
        # the migrations build, so a create_all harness gets the narrower type
        # and the effective view's UNION cannot reconcile the two branches.
        await conn.execute(text(
            "ALTER TABLE games ALTER COLUMN raw_payload TYPE jsonb "
            "USING raw_payload::text::jsonb"))
        for _name, stmt in view_statements():
            await conn.execute(text(stmt))
        # grade_merge_logs is a raw pre-ORM table create_all cannot see.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)
        """))


async def apply_ignore_ddl(times: int = 1) -> None:
    """The lifespan re-runs the whole list on every boot, so it must be safe to."""
    for _ in range(times):
        async with engine.begin() as conn:
            for stmt in IGNORE_DDL:
                await conn.execute(text(stmt))


async def seed(session) -> None:
    for org, name in ((ORG, "Applecross Cricket Club"), (OTHER, "High Wycombe Cricket Club")):
        await session.execute(text(
            "INSERT INTO organisations (id, name, is_active) VALUES (:i, :n, true)"
        ), {"i": org, "n": name})
    for sid, (name, year) in SEASONS.items():
        for org in (ORG, OTHER):
            await session.execute(text(
                "INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, :n, :y)"
            ), {"i": sid if org == ORG else uuid.uuid5(org, str(sid)), "o": org, "n": name, "y": year})

    async def add_grade(org, season_id, name, assoc, assoc_name, category, games):
        gid = uuid.uuid4()
        await session.execute(text("""
            INSERT INTO grades (id, season_id, name, grassroots_id, association_id,
                                association_name, category, categories, is_public)
            VALUES (:i, :s, :n, :g, :a, :an, :c, :cs, true)
        """), {"i": gid, "s": season_id, "n": name,
               # A FRESH CA guid per grade row, which is what the live API does.
               "g": str(uuid.uuid4()), "a": assoc, "an": assoc_name,
               "c": category, "cs": [category] if category else None})
        for n in range(games):
            # `games` has no `source` of its own — the effective view stamps
            # 'api' on this branch.
            await session.execute(text("""
                INSERT INTO games (id, grade_id, played_at)
                VALUES (:i, :g, :d)
            """), {"i": uuid.uuid4(), "g": gid, "d": date(2025, 1, 1)})

    for sid, name, assoc, assoc_name, category, games in GRADES:
        await add_grade(ORG, sid, name, assoc, assoc_name, category, games)
    for sid, name, games in OTHER_GRADES:
        await add_grade(OTHER, uuid.uuid5(OTHER, str(sid)), name, WASTCA, "WASTCA", "senior", games)


def pair_for(pairs, a: str, b: str):
    want = {a, b}
    for p in pairs:
        if {p["grade_a"]["grade_name"], p["grade_b"]["grade_name"]} == want:
            return p
    return None


# The exact calibration that killed the similarity approach. Re-run as checks so
# a future "let's just use SequenceMatcher" cannot pass.
REAL_DUPLICATES = [
    ("PSWL South", "PSWL: South"),
    ("A Grade", "A Grade (Gatorade)"),
    ("Under 14s", "Under-14s"),
    ("Under 14s", "U14"),
    ("Under 14s", "U14s"),
    ("Year 9 Boys", "Yr9 Boys"),
    ("One Day Grade 5 Black", "One Day Grade 5 - Black"),
    ("Twenty20 Div 2", "Twenty20 Division 2"),
    ("Twenty20 Div 2", "Twenty20 Divsion 2"),
    ("Division 1", "Div 1"),
    ("F Grade", "F Grade Colts Cup"),
    ("RJR Sports T20 Division 1", "RJR T20 Division 1"),
]
DIFFERENT_GRADES = [
    ("5th Grade", "6th Grade"),
    ("One Day Grade 2", "One Day Grade 4"),
    ("PSWL South A", "PSWL South B"),
    ("Twenty20 Div 2", "Twenty20 Div 3"),
    ("1st Grade", "3rd Grade"),
    ("Under 14s", "Under 16s"),
    ("U14", "U16"),
    ("One Day Grade 5 Black", "One Day Grade 5 Gold"),
    ("1st Grade", "One Day Grade 1"),
    ("5th Grade", "One Day Grade 5"),
    ("1st Grade", "1st Grade T20"),
    ("Under 14s", "Under 14s T20"),
    ("A Grade", "A Grade (One Day)"),
    ("A Grade", "B Grade"),
    ("Colts T20", "Twenty20 Div 1"),
    ("Year 9 Boys", "Year 9 Girls"),
]


class _Actor:
    """Stand-in for the signed-in admin the route bodies take."""
    id = uuid.uuid4()


async def main() -> None:
    if not HAVE:
        check("suggested duplicate grades are built at all", False, "; ".join(MISSING))
        print(f"\n{PASS} passed, {FAIL} failed")
        await engine.dispose()
        sys.exit(1)

    print("\n-- the calibration that ruled out edit distance --")
    for a, b in REAL_DUPLICATES:
        v = grade_duplicates.classify_pair(a, b)
        check(f"a real duplicate is caught: {a!r} / {b!r}", bool(v), str(v))
    for a, b in DIFFERENT_GRADES:
        v = grade_duplicates.classify_pair(a, b)
        check(f"two REAL grades are refused: {a!r} / {b!r}",
              v is None, f"offered as {v['kind'] if v else None}")

    print("\n-- the discriminator rule itself --")
    check("a number is a discriminator, never decoration",
          grade_duplicates.split_tokens("5th Grade")[0] == frozenset({"5"}),
          str(grade_duplicates.split_tokens("5th Grade")))
    check("an ordinal loses its suffix — 5th and 5 are one number",
          grade_duplicates.split_tokens("5th Grade")[0]
          == grade_duplicates.split_tokens("Grade 5")[0])
    check("a bare letter is a grade tier",
          grade_duplicates.split_tokens("F Grade")[0] == frozenset({"f"}))
    check("a colour is a discriminator — Black and Gold are two real grades",
          "black" in grade_duplicates.split_tokens("One Day Grade 5 Black")[0])
    check("THE MATCH FORMAT THE NAME ANNOUNCES IS A DISCRIMINATOR",
          "fmt:one_day" in grade_duplicates.split_tokens("One Day Grade 1")[0],
          str(grade_duplicates.split_tokens("One Day Grade 1")))
    check("and it is read off the RAW name, so a parenthetical the sponsor "
          "strip removes is still seen",
          "fmt:one_day" in grade_duplicates.split_tokens("A Grade (One Day)")[0])
    # An abbreviation must EXPAND ('div' -> 'division'), never contract:
    # contracting leaves a misspelt 'Divsion' compared against a three-letter
    # stub, which scores 0.60 and reads as a different word. Dropping a plural
    # 's' is the one shortening allowed — it takes one character off both sides
    # equally and cannot hide a typo.
    contracted = {k: v for k, v in grade_duplicates._SYNONYMS.items() if len(v) < len(k) - 1}
    check("NO SYNONYM CONTRACTS AN ABBREVIATION — contracting hides a typo "
          "behind a stub (found by running it)",
          not contracted, str(contracted))
    check("and the abbreviation this was found on expands",
          grade_duplicates._SYNONYMS.get("div") == "division")
    check("so a misspelt Division is still caught",
          (grade_duplicates.classify_pair("Twenty20 Div 2", "Twenty20 Divsion 2") or {}).get("kind")
          == "word_typo")

    await build_schema()
    await apply_ignore_ddl(times=3)
    check("the ignore-table DDL applies three times over — the lifespan mirror "
          "re-runs the whole list on every boot", True)

    async with Session() as session:
        await seed(session)
        await session.commit()

    actor = _Actor()

    async with Session() as session:
        pairs = await get_grade_merge_candidates(str(ORG), session, actor)
        names = {(p["grade_a"]["grade_name"], p["grade_b"]["grade_name"]) for p in pairs}
        print(f"\n-- the club's own grade list, {len(pairs)} pair(s) suggested --")
        for p in pairs:
            print(f"     {p['kind']:12} {p['alias']!r} -> {p['canonical']!r}")

        print("\n-- what is offered --")
        sponsor = pair_for(pairs, "A Grade", "A Grade (Gatorade)")
        check("the sponsored spelling is offered", sponsor is not None)
        check("as the near-certain tier", sponsor and sponsor["kind"] == "same_name", str(sponsor and sponsor["kind"]))
        check("THE FULLER RECORD IS KEPT — 12 games beats 10",
              sponsor and sponsor["canonical"] == "A Grade", str(sponsor and sponsor["canonical"]))

        rename = pair_for(pairs, "PSWL South", "PSWL: South")
        check("the punctuation-only rename is offered", rename is not None)
        check("and says they were never played in the same season, which reads "
              "as a rename",
              rename and any("never played in the same season" in c for c in rename["cautions"]),
              str(rename and rename["cautions"]))

        colts = pair_for(pairs, "F Grade", "F Grade Colts Cup")
        check("the junior-sounding cup name is offered against the senior grade "
              "— a merge this platform has already seen happen", colts is not None)
        check("as the weaker extra-words tier, never bulk-safe",
              colts and colts["kind"] == "extra_words" and not colts["bulk_safe"],
              str(colts and (colts["kind"], colts["bulk_safe"])))
        check("A CLASSIFICATION CLASH IS A CAUTION, NEVER A VETO — refusing it "
              "would block that merge",
              colts and any("Classified differently" in c for c in colts["cautions"]),
              str(colts and colts["cautions"]))

        print("\n-- what is refused --")
        check("5th Grade is never offered against 6th Grade",
              pair_for(pairs, "5th Grade", "6th Grade") is None)
        check("One Day Grade 5 Black is never offered against Gold",
              pair_for(pairs, "One Day Grade 5 Black", "One Day Grade 5 Gold") is None)
        check("1st Grade is never offered against One Day Grade 1 — naming a "
              "format is identity, not decoration",
              pair_for(pairs, "1st Grade", "One Day Grade 1") is None)

        print("\n-- the one place Cricket Australia's ids decide anything --")
        cross = pair_for(pairs, "Division 2", "Div 2")
        check("TWO NAMES THAT WOULD OTHERWISE MATCH ARE REFUSED when the "
              "association guids say they are different competitions",
              cross is None,
              "offered despite disjoint associations")
        check("a same-association pair still reports which association it is",
              sponsor and any("WASTCA" in c for c in sponsor["cautions"]),
              str(sponsor and sponsor["cautions"]))
        check("the association is carried on the card",
              sponsor and sponsor["grade_a"]["association_names"] == ["WASTCA"],
              str(sponsor and sponsor["grade_a"]))

        print("\n-- scope --")
        check("another club's identical pair is never offered here",
              not any("B Grade" in n or "B Grade (Solo Energy)" in n
                      for pair in names for n in pair),
              str(names))
        other_pairs = await get_grade_merge_candidates(str(OTHER), session, actor)
        check("and that club gets its own pair when it asks",
              pair_for(other_pairs, "B Grade", "B Grade (Solo Energy)") is not None,
              str([(p["alias"], p["canonical"]) for p in other_pairs]))

        print("\n-- a pair is only ever bulk-safe on the near-certain tier --")
        check("only same_name may be bulk-merged",
              all(p["kind"] in grade_duplicates.BULK_SAFE_KINDS for p in pairs if p["bulk_safe"]),
              str([(p["kind"], p["bulk_safe"]) for p in pairs]))
        check("and never while the two coexisted in a season",
              all(not p["bulk_safe"] for p in pairs
                  if any("may be two real grades" in c for c in p["cautions"])))

        print("\n-- dismissing a pair --")
        before = len(pairs)
        await ignore_grade_pair(
            IgnoreGradePairRequest(org_id=str(ORG), name_a="F Grade Colts Cup", name_b="F Grade"),
            session, actor)
        after = await get_grade_merge_candidates(str(ORG), session, actor)
        check("a dismissed pair stops being suggested",
              pair_for(after, "F Grade", "F Grade Colts Cup") is None)
        check("and only that pair goes", len(after) == before - 1, f"{before} -> {len(after)}")

        await ignore_grade_pair(
            IgnoreGradePairRequest(org_id=str(ORG), name_a="F Grade", name_b="F Grade Colts Cup"),
            session, actor)
        again = await get_grade_merge_candidates(str(ORG), session, actor)
        check("DISMISSING IT THE OTHER WAY ROUND IS THE SAME PAIR, not a second "
              "row — names are stored sorted",
              len(again) == len(after))
        rows = await session.execute(text(
            "SELECT COUNT(*) FROM grade_merge_pair_ignores WHERE org_id = :o"), {"o": ORG})
        check("one dismissal, one row", rows.scalar() == 1, str(rows))

    # The lifespan mirror re-runs the DDL on every boot, so it has to be safe
    # over a table that already holds a club's dismissals — not just an empty one.
    await apply_ignore_ddl(times=2)
    async with Session() as session:
        rows = await session.execute(text("SELECT COUNT(*) FROM grade_merge_pair_ignores"))
        check("re-running the DDL over a POPULATED table keeps the dismissal",
              rows.scalar() == 1, str(rows))
        still = await get_grade_merge_candidates(str(ORG), session, actor)
        check("and the pair stays dismissed after the re-run",
              pair_for(still, "F Grade", "F Grade Colts Cup") is None)

        check("another club is unaffected by this club's dismissal",
              pair_for(await get_grade_merge_candidates(str(OTHER), session, actor),
                       "B Grade", "B Grade (Solo Energy)") is not None)

        print("\n-- refusals --")
        for label, a, b in (("a blank name", "", "A Grade"),
                            ("one name twice", "A Grade", "A Grade")):
            try:
                await ignore_grade_pair(
                    IgnoreGradePairRequest(org_id=str(ORG), name_a=a, name_b=b), session, actor)
                check(f"{label} is refused", False, "accepted")
            except Exception as exc:
                check(f"{label} is refused", getattr(exc, "status_code", None) == 400, str(exc))

    print("\n-- an already-merged group is not suggested against itself --")
    async with Session() as session:
        await session.execute(text("""
            INSERT INTO grade_merge_logs (org_id, canonical_name, alias_name)
            VALUES (:o, 'A Grade', 'A Grade (Gatorade)')
        """), {"o": ORG})
        await session.commit()
        merged = await get_grade_merge_candidates(str(ORG), session, actor)
        check("the merged spelling is gone from the suggestions",
              pair_for(merged, "A Grade", "A Grade (Gatorade)") is None,
              str([(p["alias"], p["canonical"]) for p in merged]))
        check("and no pair names a grade the screen no longer lists",
              all("A Grade (Gatorade)" not in (p["grade_a"]["grade_name"], p["grade_b"]["grade_name"])
                  for p in merged))

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
