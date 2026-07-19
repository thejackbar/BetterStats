import { useEffect, useMemo, useState } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

// Super-Admin rollup of Setup Wizard progress across every club — see
// routers/wizard_analytics.py. Reads STORED progress only (no live
// auto-detection), and only clubs that have actually opened the wizard at
// least once (first_opened_at) feed the per-step numbers — a club that's
// simply never looked at it would otherwise read as "stuck on step 1" for
// every step, drowning out the clubs genuinely working through it.

function SummaryCard({ label, value, sub, tone }) {
  const toneCls = tone === 'warn' ? 'text-pb-amber' : tone === 'good' ? 'text-pb-positive' : 'text-pb-text'
  return (
    <div className="pb-card p-4">
      <p className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint">{label}</p>
      <p className={`text-2xl font-display font-bold mt-1 ${toneCls}`}>{value}</p>
      {sub && <p className="font-mono text-[10px] text-pb-faintest mt-1">{sub}</p>}
    </div>
  )
}

// A thin inline bar, used for done/skip/stuck rates in the steps table —
// keeps the numbers scannable without a charting dependency.
function Bar({ pct, color }) {
  if (pct == null) return <span className="text-pb-faintest">—</span>
  return (
    <div className="flex items-center gap-2 min-w-[90px]">
      <div className="flex-1 h-1.5 rounded-full bg-pb-surface2 overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="font-mono text-[10px] text-pb-faint w-8 text-right">{pct}%</span>
    </div>
  )
}

const STEP_SORTS = {
  order: null, // registry order, the default
  stuck: (s) => -(s.stuck_pct ?? -1),
  skip: (s) => -(s.skip_pct ?? -1),
  days: (s) => -(s.avg_days_to_done ?? -1),
}

const CLUB_SORTS = {
  name: (c) => c.name.toLowerCase(),
  pct: (c) => c.pct ?? -1,
  stuck: (c) => c.current_step_title || '',
  last: (c) => c.last_activity_at || '',
}

export default function SuperWizardAnalytics() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [stepSort, setStepSort] = useState('order')
  const [clubSort, setClubSort] = useState('pct')
  const [clubFilter, setClubFilter] = useState('')
  const [showUnengaged, setShowUnengaged] = useState(false)

  useEffect(() => {
    api.superWizardAnalytics()
      .then(setData)
      .catch((e) => setError(e.message || 'Could not load wizard analytics'))
      .finally(() => setLoading(false))
  }, [])

  const steps = useMemo(() => {
    if (!data) return []
    const list = [...data.steps]
    const sorter = STEP_SORTS[stepSort]
    if (sorter) list.sort((a, b) => (sorter(a) > sorter(b) ? 1 : sorter(a) < sorter(b) ? -1 : 0))
    return list
  }, [data, stepSort])

  const clubs = useMemo(() => {
    if (!data) return []
    let list = data.clubs
    if (!showUnengaged) list = list.filter((c) => c.engaged)
    if (clubFilter.trim()) {
      const q = clubFilter.trim().toLowerCase()
      list = list.filter((c) => c.name.toLowerCase().includes(q))
    }
    list = [...list]
    const key = CLUB_SORTS[clubSort]
    if (key) list.sort((a, b) => (key(a) < key(b) ? 1 : key(a) > key(b) ? -1 : 0))
    return list
  }, [data, clubFilter, showUnengaged, clubSort])

  const fmtDate = (d) => d ? new Date(d).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' }) : '—'

  return (
    <AdminLayout>
      <div className="max-w-[1200px] mx-auto p-4 sm:p-6">
        <div className="mb-5">
          <h1 className="text-xl font-semibold text-pb-text">Setup Wizard analytics</h1>
          <p className="text-sm text-pb-dim mt-1">
            Where clubs get stuck, skip, or mark steps as not applicable working through the
            Setup Wizard. Only clubs that have opened the wizard at least once feed the
            per-step numbers below.
          </p>
        </div>

        {error && <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3 mb-4">{error}</p>}

        {loading ? (
          <p className="text-sm text-pb-dim">Loading…</p>
        ) : !data ? null : (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-6">
              <SummaryCard label="Clubs" value={data.totals.clubs_total} />
              <SummaryCard label="Opened the wizard" value={data.totals.clubs_engaged}
                sub={`${data.totals.clubs_never_opened} never opened it`} />
              <SummaryCard label="Fully set up" value={data.totals.clubs_all_done} tone="good" />
              <SummaryCard label="Blocked on first sync" value={data.totals.clubs_blocked_on_sync}
                tone={data.totals.clubs_blocked_on_sync > 0 ? 'warn' : undefined} />
              <SummaryCard label="Avg. completion"
                value={data.totals.avg_completion_pct != null ? `${data.totals.avg_completion_pct}%` : '—'}
                sub="Among clubs that opened it" />
            </div>

            <div className="mb-6">
              <div className="flex items-center justify-between mb-2">
                <h2 className="font-display font-bold text-pb-text">Step-by-step funnel</h2>
                <div className="flex items-center gap-1.5 font-mono text-[10px]">
                  <span className="text-pb-faintest mr-1">SORT</span>
                  {[['order', 'Order'], ['stuck', 'Stuck %'], ['skip', 'Skip %'], ['days', 'Days to done']].map(([k, l]) => (
                    <button key={k} onClick={() => setStepSort(k)}
                      className={`px-2 py-1 rounded border transition-colors ${stepSort === k ? 'border-pb-accent text-pb-accent' : 'pb-hairline text-pb-faint hover:text-pb-text'}`}>
                      {l.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>
              <div className="pb-card overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left font-mono text-[10px] tracking-wide2 uppercase text-pb-faint border-b pb-hairline">
                      <th className="px-3 py-2.5">Step</th>
                      <th className="px-3 py-2.5">Reached</th>
                      <th className="px-3 py-2.5">Done</th>
                      <th className="px-3 py-2.5">Skipped</th>
                      <th className="px-3 py-2.5">Currently stuck here</th>
                      <th className="px-3 py-2.5">Avg. days to done</th>
                    </tr>
                  </thead>
                  <tbody>
                    {steps.map((s) => (
                      <tr key={s.key} className="border-b pb-hairline hover:bg-pb-surface2/40">
                        <td className="px-3 py-2">
                          <div className="text-pb-text">{s.title}</div>
                          <div className="font-mono text-[9px] text-pb-faintest">
                            {s.group_title}{s.vital ? ' · vital' : ''}{s.optional ? ' · optional' : ''}
                            {s.minutes ? ` · ≈${s.minutes}min` : ''}
                          </div>
                        </td>
                        <td className="px-3 py-2 text-pb-dim font-mono">{s.reached}</td>
                        <td className="px-3 py-2"><Bar pct={s.done_pct} color="var(--pb-positive)" /></td>
                        <td className="px-3 py-2"><Bar pct={s.skip_pct} color="var(--pb-amber)" /></td>
                        <td className="px-3 py-2">
                          <div className="flex items-center gap-2">
                            <span className={`font-mono text-sm ${s.stuck > 0 && s.stuck_pct >= 30 ? 'text-pb-red' : s.stuck > 0 ? 'text-pb-amber' : 'text-pb-faintest'}`}>
                              {s.stuck}
                            </span>
                            {s.stuck_pct != null && s.stuck > 0 && (
                              <span className="font-mono text-[10px] text-pb-faintest">({s.stuck_pct}%)</span>
                            )}
                          </div>
                        </td>
                        <td className="px-3 py-2 font-mono text-pb-dim text-[11px]">
                          {s.avg_days_to_done != null ? `${s.avg_days_to_done}d (n=${s.avg_days_sample})` : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="font-mono text-[10px] text-pb-faintest mt-1.5">
                "Reached" excludes clubs that haven't unlocked the step yet (still waiting on their
                first sync) and steps marked not applicable. "Stuck here" is the first step still
                open for that club, in wizard order — i.e. where they'd land if they opened the
                wizard right now.
              </p>
            </div>

            <div>
              <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                <h2 className="font-display font-bold text-pb-text">By club</h2>
                <div className="flex items-center gap-2">
                  <input
                    value={clubFilter}
                    onChange={(e) => setClubFilter(e.target.value)}
                    placeholder="Filter by club name…"
                    className="bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
                  />
                  <label className="flex items-center gap-1.5 font-mono text-[10px] text-pb-faint">
                    <input type="checkbox" checked={showUnengaged} onChange={(e) => setShowUnengaged(e.target.checked)} />
                    SHOW NEVER-OPENED
                  </label>
                </div>
              </div>
              <div className="pb-card overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left font-mono text-[10px] tracking-wide2 uppercase text-pb-faint border-b pb-hairline">
                      {[['name', 'Club'], ['pct', 'Progress'], ['stuck', 'Stuck at'], ['last', 'Last activity']].map(([k, l]) => (
                        <th key={k} className="px-3 py-2.5 cursor-pointer select-none" onClick={() => setClubSort(k)}>
                          {l}{clubSort === k ? ' ▾' : ''}
                        </th>
                      ))}
                      <th className="px-3 py-2.5">Skipped</th>
                      <th className="px-3 py-2.5">N/A</th>
                      <th className="px-3 py-2.5">Flags</th>
                    </tr>
                  </thead>
                  <tbody>
                    {clubs.length === 0 ? (
                      <tr><td colSpan={7} className="px-3 py-4 text-pb-faint font-mono text-[11px]">No clubs match.</td></tr>
                    ) : clubs.map((c) => (
                      <tr key={c.organisation_id} className="border-b pb-hairline hover:bg-pb-surface2/40">
                        <td className="px-3 py-2 text-pb-text">{c.name}</td>
                        <td className="px-3 py-2">
                          {c.engaged ? <Bar pct={c.pct} color={c.pct === 100 ? 'var(--pb-positive)' : 'var(--pb-accent)'} /> : <span className="text-pb-faintest font-mono text-[11px]">not opened</span>}
                        </td>
                        <td className="px-3 py-2 text-pb-dim text-[12px]">{c.engaged ? (c.current_step_title || 'All done') : '—'}</td>
                        <td className="px-3 py-2 font-mono text-[10px] text-pb-faintest">{fmtDate(c.last_activity_at)}</td>
                        <td className="px-3 py-2 font-mono text-pb-dim">{c.skipped_count || '—'}</td>
                        <td className="px-3 py-2 font-mono text-pb-dim">{c.na_count || '—'}</td>
                        <td className="px-3 py-2">
                          <div className="flex flex-wrap gap-1">
                            {!c.sync_ready && c.engaged && (
                              <span className="font-mono text-[9px] px-1.5 py-0.5 rounded bg-pb-amber/15 text-pb-amber">NO SYNC YET</span>
                            )}
                            {c.dismissed && (
                              <span className="font-mono text-[9px] px-1.5 py-0.5 rounded bg-pb-surface2 text-pb-faint">DISMISSED</span>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>
    </AdminLayout>
  )
}
