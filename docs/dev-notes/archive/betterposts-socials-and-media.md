# Archive: betterposts-socials-and-media

Verbatim history moved out of `CLAUDE.md` on 2026-09-30. NOT loaded into context automatically.
Scope: BetterPosts editor, template layouts, club fonts and theming, instructional videos.
Read the distilled rules first: `docs/dev-notes/guides/betterposts-socials-and-media.md`. Open this file only when you need the full reasoning, measurements or history behind a rule, and search it (grep) rather than reading it whole.
Sections are in their original relative order. The `BEGIN`/`END` comments carry the line range in the untouched copy `CLAUDE.original-2026-09-30.md`.

<!-- BEGIN original CLAUDE.md L995-1085 -->
## A FIXED LAYOUT CANNOT RE-LAY ITSELF OUT AT 4:5 (v9.73.0, Sep 2026)

Seven questions off the live BetterPosts editor, three of them real gaps and
four of them things that exist and could not be found.

- **EVERY BUILT-IN TEMPLATE IS A HARDCODED `width: 1080, height: 1080` DIV OF
  ABSOLUTELY-POSITIONED CHILDREN**, so "make this 1080×1350" is not a layout
  question — there is no layout to re-run. What a template CAN do is sit inside
  the taller canvas: `social/postSizes.jsx` owns that one piece of maths, used
  by the live canvas, the mobile preview AND the off-screen export node.
  `fit` (whole, letterboxed) is the default because it never loses artwork;
  `fill` scales up and crops, and the panel says the edges go.
- **THE BLANK CANVAS IS THE EXCEPTION AND IT IS GENUINELY PORTRAIT.** Its blocks
  carry their own x/y, so there is nothing to place — `framed` is
  `!isBlankTab && (W !== nativeW || H !== nativeH)`, and `BlankCanvas` is handed
  the real width/height rather than falling back to its 1080 default.
- **THE SAME FORMULA WAS WRITTEN OUT THREE TIMES** — `handleExport`,
  `handleSaveToClubRoom` and the preview each recomputed `tmpl.w || 1080`. Both
  copies are gone; the two handlers close over the ONE `W`/`H`. A second copy of
  the canvas size is how a downloaded PNG comes out a different shape from the
  preview.
- **`postPages` IS THE ONE LIST OF WHAT THIS POST IS**, and the off-screen
  export nodes and the Preview overlay both map it. The four page shapes
  (blank carousel / derived roundup pages / the scorecard's two squares /
  a single post) used to be a four-branch ternary written out once for export
  and would have needed a second copy for the preview.
- **THE LETTERBOX BANDS ARE FILLED WITH THE CLUB'S OWN PRIMARY.** Left at the
  canvas well's `#080808` a fitted post reads as a broken export rather than a
  deliberate portrait one. Found by SCREENSHOTTING the real render, not by the
  geometry checks — which all passed on the black version.
- **A SCORECARD IS NOT OFFERED THE PICKER.** It is 1920×1080 and already has its
  own reframing control (the Instagram-squares split); two answers to one
  question is worse than one.
- **BACKGROUND REMOVAL EXISTED AND ONLY THREE UPLOAD PATHS REACHED IT.**
  `ImageEditorModal` has had an AI cut-out and a colour key since it was
  written, wired to the hero photo, sponsor logos and an image block's REPLACE.
  An image already on the post, and anything in the club library, had no way in
  — which is exactly where somebody who has just uploaded a white-backgrounded
  PNG is standing. Both now open the same editor; a library edit is stored as a
  NEW asset rather than overwriting, since the original may be on a post nobody
  has re-exported.
- **"SAVE TO CLUB ROOM" IS NOT "SAVE THIS DESIGN", AND `✓ SAVED` IS WHAT MADE
  THE TWO READ AS ONE THING.** It renders a PNG into the Club Room TV
  slideshow's media pool; SAVE AS TEMPLATE writes a `bs_social_templates`
  localStorage row that appears under Design → Your templates on that browser
  only. Both now say where the thing went, and the Club Room one links there.
- **A CONTROL THAT IS CORRECTLY ABSENT STILL HAS TO EXPLAIN ITSELF**, the call
  this file already records for a figure that is correctly zero. The Hero Image
  panel is gated on a seven-id list; on every other layout it simply was not
  there. It now names the layouts that have a hero slot, off the same list, so
  the two cannot drift.
- **"SEND THIS IMAGE BEHIND THAT HEADING" IS GENUINELY NOT POSSIBLE ON MOST
  LAYOUTS, and saying so beats a control that looks broken.** Only C1–C4
  decompose into blocks (`templateToBlocks`); everything else takes added blocks
  as an overlay ON TOP, and each template root paints its own opaque gradient,
  so a block behind one would be invisible anyway. The Layers panel says it and
  points at the two ways out (Custom Edit where it exists, else the blank
  canvas). **Extending `templateToBlocks` past four templates is the real fix
  and is a large piece of work — 40+ bespoke layouts, each hand-recreated.**
- **Driven in Chromium** (`frontend/verification/verify_post_designer_browser.mjs`,
  49 checks: the canvas AND the export node moving together, the frame measured
  off the real element at scale 1 / top 135 for fit and 1.25 / left −135 for
  fill, the blank canvas NOT framed, the bands' computed colour, a scorecard
  offered no picker, Preview opening with one page and with two, Escape closing
  it, the editor reachable from a library tile and from an image on the canvas,
  all four explanations, and no overflow at 390px) **with a control run**: 33 of
  the 49 fail against the previous commit, and the 16 that pass in both are
  don't-regress guards.
- **THE FRAME IS ADDRESSED BY `data-post-frame`, NOT BY "an element with a scale
  transform".** The loose selector matched a transform INSIDE a template, so on
  a build with no frame at all the check read the wrong element and reported
  `scale: 1.4` — a measurement of nothing. **And "the blank canvas is not
  letterboxed" is trivially true of a build that never frames anything**, so it
  is gated on the canvas really being 1080×1350 first.
- **A CONTROL RUN THAT CRASHES IS NOT A CONTROL RUN.** The suite anchors on the
  export button (which every build has) rather than on anything this change
  adds, and every new element is read through `textOf`/`seen`/`press`, which
  report absence instead of throwing.
- **THE CSS-`uppercase` TRAP, HIT AGAIN.** The preview header renders
  `2 pages` as `2 PAGES`, so a check written in the source's casing could never
  pass. And `getByText('Club library')` matched three elements — the panel meta,
  the drop-zone copy and the heading.
- **NOTICED, NOT BUILT**: there are no portrait-native template variants — the
  honest fix for a club that wants the full 4:5 filled edge to edge, and a
  design job per layout rather than a code one. Saved templates are still
  `localStorage`, so they do not follow a volunteer to another device (the
  design handoff proposes `social_post_template`; the media library and brand
  kit already went server-side). A multi-file drop into the club library still
  uploads as-is rather than opening the editor per file — deliberate, since ten
  modals for ten photos is worse than the Edit affordance on each tile.

<!-- END original CLAUDE.md L995-1085 -->
<!-- BEGIN original CLAUDE.md L1086-1200 -->
## Every template reflows, and a block can go BEHIND the layout (v9.74.0, Sep 2026)

The two things the v9.73.0 note above listed as NOT BUILT, asked for together:
make the layouts actually fit 4:5 and 9:16 rather than being letterboxed into
them, and let an added image go behind a template's own text.

- **"40+ BESPOKE LAYOUTS, EACH HAND-RECREATED" WAS WRONG, AND MEASURING IS WHAT
  SHOWED IT.** That estimate (this file's own, one release earlier) was about
  DECOMPOSING a template into blocks. Reflow is a far smaller job: **30 of the
  48 templates go through two shared shells** (`round-templates`' one `Post`
  serves 19, `event-templates`' one `FRAME` serves 11), **all three post sizes
  are 1080 WIDE** so the problem is purely vertical, and most layouts were
  already top/bottom-anchored or flex columns. Threading `width`/`height`
  through four files plus a handful of per-template fixes did the whole thing.
- **THE TRANSFORMATION IS `top: X, height: Y` → `top: X, bottom: 1080−X−Y`**,
  which is byte-identical at square by construction and simply gives the box
  the extra room on a taller canvas. That is why the square output needed no
  re-approval: it is the same arithmetic, not a re-design.
- **A STRUCTURAL BAND KEEPS ITS SHARE, IT DOES NOT KEEP ITS PIXELS.**
  `event-templates.share(canvasH, at1080)` — a photo band fixed at 680 is two
  thirds of a square and barely a third of a story, which reads as the design
  falling apart rather than as a taller post. Exact at 1080, so again the square
  is untouched. Six bands across the event posters.
- **A FIXED-HEIGHT CHILD IN A NOW-TALLER BOX IS THE TRAP, and the screenshots
  could not see it.** T7/C3/C1 stand a cut-out headshot on the panel floor and
  let it overflow the top — `height: 720` with the box bottom-anchored. Growing
  the box alone just grows the DEAD AIR above a photo that never followed it.
  Each is derived from the canvas now (`height - 360` / `- 320` / `- 260`),
  which evaluates to exactly the old literal at 1080. **Measured through the
  real editor: 720 / 990 / 1560, 760 / 1030 / 1600, 820 / 1090 / 1660.**
- **THE HARNESS WAS TESTING THE WRONG BRANCH FOR FOUR RUNS.** Its roster stubbed
  `photo_url: null`, so every hero layout rendered its CREST FALLBACK and the
  cut-out never appeared at all — the screenshots showed a crest and I read the
  empty space as a layout question. **A stub whose data misses a conditional is
  worse than no stub**: it produces confident, wrong pictures. Both the shoot
  harness and the suite give their players a photo now, with a route for it.
- **T1 AND T3 NEEDED NOTHING** — their images are `inset: 0; width: 100%;
  height: 100%; object-fit: cover`, which fills any box. Worth checking before
  assuming a photo is broken by a taller canvas; only the fixed-height cut-outs
  were.
- **FIT/FILL IS GONE, NOT HIDDEN.** With every layout native, `framed` is always
  false and the control could never be reached — a control that does nothing is
  worse than none, the call this file already makes for `ageFilterOptions`. The
  `PostFrame` / `tmpl.fixed` escape hatch stays for the scorecards, which keep
  their own 1920×1080 and are still offered no picker.
- **A BLOCK GOES BEHIND BY A FLAG, NOT BY DECOMPOSITION.** `templateToBlocks`
  reaches four templates and extending it would destroy each layout's own
  AutoFitText sizing, role chips and responsive squad logic. `useBlankLayer`'s
  `behind` flag answers the actual complaint — "I can't send the image to the
  back" — on all 48 with no per-template work.
- **ARRAY ORDER IS Z-ORDER, SO THE ARRAY IS PARTITIONED.** Behind-group first,
  front-group second; `setBehind` splices at `behindCount(next)`, which is the
  same index either way because the end of one group and the start of the other
  are the same slot. `moveBefore` carries the destination's own `behind` so a
  drag cannot break the partition.
- **THE LAYOUT STOPS PAINTING ITS OWN BACKGROUND, and only its own.**
  `.pb-template-seethrough { display: contents }` plus
  `> * { background: transparent !important }` — the SHORTHAND, which resets
  `background-image` too, since most of these roots paint a gradient rather
  than a colour. Scoped to the direct child on purpose: a blanket `*` would
  strip every intentional chip and accent bar inside the template, which is
  gutting the layout rather than revealing what is behind it.
- **A BLOCK UNDER THE TEMPLATE CANNOT BE CLICKED unless the template stops
  taking the pointer.** The see-through wrapper is `pointer-events: none`, the
  front overlay layer takes `passThrough`, and each block re-arms
  `pointer-events: auto` — otherwise sending an image back also makes it
  unselectable, which reads as having lost it.
- **Driven in Chromium** (`verify_post_designer_browser.mjs`, 64 checks: the
  canvas and the export node moving together, the layout measured at the FULL
  canvas rather than letterboxed, all three template families filling 4:5, the
  scorecard keeping 1920×1080 and no picker, the cut-out unchanged at 1080 and
  growing at story, a block starting over the layout and moving under it, the
  layout's background measured before AND after, and no overflow at 390px)
  **with a control run**: **17 of the 64 fail** against the previous commit,
  reporting `framed=true`, the Fit/Fill control still present, and
  `["layout","blocks"]` — the block over the layout, which is the reported
  complaint verbatim. The 47 that pass in both are don't-regress guards.
- **`backgroundColor` CANNOT SEE A GRADIENT, and that check was passing for the
  wrong reason.** These roots paint `background-image`, so a gradient-backed
  layout reads `rgba(0,0,0,0)` in BOTH states — "the layout stops painting over
  it" would have passed whether or not anything was suppressed. **Caught by
  adding the BEFORE measurement**, which is the general fix: a check that
  something turned off is worth little without a check that it was on.
- **AND THE PROBE HAD TO DESCEND THROUGH THE WRAPPER.** `display: contents`
  means the see-through div has no width and is not the template root, so
  addressing the layer's direct children found it and measured nothing —
  reported as `null`, which is the shape of a broken probe rather than a real
  failure. Read a `null` from a measurement as "my selector missed", not as
  "the feature is broken".
- **A CONTROL RUN'S DETAIL CAN BE TRUE FOR THE WRONG REASON.** The cut-out check
  fails on the control reporting `44` — the old build does not honour
  `?template=`, so it measured the default template, not T7. A genuine "not
  reachable on the old build" signal, but NOT evidence about the arithmetic;
  that came from the direct measurement above.
- **`?template=` WAS ACCEPTED BY THE START SCREEN AND READ BY NOTHING.** The
  editor skipped its "What are you posting?" screen for it and then opened the
  default template anyway — a real user-facing dead link, found because the
  harness needed it to reach one template per page load.
- **SERVE THE PRODUCTION BUILD, NOT THE DEV SERVER, FOR A LONG SHOOT.** HMR
  reloads on every src edit, and a running shoot then dies with "Failed to fetch
  dynamically imported module". `vite preview` on its own port is immune, and it
  took a 144-shot run from ~30s per shot to a few minutes. **Do not rebuild into
  `dist` while a run is reading it** — that voided one verification pass with
  404s on chunk hashes that no longer existed.
- **A PLAYWRIGHT SCRIPT MUST LIVE UNDER `frontend/`** or it cannot resolve
  `playwright`, and it needs the pinned `executablePath` the suites use.
  `Locator.screenshot()` takes no `clip` — only `Page.screenshot` does. And the
  contact sheet's `file://` thumbnails do not load from an `about:blank` page,
  so read the individual PNGs rather than trusting the sheet.
- **NOTICED, NOT BUILT**: still no portrait-NATIVE variants — a layout that
  reflows well is not the same as one designed for 4:5, and that is a design job
  per template. `templateToBlocks` still reaches four templates, so "edit this
  layout's own text as blocks" is unchanged. Saved templates are still
  `localStorage`.

<!-- END original CLAUDE.md L1086-1200 -->
<!-- BEGIN original CLAUDE.md L1201-1354 -->
## A portrait design per template, not a square one stretched (v9.75.0, Sep 2026)

The thing the note above lists as NOT BUILT, asked for in those words: *"yeh i
want a design per template done please."*

- **REFLOWING AND DESIGNING ARE DIFFERENT JOBS, and the first is what shipped
  last release.** v9.74.0 made all 48 layouts DRAW at 1080×1350 and 1080×1920 —
  boxes grow, nothing overlaps, nothing is letterboxed. It did not make one of
  them a portrait design: a fixture row is 45px of content sitting in a 200px
  slot, a 196px masthead becomes a tenth of a story, and a 150px sponsor strip
  becomes a hairline. That reads as a square with air pushed through it, which
  is the complaint reflow does not answer.
- **ALL THREE SIZES ARE 1080 WIDE, so a design per template is entirely a
  decision about where the extra HEIGHT goes** — which band grows, which type
  steps up, and what has to re-compose rather than stretch. There is no
  re-columning problem to solve.
- **`social/postAspect.js` IS THE VOCABULARY, and a template inventing its own
  breakpoint is what it exists to stop.** `aspectOf` names the shape;
  `pick(A, {square, portrait, story})` falls back square → portrait → story, so
  a template names only the shapes it redesigns for; `share(h, at1080)` keeps a
  band's SHARE; `grow(h, at1080, rate)` keeps its pixels and adds a fraction of
  the extra; `type(h, at1080)` steps type up without tracking the canvas.
- **EVERY PRIMITIVE IS EXACT AT 1080 BY CONSTRUCTION**: `share` is `h*n/1080`,
  `grow` adds `max(0, h − 1080) × rate`, and every `pick` multiplier at square is
  1. **That is necessary and it is nowhere near sufficient** — see the anchoring
  note below, which is what shooting all 48 squares on both builds and comparing
  byte for byte actually found.
- **A PRIMITIVE BEING EXACT SAYS NOTHING ABOUT THE LAYOUT AROUND IT, and 15 of
  the 48 squares moved before this was measured.** Every offending change was
  the same shape: a block the square top-anchored at its NATURAL height turned
  into a stretched box with its content centred or spread. Giving a 300px
  medallion a 420px box and centring it moves it down 60px; re-pinning a block
  from `top: 700` to `bottom: 240` only lands in the same place if its height
  happens to be exactly 140; `space-between` on a panel that now fills the
  column pushes its two halves apart; and `minHeight: 0` on a grid cell lets it
  shrink past its own content, which on EV2's already-overflowing square
  collapsed each cell to its label with the value gone. **`anchor(A, sq, tall)`
  in round-templates and a plain `A === 'square' ? … : …` elsewhere is the fix:
  the square keeps its original anchoring and only a taller canvas stretches.**
- **THE FINAL COUNT IS 44 OF 48 BYTE-IDENTICAL, and the four are named rather
  than rounded away.** T4 (40% of the post) and T9 (10%) changed because their
  squares were ALREADY broken — T4's thirteenth row landed on top of the footer
  and T9's billing ran 76px off the edge — so both are fixes and both are in the
  changelog as such. T5 (3.5% of pixels, no pixel differing by more than 55 of a
  possible 765) and C2 (0.8%, one glyph rasterising 1px taller) are sub-pixel:
  measured, nothing moved.
- **MEASURE THE CLAIM BEFORE YOU WRITE IT.** "Square posts are unchanged" went
  into the changelog on the strength of the arithmetic being exact, and was
  false for 15 templates at the time. The pixel comparison is cheap — one
  `SIZES=square` shoot per build and `cmp` — and it is the only thing that
  turns that sentence from a hope into a fact.
- **A MASTHEAD KEEPS ITS PIXELS AND A PHOTO BAND KEEPS ITS SHARE.** That is the
  whole reason `grow` and `share` are separate: `share` on a 150px footer
  balloons it to 267 on a story, and `grow` on a 680px photo band leaves it a
  third of the post. Use `grow` for chrome and `share` for structure.
- **`roundScale()` IS THE SAME DECISION MADE ONCE FOR NINETEEN TEMPLATES.** The
  roundup family is one shape — masthead, body of rows, sponsor strip — so it
  gets one design scale (`head()`, `foot`, `row`, `big`) and each template
  spends it. `sz(mult)` wraps it so a template still reads as the square sizes
  it was drawn at rather than a column of arithmetic.
- **ROW TYPE STEPS UP WITH THE SLOT IT SITS IN.** The single most visible half
  of this release: a body that absorbs the whole of the extra height gives its
  rows 200px each and then sets them at the size they were in a 60px row.
- **THE PANELS THAT STOPPED WHERE THE SQUARE ENDED NOW RUN TO THE FOOTER.** T4's
  batting order was document flow, so its rows kept their square height and left
  a dead strip; the root is a flex column and the rows share what is left. Same
  shape for T5, and for C4's two top-performer panels, which distribute batting
  and bowling with `space-between` instead of clumping at the top.
- **WHAT RE-COMPOSES RATHER THAN STRETCHING, and each is a real design decision
  rather than a multiplier**: T2 and C1's card grids go 4×3 → 3×4 on a story so
  the cards stay card-shaped instead of becoming letterboxes; T9's support act
  re-sets two names to a line instead of three, so the billing is five lines and
  each name is half as wide again; T1's squad list is set as ONE centred block
  rather than 13 names spread 130px apart.
- **CENTRED, NOT BOTTOM-ANCHORED, ON A STORY.** T1 first anchored its name block
  to the foot of the rail on the reasoning that a phone shows the bottom. That
  is backwards: a story's bottom couple of hundred pixels carry the app's own
  reply bar and its top the profile row, so anything anchored to either edge is
  the half that gets covered.
- **`space-evenly` WAS TRIED ON T9 AND IS WORSE.** Spreading three tiers down a
  story puts 350px between them and the billing reads as three unrelated lines.
  A gig poster's billing is a block; the extra height buys more LINES, not more
  air between the ones you have.
- **AutoFitText MEASURED AGAINST THE PARENT'S `clientWidth`, WHICH INCLUDES ITS
  PADDING.** So a node inside a padded parent was allowed to overflow by exactly
  that padding with nothing detecting it — T9's tiers sat in a `padding: 0 40px`
  box, measured 1076 against a parent `clientWidth` of 1080, and ran 76px off
  the poster at full size. It measures the tighter of the node's own box and the
  parent's now, so a node positioned wider than its parent is still caught. **A
  general bug in a shared primitive, not a T9 one** — the same line is in
  `round-templates`' own `AutoFit`.
- **THE BLAST RADIUS WAS MEASURED BEFORE THE FIX WENT IN.** Probing 12
  templates at square for `scrollWidth > clientWidth` found **zero** overflowing
  nodes, so the change can only ever shrink text that was already clipped and
  the square claim stays honest. A shared primitive is exactly where that
  measurement is worth taking.
- **Three real bugs found on the way, all shipped in v9.74.0's reflow**: EVT_Block
  put its colour band on `share()` and its panel on a hardcoded `top: 606`, so
  they overlapped by 152px at portrait and ~340 at story; T3's background was a
  hardcoded `<svg width="1080" height="1080">`, so the gradient stopped two
  thirds of the way down a story; and EV2's details grid needed its own
  `1fr` rows to reach the panel foot.
- **EV2's SQUARE HAS ALWAYS CLIPPED ITS OWN PANEL, and that is left alone.**
  The first cut gave the grid `flex: 1` at every size, which on the
  already-overflowing square hid the values entirely. Confirmed pre-existing,
  so the share behaviour is gated on `aspectOf(...) !== 'square'` and the square
  keeps its exact original fixed rows. Shrinking the square's own type to fix it
  is a different change from the one that was asked for.
- **Driven in Chromium** (`verify_post_designer_browser.mjs`, 78 checks — the 64
  from v9.74.0 plus a new section that measures the DESIGN rather than the
  geometry: a masthead keeping its share of the extra height, a sponsor strip
  still a strip, row type stepping up with its slot, a body still reaching the
  sponsor strip, EV2's band and panel meeting exactly at both sizes, T4's order
  reaching the footer, and every one of them asserted UNCHANGED at 1080)
  **with a control run**: all 6 of the new checks fail against the previous
  commit, reporting a masthead going 18.15% → 14.52% of the post, a sponsor
  strip 4.63% → 3.7%, row type frozen at `31px -> 31px`, and EV2's band bottom
  at 56.15% against a panel top of 44.89% — the overlap, in the control's own
  numbers.
- **Judged from 144 SCREENSHOTS of the real editor**, not from the checks. The
  geometry all passed on versions that read wrong: T1's story names clumped,
  T2's portrait grid with a 140px dead band, T3's XI stopping short of the
  credit rule, T9's billing running off the edge. A layout is a picture and
  only a picture settles it.
- **UNITS HAVE TO BE THE SAME ACROSS ONE RETURN OBJECT.** The measuring helper
  returned positions as percentages of the post and `font` already multiplied by
  1080, so the step-up check converted twice and read a genuine 31 → 35 as
  31 → 28: a design that had worked, reported as a failure. Every field is a
  plain percentage now and every check converts the same way.
- **A CHECK THAT ASSUMES THE FIXTURE IS NOT A CHECK.** T4's row selector wanted
  a container with more than two children; the suite seeds TWO players, so it
  found nothing and reported the design as unmeasurable. Keyed on the one
  flex-1 column in the layout instead.
- **`SIZES=square` on `shoot_templates.mjs`** shoots one size, which is what
  makes an all-48 square comparison against a control build practical.
- **`npx vite build | tail -2` REPORTS A FAILED BUILD AS A SUCCESS.** A build
  that fails ends in an esbuild stack trace, so the last two lines are
  `at Pipe.onStreamRead` rather than the error — and `vite preview` then serves
  the PREVIOUS `dist` quite happily, so the shoot runs, the screenshots come
  back, and every measurement is of code that never compiled. Cost a full round
  of "my fix had no effect". Grep for `built in|Build failed|ERROR` instead.
- **A `{/* comment */}` CANNOT GO INSIDE A `.map()` ARROW'S RETURN.** The arrow
  returns one expression, so a comment before the element is a second one. Put
  it above the `.map(` call. This is what failed the build above.
- **A `file://` PAGE CANNOT `getImageData` A `file://` IMAGE** — the canvas is
  tainted cross-origin, and from `about:blank` the image will not load at all
  (the trap this file already records for the contact sheet). Read the PNG in
  node and pass it in as a `data:` URL; that is same-origin and decodes fine.
- **NOTICED, NOT BUILT**: the scorecards (SC1-SC3) keep their own fixed
  1920×1080 and are still offered no size picker, so they are the three of the
  48 with no portrait design — they are a landscape document rather than a feed
  post. `templateToBlocks` still reaches four templates. Saved templates are
  still `localStorage`. EV2's square panel still clips at its own size.

<!-- END original CLAUDE.md L1201-1354 -->
<!-- BEGIN original CLAUDE.md L1355-1530 -->
## Every element of a layout is a layer (v9.76.0, Sep 2026)

Asked in two steps: *"what about moving elements on a template forward and back
within a design so you could upload an image and push it behind some text or in
front of some other text?"*, then, once the answer was that a block could only
go wholly behind or wholly in front of a layout: *"I want to be able to use
layers on all templates where each element except the background is a layer."*

- **THE ESTIMATE THAT SAID THIS WAS A BIG JOB WAS ABOUT THE WRONG MECHANISM, and
  the same mistake this file already records one release earlier.**
  `templateToBlocks` recreates a layout as freeform blocks with hand-placed
  x/y/fontSize, reaches four of the 48, and extending it would mean redrawing
  every layout AND throwing away each one's AutoFitText sizing, responsive squad
  logic and the v9.75.0 portrait designs. **A LAYOUT DOES NOT HAVE TO BE
  DECOMPOSED TO BE LAYERED.** Every template root is already a flat list of
  absolutely-positioned children, so each child is a discrete visual element
  that needed only an addressable z-index and a name. The template still renders
  itself; it just does so through a root that knows what its own children are.
- **THE UNTOUCHED PATH IS THE WHOLE REASON THIS IS SAFE UNDER ALL 48.** With no
  order, nothing hidden and no blocks — every export of a post nobody has
  reordered — `LayerRoot` returns the exact div the template rendered before:
  no cloning, no z-index, no stacking context. **Measured rather than asserted:
  all 48 layouts re-shot at square AND at portrait on both builds are
  byte-identical, 96 of 96 — re-shot against the exact build being shipped, not
  an earlier one.**
- **WIRING IS ONE LINE PER ROOT, and 19 of the 48 came free.** The roundup
  family's shared `Post` shell covers all 19; the 17 cricket roots, 11 event
  roots and the launch poster are a `<div style={{…}}>` → `<LayerRoot
  style={{…}}>` swap with the style untouched. `FRAME` in `event-templates` is a
  STYLE HELPER, not a component, which is why those eleven are individual.
- **IDENTITY IS STRUCTURAL, NEVER THE TEXT.** A layer named after its own words
  would lose its place in the stack the moment somebody edited those words, so
  the id is the element's type plus which one of that type it is
  (`t:div#2`). A `data-layer` attribute overrides it, which is what a
  CONDITIONALLY-RENDERED root child needs — `Children.toArray` drops a child
  that is not rendered, so everything after it shifts as it comes and goes.
- **THE NATURAL ORDER IS DOM ORDER *SORTED BY EXISTING z-index*, not DOM order.**
  T1's match-day badge carries `zIndex: 5` and has to keep painting over the
  hero photo that follows it in the markup. Read the markup alone and assigning
  fresh z-indexes silently re-stacks the layout.
- **THE BACKGROUND IS THE FLOOR, NOT A LAYER, which is what the ask actually
  said.** `isolation: isolate` on the root makes it its own stacking context, so
  a block at the bottom of the stack sits ON the club's colours rather than the
  layout being made see-through. That is a better answer than the mechanism it
  replaces: a non-full-bleed block sent behind used to blank the layout's
  background everywhere.
- **SO THE TWO-POSITION `behind` FLAG IS RETIRED, NOT HIDDEN** — the flag, the
  array partition that kept it coherent, `setBehind`, `reorder`'s `crossLayout`
  and the `pb-template-seethrough` CSS. A block's position in the stack is the
  whole answer, so a control that could only say in front or behind had nothing
  left to do: the call this file already makes for the Fit/Fill picker. An item
  saved before this still carrying `behind` is ignored.
- **BLOCKS RENDER AS RUNS, WHICH IS WHAT LET `BlankCanvas` STAY UNTOUCHED.**
  Consecutive blocks between two of the layout's own elements become one
  `BlankCanvas` with its own z-index. Splitting individual blocks out of it
  would have meant re-plumbing its pointer-drag machinery.
- **EVERY RUN IS `passThrough`.** Each one covers the whole canvas, so a run
  that took pointer events would swallow every click meant for a layer under it.
  Blocks re-arm `pointer-events: auto` themselves, which `BlankBlock` already
  did.
- **ONLY THE CANVAS REPORTS ITS LAYERS.** The same post renders several times
  over — the canvas, the off-screen export node, the Preview overlay, a page per
  carousel slide — and every one of them would otherwise register. A carousel
  whose pages hold different rows would then have them fighting over one list.
  `register` is passed only in the interactive context.
- **THE STACK IS A PREFERENCE OVER WHAT THE LAYOUT PAINTS, NOT A COPY OF IT.**
  `applyOrder` keeps the ids somebody has an opinion about and drops anything
  else back at its natural index, so a template re-rendering with one element
  more or less than last time cannot scramble the stack. Same call `sort_order`
  makes elsewhere.
- **EVERY PIECE OF THAT STATE CARRIES THE TEMPLATE IT BELONGS TO, and a mismatch
  is resolved during RENDER rather than by an effect.** Restoring a saved design
  sets the template and its stacking in one tick, so a clear-on-template-change
  effect lands second and wipes what was just restored. Found by writing it that
  way first.
- **A SAVED TEMPLATE KEEPS ITS STACKING.** Without it a design saved with a
  photo tucked behind the headline comes back with the photo on top, which is
  the whole thing somebody was saving.
- **`scale` IS LOCAL TO `renderCanvas`, SO IT IS AN ARGUMENT, NOT A CLOSURE.**
  The first cut reached for the outer name from inside the layer context and
  crashed with `ReferenceError: scale is not defined` — inside the template's
  own render, a long way from the line that caused it. The temporal-dead-zone
  trap this file already records for the Roster header, hit again.
- **`Icon` DRAWS AN EMPTY SVG FOR A NAME IT DOES NOT HOLD.** `ICON_PATHS[name]
  || null` means a missing glyph is invisible rather than an error — the old
  Layers panel had been asking for `image` and drawing nothing since it was
  written. `image`, `eye` and `eyeOff` are in the set now.
- **A COMPONENT CHILD ONLY TAKES A z-index IF IT SPREADS `style`.** Halftone and
  Stripes already did; `GrainSVG` did not, so a root-level grain would have kept
  painting in markup order while the panel said otherwise. Labels for these come
  from one `FRIENDLY` map keyed on the component name, which covers all 48 with
  no per-template naming.
- **A MINIFIED BUILD MANGLES `Component.name`, SO A MAP KEYED ON IT READS
  CORRECTLY ON THE DEV SERVER AND TURNS TO NOISE IN THE BUNDLE A CLUB USES.**
  `FRIENDLY` keyed on `fn.name` gave `Halftone texture` in dev and `R`, `ni`,
  `E` and `Ei` in the real bundle — a Layers panel of two-letter labels. Every
  primitive sets an explicit `displayName` (a string literal, which survives)
  and the map is keyed on that. **Found by sweeping every template's labels on a
  PRODUCTION build, not on the dev server** — nothing about this is visible
  before `vite build`, which is the general lesson: anything that reads a
  function's own name has to be measured on the shipped bundle.
- **AND ONE PRIMITIVE WAS MISSED IN THAT PASS**, so SC1-SC3 still read `Ni`
  until `ScSponsorFooter` got its own. The sweep is worth re-running on any
  change here: it prints every template's labels in one go, and a mangled name
  is obvious at a glance in a way one template opened by hand is not.
- **A LAYOUT'S OWN WRAPPER OFTEN HAS NO WORDS TO BE NAMED AFTER, so pointing at
  the row lights the element up instead.** Naming 300-odd children by hand was
  the wrong fix for ~35 rows reading `Element N` — the honest answer to "which
  one is Element 7" is to show it. Hover outlines it on the canvas and lifts it
  to the top for as long as the pointer is there. Editor only: `hover` is never
  passed to the export context, so it cannot reach a downloaded PNG.
- **`pkill -f` / `pgrep -f` MATCHES ITS OWN SHELL, hit FOUR times in one
  session (exit 144).** Splitting the pattern (`'shoot_temp''lates'`) only helps
  while the pattern appears nowhere else in your own command line — a command
  that kills a shoot AND then starts another one has the literal in its own
  argv, so it kills itself before reaching the second half. Even
  `pgrep -f chrome` matches the shell whose arguments contain the word.
  **Match the process NAME, not the command line**: read `/proc/*/comm`, or use
  `pkill -x`. And never put a kill in the same command as the thing it is
  clearing the way for.
- **A HUNG SHOOT IS THE PILED-UP-CHROMIUM TRAP, and the tell is CPU.** Three
  concurrent Chromium runs left the control shoot idle-waiting with 6 seconds of
  CPU and no write for eight minutes. Kill the browsers, then re-shoot only the
  templates that are missing rather than the whole set.
- **Driven in Chromium** (`verify_post_designer_browser.mjs`, 92 checks — the 78
  from v9.75.0 plus a section that measures the stack off the OFF-SCREEN EXPORT
  NODE rather than the canvas, since the canvas agreeing with itself says
  nothing about the downloaded PNG: a layout listing its own elements by name, a
  new block starting in front of everything, Send to back putting it under every
  one of them with the background still painting, ONE STEP FORWARD PUTTING IT
  BETWEEN TWO OF THE LAYOUT'S OWN ELEMENTS, hiding an element taking it off the
  exported post and putting it back, a real layout having element rows where the
  blank canvas has none, and a saved template driven through a real RELOAD in one
  context so the stack it comes back with can only have been read off the saved
  row) **with a control run**: 16 of the 92 fail against the previous commit,
  reporting its own empty layer list, every element at `z: 0`, `9 -> 9` where an
  element should have come off the post, and `sent=false` where Send to back does
  not exist. The 76 that pass in both are don't-regress guards or the structural
  displayName check, which reads the source rather than the build and so is the
  same either way.
- **COMPARING THE TWO PASS SETS IS HOW YOU FIND A CHECK THAT CANNOT FAIL.**
  `comm -12 <(grep ^PASS run.log|sort) <(grep ^PASS control.log|sort)` lists
  every check that passes in both; anything in there naming the new feature is
  either a don't-regress guard or a check passing for the wrong reason, and
  reading thirty lines settles which. It found three here: "the background still
  paints under a block sent to the back" (a build with no Send to back never
  moves the block, so the background is trivially still there) and both halves
  of "the blank canvas has no layout" (trivially true of a build that draws no
  layout rows anywhere). Each is asserted as a CONTRAST now — gated on the send
  having landed, and paired with the same read on a real layout. **Cheaper and
  more complete than re-reading the checks by hand**, and worth running on every
  suite that has a control.
- **THE SUITE TAKES ITS BASE URL AS `argv[2]`, NOT AS `BASE=`.** An env var is
  silently ignored and the run dies on `ERR_CONNECTION_REFUSED` against the
  hardcoded dev port — which reads as the server being down rather than as the
  argument being in the wrong place. `shoot_templates.mjs` beside it DOES take
  `BASE=`, which is what makes it easy to get wrong.
- **NOTICED, NOT BUILT**: a layout's own element can be reordered and hidden but
  not MOVED or retyped — that is still `templateToBlocks` territory, and still
  four templates. A `transform` offset per layer would make moving cheap without
  disturbing any layout's internal sizing, and is the obvious next step. The
  scorecards' square-split variant (SC1-SC3 rendered per side) is deliberately
  not a `LayerRoot`: two roots with colliding structural ids would apply one
  stack's order to the other. Saved templates are still `localStorage`.
- **AND FOUR EVENT POSTERS KEEP EVERYTHING INSIDE ONE FRAME**, so they report one
  or two layers rather than a stack — EV5 and EV8 draw a single inset panel and
  everything else lives inside it. Descending into that wrapper would make its
  grandchildren layers, and it is exactly the wrong move: the wrapper carries an
  `inset`, so a block rendered inside it would be offset by that much from where
  it was dropped. Naming the wrapper's own children is the fix, per template.
  **Until then the wrapper is named `Poster content` rather than left to read as
  a fragment of its own text**, and on those two the feature honestly degrades
  to the two positions it replaces: a block goes in front of the whole poster or
  behind it. That is what the row says, so nobody is hunting for a stack that is
  not there.

<!-- END original CLAUDE.md L1355-1530 -->
<!-- BEGIN original CLAUDE.md L8406-8464 -->
## A club font with no bold, and ink on a dark accent (migration 226, v9.14.0, Aug 2026)

Reported by Leeming Spartan: their uploaded font looked "too dark" as an H1 and
on the win rate / total runs figures, and the accent button's text was
unreadable. Both are one-line symptoms of two systemic gaps.

- **The bold was never real. It was SYNTHESISED.** Their file is Patua One,
  `usWeightClass 400`, no `fvar`, no italic - a single-weight slab serif. Asked
  for `font-weight: 700` the browser fakes one by smearing the outlines, which
  on an already-heavy face reads as mud. **A font FILE holds exactly one weight
  unless it is a variable font**, so this is the normal case for an upload, not
  an edge case. `services/fonts.describe_font` reads the file at upload time
  (sfnt directly, `.woff` per-table zlib, `.woff2` tag directory only since
  there is no brotli dependency - enough to spot an `fvar`) and stores
  `metrics` on the `font_config` role entry; `buildThemeCss` emits
  **`font-synthesis: none`** when any role cannot really bold. Safe page-wide:
  every app default and multi-weight preset carries a real bold, so nothing
  that COULD bold properly loses it. A file uploaded before this shipped has no
  `metrics` and is treated as single weight, which is right almost always and
  self-corrects on re-upload.
- **Five of our own presets have the same problem** (`oneWeight: true` on anton,
  bebas, archivo_black, abril, bungee). Either the family has no bold cut or
  index.html requests it with no weight axis. **Keep those flags in step with
  the Google Fonts `<link>`** - adding a family there without a weight range
  means adding the flag here.
- **`--pb-weight-display` / `-body` / `-mono`** are the per-role weight, set
  from Typography settings. Consumed through `.pb-heading` / `.pb-figure`
  (styles/theme.css), which is what `PageHeader`'s `<h1>` and `Kpi`'s figure use
  instead of `font-bold`. For everything else `buildWeightCss` emits
  `.font-display.font-bold {…}` style rules - **two classes, so they beat a
  Tailwind utility on specificity** and a club's choice wins over the ~590
  `font-bold`s written into components without editing any of them. Scoped to
  elements that opted into the club's display or mono font, so ordinary bold
  body text is untouched.
- **`--pb-on-accent` is the ONE answer for text on an accent fill** (default
  `#08110b` in theme.css, per-club in `buildThemeCss`). `onAccentInk` picks
  white or near-black by WCAG contrast, so the BetterStats green keeps its dark
  ink and navy/maroon/black get white. **Never hardcode a hex or `text-pb-bg`
  on a `var(--pb-accent)` fill again** - that is what made a navy club's primary
  button near-black on near-black. Swept across the public pages; the admin
  app still uses its own `ON_ACCENT` (`components/admin/ui.jsx`), which is
  correct there because that surface is BetterCricket amber, not club colour.
- **`organisations.public_header_logo`** (migration 226, mirrored in the
  lifespan) puts the crest beside the club name in `PageHeader`. Beside, not
  instead of: the page keeps a real `<h1>` for search and screen readers.
  Opt-in, so no existing club's public site changes on upgrade. **Read it off
  the `/clubs/{slug}` payload, not `/organisations/{id}`** - the Dashboard has
  both in scope and only the former carries it.
- **Deliberately not built**: an italic toggle. Patua One has no italic either,
  so it would hand back faux-slanted glyphs, the same class of problem. A club
  wanting a real bold or italic should upload that file for the role.
- **Verified against the club's real live site** (dev server with
  `VITE_PROXY_TARGET=https://betterat.cricket/api`, screenshotted in Chromium):
  `font-synthesis` computes to `none` on their H1, the Leaderboard button
  computes `rgb(255,255,255)` on their navy, an explicit weight choice moves the
  H1 to 400, and the crest sits beside the name at 1280px and 390px with no
  horizontal overflow. The parser was checked against their actual .ttf plus a
  known Bold file (reads 700) and a woff2 (table directory walks clean).

<!-- END original CLAUDE.md L8406-8464 -->
<!-- BEGIN original CLAUDE.md L10210-10378 -->
## Instructional videos, managed from the site (migration 280, v9.54.0, Aug 2026)

Asked for as a Blog-shaped section at `/videos` — thumbnail, intro text, watch
in a player or download — then, straight after, as something a Super Admin
runs themselves: upload, edit the title and text, replace the file, delete the
entry and its file, and drag the order.

- **THE SECOND ASK CHANGED THE ARCHITECTURE, NOT JUST THE UI.** The first cut
  was a checked-in `data/videos.js` plus `content/videos.py`, mirroring the
  blog's two-hand-kept-lists arrangement. A managed library cannot work that
  way, so both files are gone and `instructional_videos` is the record.
  `og_preview` and `seo` read the TABLE now — a video retitled or deleted by an
  admin moves its share card and its sitemap entry with it.
- **THE VIDEO IS A FILE ON THE MEDIA VOLUME, THE POSTER IS A COLUMN, and the
  split is the whole design.** A video is capped at 512MB against 4-20MB for
  every other binary in this app, and a bytea that size is re-dumped in full by
  every `pg_dump` even though the file never changes. A poster is ~100KB, so
  backing it up is free — and it is what makes a database restored onto a fresh
  box still draw a recognisable library (titles, descriptions, thumbnails) with
  only playback missing.
- **VIDEO FILES ARE DELIBERATELY OUTSIDE THE REGULAR BACKUP** (per direct
  instruction). `ops/backup/backup.sh` says so at the point where somebody
  would otherwise be tempted to add them. The consequence is accepted and
  handled rather than hidden: `file_present` rides on every payload, the page
  says a video is not on the server instead of drawing a dead player, the
  download link is withdrawn rather than left to 404, and a super admin gets a
  count of what needs re-uploading. `orphaned_files()` finds files no row
  points at, which is what a restore leaves behind.
- **AN EXPLICIT HOST PATH, NOT A DOCKER NAMED VOLUME.** `/mnt/media/bettercricket/internal/videos`
  sits under the root the backup agent already uses. A named volume can be
  orphaned by a compose project rename, which is exactly the June 2026 outage;
  a bind mount to a real path cannot. This is what the old "the /app/uploads
  volume isn't guaranteed persistent" comment was really about.
- **THE nginx HAND-OFF IS OPT-IN, AND THAT DEFAULT WAS BOUGHT THE HARD WAY.**
  Reported live: every video 404'd while `GET /public/videos` reported
  `file_present: true` and the poster served fine. The 404 body was nginx's,
  not the app's — so the backend HAD the file, set `X-Accel-Redirect`, and
  nginx then could not find it. **nginx is the process that opens the file, so
  the hand-off needs the directory mounted into the FRONTEND container as well
  as the backend**, and the second mount was missing. The app serves the bytes
  itself by default now (one mount, and it is the process that wrote the file);
  `video_accel_location` switches the hand-off on once both mounts are
  confirmed. Diagnosed by reading the response headers, not by guessing:
  `Server: openresty` with the app's own `cache-control` still attached is what
  says "the app answered and nginx failed the internal redirect".
- **A RESPONSE MUST NOT CARRY A WHOLE VIDEO, AND `Range: bytes=0-` ASKS IT
  TO.** That is what Chrome opens a video with, and the first cut honoured it
  literally: `_read_slice` for the full length, so a 96MB video was 96MB of
  memory per viewer. Every 206 is clamped to `CHUNK_BYTES` now; a short 206 is
  legal and the player just asks for the next part.
- **FastAPI DOES NOT ADD `HEAD` TO A GET ROUTE, THOUGH PLAIN STARLETTE DOES.**
  A `curl -sI` against the file endpoint came back `405 Method Not Allowed`,
  and that is not just a curl flag: players and download managers probe a file
  for `Content-Length` and `Accept-Ranges` before they start streaming, and
  uptime checks use HEAD by default. Both public file routes are
  `api_route(..., methods=["GET", "HEAD"])` now, and a HEAD answers with the
  WHOLE file's size and no body — never a range.
- **A DOWNLOAD WITH NO RANGE MUST BE THE WHOLE FILE.** The same first cut
  served the first 2MB as a 206 to a `?download=1` with no Range header, which
  hands `curl -O` a truncated file. It is a `FileResponse` now, which streams
  off disk rather than buffering. Both bugs are covered by checks that fail
  against the shipped code (6,291,456 bytes in one response, and a `Response`
  where a `FileResponse` belongs).
- **A FILENAME IS NEVER BUILT FROM ANYTHING A PERSON TYPED.** It is
  `<row uuid>.<ext>` from a fixed map, and `_SAFE_FILENAME` refuses anything
  else on the way back out, so a row edited by hand to say `../../etc/passwd`
  resolves to nothing. The uploaded name is kept in a column for the download
  header only.
- **`tempfile.mkstemp` WRITES 0600, AND `os.replace` KEEPS IT.** Every uploaded
  video landed readable by root alone, which breaks two real things: the host
  user cannot copy their own videos back off without sudo (they are outside the
  backup, so that is the recovery path), and nginx workers could not read them
  if the X-Accel hand-off were switched on. Chmodded to 0644 before the rename
  — these are public marketing files with nothing to protect. Found by reading
  a directory listing off the box, not from the code.
- **The upload streams to disk and is never read into memory.** `_check_size`
  seeks the SpooledTemporaryFile rather than calling `len()` on 512MB, and
  `store_upload` writes to a temp file in the same directory then `os.replace`s
  it, so a half-written file is never served. A failed insert deletes the file
  it just wrote — nothing would ever point at it or clean it up.
- **A NEW TOP-LEVEL ROUTE IS A CLUB SLUG UNTIL FOUR SEPARATE LISTS SAY
  OTHERWISE, and only one of them is in the backend.** `/videos` was being
  looked up as a club: `og_preview.RESERVED_ROOT_SEGMENTS`,
  `FaviconManager.RESERVED_ROOTS`, `SponsorFooter.RESERVED_ROOT_SEGMENTS` and
  `lib/marketingPaths.MARKETING_PATHS` each resolve a slug off the pathname
  with their own copy. Missing the last one also renders the club Navbar ON TOP
  of the page's own MarketingNav and drops the forced-dark marketing theme.
  **Found by watching the network, not by reading the routes** — the page
  rendered correctly while firing `/api/clubs/videos` on every visit.
- **THE SLUG IS DERIVED ONCE AND NEVER MOVES.** Retitling a video keeps its
  URL, because a link handed to a club in an email has to survive somebody
  fixing a typo in the heading. A duplicate title is suffixed (`-2`) rather
  than refusing the upload: a re-record of the same walkthrough is ordinary.
- **A FIELD LEFT OUT OF THE FORM IS LEFT ALONE.** `update_video` writes only
  what is PRESENT, so the title form cannot blank a description it never
  loaded and replacing the file cannot reset the text. The api.js helper omits
  a null rather than sending it empty, which is the half that makes it work.
- **THE THUMBNAIL IS CAPTURED IN THE BROWSER**, not on the server: the upload
  is drawn to a canvas at ~1.5s in and posted as a JPEG alongside the video.
  No ffmpeg dependency in the backend container, and the admin still gets to
  upload their own frame instead. Best-effort by design — a codec the browser
  cannot decode resolves to null and the video simply goes without one.
- **nginx caps `/api/` bodies at 20m**, which is right for a logo and useless
  for a screen recording. The cap is raised to 512m on a LONGER-PREFIX location
  for the upload route alone (`/api/club-admin/super/videos`), with
  `proxy_request_buffering off` so a large upload streams through instead of
  spooling to nginx's disk first. Raising it globally would widen every
  endpoint's surface for one route's benefit.
- **THE GATE IS THE SERVER, THE UI IS PRESENTATION.** Every write is
  `require_super_admin`; `useVideos.canManage` only decides what is DRAWN. The
  browser suite asserts both a signed-out visitor AND a signed-in `club_admin`
  see no add, edit, delete or reorder control anywhere.
- **A sixth top-level nav link overflowed the bar, and that was measured.**
  With five links the row is already 16px over its own box at 768px
  (pre-existing); a sixth took it to **91px** and introduced a new overflow at
  820px, which slides under the CTA rather than wrapping — the same trap the
  Selection-header note describes. `Videos` therefore carries a `wide` flag
  (`hidden lg:block`): in the row from 1024px, in the mobile menu below 768px,
  and in the footer always. Re-measured after: back to the 16px baseline
  exactly, 0 everywhere else.
- **`VIDEO_STORAGE_DIR` MUST BE SET BEFORE THE SERVICE MODULE IS IMPORTED**, not
  merely before it is called: the module imports `app.config.settings`, and
  pydantic-settings reads the environment once at instantiation. The first cut
  of the harness set it further down the file, which looked right and silently
  wrote eleven test videos into the real `/mnt/media` path. Same family as the
  Roster temporal-dead-zone note — position in the file is load-bearing.
- **Verified against a real Postgres** (`backend/verification/verify_instructional_videos.py`,
  119 checks through the shipped service and route bodies: the DDL applied three
  times to a populated table, the slug derived and then held still across a
  retitle, a duplicate title suffixed, a text edit not touching the file and a
  file replace not touching the text, every Range case incl. a suffix range and
  a start past the file, reorder renumbering from zero and skipping a foreign
  id without dropping anyone, delete taking the file with it, every path-
  traversal refusal, a replaced file removing the old one, a failed insert
  leaving nothing behind, the missing-file case reporting itself while its
  thumbnail still draws, orphan detection finding a hand-deleted row's file,
  every upload refusal, the share card built from the table and a deleted
  video's card ceasing to resolve, and the downgrade) and **driven in Chromium**
  (`verify_videos_browser.mjs`, 91: the exact params on the wire for a PATCH, a
  delete and a drag-reorder, a dismissed delete sending nothing, an upload with
  no file refused before any request, and the gate from three identities)
  **with a control run**: with `canManage` forced true, 10 fail on exactly the
  leakage they exist to catch.
- **Two checks passed against the broken code first and had to be tightened.**
  `Super admin` and the form's labels are CSS-`uppercase`, so `innerText`
  returns them uppercased and a check written in the source's casing could
  never fail. A check that cannot fail is not a check.
- **THE CALL TO ACTION FOLLOWS THE VIDEO'S MODULE (v9.54.1).** Reported off
  the Team Selection walkthrough: it ended by pitching BetterStats and linking
  `/features`, so a visitor who had just watched selection was sent to the
  wrong module's page. `lib/videoModule.js` maps the module to its heading,
  its marketing page and its button label; BetterStats keeps `/features` (the
  Core feature page, and what the button already pointed at) while the rest go
  to `/modules/{slug}`. A video filed under nothing, or under a label that
  matches nothing, gets the generic BetterCricket pitch — **never a guess at
  which module was meant**.
- **THE MODULE FIELD IS A PICKER, NOT A TEXT BOX, BECAUSE IT NOW DECIDES A
  DESTINATION.** While it was only a display label, free text was harmless;
  the moment it routes a viewer, a typo silently sends a module's audience
  somewhere else. Matching stays forgiving anyway (case and spacing ignored,
  so "Better Select" resolves) because the first four videos were typed by
  hand before the picker existed, and a value the picker does not know is kept
  as its own option rather than being silently reassigned.
- **Not built**: no draft/published state (an upload is atomic, so there is
  nothing to stage), no per-video "what this covers" list (one description is
  what an admin was asked to write), and no transcoding — an admin uploads
  something a browser can already play, and a `.mov` is refused with a sentence
  saying so rather than being stored and failing for every visitor later.

<!-- END original CLAUDE.md L10210-10378 -->

## Team of the Week (v9.102.0)

Asked for as "a Player of the Match that looks across every fixture in a round and uses the same scoring, with a team of any size from 11 down to 6 and up to 14".

- **One scorer, two posts.** `social_potm` was split: the fetch stays in it and the ranking moved to `_rank_our_side(db, org, raw)`, which takes an already-fetched scorecard. The team of the week calls the same function once per completed club match, so the points (1 a run, 20 a wicket, 2 a maiden, 8 an outfield catch, stumping or run out, 4 a keeper catch) cannot drift between the two. Each ranked player now also carries `guid`, the scorecard participant id, which is the pool key for a player with no club record.
- **Which matches are "the round".** With a pasted link it is `_reference_round`, the same rule the Results roundup uses (matches within 3 days of the anchor, plus the anchor grade's own round name). With no link it is the club's newest completed match-day plus games within 3 days before it. The discovery step of `social_results` was lifted out as `_recent_club_matches` so both agree on what "latest" means; the digest of the results output is identical before and after.
- **A player once.** A player who turned out in two grades appears once with the better of the two performances (with that game's grade and opponent), not the sum, which would hand the pick to whoever played most. The key is the club player id, else the scorecard participant id. Ties break on wickets, then runs, then name, so the order never depends on scorecard order.
- **Pool, not team.** The endpoint returns the top 30, ranked. The editor takes the first N (default 11) into `selectedPlayers`; the pool stays in state so the stepper can grow the team without another pull.
- **Layouts.** `TeamOfWeekGrid` (columns from the count: 6 is 3x2, 7 to 8 is 4x2, 9 is 3x3, 10 to 12 is 4x3, 13 to 14 is 5x3, last row centred) and `TeamOfWeekBoard` (row height is the body divided by the count; type, photo and number step with the row). Both use `LayerRoot`, `grow` for the masthead and footer and `pick` for the title, and reuse the roundups' `SponsorFooter` (now exported). Masthead and footer are plain functions returning a `div`, because a component child only takes a layer z-index if it spreads `style`.
- **Stat line.** Built on the client from the ranked player (`totwLine`): batting when there are runs, bowling when there are wickets, catches, stumpings and run outs when non-zero; a duck or wicketless spell only when nothing else happened. Editable per player in the panel.
- **Football.** The tab and both layouts are hidden in the football build (`AFL_HIDDEN_TABS`, `AFL_HIDDEN_TEMPLATES`); `/admin/social/totw` is cricket-only.
- **Verified** with `verify_social_totw.py` (real Postgres, shipped route body and services, Cricket Australia client stubbed to a hand-built round; 23 checks, control run on the previous commit fails exactly the two `exists` checks and the POTM and results digests match) and `verify_totw_browser.mjs` (production build, API stubbed, exact request on the wire, every size 6 to 14 on both layouts at square, portrait and story checked for count, containment and overlap).
- **Not built**: no formation or pitch view, no per-grade weighting (a 50 in 4th grade scores the same as a 50 in 1st, as it does for the player of the match), no caption text.
- **Two things the browser sweep caught that the first draft got wrong.** Growing the team scanned the ranking from the top, so a player taken off by hand came straight back on the next +; it now continues from a cursor (how far down the ranking the team has reached) that shrinking pulls back. And the body's bottom margin was an estimate that grew at its own rate, so on a story the last row of cards ran into the sponsor strip; it is now the strip's real height plus a gap. The containment check only tested the post bounds and could not see the strip until it was made to (`footTop`), and the first layout picker matched on a name that starts with the template id, so the Ranked Board was not being exercised at all until each pass asserted the layout had switched (`#01` on the sheet, `01` on the board).

## Older event templates open as themselves (v9.102.15)

Reported by Secret Harbour Dockers after v9.99.3 shipped: their saved Season Launch template came back as the Curry Night poster.

- **Cause.** v9.99.3 made new templates keep `event` (wording, preset, motif, photo). Templates saved before it hold only the layout, and the editor's own event state starts as `DEFAULT_EVENT` (Curry Night, motif `star`) and is not persisted. `applyTemplate` skipped the event block when `tpl.event` was absent, so an old EV7 template rendered the Season Launch layout over Curry Night wording, with the previous poster's motif and photo.
- **Fix.** When a template has no `event`, `applyTemplate` starts from the first `EVENT_PRESETS` entry whose `template` matches the layout (facts, preset, motif), clears the photo and resets its opacity. Non-event layouts match no preset and are untouched.
- **Not recoverable.** Wording an admin typed into a pre-v9.99.3 template was never stored anywhere server-side, so only the preset wording comes back. The club has to retype it once and press Update.
- **Verified.** Browser suite check 7j (production build, API stubbed): 130 passed on the fix; control run on the previous build fails exactly the one new check (title reads Curry Night).

## Split Poster lineup, DEBUT tags and the hero-row mark (v9.102.16)

Asked for from a club's own "Starting XI" story (South Perth, One Day Round 1): add it as a lineup template with every layer the same, then let socials identify a debutant (automatically if possible) and mark which listed player is the one in the picture.

- **T11 Split Poster** (`social/split-template.jsx`, `SplitPoster`). Pale left panel (bands, dot texture, contained full-length cut-out, shade into navy), dark XI panel, outlined XI under the STARTING wordmark, numbered rows with C/VC/WK and DEBUT chips, fixture and venue foot, sponsor logos (BetterCricket credit when the club has none). Twelve root children, each with a `data-layer` name. The photo is `contain`, never cropped, so T11 has no focal-point control (like T6/T7). Panel colour is `autoPanelColor(accent)` (accent mixed 55% to white) unless the editor's `splitPanel` is set. Hidden in the football build (the XI wordmark is cricket). Taller posts: photo and rows take the height (`share`, row pitch 46.5 / 60 / 80), the story moves type in from both edges for the app's profile row and reply bar.
- **Debut detection.** `GET /admin/social/debuts?player_ids=a,b&before=YYYY-MM-DD` (`services/social_debuts.py`, `require_module("socials")`). A player is a debut when they have no named appearance, batting line or bowling line in `v_effective_games` before the date (abandoned and cancelled games ignored) and no `v_effective_player_season_stats` row with matches in a season that started before the date's season. The current season's own summary is excluded on purpose: it already contains the match once it is synced, which would stop a lineup for a played game from ever showing a debut. Players are scoped by `players.organisation_id`. The reply is `{debuts, known, before}`; an id missing from `known` is left as it was. It is a suggestion: `sp.debut` is switched by hand with the DEBUT button on the row.
- **Editor.** `checkDebuts` runs after a BetterSelect or Play.Cricket lineup load (match day as `before`) and from FIND DEBUTS (today). Its `useState`/`useCallback` sit with the other state: placing them next to the loaders, below an early return, crashed the editor with React #310. DEBUT tag drawn by T1, T3, T10, T11 (`DEBUT_TEMPLATES`); other layouts keep the flag and the Players card names the ones that draw it.
- **Hero-row mark.** `markHero` (off by default) shades the row of `featuredOf(players, featuredId)` on T1, T3, T10, T11 via `heroRowMark` / `isHeroRow` in `cricket-templates.jsx`. T3's rows use the `padding` shorthand, so its mark passes `padY` and overrides the same property rather than adding a longhand beside it.
- **Verified.** `frontend/verification/verify_split_poster_browser.mjs` (production build, API stubbed, Google Fonts fetched with curl because the sandbox browser does not trust the proxy CA): 69 passed on the fix. Control run on the previous build fails the 37 checks that name the feature, and T1, T3 and T10 markup is byte for byte the previous build's with the tag and mark off. `backend/verification/verify_social_debuts.py` (real Postgres, the service's own SQL, effective views stood in by plain tables): 15 passed; a copy without the date, washout and season-year guards fails four.
- **Known rough edge, not changed.** A BetterSelect load puts the ISO date (`2026-10-03`) and a 24 hour time in `match.date` / `match.time`, so every lineup layout, Split Poster included, prints them that way. `fmtIsoDate` exists in `AdminSocialPost.jsx` if a club wants "SAT 3 OCT".

## Split Panels background and the grade as competition (v9.102.17)

Follow-up on v9.102.16: the Split Poster's pale panel asked for as an editable background, and the competition line showed the placeholder word instead of the grade.

- **`split-panels` variant** in `SocialBackgrounds.jsx` ('Clean & Minimal'): Secondary is the pale panel, Primary the dark rail and the foot shade, Paper the bands and dots. The shade uses Primary, not Ink: the editor's palette Ink is white, which made a white foot under white text. It draws in the shared 1080 design space like every variant, so on a taller post the split stays near the centre and the bands scale up.
- **T11 `background` prop** (the editor passes `bgStyle` when a background is active, else null). With any background its own bands, dot texture and shade step aside and the root is transparent; with `split-panels` the dark rail steps aside too, since the variant draws it. Layer ids are explicit `data-layer` names, so hiding some does not shift the others.
- **Competition.** Both lineup loaders now set `match.competition` to `fx.grade`. `matchData` fills an empty competition with the literal `COMPETITION`; T11 treats that literal as empty. Other layouts still print it when nothing was typed.
- **Verified.** `verify_split_poster_browser.mjs`: 76 passed (production build): grade pulls through, placeholder hidden, swatch present, layer hand-off for Split Panels, another background keeps the rail, clearing the background restores the panels.

## Final Score from the Games page (v9.105.3)

The Final Score tab (C4 and RS1 to RS6) could only be filled from a pasted play.cricket.com.au link, or a PlayHQ link that resolved to a short pick list. A club asked for the data to come from its public Games page (`/{slug}/games`) instead.

- **`components/admin/socialpost/ClubGamesPicker.jsx`.** Collapsed by default; nothing is fetched until it is opened. It reads `getOrgSeasons` then `getOrgResults(orgId, { seasonId })`, the same two calls `GamesPage` makes, so the list and the page cannot disagree. Newest season is the default; season and grade selects narrow it. `ABANDONED` and `CANCELLED` games are dropped (they have no score).
- **A pick calls `loadResultMatch(game.id)`.** `games.id` is the Cricket Australia match GUID, so it goes straight to `GET /admin/social/scorecard/{id}` and `applyResultScorecard`. It does not go through `match-lookup`. Mounted on the Get your data step and under the Match Result panel's link box.
- **Known gap, not changed.** `get_social_scorecard` reads Cricket Australia live. A manual game or a scorebook import is on the Games page but has no upstream card, so a pick returns "Scorecard not found". Fixing it means a DB fallback that adapts `games.get_scorecard` output to the `{meta, home, away}` social shape; not built.
- **Verified.** `frontend/verification/verify_final_score_games_browser.mjs` (production build, API stubbed): 15 passed. Control run on the previous build fails the 10 checks that name the picker and keeps the 5 unrelated ones.

## A sponsor slot in every layout, scorecard squares and scorecard POTM (v9.106.0)

Reported with five screenshots: the sponsor grid (v9.105.0) was placed in one generic bottom band and covered each layout's own content. Asked for: space made for it in every template, Final Score left-justified with the sponsor on the right, venue and season moved up, "FULL TIME" dropped, Fixtures with the club lockup cut to a logo, T11 as the lead lineup, and (second and third messages) scorecard squares that fill the post, a POTM picked like the other tabs, and no clipped scorecard rows.

- **One slot per layout** (`social/sponsorSlots.js`). Each layout file exports `SPONSOR_SLOTS` (`templateId -> (width, height, count) => { x, y, w, h, pad, gap, panel }`), the registry merges them, and the editor reads `sponsorSlotFor(templateId, w, h, count)` for the default grid, a re-patch while the grid is still `auto`, and "Use default sponsors". The layout calls the SAME function to leave the rectangle empty, so the space and the grid cannot drift apart. A layout with no entry falls back to `defaultSponsorGeometry`. Pad is 6 to 10 and the backing is `light` on almost all of them.
- **Where they went.** T1 under the hero, T2 left of the header under the venue line (where the user dragged it by hand), T3/T4/T5 in the footer, T6 to T9 above the footer strip, T10 in the torn strip, T11 under the XI on the dark panel, C1 to C3 in a taller credit footer, C4 in the result band, FX and RS in the header (club lockup reduced to the crest) or the ticket margin, RR and TW in a taller footer bar (RR3 under the title), EV1 to EV11 in a strip at the foot.
- **Retired.** `nativeSponsors` is now scorecards only. Fixtures, results and T11 no longer draw logos of their own: `SponsorFooter` in `round-templates.jsx` is a credit-only strip and T11 lost its `sponsors` prop. `scorecardMatch.meta.sponsors` still feeds the SC1 to SC3 footer.
- **Lineup default.** `LINEUP_DEFAULT` is `T11` (football keeps `T1`, it hides T11). Template ids did not change, so saved posts and templates still open.
- **Wording.** "FULL TIME" is "RESULT" on C4, RS1 to RS6 and the Custom Edit decomposition.
- **Scorecard squares.** The 1080 square was wrapped in the 1920x1080 `PostFrame` and scaled to 56% (`nativeSize` was false for scorecards). `nativeSize` is now true while the split is on.
- **Scorecard POTM.** `loadScorecardMatch` also calls `getSocialPotm`, puts the top ranked player in `meta.motm` (`scMotmOf`) and shows a select of the ranking; typing in the MOTM fields flips it to "Typed by hand". The server still returns a blank `meta.motm`.
- **Scorecard rows.** `_scRowFont(panelH, chrome, rows, rp, cap)` sizes SC1 and SC2 rows from the real panel height (SC1 800 wide and 880 square, SC2 760 and 850) instead of one budget baked for the wide post, which ran 69px (SC1) and 85px (SC2) past the panel with 12 batters and 6 bowlers.
- **Tooling.** `verification/shoot_sponsor_slots.mjs` (the real editor, stubbed sponsors with logos, `SPONSORS=1|2|3`, prints `OVERLAP` for any text or picture under the grid), `shoot_scorecards.mjs` (lists clipped text), `verify_scorecard_squares_potm_browser.mjs` (control run on the previous commit fails the scaled square and the three POTM checks), and `verify_post_sponsors_browser.mjs` updated (roundups carry one grid, scorecards none).
- **Verified.** All 47 templates at 3 sizes, 2 sponsors: 141 shots, a grid on each, 0 overlaps. Spot runs at 1 and 3 sponsors per family were also clean. Squares are NOT unchanged (space is carved out of most layouts), so `verify_post_designer_browser.mjs`'s "design measurements unchanged at 1080" checks will report the intended differences.
- **Not done.** Harness contact sheets render blank (a `file://` image from `about:blank`), read the PNGs directly. Story slots on a few footers sit at the very bottom, as their credit marks already did, not lifted clear of the app's reply bar. SC1 and SC2 team names overflow their box by 2 to 4px (descender room, not visibly clipped).

## Final Score result band (v9.106.1)

Follow-up on v9.106.0: the C4 band had the margin on one small line and a tiny MOTM chip, leaving space unused.

- **Band.** `C4_FinalScore` stacks the winner (max 26), `WIN <margin>` (max 54, accent) and a MOTM chip (initial, surname, figures). A tie shows `MATCH TIED` alone. `_c4Geom` band height is 164 / 176 / 196, and the slot follows it.
- **Props.** `AdminSocialPost` now passes `motmFirst`, `motmBat` and `motmBowl` to C4's `result` as well as `motmLast`.
- **Verified.** `verification/shoot_final_score.mjs` (real import through the stubbed editor) at all three sizes: no clipped band text. Story still has a tall empty gap between the batting and bowling groups in the performer panels (existing design, not changed).


## Match Day Card lineup, T12 (v9.106.32)

Asked for from a club's own graphic: a photo background under a colour wash, the XI on a solid panel with a bat, ball, bat and ball or bat and stumps beside each name, the fixture on the right, the club logo centred over the list, a white sponsor bar of one or eight logos, and a slash of colour in the top left and bottom right corners. The photo, wash, corner colour and logo had to be settable and saved as the club's default.

- **Layout.** `social/lineup-card-template.jsx` exports `LineupCard`, `lineupCardSponsorSlot`, `RoleIcon`, `LINEUP_CARD_DEFAULTS`, `SPONSOR_SLOTS = { T12 }`. Registered in `ALL_TEMPLATES` as `T12`, `TAB_MAP` lineup, `DEBUT_TEMPLATES`, and in `AFL_HIDDEN_TEMPLATES` (roles are cricket). Root children carry `data-layer`: Background photo, Colour wash, Sponsor bar, Corner top left, Corner bottom right, Club logo, Starting XI, Match details, Platform credit. The corner slashes come from a plain function `cornerSvg`, not a component, because `LayerRoot` reads `data-layer` off the child element's own props.
- **Role icons.** `roleIconKind(p)`: keeper (flag or role `WK`) wins, then `AR`, `BOWL`, else bat. The four are drawn as inline SVG (no image files), so they export at any size. They read the same `role`/`keeper` the Players card already sets.
- **Look is the club's default.** `lineupCard` state (`bgUrl`, `wash`, `washOpacity`, `corner`, `panel`, `logoUrl`, `logoScale`) rides in `socials_style.lineup_card`, in the same style snapshot as palette and background, so a new lineup opens with it. `lineup_card` is on `_SOCIALS_STYLE_KEYS` in `club_admin.py` (left off, the server strips it) and in `DEFAULT_STYLE_JSON` in the same key order as the snapshot. `localStorage` `bs_social_lineup_card` is the fallback for a user who cannot save settings. A background upload goes to the club's background library (`kind=background`), a logo to the Photos pool; both store the asset's `/api/images/social-media/{id}` URL. Empty wash, corner and panel mean "derive from the palette accent".
- **Logo shape.** The editor measures the logo (`new Image()`, effect on `lineupLogoSrc`) and passes `logoRatio`; the layout makes the box as wide as the list allows or as tall as the header allows, whichever the shape reaches first, then multiplies by `logoScale`. Measured in the editor and not in the layout so the canvas and the off-screen export node get the same number.
- **Sponsor bar.** Height follows the logo count (`sponsorBarH`: 150 for one, 175 for two to four, 235 for five to eight, none for zero). The editor passes `sponsorCount` from the post's own sponsors block (usable logos only). The slot function takes `count`, and `pickSponsors` re-seats a grid that is still where the layout put it (it leaves one somebody moved). With zero sponsors no bar is drawn. On a story the bar stays full-bleed and the logos sit 140px above the bottom edge, clear of the reply bar.
- **One name size.** All eleven names share a size worked out from the longest (`0.6 * chars + 2` against the room between the number and the icon rail). `AutoFitText` per row stays as a net only. Per-row fitting made `Hilton CARTWRIGHT` smaller than `Frazer HAY` on portrait and story.
- **Hooks trap hit.** A `useState` added next to the upload handlers sat below the `if (loading) return` and gave React #310 on open. New editor state goes with the other state near the top.
- **Verified.** `verification/verify_lineup_card_browser.mjs` (production build, API stubbed): 50 passed. It checks eleven rows, the five icon kinds, one and eight sponsors, none, a 6:1 and a 1:1 logo, wash and corner reaching the post, the upload request on the wire (`kind=background`), the saved `socials_style.lineup_card`, a reload applying it, portrait and story, and 390px. Control with the shared name size reverted fails exactly the two "one name size" checks (portrait and story). `shoot_sponsor_slots.mjs T12` at `SPONSORS=1` and `3`: 0 overlaps.
- **Not done.** The fixture is printed from `team.name` and `opponent.name` as the other lineups do, with `VS` (a club that writes "V's" cannot change it). The wash and corner have no gradient or pattern options. The card has no hero photo slot.


## Glass Card result layout, RS7 (v9.106.36)

Asked for from three club graphics: a match photo as the background, the two team scorecards on liquid glass over a blurred, black-tinted part of it, with the card placed top centre, bottom centre or in any of the four side corners, sponsor logo and BetterCricket logo on the photo.

- **Layout.** `social/result-glass-template.jsx` exports `ResultGlass`, `glassGeo`, `glassSponsorSlot`, `GLASS_POSITIONS`, `GLASS_DEFAULTS`, `GLASS_FOCUS`, `SPONSOR_SLOTS = { RS7 }`. Registered in `ALL_TEMPLATES` as `RS7` (`kind: 'singleresult'`, Final Score tab), `TAB_MAP`, and `AFL_HIDDEN_TEMPLATES`. Root children: Background photo, Blur and tint, Edge shade, Match header, Our scorecard, Their scorecard, Sponsor label, BetterCricket logo.
- **Glass is a blurred copy, not `backdrop-filter`.** modern-screenshot exports through an SVG foreignObject and does not paint backdrop-filter. Each pane holds a canvas-sized copy of the photo, offset so it shows what is behind it, with `filter: blur(26px)`; the tint region is a blurred copy under a gradient `mask-image` plus `rgba(0,0,0,tint)`. Centred cards fade with a linear mask, side cards with a radial one. A real PNG export was downloaded and read to confirm blur, mask and panes survive.
- **Photo is per post.** It is the editor's `heroImage` (same upload and crop modal as the hero slot), with its own framing state `glassFocus` (default centre, not the top of the lineup layouts). Position, tint and which performers each side shows (`glassLook`) live in `localStorage` `bs_social_result_glass`, not the club's saved style.
- **Sponsor slot follows the position.** `sponsorSlotFor` takes a fifth argument `opts`, handed to the layout's slot function as its fourth; the editor builds `slotOpts` for RS7. The slot is at the free end (bottom for a top card, top for a bottom card), on the card's side (right for a centred card), wider for more logos. `changeGlassPosition` re-seats a grid still in the old slot; one somebody moved stays. The "Proudly sponsored by" label is drawn only when `sponsorCount` > 0; `gridLogoCount` is shared with T12.
- **Names.** `topBatters` and `topBowlers` now carry `surname` (scorecard `last`) and bowlers carry `overs`; `mapPerf` hands `first`, `sn`, `o` to single results. `PerformerRow` clears `surname` when the name is typed over, so a hand edit shows what was typed. A hand-typed "J. BARENDSE" splits on its last word.
- **Fit traps.** `AutoFitText` re-measures only when its own props change, so a position change (new column widths) must arrive in `measureDeps` (`fitKey`); without it "MENS FIRST GRADE" clipped on side cards. Team names and player names each share one size, worked out from the longest.
- **Verified.** `verification/verify_result_glass_browser.mjs` (production build, API stubbed, `PHOTO=` a real JPEG): 226 passed. Six positions at three sizes check card half and side, no overlap, nothing outside the post, no clipped text, sponsor grid and logo clear of the card at the free end; none, one and four sponsors; a side yet to bat; performers per side; tint; grid following a move; settings kept across a reload; 390px. Control against the previous commit: 2 passed (page errors, 390px), 218 failed; several checks first passed vacuously with no card, so they now require the card to be drawn. `verify_lineup_card_browser.mjs` still 50 passed.
- **Not done.** Position, tint and performer choices are not saved to the club. The trophy and gold highlight (100 runs, 5 wickets) are fixed. No sponsor backing option beyond the Sponsors panel's own.

## Match Day Card follow-up: brand font, whole-bar backing, bigger credit (v9.106.35)

Feedback on the first release (screenshots from a club): the font did not change with Brand, the Sponsors Backing buttons drew a box inside the white bar instead of changing the bar, and the BetterCricket mark was too small.

- **Font.** `FONT` / `WEIGHT` are `var(--social-display-font)` and `var(--social-display-font-weight)`, the same variables the other layouts read; the first release hard-coded Hanken Grotesk. Per-row `AutoFitText` is gone from the names. `useSharedNameSize` measures every `[data-name]` at the cap (`rowH * 0.62`) and takes the largest size at which the widest fits, again when a web font finishes loading (`loadingdone`). Names and fixture lines therefore move with the face (Anton against Archivo Black).
- **Loop trap.** The number column's width first followed the fitted size, and the size is measured from the room beside that column, so the two chased each other (React #185 the moment a font was picked). The column is now `nameCap * 1.7`, fixed.
- **AutoFitText and font swaps.** It re-fits only on its own props, so a face change left the fixture lines clipped. The hook returns a `fontSig` (computed family plus font-load count) and the fixture lines take it as `measureDeps`.
- **Backing is the bar.** The slot returns `panel: 'light', layoutBacked: true`. `newBlankItem` keeps `layoutBacked`, `SponsorGridBlock` draws no backing of its own for such an item, and the editor passes the block's `panel` to the layout as `sponsorPanel`: light is white, dark is `rgba(8,10,14,0.9)`, none draws no bar (the photo shows). `pickSponsors` re-seats a grid with x, y, w, h only, so it no longer resets the chosen backing.
- **Credit.** `CreditMark` is 52px high (was 22), white on a dark or absent bar.
- **Verified.** `verify_lineup_card_browser.mjs`: 63 passed. Control on the v9.106.32 source fails the seven new checks (credit size, font variable, picking Anton, size follows the face, Dark bar, no box round the logos, None).


## Card layouts: Round Cover T13, Giant Type C5, Highlights Cover RS8 (v9.107.0)

Asked for from a club's own Figma handover (captains, team lists, milestone cards, a save the date and a round highlights cover). Built club-agnostic: the Scarborough look is just a green and gold palette. The source was three phone screenshots of the file plus an earlier hand-built Figma skill that records the spacing (the connector could not open the file: the signed-in account had a View seat, and the Figma MCP needs an edit seat). Treat the layouts as close matches to the screenshots and not as measured copies.

- **What maps to what.** Team-list grade cards already exist as T12 Match Day Card (role icons, captain chip, sponsor bar), so no change there. New: the round cover (T13), the captains and milestone card (C5, one layout for "FIRST XI", "100" and "5FA") and the highlights cover (RS8). The save the date poster is covered by the Events tab (EV1 to EV11).
- **Files.** `social/round-cover-template.jsx`, `giant-type-template.jsx`, `highlights-cover-template.jsx`, `card-kit.jsx` (corner line, hatch strip, glow disc, glass badge, `glowColor`, `niceName`). Registered in `ALL_TEMPLATES`, `TAB_MAP`, `AFL_HIDDEN_TEMPLATES`, `sponsorSlots.js`; T13 and C5 are in `HERO_SLOT_TEMPLATES`, T13 has a `HERO_CROP_ASPECT` entry (a rough 0.8 for the framing preview), and RS8 has its own photo panel (`highlights-cover-look`) and `highlightsFocus` state.
- **Giant Type depth.** The headline is drawn twice: filled in the accent behind the player and hollow (`-webkit-text-stroke`) in front. With a cut-out the type passes behind the head and comes back over it; with a plain photo the hollow copy still reads. The stats row splits `subheadline` on `·` or `|` only, so a sentence is never cut up.
- **Trap found while building.** The Kind, Headline and Subheadline fields were drawn only for `templateId === 'C1'`, so C5 opened with no way to type its own headline. The hero-mode switch had the same `['C1', 'C3']` list. Both now include C5.
- **Real export.** The three layouts were downloaded as PNGs (2160 by 2700 at the portrait size) and read: the masks, text stroke, hatched strip and quarter-turn word all survive modern-screenshot.
- **Verified.** `verify_card_layouts_browser.mjs` 147 passed against the new build, at square, portrait and story, 390px and the picker. Control on the v9.106.36 source: 105 fail. `verify_lineup_card_browser.mjs` 63 and `verify_result_glass_browser.mjs` 226 still pass. `verify_post_designer_browser.mjs` fails the same 8 checks on both builds (sponsor-slot reads in that older suite), so they are not from this change.
- **Not done.** Set mode (cover plus every grade in one go), and a saved club default for these looks. RS8 cannot say who batted first. Cap-presentation, captains-profile and the save the date designs from the club file were not rebuilt beyond what C5 and EV1 to EV11 already give.
