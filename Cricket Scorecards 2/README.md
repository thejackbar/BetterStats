# Cricket Lineup Templates

Production-ready, data-driven cricket post templates. 9 lineup designs + 4 match-day companions, all 1080×1080 square (Instagram feed).

Templates are built in HTML/React and render in any modern browser. They can be:
1. **Edited interactively** — open `Cricket Lineup Templates.html` in a browser, see all 13 templates on a pan/zoom canvas, click ••• on any artboard to download as PNG.
2. **Rendered from JSON server-side** — pipe your DB rows through `render/render.js` (Node + Puppeteer) to get a JPG.

---

## File layout

```
Cricket Lineup Templates.html   ← the interactive viewer (open in browser)
render.html                     ← single-artboard renderer used by Puppeteer

app.jsx                         ← wires data + tweaks into the design-canvas
data.jsx                        ← SAMPLE_TEAM / SAMPLE_PLAYERS / SAMPLE_MATCH / palettes
fx.jsx                          ← shared primitives: ClubLogo, PlayerImage, RoleChip, GrainSVG…
templates-a.jsx                 ← T1 Hero+List, T2 Trading Cards, T3 Side+Numbered
templates-b.jsx                 ← T4 Batting Order, T5 Brutalist, T6 Diagonal
templates-c.jsx                 ← T7 Captain Spotlight, T8 Asymmetric Mosaic, T9 Festival Flyer
companions.jsx                  ← C1 Captain Announce, C2 Toss, C3 MoM, C4 Final Score

design-canvas.jsx, tweaks-panel.jsx ← reusable scaffolding (don't edit)

assets/
  team-logo.webp                ← Applecross CC shield (replace per team)
  opponent-logo.png             ← Nottinghamshire CCC monogram (replace per match)
  player-cutout.png             ← Sample player cutout (transparent bg)

render/
  render.js                     ← Node entry point — config in, JPG out
  render-all.js                 ← Render all 13 templates from example-input.json
  package.json
  example-input.json
```

---

## Template inventory

### Lineup posts (9)

| Id | Name                       | Best for                            |
|----|----------------------------|-------------------------------------|
| T1 | Hero + Squad List          | Squad announce w/ captain cutout    |
| T2 | Trading Card Grid          | 12-player squad, photo per card     |
| T3 | Side Image + Numbered XI   | Probable XI w/ one feature image    |
| T4 | Batting Order              | Tactical preview, role-coded list   |
| T5 | Brutalist Typography       | Type-driven hero, no photo needed   |
| T6 | Diagonal Poster            | Match-day hype, minimal player data |
| T7 | Captain Spotlight          | Captain leads + abbreviated XI      |
| T8 | Asymmetric Mosaic          | Photo-rich, captain gets 2×2 tile   |
| T9 | Festival Flyer             | Tour-poster name lockup             |

### Match-day companions (4)

| Id | Name                | Data shape                                              |
|----|---------------------|---------------------------------------------------------|
| C1 | Captain Announce    | one player object                                       |
| C2 | Toss Won            | `{ winner, decision }`                                  |
| C3 | Man of the Match    | `{ player, stats[], summary }`                          |
| C4 | Final Score         | `{ winner, margin, teamScore, oppScore, motmLast }`     |

---

## Data shape

All templates read from the same core objects. Pseudo-TypeScript:

```ts
interface Team {
  name:     string;   // "APPLECROSS"
  short:    string;   // "AC"          — used in compact spots (T6 hero, scoreboards)
  monogram: string;   // "AC"          — fallback letter mark when no logo image
  logo:     string;   // URL or local path to PNG/SVG/WebP — transparent bg preferred
}

interface Match {
  competition: string; // "PREMIER T20"
  round:       string; // "ROUND 7"
  venue:       string; // "Heathcote Reserve"
  date:        string; // "SAT 30 MAY" — display string, not a Date
  time:        string; // "2:30 PM"
  season:      string; // "2025–26"
}

interface Player {
  first:        string;   // "Marcus"
  last:         string;   // "HOLT"     — uppercase for best fit with Anton type
  role:         "BAT" | "BOWL" | "AR" | "WK";
  roleLong?:    string;   // "Top-Order Batter"
  captain?:     boolean;  // shows C chip
  viceCaptain?: boolean;  // shows VC chip
  keeper?:      boolean;  // shows WK chip
  headshot?:    string;   // URL to transparent-bg cutout. Falls back to team.logo if missing.
}
```

Companion data:

```ts
interface Toss { winner: "TEAM" | "OPPONENT"; decision: "BAT" | "BOWL"; }

interface MoM {
  player:  Player;
  stats:   { label: string; value: string }[];  // 4–6 stats look best
  summary: string;
}

interface Result {
  winner:     "TEAM" | "OPPONENT" | "TIE";
  margin:     string;  // "by 28 runs", "by 7 wickets", "by 4 runs (DLS)"
  teamScore:  string;  // "182/6 (20)"
  oppScore:   string;  // "154/9 (20)"
  motmLast?:  string;  // surname only, shown on the scoreboard
}
```

---

## Palettes

Six built-in colorways in `data.jsx`. Each is a 4-token system: `primary` (background), `secondary` (panel/accent bg), `accent` (chips/highlight), `ink` (foreground text).

| Key       | Vibe                    |
|-----------|-------------------------|
| midnight  | navy + gold             |
| crimson   | maroon + red (default)  |
| forest    | deep green + lime       |
| cobalt    | royal blue + cyan       |
| rust      | brown + orange          |
| graphite  | near-black + acid green |

To add a new palette, append to `window.PALETTES` in `data.jsx`:

```js
applecross: {
  name: "Applecross",
  primary:   "#1a0606",
  secondary: "#330b0c",
  accent:    "#ec1d3f",     // match the shield red
  ink:       "#ffffff",
},
```

Then set `palette: "applecross"` in your render config.

---

## Interactive viewer

Open `Cricket Lineup Templates.html` in a browser.

- **Pan/zoom** the canvas with mouse drag + wheel.
- **••• menu** on any artboard → Download PNG / HTML.
- **Tweaks panel** (toolbar icon top-right) → live-swap colorway, team name, monogram, opponent, venue, date, time, competition, round, season.
- Drag artboards to reorder; click an artboard label to rename.

The viewer uses the sample data baked into `data.jsx`. It's for design review, not production output.

---

## Plugging in your DB

### Option A — replace the sample data globals

Quickest path. Edit `data.jsx` so `SAMPLE_TEAM`, `SAMPLE_PLAYERS`, `SAMPLE_MATCH`, etc. are pulled from your data source instead of hardcoded. Keep the same shape and the templates work unchanged.

If you want to serve this from a CMS, render the page on your server with the data inlined as a `<script>` block, e.g.:

```html
<script>
  window.SAMPLE_TEAM      = {{ team_json }};
  window.SAMPLE_PLAYERS   = {{ players_json }};
  window.SAMPLE_MATCH     = {{ match_json }};
  window.SAMPLE_MOTM      = {{ motm_json }};
  window.SAMPLE_TOSS      = {{ toss_json }};
  window.SAMPLE_RESULT    = {{ result_json }};
</script>
<!-- then load data.jsx -->
```

(Tweak `data.jsx` to use `window.SAMPLE_TEAM = window.SAMPLE_TEAM || {...defaults}` so your injection wins.)

### Option B — server-side render (recommended for automation)

Use the Puppeteer renderer in `render/`. See below.

---

## Server-side rendering

```bash
cd render
npm install                          # one-time
node render.js example-input.json out.jpg
```

That writes a 2160×2160 JPG (1080 logical × 2x device pixel ratio).

### Real-world usage

Build your config from a DB row:

```js
// your-pipeline.js
const fs = require("fs");
const { execSync } = require("child_process");

async function postLineup(matchId) {
  const match = await db.matches.findOne({ id: matchId });
  const players = await db.players.findMany({ matchId });

  const config = {
    template: "T1_HeroList",            // or pick another id
    palette: match.team.palette || "crimson",
    team: {
      name: match.team.name,
      short: match.team.short,
      monogram: match.team.monogram,
      logo: match.team.logoUrl,         // any URL puppeteer can fetch
    },
    opponent: {
      name: match.opponent.name,
      short: match.opponent.short,
      monogram: match.opponent.monogram,
      logo: match.opponent.logoUrl,
    },
    match: {
      competition: match.competition,
      round: match.round,
      venue: match.venue,
      date: formatDate(match.date),     // e.g. "SAT 30 MAY"
      time: formatTime(match.startTime),
      season: match.season,
    },
    players: players.map(p => ({
      first: p.firstName,
      last:  p.lastName.toUpperCase(),
      role:  p.role,                    // ensure "BAT"|"BOWL"|"AR"|"WK"
      roleLong: p.roleLabel,
      captain:     p.isCaptain,
      viceCaptain: p.isViceCaptain,
      keeper:      p.isKeeper,
      headshot:    p.headshotUrl || null,
    })),
  };

  fs.writeFileSync("/tmp/lineup.json", JSON.stringify(config));
  execSync(`node ${__dirname}/render/render.js /tmp/lineup.json /tmp/lineup.jpg`);

  // /tmp/lineup.jpg is now ready to upload to your CDN / Instagram
}
```

Or call the renderer programmatically (skip the shell, use puppeteer directly with `render.html`).

### Batch + stdin modes

```bash
node render.js --batch ./configs ./out          # every *.json in configs → ./out/<name>.jpg
cat config.json | node render.js --stdin x.jpg  # streaming pipeline
node render-all.js out                          # render every template from the example data
```

### Asset path notes

- **Logos and headshots** must be reachable from Puppeteer's headless browser. Local file paths are resolved relative to `render.html` (project root). Remote URLs (`https://your-cdn/team.png`) work fine — Puppeteer waits for network idle.
- **CORS**: if your logos are on a private CDN, the headless browser needs to be able to fetch them. Public URLs are simplest.
- **Transparent backgrounds**: cutouts read best with PNG/WebP transparency. JPGs work but the background color of the template will show through any unprintable areas.

---

## Customizing a template

Each template is a single React component in `templates-*.jsx` taking `{ team, opponent, match, players, palette }`. To create a variant:

1. Copy one of the template functions, give it a new name (e.g. `T10_MyVariant`).
2. Tweak the JSX/styles.
3. `Object.assign(window, { T10_MyVariant });` at the bottom.
4. Add an artboard in `app.jsx`:
   ```jsx
   <DCArtboard id="t10" label="10 · My Variant" width={1080} height={1080}>
     <T10_MyVariant {...common} />
   </DCArtboard>
   ```
5. To render it server-side, add `T10_MyVariant` to the templates array in `render/render-all.js` and reference it by name in your config.

---

## Fonts

Loaded from Google Fonts:

- **Anton** — primary display (last names, headlines)
- **Bebas Neue, Archivo Black** — alt display options
- **Inter** — running text, labels
- **JetBrains Mono** — utility/metadata strips

For server rendering, Puppeteer downloads them at run time (Google Fonts are CDN-hosted). For air-gapped environments, self-host the woff2 files and swap the `<link>` in `Cricket Lineup Templates.html` and `render.html`.

---

## Limitations / things to know

- Last names with >12 characters may overflow on dense templates (T1, T5). Use uppercase + short form ("VAN DER MERWE" → "V.D. MERWE") for those.
- T8 mosaic uses `role` to color-code tiles — make sure every player has a role set.
- The renderer is single-page; rendering 13 templates in sequence with cold Puppeteer takes ~30s on a laptop. Run `render-all.js` to batch.
- All sample data lives in `data.jsx`. Strip it before deploying if filesize matters.
