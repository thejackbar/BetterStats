# Guide: Player Cards (collectable cards, packs, the card book)

**Read this before**:
- Touching `services/player_cards.py`, `player_cards_ddl.py`, `routers/public_player_cards.py`, `routers/player_cards_admin.py`, `components/cards/*`, `CardsModule.jsx`, `AdminPlayerCards.jsx`.
- Changing what the player page (`/avail/:token`) needs from BetterSelect, or `player_dashboard.py` module defaults.
- Adding a table that records what a person owns or earned (it goes on `merge_carry.CARRIED`).

**Archive** (full history, do not load whole): `docs/dev-notes/archive/player-cards.md`.

**Related guides**: `betterselect-selection-and-nets` (the player page and its PIN), `cross-club-and-data-safety` (`merge_carry`), `stats-figures-records-and-filters` (the figures cards read), `sponsors-tiers-and-naming` (the sponsor chip on a card, and who picks it).

## Standing rules

1. **A regular card is derived, never stored.** Figures and the 1 to 99 rarity come from `club_snapshot` (cached 5 minutes per club; `forget(org)` after a settings or hide change). What a person owns is `player_card_copies`, one row per copy, so a double is a second row. A player's own card is implied and is never a row.
2. **Grants and cards only ever ADD.** A pack is unique on (player, source, ref_key); a figure corrected downwards never takes one back. A special card is unique on (club, event_key) and a score corrected later keeps its card (it commemorates the moment). Hiding a player removes their card from packs and galleries; it deletes nothing, and showing them again brings it back. Never delete a pack, copy or special card.
3. **Every player-keyed table here is on `merge_carry.CARRIED`** (owner and subject columns both), so a merge moves a collection. A new such table needs the same entry plus `_OWN_CLUB_TABLES`.
4. **The pool**: club players with `is_player`, minus `is_public` false (this is also how a removal request is honoured), minus `player_card_hidden`, minus junior-only players unless `include_juniors`, and only players with a match are drawable. Never widen it for a convenience.
5. **Packs**: 2 starter, the club's weekly count per Monday-to-Sunday week in the club's timezone (default `Australia/Perth`; only the weekly pack expires), 1 per 25 runs / 2 wickets / 2 dismissals in the club's CURRENT season (newest played game, as year and kind), 1 per duck since `club_card_settings.launched_at`. Never `ORDER BY year DESC, name DESC` for the season.
6. **Odds**: Common 60, Rare 28, Epic 10, Legendary 2; a special card 5% of the time when the club has any; one Rare or better guaranteed; no repeat in a pack. `draw_cards` is pure so the odds are testable. There are no paid packs. Do not add any.
7. **Special cards** are made by `refresh_specials` (throttled 10 minutes per club, `force` from the admin button), each with a stable `event_key` (player, date, innings) so pairing a manual game with a synced one does not make a second card. Add a kind in `SPECIAL_KINDS`, the insert in `refresh_specials`, `cardTheme.SPECIALS` and `specialHeadline`. An award card reads the club's display name for the award (`org_award_definitions.display_name`, one definition picked by `sort_order`) and the season the way the honour board does (a seasons id becomes its name, `2015_16` reads `2015/16`), and `refresh_specials` brings an existing award or hat-trick card in line (title and detail only). Career milestones (`STAT_MILESTONES`: every 1,000 runs, 200 wickets, 50 dismissals, capped 30/10/20 a player) key on `kind:player:threshold`, are dated only when the held scorecards can place the step, and file with the games milestones in the book.
8. **The player page no longer needs BetterSelect.** `_club_for_token(need_select=False)` serves the landing, PIN, `/me`, profile, ranks and details; the availability write (`set_me`) still needs it. A club without it gets `has_availability: false` and no Availability section. Keep `SELECT_ONLY` modules blocked for it.
9. **A PATCH reads `model_fields_set`**: an absent key leaves the setting alone, `timezone: null` clears it.
10. **Swaps** (`services/player_card_swaps.py`): any card a player HOLDS can go, a single copy as well as a double (`tradeable()`, one row = one copy). Their own card is implied and has no row, so it never goes; only copies of it they have pulled do. A request is MANY cards each way (`player_card_swap_items`: side, card, qty; up to 50 different cards a side, 99 copies of one), nothing moves until the person asked accepts, and the accept re-checks every card under row locks (owner id order, then card order) and moves all of it or none of it; a stale request answers 409. The old `give_*` / `want_*` columns on `player_card_swaps` are only read by migration 366's backfill; new requests leave them empty. A gifted special that is swapped away takes the subject's own commemorative copy with it (their choice). A request is never deleted. Only the cards another player holds are readable by a player. No separate sign in: the PIN cookie is the identity and the second person's yes is the safeguard. A swapped copy is marked `source = 'swap'`. The route still reads the first release's `give_key` / `want_key`.
11. **The book** files specials awards, milestones, centuries, half centuries, wickets, debuts (`CATEGORIES` in `CardGallery.jsx`; add a kind to one of them) and stacks one player's cards of one kind on one slot. Grey slots are for player cards only.
12. **Text on a card goes through `FitText`**, never a length based font size: it measures, so a long name, a long award or a wide club font cannot clip. Italic type needs room on the right (`FitText` adds it); never `overflow: hidden` on display type. Cards use the club's display font through `useCardStyle`.
13. **Sharing**: a picture for any card, and for the player's own card a link and a GIF made on the device (`lib/cardGif.js`). Rendering goes through `renderNodeBlob`, so the club's font is embedded as on the share card.
14. **The admin view** (`services/player_card_admin.py`) only reads. A card is drawn only for a player in the pool; anyone else appears as a line of text. "Expired" is derived from age and never written.
15. **Frontend**: card faces are drawn flat at `CARD_W x CARD_H` and scaled with `ScaledCard`. The gallery measures its own width (phone 2x2, tablet 3x2, spread two pages), so the player page's cards section spans every column (`Group wide`). Every animation is off under reduced motion. `innerText` of a card returns capitals (CSS uppercase), write checks that way.

## Verify

- `backend/verification/verify_player_cards.py` on its own database (220 checks); control: run it on the previous commit.
- `frontend/verification/verify_player_cards_browser.mjs`, `_v2_browser.mjs`, `_v3_browser.mjs` and `_admin_browser.mjs` on the production build (`vite preview`); never rebuild `dist` under a running preview for a long run.
- Also re-run `verify_merge_carry.py`, `verify_player_page_dashboard.py`, `verify_player_dashboard_and_fines.py`, `audit_route_access.py`.

## Open follow-ups

- Club record special cards; an email or push for a swap request; a season rollover rule for banked packs; figures are not raised to held scorecards. Swaps rest on the PIN, so a club that wants trading to carry weight needs real sign-in first.
