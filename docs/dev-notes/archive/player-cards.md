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

## v9.130.2 (2026-10-26): swaps, sharing, a tidier book, the admin view

Asked for after the first release was in use: the book was four pages of the owner's own special cards; special cards should use the whole photo; text was clipped; cards should use the club's font; swapping; sharing and a GIF; and an admin view of who collects what.

Decisions the club owner made:

- Swaps need no real sign in ("not high value still"). The PIN cookie names both people; the safeguard is that nothing moves without the second person's yes.
- A GIF is for the player's own card only (the shine, or turning over). Any card can be shared as a picture.
- The book orders specials awards, milestones, centuries, half centuries, wickets (five-fors and hat-tricks), debuts, and groups a player's cards of one kind into one stack.

What was built:

- Migration 364 and `services/player_card_swaps_ddl.py`: `player_card_swaps`. Its four player columns are on `merge_carry.CARRIED`. A request is never deleted; it ends accepted, declined or cancelled, or lapses (read from its age, 14 days, nothing stored).
- `services/player_card_swaps.py`: `spare()` is the one definition of what can go (one is always kept; the player's own card is implied, so every pulled copy of it is spare). The accept re-checks both cards under row locks taken in a fixed order, moves one copy each way (a pulled copy before a gifted one, marked `source = 'swap'`) and answers 409 with a readable reason if either is no longer a double. Only another player's spare cards are ever readable through the swap routes.
- `services/player_card_admin.py` and read-only routes under `/player-cards` (`MANAGE_SETTINGS`): `overview`, `activity`, `catalogue` (paged, filterable), `players/{id}`, `swaps` (audit, with expired derived from age).
- The public routes `GET/POST /me/cards/swaps...`; the profile summary carries `swaps_waiting`.
- `_club_branding` now carries the club's font fields (`fonts.public_font_fields`), and `useCardStyle` adds the club's @font-face and display font to the cards.
- Frontend: `FitText` (measured shrink-to-fit with room for italic lean; replaces the length based sizes), `SpecialFront` redrawn on the same layout as a player card, `CardGallery` categories and stacks, `SwapsPanel`, `ShareSheet`, `lib/cardGif.js` (two flat pictures of the card composed on a canvas, quantised from the card's own pixels, `gifenc` 1.0.3 MIT, pinned), `renderNodeBlob` and `deliverBlob` split out of `exportNodePng`, and a seven tab `AdminPlayerCards`.

Verified: `verify_player_cards.py` (186 checks; the control on the previous commit fails exactly the swap and admin checks and nothing else), `verify_merge_carry.py`, the two older player page suites (their harnesses now load the swaps DDL), `audit_route_access.py`; browser: `verify_player_cards_browser.mjs` (51), `verify_player_cards_v2_browser.mjs` (46: stacks and order, full photo, no clipping, club font, a real PNG and two real GIFs downloaded and read back, swaps down to the exact requests), `verify_player_cards_admin_browser.mjs` (51: every tab, the exact query each filter sends, 390px on every tab).

Not built: an email or push when a swap is asked (the page header says "1 swap request" instead); a GIF of someone else's card; special cards for club records.

## v9.130.3 (2026-10-27): swap any card you hold, and run, wicket and dismissal milestones

Asked for: swaps should work for any card a player holds, not only doubles, still agreed by both people; and milestones for runs, wickets and dismissals ("every 1000 runs, 200 wickets and 50 dismissals").

What changed:

- The swap rule: `spare()` became `tradeable()`. Every row a player holds can be offered, a single copy included. Their own card is still implied and never a row, so it cannot be given away; copies of it they pulled can. Errors read "You can only offer a card you hold" and "The card they offered is no longer theirs to give". The accept still locks both cards in a fixed order and re-checks. No migration. A swapped-away gift also removes the subject's commemorative copy, which is their call to make.
- `STAT_MILESTONES` in `services/player_cards.py` and `_insert_stat_milestones`: one card per step of career runs (1,000), wickets (200) and dismissals (50, catches plus run outs plus stumpings), capped at 30, 10 and 20 cards per player. The total is the unfiltered career block; the date is the held innings in which the running total first crossed the step, and stays empty where the held scorecards cannot place it (older season totals), never a guess. `event_key` is `kind:player:threshold`, so a corrected score does not make a second card and nothing is taken back.
- Volume: a player earns floor(runs/1000) + floor(wickets/200) + floor(dismissals/50) cards, so a long career of 4,114 runs, 211 wickets and 98 dismissals is 6 cards. Most players hold a few or none. A pool of cards grows by the sum of that across the club, and specials stay 5% of pack slots, so each special is diluted rather than packs being flooded. In the book one player's milestones are one stack.
- Frontend: three new `SPECIALS` themes (blue, pink, lime) with the number as the headline; the book files runs, wickets and dismissals under Milestones after the games card; the viewer offers a card whenever the player holds a copy to give; the swap builder pages 24 at a time with a search over eight cards.

Verified: `verify_player_cards.py` (194; the control on the previous commit fails exactly the milestone and swap checks), the other suites unchanged, browser `verify_player_cards_v2_browser.mjs` (46), new `verify_player_cards_v3_browser.mjs` (17: stack order, the three new faces without clipping, the offer button rule, search and paging at 390px).

