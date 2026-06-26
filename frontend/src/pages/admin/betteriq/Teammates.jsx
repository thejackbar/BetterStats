/* BetterIQ — Teammates: who a player has played alongside, and how they go
   together. Pick a player, see every teammate ranked by games together, then
   click one for the with-vs-without split — the Compare tool pointed at a
   context (a partner in the side) rather than a second player. All career.
   Deep-links via ?player=<id>&with=<id>. */
import { useState, useEffect, useRef } from 'react'
import Dropdown from '../../../components/Dropdown'
import { useSearchParams } from 'react-router-dom'
import IQLayout from '../../../components/admin/IQLayout'
import { api } from '../../../lib/api'
import {
  Card, Note, Empty, PageIntro, Search, Initials, surname,
  LoadingCard, a2, fmtCount, fmtPct, runsPhrase, wktsPhrase,
} from './ui'

const ACCENT = 'var(--pb-accent)'
const GREEN = 'var(--pb-brand)'
const pctTxt = (v) => fmtPct(v)
const dash = (v) => (v === null || v === undefined ? '—' : v)

/* ── Full-roster player picker (career history, from /iq/players) ─────────── */
function PlayerSearch({ players, onPick, placeholder = 'Search a player…' }) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const t = q.trim().toLowerCase()
  const matches = (t ? players.filter(p => (p.name || '').toLowerCase().includes(t)) : players).slice(0, 30)
  return (
    <div ref={ref} className="relative" onFocusCapture={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}>
      <Search value={q} onChange={(v) => { setQ(v); setOpen(true) }} placeholder={placeholder} className="w-full" />
      <Dropdown anchorRef={ref} open={open} onClose={() => setOpen(false)} maxHeight={320}
        className="iq-card p-1.5 iq-scroll" style={{ boxShadow: 'var(--iq-card-shadow)' }}>
        {matches.length === 0 ? (
          <div className="px-2.5 py-2 text-pb-faint text-sm">{players.length === 0 ? 'No players found.' : 'No match.'}</div>
        ) : matches.map(p => (
          <button key={p.player_id} type="button" onClick={() => { onPick(p.player_id); setQ(''); setOpen(false) }}
            className="w-full flex flex-col gap-0.5 px-2.5 py-2 text-left transition overflow-hidden" style={{ borderRadius: 8 }}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--pb-surface2)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}>
            <span className="font-medium text-[13.5px] truncate w-full">{p.name}</span>
            <span className="iq-mono text-pb-faintest text-[11px] truncate w-full">
              {fmtCount(p.matches)} {p.matches === 1 ? 'game' : 'games'}{p.runs ? ` · ${runsPhrase(p.runs, p.bat_avg)}` : ''}{p.wickets ? ` · ${wktsPhrase(p.wickets, p.bowl_avg)}` : ''}
            </span>
          </button>
        ))}
      </Dropdown>
    </div>
  )
}

/* ── One teammate row in the list (click → load split) ───────────────────── */
function TeammateRow({ m, active, onClick }) {
  const sub = [m.role, m.bowling_style].filter(Boolean).join(' · ')
  return (
    <button type="button" onClick={onClick}
      className="w-full flex items-center gap-3 px-2.5 py-2 text-left transition" style={{
        borderRadius: 10,
        background: active ? 'color-mix(in srgb, var(--pb-accent) 12%, transparent)' : 'transparent',
        border: `1px solid ${active ? 'color-mix(in srgb, var(--pb-accent) 35%, transparent)' : 'transparent'}`,
      }}
      onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--pb-surface2)' }}
      onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent' }}>
      <Initials name={m.name} size={32} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="font-semibold text-[13.5px] truncate">{m.name}</span>
          <span className="iq-num font-bold text-[13.5px] whitespace-nowrap">{fmtCount(m.games)}<span className="text-pb-faint font-normal text-[11px] ml-1">games</span></span>
        </div>
        <div className="flex items-center justify-between gap-2 mt-0.5">
          <span className="text-pb-faintest text-[11px] truncate">{sub || '—'}</span>
          <span className="iq-num text-pb-faint text-[11.5px] whitespace-nowrap">
            {m.wins}–{m.losses}–{m.draws}{m.win_pct != null ? ` · ${pctTxt(m.win_pct)}` : ''}
          </span>
        </div>
      </div>
    </button>
  )
}

/* ── With vs Without split — the Compare-like card ───────────────────────── */
function SplitRow({ label, withVal, withoutVal, better }) {
  const col = (side) => (better === side ? GREEN : 'var(--pb-text)')
  return (
    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 py-2.5" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
      <div className="iq-num font-semibold text-right text-[15px]" style={{ color: col('with') }}>{withVal}</div>
      <div className="iq-eyebrow text-center" style={{ fontSize: 9, minWidth: 92 }}>{label}</div>
      <div className="iq-num font-semibold text-[15px]" style={{ color: col('without') }}>{withoutVal}</div>
    </div>
  )
}

// Decide which side is "better" for a row. dir 'hi' = higher wins, 'lo' = lower
// wins (bowling avg / economy), null = neutral (no green).
function better(a, b, dir) {
  if (dir == null || a == null || b == null || a === b) return null
  if (dir === 'hi') return a > b ? 'with' : 'without'
  return a < b ? 'with' : 'without'
}

function WithWithout({ data }) {
  const w = data.with, o = data.without
  const nameX = surname(data.teammate?.name || '')
  const nameP = surname(data.player?.name || '')
  const rows = [
    { label: 'Games', a: w.record.games, b: o.record.games, dir: null, fmt: fmtCount },
    { label: 'Win %', a: w.record.win_pct, b: o.record.win_pct, dir: 'hi', fmt: pctTxt },
    { label: 'Bat avg', a: w.batting.average, b: o.batting.average, dir: 'hi', fmt: a2 },
    { label: 'Strike rate', a: w.batting.strike_rate, b: o.batting.strike_rate, dir: 'hi', fmt: (v) => (v == null ? '—' : a2(v)) },
    { label: 'Runs', a: w.batting.runs, b: o.batting.runs, dir: null, fmt: fmtCount },
    { label: 'Wickets', a: w.bowling.wickets, b: o.bowling.wickets, dir: null, fmt: fmtCount },
    { label: 'Bowl avg', a: w.bowling.average, b: o.bowling.average, dir: 'lo', fmt: a2 },
    { label: 'Economy', a: w.bowling.economy, b: o.bowling.economy, dir: 'lo', fmt: a2 },
  ]
  // Hide the bowling rows entirely if the player never bowled either way.
  const bowled = (w.bowling.wickets || o.bowling.wickets || w.bowling.economy != null || o.bowling.economy != null)
  const batted = (w.batting.innings || o.batting.innings)
  const shown = rows.filter(r => {
    if (['Bat avg', 'Strike rate', 'Runs'].includes(r.label) && !batted) return false
    if (['Wickets', 'Bowl avg', 'Economy'].includes(r.label) && !bowled) return false
    return true
  })
  return (
    <Card eyebrow="with vs without" title={<span><span style={{ color: ACCENT }}>{nameP}</span> alongside {nameX}</span>}>
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 pb-1">
        <div className="text-right font-bold iq-display truncate" style={{ color: ACCENT }}>With {nameX}</div>
        <div style={{ minWidth: 92 }} />
        <div className="font-bold iq-display truncate text-pb-dim">Without {nameX}</div>
      </div>
      {shown.map(r => (
        <SplitRow key={r.label} label={r.label}
          withVal={r.fmt(r.a)} withoutVal={r.fmt(r.b)}
          better={better(r.a, r.b, r.dir)} />
      ))}
      <Note>{nameP}’s own batting and bowling, and the team’s win rate, in the games {nameX} also played versus the games {nameX} did not. {data.note}</Note>
    </Card>
  )
}

/* ── Page ─────────────────────────────────────────────────────────────────── */
export default function Teammates() {
  const [params, setParams] = useSearchParams()
  const [players, setPlayers] = useState([])
  const [pid, setPid] = useState(params.get('player') || null)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [mate, setMate] = useState(params.get('with') || null)
  const [split, setSplit] = useState(null)
  const [splitLoading, setSplitLoading] = useState(false)

  useEffect(() => { api.iqAllPlayers().then(d => setPlayers(Array.isArray(d) ? d : [])).catch(() => setPlayers([])) }, [])

  useEffect(() => {
    if (!pid) { setData(null); return }
    let alive = true
    setLoading(true); setData(null)
    api.iqTeammates(pid)
      .then(d => { if (alive) setData(d) })
      .catch(() => { if (alive) setData({ error: true }) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [pid])

  useEffect(() => {
    if (!pid || !mate) { setSplit(null); return }
    let alive = true
    setSplitLoading(true); setSplit(null)
    api.iqTeammateSplit(pid, mate)
      .then(d => { if (alive) setSplit(d) })
      .catch(() => { if (alive) setSplit({ error: true }) })
      .finally(() => { if (alive) setSplitLoading(false) })
    return () => { alive = false }
  }, [pid, mate])

  const writeUrl = (player, withId) => {
    const p = new URLSearchParams()
    if (player) p.set('player', player)
    if (withId) p.set('with', withId)
    setParams(p, { replace: true })
  }
  const pick = (id) => { setPid(id); setMate(null); setSplit(null); writeUrl(id, null) }
  const pickMate = (id) => { setMate(id); writeUrl(pid, id) }

  const mates = data?.teammates || []
  const focal = data?.player?.name

  return (
    <IQLayout title="Teammates">
      <PageIntro>See everyone a player has shared a side with, ranked by games played together, then pick a teammate to see how the player goes with them in the side versus without. All career, from your own scorecards.</PageIntro>

      <Card eyebrow="pick a player" title="Whose teammates?">
        <div className="max-w-2xl"><PlayerSearch players={players} onPick={pick} /></div>
        {focal && <div className="mt-3 text-[13px] text-pb-dim">Showing teammates of <span className="font-semibold" style={{ color: ACCENT }}>{focal}</span>.</div>}
      </Card>

      {!pid ? null
        : loading ? <LoadingCard label="Finding teammates…" expectedMs={5000} />
        : data?.error ? <Card><Empty>Couldn’t load this player’s teammates.</Empty></Card>
        : (
          <div className="grid gap-5 lg:grid-cols-[minmax(280px,360px)_1fr] items-start mt-5">
            <Card eyebrow={`${fmtCount(mates.length)} ${mates.length === 1 ? 'teammate' : 'teammates'}`} title="Played alongside">
              {mates.length === 0 ? <Empty>No shared games on record yet.</Empty> : (
                <div className="space-y-1 -mx-1 iq-scroll" style={{ maxHeight: 560, overflowY: 'auto' }}>
                  {mates.map(m => (
                    <TeammateRow key={m.player_id} m={m} active={m.player_id === mate} onClick={() => pickMate(m.player_id)} />
                  ))}
                </div>
              )}
              <Note>Ordered by games in the same XI. Record is the team’s W–L–D in those shared games.</Note>
            </Card>

            <div>
              {!mate ? (
                <Card><Empty>Pick a teammate on the left to see {focal ? `${surname(focal)}’s` : 'the'} record with and without them.</Empty></Card>
              ) : splitLoading ? (
                <LoadingCard label="Working out the split…" expectedMs={5000} />
              ) : split?.error ? (
                <Card><Empty>Couldn’t load this split.</Empty></Card>
              ) : split ? (
                <WithWithout data={split} />
              ) : null}
            </div>
          </div>
        )}
    </IQLayout>
  )
}
