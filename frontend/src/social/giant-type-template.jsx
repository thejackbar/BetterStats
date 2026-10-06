// Giant Type (C5): a player card built around one huge word or figure. "FIRST XI"
// for a captain, "100" or "5FA" for a milestone. The player stands in front of the
// big type, and the type comes back in front of them as an outline, so the two
// read as layers (a cut-out gets real depth; a plain photo still looks designed
// because the outline copy stays visible over it).
//
// It is the Announcement post type (the C1 fields): `kind` is the small chip,
// `headline` is the giant word, `subheadline` is the line under the name. A
// subheadline written as "100* · 83 balls · 12 fours" is drawn as a row of
// stats; one without a separator stays one line of text.
//
// Colours come from the palette: `primary` is the card, `secondary` the glow,
// `accent` the giant type and the chip, `ink` the name.
//
// `giantTypeSponsorSlot` is the ONE answer for where the sponsor grid goes (a slim
// pill centred under the name); the layout calls it, so the two cannot drift.
import { AutoFitText, ClubLogo, CreditMark, heroSrcOf } from './cricket-templates'
import { mixHex } from './split-template'
import { aspectOf, pick } from './postAspect'
import { LayerRoot } from './postLayers'
import { cornerLine, glowDisc, hatch, niceName, glowColor } from './card-kit'

const FONT = "var(--social-display-font, 'Anton', 'Hanken Grotesk', sans-serif)"
const WEIGHT = 'var(--social-display-font-weight, 700)'

export function giantTypeGeo(width = 1080, height = 1080, count = 0) {
  const A = aspectOf(width, height)
  const f = pick(A, { square: 0.84, portrait: 1, story: 1.1 })
  // A story's last couple of hundred pixels sit under the app's reply bar.
  const bottom = pick(A, { square: 36, portrait: 48, story: 240 })
  const slotH = count > 0 ? pick(A, { square: 84, portrait: 92, story: 100 }) : 0
  const slotGap = count > 0 ? 22 : 0
  const stackBottom = bottom + slotH + slotGap
  const wordTop = pick(A, { square: 96, portrait: 128, story: 250 })
  const wordMax = pick(A, { square: 440, portrait: 560, story: 640 })
  const photoTop = wordTop + Math.round(wordMax * 0.16)
  const photoBottomY = height - stackBottom - Math.round(196 * f)
  return { A, f, bottom, slotH, slotGap, stackBottom, wordTop, wordMax, photoTop, photoBottomY }
}

export function giantTypeSponsorSlot(width = 1080, height = 1080, count = 1) {
  const g = giantTypeGeo(width, height, Math.max(1, count))
  const n = Math.max(1, count)
  const w = Math.min(width - 260, n <= 1 ? 340 : n <= 3 ? 600 : 760)
  return { x: Math.round((width - w) / 2), y: height - g.bottom - g.slotH, w, h: g.slotH, pad: 6, gap: 22, panel: 'light' }
}

// "100* · 83 balls · 12 fours" -> three stats. Only `·` and `|` split a line, so
// a plain sentence ("For the 2026-27 season") is never cut up.
const statsOf = (s) => String(s || '').split(/\s*[·|]\s*/).map((t) => t.trim()).filter(Boolean)

export function GiantType({
  width = 1080, height = 1080, announcement, team = {}, match = {}, palette = {}, sponsorCount = 0, player: legacyPlayer,
}) {
  const a = announcement || {}
  const player = a.player || legacyPlayer
  const g = giantTypeGeo(width, height, sponsorCount)
  const { f } = g
  const accent = palette.accent || '#ffc233'
  const ink = palette.ink || '#ffffff'
  const base = palette.primary || '#0b1530'
  const glow = glowColor(palette, mixHex)
  const shade = mixHex(base, '#000000', 0.6)
  const word = String(a.headline || '').toUpperCase()
  const kind = String(a.kind || '').toUpperCase()
  const stats = statsOf(a.subheadline)
  const photo = heroSrcOf(player)
  const first = niceName(player?.first || '')
  const last = niceName(player?.last || '')
  const photoH = Math.max(0, g.photoBottomY - g.photoTop)
  const wordBoxH = Math.round(g.wordMax * 0.9)
  const wordStyle = { lineHeight: 0.9, letterSpacing: -2, textAlign: 'center', whiteSpace: 'nowrap' }

  return (
    <LayerRoot style={{
      width, height, position: 'relative', overflow: 'hidden', background: base, color: ink, fontFamily: FONT, fontWeight: WEIGHT,
    }}>
      {glowDisc('Glow', glow, { left: -Math.round(width * 0.05), top: Math.round(height * 0.12), size: Math.round(width * 1.1) })}
      {hatch('Hatch', ink, { left: 0, top: 0, width, height, gap: 14, angle: -45, opacity: 0.05 })}
      {cornerLine('Corner top left', accent, { width, height })}
      {cornerLine('Corner bottom right', accent, { width, height, flip: true })}

      <div data-layer="Giant type" style={{ position: 'absolute', left: 40, right: 40, top: g.wordTop, height: wordBoxH, color: accent }}>
        <AutoFitText text={word || '—'} max={g.wordMax} min={80} lines={1} measureDeps={[width, height, word]} style={wordStyle} />
      </div>

      {photo ? (
        <div data-layer="Player" style={{
          position: 'absolute', left: 0, top: g.photoTop, width, height: photoH, display: 'grid', placeItems: 'end center', overflow: 'hidden',
          WebkitMaskImage: 'linear-gradient(to bottom, #000 78%, transparent 100%)', maskImage: 'linear-gradient(to bottom, #000 78%, transparent 100%)',
        }}>
          <img src={photo} alt={last} style={{ height: photoH, width: 'auto', maxWidth: width - 40, objectFit: 'contain', objectPosition: 'bottom', display: 'block' }} />
        </div>
      ) : (
        <div data-layer="Club mark" style={{ position: 'absolute', left: Math.round(width / 2 - 200), top: g.photoTop + Math.round(photoH / 2 - 200), width: 400, height: 400, opacity: 0.9 }}>
          <ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={400} shape="shield" />
        </div>
      )}

      {/* The same word again, outline only, over the player. */}
      <div data-layer="Giant type outline" style={{
        position: 'absolute', left: 40, right: 40, top: g.wordTop, height: wordBoxH, pointerEvents: 'none',
        color: 'transparent', WebkitTextStroke: `${Math.max(2, Math.round(3 * f))}px ${ink}b8`,
      }}>
        <AutoFitText text={word || '—'} max={g.wordMax} min={80} lines={1} measureDeps={[width, height, word]} style={wordStyle} />
      </div>

      <div data-layer="Name shade" style={{
        position: 'absolute', left: 0, right: 0, bottom: 0, height: height - g.photoBottomY + Math.round(80 * f), pointerEvents: 'none',
        background: `linear-gradient(to bottom, ${shade}00 0%, ${shade}d9 38%, ${shade} 100%)`,
      }} />

      {kind && (
        <div data-layer="Kind chip" style={{
          position: 'absolute', left: 48, top: pick(g.A, { square: 44, portrait: 60, story: 170 }), padding: `${Math.round(8 * f)}px ${Math.round(16 * f)}px`,
          background: accent, color: base, fontSize: Math.round(24 * f), letterSpacing: 4, lineHeight: 1,
        }}>{kind}</div>
      )}
      <div data-layer="Club logo" style={{ position: 'absolute', right: 48, top: pick(g.A, { square: 36, portrait: 50, story: 160 }), width: Math.round(76 * f), height: Math.round(76 * f) }}>
        <ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={Math.round(76 * f)} shape="shield" />
      </div>

      <div data-layer="Name and line" style={{
        position: 'absolute', left: 48, right: 48, bottom: g.stackBottom, display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center',
      }}>
        {first && <div style={{ fontSize: Math.round(46 * f), letterSpacing: 2, lineHeight: 1, opacity: 0.85 }}>{first.toUpperCase()}</div>}
        <div style={{ width: '100%' }}>
          <AutoFitText text={(last || '—').toUpperCase()} max={Math.round(150 * f)} min={36} lines={1} measureDeps={[width, height, last]}
            style={{ color: ink, lineHeight: 1, letterSpacing: 0, textAlign: 'center' }} />
        </div>
        {stats.length > 1 ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: Math.round(22 * f), marginTop: Math.round(14 * f), flexWrap: 'wrap' }}>
            {stats.map((t, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: Math.round(22 * f) }}>
                {i > 0 && <span style={{ width: 2, height: Math.round(26 * f), background: accent, opacity: 0.8 }} />}
                <span style={{ fontSize: Math.round(30 * f), letterSpacing: 1.5, color: i === 0 ? accent : ink, lineHeight: 1.1 }}>{t.toUpperCase()}</span>
              </div>
            ))}
          </div>
        ) : (
          stats[0] && <div style={{ fontSize: Math.round(30 * f), letterSpacing: 2, color: accent, marginTop: Math.round(12 * f), lineHeight: 1.1 }}>{stats[0].toUpperCase()}</div>
        )}
      </div>

      <div data-layer="Platform credit" style={{ position: 'absolute', left: 0, right: 0, top: pick(g.A, { square: 52, portrait: 68, story: 178 }), display: 'flex', justifyContent: 'center', pointerEvents: 'none' }}>
        <CreditMark ink={ink} h={Math.round(34 * f)} />
      </div>
    </LayerRoot>
  )
}
GiantType.displayName = 'GiantType'

// Where this file's layouts keep the sponsor grid (see sponsorSlots.js).
export const SPONSOR_SLOTS = { C5: giantTypeSponsorSlot }
