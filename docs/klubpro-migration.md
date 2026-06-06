# KlubPro → BetterStats migration tooling

A super-admin-only onboarding wizard, integrated into the admin app, that reviews
data already staged in the **KlubPro** Postgres database and imports two things
into BetterStats:

1. **Player profiles** — gender, email, phone, role, batting hand, bowling type,
   opening-batter flag, skills, and profile photo — matched to existing
   BetterStats players **by name** (KlubPro has no PlayHQ/CA ids).
2. **Sponsors** — name, contact, email, logo, display order.

It never touches stats, games, appearances, scores, player ids, or
`organisation_id`. Every write is preceded by a row-level backup and is
reversible from the **History** tab.

Live at **Admin → (Super Admin) → KlubPro Migration** → `/admin/super/migration`.

## Why integrated (not a standalone app)

The migration writes *into* BetterStats players/sponsors, so reusing the app's
auth, capability model, UI components and API client is far less code than a
separate service. The trade-off — the production backend now needs network
access to the KlubPro database — is contained: the second engine is **lazy** and
only ever instantiated when an operator hits a migration endpoint with
`KLUBPRO_DATABASE_URL` set. With it unset (every normal deploy), the page shows
"not configured" and nothing connects.

## Two databases

| Role | Connection | Access |
|---|---|---|
| BetterStats | the app's normal `get_db` | read + write (players, org_sponsors, audit/backup tables) |
| KlubPro | `app/services/klubpro_db.py` → `get_klubpro_db` (lazy engine from `KLUBPRO_DATABASE_URL`) | read staged data + write operator decisions to `klubpro_migration.player_match_mappings` |

KlubPro is **not** ORM-mapped — it's an external system touched only through
schema-qualified raw SQL, so it never participates in our Alembic migrations.

### Source tables (KlubPro `klubpro_migration` schema)

- `onboarding_staging_summary` (view) — the dashboard.
- `club_mappings` — links a staged KlubPro club to a BetterStats `organisation_id`. The wizard works one mapped club at a time.
- `player_migration_candidates` (view) — staged player data **with the BetterStats target fields already derived** (`betterstats_player_role`, `betterstats_batting_hand`, `betterstats_bowling_type`, `betterstats_skill_positions`, `betterstats_is_opening_batsman`) + `profile_image_data`/`thumbnail_image_data` bytea. We trust these derived columns — the KlubPro skill-code → BetterStats mapping (BAT/BWL/ALL/WKT/RHB/LHB/…) happens upstream in staging.
- `player_match_mappings` — operator decisions (approve/reject/skip), keyed `(club_mapping_id, betterstats_player_id)`. Generated candidates already exist here at a 0.95 threshold.
- `sponsor_migration_candidates` (view) — staged sponsors + `logo_data` bytea.

> **`sponsor_import_selections` is intentionally not used as the source of truth.**
> Its column shape wasn't documented in the handoff, so rather than guess, sponsor
> selection is held client-side and the import is made **dedup-safe on the
> BetterStats side** by the partial-unique index `(organisation_id,
> klubpro_sponsor_id)`. Re-running an import never double-inserts.

## BetterStats schema additions (migration 072)

The handoff's sponsor insert targets three columns the repo's `org_sponsors`
didn't have — added here (idempotent, also mirrored in `main.py` lifespan):

- `org_sponsors.contact_name`, `.email`, `.klubpro_sponsor_id` + the partial-unique
  index above.

Plus two bookkeeping tables (in **BetterStats**, so backups/audit survive even if
KlubPro is later decommissioned and rollback is a pure BetterStats operation):

- `klubpro_migration_batches` — one executed import (the unit of rollback): kind,
  org, club mapping, counts, operator, status (`imported` → `rolled_back`).
- `klubpro_migration_backups` — per-row before/after image. A player `update`
  stores the old field values (incl. the old photo as base64) to restore on undo;
  a sponsor `insert` stores just the new id so undo deletes it.

## Field-level approval

Approving a match approves the **relationship** between a BetterStats player and a
KlubPro player — it does **not** force every field across. Each match shows the 9
migratable fields side by side (BetterStats current vs KlubPro staged) with a
checkbox each; only ticked fields migrate.

- **Migratable fields** (the `migrate_fields` keys, = backend `MIGRATABLE_FIELDS`):
  `gender, email, phone, player_role, batting_hand, bowling_type,
  is_opening_batsman, skill_positions, profile_image`. First/last/nickname are
  **not** migratable — BetterStats has a single `name` field, so they're shown for
  context only and never written.
- **Smart defaults** (`recommended_fields`): every field KlubPro has a value for is
  pre-ticked, including `profile_image` whenever KlubPro has an image (untick it to
  keep a newer BetterStats photo); a KlubPro empty/missing value is unticked and can
  never blank a BetterStats value.
- **Collapsed card** keeps the rich side-by-side summary (both images + name, score,
  gender/role/hands/bowling/opener/contact/skills) so the operator can compare
  without opening Fields; "Fields" toggles the detailed checkbox panel.
- **Per-row actions**: Approve / Re-approve · Reject · Skip · Change (pick a
  different KlubPro player) · Check all · Uncheck all · Reset to recommended.
  Reject/skip **update the mapping in place** (the match is marked
  rejected/skipped, excluded from import); `match_status` is stored past-tense
  (`approved`/`rejected`/`skipped`). Approving a KP player **frees it from any
  other BetterStats player** in the club first (the KP table has a unique on the KP
  id), so a wrong match you rejected on player A can be approved on player B —
  `ensure_match_columns` drops the NOT NULL on `klubpro_player_id` so the freed
  row keeps its rejected status with a null id.
- **Name search** is double-space / suffix / order tolerant (`normName` +
  token-AND): an empty middle-name slot ("First  Last") and Jnr/Snr suffixes no
  longer stop a candidate being found.
- **Approve ≠ import.** Approving (or Bulk Approve) only records the decision +
  field selections. **Import** is the step that writes BetterStats `players`. Cards
  show `APPROVED · NOT IMPORTED` (blue) until imported, then `IMPORTED ✓` (green);
  the header shows approved / imported / pending counts and Import is enabled on the
  approved-but-not-yet-imported count.
- **Persistence** (`klubpro_migration.player_match_mappings`, columns added at
  runtime via `ensure_match_columns` since KlubPro is external): `migrate_fields
  jsonb`, `reviewed_at/by`, `imported_at/by`. The single approve
  (`POST .../players/match` with `migrate_fields`) and **Bulk Approve**
  (`POST .../players/bulk-approve` `{items:[{betterstats_player_id,
  klubpro_player_id, migrate_fields}]}`, item-level results, per-item commit so one
  failure can't poison the batch) both store the selections.
- **Import & dry-run** read the stored `migrate_fields` (`plan_player`): a field is
  written only when selected, non-empty, and actually different; `profile_image`
  overwrites an existing photo only when explicitly ticked. The import stamps
  `imported_at/by` and records per-player applied/skipped fields in the backup
  row's `after_data` (audit). The dry-run reflects the **saved** approvals, so
  approve (or bulk-approve) first, then dry-run, then import.
- **Filters**: all · unreviewed · reviewed · approved · rejected · skipped · image
  replacement selected/deselected · has field differences · has missing KlubPro
  values.

## Value normalisation (labels → codes)

KlubPro stages `betterstats_*` as **human labels**; BetterStats stores **codes**.
The import normalises on write (`_incoming_map` + `_norm_*`, mirroring
`frontend/src/lib/playerAttributes.js`):

| Field | KlubPro staged | BetterStats stored |
|---|---|---|
| batting_hand | "Right handed" | `RIGHT` |
| bowling | "Right-arm fast-medium" | `bowling_action='RIGHT_ARM'` + `bowling_type='FAST_MEDIUM'` (the checkbox sets both) |
| gender | "Male" | `male` |
| player_role | "All Rounder" | `All Rounder` (BetterStats stores the label — always worked) |

An unrecognised value normalises to None → treated as empty (never written, never
blanks an existing value). The wizard displays codes back as labels and compares
normalised, so `RIGHT` vs "Right handed" isn't shown as a difference.

**Photo:** a normal upload sets `photo_url = /api/images/players/{id}/photo?v=…`
and BetterSelect's avatar renders from `photo_url`; the import sets it too (not
just `photo_data`/`photo_mime`), so the photo shows in the admin editor as well as
the public profile. `_player_before`/rollback carry `bowling_action` + `photo_url`.

> **Clubs imported before this fix** stored the raw labels (the admin dropdowns
> showed "—" and the admin avatar was blank). Just **re-Import** the club — the
> normalised value differs from the stored label, so the re-run repairs every row.

## Safety invariants (enforced in `services/klubpro_migration.py`)

- **Never clobbers with empties.** A field is only written when its checkbox is
  ticked AND the KlubPro value is non-empty — an empty KlubPro value can never blank
  an existing BetterStats value, regardless of the checkbox. (Verified.)
- **Profile image** defaults to ticked whenever KlubPro has an image and overwrites
  the BetterStats photo when applied; the operator unticks it to keep a newer
  BetterStats photo. The old photo is captured in the backup so a rollback restores
  it.
- **`is_opening_batsman = False` is "no info"**, not a value to write (the staged
  view returns False rather than NULL). Only `True` is applied.
- **Skills compare as a set** — same skills in a different order is not a change,
  so dry-run and import agree.
- **Stats are out of scope.** Only the ten profile fields are ever written.
- **No duplicate sponsors.** Guarded by `(organisation_id, klubpro_sponsor_id)`.
- **No deleted KlubPro players.** The candidate view is the staged set.
- **Dry-run → confirm → backup → write.** The import endpoint requires
  `confirm: true`; the UI only enables Import after a dry-run; each row is backed
  up in the same transaction as its write.

## Mapping clubs (editable, from the dashboard)

The dashboard's **Mapped to** column is a dropdown of every BetterStats
organisation (`GET /club-admin/klubpro/organisations`). Pick one for any staged
club → confirm `Map KlubPro club <name> to BetterStats organisation <org>?` →
`PATCH /club-admin/klubpro/club-mapping` `{klubpro_club_id,
betterstats_organisation_id, force}`:

- Validates the org (BetterStats) and the target club (KlubPro
  `onboarding_targets`), then **UPDATE-or-INSERT** into `club_mappings` (never
  DELETE, so the row id and any `player_match_mappings` FK survive) with
  `migration_status='mapped'`, and bumps the onboarding target's `stage_status`
  to `mapped` (keeping `validated`). Repeatable / update-safe — no manual SQL,
  works for clubs added to BetterStats later.
- If the chosen org is already mapped to a **different** KlubPro club, the
  endpoint returns `{status:'conflict', message}` (HTTP 200) instead of writing;
  the UI shows the warning and only proceeds with `force:true` on confirm.
- On success the dashboard + the top **Mapped club** selector both refresh (the
  selector reads `club_mappings`, so a newly mapped club appears immediately).
- Candidate matching is **not** auto-generated on map — newly mapped clubs start
  with an empty `player_match_mappings`; match them in the **Players** tab
  (suggested rows appear for clubs that already have generated candidates).

## Operator flow

1. Pick a **mapped club** in the selector (only `club_mappings` rows with a
   BetterStats org are listed).
2. **Players** tab: review each BetterStats player (left) against its suggested
   KlubPro candidate (right). Approve / Reject / Skip, or **Change** to search and
   pick a different KlubPro player. Decisions persist to `player_match_mappings`.
3. **Dry run** → see exactly which fields change per player (old → new), with
   empties skipped. Then **Import** → backs up + writes; toast reports counts.
4. **Sponsors** tab: tick the sponsors to bring across (already-imported ones are
   marked and locked), **Dry run**, **Import**.
5. **History** tab: every import with one-click **Roll back** (restores updated
   players / deletes inserted sponsors, marks the batch `rolled_back`).

## Deployment (on the box)

1. Set `KLUBPRO_DATABASE_URL` in the BetterStats backend env (the central
   `/srv/docker/docker-compose.yaml` for `betterstats-backend`), e.g.
   `postgresql+asyncpg://klubpro_admin:<pw>@klubpro-postgres:5432/klubpro`.
   **Never commit the password** — use the `.env` / Docker secret.
2. Ensure `betterstats-backend` and `klubpro-postgres` **share a Docker network**
   so `klubpro-postgres` resolves (both run in the `bltbox_docker_app` project; add
   the shared network to the backend service if it isn't already).
3. Run migration `072` (or rely on the idempotent lifespan creates) and redeploy
   via `deploy.sh`.
4. The **KlubPro Migration** link appears in the Super Admin sidebar. If the env
   var is unset the page explains it's not configured and nothing connects.

## Endpoints (`/club-admin/klubpro/*`, all `require_super_admin`)

`GET status` · `GET dashboard` · `GET clubs/{cm}/players` ·
`POST clubs/{cm}/players/match` · `GET clubs/{cm}/players/dry-run` ·
`POST clubs/{cm}/players/import` · `GET clubs/{cm}/sponsors` ·
`POST clubs/{cm}/sponsors/dry-run` · `POST clubs/{cm}/sponsors/import` ·
`GET images/player/{id}` · `GET images/sponsor/{id}` (bytea → `<img>`, cookie
auth) · `GET batches` · `POST batches/{id}/rollback`.
