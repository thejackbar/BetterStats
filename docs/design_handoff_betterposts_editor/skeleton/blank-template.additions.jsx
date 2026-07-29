// Additions to frontend/src/social/blank-template.jsx
//
// Club Data blocks for a PLAYER: their photo and their name lockup, alongside the
// existing kind:'player' stat tiles. All three read the same `playerId`, so one
// picker in the inspector drives photo + name + numbers.
//
// Apply as three small edits to blank-template.jsx (this file is a reference, not
// a module to import).

// ── 1. BLANK_DATA — grouped so the panel can show "from a player profile" vs
//       "from the club". `group` is new; existing entries just gain it.
export const BLANK_DATA = [
  { kind: 'playerphoto', name: 'Player photo', group: 'player' },
  { kind: 'playername',  name: 'Player name',  group: 'player' },
  { kind: 'player',      name: 'Player stats', group: 'player' },
  { kind: 'fixtures',    name: 'Fixtures',     group: 'club' },
  { kind: 'results',     name: 'Results',      group: 'club' },
  { kind: 'record',      name: 'W-L-D record', group: 'club' },
  { kind: 'scorecard',   name: 'Scorecard',    group: 'club' },
]

// ── 2. newBlankItem — add two cases to the `type === 'data'` branch.
//
//    if (kind === 'playerphoto') return { ...base, x: 540, y: 300, w: 460, h: 620, playerId: opts.playerId || null, fit: 'cover' }
//    if (kind === 'playername')  return { ...base, x: 70,  y: 560, w: 900, h: 260, playerId: opts.playerId || null, showRole: true }
//
//    …and let `player` accept a seeded id the same way:
//    if (kind === 'player') return { ...base, w: 900, h: 380, playerId: opts.playerId || null }

// ── 3. DataBlock — two new branches. Photo uses the SAME url the lineup templates
//       use (playerToTemplatePlayer in AdminSocialPost builds `headshot` from it),
//       so nothing new is needed server-side.
//
//       `data.playerStats[playerId]` is already passed down from AdminSocialPost;
//       `data.players` is the roster (allPlayers) — pass it in the same bundle.

const BASE_URL = import.meta.env.VITE_API_URL || '/api'
const headshotUrl = (p) => (p?.photo_url ? `${BASE_URL}/images/players/${p.id}/photo` : null)

// Inside DataBlock({ item, palette, data }):
export function PlayerPhotoBranch({ item, palette, data, ink }) {
  const player = (data.players || []).find((p) => p.id === item.playerId)
  const src = headshotUrl(player)
  if (src) {
    return (
      <img
        src={src}
        alt=""
        draggable={false}
        style={{ width: item.w, height: item.h, objectFit: item.fit || 'cover', display: 'block', pointerEvents: 'none' }}
      />
    )
  }
  // No photo on the profile — mirror ImageBlock's dashed placeholder so the block
  // still reads as "a photo goes here" on the canvas and in the export preview.
  return (
    <div style={{
      width: item.w, height: item.h,
      border: `3px dashed ${ink}55`,
      display: 'grid', placeItems: 'center', textAlign: 'center', padding: 16,
      fontFamily: "'JetBrains Mono', monospace", fontSize: 20, letterSpacing: 2, color: `${ink}99`,
    }}>
      {player ? `NO PHOTO ON ${(player.display_name || player.name || '').toUpperCase()}'S PROFILE` : 'SELECT A PLAYER'}
    </div>
  )
}

export function PlayerNameBranch({ item, palette, data, ink, accent, displayFont, monoFont }) {
  const player = (data.players || []).find((p) => p.id === item.playerId)
  const name = player ? (player.display_name || player.name || '') : ''
  // Same "LAST, First" / "First Last" handling as splitName in AdminSocialPost —
  // import that helper rather than duplicating it when you wire this up.
  const [first, last] = name.includes(', ')
    ? [name.split(', ')[1], name.split(', ')[0]]
    : [name.split(/\s+/).slice(0, -1).join(' '), name.split(/\s+/).slice(-1)[0] || '']
  const role = player?.roles?.[0] || player?.role || ''
  return (
    <div style={{ width: item.w, fontFamily: displayFont, color: ink }}>
      {first && <div style={{ fontSize: 52, lineHeight: 1, color: accent, letterSpacing: 1 }}>{first.toUpperCase()}</div>}
      <div style={{ fontSize: 148, lineHeight: 0.92 }}>{(last || 'PLAYER').toUpperCase()}</div>
      {item.showRole && role && (
        <div style={{ fontFamily: monoFont, fontSize: 26, letterSpacing: 3, color: `${ink}aa`, marginTop: 10 }}>
          {String(role).toUpperCase()}
        </div>
      )}
    </div>
  )
}

// ── 4. itemLabel (components/admin/BlankCanvasEditor.jsx, and the new LayersPanel)
//       gains the two kinds, and images prefer their asset name:
//
//    if (it.type === 'image') return it.srcName || (it.src ? 'Image' : 'Image (empty)')
//    if (it.type === 'data') return {
//      fixtures: 'Fixtures', results: 'Results', record: 'Record', scorecard: 'Scorecard',
//      player: 'Player stats', playerphoto: 'Player photo', playername: 'Player name',
//    }[it.kind] || 'Data'

// ── 5. itemBBox — the two new kinds are plain w/h boxes, so the existing default
//       branch already covers them. No change needed.
