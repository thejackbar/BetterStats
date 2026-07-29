# Handoff: BetterPosts editor redesign (BetterSocials → Post Designer)

## Overview

`AdminSocialPost.jsx` has grown from a template picker into a full Canva-class design
tool, and its UI never caught up: Style, Background, Templates, Match Info, Opponent,
Players, per-type data and the Blank Canvas editor are all stacked as sibling cards in
one 500px column, so a user scrolls past six unrelated concepts to change one thing.

This redesign keeps **every existing capability** and reorganises the surface into:

- **one canvas engine** — templates seed movable blocks instead of being static components
- **one left icon rail** (Design · Content · Text · Shapes · Photos · Club data · Brand · Layers)
- **one panel** that changes with the rail
- **one contextual inspector** floating over the canvas for whatever is selected

Plus the new capabilities agreed in review: carousel pages, a reusable club media
library (uploads), a persisted club brand kit, a first-run post picker, and a phone
quick-post flow.

## About the design files

The files in `prototype/` are **design references written as HTML/JS**, not production
code to paste in. They show intended layout, spacing, colour, copy and behaviour.

The task is to **recreate these designs inside BetterStats' existing frontend** — React
18 + Vite + Tailwind with the `pb-*` CSS-variable tokens, `react-router-dom`, and the
existing `frontend/src/social/*` template/canvas modules. Use the codebase's own
patterns (`pb-card`, `font-mono text-[10px] tracking-wide3 text-pb-faint uppercase`
section labels, `Icon` from `pages/admin/betterselect/ui.jsx`, `api` from `lib/api.js`).

`prototype/social-bg.jsx` is **your own `SocialBackgrounds.jsx`** with the `import`/
`export` keywords stripped so it could run in the prototype's bundler-less environment.
Do not port it back — keep using `frontend/src/social/SocialBackgrounds.jsx` as-is.

## Fidelity

**High fidelity.** Colours, type, spacing and copy in the prototype are final and are
listed below. Behaviour (drag, resize, multi-select, undo/redo, page switching, uploads)
is really implemented in the prototype and can be interrogated by clicking around.

Two things are deliberately faked and must be wired to real data:

1. Player photos render as a labelled striped placeholder. Real implementation uses the
   existing headshot URL: `${BASE_URL}/images/players/${p.id}/photo` (see
   `playerToTemplatePlayer` in `AdminSocialPost.jsx`).
2. The media library and brand kit are in-memory. They need persistence (see
   **Backend work** below).

---

## Screens / views

### 1. Start (first run / empty state)

- **Purpose**: answer "what am I posting?" before any canvas appears, so a volunteer
  never lands on a blank page.
- **Layout**: full viewport, `display:flex; flex-direction:column; align-items:center;
  justify-content:center; gap:26px; padding:40px 60px`, background `#0a0d14`.
- **Components**:
  - Module lockup: `bettersocials.svg` at 40×40, `border-radius:11px`; wordmark
    "Better" + `<span style="color:#EC4899">Posts</span>` in Barlow Condensed 800 / 34px;
    subline `Applecross Cricket Club · Heathcote Reserve` in JetBrains Mono 10px,
    `letter-spacing:.12em`, `#5b6072`.
  - Row: "What are you posting?" (Inter 600 / 15px) left; right, mono 9px `#5b6072`
    "EVERY LAYOUT ARRIVES PRE-FILLED WITH YOUR CLUB'S DATA".
  - Grid `repeat(5, 1fr)`, `gap:10px`, max-width 1120px — one card per post type from
    `TABS` in `AdminSocialPost.jsx` (Lineup, Fixtures, Final Score, Results, Player of
    Match, Announcement, Toss, Scorecard, Events, Blank canvas). Card: `padding:10px`,
    `border:1px solid #1d2331`, `border-radius:9px`, background `#10141d`, hover border
    `#EC4899`; 74px thumb (render the real template at scale in production), name Inter
    600 / 12px, count mono 9px `#5b6072` ("4 layouts").
  - Footer strip above a `1px solid #1d2331` rule: "PICK UP WHERE YOU LEFT OFF" + saved
    template chips + primary button "OPEN THE EDITOR →" (`#EC4899` on `#0a0d14`, 34px, mono 10px/700).
- **Routing**: `/admin/social-post` with no query → Start. Choosing a type navigates to
  `/admin/social-post?type=lineup` and mounts the editor. Skip Start when the URL already
  carries a type or template (deep links from the dashboard keep working).

### 2. Desktop editor (the main screen)

Grid: `header 52px` / `rail 74px | panel 306px | canvas flex:1`.

**Header** (`#10141d`, bottom `1px solid #1d2331`, `padding:0 14px`, `gap:14px`)
- Club chip: 26px `#161b27` tile with mono 11px initials + club name mono 9px `#5b6072`.
  In production use `club.logo_url` from `api.adminGetSettings()` with the initials tile
  as fallback (same rule as `ModuleLayout`'s `Brand`).
- Divider `1px × 20px #1d2331`.
- Module lockup — reuse `<ModuleLockup name="BetterPosts" logo={moduleBrand('socials').logo} accent="#EC4899" />`.
- Post-type button: mono 9px "POST" label + current type + `▾`; opens a 460px popover of
  type chips (replaces today's 10-item wrapped tab row).
- Right: undo / redo (`Icon name="reset"`, redo is `scaleX(-1)`) + "N STEPS";
  `SAVE AS TEMPLATE` ghost button; primary export button whose label is
  `↓ DOWNLOAD PNG` or `↓ {n} SLIDES` when the post has multiple pages.

**Rail** (`74px`, `#10141d`, right `1px solid #1d2331`)
- 58px tall buttons, `margin:0 6px`, `border-radius:8px`, icon 18px + mono 8px label,
  `letter-spacing:.1em`. Active: background `rgba(236,72,153,.12)`, colour `#EC4899`;
  idle `#5b6072`.
- Icons come from the app's own kit (`ICON_PATHS` in `pages/admin/betterselect/ui.jsx`):
  Design `overview`, Content `sheet`, Text `list`, Shapes `selection`, Photos `player`,
  Club data `ladders`, Brand `settings`, Layers (pinned to the bottom, after a
  `1px #1d2331` divider) `cols`.

**Panel** (`306px`, `#10141d`) — 44px header with mono 10px title + mono 9px meta, then
a scrolling body with `padding:14px`.

| Rail item | Panel contents | Replaces today |
| --- | --- | --- |
| Design | Layout cards for the active post type (2-col grid) + "Your templates" | Templates card |
| Content | Quick-add row (+ Text / + Image / + Player / + Club data / + Shape), "Images for this post" slots (hero image, player headshot, sponsor logo), then the post type's fields | Match Info, Opponent, Players, per-type data cards |
| Text | Add heading / subheading / body (rendered in their real fonts) + font list | `BlankCanvasEditor` add-buttons |
| Shapes | 3-col grid of the 10 `BLANK_ELEMENTS` with real shape marks | `+ Line`, `+ Box`… buttons |
| Photos | Tabs: **Uploads** (drop zone + club library grid) · **Players** (headshot grid) · **Club** (lockup + sponsor logos) | `+ Image`, `+ Club badge` |
| Club data | Grouped: *From a player profile* (photo, name, stats) · *From the club* (fixtures, results, record, scorecard) | `+ Fixtures`… buttons |
| Brand | Save-to-club banner, crest + sponsors, palettes + custom colours, texture picker, **per-texture colour editor**, headline font, saved looks | Style card (palette + dark/light + font + background + saved designs) |
| Layers | Front-on-top list with grip/forward/back/duplicate/delete + History list | Layers block in `BlankCanvasEditor` |

**Canvas** — centred on `#07090f`, `padding:26px`. Prototype renders 1080 design space at
`scale = 660/1080`; production should fit to the available box (`Math.min(avail/1080, 1)`)
and expose the zoom in the caption. Caption below-left: `1080 × 1080 · 61% · SINGLE POST`
(or `PAGE 2 OF 3 · CAROUSEL`), below-right the hint
`DRAG TO MOVE · SHIFT-CLICK FOR SEVERAL`.

**Page rail** — 84px left of the canvas: mono 8px "PAGES", then 46×46 page chips
(active border `#EC4899`), a dashed `+` (46×30) and a `DUP` button (46×24). A chip beyond
the first carries a 15px `✕` delete affordance at its top-right.

**Inspector** — floats `left:22px; right:22px; bottom:16px`, `padding:9px 12px`,
`border-radius:10px`, background `rgba(16,20,29,.96)`, `border:1px solid #262d3d`,
`box-shadow:0 16px 40px rgba(0,0,0,.5)`, `backdrop-filter:blur(8px)`. Contents by
selection type:

- *text*: font select, size number, **B**, **AA**, align ⇤⇔⇥, 6 token swatches + custom colour
- *image*: Replace, Fit/Fill toggle, colourless
- *element*: token swatches + custom colour
- *data (fixtures/results)*: ROWS number
- *data (player/photo/name)*: PLAYER select (roster)
- always: bring forward / send backward / duplicate / delete / `⋯` more
- `⋯` opens a second row: text → textarea + line-height + letter-spacing + width;
  image → w/h/corner; element → w/h/rotation/opacity; brand → size; all → X and Y.
- With nothing selected the bar is a 46px mono 9px line:
  `SELECT SOMETHING ON THE CANVAS TO EDIT IT`.
- Empty selection state and the `float` vs `dock` placement are both implemented in the
  prototype (a prop) — ship `float`.

### 3. Mobile quick post

390×844. Status row, header (24px lockup + "Quick post", 44px "FULL EDITOR" pill), a
342px live preview, then a `20px 20px 0 0` sheet with three numbered steps —
**1 · WHAT IS IT** (scrolling type pills, 44px min height), **2 · THE DETAILS** (up to
three 44px inputs; on the freeform canvas these edit the first three text blocks),
**3 · THE LOOK** (44px palette swatches) — and a sticky footer: `SAVE DRAFT` ghost +
`↓ SAVE TO PHONE` primary, both 48px.

No dragging on mobile by design. Route it as a viewport-driven variant of
`/admin/social-post` (`md:` and below), not a separate URL.

---

## Interactions & behaviour

- **Select**: pointerdown on a block selects it; shift/ctrl/meta toggles into a
  multi-selection; pointerdown on empty canvas clears. Selected block gets
  `outline: 2px solid palette.accent` with `outline-offset: 4px` (divide the outline
  width by the canvas scale so it stays 2 screen px, as `BlankCanvas` already does).
- **Move**: dragging any selected block moves the whole selection; deltas are divided by
  the canvas scale so movement tracks the cursor 1:1 (existing `BlankCanvas.beginMove`).
- **Resize**: 18px accent handle bottom-right of a single selection; text/data resize
  width only, images keep aspect, elements free, brand scales `size` (existing
  `beginResizeSingle`). Multi-selection keeps the existing group handle.
- **Keyboard**: Delete/Backspace removes the selection; ⌘/Ctrl-Z undo, ⇧⌘Z redo. Ignore
  when focus is in an input/textarea/select.
- **Undo/redo**: snapshot the live page's item array before every mutation; 40-deep.
  Drag and resize push one snapshot on pointerup, not per move.
- **History list**: last 8 labelled actions in the Layers panel, newest first, highlighted.
- **Pages**: switching stashes the live items and loads the target page's; undo history is
  per page (reset on switch). Export walks every page.
- **Uploads**: file input (multi) → `URL.createObjectURL` for instant preview, upload in
  the background, then swap the block's `src` to the stored URL. Clicking a library asset
  with an image block selected replaces its source; otherwise it adds a new block.
- **Brand kit**: any edit marks it dirty (`SAVE TO CLUB` turns accent); saving persists
  and returns it to `SAVED TO CLUB`.
- **Texture colours**: overrides are keyed by texture, so switching textures and coming
  back keeps them; `RESET TO CLUB` deletes that texture's override (same semantics as
  today's `bgColors` state and "Reset to club colours" button).

## State management

Keep the existing hooks — `useBlankLayer` for items/selection and `AdminSocialPost`'s
existing state for templates, palette, background and per-type data. Add:

```js
screen        'start' | 'editor'              // derived from the URL, not stored
tool          'design'|'content'|'text'|'elements'|'photos'|'data'|'brand'|'layers'
advOpen       boolean                          // inspector's ⋯ row
pages         { store: {idx: items[]}, idx, count }   // carousel
uploads       MediaAsset[]                     // from the API
photoTab      'uploads' | 'players' | 'club'
brand         { crest, colours, headlineFont, bodyFont, sponsors[] }
brandDirty    boolean
bgColors      { [textureKey]: {primary,secondary,tertiary,paper,ink} }  // already exists
history       { past: items[][], future: items[][], log: {label,t}[] }
```

New item kinds on top of `newBlankItem` in `frontend/src/social/blank-template.jsx`
(see `skeleton/blank-template.additions.js` for drop-in code):

```js
{ type:'data', kind:'playerphoto', x,y,w:460,h:620, playerId, fit:'contain' }
{ type:'data', kind:'playername',  x,y,w:900,h:260, playerId, showRole:true }
```

`kind:'player'` already exists (stat tiles) — it should read the same `playerId` so one
picker drives photo + name + numbers.

## Design tokens

Chrome (all already in `styles/theme.css` / `tailwind.config.js` — use the tokens, not the hex):

| Token | Value | Use |
| --- | --- | --- |
| `--pb-bg` | `#0a0d14` | app background |
| `--pb-surface` | `#10141d` | header, rail, panel |
| `--pb-surface2` | `#161b27` | inputs, cards, chips |
| `--pb-hairline` | `#1d2331` | dividers, card borders |
| `--pb-hairline2` | `#262d3d` | control borders, inspector border |
| `--pb-text` | `#e6e8ef` | primary text |
| `--pb-dim` | `#8a90a2` | secondary text |
| `--pb-faint` | `#5b6072` | mono micro-labels |
| `--pb-faintest` | `#3a3f50` | captions, disabled |
| module accent | `#EC4899` (`moduleBrand('socials').accent`) | active rail, primary button, selection UI |
| canvas well | `#07090f` | area behind the post |
| danger | `--pb-red` `#ef5b5b` | delete hover |

Post palettes (unchanged, from `PALETTES` in `social/cricket-templates.jsx`): midnight
`#0b1530/#1a2647/#ffc233`, crimson `#2a0a0e/#5a0f1a/#ff3344`, forest `#0c2418/#163828/#c4ff4d`,
cobalt `#0b1f4a/#17336b/#00c2ff`, rust `#1e0f08/#3a1a0a/#ff7a1a`, graphite
`#101113/#1d1f23/#e8ff00`, plus Club (`orgToPalette`) and Custom.

Texture colours derive from the palette exactly as today's `paletteToBgColors`:
`primary = palette.primary`, `secondary = palette.accent`,
`tertiary = rotateHue(palette.accent, 35)`, `paper = '#ece4d3'`, `ink = palette.ink`.

Type: **Barlow Condensed 800** for the wordmark and club lockup; **Inter** 11–15px for
UI prose; **JetBrains Mono** 8–10px uppercase with `letter-spacing:.06–.14em` for every
micro-label (matches `font-mono text-[10px] tracking-wide3` in the codebase). Canvas
fonts are unchanged (`BLANK_FONTS` / `DISPLAY_FONTS`).

Radii: 5–6px controls, 7–9px cards, 10px inspector, 12px mobile buttons, 22px pills.
Spacing: 6 / 8 / 10 / 14 / 18 / 26px. Shadows: canvas `0 24px 60px rgba(0,0,0,.55)`,
inspector `0 16px 40px rgba(0,0,0,.5)`, popover `0 20px 50px rgba(0,0,0,.6)`.
Hit targets: 28px desktop controls, **44px minimum on mobile**.

## Assets

- `prototype/bettersocials.svg` — copied from `frontend/src/assets/modules/bettersocials.svg`; already in the repo.
- Icons — `ICON_PATHS` / `<Icon>` in `frontend/src/pages/admin/betterselect/ui.jsx`. Names
  used: `overview, sheet, list, selection, player, ladders, settings, cols, reset, trash,
  grip, chevron, arrow, filter`. Nothing new was drawn.
- Textures — `frontend/src/social/SocialBackgrounds.jsx` (18 variants + shared filter
  defs). Mount `<SocialBackgroundDefs />` once, as today.
- Club crest / sponsor logos / player headshots — existing uploads and
  `${VITE_API_URL}/images/players/:id/photo`.
- No new imagery was created; every placeholder is a striped `repeating-linear-gradient`
  with a mono caption.

## Frontend work plan

`AdminSocialPost.jsx` is 2,833 lines. Split as you go — the redesign maps cleanly onto it:

```
frontend/src/pages/admin/AdminSocialPost.jsx        keeps all data/state, renders the shell
frontend/src/components/admin/socialpost/
  PostEditorShell.jsx      header + rail + panel + canvas + inspector grid
  ToolRail.jsx             ← skeleton/ToolRail.jsx
  PageStrip.jsx            ← skeleton/PageStrip.jsx
  SelectionInspector.jsx   ← skeleton/SelectionInspector.jsx
  MediaLibraryPanel.jsx    ← skeleton/MediaLibraryPanel.jsx
  panels/DesignPanel.jsx   template cards + saved templates (from the Templates card)
  panels/ContentPanel.jsx  quick-add + image slots + the per-type field groups
  panels/TextPanel.jsx     add-text presets + font list
  panels/ShapesPanel.jsx   BLANK_ELEMENTS grid
  panels/ClubDataPanel.jsx BLANK_DATA grouped player/club
  panels/BrandKitPanel.jsx palette + textures + texture colours + fonts + crest/sponsors
  panels/LayersPanel.jsx   layer list + history
frontend/src/social/
  blank-template.jsx       + playerphoto / playername kinds  ← skeleton/blank-template.additions.js
  useBlankLayer.js         unchanged
  usePages.js              new  ← skeleton/usePages.js
  useEditHistory.js        new  ← skeleton/useEditHistory.js
frontend/src/lib/api.js    + media library + brand kit calls
```

Suggested order: (1) shell + rail + panels with existing state — pure reorganisation, no
new behaviour; (2) inspector + delete the per-property list from `BlankCanvasEditor`;
(3) history hook; (4) player data blocks; (5) pages; (6) media library (needs backend);
(7) brand kit (needs backend); (8) Start screen; (9) mobile.

Steps 1–5 and 8–9 are frontend-only and can ship before any backend work.

## Backend work (new — needs your call)

Both of these are proposals; nothing in the repo covers them yet.

**Media library** — a club-scoped image store so uploads are reusable.
- `alembic` migration: `social_media_asset(id, org_id, filename, mime, bytes, width, height, storage_key, created_by, created_at)`.
- `backend/app/routers/social_media.py`: `GET /social/media`, `POST /social/media`
  (multipart, reuse the existing image upload/validation path used for player photos and
  sponsor logos), `DELETE /social/media/:id`. Cap size/count per club.
- `api.js`: `listSocialMedia()`, `uploadSocialMedia(file)`, `deleteSocialMedia(id)`.

**Brand kit** — currently palettes/designs/templates live in `localStorage`
(`bs_social_palettes`, `bs_social_designs`), so they don't follow a volunteer to another
device and can't be shared.
- Either extend org settings with a `social_brand_kit` JSON column, or add
  `social_brand_kit(org_id PK, crest_asset_id, colours, headline_font, body_font, sponsors, updated_at)`.
- `GET/PUT /social/brand-kit`; migrate existing `localStorage` designs on first load.
- Saved templates and carousel page sets want the same treatment
  (`social_post_template(org_id, name, template_id, style, pages jsonb)`).

**Export** — `exportNodeToPng` handles one node. For carousels, loop the pages and
either download a zip or sequential PNGs; keep the hidden full-size render node per page.

## Files in this bundle

```
README.md                              this document
prototype/BetterPosts Editor.dc.html   the interactive prototype (all three screens;
                                       switcher bottom-right: START / DESKTOP / MOBILE)
prototype/social-bg.jsx                your SocialBackgrounds.jsx, de-ESM'd for the prototype
prototype/bettersocials.svg            module mark (already in the repo)
skeleton/ToolRail.jsx                  rail, in codebase conventions
skeleton/PageStrip.jsx                 carousel page rail
skeleton/SelectionInspector.jsx        contextual inspector (replaces BlankCanvasEditor's property list)
skeleton/MediaLibraryPanel.jsx         uploads / players / club media panel
skeleton/usePages.js                   carousel page state
skeleton/useEditHistory.js             undo/redo + action log
skeleton/blank-template.additions.js   playerphoto + playername item kinds and renderers
```

The `skeleton/` files are written against this codebase (Tailwind `pb-*`, `Icon` from
`betterselect/ui`) and are meant to be dropped in and wired up — but they are starting
points, not finished components: they assume the props listed at the top of each file.
