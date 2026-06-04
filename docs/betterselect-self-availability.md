# Self-service availability — design note

_Status: **built** (Phase 1 + the cheap Phase 2 wins). Owner: BetterSelect.
Drafted May 2026, shipped June 2026 (v8.1)._

## What shipped (June 2026, v8.1)

Phase 1 in full, plus the low-cost Phase 2 niceties:

- **Data** — migration `068`: `organisations.availability_link_token` (unique,
  nullable, rotatable) + `availability_self_service_enabled` +
  `availability_require_pin`; `player_availability.source` ('admin' | 'self').
- **Public API** (`routers/public_availability.py`, prefix `/public/availability`,
  unauthenticated — resolves the club from the token, checks the `select`
  entitlement + enabled flag itself, so it's *not* wrapped in `require_module`):
  `GET /{token}` (branding + active-player names), `POST /{token}/verify`
  (last-4 PIN → signed HttpOnly `bs_avail` cookie, ~30d), `GET|POST /{token}/me`
  (this player's dates + answers / upsert with `source='self'`),
  `POST /{token}/switch`. Lockout after 5 wrong PINs / 15 min per player+IP plus
  a per-IP throttle (`services/rate_limit.FailureTracker`).
- **Admin API** (on the gated `availability` router): `GET /availability/self-service`,
  `POST /availability/self-service` (enable + PIN toggle, mints a token on first
  enable), `POST /availability/self-service/regenerate`. Returns a phone-coverage
  count.
- **Frontend** — public route `/avail/:token` (`pages/PublicAvailability.jsx`),
  outside `ProtectedRoute`, own minimal header (global nav suppressed). Admin
  panel `SelfServiceLinkPanel.jsx` on the Availability screen: enable/PIN
  toggles, link, copy-link, copy-message, **client-side QR** (`qrcode`),
  regenerate, phone-coverage nudge. Self-reported matrix cells get a corner dot.
- **PIN default**: required, with a per-club off switch (resolves the open
  decision). **Scope**: per-club link (v1). **Session**: 30 days.

The rest of this note is the original design (kept for the rationale).

---

_Status: proposed (not built). Owner: BetterSelect. Drafted May 2026._

## Goal
Let **players update their own availability** for upcoming fixtures, so admins
stop hand-entering the whole matrix. Must work **without integrating Facebook**
and **without requiring an app download** — players are on phones, in a group
chat, and won't install anything.

## Chosen approach
**One club self-service link + self-identify + a last-4-of-phone PIN, distributed
by manual share / QR** (pinned in the team's group chat or Facebook group).

> Pinning a link in a Facebook *group* is just sharing a URL — it is **not** the
> Facebook API *integration* we're avoiding. Same for a WhatsApp/SMS group.

The link is the *distribution/scoping* control; the PIN is the *identity*
control; a session cookie keeps the player verified afterwards.

### Why per-club, not per-team (for v1)
The data model is **club-wide: players are not hard-assigned to teams** (`Team`
just groups fixtures). There's no fixed team→player roster to drive a per-team
name list. So v1 uses **one per-club link** whose name list is "active
(non-dormant) club players," surfaced via **type-to-search** (the player types
their name rather than us dumping the whole roster — better UX, mildly better
privacy). Per-team links (scoped to a team's *derived* squad from recent
appearances) are a later refinement and need a "not listed?" fallback.

## User flow (mobile-first, 3 screens)
1. **Open link / scan QR** → club crest + name (white-labelled), "Set your
   availability", a search box → tap your name.
2. **Prove it's you** → "Last 4 digits of your mobile" (numeric). Compared to
   `Player.phone` → verified.
3. **Your weekend** → upcoming fixtures grouped by date, each a 3-way
   **Available / Maybe / Unavailable** tap (+ optional note). Saves instantly.
   "Not you? Switch player."

Availability is **date-keyed** (one answer covers every fixture that day), so a
single tap can cover multiple same-day fixtures and both legs of a two-day game.

## Scope

### Data model (1 migration)
- `organisations`: `availability_link_token` (128-bit, unique, nullable,
  **rotatable**) + an enabled flag. (On the org for the per-club v1.)
- `player_availability`: add **`source TEXT DEFAULT 'admin'`** (`'admin' |
  'self'`). This is the key add — `recorded_by` is a *user* FK and is NULL for
  self-service, so `source` is what lets us tell self-reported answers apart and
  audit them. (`recorded_at` already exists for the timestamp.)

### Backend (public, unauthenticated, token-scoped)
- `GET /public/availability/{token}` → club branding + active-player names (id +
  display name only). 404 if the token is disabled/unknown.
- `POST /public/availability/{token}/verify` → `{ player_id, pin }`. Normalize
  `Player.phone` (strip non-digits, take last 4), compare. On success issue a
  **signed HttpOnly session cookie** `{ club_id, player_id, exp ~30d }`.
  **Rate-limited + lockout** (e.g. 5 fails → 15-min cooldown per player + IP).
- `GET .../me` (session) → upcoming fixtures grouped by date + this player's
  current answers.
- `POST .../me` (session) → `{ date, status, note? }`. Validate the date is a
  real upcoming club fixture; upsert `PlayerAvailability` (respecting the
  `(player_id, avail_date)` unique constraint) with `source='self'`,
  `recorded_by=NULL`, `recorded_at=now`. Rate-limited.

### Frontend
- One **public** route (outside `ProtectedRoute`), the 3-step page, white-labelled
  via the token's club. QR generated client-side (small `qrcode` lib).

### Admin (BetterSelect → Availability / Teams)
- **Self-service link panel**: enable toggle, the URL, **QR**, copy-link,
  copy-message-template ("🏏 Set your availability: {link}"), **Regenerate**
  (invalidates the old QR/link).
- **`source='self'` marker** on matrix cells, so admins see what came from
  players vs. what they set.
- **Phone-coverage nudge**: "32/45 active players have a mobile on file — the
  rest can't self-serve" + a quick way to add numbers.

## Security model & honest risks
Three separate controls:
- **Link token** — "this is the club's self-service page." It's pinned publicly,
  so it's low-trust *by design*; just keep it rotatable.
- **PIN (last-4 of phone)** — proves which player you are.
- **Session cookie** — keeps you verified ~30 days; "switch player" clears it.

Be honest about the PIN:
- **Low entropy (10k combos)** → the rate-limit/lockout is **mandatory**.
- **A teammate who knows your number can edit your availability.** Acceptable for
  availability stakes — `source` + `recorded_at` give an audit trail and the
  admin always overrides — but it's a conscious trade-off. Optional per-club
  toggle to require / disable the PIN.
- **Depends on `Player.phone` being populated** (migration 044 added it, but it's
  likely sparse). No phone ⇒ can't self-verify; that player shows "no mobile on
  file" and the admin sets them manually. (Per-player fallback link is a later
  option.)

Write endpoint only ever touches *that verified player's* availability, only for
*valid upcoming club fixture dates*, and exposes no PII beyond the player's own
name + the (semi-public) fixture list.

## Edge cases (handled cleanly)
- Two players ending "5678" → fine; you pick your name *first*, then prove with
  *your own* last-4.
- Phone formatting (+61 / 0 / spaces) → last-4 is stable after stripping
  non-digits.
- Wrong name + your own PIN → mismatch; can't accidentally edit someone else.
- Two-day games / multiple same-day fixtures → one date tap covers them.
- Leaked link → fine by design; the PIN is the real gate; Regenerate if abused.

## Phasing
- **Phase 1** — per-club link, search-name, last-4 PIN, the 4 endpoints, public
  page, admin enable/QR/copy/regenerate, `source` column, rate-limit. Manual
  share. _(Medium build, ~1–2 focused days.)_
- **Phase 2** — self-reported markers in the matrix, phone-coverage nudge,
  per-player fallback for no-phone players, optional PIN toggle.
- **Phase 3 (optional)** — automated SMS/email reminders carrying the link;
  response-rate analytics; per-team scoped links.

## Open decisions
- Per-club (recommended for v1) vs per-team (derived squad, fuzzier) — **confirm**.
- PIN required by default, or a per-club toggle from day one?
- Session length (30d convenient vs shorter for shared/kiosk QR use).

_See `docs/betterselect.md` for the module overview, and `CLAUDE.md` for deploy/
architecture._
