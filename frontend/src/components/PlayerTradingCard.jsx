// The two faces of a player's share card, drawn flat at a fixed size (CARD_W x CARD_H). The front is the
// trading card: the photo full bleed over the club's colour, the sponsor, the name and the style chips. The back
// holds the figures. The share page turns one into the other with FlipCard and renders the same markup to a PNG.
import { useEffect, useState } from 'react'
import { fmt2, fmtCount } from '../lib/cricketFormat'
import { styleChips } from '../lib/playerAttributes'
import betterStatsLogo from '../assets/bettercricket-white.svg'

export const CARD_W = 360
export const CARD_H = 492
const MONO = "'JetBrains Mono', monospace"
const INK = '#050a0c'

export function hexWithAlpha(hex, alpha) {
  if (!hex || hex[0] !== '#' || hex.length !== 7) return `rgba(22,199,132,${alpha})`
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

const ordinal = (r) => (r % 100 >= 11 && r % 100 <= 13) ? `${r}th` : `${r}${({ 1: 'st', 2: 'nd', 3: 'rd' }[r % 10] || 'th')}`

// "George Pullinger" -> first "George", last "Pullinger"; a single word is all surname.
export function splitName(full) {
  const parts = String(full || '').trim().split(/\s+/).filter(Boolean)
  if (parts.length < 2) return { first: '', last: parts[0] || '' }
  return { first: parts.slice(0, -1).join(' '), last: parts[parts.length - 1] }
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

// The sponsor shown on a card: the club's top tier sponsor that has a logo.
export function cardSponsor(data) {
  const list = ((data && data.sponsors) || []).filter(s => s.logo_url)
  return list.find(s => s.tier === 'major') || list[0] || null
}

function Icon({ kind, color }) {
  const p = { width: 13, height: 13, viewBox: '0 0 24 24', fill: 'none', stroke: color, strokeWidth: 2.2, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true }
  if (kind === 'bat') return <svg {...p}><path d="M4 20l9-9" /><path d="M13 11l4.5-4.5a2.1 2.1 0 013 3L16 14z" /></svg>
  if (kind === 'bowl') return <svg {...p}><circle cx="12" cy="12" r="8.5" /><path d="M6.5 6.5c3 2 3 9 0 11M17.5 6.5c-3 2-3 9 0 11" /></svg>
  return <svg {...p}><circle cx="12" cy="12" r="8.5" /><path d="M8 12l3 3 5-6" /></svg>
}

function Chips({ player, accent }) {
  const chips = styleChips(player)
  if (!chips.length) return null
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, marginTop: 12 }}>
      {chips.map(c => (
        <span key={c.kind} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, font: "500 14px 'Inter', sans-serif", color: 'rgba(255,255,255,.92)' }}>
          <Icon kind={c.kind} color={accent} />{c.label}
        </span>
      ))}
    </div>
  )
}

function Face({ children, accent, side }) {
  return (
    <div style={{
      position: 'relative', width: CARD_W, height: CARD_H, borderRadius: 22, overflow: 'hidden', color: '#fff', fontFamily: "'Inter', sans-serif",
      background: side === 'front'
        ? `linear-gradient(165deg, color-mix(in srgb, ${accent} 42%, ${INK}) 0%, ${INK} 78%)`
        : `linear-gradient(150deg, #0d1b2a 0%, #0f2235 60%, #0d1b2a 100%)`,
      boxShadow: `0 14px 34px rgba(0,0,0,.45), inset 0 0 0 1px ${hexWithAlpha(accent, 0.3)}`,
    }}>{children}</div>
  )
}

export function PlayerCardFront({ player, org, accent, display, sponsor, rankings, photoUrl, seasonLabel }) {
  const [photoOk, setPhotoOk] = useState(!!photoUrl)
  useEffect(() => { setPhotoOk(!!photoUrl) }, [photoUrl])
  const { first, last } = splitName(player?.display_name || player?.name)
  const rank = bestRank(rankings)
  const size = last.length <= 8 ? 58 : last.length <= 11 ? 46 : 36
  const logo = org?.logo_url || betterStatsLogo
  return (
    <Face accent={accent} side="front">
      {/* A slash of the club colour behind the player, the way the club's own posts have one. */}
      <div style={{ position: 'absolute', top: -10, right: -30, width: 210, height: 330, background: hexWithAlpha(accent, 0.85), clipPath: 'polygon(38% 0, 100% 0, 100% 100%, 0 62%)', opacity: 0.9 }} />
      <div style={{ position: 'absolute', top: 40, right: 26, width: 70, height: 250, background: hexWithAlpha(accent, 0.35), clipPath: 'polygon(55% 0, 100% 0, 45% 100%, 0 100%)' }} />
      {photoOk
        ? <img src={photoUrl} alt="" onError={() => setPhotoOk(false)} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', objectPosition: '50% 18%' }} />
        : <img src={logo} alt="" style={{ position: 'absolute', left: '50%', top: 150, width: 190, height: 190, objectFit: 'contain', transform: 'translateX(-50%)', opacity: 0.9, filter: 'drop-shadow(0 6px 24px rgba(0,0,0,.5))' }} />}
      <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: '58%', background: `linear-gradient(to top, ${INK} 6%, rgba(5,10,12,.82) 42%, rgba(5,10,12,0) 100%)` }} />

      {sponsor && (
        <div style={{ position: 'absolute', top: 14, left: 14 }}>
          <div style={{ font: "500 11px 'Inter', sans-serif", color: 'rgba(255,255,255,.8)', textShadow: '0 1px 6px rgba(0,0,0,.6)' }}>Sponsored by:</div>
          <div style={{ marginTop: 4, display: 'flex', alignItems: 'center', justifyContent: 'center', width: 128, height: 40, borderRadius: 8, background: 'rgba(8,12,14,.72)', border: '1px solid rgba(255,255,255,.12)' }}>
            <img src={sponsor.logo_url} alt={sponsor.name || ''} style={{ maxWidth: 108, maxHeight: 26, objectFit: 'contain' }} />
          </div>
        </div>
      )}
      <div style={{ position: 'absolute', top: 14, right: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ font: `600 10px ${MONO}`, letterSpacing: 1, textTransform: 'uppercase', color: 'rgba(255,255,255,.85)', textShadow: '0 1px 6px rgba(0,0,0,.6)' }}>{seasonLabel}</span>
      </div>

      <div style={{ position: 'absolute', left: 22, right: 22, bottom: 22 }}>
        {first && <div style={{ font: "500 18px 'Inter', sans-serif", color: 'rgba(255,255,255,.92)', lineHeight: 1.1 }}>{first}</div>}
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 8 }}>
          <div style={{ minWidth: 0, font: `800 ${size}px/0.95 ${display}`, textTransform: 'uppercase', letterSpacing: 0.5, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{last}</div>
          {rank && (
            <div style={{ flex: 'none', textAlign: 'right', paddingBottom: 2 }}>
              <div style={{ font: `800 62px/0.85 ${display}`, fontStyle: 'italic', color: '#fff', textShadow: `0 2px 18px ${hexWithAlpha(accent, 0.7)}` }}>#{rank.rank}</div>
              <div style={{ font: `600 9px ${MONO}`, letterSpacing: 1.5, textTransform: 'uppercase', color: accent, marginTop: 4 }}>Club {rank.label}</div>
            </div>
          )}
        </div>
        <Chips player={player} accent={accent} />
      </div>
    </Face>
  )
}

function Stat({ label, value, highlight, accent, big }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ font: `700 ${highlight ? 26 : big ? 22 : 20}px/1 ${MONO}`, color: highlight ? accent : '#fff' }}>{value ?? '—'}</div>
      <div style={{ font: "500 9px 'Inter', sans-serif", color: '#64748b', textTransform: 'uppercase', letterSpacing: 1.5, marginTop: 5 }}>{label}</div>
    </div>
  )
}

function Block({ title, display, children, first }) {
  return (
    <div style={{ borderTop: first ? undefined : '1px solid rgba(30,41,59,.9)', paddingTop: first ? 0 : 12, marginTop: first ? 0 : 12 }}>
      <div style={{ font: `500 11px ${display}`, color: '#64748b', letterSpacing: 3, textTransform: 'uppercase', marginBottom: 9 }}>{title}</div>
      {children}
    </div>
  )
}

function Pill({ children, accent }) {
  return <span style={{ background: hexWithAlpha(accent, 0.1), border: `1px solid ${hexWithAlpha(accent, 0.3)}`, borderRadius: 6, padding: '3px 9px', font: "500 11px 'Inter', sans-serif", color: accent }}>{children}</span>
}

export function PlayerCardBack({ player, cb, cbw, cf, org, accent, display, rankings, photoUrl, seasonLabel }) {
  const [photoOk, setPhotoOk] = useState(!!photoUrl)
  useEffect(() => { setPhotoOk(!!photoUrl) }, [photoUrl])
  const fieldingHasData = cf && ((cf.total_catches_non_wk ?? cf.total_catches ?? 0) > 0 || (cf.total_catches_wk ?? 0) > 0 || (cf.total_run_outs ?? 0) > 0 || (cf.total_stumpings ?? 0) > 0)
  const hasBowling = cbw && cbw.total_wickets > 0
  const ranks = [['Runs', rankings?.runs_rank], ['Wickets', rankings?.wickets_rank], ['Catches', rankings?.catches_rank]].filter(([, r]) => Number.isInteger(r) && r >= 1)
  return (
    <Face accent={accent} side="back">
      <div style={{ padding: '20px 22px', height: '100%', boxSizing: 'border-box', display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {org?.logo_url && <img src={org.logo_url} alt="" style={{ width: 28, height: 28, objectFit: 'contain', borderRadius: 4, flex: 'none' }} />}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ font: `500 12px ${display}`, color: accent, letterSpacing: 2, textTransform: 'uppercase', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{org?.name}</div>
            <div style={{ font: "400 11px 'Inter', sans-serif", color: '#64748b', marginTop: 2 }}>{seasonLabel}</div>
          </div>
          {photoOk && <img src={photoUrl} alt="" onError={() => setPhotoOk(false)} style={{ width: 44, height: 44, objectFit: 'cover', borderRadius: 8, border: `2px solid ${hexWithAlpha(accent, 0.3)}`, flex: 'none' }} />}
        </div>
        <div style={{ font: `800 34px/1 ${display}`, textTransform: 'uppercase', letterSpacing: 1, margin: '14px 0 8px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{player?.display_name || player?.name}</div>
        {ranks.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 14 }}>
            {ranks.map(([l, r]) => <span key={l} style={{ background: hexWithAlpha(accent, 0.15), border: `1px solid ${hexWithAlpha(accent, 0.4)}`, borderRadius: 5, padding: '2px 8px', font: `500 10px ${MONO}`, letterSpacing: 0.5, color: accent }}>{ordinal(r)} {l.toLowerCase()}</span>)}
          </div>
        )}

        <div style={{ flex: 1, minHeight: 0 }}>
          {cb && (
            <Block title="Batting" display={display} first>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 6 }}>
                <Stat label="M" value={cb.games} accent={accent} />
                <Stat label="Inns" value={cb.innings} accent={accent} />
                <Stat label="Runs" value={cb.total_runs != null ? fmtCount(cb.total_runs) : null} highlight accent={accent} />
                <Stat label="HS" value={cb.high_score} accent={accent} />
                <Stat label="Ave" value={cb.average != null ? fmt2(cb.average) : null} accent={accent} />
              </div>
              {(cb.hundreds > 0 || cb.fifties > 0) && (
                <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                  {cb.hundreds > 0 && <Pill accent={accent}>{cb.hundreds} x {cb.hundreds === 1 ? '100' : '100s'}</Pill>}
                  {cb.fifties > 0 && <Pill accent={accent}>{cb.fifties} x {cb.fifties === 1 ? '50' : '50s'}</Pill>}
                </div>
              )}
            </Block>
          )}
          {hasBowling && (
            <Block title="Bowling" display={display} first={!cb}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
                <Stat label="Wkts" value={cbw.total_wickets != null ? fmtCount(cbw.total_wickets) : null} highlight accent={accent} />
                <Stat label="Ave" value={cbw.average != null ? fmt2(cbw.average) : null} accent={accent} />
                <Stat label="Econ" value={cbw.economy != null ? fmt2(cbw.economy) : null} accent={accent} />
                <Stat label="Best" value={cbw.best_bowling_figures || (cbw.best_figures_wickets ? `${fmtCount(cbw.best_figures_wickets)} wkts` : '—')} accent={accent} big />
              </div>
              {cbw.five_fors > 0 && <div style={{ marginTop: 10 }}><Pill accent={accent}>{cbw.five_fors} x {cbw.five_fors === 1 ? '5fa' : '5fas'}</Pill></div>}
            </Block>
          )}
          {fieldingHasData && (
            <Block title="Fielding" display={display} first={!cb && !hasBowling}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
                <Stat label="Ct" value={fmtCount(cf.total_catches_non_wk ?? cf.total_catches)} highlight accent={accent} />
                <Stat label="Ct (WK)" value={fmtCount(cf.total_catches_wk)} accent={accent} />
                <Stat label="RO" value={fmtCount(cf.total_run_outs)} accent={accent} />
                <Stat label="Stmps" value={fmtCount(cf.total_stumpings)} accent={accent} />
              </div>
            </Block>
          )}
          {!cb && !hasBowling && !fieldingHasData && <p style={{ font: "400 13px 'Inter', sans-serif", color: '#94a3b8' }}>No figures to show yet.</p>}
        </div>
        <div style={{ textAlign: 'right', font: `500 11px ${display}`, color: hexWithAlpha(accent, 0.4), letterSpacing: 2, textTransform: 'uppercase' }}>BetterCricket</div>
      </div>
    </Face>
  )
}
