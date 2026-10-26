# Player Cards release notes

## v9.130.0 (2026-10-26): collectable cards, packs and the card book

Asked for as a gamification of BetterStats, in the spirit of EAFC Ultimate Team and collecting Pokemon cards. Every player has a card of six career figures; players open packs of other players' cards from their own player page and keep them in a book.

Decisions the club owner made, in their words where it matters:

- The PIN stays the last 4 digits of the mobile for now ("the collection doesn't have real worth"). Swapping cards between players is phase 2 and will need real sign-in, because a 4 digit PIN is not enough to trade on.
- The player page is available to every club, even with only BetterStats. It needs a mobile number on the Players page to sign in.
- Own club's players only. No juniors by default; a Player Cards setting includes them.
- No paid or purchasable packs, ever. Do not add any.
- Card figures: career matches, runs, batting average, wickets, bowling average, dismissals (catches, run outs and stumpings together). "-" where a figure does not exist. The layout is the existing share card, with RARITY in the top corner.
- Cards update as figures change; special cards are frozen at the moment they commemorate.
- Packs: 5 cards, duplicates allowed, at least one Rare or better. 2 starter packs on first use, 1 weekly (Monday 00:00 club time, the unopened one expires), one per 25 runs, 2 wickets and 2 dismissals in the current season across all grades, backfilled for the current season only. A duck earns a Duck Pack ("better luck next time"), from launch forward, not backfilled.
- Special cards: century, half century, five-for, hat-trick, debut, games milestone, club award. Each kind has its own colours; every special card is one event; the player it commemorates is always gifted a copy; anyone can pull it. Generated from the whole history.
- Fantasy's own player cards are left as they are for now.

What was built:

- Migration 363 and `services/player_cards_ddl.py` (one copy, mirrored in the lifespan): `club_card_settings`, `player_special_cards`, `player_card_packs`, `player_card_copies`, `player_card_hidden`. All player keyed tables are on `merge_carry.CARRIED`.
- `services/player_cards.py`: the pool, figures, rarity (percentile blend plus a bonus for standing on the club's all time boards, 1 to 99; Legendary 90+, Epic 75+, Rare 55+), pack grants, the draw, special card generation, the collection.
- `routers/public_player_cards.py` (player facing, behind the PIN cookie), `routers/player_cards_admin.py` (`/player-cards/*`, `MANAGE_SETTINGS`).
- The player page works without BetterSelect: `public_availability._club_for_token(need_select=False)`, a `cards` dashboard module (in `AUTO_ON_WHEN_NEW`, so every club gets it), `NO_SELECT_DEFAULT_MODULES`, `SELECT_ONLY` modules blocked without BetterSelect, `clubs._player_page_path`, and a lifespan step that mints a link for any club with players that has none.
- Frontend: `components/cards/` (`CardFaces`, `PackOpening`, `CardGallery`, `cardTheme`, `cards.css`), `pages/playerhome/CardsModule.jsx`, `pages/admin/AdminPlayerCards.jsx` (Club Data > Records & content > Player Cards).
- The pack opening is built directly on GSAP (already a dependency). `react-cards-opening` (BetterTyped) was read and not adopted: MIT and React 18 compatible, but new (6 stars, no releases listed), and our card faces and tier effects needed to drive it. Revisit if the opening needs more variety.

Changed an existing rule: `verify_player_page_dashboard.py` used to assert that a club without BetterSelect gets a null `player_page_path`; it now asserts the page exists for it.

Verified: `backend/verification/verify_player_cards.py` (104 checks, real Postgres, shipped service and route bodies; the control against the previous commit fails the landing, `/me`, module defaults and every cards check without crashing), `verify_merge_carry.py`, `verify_player_page_dashboard.py`, `verify_player_dashboard_and_fines.py`, `audit_route_access.py`; `frontend/verification/verify_player_cards_browser.mjs` (51 checks, Chromium on the production build with the API stubbed: the exact open request, tier order, NEW and DUPE marks, sort and filter, spread and phone layouts, 390px overflow, holo follows the pointer, reduced motion).

Not built yet:

- Club record special cards (needs a stable "record broken" event; records are computed on read).
- Swapping cards (phase 2).
- A season rollover rule for banked packs (they bank across seasons today; the weekly pack is the only one that expires).
- Rarity and figures are the unfiltered career block (`v_effective_player_season_stats`), not raised to held scorecards, so a profile can read a game or two higher for a player Cricket Australia undercounted.
