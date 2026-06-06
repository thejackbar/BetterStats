# BetterImport — overlap-safe historical CSV import

**Status:** data layer + reconciler shipped (P0 + P1). Import endpoints (P2) and
the upload wizard (P3) to follow.
**Branch:** `claude/jolly-cori-mpdav`

## The problem

Clubs onboard with a mix of: (a) incomplete data reachable through the
Cricket Australia *Grassroots* (GR) API, and (b) their own full history kept in
spreadsheets — almost always **summary** statistics, not per-game scorecards.
The onboarding flow we want is: pull GR first, then let the club upload its sheet
in any format, smart-match the columns, and reconcile — **without double-counting
games already covered by GR**, and without asking the club to strip its data.

The canonical example is Wayne Giles (Murdoch University Melville). GR exposes him
as **two** participant profiles (2 games + 223 games) that we merge to **225**.
His club's authoritative record is **473** games. Naively adding the uploaded 473
to GR's 225 gives **698** — the failure this design exists to prevent.

The club's own site already shows the right shape: a per-season table back to
2002/03 (the GR-covered era) plus a single **"Prior Seasons & Adjustments" = 248**
line. And `248 + 225 = 473`. That "Prior" line *is* the residual — the part of the
career GR doesn't hold.

## The guarantee

> The import never stores a club's raw total additively. It stores the club's
> figures as **authoritative truth**, and a reconciler derives only the **non-GR
> remainder**: `max(0, club_total − GR)`. Because that's the only thing ever added
> to GR, the career sum is pinned to the club's stated total and cannot exceed it.

The reconciler re-runs as the final pass of every org sync, so the residual
auto-shrinks as GR coverage grows — no re-import needed, no stale deltas.

## Reconciliation rule (chosen: "GR wins, residual catches gaps")

Per player:

1. **Season precedence.** For each season the club gives: if GR already holds that
   `(player, season)`, the imported season is dropped — GR's richer per-game detail
   wins. Otherwise it's emitted as a season delta.
2. **Career residual.** One catch-all per player =
   `max(0, club_total − GR − emitted_season_deltas)`, carrying the club's career
   high score / best bowling so the view's `MAX()` surfaces them.

Consequences (verified — see *Verification* below):

- **Career total** always equals the club's authoritative figure.
- A season GR covers **incompletely** (11 of 13 games) shows GR's 11 on the
  season row; the missing 2 land in the career residual, so the career stays
  correct. (The escape hatch for a club that disputes this is a per-club "CSV
  authoritative for covered seasons" toggle — not built; easy to add later.)
- If GR found **more** than the club's book (480 > 473), the residual clamps to 0
  and we show GR's 480. The discrepancy is surfaced at import, never silently
  summed.

## Architecture (Strategy "A2": store truth, regenerate derived deltas on sync)

Two new persisted layers + one **additive** view branch. The existing precedence
view (`v_effective_player_season_stats`, migration 060) is **not** rewritten.

| Table | Role |
|---|---|
| `import_batches` | One upload (draft → committed → undone); audit + saved column-mapping template. |
| `imported_stats` | Immutable record of what the club uploaded, with provenance. Source of truth, re-import, undo. Columns mirror `manual_career_adjustments`; `provided_*` holds the derived figures (avg/SR/econ) the club literally gave. |
| `import_effective_deltas` | **Derived**, fully regenerable by the reconciler. Read by the view's new `'import'` branch. Wiped + rebuilt per org on every reconcile, so it never goes stale and never touches the hand-entered `manual_*` tables. |

`import_effective_deltas` is empty for every club until they import, so the new
view branch contributes nothing and **single-club orgs read byte-for-byte
unchanged** — same read-time, non-destructive philosophy as migration 060.

### Why not the alternatives

- **A1 (reuse `manual_*_adjustments` with an origin flag):** tangles import-derived
  rows with the hand-entered manual-adjustments feature; the reconciler couldn't
  safely truncate-and-rebuild.
- **B (rewrite the view to do precedence + a career residual at read time):**
  rewrites the hottest read path in the app (career / season / records / IQ /
  milestones all read this view) and needs a self-referential residual subquery.
  An additive `UNION ALL` branch is far lower-risk.

## Key files

- `backend/alembic/versions/070_betterimport_historical.py` — the three tables +
  the 5th view branch (and a 4-branch downgrade copy).
- `backend/app/models/db.py` — `ImportBatch`, `ImportedStat`, `ImportEffectiveDelta`.
- `backend/app/services/import_reconcile.py` — the reconciler. A **pure, DB-free**
  arithmetic core (`reconcile_player`, `resolve_club_totals`, `accumulate`,
  `balls_to_overs`) plus the DB orchestrator `reconcile_imported_totals(org_id)`.
- `backend/app/services/sync.py` — calls `reconcile_imported_totals` as the final
  pass of `sync_organisation` (next to `_backfill_missing_season_stats`).
- `backend/scripts/verify_import_reconcile.py` — headless proof of the guarantee.

## The eight settled decisions

1. **Storage:** A2 (above).
2. **Placement / gating:** a **core onboarding tool, free to all clubs** — not a
   paid module. It's a conversion driver; gating it would fight adoption. (P2/P3:
   a dedicated wizard page under "Cricket Data", capability-gated, reusing the
   manual-entries audit/undo plumbing.)
3. **Derived vs raw stats:** clubs give Avg/SR/Econ/HS; the importer reconstructs
   raw components (`outs = round(runs/avg)`, `not_outs = innings − outs`,
   `runs_conceded = round(wickets × bowl_avg)`, …), prefers raw columns when
   present, and surfaces ±1 rounding in the review screen. `imported_stats` keeps
   both the reconstructed components and the `provided_*` originals. **(P2.)**
4. **"Prior" bucket:** both — map an explicit pre-GR/adjustments row
   (`is_prior_bucket`) *and* compute the residual from a career total; reconcile to
   the larger when both are present.
5. **Grade granularity:** display label only in v1 (`grade_label`); reconcile at
   `(player, season)`.
6. **Pre-GR seasons given individually:** preserve as real `seasons` + manual
   season rows (not flattened); the residual catches only the true remainder.
   **(P2 — the reconciler already emits per-season deltas for GR-missing seasons.)**
7. **File formats:** CSV + XLSX (`openpyxl`). **(P2.)**
8. **Player matching (the real double-count vector):** auto-accept exact
   normalised-name (`admin._normalise`) and GR-id matches only; fuzzy needs
   confirmation; never silent-create; detect a name matching two GR records and
   prompt "merge first". Targets the **post-merge** player set. **(P2/P3.)**

## Build phases

- **P0 (done):** migration 070 + models + this doc.
- **P1 (done):** reconcile engine + sync hook + headless verifier.
- **P2:** import endpoints (`preview` / `mapping` / `player-matches` /
  `season-matches` / `commit` / `undo` / `template`), the derived→raw inversion,
  the column/player/season matching services, and writing `imported_stats` +
  calling the reconciler on commit.
- **P3:** the upload wizard UI (Upload → Map columns → Match players → Match
  seasons → Review & reconcile → Commit), provenance badges.
- **P4:** changelog entry + final polish. (Deferred until the UI ships — no point
  announcing a feature clubs can't yet use.)

## Verification

`python scripts/verify_import_reconcile.py` exercises the pure core over six
scenarios and asserts that the effective career total (GR + emitted season deltas
+ residual) always equals the club's authoritative figure — never the naive sum:

| Scenario | club | GR | result |
|---|---|---|---|
| A — Wayne, career-only upload | 473 | 225 | **473** (residual 248), not 698 |
| B — season rows overlap GR + explicit Prior bucket | 270 | 22 | 270 (residual reproduces the 248 lump) |
| C — GR-incomplete season (11 of 13) | 13 | 11 | career 13, season row stays 11, +2 in residual |
| D — GR exceeds club (found more) | 473 | 480 | **480** (residual 0), not 953 |
| E — player left before GR (no GR) | 27 | 0 | 27, all as season deltas |
| F — GR grows 225→230 after import | 473 | 230 | still **473**, residual self-shrinks 248→243 |

**Before production:** run a real reconcile on a **data copy** and confirm a normal
single-club org's career numbers are byte-for-byte unchanged (no `imported_stats`
⇒ empty delta branch ⇒ identical reads), per the standing CLAUDE.md rule.
