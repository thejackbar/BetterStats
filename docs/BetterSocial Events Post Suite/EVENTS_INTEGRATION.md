# BetterSocials — Event / Announcement posts

Adds a club-event poster suite to the **BetterPosts** designer: Auction Night,
The 100 Club, Curry Night, Selections, Presentation Night, Season Launch, Live
Music, Quiz Night + a generic blank — across **11 whitelabel layouts**.

Built to the existing social-template contract, so they render and export
(`exportNodeToPng`) through the exact same pipeline as the lineup / scorecard /
roundup posts. Colour follows the club's accent (or any palette), the facts are
one editable object, and photo-led layouts take an uploaded background (curry
behind Curry Night, a band behind Live Music) behind a readable scrim.

## New files
| File | What |
|---|---|
| `frontend/src/social/event-templates.jsx` | 11 templates + `EVENT_TEMPLATES`, `EVENT_PRESETS`, `EVENT_MOTIFS`, `resolveMotif`, `eventPaletteFor` |
| `frontend/src/components/admin/EventPostEditor.jsx` | The "Events" tab controls panel |

Both land at their final repo paths in this bundle — copy the `frontend/…`
tree straight in.

## Integration — 6 edits to `frontend/src/pages/admin/AdminSocialPost.jsx`

### 1. Imports (top of file, by the other `social/` imports)
```js
import { EVENT_TEMPLATES, EVENT_PRESETS, DEFAULT_EVENT, resolveMotif, eventPaletteFor } from '../../social/event-templates'
import EventPostEditor from '../../components/admin/EventPostEditor'
```

### 2. Register the templates — append to the `TEMPLATES` array
```js
const TEMPLATES = [
  // …existing entries…
  ...EVENT_TEMPLATES.map((t) => ({ id: t.id, name: t.name, component: t.component, desc: t.desc, maxPlayers: 0, kind: 'event' })),
]
```

### 3. `TAB_MAP` — map every event id to the new tab
```js
const TAB_MAP = {
  // …existing…
  EV1: 'events', EV2: 'events', EV3: 'events', EV4: 'events', EV5: 'events', EV6: 'events',
  EV7: 'events', EV8: 'events', EV9: 'events', EV10: 'events', EV11: 'events',
}
```

### 4. `TABS` — add the tab (place it wherever you want it to appear)
```js
{ key: 'events', label: 'Events' },
```

### 5. `TAB_FIRST` — default template for the tab
```js
events: 'EV1',
```

### 6. State + preset handler (inside `AdminSocialPost`, with the other `useState`s)
```js
const [event, setEvent]           = useState(DEFAULT_EVENT)
const [eventPreset, setEventPreset] = useState('curry')
const [eventMotifKey, setEventMotifKey] = useState('star')
const [eventBg, setEventBg]       = useState(null)        // object URL or null
const [eventBgOpacity, setEventBgOpacity] = useState(0.85)

const onPickPreset = (key) => {
  const p = EVENT_PRESETS.find((x) => x.key === key)
  if (!p) return
  setEventPreset(key)
  setEvent({ ...p.event })
  setTemplateId(p.template)
  setEventMotifKey(p.motif)
}
```

## Render wiring (two spots, mirroring how the other tabs already work)

**A — controls column.** Where the page chooses which editor panel to show for
the active tab, add:
```jsx
{activeTab === 'events' && (
  <EventPostEditor
    event={event} setEvent={setEvent}
    presetKey={eventPreset} onPickPreset={onPickPreset}
    templateId={templateId} setTemplateId={setTemplateId}
    motifKey={eventMotifKey} setMotifKey={setEventMotifKey}
    bgImage={eventBg} setBgImage={setEventBg}
    bgOpacity={eventBgOpacity} setBgOpacity={setEventBgOpacity}
  />
)}
```
The Events tab already has its own layout + motif pickers, so you can skip the
parent's generic template-chip row when `activeTab === 'events'` (optional).

**B — the off-screen render target (`renderRef`).** Alongside the existing
active-template render, add an event branch. `tmpl` is the registry entry for
`templateId`; `themedPalette` is the palette you already compute:
```jsx
{activeTab === 'events' && (() => {
  const EvComp = tmpl.component
  const palette = eventPaletteFor(tmpl.surface, themedPalette)
  const motif = resolveMotif({
    motifKey: eventMotifKey,
    imageUrl: eventBg,
    opacity: eventBgOpacity,
    label: (EVENT_PRESETS.find((p) => p.key === eventPreset)?.photoLabel) || 'Add a photo',
  })
  return <EvComp team={team} event={event} palette={palette} motif={motif} />
})()}
```
Export is unchanged — `handleExport` reads `tmpl.w/h` (both undefined for events
⇒ the default 1080×1080) and calls `exportNodeToPng` on `renderRef` as today.

> **Light vs dark.** Six layouts are paper-backed (Ticket, Gazette, Sticker,
> Swiss, Polaroid, + Crest is a deep field). `eventPaletteFor` adds the
> `paper`/`deepInk` tokens they need; the existing dark-mode toggle has no effect
> on them, which is expected. The accent still drives their colour.

## index.html — fonts
The stylised layouts use faces not already loaded. Add these families to the
Google Fonts `<link>` in `frontend/index.html` (weights shown):
```
Cormorant+Garamond:ital,wght@0,500;0,600;0,700;1,500   (Ticket, Crest)
Playfair+Display:wght@600;700;900                        (Gazette)
Spectral:ital,wght@0,400;0,500;1,400                     (Gazette body)
Fredoka:wght@500;600;700                                 (Sticker Pop)
```
`Barlow Condensed`, `JetBrains Mono`, `Permanent Marker`, `Caveat` and the
sans/Helvetica stacks are already present. The export embeds whatever
`fonts.googleapis.com` sheets are in `<head>` (see `exportImage.js`), so once the
families are in the link, captures pick them up automatically.

## Notes / assumptions
- Motif glyphs reuse the existing `src/assets/thiings/*.png` set already in the
  repo — no new binary assets.
- `team` is the same object the other templates receive (built from `settings` —
  name / logo / monogram), so club logo + name + accent are automatic per club.
- Sample copy in `EVENT_PRESETS` mirrors the standalone preview deck used to
  sign these off; edit freely.
- These were authored against the template contract and the shared primitives
  (`AutoFitText`, `ClubLogo`, `Halftone`, `Stripes`); I couldn't run them against
  a live build from here, so give them one pass in the designer after wiring.
