# Archive: Sponsors (tiers, placements, naming rights, post defaults)

## Sponsor tiers, major slot and full sponsor list (v9.103.0)

Asked for by the club group: more sponsorship spots, tiers, and a full list of sponsors on every page.

- **Model.** Migration 318 (`services/sponsor_tiers_ddl.py`, mirrored in the lifespan and in the football schema mirror): `org_sponsors.tier` (default `silver`), `org_sponsors.placements` JSONB (hand-set overrides only), `organisations.sponsor_tier_labels` JSONB. Defaults: major = dashboard, bar, list; gold and silver = bar, list; supporter = list.
- **Public.** `GET /clubs/{slug}/sponsors` now returns every sponsor tier first, with `tier`, `tier_label`, `placements` and the club's `tier_labels`. `useClubSponsors` shares one fetch between the dashboard slot, `SponsorWall` and the bar.
- **Dashboard.** `PageHeader` takes an optional `aside` (right column, above the actions). `MajorSponsorSlot`: one sponsor large, several in a grid, nothing when none, an add prompt for an admin who can manage sponsors for that club.
- **Every club page.** `SponsorFooter` renders `SponsorWall` above the sticky bar. Player and scorecard pages have no slug in the URL, so they call `rememberClubSlug`, which `SponsorFooter` listens for. Section list extended with fixtures, lineups, teams, premierships, honour-board, ladders.
- **Admin.** Tier select and three spot toggles per sponsor (a star marks a hand-set spot, Reset to tier clears them), tier select on add, a Tier names panel. Server now gates every sponsor write on `MANAGE_SPONSORS`.
- **Verified.** `verify_sponsor_tiers.py` (real Postgres, shipped route bodies, 57 checks; control on the previous commit fails the 11 behaviour checks without crashing) and `verify_sponsor_tiers_browser.mjs` (production build, API stubbed, 23 checks including 390px; control build fails 16 and passes the 7 that should not change).

## Section names with a linked sponsor (v9.104.0)

Scarborough wanted Fantasy called "Froth Fantasy Cricket" for their sponsor, and the same for other public sections.

- **Model.** Migration 319 (`services/section_names_ddl.py`, lifespan mirror, football schema mirror): `organisations.section_names` JSONB, `{key: {name, sponsor_id}}`, only what the club set. The sponsor's logo and link are read live from `org_sponsors`, so a deleted sponsor stops being drawn and the rename stays.
- **Sections** (`services/section_names.SECTIONS`): leaderboard, records, statlab, premierships, honour_board, ladders, players, player_profile, compare, yearbook, fantasy. Names are one line, 60 characters, control characters flattened. A name equal to the standard one is no rename. A section key that does not exist is a 422.
- **Public.** `GET /clubs/{slug}/sponsors` also returns `section_names` (resolved, with the sponsor card), so one cached fetch (`useClubSponsors`) feeds the navbar, page headings, `SectionBanner` and the footer. Pages call `useSectionNames(clubSlug)`; a renamed page makes the club's name its heading and drops the section label from its eyebrow. URLs are unchanged on purpose (no redirects to maintain).
- **Presented by.** `SectionBanner` (mounted once under the navbar in `App.jsx`) maps the URL to a section and draws the strip only when a sponsor with a logo is linked. `/players/:id` maps to `player_profile` through the remembered club slug.
- **Fantasy.** `GET /public/fantasy/{token}` adds `club.fantasy_name` and `club.fantasy_sponsor`. The game header, sign-in, dead-link page and share cards use `fantasyName(club)`; the club name moves to the sub line.
- **Share cards.** `og_preview` keeps the section from the path and titles a renamed section's card with its own name. `honour-board`, `premierships` and `ladders` were added to its section list.
- **Not changed.** BetterPosts templates carry no section names (they name post types, not these sections), so nothing there was renamed. Admin screens keep the standard names.
- **Verified.** `verify_section_names.py` (real Postgres, shipped route bodies, 30 checks; control on the previous commit fails the 11 behaviour checks without crashing) and `verify_section_names_browser.mjs` (production build, API stubbed, 26 checks including the exact PUT body and 390px; control build fails 14 and passes the 12 that should not change).

## A sponsor on every post, and team sponsors (v9.105.0)

Asked for by the club group: bigger, more prominent sponsor marks in BetterPosts, a grid that resizes like the club lockup, a sponsor on every post by default, easy to change, and a sponsor that can be pinned to a team.

- **Model.** Migration 320 (`services/post_sponsors_ddl.py`, lifespan mirror, football schema mirror): `organisations.post_sponsor_defaults` JSONB, `{teams|grades: {normalised name: {name, sponsor_ids}}}`, only what the club pinned. A fourth placement spot, `posts` ("Social posts"), joins `dashboard`, `bar`, `footer`; Major and Gold have it by default, existing sponsors are Silver so nothing changed for them.
- **Which sponsors a post gets** (`services/post_sponsors.resolve`, route `GET /club-admin/sponsors/post-default?team=&grade=`): the team's pin, the grade's pin, the club default (sponsors with the `posts` spot, tier order, at most 4), then the top sponsor with a logo. A sponsor with no logo, a deleted sponsor or another club's id is skipped at every step. Keys are the lower-cased, space-collapsed name because a post only knows names, and a team's grade changes between seasons.
- **Routes.** `GET` and `PUT /club-admin/sponsors/post-defaults` (options from the club's `Team` rows and `club_grade_rows`, the pins, the club default; PUT needs `MANAGE_SPONSORS` and replaces the pins wholesale).
- **Editor.** A new `sponsors` block type in `social/blank-template.jsx`: `sponsorGridLayout` picks the column count that fits the biggest logo, the last row is centred, backing is light, dark or none. Ids resolve against the live `data.sponsors`, so a saved template shows current logos. `AdminSocialPost` fetches the default (debounced on the post's headline and competition), adds one grid per post (functional `setItems`, so a double effect cannot add two), and keeps an `auto` grid following the team and canvas size until it is moved, resized or its sponsors change (`releaseSponsorAuto`). The grid lives in the overlay layer, so `overlayItems` now always includes sponsors blocks even with Custom Edit off; every other block still waits for Custom Edit.
- **Removal.** `hRemove` asks before deleting the last sponsors block and records it in `sponsorDismissed[templateId|page]` so the effect does not put it back on that post. The Delete key goes through `hRemove` too.
- **Layouts with sponsor slots of their own** (fixtures, results, scorecards, `nativeSponsors`) get no grid. Their two slots start from the default, until somebody picks their own (`metaSponsorsAuto`).
- **Football.** The silo has no `post-default` route; the editor falls back to the first sponsor with a logo.
- **Verified.** `verify_post_sponsors.py` (real Postgres, shipped route bodies, 35 checks; control on the previous commit fails the three existence checks) and `verify_post_sponsors_browser.mjs` (production build, API stubbed, 24 checks; control build fails 16 and passes the 8 that should not change). The existing `verify_post_designer_browser.mjs` still passes 130 of 130.

## Dashboard buttons on the filter row (v9.105.1)

With the major sponsor slot in the header's right column, Sync and Leaderboard under it left the slot floating above the club name. When the slot (or the admin prompt) shows, `Dashboard.jsx` now passes `actions={null}` to `PageHeader` and renders the same buttons at the right of the Season filter row, so the slot's bottom edge matches the name block and the buttons match the filters. Without a slot nothing moves. Checked in `verify_sponsor_tiers_browser.mjs` by bounding boxes (28 checks), including 390px.
