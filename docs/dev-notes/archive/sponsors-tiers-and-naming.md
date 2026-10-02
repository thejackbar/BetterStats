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
