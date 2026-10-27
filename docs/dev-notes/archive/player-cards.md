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

## v9.131.1 (2026-10-27): swap as many cards as you like, and awards use display names

Asked for: "you should be able to trade multiple cards at once so you can add as many cards as you like", for example one card for four of another person's, and "awards should always pick up display name and display season too".

- Migration 366 and `player_card_swap_items` (organisation, swap, side give or want, subject, special card, qty; the subject column is on `merge_carry.CARRIED`). The DDL module now has `BASE_STATEMENTS` (364), `ITEM_STATEMENTS` (366) and `STATEMENTS` (both, for the lifespan and the harnesses). The backfill copies every pre-366 request's two cards into items once; `give_subject_player_id` and `want_subject_player_id` lost their NOT NULL, and the downgrade drops only the items table. This was first numbered 365 and v9.130.4, then renumbered when main took 365 and v9.131.0.
- `create_swap` takes lists of `{key, qty}` a side: both sides non-empty, no card on both sides, every quantity held, and an identical live request to the same person is refused (a different count is a different request). `respond` locks every copy for both people in a fixed order and moves all of it or none of it; the error says whose cards fell short.
- Frontend: tap to add or remove a card on each side, a tray listing what is picked with a count (`n of held`) where a card is held more than once, a request shown as two labelled groups of cards with their counts, and the admin audit lists every card with `×qty`.
- Awards: `_insert_achievements` titles an award with the club's own display name and gives the season as the club writes it (seasons id to name, underscore to slash), for new cards and, as an update of title and detail only, for ones already made (so a rename or a corrected season reaches them). Hat-trick cards get the same season treatment.

Verified: `verify_player_cards.py` (220; the control on the previous commit fails the award checks and stops at the first multi-card request), `verify_merge_carry.py`, the two player page suites, `audit_route_access.py`; browser `verify_player_cards_browser.mjs` (51), `_v2_` (46), `_admin_` (51), and `_v3_` (30: trays, counts, limits, the exact body posted, a long request at 390px).

## v9.131.5 (2026-10-27): browse other players' cards, and find who has a card

Asked for: "make a gallery where you can see another player's cards in the same way you can see your own cards and sort them", and "search cards to see if anyone has pulled that card so you can find specific people and request swaps".

- `CardGallery` gained `browse` (with `marked`, `onAction`, `actionLabel`, `zBase`): no grey slots, a search box over name, title, season and grade, no Newest sort (the cards another player could offer carry no date), the count on a card is `tradeable`, a round pick button on every card (and on each card inside an opened stack), and holding a card up offers Add to / Take out of my request. The builder uses it for both sides, replacing the old paged grid, and is now a solid dark sheet 780px wide so the book gets the tablet layout on wide screens.
- `swaps.find_cards` and `GET /me/cards/swaps/find?q=`: tokens must all appear in the player's name, the special's title, kind label, season, grade or opposition; at least two characters; rate limited with the other swap routes; up to 30 cards, players first by tier, then specials; `unheld` names up to five matching players nobody has pulled yet. Holders are only players in the pool, never the asker, and each shows only how many copies could go.
- Frontend: `FindCards` on the Swaps tab (debounced 300ms) with an Ask button per holder that opens the builder with the person and card already chosen.

Verified: `verify_player_cards.py` (231), the other backend suites, `audit_route_access.py`; browser `_v3_` (47: book sort, search, paging, quick pick and viewer action, find with the exact query, 390px and 1280), `_v2_` (46), `_admin_` (51), the first suite (51).

## v9.131.6 (2026-10-27): the Club cards tab

Asked for: search a particular card and see it "almost exactly the same as your own gallery", without having to start a trade, "sort of like the admin section has".

- `services/player_card_catalogue.py`: `page` lays out the club's whole set as the book does (players sorted by the chosen figure, then special cards by category, one player's cards of a category as a stack with the true count, up to 100 cards sent per stack), from light rows, building only the window asked for; `holders_of` names who could swap a copy of one card. Filters: all, regular, special or a category; search over name, title, kind label, season, grade; sorts as the book, with Newest meaning when a special card was made. 36 a window at most.
- Routes `GET /me/cards/catalogue` and `/me/cards/catalogue/holders`, rate limited.
- `CardGallery` `remote` mode: the server lays out each window, the gallery asks for it whenever the page, sort, filter or search changes (search waits 250ms), counts for the chips come from the server, and a card held up shows `viewerExtra` (the holders and their Ask buttons). `CatalogueTab` answers latest-wins.

Verified: `verify_player_cards.py` (249), the other backend suites, `audit_route_access.py`; browser `_v3_` (65: the exact query for the first window, next page, search, category and sort, badges, holders by key, Ask into a prefilled request) and the three older suites.

## v9.132.0 (2026-10-27): Player Cards as a page of its own, and the dashboard moves to /playerdash

Scope and design: the "Player Cards Page Scope" artifact the club owner approved ("build the plan which I like a lot"). This release is Phase 1 of three: the move, with nothing new in how cards, packs or swaps work.

- Route: the whole player dashboard is `/playerdash/:token`, Player Cards is `/playerdash/:token/cards/*`. `/avail/:token/*` redirects (path, query and hash kept). `playerdash` was added to `og_preview.RESERVED_ROOT_SEGMENTS`, `SponsorFooter` and `Navbar` reserved lists, `clubPath.RESERVED_ROOTS` (which `FaviconManager` reads), nginx's manifest map and App's standalone list. Links the app builds (`clubs.player_page_path`, the self service panel, vote emails, the card admin page) use the new address.
- `pages/playercards/*`: shell, context, nav (sidebar, rail, bottom bar with a More sheet, a My cards / Club cards switch on phones), Home, MyCards, ClubCards, Packs, Swaps (three tabs and Find a card), NewSwap (the builder as a page: `Builder inline`), HowItWorks. `CardsModule` is gone; `CardsSummary` is the dashboard section. `AllSummary` and `CardPanel` are components of their own.
- Backend: `GET /me/cards/swaps?history=true` (a year, 100 finished swaps), and `have=not_mine|swappable` on the catalogue.
- Club cards on a wide screen (1360px and up) holds a card up in a side panel (`CardGallery onHold`, `CardPanel`) instead of over the book.

Verified: `verify_player_cards.py` (253), `verify_merge_carry.py`, `verify_player_page_dashboard.py` and `verify_vote_my_page_link.py` (paths updated), `verify_player_dashboard_and_fines.py`, `audit_route_access.py`; browser `_page_` (54: three navs, every address cold, the old address, unknown address, Home, Packs, How, Swaps tabs and builder, filters, the side panel), `_v3_` (65), `_v2_` (45), `_admin_` (51), the first suite (55: now the dashboard summary, the page and the old address).

Phases 2 and 3 (wish list, spares, card page, counters; sets, showcase, board, feed) follow.

## v9.132.1 (2026-10-27): wish list, spares, the card page, changing a swap, alerts

Phase 2 of the Player Cards page plan.

- Migration 368 (`player_card_social_ddl.py`): wants, open offers, prefs, the alert log, `player_card_swaps.parent_swap_id` and `note`, `club_card_settings.alerts_enabled`. Defaults for the choices left open in the plan: wish list private; email alerts on by default and switchable by player and by club; counter offers in; no rewards. (The first numbered 368 as main's top was 367.)
- `services/player_card_social.py`: wish list (with who could swap each card now), spares and open to offers (the demand as a number), one card in full, prefs. Routes under `/me/cards/wants`, `/spares`, `/spares/open`, `/card`, `/prefs`, and `POST /me/cards/swaps/{id}/counter`.
- `swaps.counter_swap`: only the person asked, on a live pending request; the new request is checked like any other; the old one ends `countered` in the same transaction. The admin audit has a Changed filter and shows the note and whether a request is a changed one.
- `services/player_card_alerts.py`: `swap_asked` and `scan_wants` as background tasks after pack opens, open-all and accepted swaps (a scan re-arms an alert when nobody could swap the card any more), and a club switch on the admin Settings tab.
- Frontend: Wishlist, Spares, CardPage, Settings screens; Club cards holders panel has Add to wish list and Card page; the builder has a note box (200 characters), and "Change it" on an incoming request opens it pre-filled with their cards and yours; Home has a Wish list tile; the sidebar has Wish list (badge: cards someone could swap), Spares and Settings, and More holds them on a phone.

Verified: `verify_player_cards.py` (309; the control on the previous commit fails the seven social groups only), `verify_merge_carry.py`, the player page suites, `audit_route_access.py`; browser `_social_` (39), `_page_` (54), `_v3_` (65), `_v2_` (45), `_admin_` (54), the first suite (55).

## v9.132.2 (2026-10-27): sets, showcase, the collectors board and This week

Phase 3 of the Player Cards page plan.

- Migration 369 (`player_card_community_ddl.py`): `player_card_showcase`, `player_card_prefs.board_opt_in` and `.feed_hidden`, and the club's `sets_enabled`, `showcase_enabled`, `board_enabled`, `feed_enabled`. Choices left open in the plan, taken as suggested: the board is opt in and the feed opt out; sets earn a banner only.
- `services/player_card_sets.py`, `player_card_community.py`; routes `/me/cards/sets`, `/sets/{key}`, `/showcase` (GET, PUT), `/board`, `/feed`, `features` on `/me/cards` and on prefs; `set=` on the catalogue; admin `GET /player-cards/wanted` and the four switches on the Settings tab.
- Frontend: Sets (tabs: Sets, Collectors, This week), SetPage, Showcase, Home blocks for the showcase and the week, Settings toggles for being seen, nav entries that follow the club's switches.
- Not done, and why: the scope doc put the showcase on "your public card page". The only public page is the stats share page (`/players/:id/share`), which is not a trading card page and has no card data behind it, so the showcase shows to the club (the board, Home) instead. If a public card page is wanted, it needs its own public route and a decision about what is public.

Verified: `verify_player_cards.py` (344), `verify_merge_carry.py`, the player page suites, `audit_route_access.py`; browser `_community_` (33), `_social_` (39), `_page_` (54), `_v3_` (65), `_v2_` (45), `_admin_` (59), the first suite (55).

