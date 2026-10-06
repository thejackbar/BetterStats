# Guide: Sponsors (tiers, placements, naming rights, post defaults)

**Read this before**:
- Touching `org_sponsors`, `services/sponsor_tiers*.py`, `GET /clubs/{slug}/sponsors`, `/club-admin/sponsors*`, `AdminSponsors.jsx`, `SponsorFooter.jsx`, `MajorSponsorSlot.jsx` or `useClubSponsors.js`.
- Adding a public club page or changing how a page finds its club (`lib/clubSlug.js`).
- Touching `social/blank-template.jsx`'s `sponsors` block, `services/post_sponsors.py` or the Sponsors tool in `AdminSocialPost.jsx`.

**Archive**: `docs/dev-notes/archive/sponsors-tiers-and-naming.md`. Grep hints: `v9.103.0`, `v9.104.0`, `v9.105.0`.

## Standing rules

1. Four fixed tiers (major, gold, silver, supporter). A club renames them (`organisations.sponsor_tier_labels`) and cannot add or remove one, so placement rules and post defaults can rely on the keys.
2. Where a sponsor shows is DERIVED on read: the tier's default spots with `org_sponsors.placements` (only hand-set switches) applied on top. Never store a resolved list. The spots are `dashboard`, `bar`, `footer`. Unknown tiers and spots fail closed (shown nowhere), never widen.
3. A PATCH `placements` merges over the stored switches: null on one spot drops that switch, the whole field null clears all, absent leaves them alone. A switch set back to what the tier already does is sent as null so the sponsor follows the tier again.
4. The public endpoint returns every sponsor, logo or not. The bottom bar and the dashboard slot draw logos only (`forSpot` skips a sponsor with no logo); the full list names a logo-less sponsor in text. Any other reader of that endpoint (the yearbook does) must filter on `logo_url` itself.
5. Existing sponsors migrated to `silver` (bar and list), so no club's public pages changed on upgrade. Keep that default.
6. The sponsor DDL (`sponsor_tiers_ddl`) is in `cricket_schema_mirror.SHARED_DDL_MODULES`: football's own sponsors router selects the whole `Sponsor` entity, so a column missing there 500s it.
7. A club page with no slug in its URL (`/players/:id`, `/games/:id`) tells the sponsor list its club through `rememberClubSlug(org.slug)`. A new such page must do the same.
8. Every sponsor write needs `MANAGE_SPONSORS` on the server (`require_cap`). The list read stays open because BetterPosts and the setup wizard read it.
9. Section names (`organisations.section_names`) store only what the club set. The sponsor card is resolved live on read; never copy a logo into the column. A new public section needs an entry in `services/section_names.SECTIONS`, its page must call `useSectionNames`, and its nav label must use `sec.name(key, fallback)`. URLs never change with a rename.
10. A renamed page keeps its standard wording when nothing is set: every call site passes the old string as the fallback, so removing a name is a no-op, not a blank.
11. Every BetterPosts post carries a sponsor grid (`sponsors` block). `post_sponsors.resolve` is the one answer for which sponsors: team pin, grade pin, club default (`posts` spot), top sponsor. Never copy that order into the frontend. The editor treats an `auto` grid as the server's choice and a touched one as the user's.
12. Every layout reserves a slot for the grid (`social/sponsorSlots.js`, `SPONSOR_SLOTS` per template file) and the editor places the grid in it. Only the scorecards draw sponsor logos of their own and get no grid (`nativeSponsors`). A new template needs a slot entry and a clear area, or the grid lands on its content.
13. Removing the last sponsor grid from a post must go through `hRemove` (it confirms). A new delete path that calls `layer.remove` directly skips the warning.
14. Prose follows the humanizer rules.
15. A slot function may read `count` when the layout's bar depends on it (T12's white bar is 150, 175 or 235 tall). The editor then passes `sponsorCount` to the layout, and `pickSponsors` re-seats a grid still sitting in the old slot.
16. A slot that depends on an editor choice (the Glass Card's position) gets it as the fourth argument of the slot function via `sponsorSlotFor(..., opts)`; the editor must pass the same `opts` everywhere it seats a grid.
