// The faces of a collectable card, drawn flat at one fixed size (CARD_W x CARD_H) like the share card, so
// they scale and export the same way.
//
//   CardFront     a regular card: the club's layout (name, photo, six career figures along the band) with
//                 the RARITY rating in the top corner and a frame that tells the tier at a glance.
//   SpecialFront  a card for one event (a century, a five-for, a 100th game), each kind with its own colour
//                 and pattern, frozen at the moment it commemorates.
//   CardBack      the face-down side, the club's colour with its badge.
//   CardView      picks the right front, and wraps a special card in the holo effect.
//   ScaledCard    CardView scaled to a width, so one card design serves a phone and a desktop.
//
// Missing figures read "-" (a bowler's batting average, a batter's wickets).
import { useRef, useState } from 'react'
import './cards.css'
import { CARD_W, CARD_H, hexWithAlpha, onColor, splitName, usePhotoMode } from '../PlayerTradingCard'
import { TIERS, specialLook, specialHeadline, fmtDate } from './cardTheme'

export { CARD_W, CARD_H }
const FRAME = 7
const PANEL_W = CARD_W - FRAME * 2
const PANEL_H = CARD_H - FRAME * 2
const BAND_H = 92
const MONO = "'JetBrains Mono', monospace"
const SANS = "'Inter', sans-serif"
const INK = '#050a0c'
export const DEFAULT_DISPLAY = "'Barlow Condensed', sans-serif"

const reducedMotion = () => typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

const num = (v) => (v == null ? '-' : Number(v).toLocaleString('en-AU'))
const rate = (v) => (v == null ? '-' : Number(v).toFixed(2))
const figureSize = (v) => { const n = String(v).length; return n <= 2 ? 27 : n === 3 ? 24 : n === 4 ? 21 : n === 5 ? 18 : 15 }

function initialsOf(name) {
  const { first, last } = splitName(name)
  return `${(first || '').charAt(0)}${(last || '').charAt(0)}`.toUpperCase() || '?'
}

// The player, or the club's badge when there is no photo, or their initials when there is no badge either.
function Portrait({ card, club, accent, dim }) {
  const photo = usePhotoMode(card.hero_photo_url, card.photo_url)
  const light = `color-mix(in srgb, ${accent} 55%, #fff)`
  if (photo.mode === 'hero') {
    return <img src={photo.src} alt="" onError={photo.fail} style={{ position: 'absolute', left: 0, top: 0, width: PANEL_W, height: PANEL_H - 40, objectFit: 'cover', objectPosition: '50% 18%', opacity: dim ? 0.92 : 1 }} />
  }
  const C = 176
  if (photo.mode === 'head') {
    return <img src={photo.src} alt="" onError={photo.fail} style={{ position: 'absolute', left: (PANEL_W - C) / 2, top: 96, width: C, height: C, borderRadius: '50%', objectFit: 'cover', objectPosition: '50% 22%', boxShadow: `0 0 0 5px ${light}, 0 14px 32px rgba(0,0,0,.55)` }} />
  }
  if (club?.logo_url) {
    return <img src={club.logo_url} alt="" style={{ position: 'absolute', left: (PANEL_W - 150) / 2, top: 104, width: 150, height: 150, objectFit: 'contain', filter: 'drop-shadow(0 6px 24px rgba(0,0,0,.5))' }} />
  }
  return (
    <div style={{ position: 'absolute', left: (PANEL_W - C) / 2, top: 96, width: C, height: C, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: `linear-gradient(145deg, ${accent}, color-mix(in srgb, ${accent} 45%, #000))`, color: onColor(accent), font: `800 italic 72px ${DEFAULT_DISPLAY}`, boxShadow: `0 0 0 5px ${light}, 0 14px 32px rgba(0,0,0,.55)` }}>
      {initialsOf(card.name)}
    </div>
  )
}

// The card's outer frame: the tier's border, then the panel inside it.
function TierFrame({ tier, panel, children, accent, foil }) {
  const t = TIERS[tier] || TIERS.common
  const glowing = t.foil || foil
  return (
    <div style={{ position: 'relative', width: CARD_W, height: CARD_H, borderRadius: 26, boxSizing: 'border-box', color: '#fff', fontFamily: SANS, boxShadow: `0 14px 34px rgba(0,0,0,.45)${glowing ? `, 0 0 26px ${hexWithAlpha(t.glow, 0.35)}` : ''}` }}>
      {/* The frame is its own layer so a foil one can cycle its colours without touching the card. */}
      <div className={glowing ? 'cc-foil' : undefined} style={{ position: 'absolute', inset: 0, borderRadius: 26, background: t.frame }} aria-hidden />
      <div style={{ position: 'absolute', inset: FRAME, borderRadius: 19, overflow: 'hidden', background: panel, boxShadow: `inset 0 0 0 1px ${hexWithAlpha(accent, 0.35)}` }}>
        {children}
        {(tier === 'rare' || tier === 'epic') && <div className="cc-sheen" aria-hidden />}
      </div>
    </div>
  )
}

function Band({ items, accent }) {
  const ink = onColor(accent)
  return (
    <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: BAND_H }}>
      <div style={{ position: 'absolute', inset: 0, background: `linear-gradient(180deg, ${accent}, color-mix(in srgb, ${accent} 78%, #000))`, clipPath: 'polygon(0 22%, 100% 0, 100% 100%, 0 100%)' }} />
      <div style={{ position: 'absolute', left: 8, right: 8, bottom: 12, display: 'flex' }}>
        {items.map((it, i) => (
          <div key={it.label} style={{ flex: 1, minWidth: 0, overflow: 'hidden', textAlign: 'center', color: ink, borderLeft: i ? `1px solid ${ink === '#fff' ? 'rgba(255,255,255,.35)' : 'rgba(5,10,12,.3)'}` : undefined }}>
            <div style={{ font: `800 ${figureSize(it.value)}px/1 ${it.display}`, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>{it.value}</div>
            <div style={{ height: 2, width: 22, background: ink, opacity: 0.8, margin: '5px auto 4px', borderRadius: 1 }} />
            <div style={{ font: `700 9px ${SANS}`, letterSpacing: 0.6, textTransform: 'uppercase', opacity: 0.85, whiteSpace: 'nowrap' }}>{it.label}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

// The other side of a card, turned over in the gallery: the same card, written out.
export function CardInfoBack({ card, club, accent, display = DEFAULT_DISPLAY }) {
  const t = TIERS[card.tier] || TIERS.common
  const d = card.detail || {}
  const rows = card.kind === 'special'
    ? [
        ['Event', card.title],
        ['Player', card.name],
        d.opposition && ['Against', d.opposition],
        card.occurred_on && ['Date', fmtDate(card.occurred_on)],
        d.runs != null && ['Runs', `${d.runs}${d.not_out ? '*' : ''}`],
        d.balls != null && ['Balls', d.balls],
        d.fours != null && ['Fours', d.fours],
        d.sixes != null && ['Sixes', d.sixes],
        d.wickets != null && ['Wickets', `${d.wickets} for ${d.runs}`],
        d.overs != null && ['Overs', Number(d.overs)],
        d.season && ['Season', d.season],
        d.grade && ['Grade', d.grade],
      ].filter(Boolean)
    : [
        ['Matches', num(card.matches)], ['Runs', num(card.runs)], ['Batting average', rate(card.bat_avg)],
        ['Wickets', num(card.wickets)], ['Bowling average', rate(card.bowl_avg)], ['Dismissals', num(card.dismissals)],
      ]
  return (
    <TierFrame tier={card.tier === 'special' ? 'special' : card.tier} accent={accent} foil={card.kind === 'special'} panel="linear-gradient(160deg, #101f33 0%, #0b1624 60%, #08111c 100%)">
      <div style={{ position: 'absolute', inset: 0, padding: '18px 18px 14px', display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ font: `800 italic 22px ${display}`, letterSpacing: 2, textTransform: 'uppercase' }}>{card.kind === 'special' ? 'Special card' : 'Card details'}</div>
          <span style={{ flex: 1 }} />
          {club?.logo_url && <img src={club.logo_url} alt="" style={{ width: 28, height: 28, objectFit: 'contain' }} />}
        </div>
        <div style={{ height: 2, background: `linear-gradient(90deg, ${accent}, transparent)`, margin: '8px 0 12px' }} />
        <div style={{ font: `800 26px/1.05 ${display}`, textTransform: 'uppercase' }}>{card.name}</div>
        {card.kind !== 'special' && <div style={{ font: `700 10px ${MONO}`, letterSpacing: 1.6, textTransform: 'uppercase', color: t.ink, margin: '5px 0 12px' }}>Rarity {card.rarity}  ·  {t.label}</div>}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: card.kind === 'special' ? 12 : 0 }}>
          {rows.map(([l, v]) => (
            <div key={l} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, padding: '6px 10px', borderRadius: 8, border: '1px solid rgba(255,255,255,.2)', background: 'rgba(5,10,12,.4)' }}>
              <span style={{ font: `600 9.5px ${SANS}`, letterSpacing: 0.8, textTransform: 'uppercase', color: 'rgba(255,255,255,.7)' }}>{l}</span>
              <span style={{ font: `700 13px ${MONO}`, textAlign: 'right', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v}</span>
            </div>
          ))}
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, font: `500 9px ${MONO}`, letterSpacing: 1.4, textTransform: 'uppercase', color: 'rgba(255,255,255,.55)' }}>
          <span>{card.copies > 1 ? `${card.copies} copies` : card.copies === 1 ? '1 copy' : ''}</span>
          <span>{card.obtained_at ? `Collected ${fmtDate(card.obtained_at.slice(0, 10))}` : card.mine ? 'Your own card' : ''}</span>
        </div>
      </div>
    </TierFrame>
  )
}

// A regular card.
export function CardFront({ card, club, accent, display = DEFAULT_DISPLAY, sponsor, label = 'Career Statistics' }) {
  const { first, last } = splitName(card.name)
  const size = last.length <= 7 ? 44 : last.length <= 10 ? 37 : last.length <= 13 ? 30 : 25
  const tier = TIERS[card.tier] || TIERS.common
  const hero = !!card.hero_photo_url
  const items = [
    { label: 'Matches', value: num(card.matches) },
    { label: 'Runs', value: num(card.runs) },
    { label: 'Bat avg', value: rate(card.bat_avg) },
    { label: 'Wickets', value: num(card.wickets) },
    { label: 'Bowl avg', value: rate(card.bowl_avg) },
    { label: 'Dism.', value: num(card.dismissals) },
  ].map((i) => ({ ...i, display }))
  return (
    <TierFrame tier={card.tier} accent={accent} panel={`linear-gradient(170deg, color-mix(in srgb, ${accent} 88%, #000) 0%, color-mix(in srgb, ${accent} 34%, ${INK}) 62%, ${INK} 100%)`}>
      <div style={{ position: 'absolute', top: 0, right: -20, width: 230, height: 300, background: hexWithAlpha('#ffffff', 0.1), clipPath: 'polygon(40% 0, 100% 0, 100% 100%, 0 70%)' }} />
      <div style={{ position: 'absolute', left: 0, top: 150, width: 170, height: 190, opacity: 0.22, background: 'radial-gradient(#fff 1.3px, transparent 1.6px) 0 0 / 9px 9px', clipPath: 'polygon(0 0, 100% 18%, 80% 100%, 0 100%)' }} />
      <Portrait card={card} club={club} accent={accent} />
      {hero && <div style={{ position: 'absolute', left: 0, right: 0, top: 0, height: 120, background: 'linear-gradient(to bottom, rgba(5,10,12,.7), rgba(5,10,12,0))' }} />}
      {hero && <div style={{ position: 'absolute', left: 0, right: 0, bottom: BAND_H - 30, height: 150, background: 'linear-gradient(to top, rgba(5,10,12,.85), rgba(5,10,12,0))' }} />}

      <div style={{ position: 'absolute', top: 14, left: 16, right: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
        <div style={{ minWidth: 0 }}>
          {first && <div style={{ font: `600 italic 14px ${SANS}`, textTransform: 'uppercase', letterSpacing: 1, color: '#fff', textShadow: '0 1px 8px rgba(0,0,0,.7)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{first}</div>}
          <div style={{ font: `800 italic ${size}px/0.95 ${display}`, textTransform: 'uppercase', letterSpacing: 0.5, color: '#fff', textShadow: '0 2px 12px rgba(0,0,0,.65)', whiteSpace: 'nowrap' }}>{last}</div>
        </div>
        <div style={{ flex: 'none', textAlign: 'right' }} data-card-rarity>
          <div style={{ font: `700 8.5px ${MONO}`, letterSpacing: 1.4, textTransform: 'uppercase', color: '#fff', opacity: 0.9, textShadow: '0 1px 6px rgba(0,0,0,.7)' }}>Rarity</div>
          <div style={{ font: `800 italic 42px/0.92 ${display}`, color: tier.ink, textShadow: '0 2px 12px rgba(0,0,0,.65)' }}>{card.rarity}</div>
          <div style={{ font: `700 8.5px ${MONO}`, letterSpacing: 1.4, textTransform: 'uppercase', color: tier.ink, marginTop: 2, textShadow: '0 1px 6px rgba(0,0,0,.7)' }}>{tier.label}</div>
        </div>
      </div>

      <div style={{ position: 'absolute', left: 14, right: 14, bottom: BAND_H + 6, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 7 }}>
        <div style={{ font: `600 8.5px ${MONO}`, letterSpacing: 1.6, textTransform: 'uppercase', color: '#fff', opacity: 0.85, textShadow: '0 1px 6px rgba(0,0,0,.7)', whiteSpace: 'nowrap' }}>{label}</div>
        {sponsor && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 10px 4px 12px', borderRadius: 10, background: 'rgba(5,10,12,.7)', border: '1px solid rgba(255,255,255,.14)' }}>
            <span style={{ font: `500 9.5px ${SANS}`, color: 'rgba(255,255,255,.75)' }}>Sponsored by</span>
            <img src={sponsor.logo_url} alt={sponsor.name || ''} style={{ maxWidth: 96, maxHeight: 24, objectFit: 'contain' }} />
          </div>
        )}
      </div>
      <Band items={items} accent={accent} />
    </TierFrame>
  )
}

// A special card: one event, its own colours.
export function SpecialFront({ card, club, accent, display = DEFAULT_DISPLAY }) {
  const look = specialLook(card, accent)
  const { first, last } = splitName(card.name)
  const head = specialHeadline(card)
  const d = card.detail || {}
  const bigSize = head.long
    ? (head.big.length > 26 ? 24 : head.big.length > 16 ? 30 : 38)
    : head.small ? 54 : (String(head.big).length <= 3 ? 104 : String(head.big).length <= 5 ? 84 : 66)
  const opp = d.opposition ? `v ${d.opposition}` : ''
  const when = fmtDate(card.occurred_on)
  const nameSize = last.length <= 8 ? 32 : last.length <= 11 ? 27 : 22
  return (
    <TierFrame tier="special" accent={accent} foil panel={look.panel}>
      <div style={{ position: 'absolute', inset: 0, background: look.pattern, opacity: 0.9 }} />
      <div style={{ position: 'absolute', left: 14, top: 14, display: 'flex', alignItems: 'center', gap: 7 }}>
        <span style={{ padding: '3px 9px', borderRadius: 999, background: 'rgba(5,10,12,.55)', border: '1px solid rgba(255,255,255,.4)', font: `700 9px ${MONO}`, letterSpacing: 1.6, textTransform: 'uppercase', color: '#fff' }}>Special</span>
        <span style={{ font: `700 9px ${MONO}`, letterSpacing: 1.6, textTransform: 'uppercase', color: look.on, opacity: 0.85 }}>{look.label}</span>
      </div>
      {club?.logo_url && <img src={club.logo_url} alt="" style={{ position: 'absolute', right: 14, top: 10, width: 34, height: 34, objectFit: 'contain', filter: 'drop-shadow(0 2px 6px rgba(0,0,0,.4))' }} />}

      {/* The player, in a cut-out window so the colour of the event still reads around them. */}
      <div style={{ position: 'absolute', left: 22, right: 22, top: 56, height: 214, borderRadius: 18, overflow: 'hidden', boxShadow: `0 0 0 3px ${hexWithAlpha('#ffffff', 0.55)}, 0 12px 30px rgba(0,0,0,.4)`, background: 'rgba(5,10,12,.35)' }}>
        <WindowPortrait card={card} club={club} accent={accent} />
        <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: 90, background: 'linear-gradient(to top, rgba(5,10,12,.78), rgba(5,10,12,0))' }} />
        <div style={{ position: 'absolute', left: 12, right: 12, bottom: 8 }}>
          {first && <div style={{ font: `600 italic 12px ${SANS}`, textTransform: 'uppercase', letterSpacing: 1, color: '#fff', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{first}</div>}
          <div style={{ font: `800 italic ${nameSize}px/0.95 ${display}`, textTransform: 'uppercase', color: '#fff', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{last}</div>
        </div>
      </div>

      <div style={{ position: 'absolute', left: 14, right: 14, top: 282, bottom: 14, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', color: look.on }}>
        <div data-special-headline style={{ font: `800 italic ${bigSize}px/0.92 ${display}`, color: look.accent, textShadow: '0 3px 14px rgba(0,0,0,.35)', maxWidth: '100%', overflow: 'hidden', textTransform: head.small ? 'uppercase' : undefined, wordBreak: head.long ? 'break-word' : undefined }}>{head.big}</div>
        {head.sub && <div style={{ font: `600 12px ${SANS}`, letterSpacing: 0.5, marginTop: 6, opacity: 0.9 }}>{head.sub}</div>}
        {(opp || when) && (
          <div style={{ marginTop: 8, padding: '4px 12px', borderRadius: 999, background: 'rgba(5,10,12,.5)', color: '#fff', font: `600 10px ${MONO}`, letterSpacing: 1, textTransform: 'uppercase', maxWidth: '100%', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {[opp, when].filter(Boolean).join('  ·  ')}
          </div>
        )}
      </div>
    </TierFrame>
  )
}

// The portrait inside a special card's window (a fixed box, so it does not use the full-panel layout).
function WindowPortrait({ card, club, accent }) {
  const photo = usePhotoMode(card.hero_photo_url, card.photo_url)
  if (photo.mode === 'none') {
    return club?.logo_url
      ? <img src={club.logo_url} alt="" style={{ position: 'absolute', inset: 0, margin: 'auto', width: 120, height: 120, objectFit: 'contain' }} />
      : <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: `linear-gradient(145deg, ${accent}, color-mix(in srgb, ${accent} 45%, #000))`, color: onColor(accent), font: `800 italic 84px ${DEFAULT_DISPLAY}` }}>{initialsOf(card.name)}</div>
  }
  return <img src={photo.src} alt="" onError={photo.fail} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', objectPosition: '50% 18%' }} />
}

// The face-down side.
export function CardBack({ club, accent, tier = 'common', display = DEFAULT_DISPLAY }) {
  const t = TIERS[tier] || TIERS.common
  return (
    <TierFrame tier={tier === 'common' ? 'common' : tier} accent={accent} panel={`radial-gradient(circle at 50% 38%, color-mix(in srgb, ${accent} 70%, #fff) 0%, ${accent} 30%, color-mix(in srgb, ${accent} 30%, ${INK}) 100%)`}>
      <div style={{ position: 'absolute', inset: 0, background: 'repeating-linear-gradient(45deg, rgba(255,255,255,.07) 0 2px, transparent 2px 16px)' }} />
      <div style={{ position: 'absolute', inset: 22, borderRadius: 14, border: '2px solid rgba(255,255,255,.35)' }} />
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 14, color: onColor(accent) }}>
        {club?.logo_url
          ? <img src={club.logo_url} alt="" style={{ width: 150, height: 150, objectFit: 'contain', filter: 'drop-shadow(0 8px 22px rgba(0,0,0,.45))' }} />
          : <div style={{ font: `800 italic 96px ${display}` }}>{initialsOf(club?.name || '')}</div>}
        <div style={{ font: `800 italic 22px ${display}`, letterSpacing: 4, textTransform: 'uppercase', textAlign: 'center' }}>{club?.short_name || club?.name}</div>
        <div style={{ font: `600 9px ${MONO}`, letterSpacing: 3, textTransform: 'uppercase', opacity: 0.8 }}>Player cards</div>
      </div>
      {tier !== 'common' && <div style={{ position: 'absolute', inset: 0, boxShadow: `inset 0 0 60px ${hexWithAlpha(t.glow, 0.5)}` }} />}
    </TierFrame>
  )
}

// The holographic effect on a special card. Tilts toward the pointer and slides a rainbow sheen and a
// glare with it; with no pointer (a card at rest, or a phone) the sheen drifts on its own. The layers are
// drawn over the card and never take a click.
export function HoloCard({ children, active = true }) {
  const ref = useRef(null)
  const [pos, setPos] = useState(null) // {x, y} 0..100 while the pointer is over the card
  const move = (e) => {
    if (!active || reducedMotion()) return
    const el = ref.current
    if (!el) return
    const r = el.getBoundingClientRect()
    const x = Math.min(100, Math.max(0, ((e.clientX - r.left) / r.width) * 100))
    const y = Math.min(100, Math.max(0, ((e.clientY - r.top) / r.height) * 100))
    setPos({ x, y })
  }
  const tilt = pos ? `rotateY(${(pos.x - 50) / 5}deg) rotateX(${-(pos.y - 50) / 6}deg)` : 'none'
  return (
    <div ref={ref} onPointerMove={move} onPointerLeave={() => setPos(null)} data-holo style={{ position: 'relative', width: CARD_W, height: CARD_H, perspective: 900 }}>
      <div style={{ position: 'relative', width: '100%', height: '100%', borderRadius: 26, transform: tilt, transition: pos ? 'transform .06s linear' : 'transform .5s ease', transformStyle: 'preserve-3d' }}>
        {children}
        <div className={`cc-holo ${pos ? '' : 'cc-holo-idle'}`} style={pos ? { backgroundPosition: `${pos.x}% ${pos.y}%` } : undefined} aria-hidden />
        <div className="cc-glare" style={{ background: `radial-gradient(circle at ${pos ? pos.x : 30}% ${pos ? pos.y : 25}%, rgba(255,255,255,.65), rgba(255,255,255,0) 46%)` }} aria-hidden />
        <div className="cc-grain" aria-hidden />
      </div>
    </div>
  )
}

// A card of either kind, flat at CARD_W x CARD_H.
export function CardView({ card, club, accent, display, sponsor, holo = true }) {
  if (card.kind === 'special') {
    const face = <SpecialFront card={card} club={club} accent={accent} display={display} />
    return holo ? <HoloCard>{face}</HoloCard> : face
  }
  return <CardFront card={card} club={club} accent={accent} display={display} sponsor={sponsor} />
}

// The card shrunk (or grown) to a width. Scale the wrapper, never the faces, so type stays crisp.
export function ScaledCard({ width, children, style, ...rest }) {
  const k = width / CARD_W
  return (
    <div style={{ width, height: CARD_H * k, position: 'relative', flex: 'none', ...style }} {...rest}>
      <div style={{ width: CARD_W, height: CARD_H, transform: `scale(${k})`, transformOrigin: 'top left' }}>{children}</div>
    </div>
  )
}
