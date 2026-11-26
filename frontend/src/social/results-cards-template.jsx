// Match Cards (RR8): the weekend's results as one card per match, drawn over the
// club's own photo (Background, Upload in the editor).
//
// Each card tells the match as it stands: a kicker (our team, the grade, the
// round), the story as one headline (matchStory.js: "CROWS WIN BY 95 RUNS",
// "JANDAKOT PARK NEED 220 TO WIN"), each innings with its crest, score and
// overs in the order they were batted, and our best batter and bowler. So it
// reads the same for a two-day game at the end of day one as for a finished
// one-dayer. The card's left edge and its tag carry the state: win, loss, in
// play, or no winner.
//
// The root fill is the palette's primary at the club's veil, so their photo
// shows through it; the cards are the same colour, more solid. No texture of its
// own: the photo is the texture.
//
// `cardsGeo` is the one answer for where the header, the cards, the crest and
// the sponsor slot are; `rr8SponsorSlot` reads it, so the room the layout keeps
// and the place the editor puts the grid cannot drift apart. The slot widens
// with the logo count, anchored to the right edge.
import { useLayoutEffect, useRef, useState } from 'react'
import { aspectOf, pick, grow } from './postAspect'
import { LayerRoot } from './postLayers'
import { pc, pt, pcAlpha, inkOn, registerParts, colorPart, textPart, alphaPart, picked as partPicked } from './layoutParts'
import { perfKeys } from './round-templates'
import { matchStory } from './matchStory'

const FONT = "var(--social-display-font, 'Anton', sans-serif)"
const WEIGHT = 'var(--social-display-font-weight, 400)'
const BODY = "'Inter', sans-serif"

// The same fixed meanings as the other results layouts, independent of the palette.
const WIN = '#2fd07a'
const LOSS = '#ff5d6c'
const LIVE = '#f5b942'
const NONE = '#9aa0b4'

// '#rrggbb' from a palette colour that may carry the editor's veil ('#rrggbb99').
const solid = (hex, fallback = '#0b1f33') => (/^#[0-9a-fA-F]{6}/.test(hex || '') ? hex.slice(0, 7) : fallback)

const SLOT_W = [0, 220, 400, 560]

export function cardsGeo(width = 1080, height = 1080, n = 3) {
  const A = aspectOf(width, height)
  const side = 56
  // A story's top carries the profile row and its bottom the reply bar.
  const top = pick(A, { square: 44, portrait: 60, story: 200 })
  const bottom = pick(A, { square: 40, portrait: 52, story: 250 })
  const kickerF = pick(A, { square: 22, portrait: 24, story: 26 })
  const titleF = pick(A, { square: 120, portrait: 136, story: 150 })
  const dateF = pick(A, { square: 34, portrait: 38, story: 42 })
  const headH = top + Math.round(kickerF * 1.3) + Math.round(titleF * 0.9) + Math.round(dateF * 1.25)
  const footH = grow(height, 130, 0.04)
  const footTop = height - bottom - footH
  const bodyTop = headH + pick(A, { square: 22, portrait: 30, story: 40 })
  const bodyBottom = footTop - pick(A, { square: 26, portrait: 34, story: 40 })
  // Past a handful of matches the cards go two across, so each keeps the height a
  // headline and two innings need.
  const cols = n > pick(A, { square: 4, portrait: 5, story: 7 }) ? 2 : 1
  const rows = Math.max(1, Math.ceil(Math.max(1, n) / cols))
  const gap = pick(A, { square: 18, portrait: 22, story: 24 })
  const cardH = Math.floor((bodyBottom - bodyTop - gap * (rows - 1)) / rows)
  const cardW = Math.floor((width - side * 2 - gap * (cols - 1)) / cols)
  return { A, side, top, kickerF, titleF, dateF, headH, footTop, footH, bodyTop, bodyBottom, cols, rows, gap, cardH, cardW }
}

export function rr8SponsorSlot(width = 1080, height = 1080, count = 1) {
  const g = cardsGeo(width, height)
  const labelH = 34
  const w = SLOT_W[Math.max(1, Math.min(3, count))]
  return { x: width - g.side - w, y: g.footTop + labelH, w, h: g.footH - labelH, pad: 8, gap: 14, panel: 'light' }
}

// One headline size for every card, the largest at which the widest fits, so a
// long chase line is not set smaller than its neighbours on its own. Measured
// again when a web font finishes loading.
function useSharedFit(listRef, cap) {
  const [size, setSize] = useState(cap)
  useLayoutEffect(() => {
    const list = listRef.current
    if (!list) return undefined
    let cancelled = false
    const fit = () => {
      if (cancelled) return
      const els = [...list.querySelectorAll('[data-fit]')]
      let best = cap
      els.forEach((el) => {
        const prev = el.style.fontSize
        el.style.fontSize = `${cap}px`
        const room = el.parentElement ? el.parentElement.clientWidth : 0
        const need = el.scrollWidth
        el.style.fontSize = prev
        if (room > 0 && need > room) best = Math.min(best, (cap * room) / need)
      })
      const next = Math.max(14, Math.floor(best))
      setSize((cur) => (cur === next ? cur : next))
    }
    fit()
    const fonts = typeof document !== 'undefined' ? document.fonts : null
    if (fonts && fonts.ready) fonts.ready.then(fit)
    if (fonts && fonts.addEventListener) fonts.addEventListener('loadingdone', fit)
    return () => { cancelled = true; if (fonts && fonts.removeEventListener) fonts.removeEventListener('loadingdone', fit) }
  })
  return Math.min(size, cap)
}

function Crest({ logo, mono, size, ink }) {
  if (logo) return <img src={logo} alt={mono || 'crest'} style={{ width: size, height: size, objectFit: 'contain', flexShrink: 0, display: 'block' }} />
  return (
    <div style={{
      width: size, height: size, borderRadius: '50%', flexShrink: 0, display: 'grid', placeItems: 'center',
      background: `${ink}1f`, border: `1px solid ${ink}40`, color: ink,
      fontFamily: FONT, fontWeight: WEIGHT, fontSize: Math.round(size * 0.42), lineHeight: 1,
    }}>{mono || '?'}</div>
  )
}

const monoOf = (name) => String(name || '').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase()

export function ResultsCards({
  palette: pal, width = 1080, height = 1080, meta = {}, results = [], club = {}, perfSide = 'us', sponsorCount = 0, parts,
}) {
  const rows = results
  const g = cardsGeo(width, height, rows.length)
  const listRef = useRef(null)
  const ink = solid(pal.ink, '#ffffff')
  const accent = solid(pal.accent, '#8fd3ff')
  const base = solid(pal.primary)
  const cardFill = pcAlpha(parts, 'cardBg', 'cardAlpha', `${base}d9`)
  // A wash over the photo so the heading reads on any picture. A panel, not a
  // texture, so it stays when the club turns texture off; its strength is theirs.
  const washC = pc(parts, 'rr8WashColor', base)
  // Like every alpha part, the strength counts only once the colour is picked.
  const washA = partPicked(parts, 'rr8WashColor') && typeof parts.rr8WashAlpha === 'number' && Number.isFinite(parts.rr8WashAlpha)
    ? Math.max(0, Math.min(1, parts.rr8WashAlpha)) : 0.55
  const hexA = (a) => Math.round(Math.max(0, Math.min(1, a)) * 255).toString(16).padStart(2, '0')
  const tones = {
    win: pc(parts, 'winColor', WIN),
    loss: pc(parts, 'lossColor', LOSS),
    live: pc(parts, 'liveColor', LIVE),
    none: pc(parts, 'rr8NoneColor', NONE),
  }

  // Every card's sizes come from what its tallest card must hold, so three
  // matches get big cards and nine still fit. At scale 1 a card holding a kicker,
  // a headline, two innings and a performers line needs `need` pixels; the scale
  // is what fits that into the real card height (and, two across, its width).
  const lines = Math.max(1, ...rows.map((r) => {
    const inns = [r.us, r.them].filter((v) => /\d/.test(String(v ?? ''))).length
    return inns
  }))
  const perfAny = rows.some((r) => ['topBat', 'topBowl', 'oppTopBat', 'oppTopBowl', 'leadBat', 'leadBowl'].some((k) => (r[k] || []).some((p) => p && (p.name || p.line))))
  const need = 2 * 24 + 21 + 61 + lines * 38 + (perfAny ? 24 : 0) + (2 + lines + (perfAny ? 1 : 0)) * 8
  const s = Math.max(0.45, Math.min(1.25, g.cardH / need, (g.cardW / 968) * 1.6))
  const f = (n) => Math.round(n * s)
  const pad = f(24)
  const kickF = f(19)
  const headCap = f(54)
  const lineF = f(28)
  const crest = f(36)
  const perfF = f(21)
  const tagF = f(18)
  const gapY = f(8)
  const headF = useSharedFit(listRef, headCap)

  const keys = rows.some((r) => r && r.neutral) ? { bat: 'leadBat', bowl: 'leadBowl' } : perfKeys(perfSide)
  const usName = String(club.name || 'US').toUpperCase()
  const usHead = pt(parts, 'rr8UsName', '')
  const noWinner = pt(parts, 'rr8NoWinner', 'NO WINNER')

  return (
    <LayerRoot style={{
      width, height, position: 'relative', overflow: 'hidden',
      background: pal.primary, color: ink, fontFamily: BODY,
    }}>
      {washA > 0 ? (
        <div data-layer="Photo wash" style={{
          position: 'absolute', inset: 0, pointerEvents: 'none',
          background: `linear-gradient(180deg, ${washC}${hexA(washA + 0.2)} 0%, ${washC}${hexA(washA)} 38%, ${washC}${hexA(washA)} 70%, ${washC}${hexA(washA + 0.15)} 100%)`,
        }} />
      ) : null}
      <div data-layer="Heading" style={{ position: 'absolute', left: g.side, right: g.side, top: g.top }}>
        <div style={{ fontFamily: FONT, fontWeight: WEIGHT, fontSize: g.kickerF, letterSpacing: 6, lineHeight: 1.3, color: pc(parts, 'rr8KickerColor', accent) }}>{pt(parts, 'rr8Kicker', 'WEEKEND RESULTS')}</div>
        <div style={{ fontFamily: FONT, fontWeight: WEIGHT, fontSize: g.titleF, letterSpacing: 1, lineHeight: 0.9, color: pc(parts, 'rr8TitleColor', ink), whiteSpace: 'nowrap' }}>{pt(parts, 'title1', 'RESULTS')}</div>
        <div style={{ fontFamily: FONT, fontWeight: WEIGHT, fontSize: g.dateF, letterSpacing: 2, lineHeight: 1.25, color: pc(parts, 'roundColor', ink), opacity: 0.9 }}>{meta.date || ''}</div>
      </div>

      <div data-layer="Match cards" ref={listRef} style={{
        position: 'absolute', left: g.side, right: g.side, top: g.bodyTop, height: g.bodyBottom - g.bodyTop,
        display: 'grid', gridTemplateColumns: `repeat(${g.cols}, minmax(0, 1fr))`, gridAutoRows: g.cardH, gap: g.gap, alignContent: 'start',
      }}>
        {rows.map((r, i) => {
          const neutral = !!r.neutral
          const us = neutral ? String(r.home || r.grade || '').toUpperCase() : (usHead || r.teamLabel || usName)
          const them = String(r.opp || 'OPPOSITION').toUpperCase()
          const story = matchStory(r, { us, them, noWinner })
          const edge = tones[story.tone]
          const round = r.round || meta.round || ''
          const kicker = (neutral ? [r.grade !== r.home ? r.grade : '', round] : [r.teamLabel, r.grade, round])
            .filter((v, k, a) => v && a.indexOf(v) === k).join('  ·  ')
          const sideName = { us: neutral ? us : usName, them }
          const sideLogo = { us: neutral ? r.homeLogo : club.logo, them: r.oppLogo }
          const sideMono = { us: neutral ? (r.homeMono || monoOf(us)) : (club.mono || monoOf(usName)), them: r.oppMono || monoOf(them) }
          const bat = ((r[keys.bat] || []).find((p) => p && (p.name || p.line)))
          const bowl = ((r[keys.bowl] || []).find((p) => p && (p.name || p.line)))
          const perf = [bat, bowl].filter(Boolean)
          const tagWord = story.tag === 'WIN' ? pt(parts, 'rr8WinWord', 'WIN')
            : story.tag === 'LOSS' ? pt(parts, 'rr8LossWord', 'LOSS')
              : story.tag === 'LIVE' ? pt(parts, 'rr8LiveWord', 'LIVE') : ''
          return (
            <div key={i} data-card={story.tone} style={{
              position: 'relative', minWidth: 0, minHeight: 0, overflow: 'hidden', boxSizing: 'border-box',
              background: cardFill, borderLeft: `${Math.max(4, f(7))}px solid ${edge}`, borderRadius: f(8),
              padding: `${pad}px ${pad}px`, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: gapY,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: f(12), minWidth: 0, flexShrink: 0 }}>
                <div style={{ flex: '1 1 auto', minWidth: 0, fontFamily: FONT, fontWeight: WEIGHT, fontSize: kickF, letterSpacing: 3, lineHeight: 1.1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: pc(parts, 'rr8CardKicker', accent) }}>{kicker}</div>
                {tagWord ? (
                  <span data-tag={story.tone} style={{
                    flexShrink: 0, fontFamily: FONT, fontWeight: WEIGHT, fontSize: tagF, letterSpacing: 2, lineHeight: 1,
                    padding: `${f(6)}px ${f(14)}px`, borderRadius: 999, background: edge, color: pc(parts, 'badgeColor', inkOn(edge)),
                  }}>{tagWord}</span>
                ) : null}
              </div>
              <div style={{ minWidth: 0, overflow: 'hidden', flexShrink: 0 }}>
                <div data-fit data-headline style={{ display: 'block', width: 'max-content', whiteSpace: 'nowrap', fontFamily: FONT, fontWeight: WEIGHT, fontSize: headF, letterSpacing: 0.5, lineHeight: 1.12, color: pc(parts, 'rr8HeadlineColor', ink) }}>{story.headline}</div>
              </div>
              {story.innings.map((inn) => (
                <div key={inn.side} data-innings={inn.side} style={{ display: 'flex', alignItems: 'center', gap: f(12), minWidth: 0, flexShrink: 0 }}>
                  <Crest logo={sideLogo[inn.side]} mono={sideMono[inn.side]} size={crest} ink={ink} />
                  <span style={{ flex: '1 1 auto', minWidth: 0, fontFamily: FONT, fontWeight: WEIGHT, fontSize: lineF, letterSpacing: 1, lineHeight: 1.1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: pc(parts, 'rr8NameColor', ink) }}>{sideName[inn.side]}</span>
                  <span style={{ flexShrink: 0, fontFamily: FONT, fontWeight: WEIGHT, fontSize: lineF, letterSpacing: 1, lineHeight: 1.1, whiteSpace: 'nowrap', color: pc(parts, 'rr8ScoreColor', ink) }}>
                    {inn.score}{inn.overs ? ` (${inn.overs})` : ''}
                  </span>
                </div>
              ))}
              {perf.length ? (
                <div data-perf style={{ minWidth: 0, flexShrink: 0, fontFamily: FONT, fontWeight: WEIGHT, fontSize: perfF, letterSpacing: 1.5, lineHeight: 1.15, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: pc(parts, 'rr8PerfColor', accent) }}>
                  {perf.map((p) => [p.name, p.line].filter(Boolean).join(' ')).join('   ·   ')}
                </div>
              ) : null}
            </div>
          )
        })}
      </div>

      <div data-layer="Club crest" style={{ position: 'absolute', left: g.side, top: g.footTop, height: g.footH, width: Math.round(width * 0.36), display: 'flex', alignItems: 'flex-end' }}>
        {club.logo
          ? <img src={club.logo} alt={club.name || 'club crest'} style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain', display: 'block' }} />
          : <div style={{ fontFamily: FONT, fontWeight: WEIGHT, fontSize: Math.round(g.footH * 0.36), lineHeight: 1, letterSpacing: 1, textTransform: 'uppercase', color: ink }}>{club.full || club.name || ''}</div>}
      </div>

      {sponsorCount > 0 ? (
        <div data-layer="Sponsor label" style={{
          position: 'absolute', right: g.side, top: g.footTop, height: 34, display: 'flex', alignItems: 'center',
          fontFamily: FONT, fontWeight: WEIGHT, fontSize: 20, letterSpacing: 4, color: pc(parts, 'rr8SponsorLabelColor', accent), whiteSpace: 'nowrap',
        }}>{pt(parts, 'rr8SponsorLabel', 'PROUDLY SPONSORED BY')}</div>
      ) : null}
    </LayerRoot>
  )
}
ResultsCards.displayName = 'ResultsCards'

const HEAD = 'Heading', CARDS = 'Match cards', WL = 'Wins and losses', FOOT = 'Footer'
registerParts({
  RR8: [
    textPart('rr8Kicker', 'Line above the title', HEAD, () => 'WEEKEND RESULTS'),
    colorPart('rr8KickerColor', 'Line above the title colour', HEAD, (p) => p.accent),
    textPart('title1', 'Title word', HEAD, () => 'RESULTS'),
    colorPart('rr8TitleColor', 'Title word colour', HEAD, (p) => p.ink),
    colorPart('roundColor', 'Date line', HEAD, (p) => p.ink),
    colorPart('rr8WashColor', 'Wash over the photo', HEAD, (p) => p.primary),
    alphaPart('rr8WashAlpha', 'Wash strength', HEAD, 'rr8WashColor'),
    colorPart('cardBg', 'Card fill', CARDS, (p) => p.primary),
    alphaPart('cardAlpha', 'Card fill strength', CARDS, 'cardBg'),
    colorPart('rr8CardKicker', 'Team, grade and round line', CARDS, (p) => p.accent),
    colorPart('rr8HeadlineColor', 'Headline', CARDS, (p) => p.ink),
    textPart('rr8UsName', 'Our side in headlines', CARDS, () => '', { autoLabel: 'Team name' }),
    textPart('rr8NoWinner', 'Headline when nobody won', CARDS, () => 'NO WINNER'),
    colorPart('rr8NameColor', 'Team names', CARDS, (p) => p.ink),
    colorPart('rr8ScoreColor', 'Scores', CARDS, (p) => p.ink),
    colorPart('rr8PerfColor', 'Top performers line', CARDS, (p) => p.accent),
    colorPart('winColor', 'Win colour', WL, () => WIN),
    colorPart('lossColor', 'Loss colour', WL, () => LOSS),
    colorPart('liveColor', 'In play colour', WL, () => LIVE),
    colorPart('rr8NoneColor', 'No winner colour', WL, () => NONE),
    colorPart('badgeColor', 'Text on the tags', WL, null, { autoLabel: 'Whichever reads' }),
    textPart('rr8WinWord', 'Win tag word', WL, () => 'WIN'),
    textPart('rr8LossWord', 'Loss tag word', WL, () => 'LOSS'),
    textPart('rr8LiveWord', 'In play tag word', WL, () => 'LIVE'),
    textPart('rr8SponsorLabel', 'Sponsor heading', FOOT, () => 'PROUDLY SPONSORED BY'),
    colorPart('rr8SponsorLabelColor', 'Sponsor heading colour', FOOT, (p) => p.accent),
  ],
})

export const SPONSOR_SLOTS = { RR8: rr8SponsorSlot }
