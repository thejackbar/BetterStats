import { useCallback, useEffect, useMemo, useState } from 'react'
import { useToast } from '../../../../contexts/ToastContext'
import { api } from '../../../../lib/api'
import { Chip, Icon, Search } from '../ui'
import BallotProgress from './BallotProgress'
import VoteStateBadge from './VoteStateBadge'
import ShareVotePanel from './ShareVotePanel'
import OutstandingVoters from './OutstandingVoters'
import { STATUS_FILTERS, fmtDate, seasonLabel } from './votesTokens'

// The Votes hub replaces the old Fixtures tab. One screen answers "what needs
// me?": four counters, three filter axes that compose, per-fixture ballot
// progress, multi-select bulk open/lock/nudge, and sharing.
export default function VotesHub({ canManage, medalId, onOpenFixture }) {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [year, setYear] = useState(null)
  const [status, setStatus] = useState('all')
  const [gradeId, setGradeId] = useState('')
  const [roundKey, setRoundKey] = useState('')
  const [q, setQ] = useState('')
  const [selected, setSelected] = useState([])
  const [busy, setBusy] = useState(false)
  const [focusDetail, setFocusDetail] = useState(null)

  const load = useCallback(() => {
    api.votesFixtures({ year, grade_id: gradeId || undefined, round_key: roundKey || undefined, q: q || undefined, medal_id: medalId || undefined })
      .then(setData).catch((e) => toast.error(e.message))
  }, [year, gradeId, roundKey, q, medalId, toast])
  useEffect(() => { load() }, [load])

  // Status is filtered client-side so the counts on the pills stay stable while
  // you flick between them (the grade/round/search filters hit the API).
  const rows = useMemo(() => {
    const all = data?.fixtures || []
    const f = STATUS_FILTERS.find((s) => s.key === status)
    return f?.states ? all.filter((r) => f.states.includes(r.state)) : all
  }, [data, status])

  const counts = useMemo(() => {
    const all = data?.fixtures || []
    return STATUS_FILTERS.reduce((acc, f) => ({
      ...acc,
      [f.key]: f.states ? all.filter((r) => f.states.includes(r.state)).length : all.length,
    }), {})
  }, [data])

  const toggle = (id) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))
  const clear = () => setSelected([])

  const bulk = async (action) => {
    setBusy(true)
    try {
      const r = await api.votesBulkState({ fixture_ids: selected, action, medal_id: medalId || undefined })
      const skipped = (r.skipped || []).length
      toast.success(`${r.updated} game${r.updated === 1 ? '' : 's'} ${action === 'open' ? 'opened' : 'locked'}${skipped ? ` (${skipped} skipped)` : ''}`)
      clear(); load()
    } catch (e) { toast.error(e.message) }
    finally { setBusy(false) }
  }

  const bulkNudge = async () => {
    setBusy(true)
    try {
      const r = await api.votesNudge(null, { fixture_ids: selected, medal_id: medalId || undefined })
      toast.success(`Reminder sent to ${r.sent} player${r.sent === 1 ? '' : 's'}`)
      clear()
    } catch (e) { toast.error(e.message) }
    finally { setBusy(false) }
  }

  // The chase panel needs each outstanding voter's contact info, which the
  // hub's own list rows don't carry (only a count) — fetch it for whichever
  // open fixture is currently "in focus", same fixture-detail call the
  // FixtureDetail screen makes. Manage-only: nudging is a MANAGE_VOTES action.
  const focus = canManage ? (rows.find((r) => r.state === 'open') || null) : null
  useEffect(() => {
    if (!focus) { setFocusDetail(null); return }
    let alive = true
    api.votesFixtureDetail(focus.id, medalId).then((d) => { if (alive) setFocusDetail(d) }).catch(() => {})
    return () => { alive = false }
  }, [focus?.id, medalId]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!data) return <div className="py-16 text-center text-pb-faint text-sm">Loading fixtures…</div>

  const stats = data.summary || {}

  return (
    <div className="flex flex-col gap-5">
      {/* Counters */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-pb-hairline rounded-xl overflow-hidden border pb-hairline">
        {[
          { label: 'OPEN NOW', value: stats.open ?? 0, sub: 'games', color: 'var(--pb-positive)' },
          { label: 'BALLOTS THIS ROUND', value: stats.ballots_in ?? 0, sub: `of ${stats.ballots_expected ?? 0} eligible`, color: 'var(--pb-text)' },
          { label: 'AWAITING TEAM LIST', value: stats.awaiting_team ?? 0, sub: 'games', color: 'var(--pb-amber)' },
          { label: 'ROUNDS COUNTED', value: stats.rounds_counted ?? 0, sub: `of ${stats.rounds_total ?? 0}`, color: 'var(--pb-text)' },
        ].map((s) => (
          <div key={s.label} className="bg-pb-bg px-5 py-3.5">
            <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">{s.label}</div>
            <div className="flex items-baseline gap-2 mt-1">
              <div className="text-[26px] font-bold tabular-nums leading-none" style={{ color: s.color }}>{s.value}</div>
              <div className="text-xs text-pb-faint">{s.sub}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Filters — status (segmented) · grade (chips) · round + search */}
      <div className="flex flex-wrap items-center gap-x-3.5 gap-y-2.5">
        <div className="inline-flex p-[3px] gap-0.5 bg-pb-surface2 rounded-[9px] border pb-hairline">
          {STATUS_FILTERS.map((f) => {
            const active = status === f.key
            return (
              <button key={f.key} onClick={() => setStatus(f.key)}
                className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[12.5px] font-semibold transition ${
                  active ? 'bg-pb-accent/15 text-pb-accent' : 'text-pb-faint hover:text-pb-text'}`}>
                {f.label}
                <span className="font-mono text-[10.5px] opacity-70">{counts[f.key] ?? 0}</span>
              </button>
            )
          })}
        </div>

        <span className="w-px h-[22px] bg-pb-hairline" />

        <div className="flex flex-wrap gap-1.5">
          <Chip label="All grades" active={!gradeId} onClick={() => setGradeId('')} />
          {(data.grades || []).map((g) => (
            <Chip key={g.id} label={g.name} active={gradeId === g.id}
              onClick={() => { setGradeId(g.id); setRoundKey('') }} />
          ))}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <Search value={q} onChange={setQ} placeholder="Opponent or player…" className="w-[210px]" />
          <select value={roundKey} onChange={(e) => setRoundKey(e.target.value)}
            className="bg-pb-surface2 border pb-hairline rounded-[9px] h-[38px] px-2.5 text-[13px] focus:outline-none focus:border-pb-accent">
            <option value="">All rounds</option>
            {(data.rounds || []).map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
          </select>
          <select value={data.year} onChange={(e) => { setYear(parseInt(e.target.value, 10)); setRoundKey('') }}
            className="bg-pb-surface2 border pb-hairline rounded-[9px] h-[38px] px-2.5 text-[13px] focus:outline-none focus:border-pb-accent">
            {data.years.map((y) => <option key={y} value={y}>{seasonLabel(y)}</option>)}
          </select>
        </div>
      </div>

      {/* Fixture table */}
      <div className="rounded-xl border pb-hairline overflow-hidden">
        {canManage && selected.length > 0 && (
          <div className="flex flex-wrap items-center gap-3 px-5 py-2.5 bg-pb-accent/10 border-b border-pb-accent/25">
            <span className="text-[13px] font-semibold text-pb-accent">
              {selected.length} game{selected.length === 1 ? '' : 's'} selected
            </span>
            <div className="flex gap-1.5">
              <button onClick={() => bulk('open')} disabled={busy}
                className="px-2.5 py-1 rounded-lg text-[12.5px] font-semibold disabled:opacity-50"
                style={{ background: 'var(--pb-positive)', color: 'var(--pb-bg)' }}>Open voting</button>
              <button onClick={() => bulk('lock')} disabled={busy}
                className="px-2.5 py-1 rounded-lg text-[12.5px] bg-pb-surface2 border pb-hairline2 text-pb-text disabled:opacity-50">Lock voting</button>
              <button onClick={bulkNudge} disabled={busy}
                className="px-2.5 py-1 rounded-lg text-[12.5px] bg-pb-surface2 border pb-hairline2 text-pb-text disabled:opacity-50">Nudge non-voters</button>
            </div>
            <button onClick={clear} className="ml-auto text-[12.5px] text-pb-faint hover:text-pb-text">Clear</button>
          </div>
        )}

        <div className="hidden md:grid grid-cols-[36px_minmax(220px,1fr)_140px_210px_120px_96px] items-center gap-4
                        px-5 py-2.5 border-b pb-hairline font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">
          <div />
          <div>Fixture</div><div>Grade</div><div>Ballots in</div><div>Closes</div>
          <div className="text-right">Status</div>
        </div>

        {rows.length === 0 && (
          <div className="px-5 py-12 text-center text-pb-faint text-sm">No fixtures match these filters.</div>
        )}

        {rows.map((f) => {
          const checked = selected.includes(f.id)
          return (
            <div key={f.id}
              className="grid grid-cols-[36px_1fr] md:grid-cols-[36px_minmax(220px,1fr)_140px_210px_120px_96px]
                         items-center gap-x-4 gap-y-1.5 px-5 py-3.5 border-b pb-hairline last:border-0 hover:bg-pb-surface2/60 transition-colors">
              {canManage ? (
                <button onClick={() => toggle(f.id)} aria-label="Select fixture"
                  className="w-[18px] h-[18px] rounded-[5px] flex items-center justify-center transition"
                  style={checked
                    ? { background: 'var(--pb-accent)', border: '1px solid var(--pb-accent)' }
                    : { background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline2)' }}>
                  {checked && <Icon name="check" size={12} style={{ color: 'var(--pb-bg)' }} strokeWidth={3} />}
                </button>
              ) : <div />}

              <button onClick={() => canManage && onOpenFixture(f.id)} className="text-left min-w-0">
                <div className="text-[14.5px] font-semibold truncate">
                  {f.round} · {f.home_away === 'AWAY' ? '@' : 'vs'} {f.opponent || 'TBC'}
                </div>
                <div className="text-xs text-pb-faint mt-0.5">{fmtDate(f.date, { weekday: 'short', day: 'numeric', month: 'short' })}</div>
              </button>

              <div className="text-[13px] text-pb-dim hidden md:block">{f.grade || '—'}</div>
              <BallotProgress count={f.ballots} expected={f.voters_expected} className="hidden md:flex" />
              <div className="text-[12.5px] hidden md:block" style={{ color: f.state === 'open' ? 'var(--pb-text)' : 'var(--pb-faint)' }}>
                {f.closes_on ? fmtDate(f.closes_on) : '—'}
              </div>
              <div className="md:text-right"><VoteStateBadge state={f.state} /></div>
            </div>
          )
        })}
      </div>

      {/* Share + chase */}
      <div className="flex flex-col lg:flex-row gap-5">
        <div className="flex-1 min-w-0">
          <ShareVotePanel
            settings={data.settings}
            scope={{ gradeId, roundKey, label: gradeId ? (data.grades.find((g) => g.id === gradeId)?.name) : 'Whole club' }}
            fixtures={rows}
          />
        </div>
        {canManage && focus && (
          <div className="w-full lg:w-[300px] shrink-0">
            <OutstandingVoters
              medalId={medalId}
              fixture={focusDetail ? { ...focus, outstanding: focusDetail.outstanding } : focus}
              onNudged={() => { load(); api.votesFixtureDetail(focus.id, medalId).then(setFocusDetail).catch(() => {}) }}
            />
          </div>
        )}
      </div>
    </div>
  )
}
