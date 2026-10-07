# Guide: BetterPosts editor, template layouts, club fonts and theming, instructional videos

**Read this before**:
- Editing `frontend/src/social/` (`*-templates.jsx`, `postSizes.jsx`, `postAspect.js`, `postLayers.jsx`, `useBlankLayer.js`, `templateToBlocks.js`) or `AdminSocialPost.jsx`; adding a template; changing post sizes, the Layers panel, Preview, Save as template or Save to Club Room.
- Changing club typography or theme: `lib/theme.js` (`buildThemeCss`, `onAccentInk`), `services/fonts.py`, `settingsKit.jsx`, `--pb-on-accent`, `--pb-weight-*`, `public_header_logo`.
- Touching `/videos`: `routers/instructional_videos.py`, `services/instructional_videos.py`, `lib/videoModule.js`, nginx `/_internal_videos/`.
- Symptoms: smeared club font, unreadable text on an accent button, exported PNG shaped unlike the preview, Layers rows reading `Ni`, videos 404, `HEAD` 405, a new route firing `/api/clubs/<slug>`.

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/betterposts-socials-and-media.md`. Grep hints: `4:5`, `postPages`, `templateToBlocks`, `share(`, `postAspect`, `roundScale`, `LayerRoot`, `displayName`, `font-synthesis`, `on-accent`, `public_header_logo`, `X-Accel-Redirect`, `Range: bytes=0-`, `mkstemp`, `MARKETING_PATHS`, `video_accel_location`, `videoModule`.

**Related guides**: Playwright browser-suite guides (control-run traps); marketing-site guide (route lists, OG cards); settings/theming guide (`theme_config`); deploy/ops guide (nginx, backups, mounts).

## Standing rules

**Canvas size and export**
1. Every built-in template is a hardcoded 1080x1080 div of absolutely-positioned children. `social/postSizes.jsx` owns the size maths and is used by the live canvas, the mobile preview AND the off-screen export node. Keep ONE `W`/`H`; `handleExport`, `handleSaveToClubRoom` and the preview close over it. A second copy is how a downloaded PNG comes out a different shape from the preview.
2. `postPages` is the one list of what a post is (blank carousel, derived roundup pages, scorecard's two squares, single post). Export nodes and the Preview overlay both map it. Do not write a second branch for either.
3. The blank canvas is genuinely portrait: its blocks carry their own x/y, so it is not framed (`framed = !isBlankTab && (W !== nativeW || H !== nativeH)`) and `BlankCanvas` gets the real width/height.
4. Scorecards (SC1-SC3) keep their own fixed 1920x1080 via `PostFrame` / `tmpl.fixed`, and are offered no size picker (they have their own Instagram-squares reframing). Their square-split variant is deliberately NOT a `LayerRoot`: two roots with colliding structural ids would apply one stack's order to the other.
5. Fit/Fill is gone, not hidden (every layout is native, so the control was unreachable). Letterbox bands, if `PostFrame` is used, are the club's primary, never `#080808`.

**Reflow and portrait design (`postAspect.js`)**
6. All three sizes are 1080 wide, so the job is where the extra HEIGHT goes. Use `postAspect.js`, never a private breakpoint: `aspectOf`, `pick(A,{square,portrait,story})` (falls back square, portrait, story), `share(h, at1080)` (keeps a band's share), `grow(h, at1080, rate)` (keeps pixels, adds a fraction of the extra), `type(h, at1080)`.
7. `grow` for chrome (masthead, footer), `share` for structure (photo bands). `share` on a 150px footer balloons it to 267 on a story; `grow` on a 680px photo band leaves it a third of the post.
8. Every primitive is exact at 1080 by construction, but that is necessary, not sufficient. The square must keep its ORIGINAL anchoring: use `anchor(A, sq, tall)` in round-templates and a plain `A === 'square' ? ... : ...` elsewhere, so only a taller canvas stretches. (15 of 48 squares moved before this was measured.)
9. `top: X, height: Y` becomes `top: X, bottom: 1080-X-Y`: byte-identical at square. A fixed-height child in a now-taller box (cut-out headshots in T7/C3/C1) must be derived from the canvas (`height - 360` / `- 320` / `- 260`), which evaluates to the old literal at 1080.
10. `roundScale()` is the one design scale for the 19 roundup templates (`head()`, `foot`, `row`, `big`, `sz(mult)`). Row type steps up with its slot; panels that stopped where the square ended run to the footer (flex column).
11. On a story, centre content: the app's reply bar and profile row cover the edges. Extra height buys more LINES, not more air (`space-evenly` on T9 was worse). Grids re-compose (T2/C1 4x3 to 3x4).
12. `AutoFitText` measures the tighter of the node's own box and the parent's `clientWidth` (includes padding). `round-templates`' own `AutoFit` has the same line; keep both in step.
13. Never claim "square posts are unchanged" on arithmetic alone. Shoot `SIZES=square` on both builds and `cmp`. Intentional square changes: T4 and T9 (already broken); T5 and C2 sub-pixel.
14. EV2's square panel has always clipped; its share behaviour is gated on `aspectOf(...) !== 'square'`. Leave it unless asked.
15. Grep new templates for hardcoded 1080 `<svg>` backgrounds (T3 had one).

**Layers**
16. A layout is layered, not decomposed. `LayerRoot` (in `postLayers.jsx`) replaces each template root `<div>`; every root child becomes an addressable layer with a z-index and a name. With no order, nothing hidden and no blocks it returns the exact div as before (no cloning, no z-index, no stacking context); all 48 verified byte-identical at square and portrait.
17. New template roots must be `<LayerRoot style={{...}}>`. The roundup `Post` shell covers 19; cricket, event and launch roots are individual. `FRAME` in `event-templates` is a style helper, not a component.
18. Layer identity is structural (`t:div#2`: type plus nth of that type), never the text. Use `data-layer` on a conditionally-rendered root child, because `Children.toArray` drops unrendered children and shifts everything after.
19. Natural order is DOM order sorted by existing z-index (T1's badge has `zIndex: 5`). The background is the floor (`isolation: isolate`), not a layer.
20. The stack is a preference: `applyOrder` keeps ids somebody has an opinion about and drops the rest at their natural index. Layer state carries its template id and a mismatch is resolved during RENDER, not in an effect (an effect wipes a just-restored saved design). A saved template keeps its stacking.
21. Blocks render as runs between the layout's own elements (one `BlankCanvas` per run). Every run is `passThrough`; blocks re-arm `pointer-events: auto`. Only the interactive canvas passes `register`; `hover` never reaches export.
22. `scale` is local to `renderCanvas`: pass it as an argument (a closure gives `ReferenceError` inside the template render).
23. `Icon` draws an empty SVG for a name not in `ICON_PATHS` (no error). Add glyphs first.
24. A component child takes a z-index only if it spreads `style` (`GrainSVG` did not). Layer labels come from the `FRIENDLY` map keyed on an explicit string `displayName` on every primitive (minified builds mangle `Component.name` to `R`, `ni`, `Ni`). Any new primitive needs one.
25. `EV5` and `EV8` keep everything in one inset frame (one or two layers, named `Poster content`). Do not descend into it: the `inset` would offset dropped blocks.
26. The old two-position `behind` flag, `setBehind`, `reorder`'s `crossLayout` and `.pb-template-seethrough` are retired. An item saved with `behind` is ignored.
27. `templateToBlocks` still only decomposes C1-C4 (Custom Edit). Extending it would destroy AutoFitText sizing, role chips and portrait designs, so do not.

**Editor UX**
28. `ImageEditorModal` (AI cut-out, colour key) opens from the hero photo, sponsor logos, an image block's REPLACE, an image on the post and any club-library tile. A library edit is stored as a NEW asset, never overwriting (the original may be on an un-reexported post).
29. "Save to Club Room" renders a PNG into the TV slideshow media pool; "Save as template" writes a `bs_social_templates` localStorage row (Design, Your templates, that browser only). Both must say where the thing went.
30. A control that is correctly absent must explain itself: the Hero Image panel (seven layouts) names them off the same id list.
31. The editor must honour `?template=` (the start screen read it and the editor ignored it).

**Club fonts and colour**
32. A font FILE holds one weight unless variable. `services/fonts.describe_font` reads the upload (sfnt; `.woff` per-table zlib; `.woff2` tag directory only, no brotli) and stores `metrics` on the `font_config` role entry. `buildThemeCss` emits `font-synthesis: none` when any role cannot really bold. No `metrics` (pre-existing upload) is treated as single weight.
33. Five presets are `oneWeight: true` (anton, bebas, archivo_black, abril, bungee) in `lib/theme.js`. Keep flags in step with the Google Fonts `<link>` in `index.html`: adding a family without a weight range means adding the flag.
34. Weights come from `--pb-weight-display|body|mono` via `.pb-heading` / `.pb-figure` (`PageHeader` h1, `Kpi`), not `font-bold`. `buildWeightCss` emits `.font-display.font-bold {..}` (two classes beat a Tailwind utility) scoped to the club's display or mono font.
35. `--pb-on-accent` is the ONE answer for text on an accent fill (default `#08110b` in `theme.css`, per club from `onAccentInk`: white or near-black by WCAG contrast). Never hardcode a hex or `text-pb-bg` on a `var(--pb-accent)` fill. The admin app uses its own `ON_ACCENT` (`components/admin/ui.jsx`), correct there because that surface is BetterCricket amber.
36. `organisations.public_header_logo` (migration 226) puts the crest BESIDE the club name in `PageHeader` (the real `<h1>` stays). Opt-in. Read it from the `/clubs/{slug}` payload, not `/organisations/{id}`.
37. No italic toggle (faux-slant risk). A club wanting real bold or italic uploads that file for the role.

**Instructional videos (`/videos`, migration 280, super-admin managed)**
38. `instructional_videos` is the record (no checked-in `data/videos.js` / `content/videos.py`). `og_preview` and `seo` read the TABLE.
39. Video file lives on the media volume (`/mnt/media/bettercricket/internal/videos`, explicit host path, never a named volume); poster is a column (~100KB). Cap 512MB. Files are DELIBERATELY outside the regular backup (per direct instruction; `ops/backup/backup.sh` says so). So: `file_present` on every payload, page says "not on the server", download link withdrawn, super admin sees a re-upload count, `orphaned_files()` finds leftovers.
40. The X-Accel hand-off is opt-in (`video_accel_location`, default empty). nginx opens the file, so the directory must be mounted into the FRONTEND container too. Missing mount signature: every video 404s with `Server: openresty` and the app's `cache-control` attached, while `GET /public/videos` says `file_present: true`.
41. Never return a whole video in one response. Every 206 is clamped to `CHUNK_BYTES` (2MB), because Chrome opens with `Range: bytes=0-`. A short 206 is legal. A download with no Range header must be the full file (`FileResponse`), never a 206 (`curl -O` truncation).
42. Both public file routes are `api_route(..., methods=["GET","HEAD"])` (FastAPI adds no HEAD; 405 on `curl -sI`). HEAD answers the WHOLE file's size, no body.
43. Stored filename is `<row uuid>.<ext>`; `_SAFE_FILENAME` refuses anything else on the way out (uploaded name is for the download header only). Upload streams to disk (`_check_size` seeks, never `len()`), temp file in the same dir then `os.replace`. `mkstemp` is 0600 and `os.replace` keeps it: chmod 0644 before rename (host copy-back, nginx workers). A failed insert deletes its file.
44. Slug is derived once and never moves on retitle; duplicate title gets `-2`. `update_video` writes only PRESENT fields; api.js omits a null rather than sending it empty.
45. Thumbnail is captured in the browser (canvas at ~1.5s, JPEG posted with the upload), best-effort, no ffmpeg. nginx caps `/api/` at 20m; the 512m raise is on a longer-prefix location for `/api/club-admin/super/videos` only, with `proxy_request_buffering off`. Do not raise it globally.
46. Server is the gate: every write is `require_super_admin`; `useVideos.canManage` only decides what is drawn.
47. The CTA follows the video's module (`lib/videoModule.js`): BetterStats keeps `/features`, others `/modules/{slug}`; unknown or empty gets the generic pitch, never a guess. The module field is a picker (it decides a destination); matching ignores case and spacing; an unknown stored value stays as its own option.
48. A new top-level marketing route is a club slug until four lists know it: `og_preview.RESERVED_ROOT_SEGMENTS`, `FaviconManager.RESERVED_ROOTS`, `SponsorFooter.RESERVED_ROOT_SEGMENTS`, `lib/marketingPaths.MARKETING_PATHS`. Missing the last stacks the club Navbar over `MarketingNav`. Symptom: `/api/clubs/<route>` 404 on every visit.
49. A sixth top-level nav link overflows at 820px; `Videos` carries `wide` (`hidden lg:block`).

**Team of the week (v9.102.0, `social/totw-templates.jsx`, `social_rounds.social_totw`, `GET /admin/social/totw`)**
50. The team lives in `selectedPlayers` (each slot carries `totw: {line, grade, opp, points}`), so add, remove and reorder are the lineup's own. The stepper reads `selectedPlayers.length` and never rebuilds from the ranking: growing appends the next ranked players not already picked, shrinking drops from the end, so a hand swap survives. Size is 6 to 14, default 11 (`TOTW_MIN/MAX/DEFAULT`).
51. Scoring is `_rank_our_side`, the one function behind both the player of the match and the team of the week; change points there and both move. The pool is one entry per player (their better performance, not a sum, so the pick does not go to whoever played most). A layout that takes a variable count sizes cards and rows from the count; root children that are not `div`s must spread `style` to take a z-index, so masthead and footer are plain functions returning a `div`.
52. A saved event template with no `event` field is a pre-v9.99.3 one (layout only). `applyTemplate` starts it from the `EVENT_PRESETS` entry that owns its layout and clears the photo, because the editor's event state defaults to Curry Night and is not persisted. Any new field a template should carry needs the same "absent means legacy" branch.

**Split Poster, debut tags and the hero-row mark (v9.102.16, `social/split-template.jsx`, `services/social_debuts.py`)**
53. A debut is "nothing on record before the match date", read from appearances, batting and bowling lines (abandoned games excluded) and EARLIER seasons' summaries only, scoped by `players.organisation_id`. It is a suggestion: `sp.debut` is the admin's to flip, and an id the club cannot answer for is left as it was.
54. A new tag or option on a lineup layout is a prop that is absent when off, so a post without it stays byte for byte what it was (compare `outerHTML` against the previous build). Where a row's base style uses the `padding` shorthand, override the shorthand, never add a longhand beside it. Hooks for the editor go with the other state, above every early return (React #310).
55. `matchData` fills an empty competition with the literal `COMPETITION`, so a layout that should print nothing there must treat that literal as empty. Lineup loaders put the grade in `match.competition`. A background variant's Ink role is the palette's ink (white on the built-in palettes), so use Primary for any shade that has to stay dark.

**Final Score from the Games page (v9.105.3, `socialpost/ClubGamesPicker.jsx`)**
56. The picker lists what `GamesPage` lists (`getOrgSeasons`, `getOrgResults`) and hands `games.id` to `loadResultMatch`; do not give it a second list or route it through `match-lookup`. The scorecard import is live Cricket Australia only, so a manual or scorebook-imported game on that list answers "Scorecard not found" until a DB fallback exists (see Open follow-ups).

**Sponsor slots (v9.106.0, `social/sponsorSlots.js`)**
56. Every layout reserves a slot for the sponsor grid and exports it in its file's `SPONSOR_SLOTS`; the layout calls the SAME function to keep that rectangle clear. A new template needs an entry and a clear area, or it gets the generic bottom band over its own content. Slots must work at square, portrait and story and read the sponsor `count` only when the shape really differs.
57. Check a new or changed layout with `verification/shoot_sponsor_slots.mjs` at `SPONSORS=1|2|3`: any `OVERLAP` line is text or a picture under the grid. Read the PNGs, the contact sheet is blank.
58. Only the scorecards (SC1 to SC3) still draw sponsor logos of their own (`nativeSponsors`). The roundup `SponsorFooter` is a credit-only strip; do not draw logos in a layout as well as reserving a slot.
59. Scorecard rows are sized from the panel's real height (`_scRowFont`), not a constant. A changed panel height needs its `panelH` passed in. The split squares are native to a 1080 canvas: never frame them.

**Match Day Card (T12, v9.106.32, `social/lineup-card-template.jsx`)**
60. The card's look (photo, wash, corner, panel, logo) is the club's default in `socials_style.lineup_card`. A new key in that blob must be on `_SOCIALS_STYLE_KEYS` (the server strips the rest), in `DEFAULT_STYLE_JSON` in snapshot key order, and in the applied-style normaliser. Empty colours mean "derive from the accent", never a stored hex.
61. Its sponsor bar is as tall as the logo count needs, so the slot takes `count` and the editor passes `sponsorCount`. Zero logos draws no bar. A root child that is an SVG must be the element itself (a plain function, not a component) or the Layers panel loses its `data-layer`.
62. Measure anything the canvas and the export node must agree on (logo ratio) in the editor and pass it down, and give a list one shared type size rather than fitting each row alone.

63. A layout reads the club font from `--social-display-font` and `--social-display-font-weight`, never a hard-coded family. Text fitted by `AutoFitText` does not re-fit when the face changes: hand it a font signature in `measureDeps`. A size measured from the room beside a column must not feed back into that column's width (React #185).
64. A layout that draws the sponsor bar itself marks the slot `layoutBacked: true` and reads the block's `panel` as the bar's colour (`sponsorPanel`); the grid then draws no box of its own.

**Glass Card (RS7, v9.106.36, `social/result-glass-template.jsx`)**
66. Glass is a blurred COPY of the photo (`filter: blur`, `mask-image`), never `backdrop-filter`: modern-screenshot does not paint it. Check a layout like this by downloading a real PNG, not by reading the preview.
67. A slot that moves with an editor option takes it as `opts` (`sponsorSlotFor(id, w, h, count, opts)`), and every call site passes the same `slotOpts`. Position changes re-seat a grid still in its old slot. A layout whose widths change with an option must pass that option in `AutoFitText` `measureDeps`, or the text keeps the old fit.
68. A browser check about a layout's card (overlap, clipped, clear of) must require the card to be drawn, or it passes on the control run.

**Card layouts: Round Cover T13, Giant Type C5, Highlights Cover RS8 (v9.107.0, `social/card-kit.jsx`)**
69. They are portrait-first card layouts built from the club's own graphics. Colours come from the palette (`primary` card, `secondary` glow, `accent` headline, `ink` type) and `glowColor` falls back to a deep shade of the accent when `secondary` is a near-grey, so the default club palette is never a flat slab. Fonts come from `--social-display-font`. Nothing is Scarborough-specific.
70. The shared drawing parts in `card-kit.jsx` are plain functions that return the element, so each root child carries its own `data-layer`. No `backdrop-filter` anywhere: glass panes are a plain tint, because the PNG export does not paint it. Masks, `-webkit-text-stroke`, repeating gradients and quarter-turn text were checked in a real downloaded PNG and survive.
71. T13 and RS8 reserve their sponsor slot (`roundCoverSponsorSlot`, `highlightsSponsorSlot`) in their own files, and the layout reads `sponsorCount` to decide whether to keep the room (`count > 0`); the slot function is called with `max(1, count)`. C5 does the same. A new count-dependent slot must also be on the `pickSponsors` reseat list in `AdminSocialPost.jsx`.
72. T13 reads the picture's own shape on load: a tall cut-out is shown whole (`contain`), a wide photo fills its box (`cover`); the framing control still moves it. C5 draws the headline twice, filled behind the player and hollow in front, so a plain photo still reads as designed. C5 reuses the C1 announcement state (`kind`, `headline`, `subheadline`, `playerIdx`) and the C1 hero-mode switch; any `templateId === 'C1'` branch in the editor needs C5 beside it (the fields panel was one).
73. RS8 puts the winner on the top row unless `result.battedFirst` is `'us'` or `'them'`. Nothing sets it yet, because the scorecard import carries no batting order. All three are in `AFL_HIDDEN_TEMPLATES`; RS8 and its tab were already cricket-only.

**Club meeting requests (v9.108.0)**
69. A roster record becomes a lineup slot through `lib/playerAttributes.socialRole`, never a literal comparison against `BAT/BOWL/AR/WK`: the roster holds "All Rounder" and `ALL`. A new place that builds a slot from a roster record calls it.
70. The layouts that print the Headline are `HEADLINE_TEMPLATES`, and the ones that ignore Competition are `NO_COMPETITION_TEMPLATES`, both in `AdminSocialPost.jsx`. Re-prove them with `node frontend/verification/probe_match_info_fields.mjs` (esbuild plus a server render with marker text) whenever a layout is added. A field the open layout ignores must say so on screen (rule 30).
71. A player typed by hand goes through `POST /club-admin/players/similar` first and is only created when the admin says it is new (`services/similar_players`, read-only, own club, never a privacy-hidden person). A new player-minting screen reuses it rather than calling `POST /players` blind.
72. The event poster in progress lives in `bs_social_event_draft` and in saved templates as `event` (`facts`, `preset`, `motif`, `motifIcon`, `list`, `bg`, `bgOpacity`). A new event field joins all three (state initialiser, draft writer, template save and apply) or it is lost on a reload. Absent means legacy.
73. Event list layouts (`EL1` to `EL3`, `social/event-list-templates.jsx`) are given prepared items (`prepareEventList`), never raw ones. Their body is sized from `headingH`, not a guessed constant. At most `MAX_LIST_ITEMS` (8).
74. Icon search goes through our server only (`services/icon_library.py`): licence-safe sets, cached, paced, SVG refused if it carries script or an external reference. The post stores a data URI. A new outbound call to Iconify, or a new set, goes through `SETS` and the sanitiser. Sets with an attribution condition (CC BY and similar) are not added.

## Traps and failure signatures
- Geometry checks pass but a layout reads wrong (black bands, clumped story names). Judge from real screenshots.
- Hero layouts show a crest, not the cut-out: harness roster stubbed `photo_url: null`. Stubs must cover every conditional's data (give players a photo and a route for it).
- Layers panel of two-letter labels only in the production bundle: `Component.name` mangled. Sweep every template's labels on a PRODUCTION build, not the dev server.
- Smeared font: synthesised bold on a one-weight file. Near-black button text on a navy or maroon club: hardcoded ink on `--pb-accent`.
- `npx vite build | tail -2` reports a failed build as success and `vite preview` then serves the OLD `dist`. Grep output for `built in|Build failed|ERROR`.
- `{/* comment */}` before the element inside a `.map()` arrow return breaks the build (two expressions). Put it above `.map(`.
- Long shoots: serve the production build (`vite preview`, own port); dev HMR kills a run ("Failed to fetch dynamically imported module"), and rebuilding into `dist` mid-run gives chunk 404s.
- `VIDEO_STORAGE_DIR` must be set BEFORE the service module is imported (pydantic-settings reads env once), or test videos land in the real `/mnt/media`.
- Playwright: `Locator.screenshot()` takes no `clip`; a `file://` page cannot `getImageData` a `file://` image (pass a `data:` URL); the suite takes its base URL as `argv[2]` while `shoot_templates.mjs` takes `BASE=` (wrong one gives `ERR_CONNECTION_REFUSED`); scripts must live under `frontend/` and use the pinned `executablePath`.
- `pkill -f` / `pgrep -f` matches its own shell (exit 144): use `pkill -x`, never kill and start in one command. Hung shoot (~6s CPU, no writes) is piled-up Chromium: kill browsers, re-shoot only missing templates.

## How to verify a change here
- Club meeting requests (v9.108.0): `frontend/verification/verify_posts_club_requests_browser.mjs` (base URL as `argv[2]`; wraps each step so a control build reports instead of crashing), `probe_match_info_fields.mjs`, `backend/verification/verify_social_manual_player.py` and `verify_icon_library.py` (the first needs a Postgres, `DATABASE_URL`).
- `frontend/verification/verify_post_designer_browser.mjs` (base URL as `argv[2]`): canvas and export node move together, layout fills the FULL canvas, scorecard keeps 1920x1080, design measurements unchanged at 1080, layer stack read off the OFF-SCREEN EXPORT NODE, saved template through a real reload, no overflow at 390px. Control against the previous commit must fail the reflow, portrait-design and layer sections (framed=true, empty layer list, every z 0, no Send to back).
- Card layouts: `frontend/verification/verify_card_layouts_browser.mjs` (production build, API stubbed; `CUTOUT=` a transparent PNG and `PHOTO=` a JPEG; 147 checks incl. a real PNG download at 2x). Control against the previous commit: 105 fail, and the 36 that pass are guards paired with a positive check. `shoot_card_layouts.mjs` writes a PNG per layout and size; `shoot_sponsor_slots.mjs T13 C5 RS8` at `SPONSORS=1|3` reported 0 overlaps.
- Backend: `backend/verification/verify_instructional_videos.py` (real Postgres, shipped route bodies). `backend/verification/verify_social_totw.py` (team of the week; the control run on the previous commit fails only the two `exists` checks, and its POTM and results digest must match byte for byte). `frontend/verification/verify_totw_browser.mjs` sweeps sizes 6 to 14 on both layouts at all three post sizes for overlap and overflow. `verify_videos_browser.mjs` with `canManage` forced true must fail the gate checks (signed-out and `club_admin` see no controls).
- Harness: address the frame by `data-post-frame`. `backgroundColor` cannot see a gradient: measure BEFORE and AFTER. `display: contents` wrappers have no size: probe through them, and read a `null` as "my selector missed". Keep units consistent in one return object. CSS `uppercase` text returns uppercased from `innerText`.
- Find checks that cannot fail: `comm -12 <(grep ^PASS run.log|sort) <(grep ^PASS control.log|sort)`; anything naming the new feature is a guard or passing for the wrong reason, so make it a contrast gated on the action having landed.
- Control runs must report, not crash: anchor on the export button, read new elements through `textOf`/`seen`/`press`.
- Fonts: check on the club's real site (`VITE_PROXY_TARGET=https://betterat.cricket/api`). Videos: diagnose from response headers and directory modes.

## Operator commands and scripts
- Confirm both mounts before enabling the hand-off: `docker compose exec betterstats-backend ls /mnt/media/bettercricket/internal/videos` and the same on `betterstats-frontend`, then set `VIDEO_ACCEL_LOCATION=/_internal_videos/`.
- After a database restore onto a new box, videos show titles and thumbnails but will not play: re-upload (super admin sees the count); `orphaned_files()` lists strays.
- No scripts owned by this area. Migrations: 226 (`public_header_logo`), 280 (`instructional_videos`).

## Open follow-ups
- Set mode: a team-list set (cover plus one slide per grade) and a highlights set (cover plus photo-only slides) are still one post at a time. The blank carousel and the derived roundup pages are the only multi-slide posts.
- RS8: nothing supplies `result.battedFirst`, so the top row is the winner. Round Cover and Giant Type have no saved club defaults (a club's look is the palette and Brand font only).
- No portrait-NATIVE template variants (a design job per template). Reflow and per-template portrait designs are done.
- A layout's own elements can be reordered and hidden but not moved or retyped (a `transform` offset per layer is the suggested next step).
- Saved templates are still `localStorage` (design handoff proposes `social_post_template`; media library and brand kit already server-side).
- Multi-file drop into the club library uploads as-is (deliberate).
- SC1-SC3 have no portrait design or size picker. EV2's square panel clips; EV5/EV8 hide inner layers.
- Final Score picker: manual and scorebook-imported games have no live card, so the social scorecard 404s for them. Needs a DB fallback adapting `games.get_scorecard` to `{meta, home, away}`.
- Videos: no draft state, no transcoding (`.mov` refused with a message).
- Story slots on some footers sit at the very bottom, not lifted clear of the app's reply bar.

## Flags: conflicting, superseded or possibly obsolete guidance
- [FLAG-POSTS-1] "Only C1-C4 decompose ... 40+ layouts, large work" | wrong for reflow and layering (v9.74/v9.76) but still true for decomposition; `templateToBlocks.js` exists | "A FIXED LAYOUT CANNOT RE-LAY ITSELF OUT AT 4:5" L995-1085 | keep (decomposition only)
- [FLAG-POSTS-2] Fit/Fill picker and `data-post-frame` checks | superseded by v9.74.0; `postSizes.jsx` still exports `PostFrame`/`frameTransform(mode='fit')` for scorecards | same, L995-1085 | verify suite no longer asserts the picker
- [FLAG-POSTS-3] `behind` flag, `setBehind`, `pb-template-seethrough` | retired by v9.76.0; grep of `frontend/src` finds none of them | "Every template reflows..." L1086-1200 | retire (rule 26)
- [FLAG-POSTS-4] Videos section names `MARKETING_PATHS` as the Navbar-suppress list; other archives record a later split into `OWN_NAV_PATHS` (`MARKETING_PATHS` also forces dark theme and `ClubCTABar`) | `lib/marketingPaths.js` lists `/videos` in `MARKETING_PATHS` | "Instructional videos" L10210-10378 | verify before adding any route

## Section coverage
| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| A FIXED LAYOUT CANNOT RE-LAY ITSELF OUT AT 4:5 (v9.73.0), L995-1085 | rules extracted (fit/fill part superseded by v9.74.0) | Rules 1 to 5, 28 to 31; Verify; Open follow-ups; FLAG-POSTS-1, 2 |
| Every template reflows, and a block can go BEHIND the layout (v9.74.0), L1086-1200 | rules extracted; behind-flag design superseded by "Every element of a layout is a layer" | Rules 6, 7, 9, 15; Traps; Verify; FLAG-POSTS-3 |
| A portrait design per template, not a square one stretched (v9.75.0), L1201-1354 | rules extracted | Rules 6 to 15; Traps (vite build, `.map` comment); Verify |
| Every element of a layout is a layer (v9.76.0), L1355-1530 | rules extracted (supersedes v9.74.0 behind flag) | Rules 16 to 27; Traps; Verify |
| A club font with no bold, and ink on a dark accent (migration 226, v9.14.0), L8406-8464 | rules extracted | Rules 32 to 37; Verify (fonts) |
| Instructional videos, managed from the site (migration 280, v9.54.0), L10210-10378 | rules extracted | Rules 38 to 49; Traps (VIDEO_STORAGE_DIR); Operator commands; Open follow-ups; FLAG-POSTS-4 |
| indented: call to action follows the video's module (v9.54.1) | rules extracted | Rule 47 |
