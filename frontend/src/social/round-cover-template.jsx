// Round Cover (T13): the opening slide of a round's team lists. One hero photo
// on the right, a giant tone-on-tone word running up the left edge, the two club
// marks on glass badges, the round number large and the fixture and date below.
//
// Built for 4:5 first (the shape a club posts a carousel in) and reflowed for the
// square and the story through postAspect, like every other layout.
//
// The photo can be a cut-out or a plain photo. It is drawn `cover` in its own
// box and fades into the shade at the foot, so both read as intended; a
// cut-out stands in front of the word and the glow either way.
//
// Colours come from the palette: `primary` is the card, `secondary` the glow and
// the word on the left, `accent` the round number, `ink` the type. A club set up
// in green and gold gets a green card with a gold round number.
//
// `roundCoverSponsorSlot` is the ONE answer for where the sponsor grid goes; the
// layout calls it so the room it keeps and the place the grid sits cannot drift.
import { useState } from 'react'
import { AutoFitText, ClubLogo, CreditMark, heroFocusStyle } from './cricket-templates'
import { mixHex } from './split-template'
import { aspectOf, pick } from './postAspect'
import { LayerRoot } from './postLayers'
import { cornerLine, glowDisc, badgeStyle, glowColor } from './card-kit'

const FONT = "var(--social-display-font, 'Anton', 'Hanken Grotesk', sans-serif)"
const WEIGHT = 'var(--social-display-font-weight, 700)'

// Every measurement the layout and its sponsor slot share.
export function roundCoverGeo(width = 1080, height = 1080, count = 0) {
  const A = aspectOf(width, height)
  // A story's bottom couple of hundred pixels carry the app's reply bar.
  const bottom = pick(A, { square: 40, portrait: 52, story: 250 })
  const slotH = count > 0 ? pick(A, { square: 92, portrait: 100, story: 108 }) : 0
  const slotGap = count > 0 ? 24 : 0
  const wordW = pick(A, { square: 150, portrait: 172, story: 172 })
  const shadeH = pick(A, { square: 500, portrait: 600, story: 760 })
  const logoH = pick(A, { square: 70, portrait: 80, story: 88 })
  const logoW = Math.round(logoH * 1.5)
  const roundMax = pick(A, { square: 150, portrait: 196, story: 214 })
  const lineMax = pick(A, { square: 30, portrait: 34, story: 36 })
  const dateMax = pick(A, { square: 21, portrait: 24, story: 26 })
  const stackBottom = bottom + slotH + slotGap
  const heroTop = pick(A, { square: 24, portrait: 44, story: 140 })
  // The photo stops partway down the shade, so a standing player's lower body
  // fades out under the type rather than ending on a hard edge.
  const heroBottom = height - Math.round(shadeH * 0.42)
  return { A, bottom, slotH, slotGap, wordW, shadeH, logoH, logoW, roundMax, lineMax, dateMax, stackBottom, heroTop, heroBottom }
}

// The sponsor grid sits in a slim strip under the date, centred.
export function roundCoverSponsorSlot(width = 1080, height = 1080, count = 1) {
  const g = roundCoverGeo(width, height, Math.max(1, count))
  const w = Math.min(width - 260, count <= 1 ? 360 : count <= 3 ? 620 : 760)
  return { x: Math.round((width - w) / 2), y: height - g.bottom - g.slotH, w, h: g.slotH, pad: 6, gap: 22, panel: 'light' }
}

export function RoundCover({
  width = 1080, height = 1080, team = {}, opponent = {}, match = {}, palette = {}, heroImage, heroFocus,
  headline, sponsorCount = 0,
}) {
  const g = roundCoverGeo(width, height, sponsorCount)
  // A tall cut-out is shown whole, standing in the box; a wide photo fills it.
  // Which one it is comes from the picture's own shape, read once it loads.
  const [shape, setShape] = useState(0)
  const accent = palette.accent || '#ffc233'
  const ink = palette.ink || '#ffffff'
  const base = palette.primary || '#0b1530'
  const glow = glowColor(palette, mixHex)
  const wordInk = mixHex(glow, base, 0.35)
  const shade = mixHex(base, '#000000', 0.55)
  const fixture = `${team.name || ''} vs ${opponent.name || ''}`.toUpperCase()
  const round = String(match.round || '').toUpperCase()
  const when = [match.date, match.time].filter(Boolean).join(' · ').toUpperCase()
  const side = String(headline || '').trim().toUpperCase()
  const heroW = width - Math.round(g.wordW * 0.62)
  const heroH = g.heroBottom - g.heroTop
  // The word is set on its own box and turned a quarter turn clockwise (it reads
  // top to bottom), so the box is the post's height wide and `AutoFitText` fits
  // the word to it.
  const wordBox = height - 24
  const wordSize = Math.round(g.wordW * 1.12)

  return (
    <LayerRoot style={{
      width, height, position: 'relative', overflow: 'hidden', background: base, color: ink, fontFamily: FONT, fontWeight: WEIGHT,
    }}>
      {glowDisc('Glow', glow, { left: Math.round(width * 0.06), top: -Math.round(height * 0.08), size: Math.round(width * 1.05) })}

      <div data-layer="Side word" style={{
        position: 'absolute', left: wordSize + 6, top: 12, width: wordBox, height: wordSize,
        transform: 'rotate(90deg)', transformOrigin: '0 0', color: wordInk, pointerEvents: 'none',
      }}>
        <AutoFitText text="SELECTION" max={wordSize} min={40} lines={1} measureDeps={[width, height]}
          style={{ lineHeight: 0.95, letterSpacing: 2, textAlign: 'left' }} />
      </div>

      {cornerLine('Corner top left', accent, { width, height })}
      {cornerLine('Corner bottom right', accent, { width, height, flip: true })}

      {heroImage && (
        <div data-layer="Hero photo" style={{
          position: 'absolute', left: width - heroW, top: g.heroTop, width: heroW, height: heroH, overflow: 'hidden',
          WebkitMaskImage: 'linear-gradient(to bottom, #000 62%, transparent 100%)',
          maskImage: 'linear-gradient(to bottom, #000 62%, transparent 100%)',
        }}>
          <img src={heroImage} alt="" onLoad={(e) => setShape(e.currentTarget.naturalWidth / (e.currentTarget.naturalHeight || 1))}
            style={{ width: '100%', height: '100%', objectFit: shape && shape < (heroW / heroH) * 0.8 ? 'contain' : 'cover', display: 'block', ...heroFocusStyle(heroFocus) }} />
        </div>
      )}

      <div data-layer="Shade" style={{
        position: 'absolute', left: 0, right: 0, bottom: 0, height: g.shadeH, pointerEvents: 'none',
        background: `linear-gradient(to bottom, ${shade}00 0%, ${shade}66 12%, ${shade}f2 44%, ${shade} 100%)`,
      }} />

      <div data-layer="Round and fixture" style={{
        position: 'absolute', left: 48, right: 48, bottom: g.stackBottom, display: 'flex', flexDirection: 'column',
        alignItems: 'center', textAlign: 'center',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 18, marginBottom: Math.round(g.logoH * 0.4) }}>
          <div style={badgeStyle(g.logoW, g.logoH)}>
            <ClubLogo src={team.logo} monogram={team.monogram} color={ink} size={g.logoH - 14} shape="shield" />
          </div>
          <div style={{ fontSize: Math.round(g.logoH * 0.62), lineHeight: 1, color: ink, opacity: 0.9 }}>V</div>
          <div style={badgeStyle(g.logoW, g.logoH)}>
            <ClubLogo src={opponent.logo} monogram={opponent.monogram} color={ink} size={g.logoH - 14} shape="shield" />
          </div>
        </div>
        {side && (
          <div style={{ fontSize: Math.round(g.lineMax * 0.8), letterSpacing: 4, color: ink, opacity: 0.8, marginBottom: 6 }}>{side}</div>
        )}
        <div style={{ width: '100%' }}>
          <AutoFitText text={round || 'ROUND'} max={g.roundMax} min={48} lines={1} measureDeps={[width, height]}
            style={{ color: accent, lineHeight: 0.98, letterSpacing: 1, textAlign: 'center', textShadow: '0 4px 24px rgba(0,0,0,0.45)' }} />
        </div>
        <div style={{ width: '100%', marginTop: 14 }}>
          <AutoFitText text={fixture} max={g.lineMax} min={14} lines={1} measureDeps={[width, height]}
            style={{ color: ink, lineHeight: 1.25, letterSpacing: 1, textAlign: 'center' }} />
        </div>
        {when && (
          <div style={{ width: '100%', marginTop: 4, opacity: 0.85 }}>
            <AutoFitText text={when} max={g.dateMax} min={12} lines={1} measureDeps={[width, height]}
              style={{ color: ink, lineHeight: 1.4, letterSpacing: 1.5, textAlign: 'center' }} />
          </div>
        )}
      </div>

      <div data-layer="Platform credit" style={{ position: 'absolute', right: 40, top: pick(g.A, { square: 40, portrait: 52, story: 170 }), height: 38, display: 'flex', alignItems: 'center' }}>
        <CreditMark ink={ink} h={38} />
      </div>
    </LayerRoot>
  )
}
RoundCover.displayName = 'RoundCover'

// Where this file's layouts keep the sponsor grid (see sponsorSlots.js).
export const SPONSOR_SLOTS = { T13: roundCoverSponsorSlot }
