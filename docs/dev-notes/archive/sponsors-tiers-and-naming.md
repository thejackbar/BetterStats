# Archive: Sponsors (tiers, placements, naming rights, post defaults)

## Sponsor tiers, major slot and full sponsor list (v9.103.0)

Asked for by the club group: more sponsorship spots, tiers, and a full list of sponsors on every page.

- **Model.** Migration 318 (`services/sponsor_tiers_ddl.py`, mirrored in the lifespan and in the football schema mirror): `org_sponsors.tier` (default `silver`), `org_sponsors.placements` JSONB (hand-set overrides only), `organisations.sponsor_tier_labels` JSONB. Defaults: major = dashboard, bar, list; gold and silver = bar, list; supporter = list.
- **Public.** `GET /clubs/{slug}/sponsors` now returns every sponsor tier first, with `tier`, `tier_label`, `placements` and the club's `tier_labels`. `useClubSponsors` shares one fetch between the dashboard slot, `SponsorWall` and the bar.
- **Dashboard.** `PageHeader` takes an optional `aside` (right column, above the actions). `MajorSponsorSlot`: one sponsor large, several in a grid, nothing when none, an add prompt for an admin who can manage sponsors for that club.
- **Every club page.** `SponsorFooter` renders `SponsorWall` above the sticky bar. Player and scorecard pages have no slug in the URL, so they call `rememberClubSlug`, which `SponsorFooter` listens for. Section list extended with fixtures, lineups, teams, premierships, honour-board, ladders.
- **Admin.** Tier select and three spot toggles per sponsor (a star marks a hand-set spot, Reset to tier clears them), tier select on add, a Tier names panel. Server now gates every sponsor write on `MANAGE_SPONSORS`.
- **Verified.** `verify_sponsor_tiers.py` (real Postgres, shipped route bodies, 57 checks; control on the previous commit fails the 11 behaviour checks without crashing) and `verify_sponsor_tiers_browser.mjs` (production build, API stubbed, 23 checks including 390px; control build fails 16 and passes the 7 that should not change).
