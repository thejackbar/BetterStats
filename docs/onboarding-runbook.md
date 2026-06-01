# Manual Club Onboarding Runbook

How to bring a new cricket club onto the Better platform by hand. This is the
**manual** process used while club numbers are small (self-serve signup is a
later phase — see the Ecosystem Master Plan). Everything here is done from the
**super-admin console** (`/admin/super/clubs`) by a user with the `super_admin`
role.

> **Billing is manual too.** Setting a club's tier here grants entitlement in
> the app; collecting the money (invoice / bank transfer) is a separate,
> off-platform step. See `docs/invoicing-runbook.md`.

---

## Prerequisites

- A `super_admin` account (the operator — you).
- The club's name as it appears in Cricket Australia / PlayHQ search.
- The tier the club has agreed to (Good / Better / Best).
- A contact email and a desired URL slug (e.g. `applecross` → `betterstats.cricket/applecross`).

---

## Steps

### 1. Create the club

1. Go to **Admin → Super Admin → All Clubs** (`/admin/super/clubs`).
2. Click **+ NEW CLUB**.
3. In **Search Cricket Australia**, type the club name and pick the match.
   - This is required: the selected club's **Cricket Australia GUID becomes the
     org id**, which is the sync key. A hand-typed name won't sync.
4. Confirm the **Club name**, **Slug**, **Short name** and **Contact email**.
5. Click **CREATE CLUB**.

The club is created **inactive** and on the **Good** tier (Core only) by default.

### 2. Set the tier

1. Click **Edit** on the new club row.
2. Set **Tier (plan)** to the agreed tier:
   - **Good** — Core (BetterStats) only.
   - **Better** — + BetterSelect + BetterSocials.
   - **Best** — everything (+ BetterFees + BetterIQ).
3. **SAVE CHANGES.**

The tier pill on the club row updates immediately. Entitlement is enforced on
both the backend (`require_module`, returns 402 when not entitled) and the
frontend (locked module tiles + route guards). À-la-carte module overrides
(`module_overrides`) can be set via the API if a club wants a single module
above its tier; there's no UI for that yet.

### 3. Kick the first data sync

1. Click **Sync** on the club row (calls `POST /organisations/{id}/sync`).
2. This is the heavy initial pull — **it can take an hour or more** for a club
   with decades of history. It runs in the background.

> **Scaling note:** one club's full sync is heavy on the Cricket Australia
> proxy. Don't kick several brand-new clubs' syncs simultaneously — stagger
> them. (A proper sync queue is a tracked follow-up.)

### 4. Verify the data reconciled

Spot-check before handing over:
- A few well-known players show sensible career batting/bowling/fielding totals.
- Historical games have `home_team` / `away_team` populated.
- Season list looks complete (no missing recent seasons).

If a player shows 0s despite having scorecards, use **Fix Missing Totals**
(backfill aggregates) from that club's `/admin/sync` page. See `CLAUDE.md` →
*Sync Architecture* for the full troubleshooting model.

### 5. Invite the club admin

1. Go to **Admin → Super Admin → Users** (`/admin/super/users`).
2. Create a user: set **username**, a temporary **password** (≥ 10 chars),
   **display name**, the **club**, and role **club_admin**.
3. Send the club their username + temporary password out-of-band; they change
   it on first login.

### 6. Activate the club

1. Back on **All Clubs**, toggle the club to **Active**.
   - Inactive clubs can't log in (non-super users are blocked at `/auth/login`)
     and the public page shows the inactive state.
2. Confirm the public page loads at `betterstats.cricket/{slug}`.

Done. The club admin can now log in and will land on the module-tile dashboard
showing exactly what their tier unlocks.

---

## Per-club auth scoping (confirmed)

The platform is **organisation-scoped by construction** — verified as part of
the multi-club readiness work:

- Each admin user has exactly **one** `ClubMembership` (DB unique constraint
  `uq_membership_one_per_user`), carrying their `role` and `capabilities`.
- `get_current_club` resolves the caller's club from that membership; every
  club-admin route filters its queries by `club.id`. A club admin therefore
  **cannot see or touch another club's data** — there is no code path that
  takes a club id from the request for club-admin routes.
- **Super admins** (`require_super_admin`) act cross-club by design: they
  bypass `require_module`, and the `/super/*` endpoints operate on any club id.
- Public pages resolve the club from the URL **slug** (`/{clubSlug}`), read-only.

If you ever add a club-admin route, scope it the same way: take
`club: Organisation = Depends(get_current_club)` and filter on `club.id` —
never accept an org/club id from the request body or path on a club-admin route.

---

## Gotchas

- **Org id must be the CA GUID.** Creating a club from anything other than the
  search picker breaks sync. The console enforces this.
- **Existing/pilot clubs default to Best.** Migration 056 backfilled all
  pre-existing clubs to `best` so the live pilot kept the modules it was already
  using. New clubs start at `good`.
- **Award definitions for Applecross are seeded at startup** (a pilot-club
  artifact in `main.py`). New clubs don't get trophy-name templates
  automatically — set up their awards from the club admin area after onboarding.
