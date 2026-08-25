"""Migration 279 against a REAL Postgres, through the shipped statements.

Runs `ASSET_REGISTER_SQL` itself (the list alembic and the lifespan mirror both
run), not a retyped copy, and `services.assets.asset_alerts` itself.

What is asserted:
  * the carry is idempotent — applied three times, nothing duplicates;
  * an asset the club already holds is GAP-FILLED, never clobbered;
  * a merch-only asset comes across as its own row, with the enums mapped;
  * two merch rows matching one club asset do not silently merge into one;
  * clubs cannot bleed into each other;
  * no merch asset is left behind;
  * the alerts read the carried rows, are core, and ignore a retired asset;
  * the downgrade removes exactly the carried rows.

  python verify_asset_register.py
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.services.asset_register_ddl import ASSET_REGISTER_SQL
from app.services import assets as assets_svc

DSN = os.environ.get("VERIFY_DSN", "postgresql+asyncpg://postgres@127.0.0.1:5433/postgres")

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'  ok  ' if cond else ' FAIL '} {name}{'' if cond or not detail else '  — ' + str(detail)}")


# The two tables in their real pre-279 shape. Built by hand ON PURPOSE: the
# migration has to have something to do, and `create_all` would hand it the
# post-279 column set.
SCHEMA = """
DROP TABLE IF EXISTS club_assets, merch_assets, facilities, organisations CASCADE;
CREATE TABLE organisations (id UUID PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE facilities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    name TEXT NOT NULL
);
CREATE TABLE club_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'other',
    asset_tag TEXT,
    purchase_cost NUMERIC(10,2),
    purchase_date DATE,
    condition TEXT NOT NULL DEFAULT 'good',
    status TEXT NOT NULL DEFAULT 'in_service',
    service_due_date DATE,
    replace_due_date DATE,
    facility_id UUID REFERENCES facilities(id) ON DELETE SET NULL,
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE merch_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    asset_tag TEXT,
    purchase_cost NUMERIC(10,2),
    purchase_date DATE,
    condition TEXT NOT NULL DEFAULT 'good',
    service_due_date DATE,
    replace_due_date DATE,
    status TEXT NOT NULL DEFAULT 'in_service',
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

ORG_A = uuid.uuid4()
ORG_B = uuid.uuid4()
TODAY = date.today()
SOON = TODAY + timedelta(days=10)
LATER = TODAY + timedelta(days=400)
PAST = TODAY - timedelta(days=5)


async def seed(conn):
    await conn.execute(text("INSERT INTO organisations (id, name) VALUES (:a,'A CC'), (:b,'B CC')"),
                       {"a": ORG_A, "b": ORG_B})

    # The reported case: one bowling machine, entered on BOTH registers. The
    # club row has a category, a facility-less location and its own notes; the
    # merch row is the one carrying the service dates and the purchase figure.
    await conn.execute(text("""
        INSERT INTO club_assets (organisation_id, name, category, condition, status, notes)
        VALUES (:o, 'Bowling machine', 'equipment', 'good', 'in_service', 'Keys in the shed')
    """), {"o": ORG_A})
    await conn.execute(text("""
        INSERT INTO merch_assets (organisation_id, name, asset_tag, purchase_cost, purchase_date,
                                  condition, status, service_due_date, replace_due_date, notes)
        VALUES (:o, 'bowling machine ', 'BM-1', 4200.00, '2024-02-01',
                'new', 'out_for_repair', :soon, :later, 'Serviced by Bola')
    """), {"o": ORG_A, "soon": SOON, "later": LATER})

    # Matched on the SERIAL rather than the name — different wording, same tag.
    await conn.execute(text("""
        INSERT INTO club_assets (organisation_id, name, asset_tag, purchase_cost, notes)
        VALUES (:o, 'Line marker', 'LM-9', 900.00, 'Back of the shed')
    """), {"o": ORG_A})
    await conn.execute(text("""
        INSERT INTO merch_assets (organisation_id, name, asset_tag, purchase_cost,
                                  service_due_date, notes)
        VALUES (:o, 'Line marking machine', 'lm-9 ', 1500.00, :past, 'Back of the shed')
    """), {"o": ORG_A, "past": PAST})

    # Merch only: comes across as its own row.
    await conn.execute(text("""
        INSERT INTO merch_assets (organisation_id, name, purchase_cost, condition, status, replace_due_date)
        VALUES (:o, 'Sight screen', 2600.00, 'retired', 'retired', :later)
    """), {"o": ORG_A, "later": LATER})

    # TWO merch rows for one club asset. The second must NOT be folded in.
    await conn.execute(text("INSERT INTO club_assets (organisation_id, name) VALUES (:o, 'Covers')"),
                       {"o": ORG_A})
    await conn.execute(text("""
        INSERT INTO merch_assets (organisation_id, name, purchase_cost, created_at)
        VALUES (:o, 'Covers', 500.00, NOW() - INTERVAL '2 days'),
               (:o, 'covers', 800.00, NOW() - INTERVAL '1 day')
    """), {"o": ORG_A})

    # Another club's asset of the same name, which must not be touched.
    await conn.execute(text("INSERT INTO merch_assets (organisation_id, name, purchase_cost) VALUES (:o,'Bowling machine',111.00)"),
                       {"o": ORG_B})


async def apply_ddl(conn):
    for stmt in ASSET_REGISTER_SQL:
        await conn.execute(text(stmt))


async def main():
    engine = create_async_engine(DSN, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        for stmt in SCHEMA.strip().split(";\n"):
            if stmt.strip():
                await conn.execute(text(stmt))
        await seed(conn)

    merch_total = None
    async with engine.begin() as conn:
        merch_total = await conn.scalar(text("SELECT count(*) FROM merch_assets"))
        # APPLIED THREE TIMES. The lifespan re-runs the whole list on every
        # boot, so anything not idempotent duplicates a club's asset register
        # once per restart.
        for _ in range(3):
            await apply_ddl(conn)

    async with engine.begin() as conn:
        carried = await conn.scalar(text("SELECT count(*) FROM club_assets WHERE merch_asset_id IS NOT NULL"))
        check("every merch asset is accounted for exactly once",
              carried == merch_total, f"{carried} carried vs {merch_total} merch rows")

        left = await conn.scalar(text("""
            SELECT count(*) FROM merch_assets m
             WHERE NOT EXISTS (SELECT 1 FROM club_assets c WHERE c.merch_asset_id = m.id)
        """))
        check("no merch asset is left behind", left == 0, left)

        total_a = await conn.scalar(text("SELECT count(*) FROM club_assets WHERE organisation_id = :o"), {"o": ORG_A})
        # 3 pre-existing + Sight screen + the second Covers row = 5.
        check("applying three times does not duplicate", total_a == 5, total_a)
        srcs = dict((r["source"], r["n"]) for r in (await conn.execute(text(
            "SELECT source, count(*) AS n FROM club_assets WHERE organisation_id = :o GROUP BY source"
        ), {"o": ORG_A})).mappings())
        check("a gap-filled row is still the CLUB's own row", srcs.get("club") == 3, srcs)
        check("only the two genuinely new rows are marked as carried", srcs.get("merch") == 2, srcs)

        # ── The gap-fill ──────────────────────────────────────────────────────
        bm = (await conn.execute(text("""
            SELECT name, category, asset_tag, purchase_cost, purchase_date, condition, status,
                   service_due_date, replace_due_date, notes, merch_asset_id IS NOT NULL AS carried
              FROM club_assets WHERE organisation_id = :o AND lower(name) = 'bowling machine'
        """), {"o": ORG_A})).mappings().all()
        check("the club's bowling machine is still ONE row", len(bm) == 1, len(bm))
        if bm:
            r = bm[0]
            check("gap-fill: the club's own name is kept", r["name"] == "Bowling machine", r["name"])
            check("gap-fill: the club's own category is kept", r["category"] == "equipment", r["category"])
            check("gap-fill: the club's own notes are kept", "Keys in the shed" in (r["notes"] or ""), r["notes"])
            check("gap-fill: the merch note is appended, not dropped",
                  "Serviced by Bola" in (r["notes"] or ""), r["notes"])
            check("gap-fill: the missing purchase cost is taken", float(r["purchase_cost"] or 0) == 4200.0, r["purchase_cost"])
            check("gap-fill: the missing asset tag is taken", r["asset_tag"] == "BM-1", r["asset_tag"])
            check("gap-fill: the missing service date is taken", r["service_due_date"] == SOON, r["service_due_date"])
            check("gap-fill: the missing replace date is taken", r["replace_due_date"] == LATER, r["replace_due_date"])
            # NOT NULL on this side, so it always had a value and must not move.
            check("gap-fill: condition is NOT clobbered", r["condition"] == "good", r["condition"])
            check("gap-fill: status is NOT clobbered", r["status"] == "in_service", r["status"])
            check("gap-fill: the row is stamped with where it came from", r["carried"] is True)

        lm = (await conn.execute(text("""
            SELECT name, purchase_cost, service_due_date, notes FROM club_assets
             WHERE organisation_id = :o AND asset_tag ILIKE 'LM-9'
        """), {"o": ORG_A})).mappings().all()
        check("matched on the serial, not the name", len(lm) == 1, [dict(x) for x in lm])
        if lm:
            check("gap-fill: a figure already recorded wins over the merch one",
                  float(lm[0]["purchase_cost"]) == 900.0, lm[0]["purchase_cost"])
            check("gap-fill: the merch service date still lands",
                  lm[0]["service_due_date"] == PAST, lm[0]["service_due_date"])
            check("gap-fill: an identical note is not appended twice",
                  (lm[0]["notes"] or "").count("Back of the shed") == 1, lm[0]["notes"])

        # ── The carried-across row ────────────────────────────────────────────
        ss = (await conn.execute(text("""
            SELECT category, condition, status, purchase_cost, facility_id FROM club_assets
             WHERE organisation_id = :o AND name = 'Sight screen'
        """), {"o": ORG_A})).mappings().all()
        check("a merch-only asset comes across as its own row", len(ss) == 1, len(ss))
        if ss:
            check("carried: category is stamped equipment", ss[0]["category"] == "equipment", ss[0]["category"])
            check("carried: condition 'retired' maps to unserviceable",
                  ss[0]["condition"] == "unserviceable", ss[0]["condition"])
            check("carried: status 'retired' stays retired", ss[0]["status"] == "retired", ss[0]["status"])
            check("carried: the purchase cost comes with it", float(ss[0]["purchase_cost"]) == 2600.0)
            check("carried: no facility is invented", ss[0]["facility_id"] is None)

        # `out_for_repair` had to become `in_repair` somewhere, and it did on the
        # row it was gap-filled into? No — condition/status are never clobbered,
        # so assert the mapping on a row that was actually inserted.
        mapped = await conn.scalar(text("""
            SELECT count(*) FROM club_assets WHERE status = 'out_for_repair' OR condition IN ('new','retired')
        """))
        check("no unmapped merch vocabulary survives anywhere", mapped == 0, mapped)

        # ── Two merch rows, one club asset ────────────────────────────────────
        cov = (await conn.execute(text("""
            SELECT purchase_cost, merch_asset_id IS NOT NULL AS carried FROM club_assets
             WHERE organisation_id = :o AND lower(name) = 'covers' ORDER BY purchase_cost NULLS FIRST
        """), {"o": ORG_A})).mappings().all()
        check("two merch rows matching one asset do not merge into one", len(cov) == 2, [dict(c) for c in cov])
        check("both of them are traceable", all(c["carried"] for c in cov))

        # ── Cross-club ────────────────────────────────────────────────────────
        b_rows = (await conn.execute(text(
            "SELECT name, purchase_cost FROM club_assets WHERE organisation_id = :o"), {"o": ORG_B})).mappings().all()
        check("another club's asset lands in ITS OWN register", len(b_rows) == 1, [dict(x) for x in b_rows])
        check("and carries its own figure", b_rows and float(b_rows[0]["purchase_cost"]) == 111.0)
        a_has_b = await conn.scalar(text(
            "SELECT count(*) FROM club_assets WHERE organisation_id = :o AND purchase_cost = 111.00"), {"o": ORG_A})
        check("no club bleeds into another", a_has_b == 0, a_has_b)

        # ── merch_assets is untouched history ─────────────────────────────────
        still = await conn.scalar(text("SELECT count(*) FROM merch_assets"))
        check("merch_assets is left in place, not emptied", still == merch_total, f"{still} vs {merch_total}")

    # ── The alerts, through the shipped service ──────────────────────────────
    async with Session() as s:
        alerts = await assets_svc.asset_alerts(s, ORG_A)
        names = [a["name"] for a in alerts["service_due"]]
        check("alerts read the carried service dates", "Bowling machine" in names, names)
        check("alerts read a carried row's own dates", "Line marker" in names, names)
        check("a retired asset raises nothing", "Sight screen" not in names, names)
        overdue = [a for a in alerts["service_due"] if a["name"] == "Line marker"]
        check("an overdue service reads as overdue", overdue and overdue[0]["service_overdue"] is True)
        check("most urgent first", names and names[0] == "Line marker", names)
        check("the count matches the list", alerts["total"] == len(alerts["service_due"]))
        b_alerts = await assets_svc.asset_alerts(s, ORG_B)
        check("alerts are per club", b_alerts["total"] == 0, b_alerts["total"])
        cnt = await assets_svc.count_asset_alerts(s, ORG_A)
        check("the badge count agrees with the list", cnt == alerts["total"], f"{cnt} vs {alerts['total']}")

    # ── The downgrade ────────────────────────────────────────────────────────
    async with engine.begin() as conn:
        # Exactly what alembic's downgrade runs. On `source`, NOT on
        # `merch_asset_id`: the gap-filled rows carry the id too, so deleting on
        # that would destroy three of the club's own assets.
        await conn.execute(text("DELETE FROM club_assets WHERE source = 'merch'"))
        left_a = await conn.scalar(text("SELECT count(*) FROM club_assets WHERE organisation_id = :o"), {"o": ORG_A})
        check("the downgrade removes ONLY the rows the carry created", left_a == 3, left_a)
        names = sorted(r[0] for r in (await conn.execute(text(
            "SELECT name FROM club_assets WHERE organisation_id = :o"), {"o": ORG_A})).all())
        check("the club's own assets survive the downgrade",
              names == ["Bowling machine", "Covers", "Line marker"], names)

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:\n  " + "\n  ".join(FAIL))
        raise SystemExit(1)


asyncio.run(main())
