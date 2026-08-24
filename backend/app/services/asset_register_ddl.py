"""ONE asset register: BetterMerch's `merch_assets` carried into `club_assets`.

Per direct instruction: inventory is one thing, and property / facilities /
fixed assets / equipment are another. `merch_assets` was never inventory. Its
own model docstring calls it "an individual high-value piece of equipment
(bowling machine, covers, sight screen) … quantity is implicitly 1; not
stock-counted", which is a fixed-asset register, and `club_assets` is the same
register built again 94 revisions later.

Migration 177 said why it did not reuse what existed: general club property "is
a different concern from BetterMerch's retail/kit stock tracking (merch_assets,
a paid-module table)". That sentence names the wrong table. Retail and kit stock
are `merch_products` / `merch_variants`, which carry quantity, cost, price and
movements; `merch_assets` carries none of those. The duplication came from a
mis-description rather than a decision, which is why it is safe to undo.

`club_assets` is the base rather than `merch_assets`, and not arbitrarily:
`merch_assets` is a strict column SUBSET of it. Every one of its thirteen
columns has a same-named, same-typed, same-defaulted twin in `club_assets`'
sixteen; only `category` and `facility_id` are unique to the club side. Nothing
is given up by carrying one into the other, and the club register additionally
has maintenance history and lives in core rather than behind a paid module.

`merch_assets` IS LEFT IN PLACE AND READ BY NOTHING after this, the call
migration 267 made for `vote_settings` and 278 for `crm_deals.
commission_rate_percent`. A second register that still answered writes could
only drift from the one people are now looking at.

Every statement is idempotent, because the lifespan mirror re-runs the whole
list on every boot. `merch_asset_id` is what makes the carry itself idempotent:
a row already carried is found and skipped rather than inserted twice.
"""
from __future__ import annotations

# The two vocabularies say the same three or four things in different words.
# Mapped rather than added to `ASSET_CONDITIONS` / `ASSET_STATUSES`, so the
# register ends up with ONE vocabulary instead of the union of two.
#
#   condition:  new → excellent, retired → unserviceable, rest identical
#   status:     out_for_repair → in_repair, rest identical
_CONDITION_MAP = """
    CASE lower(coalesce(m.condition, 'good'))
        WHEN 'new'     THEN 'excellent'
        WHEN 'retired' THEN 'unserviceable'
        WHEN 'good'    THEN 'good'
        WHEN 'fair'    THEN 'fair'
        WHEN 'poor'    THEN 'poor'
        ELSE 'good'
    END
"""
_STATUS_MAP = """
    CASE lower(coalesce(m.status, 'in_service'))
        WHEN 'out_for_repair' THEN 'in_repair'
        WHEN 'retired'        THEN 'retired'
        WHEN 'in_service'     THEN 'in_service'
        ELSE 'in_service'
    END
"""

# A merch row and a club row are the same physical object when they share an
# asset tag (a serial number is a real identity) or, failing that, a name. Case
# and surrounding space are folded and NOTHING ELSE — two clubs really can own
# a "Line marker" and a "Line marking machine", and quietly folding those would
# put one object's service history on another.
_MATCH = """
    (
      (
        nullif(btrim(coalesce(c.asset_tag, '')), '') IS NOT NULL
        AND lower(btrim(c.asset_tag)) = lower(btrim(m.asset_tag))
      )
      OR lower(btrim(c.name)) = lower(btrim(m.name))
    )
"""

ASSET_REGISTER_SQL = [
    # ── Where a carried row came from ────────────────────────────────────────
    # Nullable, and NO foreign key on purpose: `merch_assets` is history now,
    # and a club tidying it later must not take the live register's rows with
    # it. The unique index is what makes the backfill re-runnable.
    "ALTER TABLE club_assets ADD COLUMN IF NOT EXISTS merch_asset_id UUID",
    # WHO MADE THE ROW, which is a different question from which merch row it
    # corresponds to, and the downgrade turns on the difference. Both a
    # gap-filled row and an inserted one carry `merch_asset_id`, because both
    # have dealt with that merch row and neither must be processed twice — but
    # only an INSERTED row is this migration's to remove. Deleting on the id
    # alone would take the club's own pre-existing assets with it, which is
    # what the verification caught.
    "ALTER TABLE club_assets ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'club'",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_club_assets_merch_asset
        ON club_assets (merch_asset_id) WHERE merch_asset_id IS NOT NULL
    """,

    # ── Step 1: fill the gaps on an asset the club already holds ─────────────
    # FILLS, NEVER CLOBBERS. Every field is COALESCE(what is here, what is
    # coming), so a figure somebody typed on the club register always wins over
    # the merch copy of the same object. `condition` and `status` are NOT NULL
    # on this side, so they always have a value and are never touched.
    #
    # Notes are the one field where "keep what is here" would lose something
    # real, so a merch note that is not already contained in the club note is
    # appended rather than dropped.
    #
    # DISTINCT ON picks one merch row per club row: where two merch rows match
    # the same club asset, the second stays uncarried and step 2 gives it its
    # own row rather than silently merging two objects.
    f"""
    UPDATE club_assets AS tgt SET
        asset_tag         = coalesce(tgt.asset_tag, pick.asset_tag),
        purchase_cost     = coalesce(tgt.purchase_cost, pick.purchase_cost),
        purchase_date     = coalesce(tgt.purchase_date, pick.purchase_date),
        service_due_date  = coalesce(tgt.service_due_date, pick.service_due_date),
        replace_due_date  = coalesce(tgt.replace_due_date, pick.replace_due_date),
        notes             = CASE
                              WHEN tgt.notes IS NULL OR btrim(tgt.notes) = '' THEN pick.notes
                              WHEN pick.notes IS NULL OR btrim(pick.notes) = '' THEN tgt.notes
                              WHEN position(btrim(pick.notes) in tgt.notes) > 0 THEN tgt.notes
                              ELSE tgt.notes || chr(10) || btrim(pick.notes)
                            END,
        merch_asset_id    = pick.merch_asset_id,
        -- `source` deliberately NOT set: this row is the club's own, it has
        -- merely had its blanks filled in.
        updated_at        = now()
    FROM (
        SELECT DISTINCT ON (c.id)
               c.id AS club_asset_id, m.id AS merch_asset_id,
               m.asset_tag, m.purchase_cost, m.purchase_date,
               m.service_due_date, m.replace_due_date, m.notes
          FROM merch_assets m
          JOIN club_assets c
            ON c.organisation_id = m.organisation_id
           AND c.merch_asset_id IS NULL
           AND {_MATCH}
         WHERE NOT EXISTS (
                   SELECT 1 FROM club_assets x WHERE x.merch_asset_id = m.id
               )
         ORDER BY c.id, m.created_at
    ) AS pick
    WHERE tgt.id = pick.club_asset_id
    """,

    # ── Step 2: carry the rest across as their own rows ──────────────────────
    # `gen_random_uuid()` is supplied EXPLICITLY rather than relied on as a
    # server default: `create_all` builds this table without one, so a bare
    # INSERT has no id and fails outright on a fresh database (the trap the
    # self-serve-trial and sales-commission notes already document).
    #
    # `category` is stamped 'equipment' because that is what the merch table
    # held by its own definition, and it is a real `ASSET_CATEGORIES` value.
    # `facility_id` stays NULL: nothing in the merch row says where the thing
    # lives, and guessing a location is worse than leaving it to be set.
    f"""
    INSERT INTO club_assets (
        id, organisation_id, name, category, asset_tag, purchase_cost, purchase_date,
        condition, status, service_due_date, replace_due_date, facility_id, notes,
        is_active, created_at, updated_at, merch_asset_id, source
    )
    SELECT gen_random_uuid(), m.organisation_id, m.name, 'equipment', m.asset_tag,
           m.purchase_cost, m.purchase_date,
           {_CONDITION_MAP}, {_STATUS_MAP},
           m.service_due_date, m.replace_due_date, NULL, m.notes,
           m.is_active, m.created_at, now(), m.id, 'merch'
      FROM merch_assets m
     WHERE NOT EXISTS (
               SELECT 1 FROM club_assets x WHERE x.merch_asset_id = m.id
           )
    """,
]
