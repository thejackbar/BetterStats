import { useState, useEffect, useRef, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import IQLayout from '../../../components/admin/IQLayout'
import { api } from '../../../lib/api'
import { Icon, Btn, Tag, Empty, Search, Segmented } from '../betterselect/ui'

const POLL_MS = 2500

/* ── tiny presentational helpers ─────────────────────────────────────────── */

function ResultBadge({ r }) {
  const map = { W: ['W', 'var(--pb-brand)'], L: ['L', 'var(--pb-red)'], D: ['D', 'var(--pb-amber)'], T: ['T', 'var(--pb-amber)'] }
  const [label, color] = map[r] || ['·', 'var(--pb-faint)']
  return (
    <span className="inline-flex items-center justify-center w-5 h-5 rounded font-mono text-[10px] font-bold"
      style={{ background: `color-mix(in srgb, ${color} 18%, transparent)`, color }}>{label}</span>
  )
}

function FormTag({ form }) {
  if (!form) return null
  const tone = form === 'hot' ? 'amber' : form === 'cold' ? 'faint' : 'accent'
  const label = form === 'hot' ? 'In form' : form === 'cold' ? 'Out of form' : 'Steady'
  return <Tag tone={tone}>{label}</Tag>
}

function Stat({ label, value, sub }) {
  return (
    <div className="text-center px-3 py-2">
      <div className="font-display font-bold text-2xl pb-num leading-none">{value}</div>
      <div className="text-pb-faint text-[11px] mt-1 uppercase tracking-wide2">{label}</div>
      {sub && <div className="text-pb-faintest text-[10px] mt-0.5">{sub}</div>}
    </div>
  )
}

function Card({ title, right, children, accent = false }) {
  return (
    <div className="pb-card p-4 md:p-5" style={accent ? { borderColor: 'color-mix(in srgb, var(--pb-accent) 30%, transparent)' } : undefined}>
      {(title || right) && (
        <div className="flex items-center justify-between gap-3 mb-3">
          <h3 className="font-display font-bold">{title}</h3>
          {right}
        </div>
      )}
      {children}
    </div>
  )
}

const num = (v, dash = '—') => (v === null || v === undefined ? dash : v)

/* ── head-to-head (from the instant, held-data report) ───────────────────── */

function HeadToHead({ h2h }) {
  if (!h2h || !h2h.meetings) return null
  return (
    <Card title="Head-to-head" right={<span className="text-pb-faint text-xs">{h2h.meetings} meetings</span>}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-hairline pb-3 mb-3">
        <Stat label="Won" value={h2h.wins} />
        <Stat label="Lost" value={h2h.losses} />
        <Stat label="Drawn" value={(h2h.draws || 0) + (h2h.ties || 0)} />
        <Stat label="Win %" value={h2h.win_pct === null ? '—' : `${h2h.win_pct}`} />
        <Stat label="At home" value={`${h2h.home.wins}/${h2h.home.played}`} sub="W/P" />
        <Stat label="Away" value={`${h2h.away.wins}/${h2h.away.played}`} sub="W/P" />
      </div>
      {h2h.recent_form?.length > 0 && (
        <div className="flex items-center gap-2 mb-3">
          <span className="text-pb-faint text-xs uppercase tracking-wide2">Recent</span>
          <div className="flex gap-1">{h2h.recent_form.map((r, i) => <ResultBadge key={i} r={r} />)}</div>
        </div>
      )}
      {h2h.recent?.length > 0 && (
        <div className="overflow-x-auto -mx-1">
          <table className="w-full text-sm">
            <thead><tr className="text-pb-faint text-[11px] uppercase tracking-wide2 text-left">
              <th className="py-1 px-1 font-medium">Date</th>
              <th className="py-1 px-1 font-medium">Grade</th>
              <th className="py-1 px-1 font-medium">H/A</th>
              <th className="py-1 px-1 font-medium">Result</th>
            </tr></thead>
            <tbody>
              {h2h.recent.map((m, i) => (
                <tr key={i} className="border-t pb-hairline">
                  <td className="py-1.5 px-1 pb-num whitespace-nowrap">{m.played_at || '—'}</td>
                  <td className="py-1.5 px-1 text-pb-faint truncate max-w-[160px]">{m.grade_name || '—'}</td>
                  <td className="py-1.5 px-1 font-mono text-[11px]">{m.our_venue || '—'}</td>
                  <td className="py-1.5 px-1">{m.result ? <ResultBadge r={m.result[0]} /> : '—'}<span className="text-pb-faint text-xs ml-1">{m.winning_team || ''}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

/* ── opponent batting / bowling squad tables (from the live dossier) ──────── */

function BattingTable({ rows }) {
  if (!rows?.length) return <Empty>No batting data found.</Empty>
  return (
    <div className="overflow-x-auto -mx-1">
      <table className="w-full text-sm">
        <thead><tr className="text-pb-faint text-[11px] uppercase tracking-wide2 text-left">
          <th className="py-1 px-1 font-medium">Batter</th>
          <th className="py-1 px-1 font-medium text-right">Inns</th>
          <th className="py-1 px-1 font-medium text-right">Runs</th>
          <th className="py-1 px-1 font-medium text-right">Avg</th>
          <th className="py-1 px-1 font-medium text-right">SR</th>
          <th className="py-1 px-1 font-medium text-right">HS</th>
          <th className="py-1 px-1 font-medium text-right">50/100</th>
          <th className="py-1 px-1 font-medium">Recent</th>
          <th className="py-1 px-1 font-medium text-right">vs us</th>
        </tr></thead>
        <tbody>
          {rows.map(p => (
            <tr key={p.player_id} className="border-t pb-hairline">
              <td className="py-1.5 px-1 font-medium whitespace-nowrap">{p.name} {p.form === 'hot' && <span title="In form">🔥</span>}</td>
              <td className="py-1.5 px-1 text-right pb-num">{p.innings}</td>
              <td className="py-1.5 px-1 text-right pb-num font-semibold">{p.runs}</td>
              <td className="py-1.5 px-1 text-right pb-num">{num(p.average)}</td>
              <td className="py-1.5 px-1 text-right pb-num text-pb-faint">{num(p.strike_rate)}</td>
              <td className="py-1.5 px-1 text-right pb-num">{num(p.high_score)}</td>
              <td className="py-1.5 px-1 text-right pb-num text-pb-faint">{p.fifties}/{p.hundreds}</td>
              <td className="py-1.5 px-1 text-pb-faint pb-num text-[11px] whitespace-nowrap">{(p.recent_scores || []).join(' ') || '—'}</td>
              <td className="py-1.5 px-1 text-right text-[11px]">{p.vs_us ? <span title={`${p.vs_us.runs} runs @ ${num(p.vs_us.average)} vs us`} className="text-pb-text pb-num">{p.vs_us.runs}@{num(p.vs_us.average)}</span> : <span className="text-pb-faintest">—</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function BowlingTable({ rows }) {
  if (!rows?.length) return <Empty>No bowling data found.</Empty>
  return (
    <div className="overflow-x-auto -mx-1">
      <table className="w-full text-sm">
        <thead><tr className="text-pb-faint text-[11px] uppercase tracking-wide2 text-left">
          <th className="py-1 px-1 font-medium">Bowler</th>
          <th className="py-1 px-1 font-medium text-right">Ov</th>
          <th className="py-1 px-1 font-medium text-right">Wkts</th>
          <th className="py-1 px-1 font-medium text-right">Avg</th>
          <th className="py-1 px-1 font-medium text-right">Econ</th>
          <th className="py-1 px-1 font-medium text-right">Best</th>
          <th className="py-1 px-1 font-medium">Recent</th>
          <th className="py-1 px-1 font-medium text-right">vs us</th>
        </tr></thead>
        <tbody>
          {rows.map(p => (
            <tr key={p.player_id} className="border-t pb-hairline">
              <td className="py-1.5 px-1 font-medium whitespace-nowrap">{p.name}</td>
              <td className="py-1.5 px-1 text-right pb-num text-pb-faint">{num(p.overs)}</td>
              <td className="py-1.5 px-1 text-right pb-num font-semibold">{p.wickets}</td>
              <td className="py-1.5 px-1 text-right pb-num">{num(p.average)}</td>
              <td className="py-1.5 px-1 text-right pb-num text-pb-faint">{num(p.economy)}</td>
              <td className="py-1.5 px-1 text-right pb-num">{num(p.best)}</td>
              <td className="py-1.5 px-1 text-pb-faint pb-num text-[11px] whitespace-nowrap">{(p.recent_wickets || []).join(' ') || '—'}</td>
              <td className="py-1.5 px-1 text-right text-[11px]">{p.vs_us ? <span title={`${p.vs_us.wickets} wkts @ ${num(p.vs_us.average)} vs us`} className="text-pb-text pb-num">{p.vs_us.wickets}w@{num(p.vs_us.average)}</span> : <span className="text-pb-faintest">—</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ── danger men cards ─────────────────────────────────────────────────────── */

function DangerMen({ batters, bowlers }) {
  if (!batters?.length && !bowlers?.length) return null
  return (
    <Card title="Danger men" accent right={<Tag tone="accent">Watch these</Tag>}>
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-2">Top batters</div>
          <div className="space-y-2">
            {(batters || []).map(p => (
              <div key={p.player_id} className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <span className="font-medium">{p.name}</span> <FormTag form={p.form} />
                  <div className="text-pb-faintest text-[11px]">{(p.recent_scores || []).join(', ') || 'no recent scores'}</div>
                </div>
                <div className="text-right shrink-0 pb-num">
                  <div className="font-semibold">{p.runs} <span className="text-pb-faint text-xs">runs</span></div>
                  <div className="text-pb-faint text-[11px]">avg {num(p.average)}{p.vs_us ? ` · ${p.vs_us.runs} vs us` : ''}</div>
                </div>
              </div>
            ))}
            {!batters?.length && <Empty>—</Empty>}
          </div>
        </div>
        <div>
          <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-2">Top bowlers</div>
          <div className="space-y-2">
            {(bowlers || []).map(p => (
              <div key={p.player_id} className="flex items-center justify-between gap-2">
                <div className="min-w-0"><span className="font-medium">{p.name}</span>
                  <div className="text-pb-faintest text-[11px]">econ {num(p.economy)} · best {num(p.best)}</div>
                </div>
                <div className="text-right shrink-0 pb-num">
                  <div className="font-semibold">{p.wickets} <span className="text-pb-faint text-xs">wkts</span></div>
                  <div className="text-pb-faint text-[11px]">avg {num(p.average)}{p.vs_us ? ` · ${p.vs_us.wickets}w vs us` : ''}</div>
                </div>
              </div>
            ))}
            {!bowlers?.length && <Empty>—</Empty>}
          </div>
        </div>
      </div>
    </Card>
  )
}

/* ── our players vs them (selection intel, from the instant report) ───────── */

function OurRecord({ performers }) {
  const bat = performers?.batting || []
  const bowl = performers?.bowling || []
  if (!bat.length && !bowl.length) return null
  return (
    <Card title="Our record against them" right={<span className="text-pb-faint text-xs">selection intel</span>}>
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-2">Bat well vs them</div>
          {bat.length ? bat.slice(0, 6).map(p => (
            <div key={p.player_id} className="flex items-center justify-between py-0.5">
              <span className={p.active ? '' : 'text-pb-faint'}>{p.name}{!p.active && ' ·'}</span>
              <span className="pb-num text-pb-faint text-sm">{p.runs} @ {num(p.average)}</span>
            </div>
          )) : <Empty>—</Empty>}
        </div>
        <div>
          <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-2">Bowl well vs them</div>
          {bowl.length ? bowl.slice(0, 6).map(p => (
            <div key={p.player_id} className="flex items-center justify-between py-0.5">
              <span className={p.active ? '' : 'text-pb-faint'}>{p.name}{!p.active && ' ·'}</span>
              <span className="pb-num text-pb-faint text-sm">{p.wickets}w @ {num(p.average)}</span>
            </div>
          )) : <Empty>—</Empty>}
        </div>
      </div>
      <div className="text-pb-faintest text-[11px] mt-2">· = no longer active</div>
    </Card>
  )
}

/* ── venue record vs this opponent (instant) ─────────────────────────────── */

function VenueCard({ venues }) {
  if (!venues?.length) return null
  return (
    <Card title="By venue" right={<span className="text-pb-faint text-xs">vs this opponent</span>}>
      <div className="space-y-1.5">
        {venues.map((v, i) => {
          const losses = v.losses || 0
          const tone = v.wins > losses ? 'var(--pb-brand)' : v.wins < losses ? 'var(--pb-red)' : 'var(--pb-amber)'
          return (
            <div key={i} className="flex items-center justify-between gap-2 text-sm">
              <span className="truncate">{v.venue}</span>
              <span className="pb-num whitespace-nowrap" style={{ color: tone }}>
                {v.wins}–{losses}<span className="text-pb-faintest"> /{v.played}</span>
              </span>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

/* ── our bowlers vs their batters (instant, from wickets we've taken) ─────── */

function MatchupCard({ matchups }) {
  if (!matchups?.length) return null
  return (
    <Card title="Match-ups" accent right={<span className="text-pb-faint text-xs">our bowlers vs their batters</span>}>
      <div className="space-y-1.5">
        {matchups.map((m, i) => (
          <div key={i} className="flex items-center justify-between gap-2 text-sm">
            <span className="truncate"><span className="font-medium">{m.bowler}</span> <span className="text-pb-faintest">▸</span> {m.batter}</span>
            <span className="pb-num whitespace-nowrap text-pb-faint" title={`${m.runs} runs scored before dismissal`}>
              <b className="text-pb-text">{m.dismissals}×</b>
            </span>
          </div>
        ))}
      </div>
      <div className="text-pb-faintest text-[11px] mt-2">Times each of our bowlers has dismissed their batters.</div>
    </Card>
  )
}

/* ── opponent picker ──────────────────────────────────────────────────────── */

function OpponentPicker({ data, onPick, onMatch }) {
  const [q, setQ] = useState('')
  const opponents = data?.opponents || []
  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase()
    return t ? opponents.filter(o => (o.name || '').toLowerCase().includes(t)) : opponents
  }, [q, opponents])

  return (
    <div>
      {data?.upcoming?.length > 0 && (
        <div className="mb-5">
          <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-2">Upcoming</div>
          <div className="flex flex-wrap gap-2">
            {data.upcoming.slice(0, 6).map(fx => fx.opp_key ? (
              <button key={fx.fixture_id} onClick={() => onPick({ fixtureId: fx.fixture_id, opponent: fx.opp_key, name: fx.opponent_name })}
                className="pb-card px-3 py-2 text-left hover:border-pb-accent/50 transition-colors">
                <div className="font-medium text-sm flex items-center gap-1.5">{fx.opponent_name} <Tag tone="accent">History</Tag></div>
                <div className="text-pb-faintest text-[11px]">{fx.played_on || ''} {fx.home_away ? `· ${fx.home_away}` : ''}</div>
              </button>
            ) : (
              <div key={fx.fixture_id} className="pb-card px-3 py-2">
                <div className="font-medium text-sm flex items-center gap-1.5">{fx.opponent_name} <Tag tone="faint">Not linked</Tag></div>
                <div className="text-pb-faintest text-[11px] mb-1.5">{fx.played_on || ''} {fx.home_away ? `· ${fx.home_away}` : ''}</div>
                <div className="flex gap-1.5">
                  <Btn sm variant="soft" icon="search" onClick={() => onMatch(fx)}>Match club</Btn>
                  <Btn sm variant="ghost" onClick={() => onPick({ fixtureId: fx.fixture_id, name: fx.opponent_name })}>Scout as new</Btn>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-2">All opponents ({opponents.length})</div>
      <Search value={q} onChange={setQ} placeholder="Search opponents…" className="mb-3 max-w-sm" />
      {filtered.length === 0 ? (
        <Empty>No opponents found{q ? ` for “${q}”` : ' yet — play some games or sync history'}.</Empty>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map(o => (
            <button key={o.opp_key} onClick={() => onPick({ opponent: o.opp_key, name: o.name })}
              className="pb-card px-3 py-2.5 text-left hover:border-pb-accent/50 transition-colors flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="font-medium truncate">{o.name}</div>
                <div className="text-pb-faintest text-[11px]">{o.meetings} meetings{o.last_played ? ` · last ${o.last_played.slice(0, 4)}` : ''}</div>
              </div>
              {o.coverage === 'rich' && <Tag tone="accent">Synced</Tag>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

/* ── match-to-club modal ─────────────────────────────────────────────────────
 * When a fixture's free-text opponent name doesn't auto-link to a club in our
 * history, let the user search and pick the right club entity. The chosen
 * opp_key then drives head-to-head / our-record (identity), while the fixture
 * still supplies the grade for the live dossier. */
function MatchOpponentModal({ opponents, fixture, onPick, onClose }) {
  const [q, setQ] = useState('')
  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase()
    const base = t ? opponents.filter(o => (o.name || '').toLowerCase().includes(t)) : opponents
    return base.slice(0, 50)
  }, [q, opponents])
  return (
    <div onClick={onClose} className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div onClick={e => e.stopPropagation()} className="w-[440px] max-w-full bg-pb-surface rounded-2xl border border-pb-hairline2 overflow-hidden shadow-2xl flex flex-col max-h-[80vh]">
        <div className="px-4 py-3 border-b border-pb-hairline">
          <div className="font-mono text-[10px] uppercase tracking-wide3" style={{ color: 'var(--pb-accent)' }}>Match opponent to a club</div>
          <div className="font-display font-bold text-[15px] mt-0.5 truncate">{fixture?.name || 'Opponent'}</div>
          <div className="text-pb-faintest text-[11px]">Link this fixture to a club in your history to unlock head-to-head and your record vs them.</div>
        </div>
        <div className="p-3"><Search value={q} onChange={setQ} placeholder="Search your clubs…" /></div>
        <div className="px-3 pb-2 overflow-y-auto">
          {filtered.length === 0 ? <Empty>No clubs found.</Empty> : (
            <div className="space-y-1">
              {filtered.map(o => (
                <button key={o.opp_key} onClick={() => onPick(o)}
                  className="w-full flex items-center justify-between gap-2 px-3 py-2 rounded-lg hover:bg-pb-surface2 text-left">
                  <div className="min-w-0">
                    <div className="font-medium truncate">{o.name}</div>
                    <div className="text-pb-faintest text-[11px]">{o.meetings} meetings{o.last_played ? ` · last ${o.last_played.slice(0, 4)}` : ''}</div>
                  </div>
                  {o.coverage === 'rich' && <Tag tone="accent">Synced</Tag>}
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="px-4 py-3 border-t border-pb-hairline flex justify-end">
          <Btn variant="ghost" sm onClick={onClose}>Cancel</Btn>
        </div>
      </div>
    </div>
  )
}

/* ── main ─────────────────────────────────────────────────────────────────── */

export default function OppositionScout() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [list, setList] = useState(null)             // {opponents, upcoming}
  const [selected, setSelected] = useState(null)     // {opponent?, fixtureId?, name?}
  const [report, setReport] = useState(null)         // instant held-data report
  const [dossier, setDossier] = useState(null)       // live dossier (status/payload)
  const [tab, setTab] = useState('batting')
  const [matching, setMatching] = useState(null)     // fixture being matched to a club
  const pollRef = useRef(null)

  // Pull opponent list once.
  useEffect(() => {
    api.iqListOpponents().then(setList).catch(() => setList({ opponents: [], upcoming: [] }))
  }, [])

  // Seed selection from the URL (?fixture= or ?opponent=).
  useEffect(() => {
    const fixtureId = searchParams.get('fixture')
    const opponent = searchParams.get('opponent')
    if (fixtureId) setSelected({ fixtureId })
    else if (opponent) setSelected({ opponent })
  }, [])  // once, on mount

  const stopPoll = () => { if (pollRef.current) { clearTimeout(pollRef.current); pollRef.current = null } }

  // Load report + dossier whenever the selection changes.
  useEffect(() => {
    stopPoll()
    setReport(null); setDossier(null)
    if (!selected) return
    let alive = true
    const params = { opponent: selected.opponent, fixtureId: selected.fixtureId }

    api.iqOppositionReport(params).then(r => { if (alive) setReport(r) }).catch(() => { if (alive) setReport({ error: true }) })

    const poll = () => {
      api.iqOppositionDossier(params).then(d => {
        if (!alive) return
        setDossier(d)
        if (d.status === 'building') pollRef.current = setTimeout(poll, POLL_MS)
      }).catch(() => { if (alive) setDossier({ status: 'error' }) })
    }
    poll()
    return () => { alive = false; stopPoll() }
  }, [selected])

  const pick = (sel) => {
    setSelected(sel)
    const sp = {}
    if (sel.fixtureId) sp.fixture = sel.fixtureId
    else if (sel.opponent) sp.opponent = sel.opponent
    setSearchParams(sp, { replace: true })
  }
  const clearSelection = () => { setSelected(null); setSearchParams({}, { replace: true }) }

  // Manually match an unlinked fixture to a known club entity.
  const startMatch = (fx) => setMatching({ fixtureId: fx.fixture_id, name: fx.opponent_name })
  const applyMatch = (opp) => {
    const m = matching
    setMatching(null)
    if (m) pick({ fixtureId: m.fixtureId, opponent: opp.opp_key, name: opp.name })
  }

  const refresh = () => {
    if (!selected) return
    setDossier({ status: 'building' })
    api.iqRefreshDossier({ opponent: selected.opponent, fixtureId: selected.fixtureId })
      .then(d => {
        setDossier(d)
        if (d.status === 'building') { stopPoll(); pollRef.current = setTimeout(function p() {
          api.iqOppositionDossier({ opponent: selected.opponent, fixtureId: selected.fixtureId }).then(d2 => {
            setDossier(d2); if (d2.status === 'building') pollRef.current = setTimeout(p, POLL_MS)
          }).catch(() => setDossier({ status: 'error' }))
        }, POLL_MS) }
      }).catch(() => setDossier({ status: 'error' }))
  }

  const oppName = report?.opponent?.name || dossier?.opponent?.name || selected?.name || 'Opponent'
  const building = dossier?.status === 'building'
  const ready = dossier && dossier.status !== 'building' && dossier.status !== 'error' && dossier.status !== 'unavailable'

  // ── Picker view ──
  if (!selected) {
    return (
      <IQLayout title="Opposition analysis">
        {list === null
          ? <div className="pb-card p-5 animate-pulse text-pb-faint text-sm">Loading opponents…</div>
          : <OpponentPicker data={list} onPick={pick} onMatch={startMatch} />}
        {matching && <MatchOpponentModal opponents={list?.opponents || []} fixture={matching} onPick={applyMatch} onClose={() => setMatching(null)} />}
      </IQLayout>
    )
  }

  // A fixture was picked but its opponent didn't resolve to club history.
  const unresolved = !!selected?.fixtureId && report && !report.error && report.opponent && !report.opponent.opp_key

  // ── Report view ──
  return (
    <IQLayout
      title="Opposition analysis"
      actions={<Btn variant="ghost" sm icon="back" onClick={clearSelection}>Change opponent</Btn>}
    >
      {/* Opponent header */}
      <div className="flex flex-wrap items-end justify-between gap-3 mb-4">
        <div>
          <div className="font-mono text-[11px] uppercase tracking-wide3" style={{ color: 'var(--pb-accent)' }}>Scouting report</div>
          <h2 className="font-display font-bold text-2xl">{oppName}</h2>
        </div>
        <Btn variant="soft" sm icon="bolt" onClick={refresh} disabled={building}>
          {building ? 'Building…' : 'Refresh'}
        </Btn>
      </div>

      {unresolved && (
        <div className="pb-card p-4 mb-4 flex flex-wrap items-center justify-between gap-3"
          style={{ borderColor: 'color-mix(in srgb, var(--pb-accent) 30%, transparent)' }}>
          <div className="text-sm">
            <span className="font-medium">No history matched for “{oppName}”.</span>{' '}
            <span className="text-pb-faint">Link this fixture to a club to unlock head-to-head and your record against them.</span>
          </div>
          <Btn sm variant="soft" icon="search" onClick={() => startMatch({ fixture_id: selected.fixtureId, opponent_name: oppName })}>Match club</Btn>
        </div>
      )}

      {/* Instant: head-to-head + our record */}
      <div className="grid gap-4 lg:grid-cols-2 mb-4">
        {report === null ? <div className="pb-card p-5 animate-pulse text-pb-faint text-sm">Loading head-to-head…</div> : <HeadToHead h2h={report.head_to_head} />}
        {report && <OurRecord performers={report.our_performers} />}
      </div>

      {/* Instant: venue record + match-ups (from held data) */}
      {report && !report.error && (report.venues?.length > 0 || report.matchups?.length > 0) && (
        <div className="grid gap-4 lg:grid-cols-2 mb-4">
          <VenueCard venues={report.venues} />
          <MatchupCard matchups={report.matchups} />
        </div>
      )}

      {/* Live dossier */}
      {building && (
        <div className="pb-card p-6 text-center mb-4" style={{ borderColor: 'color-mix(in srgb, var(--pb-accent) 30%, transparent)' }}>
          <div className="inline-flex w-7 h-7 border-2 border-t-transparent rounded-full animate-spin mb-2" style={{ borderColor: 'var(--pb-accent)', borderTopColor: 'transparent' }} />
          <div className="font-display font-bold">Building their dossier…</div>
          <div className="text-pb-faint text-sm mt-1">Pulling {oppName}'s recent scorecards and their record against us. This can take up to a minute the first time.</div>
        </div>
      )}

      {dossier?.status === 'unavailable' && (
        <div className="pb-card p-5 mb-4"><Empty>{dossier.message || 'No live data available for this opponent yet.'}</Empty></div>
      )}
      {dossier?.status === 'error' && (
        <div className="pb-card p-5 mb-4"><Empty>Couldn’t build the live dossier just now. The head-to-head above still applies — try Refresh in a moment.</Empty></div>
      )}

      {ready && (
        <>
          <DangerMen batters={dossier.danger_batters} bowlers={dossier.danger_bowlers} />

          {dossier.historical_threats?.length > 0 && (
            <div className="mt-4">
              <Card title="Historically hurt us" right={<span className="text-pb-faint text-xs">not in recent squad</span>}>
                <div className="flex flex-wrap gap-x-5 gap-y-1">
                  {dossier.historical_threats.map(p => (
                    <span key={p.player_id} className="text-sm">{p.name} <span className="text-pb-faint pb-num">{p.runs}@{num(p.average)}</span></span>
                  ))}
                </div>
              </Card>
            </div>
          )}

          <div className="mt-4">
            <Card
              title="Their squad"
              right={<Segmented sm value={tab} onChange={setTab} options={[{ value: 'batting', label: 'Batting' }, { value: 'bowling', label: 'Bowling' }]} />}
            >
              {tab === 'batting' ? <BattingTable rows={dossier.batting} /> : <BowlingTable rows={dossier.bowling} />}
            </Card>
          </div>

          {/* Coverage note — honest about what the data supports */}
          {dossier.coverage?.notes?.length > 0 && (
            <div className="text-pb-faintest text-[11px] mt-3 flex items-start gap-1.5">
              <Icon name="info" size={13} className="mt-0.5 shrink-0" />
              <span>{dossier.coverage.notes.join(' ')}{dossier.built_at ? ` · built ${new Date(dossier.built_at).toLocaleString()}` : ''}</span>
            </div>
          )}
        </>
      )}

      {matching && <MatchOpponentModal opponents={list?.opponents || []} fixture={matching} onPick={applyMatch} onClose={() => setMatching(null)} />}
    </IQLayout>
  )
}
