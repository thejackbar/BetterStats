// BetterCricket — Event / Announcement posters. The whitelabel club-event suite
// (Auction Night, 100 Club, Curry Night, Selections, Presentation Night, …).
//
// Same contract as cricket-templates / round-templates so these slot straight
// into the Post Designer (AdminSocialPost) and capture through the shared
// modern-screenshot pipeline (exportImage.js):
//   • every template renders full-bleed at exactly 1080×1080
//   • colour comes from the active `palette` ({ primary, secondary, accent, ink })
//   • display type reads `var(--social-display-font, …)` where it should follow
//     the font picker; stylised directions (Gazette/Ticket/Sticker/…) keep a
//     signature face so the look survives.
//
// WHITELABEL FACTS — the editable post copy lives in one `event` object:
//   { kicker, title, subtitle, date, time, venue, price, cta, sponsor }
//
// BACKGROUNDS — the "curry behind Curry Night / guitar behind Music Night" idea:
//   `motif` = { imageUrl, icon, opacity, label }
//     · imageUrl — a user-uploaded photo, drawn full-bleed behind a dark/accent
//       scrim at `opacity` so text stays legible (the headline feature).
//     · icon — a bundled 3D "thiings" glyph used as a faded watermark when no
//       photo is supplied (auto-picked per preset, override in the editor).
import { AutoFitText, BrandLockup, ClubLogo, GrainSVG, Halftone, Stripes } from './cricket-templates'
import { IS_AFL, PLATFORM_NAME } from '../lib/sport'
import { aspectOf, pick, share } from './postAspect'
import { LayerRoot } from './postLayers'
import { EVENT_LIST_TEMPLATES, SPONSOR_SLOTS as LIST_SLOTS, MAX_LIST_ITEMS } from './event-list-templates'
import { pc, pt, inkOn, registerParts, colorPart, textPart, picked as partPicked } from './layoutParts'
import { usePostLook } from './postLook'

// Bundled motif glyphs (already in the repo at src/assets/thiings/).
import icoTrophy from '../assets/thiings/trophy.png'
import icoMedal from '../assets/thiings/gold-medal.png'
import icoHandshake from '../assets/thiings/handshake.png'
import icoBat from '../assets/thiings/cricket-bat.png'
import icoStar from '../assets/thiings/star.png'
import icoTarget from '../assets/thiings/target.png'
import icoBolt from '../assets/thiings/lightning-bolt.png'
import icoCalendar from '../assets/thiings/calendar.png'
import icoNecktie from '../assets/thiings/necktie.png'
import icoRibbon from '../assets/thiings/ribbon.png'
import { pc, pt, inkOn, registerParts, colorPart, textPart, picked as partPicked } from './layoutParts'
import { usePostLook } from './postLook'

// Append an 8-bit alpha to a 6-digit hex (palette colours are always #rrggbb).
const a = (hex, alpha) => {
  if (!hex || hex[0] !== '#' || hex.length < 7) return hex
  return hex + Math.round(Math.max(0, Math.min(1, alpha)) * 255).toString(16).padStart(2, '0')
}

const MONO = "'JetBrains Mono', monospace"
// Sporty directions follow the global font picker; the var falls back to the
// direction's own face when the picker hasn't set one.
const SPORT = "var(--social-display-font, 'Barlow Condensed', sans-serif)"

// Small pink BetterCricket chip-mark used as the export watermark.
function BSMark({ size = 22, color = '#f25aa6' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" style={{ flexShrink: 0 }}>
      <path d="M22 32 L43 19 M22 32 L43 45" fill="none" stroke={color} strokeWidth="5" strokeLinecap="round" />
      <circle cx="20" cy="32" r="8" fill={color} />
      <circle cx="44" cy="18" r="8" fill={color} />
      <circle cx="44" cy="46" r="8" fill={color} />
    </svg>
  )
}

// Full-bleed photo layer + scrim for the directions that take a hero image.
// Falls back to a diagonal accent weave (so the slot reads even with no photo).
function PhotoLayer({ motif, palette, height = '100%', scrimFrom = 0.04, label, parts }) {
  const P = palette
  const texture = usePostLook().texture !== false
  return (
    <div style={{ position: 'absolute', left: 0, top: 0, right: 0, height, overflow: 'hidden' }}>
      {motif?.imageUrl ? (
        <img src={motif.imageUrl} alt="" crossOrigin="anonymous"
          style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: motif.opacity ?? 0.85 }} />
      ) : (
        <div style={{ position: 'absolute', inset: 0, background: texture ? `repeating-linear-gradient(135deg, ${P.primary} 0px, ${P.primary} 17px, ${a(P.accent, 0.1)} 17px, ${a(P.accent, 0.1)} 34px)` : P.primary }}>
          <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 14, opacity: 0.5 }}>
            <div style={{ width: 60, height: 60, border: `2px solid ${a(P.accent, 0.45)}`, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <div style={{ width: 22, height: 22, border: `2px solid ${a(P.accent, 0.45)}`, borderRadius: '50%' }} />
            </div>
            <div style={{ fontFamily: MONO, fontSize: 15, letterSpacing: 3, textTransform: 'uppercase', color: a(P.accent, 0.55) }}>{label || 'Add a photo'}</div>
          </div>
        </div>
      )}
      <div style={{ position: 'absolute', inset: 0, background: `linear-gradient(180deg, ${a(pc(parts, 'photoGlow', P.accent), 0.16)} 0%, transparent 38%), linear-gradient(0deg, ${pc(parts, 'photoFade', P.primary)} ${scrimFrom * 100}%, transparent 64%)` }} />
    </div>
  )
}

// Club lockup (logo or monogram shield + name) used across several directions.
function ClubLockup({ team, palette, color }) {
  const ink = color || palette.ink
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
      {team.logo
        ? <ClubLogo src={team.logo} size={100} />
        : <ClubLogo monogram={team.monogram} color={palette.accent} size={100} shape="shield" />}
      <div style={{ fontFamily: SPORT, fontSize: 36, fontWeight: 700, letterSpacing: 3, textTransform: 'uppercase', color: ink, lineHeight: 0.95, maxWidth: 460 }}>{team.fullName || team.name}</div>
    </div>
  )
}

function Watermark({ sponsor, color = 'rgba(255,255,255,0.42)', parts }) {
  const credit = pc(parts, 'creditColor', color)
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <BSMark color={pc(parts, 'markColor', '#f25aa6')} />
        <span style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 2, textTransform: 'uppercase', color: credit }}>Made with {PLATFORM_NAME}</span>
      </div>
      {sponsor ? <div style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 2, textTransform: 'uppercase', color: pc(parts, 'sponsorColor', credit) }}>{sponsor}</div> : null}
    </div>
  )
}

// The post's real size lands here, once, for all eleven event posters. Called
// rather than spread so a template can't silently keep the old fixed square by
// forgetting to pass its own width and height through.
const FRAME = (width = 1080, height = 1080) => ({
  width, height, position: 'relative', overflow: 'hidden',
  fontFamily: "'Inter', sans-serif", boxSizing: 'border-box',
})

// `share`, `grow` and `pick` come from postAspect — one definition across all
// three template families, so an event poster and a fixture list cannot end up
// with different ideas of how a band grows.

// A headline slot sized to exactly TWO lines at its own max font. AutoFitText
// clamps a 2-line headline and only shrinks on HEIGHT overflow, so a slot taller
// than two lines lets it fit a THREE-line block and then the clamp truncates the
// third line to an ellipsis (seen on a long "Grand Final Awards Presentation").
// Sizing the slot to two lines forces the shrink to land on two real lines. The
// font is capped at `max` regardless, so a taller canvas gains nothing from a
// taller slot — its extra height belongs in the flex spacers, not here.
const twoLineBox = (max, lineHeight) => Math.round(2 * max * lineHeight) + 12

// SPONSOR SLOTS. Every poster reserves a rectangle for the club's sponsor grid
// and the layout calls the SAME slot function to keep that rectangle clear, so
// the space and the grid cannot drift apart (see sponsorSlots.js). Pad stays
// small (8) so the logos, not the backing panel, are what you read.
const SLOT_PAD = 8
const SLOT_GAP = 24
const slotRect = (width, height, { x, bottom, h, panel = 'light' }) => ({
  x, y: height - bottom - h, w: width - 2 * x, h, pad: SLOT_PAD, gap: SLOT_GAP, panel,
})

// ─────────────────────────────────────────────────────────────────────────────
// EV1 — FLOODLIT · full-bleed photo + opacity filter (sporty, BetterStats-native)
// ─────────────────────────────────────────────────────────────────────────────
// Floodlit: the grid is a full-width strip along the foot, on the dark field
// below the photo band, with the whole text column sitting above it.
const slotEV1 = (width, height) => {
  const A = aspectOf(width, height)
  return slotRect(width, height, { x: 64, bottom: pick(A, { square: 40, portrait: 44, story: 120 }), h: pick(A, { square: 112, portrait: 120, story: 136 }) })
}
export function EVT_Floodlit({ team, event = {}, width = 1080, height = 1080, palette, motif, parts }) {
  const P = palette
  const A = aspectOf(width, height)
  const slot = slotEV1(width, height)
  const texture = usePostLook().texture !== false
  const priceBg = pc(parts, 'priceBg', P.accent)
  const rule = pc(parts, 'dividerColor', 'rgba(255,255,255,0.16)')
  return (
    <LayerRoot style={{ ...FRAME(width, height), background: P.primary, color: '#fff' }}>
      <PhotoLayer motif={motif} palette={P} height={share(height, 680)} scrimFrom={0.04} label={motif?.label} parts={parts} />
      {texture ? <div style={{ position: 'absolute', left: -180, top: -180, width: 520, height: 520, borderRadius: '50%', background: `radial-gradient(circle, ${a(pc(parts, 'glowColor', P.accent), 0.3)}, transparent 68%)`, pointerEvents: 'none' }} /> : null}

      <div style={{ position: 'absolute', top: 56, left: 64, right: 64, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <ClubLockup team={team} palette={P} color={pc(parts, 'clubColor', '#fff')} />
        <div style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 3, textTransform: 'uppercase', color: pc(parts, 'badgeColor', P.accent), border: `1.5px solid ${pc(parts, 'badgeBorder', a(P.accent, 0.45))}`, borderRadius: 999, padding: '9px 18px', background: a(pc(parts, 'badgeBg', P.accent), 0.1) }}>{pt(parts, 'badgeText', 'Club Event')}</div>
      </div>

      <div style={{ position: 'absolute', left: 64, right: 64, bottom: height - slot.y + 22, display: 'flex', flexDirection: 'column' }}>
        <div style={{ fontFamily: MONO, fontSize: 18, letterSpacing: 6, textTransform: 'uppercase', color: pc(parts, 'kickerColor', P.accent), marginBottom: 14 }}>{event.kicker}</div>
        <div style={{ height: twoLineBox(148, 0.86), display: 'flex', alignItems: 'flex-end' }}>
          <AutoFitText text={(event.title || '').toUpperCase()} max={148} min={56} lines={2} measureDeps={[event.title]}
            style={{ fontFamily: SPORT, fontWeight: 800, lineHeight: 0.86, textTransform: 'uppercase', color: pc(parts, 'titleColor', '#fff'), letterSpacing: 1 }} />
        </div>
        {event.subtitle ? <div style={{ fontSize: 30, color: pc(parts, 'subtitleColor', 'rgba(255,255,255,0.78)'), marginTop: pick(A, { square: 16, portrait: 22 }), maxWidth: 760, lineHeight: 1.3 }}>{event.subtitle}</div> : null}

        <div style={{ display: 'flex', marginTop: pick(A, { square: 28, portrait: 40 }), borderTop: `1px solid ${rule}`, borderBottom: `1px solid ${rule}` }}>
          {[['Date', event.date], ['Time', event.time], ['Venue', event.venue]].map(([l, v], i) => (
            <div key={l} style={{ flex: i === 2 ? 1.4 : 1, padding: i ? '22px 0 22px 28px' : '22px 0', borderLeft: i ? `1px solid ${rule}` : 'none' }}>
              <div style={{ fontFamily: MONO, fontSize: 14, letterSpacing: 3, textTransform: 'uppercase', color: pc(parts, 'labelColor', 'rgba(255,255,255,0.45)') }}>{l}</div>
              <div style={{ fontFamily: SPORT, fontWeight: 700, fontSize: 38, color: pc(parts, 'valueColor', '#fff'), marginTop: 6 }}>{v}</div>
            </div>
          ))}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 20, marginTop: pick(A, { square: 22, portrait: 30 }) }}>
          {event.price ? <div style={{ background: priceBg, color: pc(parts, 'priceColor', partPicked(parts, 'priceBg') ? inkOn(priceBg) : P.primary), fontFamily: SPORT, fontWeight: 800, fontSize: 40, textTransform: 'uppercase', letterSpacing: 1, padding: '12px 26px', borderRadius: 10 }}>{event.price}</div> : null}
          {event.cta ? <div style={{ fontFamily: MONO, fontSize: 17, letterSpacing: 2, textTransform: 'uppercase', color: pc(parts, 'ctaColor', 'rgba(255,255,255,0.7)') }}>{event.cta}</div> : null}
        </div>

        <div style={{ marginTop: pick(A, { square: 20, portrait: 30 }) }}><Watermark sponsor={event.sponsor} parts={parts} /></div>
      </div>
    </LayerRoot>
  )
}
registerParts({
  EV1: [
    colorPart('photoFade', 'Photo fade at the foot', 'Photo', (p) => p.primary),
    colorPart('photoGlow', 'Photo top tint', 'Photo', (p) => p.accent),
    colorPart('glowColor', 'Corner glow', 'Photo', (p) => p.accent),
    colorPart('clubColor', 'Club name', 'Heading', () => '#ffffff'),
    colorPart('kickerColor', 'Line above the title', 'Heading', (p) => p.accent),
    colorPart('titleColor', 'Title', 'Heading', () => '#ffffff'),
    colorPart('subtitleColor', 'Subtitle', 'Heading', () => '#ffffff'),
    textPart('badgeText', 'Tag words', 'Tag', () => 'Club Event'),
    colorPart('badgeColor', 'Tag text', 'Tag', (p) => p.accent),
    colorPart('badgeBg', 'Tag fill', 'Tag', (p) => p.accent),
    colorPart('badgeBorder', 'Tag outline', 'Tag', (p) => p.accent),
    colorPart('dividerColor', 'Lines around the details', 'Details', () => '#ffffff'),
    colorPart('labelColor', 'Detail captions', 'Details', () => '#ffffff'),
    colorPart('valueColor', 'Date, time and venue', 'Details', () => '#ffffff'),
    colorPart('priceBg', 'Price tag', 'Price and action', (p) => p.accent),
    colorPart('priceColor', 'Price text', 'Price and action', (p) => p.primary),
    colorPart('ctaColor', 'Call to action', 'Price and action', () => '#ffffff'),
    colorPart('creditColor', 'Made with line', 'Footer', () => '#ffffff'),
    colorPart('sponsorColor', 'Sponsor line', 'Footer', () => '#ffffff'),
    colorPart('markColor', 'Logo mark', 'Footer', () => '#f25aa6'),
  ],
})

// ─────────────────────────────────────────────────────────────────────────────
// EV2 — COLOUR BLOCK · club colour leads, giant motif (bold, high-energy)
// ─────────────────────────────────────────────────────────────────────────────
// Colour Block: the grid is a strip along the foot of the dark detail panel, under
// the little watermark line. The colour band gives up some height on the square
// to pay for it.
const slotEV2 = (width, height) => {
  const A = aspectOf(width, height)
  return slotRect(width, height, { x: 64, bottom: pick(A, { square: 36, portrait: 44, story: 120 }), h: pick(A, { square: 100, portrait: 116, story: 136 }) })
}
export function EVT_Block({ team, event = {}, width = 1080, height = 1080, palette, motif, parts }) {
  const P = palette
  const aspect = aspectOf(width, height)
  const slot = slotEV2(width, height)
  const texture = usePostLook().texture !== false
  const band = pc(parts, 'bandBg', P.accent)
  const cellBg = pc(parts, 'cardBg', P.primary)
  const ctaBg = pc(parts, 'ctaBg', P.accent)
  const ctaText = pc(parts, 'ctaColor', partPicked(parts, 'ctaBg') ? inkOn(ctaBg) : P.primary)
  const rule = pc(parts, 'dividerColor', 'rgba(255,255,255,0.12)')
  // The colour band is a touch shorter on the square so the detail panel has
  // room for all four cells + the CTA + the sponsor strip. Portrait/story keep
  // their share of the canvas.
  const bandH = pick(aspect, { square: 480, portrait: 650, story: share(height, 606) })
  const tight = aspect === 'square'
  return (
    <LayerRoot style={{ ...FRAME(width, height), background: P.primary, color: '#fff' }}>
      <div style={{ position: 'absolute', left: 0, top: 0, right: 0, height: bandH, background: `linear-gradient(150deg, ${band} 0%, ${a(band, 0.78)} 100%)`, overflow: 'hidden' }}>
        {motif?.imageUrl
          ? <img src={motif.imageUrl} alt="" crossOrigin="anonymous" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: 0.3, mixBlendMode: 'overlay' }} />
          : (texture ? <img src={motif?.icon || icoHandshake} alt="" style={{ position: 'absolute', right: -130, top: 54, width: 560, height: 560, objectFit: 'contain', opacity: 0.26, transform: 'rotate(-8deg)' }} /> : null)}
        {texture ? <div style={{ position: 'absolute', right: -220, top: -40, width: 560, height: 560, borderRadius: '50%', background: `radial-gradient(circle, ${partPicked(parts, 'glowColor') ? a(parts.glowColor, 0.18) : 'rgba(255,255,255,0.18)'}, transparent 66%)` }} /> : null}

        <div style={{ position: 'absolute', top: tight ? 44 : 60, left: 64, right: 64, display: 'flex', alignItems: 'center', gap: 16 }}>
          <BrandLockup team={team} palette={P} size={tight ? 84 : 96} nameColor={pc(parts, 'clubColor', '#fff')} nameSize={tight ? 30 : 32} />
          <div style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 13, letterSpacing: 3, textTransform: 'uppercase', color: pc(parts, 'badgeColor', '#fff'), border: `1.5px solid ${pc(parts, 'badgeBorder', 'rgba(255,255,255,0.55)')}`, borderRadius: 999, padding: '9px 18px' }}>{pt(parts, 'badgeText', 'Club Event')}</div>
        </div>

        <div style={{ position: 'absolute', left: 64, right: 64, bottom: tight ? 38 : 52 }}>
          <div style={{ fontFamily: MONO, fontSize: 18, letterSpacing: 6, textTransform: 'uppercase', color: pc(parts, 'kickerColor', 'rgba(255,255,255,0.9)'), marginBottom: tight ? 10 : 16 }}>{event.kicker}</div>
          <div style={{ height: twoLineBox(tight ? 144 : 158, 0.82), display: 'flex', alignItems: 'flex-end' }}>
            <AutoFitText text={(event.title || '').toUpperCase()} max={tight ? 144 : 158} min={56} lines={2} measureDeps={[event.title]}
              style={{ fontFamily: SPORT, fontWeight: 800, lineHeight: 0.82, textTransform: 'uppercase', color: pc(parts, 'titleColor', '#fff'), letterSpacing: 1, textShadow: '0 4px 30px rgba(0,0,0,0.18)' }} />
          </div>
        </div>
      </div>

      <div style={{ position: 'absolute', left: 0, top: bandH, right: 0, bottom: height - slot.y + 12, padding: pick(aspect, { square: '26px 64px 0', portrait: '46px 64px 0', story: '54px 64px 0' }), boxSizing: 'border-box', display: 'flex', flexDirection: 'column' }}>
        {event.subtitle ? <div style={{ fontSize: pick(aspect, { square: 25, portrait: 27, story: 29 }), color: pc(parts, 'subtitleColor', 'rgba(255,255,255,0.74)'), lineHeight: 1.3, maxWidth: 840, marginBottom: pick(aspect, { square: 16, portrait: 30, story: 34 }), flexShrink: 0 }}>{event.subtitle}</div> : null}
        {/* The four details SHARE whatever the panel has left, at every size, so
            they fill the space and centre their content instead of the fixed
            2×2 stack running past the panel (the square used to clip its bottom
            row). A long value wraps to two lines rather than being truncated. */}
        <div style={{
          flex: 1, minHeight: 0, display: 'grid', gridTemplateColumns: '1fr 1fr', gridTemplateRows: 'repeat(2, minmax(0, 1fr))', gap: 1,
          background: rule, border: `1px solid ${rule}`, borderRadius: 14, overflow: 'hidden',
        }}>
          {[['Date', event.date], ['Time', event.time], ['Venue', event.venue], [pt(parts, 'entryLabel', 'Entry'), event.price]].map(([l, v]) => (
            <div key={l} style={{ background: cellBg, padding: tight ? '10px 24px' : '16px 24px', minHeight: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center', overflow: 'hidden' }}>
              <div style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 3, textTransform: 'uppercase', color: pc(parts, 'labelColor', P.accent), marginBottom: 5 }}>{l}</div>
              <div style={{ fontFamily: SPORT, fontWeight: 700, fontSize: pick(aspect, { square: 34, portrait: 40, story: 44 }), color: pc(parts, 'valueColor', partPicked(parts, 'cardBg') ? inkOn(cellBg) : '#fff'), lineHeight: 1.04, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{v}</div>
            </div>
          ))}
        </div>
        {event.cta ? (
          <div style={{ marginTop: pick(aspect, { square: 14, portrait: 26, story: 28 }), flexShrink: 0, background: ctaBg, borderRadius: 14, padding: pick(aspect, { square: '12px 28px', portrait: '20px 28px', story: '22px 30px' }), display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
            <span style={{ fontFamily: SPORT, fontWeight: 800, fontSize: pick(aspect, { square: 36, portrait: 42, story: 44 }), textTransform: 'uppercase', letterSpacing: 1, color: ctaText, lineHeight: 1 }}>{event.cta}</span>
            <span style={{ fontFamily: MONO, fontSize: 15, color: ctaText, opacity: 0.7, flexShrink: 0 }}>↗</span>
          </div>
        ) : null}
        <div style={{ marginTop: 'auto', flexShrink: 0, paddingTop: pick(aspect, { square: 12, portrait: 28, story: 30 }) }}><Watermark sponsor={event.sponsor} parts={parts} /></div>
      </div>
    </LayerRoot>
  )
}
registerParts({
  EV2: [
    colorPart('bandBg', 'Colour band', 'Colour band', (p) => p.accent),
    colorPart('glowColor', 'Corner glow', 'Colour band', () => '#ffffff'),
    colorPart('clubColor', 'Club name', 'Colour band', () => '#ffffff'),
    textPart('badgeText', 'Tag words', 'Colour band', () => 'Club Event'),
    colorPart('badgeColor', 'Tag text', 'Colour band', () => '#ffffff'),
    colorPart('badgeBorder', 'Tag outline', 'Colour band', () => '#ffffff'),
    colorPart('kickerColor', 'Line above the title', 'Colour band', () => '#ffffff'),
    colorPart('titleColor', 'Title', 'Colour band', () => '#ffffff'),
    colorPart('subtitleColor', 'Subtitle', 'Details panel', () => '#ffffff'),
    colorPart('dividerColor', 'Lines between details', 'Details panel', () => '#ffffff'),
    colorPart('cardBg', 'Detail boxes', 'Details panel', (p) => p.primary),
    colorPart('labelColor', 'Detail captions', 'Details panel', (p) => p.accent),
    colorPart('valueColor', 'Detail values', 'Details panel', () => '#ffffff'),
    textPart('entryLabel', 'Price caption', 'Details panel', () => 'Entry'),
    colorPart('ctaBg', 'Call to action bar', 'Call to action', (p) => p.accent),
    colorPart('ctaColor', 'Call to action text', 'Call to action', (p) => p.primary),
    colorPart('creditColor', 'Made with line', 'Footer', () => '#ffffff'),
    colorPart('sponsorColor', 'Sponsor line', 'Footer', () => '#ffffff'),
    colorPart('markColor', 'Logo mark', 'Footer', () => '#f25aa6'),
  ],
})

// ─────────────────────────────────────────────────────────────────────────────
// EV3 — TICKET · refined, editorial, motif watermark (premium occasions)
// Light "paper" surface: uses palette.ink for paper, primary for type.
// ─────────────────────────────────────────────────────────────────────────────
// Ticket: the grid is a strip inside the double rule, under the small footer line.
const slotEV3 = (width, height) => {
  const A = aspectOf(width, height)
  return slotRect(width, height, { x: 100, bottom: pick(A, { square: 76, portrait: 80, story: 110 }), h: pick(A, { square: 104, portrait: 116, story: 132 }) })
}
export function EVT_Ticket({ team, event = {}, width = 1080, height = 1080, palette, motif, parts }) {
  const P = palette
  const aspect = aspectOf(width, height)
  const slot = slotEV3(width, height)
  const tight = aspect === 'square'
  const texture = usePostLook().texture !== false
  const paper = pc(parts, 'paperColor', P.paper || '#f4efe4')
  const ink = pc(parts, 'deepInkColor', P.deepInk || '#1f1c14')
  const line = a(ink, 0.2)
  const rule = pc(parts, 'dividerColor', line)
  const tear = pc(parts, 'ev3TearLine', line)
  const stampBg = pc(parts, 'badgeBg', paper)
  const SERIF = "'Cormorant Garamond', serif"
  return (
    <LayerRoot style={{ ...FRAME(width, height), background: paper, color: ink, fontFamily: SERIF }}>
      {texture ? <img src={motif?.icon || icoTrophy} alt="" style={{ position: 'absolute', left: '50%', top: share(height, 300), transform: 'translateX(-50%)', width: 600, height: 600, objectFit: 'contain', opacity: 0.12 }} /> : null}
      <div style={{ position: 'absolute', inset: 42, border: `1.5px solid ${pc(parts, 'frameColor', line)}`, pointerEvents: 'none' }} />
      <div style={{ position: 'absolute', inset: 50, border: `1px solid ${pc(parts, 'frameInnerColor', a(ink, 0.12))}`, pointerEvents: 'none' }} />

      {/* Stamp lives in the top-right corner (the content is centred, so that
          corner is always clear) rather than at a fixed y that the headline
          slides under on a taller canvas. */}
      {event.price ? (
        <div style={{ position: 'absolute', top: pick(aspect, { square: 118, portrait: 130, story: 150 }), right: 94, width: 138, height: 138, borderRadius: '50%', border: `2px solid ${pc(parts, 'badgeBorder', P.accent)}`, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', transform: 'rotate(-9deg)', background: stampBg }}>
          <div style={{ fontFamily: MONO, fontSize: 12, letterSpacing: 3, textTransform: 'uppercase', color: pc(parts, 'badgeColor', P.accent) }}>{pt(parts, 'entryLabel', 'Entry')}</div>
          <div style={{ fontFamily: SERIF, fontWeight: 600, fontSize: 46, lineHeight: 1, color: pc(parts, 'priceColor', partPicked(parts, 'badgeBg') ? inkOn(stampBg) : ink), marginTop: 2 }}>{event.price}</div>
        </div>
      ) : null}

      <div style={{ position: 'absolute', top: tight ? 80 : 92, left: 100, right: 100, bottom: height - slot.y + 14, display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
        <div style={{ flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: tight ? 10 : 16 }}>
          {team.logo ? <ClubLogo src={team.logo} size={tight ? 80 : 98} /> : <ClubLogo monogram={team.monogram} color={P.accent} size={tight ? 80 : 98} shape="shield" />}
          <div style={{ display: 'flex', alignItems: 'center', gap: 18, maxWidth: '84%' }}>
            <div style={{ width: 44, height: 1, background: rule, flexShrink: 0 }} />
            <div style={{ fontFamily: SPORT, fontSize: 30, fontWeight: 700, letterSpacing: 2, textTransform: 'uppercase', color: pc(parts, 'clubColor', ink), lineHeight: 0.98 }}>{team.fullName || team.name}</div>
            <div style={{ width: 44, height: 1, background: rule, flexShrink: 0 }} />
          </div>
        </div>

        {/* Hero + ticket stub as ONE block, centred in the leftover space (auto
            margins top and bottom) — the poster reads as a ticket with its
            details, not three groups flung to the top, middle and edges. */}
        <div style={{ marginTop: 'auto', marginBottom: 'auto', width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: tight ? 14 : 30 }}>
          <div style={{ fontFamily: MONO, fontSize: 17, letterSpacing: 6, textTransform: 'uppercase', color: pc(parts, 'kickerColor', P.accent), marginBottom: tight ? 10 : 16 }}>{event.kicker}</div>
          <div style={{ height: twoLineBox(tight ? 136 : 158, 0.92), display: 'flex', alignItems: 'center', width: '100%' }}>
            <AutoFitText text={event.title} max={tight ? 136 : 158} min={60} lines={2} measureDeps={[event.title]}
              style={{ fontFamily: SERIF, fontWeight: 600, lineHeight: 0.92, color: pc(parts, 'titleColor', ink), letterSpacing: 1, textAlign: 'center', width: '100%' }} />
          </div>
          {event.subtitle ? <div style={{ fontFamily: SERIF, fontStyle: 'italic', fontWeight: 500, fontSize: pick(aspect, { square: 31, portrait: 37, story: 39 }), color: pc(parts, 'subtitleColor', a(ink, 0.66)), marginTop: tight ? 8 : 14, maxWidth: 720, lineHeight: 1.3 }}>{event.subtitle}</div> : null}

          <div style={{ position: 'relative', width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: tight ? '22px 0 20px' : '34px 0 32px' }}>
            <div style={{ position: 'absolute', left: -58, width: 34, height: 34, borderRadius: '50%', background: pc(parts, 'ev3HoleBg', a(ink, 0.08)), border: `1px solid ${tear}` }} />
            <div style={{ flex: 1, borderTop: `2px dashed ${tear}` }} />
            <div style={{ position: 'absolute', right: -58, width: 34, height: 34, borderRadius: '50%', background: pc(parts, 'ev3HoleBg', a(ink, 0.08)), border: `1px solid ${tear}` }} />
          </div>
          <div style={{ display: 'flex', alignItems: 'stretch', maxWidth: '100%' }}>
            {[['Date', event.date], ['Time', event.time], ['Venue', event.venue]].map(([l, v], i) => (
              <div key={l} style={{ padding: '0 30px', textAlign: 'center', borderLeft: i ? `1px solid ${rule}` : 'none', minWidth: 0 }}>
                <div style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 3, textTransform: 'uppercase', color: pc(parts, 'labelColor', a(ink, 0.5)) }}>{l}</div>
                <div style={{ fontFamily: SERIF, fontWeight: 600, fontSize: 36, color: pc(parts, 'valueColor', ink), marginTop: 4, lineHeight: 1.08 }}>{v}</div>
              </div>
            ))}
          </div>
          {event.cta ? <div style={{ marginTop: tight ? 20 : 28, fontFamily: MONO, fontSize: 15, letterSpacing: 3, textTransform: 'uppercase', color: pc(parts, 'ctaColor', P.accent), border: `1.5px solid ${pc(parts, 'ctaBorder', P.accent)}`, borderRadius: 999, padding: '11px 26px' }}>{event.cta}</div> : null}
        </div>

        <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: 10 }}>
          <BSMark size={18} color={pc(parts, 'markColor', P.accent)} />
          <span style={{ fontFamily: MONO, fontSize: 12, letterSpacing: 2, textTransform: 'uppercase', color: pc(parts, 'creditColor', a(ink, 0.5)) }}>Made with {PLATFORM_NAME}{event.sponsor ? ` · ${event.sponsor}` : ''}</span>
        </div>
      </div>
    </LayerRoot>
  )
}
registerParts({
  EV3: [
    colorPart('paperColor', 'Paper', 'Paper and frame', (p) => p.paper || '#f4efe4'),
    colorPart('deepInkColor', 'Main ink', 'Paper and frame', (p) => p.deepInk || '#1f1c14'),
    colorPart('frameColor', 'Outer frame line', 'Paper and frame', (p) => p.deepInk || '#1f1c14'),
    colorPart('frameInnerColor', 'Inner frame line', 'Paper and frame', (p) => p.deepInk || '#1f1c14'),
    colorPart('clubColor', 'Club name', 'Heading', (p) => p.deepInk || '#1f1c14'),
    colorPart('kickerColor', 'Line above the title', 'Heading', (p) => p.accent),
    colorPart('titleColor', 'Title', 'Heading', (p) => p.deepInk || '#1f1c14'),
    colorPart('subtitleColor', 'Subtitle', 'Heading', (p) => p.deepInk || '#1f1c14'),
    colorPart('dividerColor', 'Rules by the club name and between details', 'Ticket stub', (p) => p.deepInk || '#1f1c14'),
    colorPart('ev3TearLine', 'Tear line and notches outline', 'Ticket stub', (p) => p.deepInk || '#1f1c14'),
    colorPart('ev3HoleBg', 'Notches', 'Ticket stub', (p) => p.deepInk || '#1f1c14'),
    colorPart('labelColor', 'Detail captions', 'Ticket stub', (p) => p.deepInk || '#1f1c14'),
    colorPart('valueColor', 'Date, time and venue', 'Ticket stub', (p) => p.deepInk || '#1f1c14'),
    textPart('entryLabel', 'Stamp caption', 'Entry stamp', () => 'Entry'),
    colorPart('badgeBg', 'Stamp fill', 'Entry stamp', (p) => p.paper || '#f4efe4'),
    colorPart('badgeBorder', 'Stamp ring', 'Entry stamp', (p) => p.accent),
    colorPart('badgeColor', 'Stamp caption colour', 'Entry stamp', (p) => p.accent),
    colorPart('priceColor', 'Price', 'Entry stamp', (p) => p.deepInk || '#1f1c14'),
    colorPart('ctaColor', 'Call to action text', 'Call to action', (p) => p.accent),
    colorPart('ctaBorder', 'Call to action outline', 'Call to action', (p) => p.accent),
    colorPart('markColor', 'Logo mark', 'Footer', (p) => p.accent),
    colorPart('creditColor', 'Made with line', 'Footer', (p) => p.deepInk || '#1f1c14'),
  ],
})

// ─────────────────────────────────────────────────────────────────────────────
// EV4 — SCOREBOARD · LED dot-matrix, mono numerals (fixtures & selections)
// ─────────────────────────────────────────────────────────────────────────────
// Scoreboard: the grid is a strip along the foot, below the CTA line. The fixture
// card's rows are a little tighter on the square to pay for it.
const slotEV4 = (width, height) => {
  const A = aspectOf(width, height)
  return slotRect(width, height, { x: 64, bottom: pick(A, { square: 40, portrait: 44, story: 120 }), h: pick(A, { square: 108, portrait: 116, story: 136 }) })
}
export function EVT_Scoreboard({ team, event = {}, width = 1080, height = 1080, palette, motif, parts }) {
  const P = palette
  const aspect = aspectOf(width, height)
  const slot = slotEV4(width, height)
  const texture = usePostLook().texture !== false
  // Title box grows modestly with the canvas; the FLEX GAP below the headline
  // takes the rest, so a taller post breathes in the middle rather than the
  // fixture card sliding under the CTA bar (the reported collision — the card
  // and the footer used to be two separate absolute blocks with nothing
  // stopping them meeting).
  const titleH = twoLineBox(150, 0.84)
  const rowPad = pick(aspect, { square: 9, portrait: 22, story: 30 })
  const bullet = pc(parts, 'ev4Bullet', P.accent)
  const rowRule = pc(parts, 'dividerColor', a(P.accent, 0.3))
  return (
    <LayerRoot style={{ ...FRAME(width, height), background: P.primary, color: '#fff' }}>
      {texture ? <div style={{ position: 'absolute', inset: 0, backgroundImage: `radial-gradient(${a(pc(parts, 'ledColor', P.accent), 0.1)} 1.4px, transparent 1.6px)`, backgroundSize: '24px 24px' }} /> : null}
      {texture ? <div style={{ position: 'absolute', left: -160, bottom: -160, width: 560, height: 560, borderRadius: '50%', background: `radial-gradient(circle, ${a(pc(parts, 'glowColor', P.accent), 0.16)}, transparent 68%)` }} /> : null}
      {texture ? <img src={motif?.icon || (IS_AFL ? icoStar : icoBat)} alt="" style={{ position: 'absolute', right: 54, top: 64, width: 150, height: 150, objectFit: 'contain', opacity: 0.5 }} /> : null}

      <div style={{ position: 'absolute', top: 60, left: 64, right: 230, display: 'flex', alignItems: 'center', gap: 16 }}>
        <BrandLockup team={team} palette={P} size={96} nameColor={pc(parts, 'clubColor', '#fff')} nameSize={32} />
      </div>

      {/* One column bounded top AND bottom, so the fixture card can never reach
          the footer. Header block at top, footer group at bottom, slack pooled
          between them. */}
      <div style={{ position: 'absolute', left: 64, right: 64, top: pick(aspect, { square: 188, portrait: share(height, 214) }), bottom: height - slot.y + 16, display: 'flex', flexDirection: 'column' }}>
        <div style={{ flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 18 }}>
            <div style={{ width: 13, height: 13, borderRadius: '50%', background: bullet, boxShadow: `0 0 16px ${bullet}` }} />
            <div style={{ fontFamily: MONO, fontSize: 18, letterSpacing: 6, textTransform: 'uppercase', color: pc(parts, 'kickerColor', P.accent) }}>{event.kicker}</div>
          </div>
          <div style={{ height: titleH, display: 'flex', alignItems: 'flex-end' }}>
            <AutoFitText text={(event.title || '').toUpperCase()} max={150} min={56} lines={2} measureDeps={[event.title]}
              style={{ fontFamily: SPORT, fontWeight: 800, lineHeight: 0.84, textTransform: 'uppercase', color: pc(parts, 'titleColor', '#fff'), letterSpacing: 1 }} />
          </div>
          {event.subtitle ? <div style={{ fontFamily: MONO, fontSize: 21, color: pc(parts, 'subtitleColor', 'rgba(255,255,255,0.6)'), marginTop: 6, lineHeight: 1.5, maxWidth: 820 }}>{event.subtitle}</div> : null}
        </div>

        {/* Card floats in the middle of the slack (auto margins top AND bottom),
            so a taller post keeps the headline at the top and the footer at the
            foot with the details centred between — not one pooled gap. */}
        <div style={{ marginTop: 'auto', marginBottom: 'auto', flexShrink: 0, border: `1.5px solid ${pc(parts, 'cardBorder', a(P.accent, 0.3))}`, borderRadius: 18, background: a(pc(parts, 'cardBg', P.accent), 0.1), overflow: 'hidden' }}>
          <div style={{ background: a(pc(parts, 'headerBg', P.accent), 0.16), padding: '14px 28px', borderBottom: `1px solid ${pc(parts, 'headerRule', a(P.accent, 0.3))}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontFamily: MONO, fontSize: 14, letterSpacing: 4, textTransform: 'uppercase', color: pc(parts, 'ev4CardTitleColor', P.accent) }}>{pt(parts, 'ev4CardTitle', '▸ Fixture Card')}</span>
            <span style={{ fontFamily: MONO, fontSize: 14, letterSpacing: 2, color: pc(parts, 'priceColor', 'rgba(255,255,255,0.4)') }}>{event.price}</span>
          </div>
          <div style={{ padding: '6px 28px' }}>
            {[['Date', event.date], ['Time', event.time], ['Venue', event.venue]].map(([l, v], i) => (
              <div key={l} style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 20, padding: `${rowPad}px 0`, borderBottom: i < 2 ? `1px dashed ${rowRule}` : 'none' }}>
                <span style={{ fontFamily: MONO, fontSize: 16, letterSpacing: 4, textTransform: 'uppercase', color: pc(parts, 'labelColor', 'rgba(255,255,255,0.5)'), flexShrink: 0 }}>{l}</span>
                <span style={{ fontFamily: SPORT, fontWeight: 700, fontSize: 46, color: i === 2 ? pc(parts, 'ev4VenueColor', P.accent) : pc(parts, 'valueColor', '#fff'), textAlign: 'right', lineHeight: 1.05 }}>{v}</span>
              </div>
            ))}
          </div>
        </div>

        <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
          <div style={{ fontFamily: MONO, fontSize: 16, letterSpacing: 2, textTransform: 'uppercase', color: pc(parts, 'ctaColor', P.accent) }}>{event.cta}</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, flexShrink: 0 }}>
            {event.sponsor ? <span style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 2, textTransform: 'uppercase', color: pc(parts, 'sponsorColor', 'rgba(255,255,255,0.4)') }}>{event.sponsor}</span> : null}
            <BSMark size={20} color={pc(parts, 'markColor', '#f25aa6')} />
          </div>
        </div>
      </div>
    </LayerRoot>
  )
}
registerParts({
  EV4: [
    colorPart('ledColor', 'Dot grid', 'Backdrop', (p) => p.accent),
    colorPart('glowColor', 'Corner glow', 'Backdrop', (p) => p.accent),
    colorPart('clubColor', 'Club name', 'Heading', () => '#ffffff'),
    colorPart('ev4Bullet', 'Glowing dot by the title line', 'Heading', (p) => p.accent),
    colorPart('kickerColor', 'Line above the title', 'Heading', (p) => p.accent),
    colorPart('titleColor', 'Title', 'Heading', () => '#ffffff'),
    colorPart('subtitleColor', 'Subtitle', 'Heading', () => '#ffffff'),
    colorPart('cardBg', 'Fixture card tint', 'Fixture card', (p) => p.accent),
    colorPart('cardBorder', 'Fixture card outline', 'Fixture card', (p) => p.accent),
    colorPart('headerBg', 'Card heading bar', 'Fixture card', (p) => p.accent),
    colorPart('headerRule', 'Line under the card heading', 'Fixture card', (p) => p.accent),
    textPart('ev4CardTitle', 'Card heading words', 'Fixture card', () => '▸ Fixture Card'),
    colorPart('ev4CardTitleColor', 'Card heading text', 'Fixture card', (p) => p.accent),
    colorPart('priceColor', 'Price', 'Fixture card', () => '#ffffff'),
    colorPart('dividerColor', 'Dashed lines between rows', 'Fixture card', (p) => p.accent),
    colorPart('labelColor', 'Row captions', 'Fixture card', () => '#ffffff'),
    colorPart('valueColor', 'Date and time', 'Fixture card', () => '#ffffff'),
    colorPart('ev4VenueColor', 'Venue', 'Fixture card', (p) => p.accent),
    colorPart('ctaColor', 'Call to action', 'Footer', (p) => p.accent),
    colorPart('sponsorColor', 'Sponsor line', 'Footer', () => '#ffffff'),
    colorPart('markColor', 'Logo mark', 'Footer', () => '#f25aa6'),
  ],
})

// ─────────────────────────────────────────────────────────────────────────────
// EV5 — GAZETTE · newspaper masthead + serif headline (stately notices)
// ─────────────────────────────────────────────────────────────────────────────
// Gazette: the grid is an advertisement strip along the foot of the page, full
// frame width, under the closing rule. The frame itself stops above it, so the
// poster is still one inset frame (one layer).
const slotEV5 = (width, height) => {
  const A = aspectOf(width, height)
  return slotRect(width, height, { x: 56, bottom: pick(A, { square: 52, portrait: 56, story: 110 }), h: pick(A, { square: 100, portrait: 112, story: 132 }) })
}
export function EVT_Gazette({ team, event = {}, width = 1080, height = 1080, palette, motif, parts }) {
  const P = palette
  const aspect = aspectOf(width, height)
  const slot = slotEV5(width, height)
  const tight = aspect === 'square'
  const texture = usePostLook().texture !== false
  const paper = pc(parts, 'paperColor', P.paper || '#f4f0e6')
  const ink = pc(parts, 'deepInkColor', P.deepInk || '#1a1814')
  const line = a(ink, 0.28)
  const faint = a(ink, 0.55)
  const heavy = pc(parts, 'ev5RuleColor', ink)
  const thin = pc(parts, 'dividerColor', line)
  const box = pc(parts, 'cardBorder', ink)
  const band = pc(parts, 'bandBg', ink)
  const onBand = partPicked(parts, 'bandBg') ? inkOn(band) : null
  const SERIF = "'Playfair Display', serif"
  const BODY = "'Spectral', serif"
  const t5max = pick(aspect, { square: 92, portrait: 128, story: 138 })
  return (
    <LayerRoot style={{ ...FRAME(width, height), background: paper, color: ink, fontFamily: BODY }}>
      {/* This poster keeps everything inside ONE inset frame, so it is a single
          layer rather than a stack. Naming it says so; splitting it would mean
          promoting this div's own children, and a block spliced in among them
          would be offset by the inset from where it was dropped. */}
      <div data-layer="Poster content" style={{ position: 'absolute', top: 56, left: 56, right: 56, bottom: height - slot.y + 14, display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontFamily: MONO, fontSize: 13, letterSpacing: 2, textTransform: 'uppercase', color: pc(parts, 'ev5IssueColor', faint), paddingBottom: tight ? 6 : 10 }}>
          <span>{pt(parts, 'ev5Issue', 'Vol. XCIV — No. 12')}</span><span>{pt(parts, 'ev5Est', 'Est. 1921')}</span>
        </div>
        <div style={{ borderTop: `3px solid ${heavy}`, borderBottom: `1px solid ${heavy}`, padding: tight ? '10px 0 8px' : '16px 0 12px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 26 }}>
          {team.logo ? <ClubLogo src={team.logo} size={tight ? 68 : 88} /> : <ClubLogo monogram={team.monogram} color={ink} size={tight ? 64 : 80} shape="shield" />}
          {/* AutoFit the masthead so a long club name shrinks instead of wrapping
              to a two-line block that eats the poster. */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <AutoFitText text={team.fullName || team.name} max={tight ? 60 : 72} min={34} lines={2} measureDeps={[team.fullName || team.name]}
              style={{ fontFamily: SERIF, fontWeight: 900, lineHeight: 0.96, color: pc(parts, 'clubColor', ink), letterSpacing: 0.5, textAlign: 'center' }} />
          </div>
        </div>
        <div style={{ borderBottom: `3px solid ${heavy}`, padding: tight ? '6px 0' : '9px 0', textAlign: 'center', fontFamily: MONO, fontSize: 14, letterSpacing: 5, textTransform: 'uppercase', color: pc(parts, 'kickerColor', ink) }}>{event.kicker}</div>

        <div style={{ textAlign: 'center', padding: pick(aspect, { square: '16px 0 2px', portrait: '30px 0 8px', story: '54px 0 12px' }) }}>
          <div style={{ fontFamily: MONO, fontSize: 15, letterSpacing: 5, textTransform: 'uppercase', color: pc(parts, 'ev5NoticeColor', P.accent), marginBottom: pick(aspect, { square: 6, portrait: 18, story: 20 }) }}>{pt(parts, 'ev5Notice', '— Official Notice —')}</div>
          <div style={{ height: twoLineBox(t5max, 0.9), display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <AutoFitText text={event.title} max={t5max} min={52} lines={2} measureDeps={[event.title]}
              style={{ fontFamily: SERIF, fontWeight: 900, lineHeight: 0.9, color: pc(parts, 'titleColor', ink) }} />
          </div>
          {event.subtitle ? <div style={{ fontFamily: BODY, fontStyle: 'italic', fontSize: pick(aspect, { square: 24, portrait: 33, story: 36 }), color: pc(parts, 'subtitleColor', a(ink, 0.72)), marginTop: pick(aspect, { square: 8, portrait: 20, story: 22 }), maxWidth: 840, marginLeft: 'auto', marginRight: 'auto', lineHeight: 1.32 }}>{event.subtitle}</div> : null}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1.35fr 1fr', gap: 40, marginTop: pick(aspect, { square: 12, portrait: 22, story: 40 }), flex: 1, minHeight: 0, borderTop: `1px solid ${thin}`, paddingTop: pick(aspect, { square: 14, portrait: 22, story: 40 }) }}>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <div style={{ flex: 1, border: `1px solid ${box}`, backgroundColor: pc(parts, 'photoBg', '#d8d3c6'), backgroundImage: (motif?.imageUrl || !texture) ? undefined : `radial-gradient(${a(ink, 0.42)} 1.3px, transparent 1.6px)`, backgroundSize: '7px 7px', overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {motif?.imageUrl
                ? <img src={motif.imageUrl} alt="" crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover', filter: 'grayscale(1) contrast(1.1)' }} />
                : <span style={{ fontFamily: MONO, fontSize: 14, letterSpacing: 3, textTransform: 'uppercase', color: pc(parts, 'ev5PhotoLabel', a(ink, 0.55)), background: paper, padding: '6px 14px' }}>{motif?.label || 'Add a photo'}</span>}
            </div>
            <div style={{ fontFamily: BODY, fontStyle: 'italic', fontSize: 18, color: pc(parts, 'ev5CaptionColor', faint), marginTop: 10 }}>{pt(parts, 'ev5Caption', "Pictured: members at last year's event.")}</div>
          </div>

          <div style={{ border: `2px solid ${box}`, padding: pick(aspect, { square: '12px 22px', portrait: '18px 24px', story: '28px 28px' }), display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            <div style={{ fontFamily: SERIF, fontWeight: 700, fontSize: 28, color: pc(parts, 'ev5GlanceColor', ink), borderBottom: `2px solid ${pc(parts, 'headerRule', ink)}`, paddingBottom: tight ? 6 : 10, marginBottom: 4, flexShrink: 0 }}>{pt(parts, 'ev5GlanceTitle', 'At a Glance')}</div>
            {[['Date', event.date], ['Time', event.time], ['Venue', event.venue]].map(([l, v]) => (
              <div key={l} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12, padding: pick(aspect, { square: '7px 0', portrait: '11px 0', story: '17px 0' }), borderBottom: `1px solid ${thin}` }}>
                <span style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 2, textTransform: 'uppercase', color: pc(parts, 'labelColor', faint), flexShrink: 0 }}>{l}</span>
                <span style={{ fontFamily: SERIF, fontWeight: 700, fontSize: 27, color: pc(parts, 'valueColor', ink), textAlign: 'right', lineHeight: 1.1 }}>{v}</span>
              </div>
            ))}
            <div style={{ marginTop: 'auto', background: band, padding: tight ? '9px 18px' : '13px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
              <span style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 2, textTransform: 'uppercase', color: pc(parts, 'ev5AdmissionColor', onBand || 'rgba(255,255,255,0.6)'), flexShrink: 0 }}>{pt(parts, 'entryLabel', 'Admission')}</span>
              <span style={{ fontFamily: SERIF, fontWeight: 900, fontSize: 30, color: pc(parts, 'priceColor', onBand || '#fff') }}>{event.price}</span>
            </div>
          </div>
        </div>

        <div style={{ borderTop: `3px solid ${heavy}`, marginTop: pick(aspect, { square: 10, portrait: 26, story: 30 }), paddingTop: pick(aspect, { square: 8, portrait: 14 }), display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
          <span style={{ fontFamily: BODY, fontStyle: 'italic', fontSize: 22, color: pc(parts, 'ctaColor', ink) }}>{event.cta}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            {event.sponsor ? <span style={{ fontFamily: MONO, fontSize: 12, letterSpacing: 2, textTransform: 'uppercase', color: pc(parts, 'sponsorColor', faint) }}>{event.sponsor}</span> : null}
            <span style={{ color: thin }}>|</span>
            <span style={{ fontFamily: MONO, fontSize: 12, letterSpacing: 2, textTransform: 'uppercase', color: pc(parts, 'creditColor', faint) }}>Made with {PLATFORM_NAME}</span>
          </div>
        </div>
      </div>
    </LayerRoot>
  )
}
registerParts({
  EV5: [
    colorPart('paperColor', 'Paper', 'Paper', (p) => p.paper || '#f4f0e6'),
    colorPart('deepInkColor', 'Main ink', 'Paper', (p) => p.deepInk || '#1a1814'),
    textPart('ev5Issue', 'Issue line words', 'Masthead', () => 'Vol. XCIV — No. 12'),
    textPart('ev5Est', 'Founded line words', 'Masthead', () => 'Est. 1921'),
    colorPart('ev5IssueColor', 'Issue and founded lines', 'Masthead', (p) => p.deepInk || '#1a1814'),
    colorPart('ev5RuleColor', 'Heavy rules', 'Masthead', (p) => p.deepInk || '#1a1814'),
    colorPart('clubColor', 'Club name', 'Masthead', (p) => p.deepInk || '#1a1814'),
    colorPart('kickerColor', 'Line under the masthead', 'Masthead', (p) => p.deepInk || '#1a1814'),
    textPart('ev5Notice', 'Notice line words', 'Headline', () => '— Official Notice —'),
    colorPart('ev5NoticeColor', 'Notice line', 'Headline', (p) => p.accent),
    colorPart('titleColor', 'Title', 'Headline', (p) => p.deepInk || '#1a1814'),
    colorPart('subtitleColor', 'Subtitle', 'Headline', (p) => p.deepInk || '#1a1814'),
    colorPart('photoBg', 'Photo backdrop', 'Photo', () => '#d8d3c6'),
    colorPart('ev5PhotoLabel', 'Words on an empty photo', 'Photo', (p) => p.deepInk || '#1a1814'),
    textPart('ev5Caption', 'Photo caption words', 'Photo', () => "Pictured: members at last year's event."),
    colorPart('ev5CaptionColor', 'Photo caption', 'Photo', (p) => p.deepInk || '#1a1814'),
    textPart('ev5GlanceTitle', 'Details box heading words', 'Details box', () => 'At a Glance'),
    colorPart('ev5GlanceColor', 'Details box heading', 'Details box', (p) => p.deepInk || '#1a1814'),
    colorPart('cardBorder', 'Photo and details box outlines', 'Details box', (p) => p.deepInk || '#1a1814'),
    colorPart('headerRule', 'Line under the box heading', 'Details box', (p) => p.deepInk || '#1a1814'),
    colorPart('dividerColor', 'Thin rules', 'Details box', (p) => p.deepInk || '#1a1814'),
    colorPart('labelColor', 'Detail captions', 'Details box', (p) => p.deepInk || '#1a1814'),
    colorPart('valueColor', 'Date, time and venue', 'Details box', (p) => p.deepInk || '#1a1814'),
    textPart('entryLabel', 'Price caption', 'Price bar', () => 'Admission'),
    colorPart('bandBg', 'Price bar', 'Price bar', (p) => p.deepInk || '#1a1814'),
    colorPart('ev5AdmissionColor', 'Price caption colour', 'Price bar', () => '#ffffff'),
    colorPart('priceColor', 'Price', 'Price bar', () => '#ffffff'),
    colorPart('ctaColor', 'Call to action', 'Footer', (p) => p.deepInk || '#1a1814'),
    colorPart('sponsorColor', 'Sponsor line', 'Footer', (p) => p.deepInk || '#1a1814'),
    colorPart('creditColor', 'Made with line', 'Footer', (p) => p.deepInk || '#1a1814'),
  ],
})

// ─────────────────────────────────────────────────────────────────────────────
// EV6 — STICKER POP · playful rounded badges (casual socials)
// ─────────────────────────────────────────────────────────────────────────────
// Sticker Pop: the grid is a strip along the foot with the small watermark line
// tucked underneath it, so the sticker, chips and CTA all sit above it.
const slotEV6Bottom = (A) => pick(A, { square: 54, portrait: 58, story: 130 })
const slotEV6 = (width, height) => {
  const A = aspectOf(width, height)
  return slotRect(width, height, { x: 72, bottom: slotEV6Bottom(A), h: pick(A, { square: 100, portrait: 112, story: 132 }) })
}
export function EVT_Sticker({ team, event = {}, width = 1080, height = 1080, palette, motif, parts }) {
  const P = palette
  const aspect = aspectOf(width, height)
  const slot = slotEV6(width, height)
  const tight = aspect === 'square'
  const texture = usePostLook().texture !== false
  const paper = pc(parts, 'paperColor', P.paper || '#fbf6ec')
  const ink = pc(parts, 'deepInkColor', P.deepInk || '#23202c')
  const pillBg = pc(parts, 'bandBg', P.accent)
  const chipBg = pc(parts, 'cardBg', '#fff')
  const ctaBg = pc(parts, 'ctaBg', ink)
  const priceBg = pc(parts, 'priceBg', P.accent)
  const FUN = "'Fredoka', sans-serif"
  return (
    <LayerRoot style={{ ...FRAME(width, height), background: paper, color: ink }}>
      {texture ? <div style={{ position: 'absolute', right: -130, top: -130, width: 480, height: 480, borderRadius: '50%', background: a(pc(parts, 'ev6BlobColor', P.accent), 0.18) }} /> : null}
      {texture ? <div style={{ position: 'absolute', left: -90, bottom: share(height, 110), width: 300, height: 300, borderRadius: '50%', border: `4px dashed ${a(pc(parts, 'ev6RingColor', P.accent), 0.4)}` }} /> : null}

      <div style={{ position: 'absolute', top: pick(aspect, { square: 84, portrait: share(height, 130), story: 190 }), right: 96, width: tight ? 236 : 280, height: tight ? 236 : 280, background: pc(parts, 'ev6StickerBg', '#fff'), borderRadius: 36, boxShadow: '0 18px 44px rgba(0,0,0,0.16)', transform: 'rotate(7deg)', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
        {motif?.imageUrl
          ? <img src={motif.imageUrl} alt="" crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          : <img src={motif?.icon || icoTarget} alt="" style={{ width: tight ? 170 : 200, height: tight ? 170 : 200, objectFit: 'contain' }} />}
      </div>

      <div style={{ position: 'absolute', top: 72, left: 72, right: 72, bottom: height - slot.y + 16, display: 'flex', flexDirection: 'column' }}>
        <div style={{ flexShrink: 0, alignSelf: 'flex-start', display: 'flex', alignItems: 'center', gap: 18, maxWidth: 640 }}>
          {team.logo ? <ClubLogo src={team.logo} size={92} /> : <ClubLogo monogram={team.monogram} color={P.accent} size={92} shape="shield" />}
          <div style={{ background: pillBg, color: pc(parts, 'clubColor', partPicked(parts, 'bandBg') ? inkOn(pillBg) : '#fff'), fontFamily: FUN, fontWeight: 600, fontSize: 28, letterSpacing: 1, padding: '12px 26px', borderRadius: 999, transform: 'rotate(-3deg)', boxShadow: `0 8px 22px ${a(pillBg, 0.4)}` }}>{team.fullName || team.name}</div>
        </div>

        {/* Hero + chips + CTA sit as one cluster: centred on square/portrait,
            and on the very tall story anchored a set distance below the logo
            (breathing room at the foot) so the logo isn't stranded above a huge
            centred gap. The title box is capped per aspect, not share()d up to
            498px on a story. */}
        <div style={{ marginTop: pick(aspect, { square: 'auto', portrait: 'auto', story: 96 }), marginBottom: 'auto', width: '100%', display: 'flex', flexDirection: 'column', paddingTop: tight ? 12 : 28 }}>
          <div>
            <div style={{ display: 'inline-block', background: a(pc(parts, 'badgeBg', P.accent), 0.18), color: pc(parts, 'kickerColor', P.accent), fontFamily: FUN, fontWeight: 600, fontSize: 22, padding: '8px 18px', borderRadius: 999, marginBottom: tight ? 10 : 18 }}>{event.kicker}</div>
            <div style={{ height: twoLineBox(tight ? 136 : 158, 0.9), display: 'flex', alignItems: 'flex-end' }}>
              <AutoFitText text={event.title} max={tight ? 136 : 158} min={60} lines={2} measureDeps={[event.title]}
                style={{ fontFamily: FUN, fontWeight: 700, lineHeight: 0.9, color: pc(parts, 'titleColor', ink), letterSpacing: -1 }} />
            </div>
            {event.subtitle ? <div style={{ fontWeight: 500, fontSize: tight ? 26 : 29, color: pc(parts, 'subtitleColor', a(ink, 0.7)), marginTop: tight ? 10 : 18, maxWidth: 760, lineHeight: tight ? 1.3 : 1.36 }}>{event.subtitle}</div> : null}
          </div>

          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: pick(aspect, { square: 20, portrait: 36, story: 40 }) }}>
            {[['Date', event.date], ['Time', event.time], ['Venue', event.venue]].map(([l, v]) => (
              <div key={l} style={{ background: chipBg, border: `2.5px solid ${pc(parts, 'cardBorder', ink)}`, borderRadius: 18, padding: '14px 22px', boxShadow: `5px 5px 0 ${pc(parts, 'ev6ChipShadow', ink)}` }}>
                <div style={{ fontWeight: 600, fontSize: 13, letterSpacing: 2, textTransform: 'uppercase', color: pc(parts, 'labelColor', P.accent) }}>{l}</div>
                <div style={{ fontFamily: FUN, fontWeight: 600, fontSize: 34, color: pc(parts, 'valueColor', partPicked(parts, 'cardBg') ? inkOn(chipBg) : ink), lineHeight: 1.1 }}>{v}</div>
              </div>
            ))}
          </div>

          <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, marginTop: pick(aspect, { square: 20, portrait: 42, story: 46 }) }}>
            {event.cta ? <div style={{ background: ctaBg, color: pc(parts, 'ctaColor', partPicked(parts, 'ctaBg') ? inkOn(ctaBg) : '#fff'), fontFamily: FUN, fontWeight: 600, fontSize: 34, padding: tight ? '14px 34px' : '18px 38px', borderRadius: 999, boxShadow: '0 10px 26px rgba(0,0,0,0.2)' }}>{event.cta}</div> : <span />}
            {event.price ? (
              <div style={{ width: tight ? 124 : 150, height: tight ? 124 : 150, borderRadius: '50%', background: priceBg, color: pc(parts, 'priceColor', partPicked(parts, 'priceBg') ? inkOn(priceBg) : '#fff'), display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', transform: 'rotate(-9deg)', boxShadow: `0 12px 30px ${a(priceBg, 0.4)}`, flexShrink: 0 }}>
                <span style={{ fontWeight: 600, fontSize: 13, letterSpacing: 2, textTransform: 'uppercase', opacity: 0.85 }}>{pt(parts, 'entryLabel', 'Entry')}</span>
                <span style={{ fontFamily: FUN, fontWeight: 700, fontSize: tight ? 34 : 42, lineHeight: 1, textAlign: 'center', padding: '0 8px' }}>{event.price}</span>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <div style={{ position: 'absolute', bottom: slotEV6Bottom(aspect) - 30, left: 72, display: 'flex', alignItems: 'center', gap: 9 }}>
        <BSMark size={18} color={pc(parts, 'markColor', '#f25aa6')} />
        <span style={{ fontWeight: 500, fontSize: 13, letterSpacing: 1, color: pc(parts, 'creditColor', a(ink, 0.5)) }}>Made with {PLATFORM_NAME}{event.sponsor ? ` · ${event.sponsor}` : ''}</span>
      </div>
    </LayerRoot>
  )
}
registerParts({
  EV6: [
    colorPart('paperColor', 'Paper', 'Paper', (p) => p.paper || '#fbf6ec'),
    colorPart('deepInkColor', 'Main ink', 'Paper', (p) => p.deepInk || '#23202c'),
    colorPart('ev6BlobColor', 'Corner circle', 'Paper', (p) => p.accent),
    colorPart('ev6RingColor', 'Dashed ring', 'Paper', (p) => p.accent),
    colorPart('ev6StickerBg', 'Picture sticker', 'Heading', () => '#ffffff'),
    colorPart('bandBg', 'Club name pill', 'Heading', (p) => p.accent),
    colorPart('clubColor', 'Club name', 'Heading', () => '#ffffff'),
    colorPart('badgeBg', 'Line above the title, pill', 'Heading', (p) => p.accent),
    colorPart('kickerColor', 'Line above the title, text', 'Heading', (p) => p.accent),
    colorPart('titleColor', 'Title', 'Heading', (p) => p.deepInk || '#23202c'),
    colorPart('subtitleColor', 'Subtitle', 'Heading', (p) => p.deepInk || '#23202c'),
    colorPart('cardBg', 'Detail boxes', 'Detail boxes', () => '#ffffff'),
    colorPart('cardBorder', 'Detail box outline', 'Detail boxes', (p) => p.deepInk || '#23202c'),
    colorPart('ev6ChipShadow', 'Detail box shadow', 'Detail boxes', (p) => p.deepInk || '#23202c'),
    colorPart('labelColor', 'Detail captions', 'Detail boxes', (p) => p.accent),
    colorPart('valueColor', 'Date, time and venue', 'Detail boxes', (p) => p.deepInk || '#23202c'),
    colorPart('ctaBg', 'Call to action pill', 'Call to action and price', (p) => p.deepInk || '#23202c'),
    colorPart('ctaColor', 'Call to action text', 'Call to action and price', () => '#ffffff'),
    colorPart('priceBg', 'Price circle', 'Call to action and price', (p) => p.accent),
    colorPart('priceColor', 'Price text', 'Call to action and price', () => '#ffffff'),
    textPart('entryLabel', 'Price circle caption', 'Call to action and price', () => 'Entry'),
    colorPart('markColor', 'Logo mark', 'Footer', () => '#f25aa6'),
    colorPart('creditColor', 'Made with line', 'Footer', (p) => p.deepInk || '#23202c'),
  ],
})

// ─────────────────────────────────────────────────────────────────────────────
// EV7 — KINETIC · diagonal bands, italic motion type (high-energy sport)
// ─────────────────────────────────────────────────────────────────────────────
// Kinetic: the grid is a strip along the foot, on the dark field under the detail
// bar. The photo band and its diagonal give the square some height back for it.
const slotEV7 = (width, height) => {
  const A = aspectOf(width, height)
  return slotRect(width, height, { x: 64, bottom: pick(A, { square: 40, portrait: 44, story: 120 }), h: pick(A, { square: 104, portrait: 116, story: 136 }) })
}
export function EVT_Kinetic({ team, event = {}, width = 1080, height = 1080, palette, motif, parts }) {
  const P = palette
  const texture = usePostLook().texture !== false
  const aspect = aspectOf(width, height)
  const slot = slotEV7(width, height)
  const tight = aspect === 'square'
  // Photo band height and the top of the text column. The square's band is
  // shorter; the others keep their share of the canvas.
  const bandH = pick(aspect, { square: 396, portrait: 560, story: 1040 })
  const colTop = pick(aspect, { square: 400, portrait: 566, story: 1048 })
  const skew = { transform: 'skewX(-8deg)' }
  const unskew = { display: 'inline-block', transform: 'skewX(8deg)' }
  return (
    <LayerRoot style={{ ...FRAME(width, height), background: P.primary, color: '#fff' }}>
      <div style={{ position: 'absolute', left: 0, top: 0, right: 0, height: bandH, clipPath: `polygon(0 0, 100% 0, 100% 100%, 0 ${(((bandH - 148) / bandH) * 100).toFixed(2)}%)`, overflow: 'hidden' }}>
        {motif?.imageUrl
          ? <img src={motif.imageUrl} alt="" crossOrigin="anonymous" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
          : <div style={{ position: 'absolute', inset: 0, background: texture ? `repeating-linear-gradient(120deg, ${a(P.accent, 0.06)} 0px, ${a(P.accent, 0.06)} 18px, ${a(P.accent, 0.12)} 18px, ${a(P.accent, 0.12)} 36px)` : undefined, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <span style={{ fontFamily: MONO, fontSize: 16, letterSpacing: 4, textTransform: 'uppercase', color: a(P.accent, 0.45) }}>{motif?.label || 'Add a photo'}</span>
            </div>}
        <div style={{ position: 'absolute', inset: 0, background: `linear-gradient(180deg, rgba(0,0,0,0.1) 0%, transparent 35%), linear-gradient(0deg, ${P.primary} 2%, transparent 50%)` }} />
      </div>
      <div style={{ position: 'absolute', left: -60, top: bandH - 104, width: 1200, height: 18, background: pc(parts, 'ev7BarColor', P.accent), transform: 'rotate(8deg)' }} />
      <div style={{ position: 'absolute', left: -60, top: bandH - 68, width: 1200, height: 7, background: pc(parts, 'ev7BarThinColor', a(P.accent, 0.45)), transform: 'rotate(8deg)' }} />

      <div style={{ position: 'absolute', top: 56, left: 64, right: 64, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {team.logo ? <ClubLogo src={team.logo} size={94} /> : <ClubLogo monogram={team.monogram} color="#fff" size={94} shape="shield" />}
          <div style={{ fontFamily: SPORT, fontStyle: 'italic', fontSize: 32, fontWeight: 700, letterSpacing: 3, textTransform: 'uppercase', color: pc(parts, 'clubColor', '#fff'), lineHeight: 0.95, maxWidth: 420 }}>{team.fullName || team.name}</div>
        </div>
        <div style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 3, textTransform: 'uppercase', color: pc(parts, 'chipColor', P.accent), border: `1.5px solid ${pc(parts, 'chipBorder', a(P.accent, 0.45))}`, borderRadius: 4, padding: '9px 16px', ...skew }}><span style={unskew}>{pt(parts, 'chipText', 'Club Event')}</span></div>
      </div>

      {/* One column bounded top AND bottom: the italic title group up top, the
          detail bar pinned to the foot, slack pooled between. The title block
          and the bar used to be separate absolute blocks, so a long headline or
          a wrapping venue drove them straight into each other. */}
      <div style={{ position: 'absolute', left: 64, right: 64, top: colTop, bottom: height - slot.y + 16, display: 'flex', flexDirection: 'column' }}>
        <div style={{ flexShrink: 0, ...skew }}>
          <div style={{ fontFamily: MONO, fontSize: 18, letterSpacing: 6, textTransform: 'uppercase', color: pc(parts, 'kickerColor', P.accent), marginBottom: 12, ...unskew }}>{event.kicker}</div>
          <div style={{ height: twoLineBox(tight ? 120 : 138, 0.84), display: 'flex', alignItems: 'flex-end' }}>
            <AutoFitText text={(event.title || '').toUpperCase()} max={tight ? 120 : 138} min={52} lines={2} measureDeps={[event.title]}
              style={{ fontFamily: SPORT, fontStyle: 'italic', fontWeight: 800, lineHeight: 0.84, textTransform: 'uppercase', color: pc(parts, 'title1Color', '#fff') }} />
          </div>
          {event.subtitle ? <div style={{ fontFamily: "'Inter', sans-serif", fontSize: tight ? 24 : 27, color: pc(parts, 'subtitleColor', 'rgba(255,255,255,0.74)'), marginTop: tight ? 10 : 18, maxWidth: 760, lineHeight: 1.3, ...unskew }}>{event.subtitle}</div> : null}
        </div>

        <div style={{ marginTop: 'auto', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16, borderLeft: `4px solid ${pc(parts, 'ev7EdgeColor', P.accent)}`, paddingLeft: 22 }}>
            {[['Date', event.date, 1], ['Time', event.time, 1], ['Venue', event.venue, 1.3]].map(([l, v, fl]) => (
              <div key={l} style={{ flex: fl, minWidth: 0 }}>
                <div style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 3, textTransform: 'uppercase', color: pc(parts, 'labelColor', 'rgba(255,255,255,0.45)') }}>{l}</div>
                <div style={{ fontFamily: SPORT, fontStyle: 'italic', fontWeight: 800, fontSize: tight ? 36 : 40, color: pc(parts, 'valueColor', '#fff'), lineHeight: 1.06 }}>{v}</div>
              </div>
            ))}
            {event.price ? (
              <div style={{ display: 'flex', alignItems: 'center', flexShrink: 0 }}>
                <div style={{ background: pc(parts, 'priceBg', P.accent), color: pc(parts, 'priceColor', partPicked(parts, 'priceBg') ? inkOn(pc(parts, 'priceBg', P.accent)) : P.primary), fontFamily: SPORT, fontStyle: 'italic', fontWeight: 800, fontSize: tight ? 36 : 40, textTransform: 'uppercase', padding: '10px 24px', ...skew }}><span style={unskew}>{event.price}</span></div>
              </div>
            ) : null}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, marginTop: tight ? 12 : 26, paddingTop: tight ? 12 : 20, borderTop: `1px solid ${pc(parts, 'dividerColor', 'rgba(255,255,255,0.14)')}` }}>
            <span style={{ fontFamily: MONO, fontSize: 16, letterSpacing: 2, textTransform: 'uppercase', color: pc(parts, 'ctaColor', P.accent) }}>{event.cta}</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexShrink: 0 }}>
              {event.sponsor ? <span style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 2, textTransform: 'uppercase', color: pc(parts, 'creditColor', 'rgba(255,255,255,0.42)') }}>{event.sponsor}</span> : null}
              <BSMark size={20} color={pc(parts, 'markColor', '#f25aa6')} />
            </div>
          </div>
        </div>
      </div>
    </LayerRoot>
  )
}
registerParts({
  EV7: [
    colorPart('clubColor', 'Club name', 'Header', () => '#ffffff'),
    textPart('chipText', 'Badge words', 'Header', () => 'Club Event'),
    colorPart('chipColor', 'Badge text', 'Header', (p) => p.accent),
    colorPart('chipBorder', 'Badge outline', 'Header', (p) => p.accent),
    colorPart('ev7BarColor', 'Wide slash', 'Slash bars', (p) => p.accent),
    colorPart('ev7BarThinColor', 'Thin slash', 'Slash bars', (p) => p.accent),
    colorPart('kickerColor', 'Line above the title', 'Heading', (p) => p.accent),
    colorPart('title1Color', 'Title', 'Heading', () => '#ffffff'),
    colorPart('subtitleColor', 'Subtitle', 'Heading', () => '#ffffff'),
    colorPart('ev7EdgeColor', 'Bar beside the details', 'Details', (p) => p.accent),
    colorPart('labelColor', 'Date, Time and Venue labels', 'Details', () => '#ffffff'),
    colorPart('valueColor', 'Date, time and venue', 'Details', () => '#ffffff'),
    colorPart('priceBg', 'Price tag', 'Details', (p) => p.accent),
    colorPart('priceColor', 'Price text', 'Details', (p) => p.primary),
    colorPart('dividerColor', 'Line above the call to action', 'Foot', () => '#ffffff'),
    colorPart('ctaColor', 'Call to action', 'Foot', (p) => p.accent),
    colorPart('creditColor', 'Sponsor line', 'Foot', () => '#ffffff'),
    colorPart('markColor', 'Logo mark', 'Foot', () => '#f25aa6'),
  ],
})

// ─────────────────────────────────────────────────────────────────────────────
// EV8 — SWISS · ultra-minimal Helvetica, baseline grid (clean & unmistakable)
// ─────────────────────────────────────────────────────────────────────────────
// Swiss: the grid is a strip on the poster's 80px side margin. The one inset
// frame stops above it.
const slotEV8 = (width, height) => {
  const A = aspectOf(width, height)
  return slotRect(width, height, { x: 80, bottom: pick(A, { square: 60, portrait: 64, story: 120 }), h: pick(A, { square: 100, portrait: 112, story: 128 }) })
}
export function EVT_Swiss({ team, event = {}, width = 1080, height = 1080, palette, parts }) {
  const P = palette
  const slot = slotEV8(width, height)
  const paper = pc(parts, 'ev8Paper', P.paper || '#f6f5f2')
  const ink = pc(parts, 'ev8Ink', P.deepInk || '#15171a')
  const faint = a(ink, 0.5)
  const line = a(ink, 0.2)
  const HELV = "'Helvetica Neue', Helvetica, Arial, sans-serif"
  return (
    <LayerRoot style={{ ...FRAME(width, height), background: paper, color: ink, fontFamily: HELV }}>
      {/* One inset frame holding the whole poster — see EVT_Gazette above. */}
      <div data-layer="Poster content" style={{ position: 'absolute', top: 80, left: 80, right: 80, bottom: height - slot.y + 22, display: 'flex', flexDirection: 'column' }}>
        <div style={{ borderTop: `2px solid ${pc(parts, 'ev8TopRule', ink)}`, paddingTop: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
            {team.logo ? <ClubLogo src={team.logo} size={76} /> : <ClubLogo monogram={team.monogram} color={ink} size={76} shape="shield" />}
            <div style={{ fontSize: 34, fontWeight: 700, letterSpacing: -0.3, color: pc(parts, 'clubColor', ink), lineHeight: 0.98, maxWidth: 520 }}>{team.fullName || team.name}</div>
          </div>
          <div style={{ textAlign: 'right', fontSize: 15, fontWeight: 500, letterSpacing: 2, textTransform: 'uppercase', color: pc(parts, 'ev8NoticeColor', faint) }}>{pt(parts, 'ev8NoticeA', 'Club Notice')}<br />{pt(parts, 'ev8NoticeB', '№ 01 / 25–26')}</div>
        </div>

        <div style={{ marginTop: 'auto' }}>
          <div style={{ fontSize: 16, fontWeight: 700, letterSpacing: 3, textTransform: 'uppercase', color: pc(parts, 'kickerColor', P.accent), marginBottom: 26 }}>{event.kicker}</div>
          <div style={{ display: 'flex', alignItems: 'stretch', gap: 28 }}>
            <div style={{ width: 10, background: pc(parts, 'ev8BarColor', P.accent), flexShrink: 0, margin: '8px 0' }} />
            {/* alignSelf:flex-start keeps this box at its real 2-line height — a
                stretch row would grow it to fit the unclamped measurement pass,
                so AutoFit's height check never trips and a long title clamps to
                an ellipsis. The bar stretches to match it. */}
            <div style={{ height: twoLineBox(152, 0.9), flex: 1, minWidth: 0, alignSelf: 'flex-start' }}>
              <AutoFitText text={event.title} max={152} min={56} lines={2} measureDeps={[event.title]}
                style={{ fontWeight: 800, lineHeight: 0.9, letterSpacing: -3, color: pc(parts, 'title1Color', ink) }} />
            </div>
          </div>
          {event.subtitle ? <div style={{ fontSize: 30, fontWeight: 400, color: pc(parts, 'subtitleColor', a(ink, 0.62)), marginTop: 30, marginLeft: 38, maxWidth: 760, lineHeight: 1.3 }}>{event.subtitle}</div> : null}
        </div>

        <div style={{ marginTop: 'auto', borderTop: `2px solid ${pc(parts, 'ev8DetailRule', ink)}`, paddingTop: 26, display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)' }}>
          {[['Date', event.date], ['Time', event.time], ['Venue', event.venue], ['Entry', event.price]].map(([l, v], i) => (
            <div key={l} style={{ padding: i ? '0 24px' : '0 24px 0 0', borderLeft: i ? `1px solid ${pc(parts, 'dividerColor', line)}` : 'none' }}>
              <div style={{ fontSize: 13, fontWeight: 600, letterSpacing: 2, textTransform: 'uppercase', color: i === 3 ? pc(parts, 'ev8EntryLabel', P.accent) : pc(parts, 'labelColor', faint), marginBottom: 10 }}>{l}</div>
              <div style={{ fontSize: 34, fontWeight: 700, letterSpacing: -0.5, color: pc(parts, 'valueColor', ink) }}>{v}</div>
            </div>
          ))}
        </div>

        <div style={{ marginTop: 28, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 16, fontWeight: 500, color: pc(parts, 'ctaColor', ink) }}>{event.cta}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <BSMark size={17} color={pc(parts, 'markColor', P.accent)} />
            <span style={{ fontSize: 13, fontWeight: 500, letterSpacing: 1, color: pc(parts, 'creditColor', faint) }}>Made with {PLATFORM_NAME}{event.sponsor ? ` · ${event.sponsor}` : ''}</span>
          </div>
        </div>
      </div>
    </LayerRoot>
  )
}
registerParts({
  EV8: [
    colorPart('ev8Paper', 'Paper', 'Page', (p) => p.paper || '#f6f5f2'),
    colorPart('ev8Ink', 'Ink (text and lines)', 'Page', (p) => p.deepInk || '#15171a'),
    colorPart('ev8TopRule', 'Line across the top', 'Header', (p) => p.deepInk || '#15171a'),
    colorPart('clubColor', 'Club name', 'Header', (p) => p.deepInk || '#15171a'),
    textPart('ev8NoticeA', 'Notice words, first line', 'Header', () => 'Club Notice'),
    textPart('ev8NoticeB', 'Notice words, second line', 'Header', () => '№ 01 / 25–26'),
    colorPart('ev8NoticeColor', 'Notice words', 'Header', (p) => p.deepInk || '#15171a'),
    colorPart('kickerColor', 'Line above the title', 'Heading', (p) => p.accent),
    colorPart('ev8BarColor', 'Bar beside the title', 'Heading', (p) => p.accent),
    colorPart('title1Color', 'Title', 'Heading', (p) => p.deepInk || '#15171a'),
    colorPart('subtitleColor', 'Subtitle', 'Heading', (p) => p.deepInk || '#15171a'),
    colorPart('ev8DetailRule', 'Line above the details', 'Details', (p) => p.deepInk || '#15171a'),
    colorPart('dividerColor', 'Lines between details', 'Details', (p) => p.deepInk || '#15171a'),
    colorPart('labelColor', 'Date, Time and Venue labels', 'Details', (p) => p.deepInk || '#15171a'),
    colorPart('ev8EntryLabel', 'Entry label', 'Details', (p) => p.accent),
    colorPart('valueColor', 'Date, time, venue and price', 'Details', (p) => p.deepInk || '#15171a'),
    colorPart('ctaColor', 'Call to action', 'Foot', (p) => p.deepInk || '#15171a'),
    colorPart('markColor', 'Logo mark', 'Foot', (p) => p.accent),
    colorPart('creditColor', 'Credit and sponsor line', 'Foot', (p) => p.deepInk || '#15171a'),
  ],
})

// ─────────────────────────────────────────────────────────────────────────────
// EV9 — CREST · heritage emblem, gold-on-green serif (prestige occasions)
// Uses palette.primary as the deep field, palette.accent as the gold.
// ─────────────────────────────────────────────────────────────────────────────
// Crest: the grid is a strip inside the double gold rule, under the watermark
// line. The emblem and the headline are a little smaller on the square.
const slotEV9 = (width, height) => {
  const A = aspectOf(width, height)
  return slotRect(width, height, { x: 96, bottom: pick(A, { square: 72, portrait: 76, story: 112 }), h: pick(A, { square: 100, portrait: 112, story: 128 }) })
}
export function EVT_Crest({ team, event = {}, width = 1080, height = 1080, palette, motif, parts }) {
  const P = palette
  const texture = usePostLook().texture !== false
  const aspect = aspectOf(width, height)
  const slot = slotEV9(width, height)
  const tight = aspect === 'square'
  const cream = pc(parts, 'ev9Cream', P.cream || '#f3ead2')
  const SERIF = "'Cormorant Garamond', serif"
  const line = a(P.accent, 0.55)
  // The ribbon's words follow its colour once the club has set one.
  const ribbonBg = pc(parts, 'bandBg', P.accent)
  return (
    <LayerRoot style={{ ...FRAME(width, height), background: P.primary, color: cream, fontFamily: SERIF }}>
      {texture ? <div style={{ position: 'absolute', left: 0, right: 0, top: 0, height: share(height, 560), background: `radial-gradient(ellipse 600px 420px at 50% 0%, ${a(pc(parts, 'ev9GlowColor', P.accent), 0.18)}, transparent 70%)` }} /> : null}
      <div style={{ position: 'absolute', inset: 44, border: `2px solid ${pc(parts, 'ev9FrameColor', line)}`, pointerEvents: 'none' }} />
      <div style={{ position: 'absolute', inset: 52, border: `1px solid ${pc(parts, 'ev9InnerFrame', a(P.accent, 0.3))}`, pointerEvents: 'none' }} />

      <div style={{ position: 'absolute', top: tight ? 74 : 84, left: 96, right: 96, bottom: height - slot.y + 14, display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
        <div style={{ width: tight ? 176 : 264, height: tight ? 176 : 264, borderRadius: '50%', border: `2px solid ${pc(parts, 'ev9EmblemRing', P.accent)}`, display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
          <div style={{ position: 'absolute', inset: 13, borderRadius: '50%', border: `1px dashed ${pc(parts, 'ev9EmblemDash', a(P.accent, 0.3))}` }} />
          {team.logo ? <ClubLogo src={team.logo} size={tight ? 124 : 186} /> : <img src={motif?.icon || icoTrophy} alt="" style={{ width: tight ? 88 : 130, height: tight ? 88 : 130, objectFit: 'contain' }} />}
        </div>

        <div style={{ marginTop: tight ? 16 : 26, background: ribbonBg, color: pc(parts, 'nameColor', partPicked(parts, 'bandBg') ? inkOn(ribbonBg) : P.primary), fontFamily: MONO, fontSize: 22, fontWeight: 700, letterSpacing: 4, textTransform: 'uppercase', padding: tight ? '9px 50px' : '12px 50px', clipPath: 'polygon(0 0, 100% 0, calc(100% - 20px) 50%, 100% 100%, 0 100%, 20px 50%)' }}>{team.name}</div>

        <div style={{ marginTop: 'auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 16, marginBottom: tight ? 12 : 20 }}>
            <div style={{ width: 80, height: 1, background: pc(parts, 'ev9OrnamentColor', P.accent) }} />
            <div style={{ width: 9, height: 9, background: pc(parts, 'ev9OrnamentColor', P.accent), transform: 'rotate(45deg)' }} />
            <div style={{ width: 80, height: 1, background: pc(parts, 'ev9OrnamentColor', P.accent) }} />
          </div>
          <div style={{ fontFamily: MONO, fontSize: 17, letterSpacing: 6, textTransform: 'uppercase', color: pc(parts, 'kickerColor', P.accent), marginBottom: tight ? 8 : 14 }}>{event.kicker}</div>
          <div style={{ height: twoLineBox(tight ? 110 : 130, 0.92), display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <AutoFitText text={event.title} max={tight ? 110 : 130} min={52} lines={2} measureDeps={[event.title]}
              style={{ fontFamily: SERIF, fontWeight: 700, lineHeight: 0.92, color: pc(parts, 'title1Color', cream), letterSpacing: 1 }} />
          </div>
          {event.subtitle ? <div style={{ fontFamily: SERIF, fontStyle: 'italic', fontWeight: 500, fontSize: tight ? 28 : 36, color: pc(parts, 'subtitleColor', a(cream, 0.72)), marginTop: tight ? 8 : 16, maxWidth: 720, marginLeft: 'auto', marginRight: 'auto', lineHeight: 1.32 }}>{event.subtitle}</div> : null}
        </div>

        <div style={{ marginTop: 'auto', width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 16, marginBottom: tight ? 16 : 30 }}>
            <div style={{ width: 60, height: 1, background: pc(parts, 'ev9Ornament2Color', line) }} />
            <div style={{ width: 7, height: 7, background: pc(parts, 'ev9Ornament2Color', P.accent), transform: 'rotate(45deg)' }} />
            <div style={{ width: 60, height: 1, background: pc(parts, 'ev9Ornament2Color', line) }} />
          </div>
          <div style={{ display: 'flex', alignItems: 'stretch' }}>
            {[['Date', event.date], ['Time', event.time], ['Venue', event.venue]].map(([l, v], i) => (
              <div key={l} style={{ padding: '0 40px', textAlign: 'center', borderLeft: i ? `1px solid ${pc(parts, 'dividerColor', line)}` : 'none' }}>
                <div style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 3, textTransform: 'uppercase', color: pc(parts, 'labelColor', P.accent) }}>{l}</div>
                <div style={{ fontFamily: SERIF, fontWeight: 600, fontSize: tight ? 36 : 40, color: pc(parts, 'valueColor', cream), marginTop: 4 }}>{v}</div>
              </div>
            ))}
          </div>
          {(event.cta || event.price) ? <div style={{ marginTop: tight ? 16 : 28, fontFamily: MONO, fontSize: 15, letterSpacing: 3, textTransform: 'uppercase', color: pc(parts, 'ctaColor', cream), border: `1px solid ${pc(parts, 'ev9CtaBorder', P.accent)}`, borderRadius: 2, padding: '11px 28px' }}>{[event.cta, event.price].filter(Boolean).join(' · ')}</div> : null}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: tight ? 14 : 26 }}>
            <BSMark size={17} color={pc(parts, 'markColor', '#f25aa6')} />
            <span style={{ fontFamily: MONO, fontSize: 12, letterSpacing: 2, textTransform: 'uppercase', color: pc(parts, 'creditColor', a(cream, 0.72)) }}>Made with {PLATFORM_NAME}{event.sponsor ? ` · ${event.sponsor}` : ''}</span>
          </div>
        </div>
      </div>
    </LayerRoot>
  )
}
registerParts({
  EV9: [
    colorPart('ev9Cream', 'Cream (text colour)', 'Page', (p) => p.cream || '#f3ead2'),
    colorPart('ev9GlowColor', 'Glow at the top', 'Page', (p) => p.accent),
    colorPart('ev9FrameColor', 'Outer frame', 'Frame and emblem', (p) => p.accent),
    colorPart('ev9InnerFrame', 'Inner frame', 'Frame and emblem', (p) => p.accent),
    colorPart('ev9EmblemRing', 'Emblem ring', 'Frame and emblem', (p) => p.accent),
    colorPart('ev9EmblemDash', 'Emblem inner ring', 'Frame and emblem', (p) => p.accent),
    colorPart('bandBg', 'Name ribbon', 'Frame and emblem', (p) => p.accent),
    colorPart('nameColor', 'Name on the ribbon', 'Frame and emblem', (p) => p.primary),
    colorPart('ev9OrnamentColor', 'Ornament above the title', 'Heading', (p) => p.accent),
    colorPart('kickerColor', 'Line above the title', 'Heading', (p) => p.accent),
    colorPart('title1Color', 'Title', 'Heading', (p) => p.cream || '#f3ead2'),
    colorPart('subtitleColor', 'Subtitle', 'Heading', (p) => p.cream || '#f3ead2'),
    colorPart('ev9Ornament2Color', 'Ornament above the details', 'Details', (p) => p.accent),
    colorPart('labelColor', 'Date, Time and Venue labels', 'Details', (p) => p.accent),
    colorPart('valueColor', 'Date, time and venue', 'Details', (p) => p.cream || '#f3ead2'),
    colorPart('dividerColor', 'Lines between details', 'Details', (p) => p.accent),
    colorPart('ctaColor', 'Call to action', 'Foot', (p) => p.cream || '#f3ead2'),
    colorPart('ev9CtaBorder', 'Call to action outline', 'Foot', (p) => p.accent),
    colorPart('markColor', 'Logo mark', 'Foot', () => '#f25aa6'),
    colorPart('creditColor', 'Credit and sponsor line', 'Foot', (p) => p.cream || '#f3ead2'),
  ],
})

// ─────────────────────────────────────────────────────────────────────────────
// EV10 — CHALKBOARD · clubhouse blackboard, chalk handwriting (casual notices)
// ─────────────────────────────────────────────────────────────────────────────
// Chalkboard: the grid is a pinned paper strip inside the chalk border, below the
// notice. The notice is a little tighter on the square to leave it room.
const slotEV10 = (width, height) => {
  const A = aspectOf(width, height)
  return slotRect(width, height, { x: 92, bottom: pick(A, { square: 72, portrait: 76, story: 112 }), h: pick(A, { square: 100, portrait: 112, story: 128 }) })
}
export function EVT_Chalkboard({ team, event = {}, width = 1080, height = 1080, palette, parts }) {
  const P = palette
  const texture = usePostLook().texture !== false
  const aspect = aspectOf(width, height)
  const slot = slotEV10(width, height)
  const tight = aspect === 'square'
  const board = P.primary || '#20251f'
  // The chalk colour, and its two softer strengths, which follow it once it is set.
  const chalk = pc(parts, 'ev10Chalk', '#f1efe4')
  const chalk2 = partPicked(parts, 'ev10Chalk') ? a(chalk, 0.74) : 'rgba(241,239,228,0.74)'
  const faint = partPicked(parts, 'ev10Chalk') ? a(chalk, 0.4) : 'rgba(241,239,228,0.4)'
  const HAND = "'Caveat', cursive"
  return (
    <LayerRoot style={{ ...FRAME(width, height), background: board, color: chalk }}>
      {texture ? <div style={{ position: 'absolute', left: '8%', top: '14%', width: 420, height: 300, background: 'radial-gradient(ellipse, rgba(255,255,255,0.05), transparent 70%)', transform: 'rotate(-18deg)' }} /> : null}
      {texture ? <div style={{ position: 'absolute', right: '6%', bottom: '18%', width: 380, height: 260, background: 'radial-gradient(ellipse, rgba(255,255,255,0.045), transparent 70%)', transform: 'rotate(12deg)' }} /> : null}
      <div style={{ position: 'absolute', inset: 44, border: `2px dashed ${pc(parts, 'ev10BorderColor', faint)}`, borderRadius: 8, pointerEvents: 'none' }} />

      <div style={{ position: 'absolute', top: tight ? 76 : 88, left: 92, right: 92, bottom: height - slot.y + 14, display: 'flex', flexDirection: 'column' }}>
        <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: 20 }}>
          {team.logo ? <ClubLogo src={team.logo} size={tight ? 76 : 88} /> : <ClubLogo monogram={team.monogram} color={chalk} size={tight ? 76 : 88} shape="shield" />}
          <div>
            <div style={{ fontWeight: 700, fontSize: 28, letterSpacing: 3, textTransform: 'uppercase', color: pc(parts, 'clubColor', chalk), lineHeight: 1 }}>{team.fullName || team.name}</div>
            <div style={{ fontWeight: 600, fontSize: 15, letterSpacing: 5, textTransform: 'uppercase', color: pc(parts, 'ev10TaglineColor', chalk2), marginTop: 6 }}>{pt(parts, 'ev10Tagline', 'Notice Board')}</div>
            <div style={{ width: 300, height: 3, background: pc(parts, 'ev10UnderlineColor', chalk), borderRadius: 3, transform: 'rotate(-1deg)', marginTop: 10, opacity: 0.85 }} />
          </div>
        </div>

        {/* The notice and its details are ONE block: centred on square/portrait,
            and pinned a set distance below the masthead on a story (the board
            extends below it) rather than stranding the masthead above a huge gap. */}
        <div style={{ marginTop: pick(aspect, { square: 'auto', portrait: 'auto', story: 104 }), marginBottom: 'auto', width: '100%', paddingTop: tight ? 14 : 34 }}>
          <div style={{ fontFamily: HAND, fontWeight: 600, fontSize: tight ? 42 : 48, color: pc(parts, 'kickerColor', P.accent), lineHeight: 1, marginBottom: 6, transform: 'rotate(-1deg)' }}>{event.kicker}</div>
          <div style={{ height: twoLineBox(tight ? 136 : 172, 0.82), transform: 'rotate(-1.5deg)', display: 'flex', alignItems: 'flex-end' }}>
            <AutoFitText text={event.title} max={tight ? 136 : 172} min={64} lines={2} measureDeps={[event.title]}
              style={{ fontFamily: HAND, fontWeight: 700, lineHeight: 0.82, color: pc(parts, 'title1Color', chalk) }} />
          </div>
          {event.subtitle ? <div style={{ fontFamily: HAND, fontWeight: 500, fontSize: tight ? 38 : 46, color: pc(parts, 'subtitleColor', chalk2), marginTop: tight ? 8 : 16, maxWidth: 780, lineHeight: 1.15 }}>{event.subtitle}</div> : null}

          <div style={{ border: `2px dashed ${pc(parts, 'cardBorder', faint)}`, borderRadius: 10, padding: pick(aspect, { square: '8px 30px', portrait: '22px 30px', story: '26px 32px' }), marginTop: pick(aspect, { square: 18, portrait: 44, story: 52 }) }}>
            {[['When', `${event.date || ''}${event.date && event.time ? ' · ' : ''}${event.time || ''}`], ['Where', event.venue], ['Cost', event.price]].map(([l, v]) => (
              <div key={l} style={{ display: 'flex', alignItems: 'center', gap: 18, padding: tight ? '5px 0' : '11px 0' }}>
                <span style={{ fontWeight: 600, fontSize: 14, letterSpacing: 3, textTransform: 'uppercase', color: pc(parts, 'labelColor', P.accent), width: 90 }}>{l}</span>
                <span style={{ fontFamily: HAND, fontWeight: 600, fontSize: tight ? 40 : 44, color: pc(parts, 'valueColor', chalk), lineHeight: 1.08, whiteSpace: 'nowrap' }}>{v}</span>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: tight ? 14 : 26 }}>
            {event.cta ? <div style={{ fontFamily: HAND, fontWeight: 700, fontSize: tight ? 40 : 46, color: pc(parts, 'ctaColor', P.accent), border: `3px solid ${pc(parts, 'ev10CtaBorder', P.accent)}`, borderRadius: '60% 58% 62% 56%', padding: tight ? '4px 30px' : '8px 34px', transform: 'rotate(-2deg)', lineHeight: 1 }}>{event.cta}</div> : <span />}
            <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
              <BSMark size={18} color={pc(parts, 'markColor', '#f25aa6')} />
              <span style={{ fontWeight: 500, fontSize: 13, letterSpacing: 1, color: pc(parts, 'creditColor', chalk2) }}>{PLATFORM_NAME}{event.sponsor ? ` · ${event.sponsor}` : ''}</span>
            </div>
          </div>
        </div>
      </div>
    </LayerRoot>
  )
}
registerParts({
  EV10: [
    colorPart('ev10Chalk', 'Chalk (text colour)', 'Board', () => '#f1efe4'),
    colorPart('ev10BorderColor', 'Dashed border round the board', 'Board', () => '#f1efe4'),
    colorPart('clubColor', 'Club name', 'Header', () => '#f1efe4'),
    textPart('ev10Tagline', 'Words under the club name', 'Header', () => 'Notice Board'),
    colorPart('ev10TaglineColor', 'Words under the club name', 'Header', () => '#f1efe4'),
    colorPart('ev10UnderlineColor', 'Chalk line under the club name', 'Header', () => '#f1efe4'),
    colorPart('kickerColor', 'Handwriting above the title', 'Heading', (p) => p.accent),
    colorPart('title1Color', 'Title', 'Heading', () => '#f1efe4'),
    colorPart('subtitleColor', 'Subtitle', 'Heading', () => '#f1efe4'),
    colorPart('cardBorder', 'Dashed box round the details', 'Details', () => '#f1efe4'),
    colorPart('labelColor', 'When, Where and Cost labels', 'Details', (p) => p.accent),
    colorPart('valueColor', 'Date, time, venue and price', 'Details', () => '#f1efe4'),
    colorPart('ctaColor', 'Call to action', 'Foot', (p) => p.accent),
    colorPart('ev10CtaBorder', 'Call to action circle', 'Foot', (p) => p.accent),
    colorPart('markColor', 'Logo mark', 'Foot', () => '#f25aa6'),
    colorPart('creditColor', 'Credit and sponsor line', 'Foot', () => '#f1efe4'),
  ],
})

// ─────────────────────────────────────────────────────────────────────────────
// EV11 — POLAROID · taped scrapbook photo + marker pen (photo-led socials)
// ─────────────────────────────────────────────────────────────────────────────
// Polaroid: the grid is a strip along the foot of the scrapbook page, under the
// small credit line. The taped photo is a little smaller on the square.
const slotEV11 = (width, height) => {
  const A = aspectOf(width, height)
  return slotRect(width, height, { x: 76, bottom: pick(A, { square: 50, portrait: 56, story: 116 }), h: pick(A, { square: 100, portrait: 112, story: 132 }) })
}
export function EVT_Polaroid({ team, event = {}, width = 1080, height = 1080, palette, motif, parts }) {
  const P = palette
  const texture = usePostLook().texture !== false
  const aspect = aspectOf(width, height)
  const slot = slotEV11(width, height)
  const tight = aspect === 'square'
  const paper = pc(parts, 'ev11Paper', P.paper || '#ece3d0')
  const ink = pc(parts, 'ev11Ink', P.deepInk || '#2e2a22')
  // The tag's words follow its colour once the club has set one.
  const ctaBg = pc(parts, 'ctaBg', ink)
  const MARKER = "'Permanent Marker', cursive"
  const HAND = "'Caveat', cursive"
  // The polaroid is the hero, so it grows with the canvas — a fixed 404 square
  // adrift in a 1920 story reads as a stamp lost on the page.
  const photo = pick(aspect, { square: 350, portrait: 470, story: 540 })
  return (
    <LayerRoot style={{ ...FRAME(width, height), background: paper, color: ink }}>
      {texture ? <div style={{ position: 'absolute', inset: 0, backgroundImage: 'radial-gradient(rgba(120,100,70,0.06) 1px, transparent 1.4px)', backgroundSize: '5px 5px', opacity: 0.6 }} /> : null}
      <div style={{ position: 'absolute', top: tight ? 64 : 76, left: 76, right: 76, bottom: height - slot.y + 14, display: 'flex', flexDirection: 'column' }}>
        <div style={{ marginBottom: tight ? 10 : 18 }}>
          <BrandLockup team={team} palette={P} size={tight ? 76 : 84} nameColor={pc(parts, 'clubColor', ink)} nameSize={30} />
        </div>
        <div style={{ flexShrink: 0 }}>
          <div style={{ fontFamily: HAND, fontWeight: 600, fontSize: 46, color: pc(parts, 'kickerColor', P.accent), lineHeight: 1, transform: 'rotate(-1deg)' }}>{event.kicker}</div>
          <div style={{ height: pick(aspect, { square: 128, portrait: 162, story: 176 }), marginTop: 4, display: 'flex', alignItems: 'flex-end' }}>
            <AutoFitText text={event.title} max={tight ? 104 : 118} min={44} lines={1} measureDeps={[event.title]}
              style={{ fontFamily: MARKER, lineHeight: 0.9, color: pc(parts, 'title1Color', ink) }} />
          </div>
        </div>

        <div style={{ display: 'flex', gap: pick(aspect, { square: 54, portrait: 54, story: 60 }), alignItems: 'center', marginTop: pick(aspect, { square: 'auto', portrait: 'auto', story: 90 }), marginBottom: 'auto' }}>
          <div style={{ position: 'relative', flexShrink: 0, transform: 'rotate(-3.5deg)' }}>
            <div style={{ position: 'absolute', top: -20, left: 54, width: 150, height: 42, background: a(pc(parts, 'ev11TapeColor', P.accent), 0.42), transform: 'rotate(-7deg)', boxShadow: '0 2px 6px rgba(0,0,0,0.08)', zIndex: 2 }} />
            <div style={{ background: pc(parts, 'cardBg', '#fff'), padding: '18px 18px 26px', boxShadow: '0 22px 50px rgba(60,45,25,0.26)' }}>
              <div style={{ width: photo, height: photo, overflow: 'hidden', background: motif?.imageUrl ? undefined : 'repeating-linear-gradient(135deg, #e8ddc7 0px, #e8ddc7 16px, #ddd0b4 16px, #ddd0b4 32px)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                {motif?.imageUrl
                  ? <img src={motif.imageUrl} alt="" crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  : <span style={{ fontFamily: MONO, fontSize: 14, letterSpacing: 3, textTransform: 'uppercase', color: 'rgba(80,64,40,0.6)', background: '#fff', padding: '6px 14px' }}>{motif?.label || 'Add a photo'}</span>}
              </div>
              <div style={{ fontFamily: HAND, fontWeight: 600, fontSize: 48, color: pc(parts, 'ev11CaptionColor', '#2e2a22'), textAlign: 'center', marginTop: 12, lineHeight: 1 }}>{event.date}</div>
            </div>
          </div>

          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'inline-block', fontWeight: 600, fontSize: 14, letterSpacing: 3, textTransform: 'uppercase', color: pc(parts, 'ev11StampColor', P.accent), border: `2px solid ${pc(parts, 'ev11StampBorder', P.accent)}`, padding: '8px 16px', transform: 'rotate(-6deg)', opacity: 0.92 }}>{pt(parts, 'ev11Stamp', '★ Save the Date')}</div>
            {[['When', `${event.date || ''}${event.date && event.time ? ' · ' : ''}${event.time || ''}`], ['Where', event.venue], ['Cost', event.price]].map(([l, v], i) => (
              <div key={l} style={{ marginTop: i ? pick(aspect, { square: 22, portrait: 26, story: 30 }) : pick(aspect, { square: 32, portrait: 38, story: 44 }) }}>
                <div style={{ fontWeight: 600, fontSize: 13, letterSpacing: 3, textTransform: 'uppercase', color: pc(parts, 'labelColor', P.accent), marginBottom: 2 }}>{l}</div>
                <div style={{ fontFamily: HAND, fontWeight: 600, fontSize: pick(aspect, { square: 50, portrait: 54, story: 58 }), color: pc(parts, 'valueColor', ink), lineHeight: 1.02 }}>{v}</div>
              </div>
            ))}
            {event.cta ? <div style={{ marginTop: pick(aspect, { square: 28, portrait: 34, story: 40 }), display: 'inline-block', background: ctaBg, color: pc(parts, 'ctaColor', partPicked(parts, 'ctaBg') ? inkOn(ctaBg) : paper), fontFamily: MARKER, fontSize: 30, padding: '12px 28px', transform: 'rotate(-1.5deg)' }}>{event.cta}</div> : null}
          </div>
        </div>

        <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: 9 }}>
          <BSMark size={18} color={pc(parts, 'markColor', '#be185d')} />
          <span style={{ fontWeight: 500, fontSize: 13, letterSpacing: 1, color: pc(parts, 'creditColor', a(ink, 0.5)) }}>{team.name} · Made with {PLATFORM_NAME}{event.sponsor ? ` · ${event.sponsor}` : ''}</span>
        </div>
      </div>
    </LayerRoot>
  )
}
registerParts({
  EV11: [
    colorPart('ev11Paper', 'Paper', 'Page', (p) => p.paper || '#ece3d0'),
    colorPart('ev11Ink', 'Ink (text colour)', 'Page', (p) => p.deepInk || '#2e2a22'),
    colorPart('clubColor', 'Club name', 'Heading', (p) => p.deepInk || '#2e2a22'),
    colorPart('kickerColor', 'Handwriting above the title', 'Heading', (p) => p.accent),
    colorPart('title1Color', 'Title', 'Heading', (p) => p.deepInk || '#2e2a22'),
    colorPart('ev11TapeColor', 'Tape on the photo', 'Photo', (p) => p.accent),
    colorPart('cardBg', 'Photo frame', 'Photo', () => '#ffffff'),
    colorPart('ev11CaptionColor', 'Date under the photo', 'Photo', () => '#2e2a22'),
    textPart('ev11Stamp', 'Stamp words', 'Details', () => '★ Save the Date'),
    colorPart('ev11StampColor', 'Stamp text', 'Details', (p) => p.accent),
    colorPart('ev11StampBorder', 'Stamp outline', 'Details', (p) => p.accent),
    colorPart('labelColor', 'When, Where and Cost labels', 'Details', (p) => p.accent),
    colorPart('valueColor', 'Date, time, venue and price', 'Details', (p) => p.deepInk || '#2e2a22'),
    colorPart('ctaBg', 'Call to action tag', 'Foot', (p) => p.deepInk || '#2e2a22'),
    colorPart('ctaColor', 'Call to action text', 'Foot', (p) => p.paper || '#ece3d0'),
    colorPart('markColor', 'Logo mark', 'Foot', () => '#be185d'),
    colorPart('creditColor', 'Credit and sponsor line', 'Foot', (p) => p.deepInk || '#2e2a22'),
  ],
})

// ─────────────────────────────────────────────────────────────────────────────
// REGISTRY — drop these straight into AdminSocialPost's TEMPLATES array.
// `kind: 'event'` keeps them on their own "Events" tab.
// `surface: 'light'` flags the paper-backed directions so the designer can hide
// the dark-mode toggle for them.
// ─────────────────────────────────────────────────────────────────────────────
export const EVENT_TEMPLATES = [
  { id: 'EV1',  name: 'Floodlit',    component: EVT_Floodlit,   desc: 'Full-bleed photo + opacity filter', surface: 'dark',  photo: true },
  { id: 'EV2',  name: 'Colour Block', component: EVT_Block,      desc: 'Club colour leads, giant motif',    surface: 'dark',  photo: true },
  { id: 'EV3',  name: 'Ticket',      component: EVT_Ticket,     desc: 'Refined, editorial, motif mark',    surface: 'light', photo: false },
  { id: 'EV4',  name: 'Scoreboard',  component: EVT_Scoreboard, desc: 'LED dot-matrix, mono numerals',     surface: 'dark',  photo: false },
  { id: 'EV5',  name: 'Gazette',     component: EVT_Gazette,    desc: 'Newspaper masthead, serif',         surface: 'light', photo: true },
  { id: 'EV6',  name: 'Sticker Pop', component: EVT_Sticker,    desc: 'Playful rounded badges',            surface: 'light', photo: true },
  { id: 'EV7',  name: 'Kinetic',     component: EVT_Kinetic,    desc: 'Diagonal bands, italic motion',     surface: 'dark',  photo: true },
  { id: 'EV8',  name: 'Swiss',       component: EVT_Swiss,      desc: 'Ultra-minimal Helvetica grid',      surface: 'light', photo: false },
  { id: 'EV9',  name: 'Crest',       component: EVT_Crest,      desc: 'Heritage emblem, gold-on-green',    surface: 'dark',  photo: false },
  { id: 'EV10', name: 'Chalkboard',  component: EVT_Chalkboard, desc: 'Clubhouse blackboard handwriting',  surface: 'dark',  photo: false },
  { id: 'EV11', name: 'Polaroid',    component: EVT_Polaroid,   desc: 'Taped scrapbook photo + marker',    surface: 'light', photo: true },
  // A run of events on one post (agenda, calendar, icon cards).
  ...EVENT_LIST_TEMPLATES,
]

// ─────────────────────────────────────────────────────────────────────────────
// MOTIFS — bundled 3D glyphs for the faded watermark (no photo case). Curry /
// Music / Quiz etc. have no literal glyph, so they map to the nearest mark and
// lean on an uploaded background photo for the themed look.
// ─────────────────────────────────────────────────────────────────────────────
const ALL_EVENT_MOTIFS = [
  { key: 'trophy',    label: 'Trophy',     icon: icoTrophy },
  { key: 'medal',     label: 'Medal',      icon: icoMedal },
  { key: 'handshake', label: 'Handshake',  icon: icoHandshake },
  { key: 'bat',       label: 'Cricket bat', icon: icoBat },
  { key: 'star',      label: 'Star',       icon: icoStar },
  { key: 'target',    label: 'Target',     icon: icoTarget },
  { key: 'bolt',      label: 'Lightning',  icon: icoBolt },
  { key: 'calendar',  label: 'Calendar',   icon: icoCalendar },
  { key: 'necktie',   label: 'Black tie',  icon: icoNecktie },
  { key: 'ribbon',    label: 'Ribbon',     icon: icoRibbon },
]
// The football build has no use for a cricket bat as a watermark.
export const EVENT_MOTIFS = IS_AFL ? ALL_EVENT_MOTIFS.filter(m => m.key !== 'bat') : ALL_EVENT_MOTIFS
const motifIcon = (key) => (EVENT_MOTIFS.find((m) => m.key === key) || EVENT_MOTIFS[0]).icon

// ─────────────────────────────────────────────────────────────────────────────
// PRESETS — one-click event facts. Selecting a preset fills the `event` object
// and picks a sensible default template + motif; everything stays editable.
// ─────────────────────────────────────────────────────────────────────────────
const ALL_EVENT_PRESETS = [
  {
    key: 'auction', label: 'Auction Night', template: 'EV2', motif: 'handshake', photoLabel: 'Auction / lots photo',
    event: { kicker: 'Annual Fundraiser', title: 'Auction Night', subtitle: 'Bid on signed gear, mystery lots & big-ticket experiences. Every dollar backs the club.', date: 'Sat 9 Aug', time: '6:30 PM', venue: 'Function Room', price: '$40', cta: 'Book your table', sponsor: '' },
  },
  {
    key: '100club', label: 'The 100 Club', template: 'EV2', motif: 'medal', photoLabel: '',
    event: { kicker: "Members' Cash Draw", title: 'The 100 Club', subtitle: 'Ten dollars a number. One drawn each month. Half the pot is yours.', date: 'Drawn 1st Fri', time: 'Monthly', venue: 'The Clubhouse', price: '$10', cta: 'Grab your number', sponsor: 'Junior program fund' },
  },
  {
    key: 'curry', label: 'Curry Night', template: 'EV1', motif: 'star', photoLabel: 'Curry / food photo',
    event: { kicker: 'Club Social', title: 'Curry Night', subtitle: 'A night of spice, cold beers & cricket chat. All members & families welcome.', date: 'Fri 18 Jul', time: '7:00 PM', venue: 'The Clubhouse', price: '$25 / head', cta: 'RSVP by Wed 16 Jul', sponsor: '' },
  },
  {
    key: 'selections', label: 'Selections', template: 'EV4', motif: 'bat', photoLabel: 'Squad / team photo',
    event: { kicker: 'Round 1 · 25/26', title: 'Selections', subtitle: 'First-grade XI named for the season opener. Full team list below.', date: 'Sat 4 Oct', time: '10:30 AM', venue: 'Ashcombe Oval', price: '1ST XI', cta: 'Congrats to all named', sponsor: '' },
  },
  {
    key: 'presentation', label: 'Presentation Night', template: 'EV9', motif: 'trophy', photoLabel: 'Team photo',
    event: { kicker: 'Founded 1921', title: 'Presentation Night', subtitle: "Celebrating the season's finest — awards, life memberships & a few tall tales.", date: 'Sat 20 Sep', time: '7:00 PM', venue: 'The Pavilion', price: '$55', cta: 'RSVP by 12 Sep', sponsor: '' },
  },
  {
    key: 'launch', label: 'Season Launch', template: 'EV7', motif: 'calendar', photoLabel: 'Action / team photo',
    event: { kicker: 'Round 1 · 25/26', title: 'Season Launch', subtitle: 'New season, new caps. Meet the squads and kick off the campaign.', date: 'Sat 4 Oct', time: '11:00 AM', venue: 'Ashcombe Oval', price: 'Free', cta: 'Bring the family', sponsor: '' },
  },
  {
    key: 'music', label: 'Live Music', template: 'EV11', motif: 'star', photoLabel: 'Band / live photo',
    event: { kicker: 'Friday Sessions', title: 'Live Music', subtitle: 'Local legends on stage. Bar open late, kitchen running til nine.', date: 'Sat 26 Jul', time: '8:00 PM', venue: 'The Clubhouse', price: '$15 entry', cta: 'Tickets at the bar', sponsor: '' },
  },
  {
    key: 'quiz', label: 'Quiz Night', template: 'EV6', motif: 'target', photoLabel: '',
    event: { kicker: 'Trivia & Pizza', title: 'Quiz Night', subtitle: 'Six rounds, one champion table. Teams of up to six players.', date: 'Thu 14 Aug', time: '7:30 PM', venue: 'The Clubhouse', price: '$12', cta: 'Build your team', sponsor: 'Pizza by Forno 47' },
  },
  {
    key: 'generic', label: 'Generic / Blank', template: 'EV8', motif: 'star', photoLabel: 'Add a photo',
    event: { kicker: 'Save the Date', title: 'Club Notice', subtitle: 'Your headline goes here. One template, any announcement — clean and unmistakable.', date: 'Date', time: 'Time', venue: 'Venue', price: 'Free', cta: 'Details to follow.', sponsor: 'Your sponsor here' },
  },
]

// The football build keeps every preset and rewrites the few words that are
// cricket's own (an XI, a first-grade side, cricket chat), so a club posting a
// footy social night isn't handed cricket copy to correct.
const AFL_PRESET_EVENT = {
  curry: { subtitle: 'A night of spice, cold beers & footy chat. All members & families welcome.' },
  selections: { kicker: 'Round 1 · 2026', subtitle: 'Senior side named for the season opener. Full team list below.', price: 'SENIORS', venue: 'Home Ground' },
  presentation: { subtitle: "Celebrating the season's finest: the best & fairest, life memberships & a few tall tales." },
  launch: { kicker: 'Round 1 · 2026', subtitle: 'New season, new jumpers. Meet the squads and kick off the campaign.', venue: 'Home Ground' },
}
export const EVENT_PRESETS = IS_AFL
  ? ALL_EVENT_PRESETS.map(p => ({
      ...p,
      motif: p.motif === 'bat' ? 'star' : p.motif,
      event: { ...p.event, ...(AFL_PRESET_EVENT[p.key] || {}) },
    }))
  : ALL_EVENT_PRESETS

export const DEFAULT_EVENT = { ...EVENT_PRESETS[2].event }
export const DEFAULT_EVENT_MOTIF = { key: 'star', icon: motifIcon('star'), imageUrl: null, opacity: 0.85, label: 'Add a photo' }

// Resolve a motif descriptor for a template, given the chosen motif key + any
// uploaded photo. Pass the result straight to a template's `motif` prop.
export function resolveMotif({ motifKey, imageUrl, opacity, label, customIcon }) {
  // `custom` is an icon the club searched for (a data URI it keeps with the post).
  const icon = motifKey === 'custom' && customIcon ? customIcon : motifIcon(motifKey)
  return { key: motifKey, icon, imageUrl: imageUrl || null, opacity: opacity ?? 0.85, label: label || 'Add a photo' }
}

// ─────────────────────────────────────────────────────────────────────────────
// EVENT LIST — the raw items the editor holds, and the prepared form the list
// layouts draw (event-list-templates.jsx). A layout never parses a date or looks
// an icon up.
//   raw item: { id, date: 'YYYY-MM-DD' | '', title, time, venue, price,
//               iconKey: motif key | 'custom' | '', iconUri, imageUrl }
// ─────────────────────────────────────────────────────────────────────────────
export { MAX_LIST_ITEMS }
const MONTHS = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER']
const WEEKDAYS = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']
const ISO = /^(\d{4})-(\d{2})-(\d{2})$/

export const parseIsoDate = (iso) => {
  const m = ISO.exec(iso || '')
  if (!m) return null
  const [y, mo, d] = [Number(m[1]), Number(m[2]) - 1, Number(m[3])]
  const dt = new Date(Date.UTC(y, mo, d))
  // A date that does not exist (31 Feb) is not a date.
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === mo && dt.getUTCDate() === d ? { y, mo, d, wd: dt.getUTCDay() } : null
}

export function prepareEventList(raw = {}) {
  const items = (raw.items || []).slice(0, MAX_LIST_ITEMS).map((it, i) => {
    const p = parseIsoDate(it.date)
    const mon = p ? MONTHS[p.mo].slice(0, 3) : ''
    const wd = p ? WEEKDAYS[p.wd] : ''
    const iconSrc = it.iconKey === 'custom' ? it.iconUri : (it.iconKey ? (EVENT_MOTIFS.find((m) => m.key === it.iconKey)?.icon || null) : null)
    return {
      id: it.id || `i${i}`,
      iso: p ? it.date : '', day: p ? String(p.d) : '', mon, wd,
      dateLabel: p ? `${wd[0]}${wd.slice(1).toLowerCase()} ${p.d} ${mon[0]}${mon.slice(1).toLowerCase()}` : '',
      title: it.title || '', time: it.time || '', venue: it.venue || '', price: it.price || '',
      visual: it.imageUrl ? { kind: 'image', src: it.imageUrl } : (iconSrc ? { kind: 'icon', src: iconSrc } : null),
    }
  })
  // The calendar shows the month of the earliest dated event.
  const dated = items.filter((it) => it.iso).sort((x, y) => (x.iso < y.iso ? -1 : 1))
  const first = dated.length ? parseIsoDate(dated[0].iso) : null
  const now = new Date()
  const year = first ? first.y : now.getFullYear()
  const month = first ? first.mo : now.getMonth()
  return { items, year, month, monthLabel: `${MONTHS[month]} ${year}` }
}

const pad2 = (n) => String(n).padStart(2, '0')
const plusDays = (days) => {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}
// What a new list starts with, so the layouts are never an empty page. Dates are
// relative to today so the calendar opens on a month that is about to happen.
export const defaultEventList = () => ({
  items: [
    { id: 'e1', date: plusDays(7), title: 'Working Bee', time: '9:00 AM', venue: 'The Clubhouse', price: 'Free', iconKey: 'star', iconUri: '', imageUrl: '' },
    { id: 'e2', date: plusDays(12), title: 'Quiz Night', time: '7:30 PM', venue: 'The Clubhouse', price: '$12', iconKey: 'target', iconUri: '', imageUrl: '' },
    { id: 'e3', date: plusDays(19), title: 'Season Launch', time: '11:00 AM', venue: 'Home Ground', price: 'Free', iconKey: 'calendar', iconUri: '', imageUrl: '' },
    { id: 'e4', date: plusDays(26), title: 'Presentation Night', time: '7:00 PM', venue: 'The Pavilion', price: '$55', iconKey: 'trophy', iconUri: '', imageUrl: '' },
  ],
})

// Light-surface directions want a paper/ink pair rather than dark mode. Merge
// these onto the active palette before handing it to a light template so the
// club accent still drives the colour but the surface reads as paper.
export function eventPaletteFor(surface, palette) {
  if (surface !== 'light') return palette
  return { ...palette, paper: palette.paper || '#f4efe4', deepInk: palette.deepInk || '#1f1c14' }
}

// MINIFICATION MANGLES `Component.name`, so a layer label derived from it
// reads as `R` or `ni` in a production build and as the real name in dev —
// which is exactly the kind of thing only a built bundle shows. An explicit
// displayName is a string literal, so it survives.
BSMark.displayName = 'BSMark'
PhotoLayer.displayName = 'PhotoLayer'
ClubLockup.displayName = 'ClubLockup'
Watermark.displayName = 'Watermark'

// Where this file's layouts keep the sponsor grid (see sponsorSlots.js). Each
// layout calls the same slot function above to leave that rectangle clear.
export const SPONSOR_SLOTS = {
  ...LIST_SLOTS,
  EV1: slotEV1,
  EV2: slotEV2,
  EV3: slotEV3,
  EV4: slotEV4,
  EV5: slotEV5,
  EV6: slotEV6,
  EV7: slotEV7,
  EV8: slotEV8,
  EV9: slotEV9,
  EV10: slotEV10,
  EV11: slotEV11,
}
