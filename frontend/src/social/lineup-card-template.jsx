// Match Day Card (T12): the club's own photo under a colour wash, the XI on a
// solid panel with a role icon beside every name, the fixture on the right, the
// club logo centred over the list and a white sponsor bar along the foot. Two
// slashes of colour mark the top left and bottom right corners.
//
// Everything a club sets once is a prop (`card`): the background photo, the wash
// colour and strength, the corner colour, the list panel colour and the logo.
// The editor keeps those as the club's defaults, so a new lineup opens already
// looking like the club's.
//
// The logo can be any shape. The editor measures it and passes `logoRatio`
// (width over height); a 6:1 wordmark is as wide as the list allows, a square
// crest stands at the tallest the header allows, and everything between.
//
// The sponsor bar is as tall as the number of logos needs. One logo sits in a
// slim bar, five to eight take two rows. With none the bar is not drawn and the
// list takes the room. `lineupCardSponsorSlot` is the ONE answer for where the
// grid goes; the layout calls it so the bar and the grid cannot drift apart.
//
// Every part is a root child with a `data-layer` name, so each is a layer in
// the Layers panel and can be reordered or hidden.
import { useLayoutEffect, useRef, useState } from 'react'
import { AutoFitText, CreditMark, RoleChip, DebutTag } from './cricket-templates'
import { mixHex } from './split-template'
import { aspectOf, pick } from './postAspect'
import { LayerRoot } from './postLayers'

// The club's chosen display face and its weight (Style, Font in the editor), the
// same variables every other layout reads, so the card follows the brand.
const FONT = "var(--social-display-font, 'Hanken Grotesk', 'Inter', sans-serif)"
const WEIGHT = 'var(--social-display-font-weight, 700)'

function rgb(hex) {
  const h = String(hex || '').replace('#', '')
  if (h.length < 6) return [128, 128, 128]
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]
}
function isLight(hex) {
  const [r, g, b] = rgb(hex)
  return (0.299 * r + 0.587 * g + 0.114 * b) > 150
}

// What a club gets before it has picked anything.
export const LINEUP_CARD_DEFAULTS = { bgUrl: '', wash: '', washOpacity: 0.8, corner: '', panel: '', logoUrl: '', logoScale: 1 }

// The colours the card falls back to, from the club's accent.
export const cardWashDefault = (accent) => mixHex(accent || '#1d4ed8', '#050b18', 0.8)

const LIST_X = 96
const LIST_W = 486
const RAIL_W = 76
const EDGE = 56

// How tall the sponsor bar needs to be for this many logos (not counting the
// lift a story needs to clear the app's reply bar).
function sponsorBarH(count) {
  if (count <= 0) return 0
  if (count === 1) return 150
  if (count <= 4) return 175
  return 235
}

// Every measurement the layout and its sponsor slot share. All three post
// shapes are 1080 wide, so the question is only where the extra height goes.
function cardGeo(width, height, count) {
  const A = aspectOf(width, height)
  const barH = sponsorBarH(count)
  // A story's bottom couple of hundred pixels carry the app's reply bar: the
  // bar stays full-bleed to the edge and its logos sit above that.
  const lift = barH ? pick(A, { square: 0, portrait: 0, story: 140 }) : 0
  const barTotal = barH ? barH + lift : 0
  const logoTop = pick(A, { square: 64, portrait: 76, story: 150 })
  const logoMaxH = pick(A, { square: 116, portrait: 132, story: 176 })
  const top0 = logoTop + logoMaxH + pick(A, { square: 24, portrait: 30, story: 40 })
  const gapAbove = barH ? pick(A, { square: 36, portrait: 44, story: 56 }) : pick(A, { square: 56, portrait: 64, story: 220 })
  const avail = height - barTotal - gapAbove - top0
  const rowH = Math.min(pick(A, { square: 60, portrait: 76, story: 88 }), avail / 11)
  const listH = rowH * 11
  // Rows stop growing before the room runs out, so the list is centred in what
  // is left rather than hanging from the logo.
  const listTop = top0 + Math.max(0, (avail - listH) / 2)
  return { A, barH, lift, barTotal, logoTop, logoMaxH, top0, rowH, listH, listTop }
}

// The sponsor grid sits inside the white bar, clear of the two corner slashes.
export function lineupCardSponsorSlot(width = 1080, height = 1080, count = 1) {
  const g = cardGeo(width, height, Math.max(1, count))
  const padY = 14
  return {
    x: 180, w: width - 360,
    y: height - g.barTotal + padY, h: g.barH - padY * 2,
    pad: 6, gap: 20, panel: 'light', layoutBacked: true,
  }
}

// ── Role icons ───────────────────────────────────────────────────────────────
// A bat, a ball, a bat with a ball, a bat with stumps: batter, bowler,
// all-rounder, wicketkeeper. Drawn here so they export crisply at any size.
const BatShape = ({ transform }) => (
  <g transform={transform}>
    <rect x="17.8" y="1.5" width="4.4" height="12.5" rx="2" fill="#5b3a21" />
    <path d="M14.5 13.5h11l1 3v18.5a3 3 0 0 1-3 3h-7a3 3 0 0 1-3-3V16.5z" fill="#e8b46a" stroke="#b9823f" strokeWidth="1" />
    <line x1="20" y1="17" x2="20" y2="35" stroke="#c99650" strokeWidth="1" />
  </g>
)
const BallShape = ({ cx, cy, r }) => {
  const k = r / 11
  return (
    <g transform={`translate(${cx - 20 * k} ${cy - 20 * k}) scale(${k})`}>
      <circle cx="20" cy="20" r="11" fill="#c8202f" />
      <path d="M12.5 12.5c4 3.5 4 11.5 0 15M27.5 12.5c-4 3.5-4 11.5 0 15" stroke="#f5d9d9" strokeWidth="1" fill="none" strokeDasharray="1.6 1.6" />
      <circle cx="16" cy="15.5" r="3" fill="#ffffff" opacity="0.2" />
    </g>
  )
}

export function RoleIcon({ kind, size = 40 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" style={{ display: 'block', flexShrink: 0 }}>
      {kind === 'BOWL' && <BallShape cx={20} cy={20} r={12} />}
      {kind === 'BAT' && <BatShape transform="rotate(38 20 20)" />}
      {kind === 'AR' && <>
        <BatShape transform="translate(-3 -1) rotate(38 20 20) scale(0.9)" />
        <BallShape cx={29} cy={29.5} r={7.5} />
      </>}
      {kind === 'WK' && <>
        <BatShape transform="translate(-6 -1) rotate(38 20 20) scale(0.9)" />
        <g fill="#d9a45f" stroke="#a8742f" strokeWidth="0.5">
          <rect x="26" y="15" width="2.2" height="22" rx="0.6" />
          <rect x="29.4" y="15" width="2.2" height="22" rx="0.6" />
          <rect x="32.8" y="15" width="2.2" height="22" rx="0.6" />
          <rect x="26.5" y="13.2" width="3" height="1.6" rx="0.5" />
          <rect x="31.5" y="13.2" width="3" height="1.6" rx="0.5" />
        </g>
      </>}
    </svg>
  )
}
RoleIcon.displayName = 'RoleIcon'

// A keeper's icon wins over their batting or bowling role.
export const roleIconKind = (p) => (p.keeper || p.role === 'WK' ? 'WK' : p.role === 'AR' ? 'AR' : p.role === 'BOWL' ? 'BOWL' : 'BAT')

// The slash in a corner: a long wedge and a lighter stripe running parallel to it.
// The bottom right is the same drawing turned half way round.
// A plain function, not a component: a root child must be the element itself so
// the Layers panel reads its `data-layer`.
function cornerSvg(layer, c1, c2, style) {
  return (
    <svg data-layer={layer} width="190" height="130" viewBox="0 0 190 130" style={{ position: 'absolute', ...style }}>
      <polygon points="0,0 96,0 0,120" fill={c1} />
      <polygon points="116,0 184,0 128,70 60,70" fill={c2} />
    </svg>
  )
}

// One type size for the whole list: the largest at which the widest name still
// fits its row. Faces differ a lot in width (Teko against Archivo Black), so it
// is measured in the DOM rather than guessed, and measured again when a web font
// finishes loading. A per-row fit would shrink one long surname on its own and
// read as a mistake beside ten that did not.
function useSharedNameSize(listRef, cap) {
  const [size, setSize] = useState(cap)
  // Changes when the face changes or a web font finishes loading, so text fitted
  // by AutoFitText (which only re-fits on its own props) can be told to re-fit.
  const [fontSig, setFontSig] = useState('')
  const loads = useRef(0)
  useLayoutEffect(() => {
    const list = listRef.current
    if (!list) return undefined
    let cancelled = false
    const fit = () => {
      if (cancelled) return
      const els = [...list.querySelectorAll('[data-name]')]
      if (!els.length) return
      let best = cap
      els.forEach((el) => {
        const prev = el.style.fontSize
        el.style.fontSize = `${cap}px`
        const room = (el.parentElement ? el.parentElement.clientWidth : 0) - 8
        const need = el.offsetWidth
        el.style.fontSize = prev
        if (need > room && need > 0) best = Math.min(best, (cap * room) / need)
      })
      const next = Math.max(12, Math.floor(best))
      setSize((cur) => (cur === next ? cur : next))
      const sig = `${getComputedStyle(list).fontFamily}|${loads.current}`
      setFontSig((cur) => (cur === sig ? cur : sig))
    }
    fit()
    const fonts = typeof document !== 'undefined' ? document.fonts : null
    if (fonts && fonts.ready) fonts.ready.then(fit)
    const onLoaded = () => { loads.current += 1; fit() }
    if (fonts && fonts.addEventListener) fonts.addEventListener('loadingdone', onLoaded)
    return () => { cancelled = true; if (fonts && fonts.removeEventListener) fonts.removeEventListener('loadingdone', onLoaded) }
  })
  return { size: Math.min(size, cap), fontSig }
}

export function LineupCard({
  width = 1080, height = 1080, team = {}, opponent = {}, match = {}, players, palette = {},
  card, sponsorCount = 1, sponsorPanel = 'light', logoRatio = 1, headline = '',
}) {
  const P = (players || []).slice(0, 11)
  const c = { ...LINEUP_CARD_DEFAULTS, ...(card || {}) }
  const accent = palette.accent || '#1d4ed8'
  const panel = c.panel || accent
  const corner = c.corner || accent
  const cornerLight = mixHex(corner, '#ffffff', 0.38)
  const wash = c.wash || cardWashDefault(accent)
  const washOpacity = Math.max(0, Math.min(1, Number(c.washOpacity)))
  const g = cardGeo(width, height, sponsorCount)
  const { A, rowH } = g

  // Text is white unless the wash is both pale and heavy enough to need dark type.
  const photoOnly = !c.bgUrl
  const pale = isLight(wash) && (photoOnly || washOpacity > 0.5)
  const ink = pale ? '#0b0b0c' : '#ffffff'
  const panelInk = isLight(panel) ? '#0b0b0c' : '#ffffff'
  const rail = mixHex(panel, panelInk === '#ffffff' ? '#ffffff' : '#000000', 0.14)
  const line = panelInk === '#ffffff' ? 'rgba(255,255,255,0.26)' : 'rgba(0,0,0,0.22)'
  const chipBg = panelInk === '#ffffff' ? '#ffffff' : '#0b0b0c'
  const chipInk = panelInk === '#ffffff' ? '#0b0b0c' : '#ffffff'
  const listRef = useRef(null)
  const nameCap = Math.round(rowH * 0.62)
  const { size: nameSize, fontSig } = useSharedNameSize(listRef, nameCap)
  // Fixed by the cap, not the fitted size: the size is measured from the room this
  // column leaves, so a column that moved with it would chase its own tail.
  const numW = Math.round(nameCap * 1.7)
  const iconSize = Math.round(Math.min(rowH * 0.78, 52))

  // The logo: as wide as the list allows or as tall as the header allows,
  // whichever the logo's own shape reaches first.
  const logoSrc = c.logoUrl || team.logo
  const ratio = Number(logoRatio) > 0 ? Number(logoRatio) : 1
  const scale = Math.max(0.4, Math.min(1.4, Number(c.logoScale) || 1))
  const logoW = Math.min((LIST_W + 40) * scale, g.logoMaxH * scale * ratio)
  const logoH = logoW / ratio

  // The Backing choice in the Sponsors tool colours the whole bar, not a box in it.
  const barBg = sponsorPanel === 'dark' ? 'rgba(8,10,14,0.9)' : sponsorPanel === 'none' ? 'transparent' : '#ffffff'
  const barLight = barBg === '#ffffff'
  const detailsX = LIST_X + LIST_W + 48
  const detailsW = width - EDGE - detailsX
  const fixture = pick(A, { square: 58, portrait: 64, story: 70 })
  const small = pick(A, { square: 40, portrait: 44, story: 48 })
  const compText = (match.competition && match.competition !== 'COMPETITION' ? match.competition : '').toUpperCase()

  return (
    <LayerRoot style={{
      width, height, position: 'relative', overflow: 'hidden',
      background: c.bgUrl ? '#0b1220' : wash, color: ink, fontFamily: FONT, fontWeight: WEIGHT,
    }}>
      {c.bgUrl && (
        <div data-layer="Background photo" style={{ position: 'absolute', left: 0, top: 0, width, height }}>
          <img src={c.bgUrl} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
        </div>
      )}
      <div data-layer="Colour wash" style={{
        position: 'absolute', left: 0, top: 0, width, height,
        background: c.bgUrl ? wash : `linear-gradient(160deg, ${mixHex(wash, '#ffffff', 0.12)} 0%, ${wash} 55%, ${mixHex(wash, '#000000', 0.25)} 100%)`,
        opacity: c.bgUrl ? washOpacity : 1,
      }} />

      {g.barH > 0 && sponsorPanel !== 'none' && (
        <div data-layer="Sponsor bar" style={{ position: 'absolute', left: 0, top: height - g.barTotal, width, height: g.barTotal, background: barBg }} />
      )}

      {cornerSvg('Corner top left', corner, cornerLight, { left: 0, top: 0 })}
      {cornerSvg('Corner bottom right', corner, cornerLight, { right: 0, bottom: 0, transform: 'rotate(180deg)' })}

      {logoSrc && (
        <div data-layer="Club logo" style={{
          position: 'absolute', left: LIST_X + LIST_W / 2 - logoW / 2, top: g.logoTop + g.logoMaxH / 2 - logoH / 2,
          width: logoW, height: logoH,
        }}>
          <img src={logoSrc} alt={team.short || team.name || 'club'} style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }} />
        </div>
      )}

      <div data-layer="Starting XI" ref={listRef} style={{
        position: 'absolute', left: LIST_X, top: g.listTop, width: LIST_W, height: g.listH,
        background: panel, color: panelInk, boxShadow: '0 10px 30px rgba(0,0,0,0.28)', overflow: 'hidden',
      }}>
        <div style={{ position: 'absolute', right: 0, top: 0, bottom: 0, width: RAIL_W, background: rail }} />
        {P.map((p, i) => {
          const kind = roleIconKind(p)
          return (
            <div key={i} style={{
              position: 'absolute', left: 0, right: 0, top: i * rowH, height: rowH, display: 'flex', alignItems: 'center',
              boxSizing: 'border-box', borderBottom: i < P.length - 1 ? `1px solid ${line}` : 'none',
            }}>
              <div style={{
                width: numW, flexShrink: 0, textAlign: 'right', paddingRight: 12, boxSizing: 'border-box',
                fontSize: nameSize, lineHeight: 1, opacity: 0.92,
              }}>{i + 1}.</div>
              <div style={{ flex: 1, minWidth: 0, overflow: 'hidden' }}>
                <span data-name="" style={{ display: 'inline-block', whiteSpace: 'nowrap', fontSize: nameSize, letterSpacing: 0.3, lineHeight: 1.1, color: panelInk }}>
                  {`${p.first || ''} ${p.last || ''}`.trim()}
                </span>
              </div>
              <div style={{ display: 'flex', gap: 5, flexShrink: 0, alignItems: 'center', paddingRight: 8 }}>
                {p.captain && <RoleChip kind="C" accent={chipBg} ink={chipInk} />}
                {p.viceCaptain && <RoleChip kind="VC" accent={chipBg} ink={chipInk} />}
                {p.debut && <DebutTag accent={chipBg} ink={chipInk} />}
              </div>
              <div style={{ width: RAIL_W, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <RoleIcon kind={kind} size={iconSize} />
              </div>
            </div>
          )
        })}
      </div>

      <div data-layer="Match details" style={{
        position: 'absolute', left: detailsX, top: g.listTop, width: detailsW, textAlign: 'center', color: ink,
        textShadow: pale ? 'none' : '0 3px 16px rgba(0,0,0,0.45)',
      }}>
        {compText && (
          <AutoFitText text={compText} max={Math.round(small * 0.7)} min={12} lines={1}
            measureDeps={[fontSig]} style={{ letterSpacing: 2, lineHeight: 1.2, opacity: 0.85, marginBottom: 14 }} />
        )}
        {(headline || '').trim() && (
          <AutoFitText text={headline.trim().toUpperCase()} max={Math.round(small * 0.8)} min={12} lines={1}
            measureDeps={[fontSig]} style={{ letterSpacing: 1.5, lineHeight: 1.2, marginBottom: 10 }} />
        )}
        <AutoFitText text={(team.name || '').toUpperCase()} max={fixture} min={18} lines={1}
          measureDeps={[fontSig]} style={{ letterSpacing: 0.5, lineHeight: 1.15 }} />
        <div style={{ fontSize: Math.round(small * 0.85), lineHeight: 1.5, letterSpacing: 1 }}>VS</div>
        <AutoFitText text={(opponent.name || '').toUpperCase()} max={fixture} min={18} lines={1}
          measureDeps={[fontSig]} style={{ letterSpacing: 0.5, lineHeight: 1.15 }} />
        <div style={{ marginTop: 34 }}>
          <AutoFitText text={(match.date || '').toUpperCase()} max={small} min={14} lines={1}
            measureDeps={[fontSig]} style={{ letterSpacing: 0.4, lineHeight: 1.3 }} />
          <AutoFitText text={(match.time || '').toUpperCase()} max={small} min={14} lines={1}
            measureDeps={[fontSig]} style={{ letterSpacing: 0.4, lineHeight: 1.3 }} />
          <AutoFitText text={(match.venue || '').toUpperCase()} max={small} min={14} lines={2}
            measureDeps={[fontSig]} style={{ letterSpacing: 0.4, lineHeight: 1.3 }} />
        </div>
      </div>

      {g.barH > 0 && (
        <div data-layer="Platform credit" style={{ position: 'absolute', left: 36, top: height - g.lift - 16 - 52, height: 52, display: 'flex', alignItems: 'center' }}>
          <CreditMark ink={barLight ? '#0b0b0c' : '#ffffff'} h={52} />
        </div>
      )}
    </LayerRoot>
  )
}
LineupCard.displayName = 'LineupCard'

// Where this file's layouts keep the sponsor grid (see sponsorSlots.js).
export const SPONSOR_SLOTS = { T12: lineupCardSponsorSlot }
