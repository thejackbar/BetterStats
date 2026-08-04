# Unified Roles Model — BetterStats (Core) + BetterClubManager

**Status:** proposed plan (Option A — unify now). **Goal:** one shared data
structure for Roles, Role Types and Role Holdings, used by both modules, so a
BetterStats-only club that later subscribes to BetterClubManager adopts the
richer role model with **no club-facing migration**. BetterStats uses the
structure simply; BetterClubManager layers richer attributes and workflow on the
same rows.

Retire "Office Bearer" as an *award* category and re-home it as *role holdings*.
Awards stay for genuine awards (Best Batsman, Club Champion); roles-held are
appointments, a different concept.

---

## 1. Current state (two representations of the same idea)

**BetterStats honour board** — `player_achievements`
`(org_id, player_id [nullable], player_name, season, category, subcategory,
achievement, detail)`. Office bearers are `category='Office Bearer'`,
`subcategory ∈ {Executive Committee, General Committee, Captains, Coaches, Other
Roles}`, `achievement=<role name>` (President, 1st XI Captain…). So a record is
already *"a person held a named, classified role in a season"* — stored flat as
text.

**BetterClubManager** — `club_roles` (title, `role_type_id`, `is_committee`),
`club_role_types` (name, `category`), `committee_positions` (synced from
committee-flagged roles), `committee_terms` (a `fee_member` holds a position for
a term), `volunteer_roles` (member↔role).

Same concept ("a role held for a period"), two schemas. Unifying them is the job.

---

## 2. Target: three shared **Core** tables

All Core (populated/readable with or without a BetterClubManager subscription —
`roles_activities` is already "core, not a paid module").

1. **Role Types** — `club_role_types` (exists). Add **`classification`** (the one
   shared attribute). BetterClubManager-only richer attributes are extra columns
   BetterStats ignores.
2. **Roles** — `club_roles` (exists). President, Turf Curator, WASTCA Delegate,
   each under a type.
3. **Role Holdings** — **new** `role_holdings`: *(person, role, term)*. The
   unifier. Replaces both `player_achievements` office-bearer rows and
   `committee_terms`.

### `role_holdings` (new, Core)

| column | notes |
|---|---|
| `id` | uuid pk |
| `organisation_id` | FK organisations |
| `role_id` | FK `club_roles`, **nullable** (legacy rows may only have a name) |
| `role_name` | text fallback when `role_id` is null (unmapped legacy import) |
| `member_id` | FK `fee_members`, **nullable** (the person spine; players + non-players) |
| `holder_name` | text fallback when unmatched to a member |
| `season_year` | int, nullable — BetterStats honour-board granularity |
| `start_date` / `end_date` | date, nullable — BetterClubManager term granularity; `end_date IS NULL` = current |
| `source` | `manual` \| `derived` \| `imported` \| `legacy_award` |
| `notes` | text |
| `created_at` | ts |

`member_id` reuses the shared person spine (`fee_members`, `player_id` already
nullable), so a non-player office bearer already works, and
`members.ensure_for_player` links a synced player on demand.

### Attribute split (avoids conflating two axes)

- **`classification`** (role's nature): `governance | operational | playing |
  representative | honorary | official`. This is the primary axis and supersedes
  the interim `category` on `club_role_types`.
- Governance sub-tier stays at the **role-type** level, reusing what exists:
  type "Office Bearer" (governance, executive) vs "Committee Member" (governance,
  general). No new column needed for the tier.
- **Engagement basis** (`volunteer | paid`) is a *separate, optional* attribute,
  not a classification value — **deferred** until a club needs it.
- BetterClubManager-only extras (voting rights, committee membership, appointment
  method, constitutional flag) are additional columns added when their UI is
  built; BetterStats never reads them.

---

## 3. Classification mapping (drives the one-time backfill)

BetterStats `player_achievements` → holdings:

| Office-Bearer subcategory | classification | role-type on backfill |
|---|---|---|
| Executive Committee | governance | Office Bearer |
| General Committee | governance | Committee Member |
| Captains | **playing** — a MANUAL season appointment (see §5) | Captain (team encoded in the name, e.g. "1st XI Captain") |
| Coaches | operational | Coach |
| Other Roles | operational / other | (match by name, else Other) |

Interim `club_role_types.category` → `classification`:
`committee→governance`, `official→official`, `volunteer/paid→operational`,
`third_party→representative`, `other→other`. (`volunteer/paid` fold to
operational; the engagement basis is captured separately later.)

---

## 4. Phases

**Phase 0 — schema (additive, non-breaking).**
- Add `club_role_types.classification`; backfill from `category` per the map
  above (keep `category` for one release, then drop).
- Create `role_holdings` (Core; ORM model + lifespan mirror + Alembic).
- No behaviour change yet.

**Phase 1 — BetterStats reads a union (nothing breaks).**
- A view `v_role_holdings_effective` = structured `role_holdings` **UNION**
  legacy `player_achievements` office-bearer rows (projected into the holdings
  shape). The honour board reads the view, so day-one output is identical.

**Phase 2 — one-time internal backfill (invisible to clubs).**
- Copy every `player_achievements` `category='Office Bearer'` row into
  `role_holdings`: resolve/create the `club_role` by name under the mapped type,
  link the holder to a `fee_member` (`ensure_for_player` when `player_id` set,
  else `holder_name`), set `season_year`, `source='legacy_award'`.
- Idempotent (dedupe on org+role+holder+season), re-runnable, logged. This is the
  only migration and it is engineering-side, not a task the club performs.

**Phase 3 — switch BetterStats writes; retire the award category.**
- BetterStats' office-bearer editor writes to `role_holdings` (Core), not
  `player_achievements`. The honour board reads structured holdings directly
  (view can drop the legacy branch once backfill is verified).
- `player_achievements` keeps only genuine awards; "Office Bearer" is removed
  from the award category list and its starter-template rows.

**Phase 4 — BetterClubManager committee terms become holdings.**
- `committee_terms` is migrated into `role_holdings` (governance-classified
  holdings). `committee_positions` stays as the governance-role anchor for
  tasks/docs/AGM (still synced from governance roles). The committee screen reads
  holdings filtered to `classification='governance'`; assigning a position writes
  a holding.
- Directory/committee assignment (built this session) repoints to holdings.

**Phase 5 — surface per-match captaincy alongside the manual season-captain holding.**
- Season/team captains are **manual** holdings (§5), assigned pre-season and
  editable — not derived, because the appointment exists before any match lineup
  is posted. Per-match captaincy already lives in the data
  (`game_appearances.is_captain`, sourced from PlayHQ); surface it next to the
  season holding as read-only match fact. Derived per-match data **never
  overwrites** the manual season appointment.

---

## 5. Captain / playing roles (manual appointment + separate per-match fact)

Two distinct things, and neither overrides the other:

- **Season/team captain = a MANUAL holding.** Clubs decide captains at the AGM or
  before the season starts — *before* any match lineup exists in PlayHQ — so the
  appointment cannot wait on, or be derived from, match data. It is assigned in
  BetterCricket like any other appointment (`source='manual'`), is editable, and
  can change through the season (re-nomination). Captaincy is team-specific
  (1st XI, 2nd XI, Women's…); pragmatically the team is encoded in the role name
  ("1st XI Captain"), as BetterStats already does, until formal team-scoping (§8).
- **Per-match captain = a DERIVED fact from PlayHQ.** Who actually captained a
  given match already lives in `game_appearances.is_captain`. It is read-only
  match data, surfaced *alongside* the season holding. When a nominated season
  captain misses a match and another player captains that game, **both** are true
  and shown: the manual season appointment (unchanged) and the derived per-match
  captain for that game. The derived record never rewrites the appointment.

So captaincy is not "derived instead of managed" — the season role is managed
(manual holding), and the per-match record is derived context on top.

---

## 6. Why adoption is seamless

A BetterStats-only club already writes its office bearers into the shared
`role_holdings` / `club_roles` / `club_role_types` tables (Phase 3). Subscribing
to BetterClubManager unlocks the richer editing UI and extra attributes **over
data already present** — nothing is copied or re-entered. The lone migration
(Phase 2 backfill of pre-existing award rows) is automatic and one-time.

---

## 7. Risks & mitigations

- **Breaking existing honour boards** → Phase 1 union view keeps output identical
  until the backfill is verified; writes switch only in Phase 3.
- **`committee_terms` in flight** (Directory committee assignment shipped this
  session) → Phase 4 migrates it behind the same service functions; the view
  bridges during the switch.
- **Name→role/member matching in the backfill** → reuse the existing
  `import_ingest.match_players` / `members.ensure_for_player` helpers; unmatched
  rows keep `role_name`/`holder_name` text so nothing is lost.
- **Two ID axes (player vs fee_member)** → holdings key on `fee_member` (spine);
  `ensure_for_player` bridges synced players. Consistent with the Directory work.

---

## 8. Deliberately deferred (avoid over-engineering community cricket)

Reporting line; team-scoping of roles (First XI / Women's / Juniors) as a
person-role-team triple; per-role voting-rights/constitutional workflow. All are
additive columns/tables on the same structure later — none change the shared
spine, so deferring them costs nothing in seamlessness.

**Team-scoping is genuinely needed for captains** (and coaches/managers), but the
interim is pragmatic: encode the team in the role name ("1st XI Captain",
"Women's Coach"), exactly as BetterStats already does on the honour board. When
formal team-scoping lands, a `team_id` on the holding replaces the naming
convention without disturbing the shared structure — and the per-match captain
fact (§5) is already team-aware via the game it belongs to.
