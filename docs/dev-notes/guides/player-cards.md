# Guide: Player Cards (collectable cards, packs, the card book)

**Read this before**:
- Touching `services/player_cards.py`, `player_cards_ddl.py`, `routers/public_player_cards.py`, `routers/player_cards_admin.py`, `components/cards/*`, `CardsModule.jsx`, `AdminPlayerCards.jsx`.
- Changing what the player page (`/avail/:token`) needs from BetterSelect, or `player_dashboard.py` module defaults.
- Adding a table that records what a person owns or earned (it goes on `merge_carry.CARRIED`).

**Archive** (full history, do not load whole): `docs/dev-notes/archive/player-cards.md`.

**Related guides**: `betterselect-selection-and-nets` (the player page and its PIN), `cross-club-and-data-safety` (`merge_carry`), `stats-figures-records-and-filters` (the figures cards read), `sponsors-tiers-and-naming` (the sponsor chip on a card).

## Standing rules

1. **A regular card is derived, never stored.** Figures and the 1 to 99 rarity come from `club_snapshot` (cached 5 minutes per club; `forget(org)` after a settings or hide change). What a person owns is `player_card_copies`, one row per copy, so a double is a second row. A player's own card is implied and is never a row.
2. **Grants and cards only ever ADD.** A pack is unique on (player, source, ref_key); a figure corrected downwards never takes one back. A special card is unique on (club, event_key) and a score corrected later keeps its card (it commemorates the moment). Hiding a player removes their card from packs and galleries; it deletes nothing, and showing them again brings it back. Never delete a pack, copy or special card.
3. **Every player-keyed table here is on `merge_carry.CARRIED`** (owner and subject columns both), so a merge moves a collection. A new such table needs the same entry plus `_OWN_CLUB_TABLES`.
4. **The pool**: club players with `is_player`, minus `is_public` false (this is also how a removal request is honoured), minus `player_card_hidden`, minus junior-only players unless `include_juniors`, and only players with a match are drawable. Never widen it for a convenience.
5. **Packs**: 2 starter, the club's weekly count per Monday-to-Sunday week in the club's timezone (default `Australia/Perth`; only the weekly pack expires), 1 per 25 runs / 2 wickets / 2 dismissals in the club's CURRENT season (newest played game, as year and kind), 1 per duck since `club_card_settings.launched_at`. Never `ORDER BY year DESC, name DESC` for the season.
6. **Odds**: Common 60, Rare 28, Epic 10, Legendary 2; a special card 5% of the time when the club has any; one Rare or better guaranteed; no repeat in a pack. `draw_cards` is pure so the odds are testable. There are no paid packs. Do not add any.
7. **Special cards** are made by `refresh_specials` (throttled 10 minutes per club, `force` from the admin button), each with a stable `event_key` (player, date, innings) so pairing a manual game with a synced one does not make a second card. Add a kind in `SPECIAL_KINDS`, the insert in `refresh_specials`, `cardTheme.SPECIALS` and `specialHeadline`.
8. **The player page no longer needs BetterSelect.** `_club_for_token(need_select=False)` serves the landing, PIN, `/me`, profile, ranks and details; the availability write (`set_me`) still needs it. A club without it gets `has_availability: false` and no Availability section. Keep `SELECT_ONLY` modules blocked for it.
9. **A PATCH reads `model_fields_set`**: an absent key leaves the setting alone, `timezone: null` clears it.
10. **Frontend**: card faces are drawn flat at `CARD_W x CARD_H` and scaled with `ScaledCard`. The gallery measures its own width (phone 2x2, tablet 3x2, spread two pages), so the player page's cards section spans every column (`Group wide`). Every animation is off under reduced motion. `innerText` of a card returns capitals (CSS uppercase), write checks that way.

## Verify

- `backend/verification/verify_player_cards.py` on its own database (104 checks); control: run it on the previous commit.
- `frontend/verification/verify_player_cards_browser.mjs` on the production build (`vite preview`); never rebuild `dist` under a running preview for a long run.
- Also re-run `verify_merge_carry.py`, `verify_player_page_dashboard.py`, `verify_player_dashboard_and_fines.py`, `audit_route_access.py`.

## Open follow-ups

- Club record special cards; swapping cards (needs real sign-in, not a 4 digit PIN); a season rollover rule for banked packs; figures are not raised to held scorecards.
