// The two faces of a player's share card, drawn flat at a fixed size (CARD_W x CARD_H). The front is the
// trading card: a black frame round a panel in the club's colour, the name and best club ranking up top, the
// photo, the sponsor and style chips, and a band of headline figures along the bottom. A hero (action) photo
// fills the panel; a headshot sits smaller, in the middle. The back is the player details sheet. The share page
// turns one into the other with FlipCard and renders the same markup to a PNG.
import { useEffect, useState } from 'react'
import { fmt2, fmtCount } from '../lib/cricketFormat'
import { styleChips } from '../lib/playerAttributes'
import { splitDisplayName } from '../lib/nameFormat'
import betterStatsLogo from '../assets/bettercricket-white.svg'

export const CARD_W = 360
export const CARD_H = 492
const FRAME = 7
const MONO = "'JetBrains Mono', monospace"
const SANS = "'Inter', sans-serif"
const INK = '#050a0c'

export function hexWithAlpha(hex, alpha) {
  if (!hex || hex[0] !== '#' || hex.length !== 7) return `rgba(22,199,132,${alpha})`
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

// Dark ink on a light club colour, white on a dark one, so the stat band stays readable whatever the club picked.
export function onColor(hex) {
  if (!hex || hex[0] !== '#' || hex.length !== 7) return '#fff'
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16))
  return (0.299 * r + 0.587 * g + 0.114 * b) > 150 ? INK : '#fff'
}

const ordinal = (r) => (r % 100 >= 11 && r % 100 <= 13) ? `${r}th` : `${r}${({ 1: 'st', 2: 'nd', 3: 'rd' }[r % 10] || 'th')}`

// Stored names are "Last, First"; a free-text override can be "First Last". A single word is all surname.
export function splitName(full) {
  const { first, last } = splitDisplayName(full)
  return last ? { first, last } : { first: '', last: first }
}

// The player's best club ranking, the big number on the front. None when they are not ranked in the top 99.
export function bestRank(rankings) {
  const all = [
    { rank: rankings?.runs_rank, label: 'Runs' },
    { rank: rankings?.wickets_rank, label: 'Wickets' },
    { rank: rankings?.catches_rank, label: 'Catches' },
  ].filter(r => Number.isInteger(r.rank) && r.rank >= 1 && r.rank <= 99)
  return all.sort((a, b) => a.rank - b.rank)[0] || null
}

// Sponsor choice values for a single share: '' follows the club's pick, NO_SPONSOR leaves the sponsor off.
export const NO_SPONSOR = 'none'

// The sponsors a card can show: the ones with a logo (the public list returns every sponsor).
export function cardSponsorOptions(data) {
  return ((data && data.sponsors) || []).filter(s => s.logo_url)
}

// The sponsor shown on a card. `surface` is 'share_card' or 'player_cards'. A `choice` made while sharing wins,
// then the sponsor the club picked for that surface, then the club's top tier sponsor that has a logo.
export function cardSponsor(data, surface, choice) {
  const list = cardSponsorOptions(data)
  if (choice === NO_SPONSOR) return null
  const byId = (id) => (id ? list.find(s => s.id === id) : null)
  return byId(choice) || byId(data?.card_sponsors?.[surface]) || list.find(s => s.tier === 'major') || list[0] || null
}

// Hero photo first, then the headshot, then nothing (the club logo stands in). A photo that fails to load drops a step.
export function usePhotoMode(heroUrl, photoUrl) {
  const [heroOk, setHeroOk] = useState(!!heroUrl)
  const [photoOk, setPhotoOk] = useState(!!photoUrl)
  useEffect(() => { setHeroOk(!!heroUrl) }, [heroUrl])
  useEffect(() => { setPhotoOk(!!photoUrl) }, [photoUrl])
  if (heroUrl && heroOk) return { mode: 'hero', src: heroUrl, fail: () => setHeroOk(false) }
  if (photoUrl && photoOk) return { mode: 'head', src: photoUrl, fail: () => setPhotoOk(false) }
  return { mode: 'none', src: null, fail: () => {} }
}

function Icon({ kind, color }) {
  const p = { width: 12, height: 12, viewBox: '0 0 24 24', fill: 'none', stroke: color, strokeWidth: 2.4, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true }
  if (kind === 'bat') return <svg {...p}><path d="M4 20l9-9" /><path d="M13 11l4.5-4.5a2.1 2.1 0 013 3L16 14z" /></svg>
  if (kind === 'bowl') return <svg {...p}><circle cx="12" cy="12" r="8.5" /><path d="M6.5 6.5c3 2 3 9 0 11M17.5 6.5c-3 2-3 9 0 11" /></svg>
  return <svg {...p}><circle cx="12" cy="12" r="8.5" /><path d="M8 12l3 3 5-6" /></svg>
}

function Chips({ player, light }) {
  const chips = styleChips(player)
  if (!chips.length) return null
  return (
    <div style={{ display: 'flex', flexWrap: 'nowrap', justifyContent: 'center', gap: 6, width: '100%' }}>
      {chips.map(c => (
        <span key={c.kind} style={{ whiteSpace: 'nowrap', flex: 'none', display: 'inline-flex', alignItems: 'center', gap: 5, padding: '4px 10px', borderRadius: 999, background: 'rgba(5,10,12,.62)', border: '1px solid rgba(255,255,255,.22)', font: `600 11px ${SANS}`, color: '#fff' }}>
          <Icon kind={c.kind} color={light} />{c.label}
        </span>
      ))}
    </div>
  )
}

// The black frame every face sits in, with the club-coloured (front) or navy (back) panel inside it.
function Frame({ children, accent, panel }) {
  return (
    <div style={{ position: 'relative', width: CARD_W, height: CARD_H, borderRadius: 26, padding: FRAME, boxSizing: 'border-box', background: INK, color: '#fff', fontFamily: SANS, boxShadow: '0 14px 34px rgba(0,0,0,.45)' }}>
      <div style={{ position: 'relative', width: '100%', height: '100%', borderRadius: 19, overflow: 'hidden', background: panel, boxShadow: `inset 0 0 0 1px ${hexWithAlpha(accent, 0.35)}` }}>{children}</div>
    </div>
  )
}

const PANEL_W = CARD_W - FRAME * 2
const PANEL_H = CARD_H - FRAME * 2
const BAND_H = 92

// Longer figures get smaller type so six of them always fit along the band, in the club's font or a fallback.
const figureSize = (v) => { const n = String(v).length; return n <= 2 ? 27 : n === 3 ? 24 : n === 4 ? 21 : n === 5 ? 18 : 15 }

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
            <div style={{ font: `700 9px ${SANS}`, letterSpacing: 0.6, textTransform: 'uppercase', opacity: 0.85 }}>{it.label}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

// Up to six headline figures: the ones this player has.
function bandItems({ cb, cbw, cf }, display) {
  const catches = cf ? (cf.total_catches_non_wk ?? cf.total_catches ?? 0) + (cf.total_catches_wk ?? 0) : 0
  return [
    cb?.games != null && { label: 'Matches', value: String(cb.games) },
    cb?.total_runs != null && { label: 'Runs', value: fmtCount(cb.total_runs) },
    cb?.high_score != null && { label: 'HS', value: String(cb.high_score) },
    cb?.average != null && { label: 'Average', value: fmt2(cb.average) },
    cbw?.total_wickets > 0 && { label: 'Wickets', value: fmtCount(cbw.total_wickets) },
    catches > 0 && { label: 'Catches', value: fmtCount(catches) },
  ].filter(Boolean).slice(0, 6).map(i => ({ ...i, display }))
}

export function PlayerCardFront({ player, org, accent, display, sponsor, rankings, photoUrl, heroUrl, seasonLabel, cb, cbw, cf }) {
  const photo = usePhotoMode(heroUrl, photoUrl)
  const { first, last } = splitName(player?.display_name || player?.name)
  const rank = bestRank(rankings)
  const size = last.length <= 7 ? 44 : last.length <= 10 ? 37 : last.length <= 13 ? 30 : 25
  const light = `color-mix(in srgb, ${accent} 55%, #fff)`
  const items = bandItems({ cb, cbw, cf }, display)
  const hero = photo.mode === 'hero'
  const CIRCLE = 176
  return (
    <Frame accent={accent} panel={`linear-gradient(170deg, color-mix(in srgb, ${accent} 88%, #000) 0%, color-mix(in srgb, ${accent} 34%, ${INK}) 62%, ${INK} 100%)`}>
      {/* The club colour as a slash and a patch of halftone behind the player. */}
      <div style={{ position: 'absolute', top: 0, right: -20, width: 230, height: 300, background: hexWithAlpha('#ffffff', 0.1), clipPath: 'polygon(40% 0, 100% 0, 100% 100%, 0 70%)' }} />
      <div style={{ position: 'absolute', left: 0, top: 150, width: 170, height: 190, opacity: 0.22, background: 'radial-gradient(#fff 1.3px, transparent 1.6px) 0 0 / 9px 9px', clipPath: 'polygon(0 0, 100% 18%, 80% 100%, 0 100%)' }} />

      {hero && <img src={photo.src} alt="" onError={photo.fail} style={{ position: 'absolute', left: 0, top: 0, width: PANEL_W, height: PANEL_H - 40, objectFit: 'cover', objectPosition: '50% 18%' }} />}
      {photo.mode === 'head' && (
        <img src={photo.src} alt="" onError={photo.fail} style={{ position: 'absolute', left: (PANEL_W - CIRCLE) / 2, top: 96, width: CIRCLE, height: CIRCLE, borderRadius: '50%', objectFit: 'cover', objectPosition: '50% 22%', boxShadow: `0 0 0 5px ${light}, 0 14px 32px rgba(0,0,0,.55)` }} />
      )}
      {photo.mode === 'none' && (
        <img src={org?.logo_url || betterStatsLogo} alt="" style={{ position: 'absolute', left: (PANEL_W - 150) / 2, top: 104, width: 150, height: 150, objectFit: 'contain', filter: 'drop-shadow(0 6px 24px rgba(0,0,0,.5))' }} />
      )}
      {hero && <div style={{ position: 'absolute', left: 0, right: 0, top: 0, height: 120, background: 'linear-gradient(to bottom, rgba(5,10,12,.7), rgba(5,10,12,0))' }} />}
      {hero && <div style={{ position: 'absolute', left: 0, right: 0, bottom: BAND_H - 30, height: 150, background: 'linear-gradient(to top, rgba(5,10,12,.85), rgba(5,10,12,0))' }} />}

      {/* Name and best ranking */}
      <div style={{ position: 'absolute', top: 14, left: 16, right: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
        <div style={{ minWidth: 0 }}>
          {first && <div style={{ font: `600 italic 14px ${SANS}`, textTransform: 'uppercase', letterSpacing: 1, color: '#fff', textShadow: '0 1px 8px rgba(0,0,0,.7)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{first}</div>}
          <div style={{ font: `800 italic ${size}px/0.95 ${display}`, textTransform: 'uppercase', letterSpacing: 0.5, color: '#fff', textShadow: '0 2px 12px rgba(0,0,0,.65)', whiteSpace: 'nowrap' }}>{last}</div>
        </div>
        {rank && (
          <div style={{ flex: 'none', textAlign: 'right' }}>
            <div style={{ font: `800 italic 40px/0.9 ${display}`, color: '#fff', textShadow: '0 2px 12px rgba(0,0,0,.65)' }}>#{rank.rank}</div>
            <div style={{ font: `700 8.5px ${MONO}`, letterSpacing: 1.2, textTransform: 'uppercase', color: '#fff', opacity: 0.9, marginTop: 3, textShadow: '0 1px 6px rgba(0,0,0,.7)' }}>Club {rank.label}</div>
          </div>
        )}
      </div>

      {/* Style chips and the sponsor, above the band */}
      <div style={{ position: 'absolute', left: 14, right: 14, bottom: BAND_H + 6, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 7 }}>
        <div style={{ font: `600 8.5px ${MONO}`, letterSpacing: 1.6, textTransform: 'uppercase', color: '#fff', opacity: 0.85, textShadow: '0 1px 6px rgba(0,0,0,.7)', whiteSpace: 'nowrap' }}>{seasonLabel}</div>
        <Chips player={player} light={light} />
        {sponsor && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 10px 4px 12px', borderRadius: 10, background: 'rgba(5,10,12,.7)', border: '1px solid rgba(255,255,255,.14)' }}>
            <span style={{ font: `500 9.5px ${SANS}`, color: 'rgba(255,255,255,.75)' }}>Sponsored by</span>
            <img src={sponsor.logo_url} alt={sponsor.name || ''} style={{ maxWidth: 96, maxHeight: 24, objectFit: 'contain' }} />
          </div>
        )}
      </div>

      {items.length > 0 ? <Band items={items} accent={accent} /> : null}
    </Frame>
  )
}

// A pill-outlined row of the details sheet: a muted label on the left, the figure on the right.
function Row({ label, value, accent, strong }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6, height: 24, padding: '0 9px', borderRadius: 8, border: `1px solid ${strong ? hexWithAlpha(accent, 0.7) : 'rgba(255,255,255,.28)'}`, background: strong ? hexWithAlpha(accent, 0.16) : 'rgba(5,10,12,.35)' }}>
      <span style={{ font: `600 9px ${SANS}`, letterSpacing: 0.8, textTransform: 'uppercase', color: 'rgba(255,255,255,.7)', whiteSpace: 'nowrap' }}>{label}</span>
      <span style={{ font: `700 13px ${MONO}`, color: strong ? '#fff' : 'rgba(255,255,255,.95)', whiteSpace: 'nowrap' }}>{value ?? '-'}</span>
    </div>
  )
}

function Section({ title, rows, accent, display }) {
  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <span style={{ font: `700 11px ${display}`, letterSpacing: 2.5, textTransform: 'uppercase', color: accent }}>{title}</span>
        <span style={{ flex: 1, height: 1, background: hexWithAlpha(accent, 0.35) }} />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 5 }}>
        {rows.map(r => <Row key={r.label} {...r} accent={accent} />)}
      </div>
    </div>
  )
}

export function PlayerCardBack({ player, org, accent, display, rankings, photoUrl, heroUrl, seasonLabel, cb, cbw, cf }) {
  const photo = usePhotoMode(heroUrl, photoUrl)
  const { first, last } = splitName(player?.display_name || player?.name)
  const hasBowling = cbw && cbw.total_wickets > 0
  const catches = cf ? (cf.total_catches_non_wk ?? cf.total_catches ?? 0) : 0
  const fieldingHasData = cf && (catches > 0 || (cf.total_catches_wk ?? 0) > 0 || (cf.total_run_outs ?? 0) > 0 || (cf.total_stumpings ?? 0) > 0)
  const ranks = [['Runs', rankings?.runs_rank], ['Wickets', rankings?.wickets_rank], ['Catches', rankings?.catches_rank]].filter(([, r]) => Number.isInteger(r) && r >= 1)
  const batting = cb && [
    { label: 'Matches', value: cb.games }, { label: 'Innings', value: cb.innings },
    { label: 'Runs', value: cb.total_runs != null ? fmtCount(cb.total_runs) : null, strong: true }, { label: 'High score', value: cb.high_score },
    { label: 'Average', value: cb.average != null ? fmt2(cb.average) : null }, { label: '100s / 50s', value: `${cb.hundreds ?? 0} / ${cb.fifties ?? 0}` },
  ]
  const bowling = hasBowling && [
    { label: 'Wickets', value: fmtCount(cbw.total_wickets), strong: true }, { label: 'Average', value: cbw.average != null ? fmt2(cbw.average) : null },
    { label: 'Economy', value: cbw.economy != null ? fmt2(cbw.economy) : null }, { label: 'Best', value: cbw.best_bowling_figures || (cbw.best_figures_wickets ? `${fmtCount(cbw.best_figures_wickets)} wkts` : null) },
    { label: '5 wickets', value: fmtCount(cbw.five_fors ?? 0) },
  ]
  const fielding = fieldingHasData && [
    { label: 'Catches', value: fmtCount(catches), strong: true }, { label: 'Keeper ct', value: fmtCount(cf.total_catches_wk ?? 0) },
    { label: 'Run outs', value: fmtCount(cf.total_run_outs ?? 0) }, { label: 'Stumpings', value: fmtCount(cf.total_stumpings ?? 0) },
  ]
  return (
    <Frame accent={accent} panel="linear-gradient(160deg, #101f33 0%, #0b1624 60%, #08111c 100%)">
      {photo.src && <img src={photo.src} alt="" onError={photo.fail} style={{ position: 'absolute', right: 0, top: 30, width: '66%', height: '74%', objectFit: 'cover', objectPosition: '50% 20%', opacity: 0.2 }} />}
      <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(90deg, rgba(8,17,28,.55) 0%, rgba(8,17,28,.2) 100%)' }} />
      <div style={{ position: 'relative', height: '100%', boxSizing: 'border-box', padding: '14px 16px 10px', display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ font: `800 italic 20px ${display}`, letterSpacing: 2, textTransform: 'uppercase', whiteSpace: 'nowrap' }}>Player details</div>
          <span style={{ flex: 1 }} />
          {org?.logo_url && <img src={org.logo_url} alt="" style={{ width: 26, height: 26, objectFit: 'contain', borderRadius: 4 }} />}
        </div>
        <div style={{ height: 2, background: `linear-gradient(90deg, ${accent}, transparent)`, margin: '7px 0 10px' }} />

        <div style={{ width: '100%', boxSizing: 'border-box', padding: '6px 12px', borderRadius: 8, border: `1px solid ${hexWithAlpha(accent, 0.7)}`, background: 'rgba(5,10,12,.55)' }}>
          {first && <div style={{ font: `500 italic 11px ${SANS}`, letterSpacing: 1.2, textTransform: 'uppercase', color: 'rgba(255,255,255,.85)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{first}</div>}
          <div style={{ font: `800 24px/1.05 ${display}`, textTransform: 'uppercase', letterSpacing: 0.5, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{last}</div>
          <div style={{ font: `500 9px ${MONO}`, letterSpacing: 1, textTransform: 'uppercase', color: 'rgba(255,255,255,.6)', marginTop: 3, whiteSpace: 'nowrap' }}>{seasonLabel}</div>
        </div>
        {ranks.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 8 }}>
            {ranks.map(([l, r]) => <span key={l} style={{ background: hexWithAlpha(accent, 0.18), border: `1px solid ${hexWithAlpha(accent, 0.5)}`, borderRadius: 5, padding: '1px 7px', font: `600 9.5px ${MONO}`, color: '#fff' }}>{ordinal(r)} {l.toLowerCase()}</span>)}
          </div>
        )}

        <div style={{ flex: 1, minHeight: 0 }}>
          {batting && <Section title="Batting" rows={batting} accent={accent} display={display} />}
          {bowling && <Section title="Bowling" rows={bowling} accent={accent} display={display} />}
          {fielding && <Section title="Fielding" rows={fielding} accent={accent} display={display} />}
          {!batting && !bowling && !fielding && <p style={{ font: `400 13px ${SANS}`, color: '#94a3b8', marginTop: 14 }}>No figures to show yet.</p>}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, font: `500 9px ${display}`, letterSpacing: 1.8, textTransform: 'uppercase', color: 'rgba(255,255,255,.5)' }}>
          <span style={{ minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{org?.name}</span>
          <span style={{ minWidth: 0, flex: '0 1 auto', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: hexWithAlpha(accent, 0.8) }}>BetterCricket</span>
        </div>
      </div>
    </Frame>
  )
}
