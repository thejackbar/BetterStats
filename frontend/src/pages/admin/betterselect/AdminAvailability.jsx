import { useState, useEffect, useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { nameMatchesSearch } from '../../../lib/nameFormat'
import { PbSpinner } from '../../../lib/presskit'
import { AVAILABILITY, AVAIL_ORDER } from '../../../lib/availability'
import {
  Icon, Avatar, RoleChips, Btn, Segmented, Search, Chip, Empty, AvailSummary, QuickAvailModal,
  RecencySelect, playedWithinYears,
} from './ui'

// ============================================================================
// Availability — players × upcoming-dates matrix.
//
// Ported from docs/design_handoff_betterselect/prototype/bs-availability.jsx
// onto the real ./ui atom kit and the live availability API.
//
// NOTE on "periods": the old Availability-Periods editor that used to live on
// this screen has been REPLACED by the date-range bulk-fill below. Applying a
// range expands to explicit per-(player,date) rows via bsBulkAvailability, which
// the backend already treats as overrides ("an explicit answer always takes
// precedence over a period" — see availability.py:resolve_period_statuses). The
// period endpoints (bsAvailabilityPeriods / bsCreateAvailabilityPeriod /
// bsDeleteAvailabilityPeriod) are intentionally LEFT IN PLACE server-side: any
// pre-existing period still resolves as a background fallback for dates that
// have no explicit row, and such cells still render with a dashed border. We
// simply no longer surface period CRUD here.
// ============================================================================

const STATUS_LABEL = Object.fromEntries(AVAIL_ORDER.map((s) => [s, AVAILABILITY[s].label.toLowerCase()]))

function fmtDay(d) {
  try { return new Date(d + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }) }
  catch { return d }
}

function fmtYear(d) {
  if (!d) return ''
  try { return new Date(d + 'T00:00:00').getFullYear() } catch { return '' }
}

// Build the prototype's "vs Willetton" fixture sub-label from a date's fixtures.
function fixtureSub(dateObj) {
  const fxs = dateObj.fixtures || []
  if (!fxs.length) return ''
  return fxs.map((f) => {
    const opp = f.opponent_name || f.label || 'TBC'
    const prefix = f.home_away === 'AWAY' ? '@ ' : f.home_away === 'BYE' ? '' : 'vs '
    const d1d2 = f.two_day ? (f.role === 'day1' ? 'D1 ' : f.role === 'day2' ? 'D2 ' : '') : ''
    return `${d1d2}${prefix}${opp}`
  }).join(' · ')
}

export default function AdminAvailability() {
  const { hasCapability } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const canEdit = hasCapability(CAP.MANAGE_SELECTIONS)

  const [data, setData] = useState(null)
  const [avail, setAvail] = useState({}) // {playerId: {date: {status, source, note, ...}}}

  // Filters
  const [search, setSearch] = useState('')
  const [roster, setRoster] = useState('current')   // 'current' hides dormant/inactive; 'all' shows everyone
  const [squadFilter, setSquadFilter] = useState('') // '' = any squad
  const [years, setYears] = useState(0)              // recency: played within N yrs (0 = any)
  const [respFilter, setRespFilter] = useState(null) // availability status across shown dates

  // Selected week (column) — drives the Pick XI handoff and single-week bulk.
  const [selDate, setSelDate] = useState(null)

  // Date-range: filters which date COLUMNS are shown AND scopes the bulk-fill.
  // `rangeApplied` is what the matrix actually uses; the From/To selects are
  // staged until Apply so the column count only changes when you commit.
  const [rangeOn, setRangeOn] = useState(false)
  const [rangeFrom, setRangeFrom] = useState(null)
  const [rangeTo, setRangeTo] = useState(null)
  const [rangeApplied, setRangeApplied] = useState(null) // { from, to } | null

  // Bulk update
  const [selected, setSelected] = useState(() => new Set())
  const [bulkStatus, setBulkStatus] = useState('AVAILABLE')
  const [bulkReason, setBulkReason] = useState('')
  const [applying, setApplying] = useState(false)

  // Quick-update modal: { pid, date }
  const [modal, setModal] = useState(null)

  const load = useCallback(() => {
    setData(null)
    api.bsAvailabilityMatrix()
      .then((d) => {
        setData(d)
        setAvail(d.availability || {})
        const dts = d.dates || []
        if (dts.length) {
          setSelDate((cur) => cur || dts[0].date)
          setRangeFrom((cur) => cur || dts[0].date)
          setRangeTo((cur) => cur || dts[Math.min(3, dts.length - 1)].date)
        }
      })
      .catch((e) => { toast.error(e.message); setData({ dates: [], players: [], availability: {} }) })
  }, [toast])

  useEffect(() => { load() }, [load])

  const allDates = useMemo(() => data?.dates || [], [data])
  // The columns the matrix actually shows: the applied range narrows them.
  const dates = useMemo(() => {
    if (!rangeApplied) return allDates
    const all = allDates.map((d) => d.date)
    const a = all.indexOf(rangeApplied.from), b = all.indexOf(rangeApplied.to)
    if (a < 0 || b < 0) return allDates
    return allDates.slice(Math.min(a, b), Math.max(a, b) + 1)
  }, [allDates, rangeApplied])
  const squadOptions = useMemo(() => data?.all_squads || [], [data])

  // Staged-range preview (for the panel's "N games" + chips, before Apply).
  const idxAll = useCallback((dt) => allDates.findIndex((d) => d.date === dt), [allDates])
  const stagedDates = useMemo(() => {
    const a = idxAll(rangeFrom), b = idxAll(rangeTo)
    if (a < 0 || b < 0) return allDates
    return allDates.slice(Math.min(a, b), Math.max(a, b) + 1)
  }, [allDates, idxAll, rangeFrom, rangeTo])

  const applyRange = () => { setRangeApplied({ from: rangeFrom, to: rangeTo }); if (!stagedDates.some((d) => d.date === selDate)) setSelDate(stagedDates[0]?.date || null) }
  const clearRange = () => { setRangeApplied(null) }

  // Keep the active week inside the shown columns.
  useEffect(() => {
    if (dates.length && selDate && !dates.some((d) => d.date === selDate)) setSelDate(dates[0].date)
  }, [dates, selDate])

  // A player's "effective" response for the response filter.
  const matchesResponse = useCallback((p) => {
    if (!respFilter) return true
    const byDate = avail[p.id] || {}
    if (respFilter === 'NO_RESPONSE') {
      return dates.every((d) => (byDate[d.date]?.status || 'NO_RESPONSE') === 'NO_RESPONSE')
    }
    return dates.some((d) => byDate[d.date]?.status === respFilter)
  }, [respFilter, avail, dates])

  const players = useMemo(() => {
    return (data?.players || []).filter((p) => {
      // Roster visibility — 'current' hides dormant (and never-played inactive).
      if (roster === 'current' && !p.is_current) return false
      if (squadFilter && !(p.squads || []).includes(squadFilter)) return false
      if (!playedWithinYears(p.last_played, years)) return false
      if (search.trim() && !nameMatchesSearch(p.display_name, search)) return false
      if (!matchesResponse(p)) return false
      return true
    })
  }, [data, roster, squadFilter, years, search, matchesResponse])

  // Per-date player list as objects carrying a flat `availability` status, so we
  // can hand the matched-player set straight to <AvailSummary statusOf=…>.
  const colPlayers = useCallback((date) =>
    players.map((p) => ({ availability: avail[p.id]?.[date]?.status || 'NO_RESPONSE' })),
  [players, avail])
  const colInCount = useCallback((date) =>
    players.reduce((n, p) => n + ((avail[p.id]?.[date]?.status || 'NO_RESPONSE') === 'AVAILABLE' ? 1 : 0), 0),
  [players, avail])

  // ---- single-cell write (quick modal; no cell cycling) --------------------
  const setCell = async (pid, date, status) => {
    if (!canEdit) return
    const prev = avail
    setAvail((a) => ({ ...a, [pid]: { ...(a[pid] || {}), [date]: { status, source: 'explicit' } } }))
    setModal(null)
    try {
      await api.bsSetAvailability({ player_id: pid, date, status })
    } catch (e) {
      setAvail(prev)
      toast.error('Save failed: ' + e.message)
    }
  }

  const toggleSel = (pid) => setSelected((s) => { const n = new Set(s); n.has(pid) ? n.delete(pid) : n.add(pid); return n })
  const allSelected = players.length > 0 && players.every((p) => selected.has(p.id))
  const toggleSelAll = () => setSelected((s) => {
    const all = players.every((p) => s.has(p.id))
    const n = new Set(s)
    players.forEach((p) => all ? n.delete(p.id) : n.add(p.id))
    return n
  })

  // ---- bulk write: expand (selected players × target dates) into ONE call --
  // In range mode the targets are every shown (in-range) date; otherwise just
  // the selected week. Each item carries the optional reason as `note`.
  const applyBulk = async () => {
    if (!canEdit || selected.size === 0) return
    const targets = rangeApplied ? dates.map((d) => d.date) : (selDate ? [selDate] : [])
    if (!targets.length) return
    const note = bulkReason.trim() || undefined
    const items = []
    for (const pid of selected) {
      for (const date of targets) {
        items.push({ player_id: pid, date, status: bulkStatus, ...(note ? { note } : {}) })
      }
    }
    setApplying(true)
    const prev = avail
    setAvail((a) => {
      const next = { ...a }
      for (const pid of selected) {
        next[pid] = { ...(next[pid] || {}) }
        for (const date of targets) next[pid][date] = { status: bulkStatus, note, source: 'explicit' }
      }
      return next
    })
    try {
      await api.bsBulkAvailability(items)
      const span = rangeApplied
        ? `${fmtDay(rangeApplied.from)} → ${fmtDay(rangeApplied.to)} (${targets.length} game${targets.length === 1 ? '' : 's'})`
        : fmtDay(selDate)
      toast.success(`Marked ${selected.size} player${selected.size === 1 ? '' : 's'} ${STATUS_LABEL[bulkStatus]} · ${span}`)
      setSelected(new Set())
      setBulkReason('')
    } catch (e) {
      setAvail(prev)
      toast.error('Bulk update failed: ' + e.message)
    } finally {
      setApplying(false)
    }
  }

  if (data === null) {
    return <BetterSelectLayout title="Availability"><PbSpinner message="Loading availability…" /></BetterSelectLayout>
  }

  if (!dates.length) {
    return (
      <BetterSelectLayout title="Availability">
        <div className="pb-card px-5 py-10 text-center text-pb-faint text-sm">
          No upcoming fixtures to collect availability for.{' '}
          <button onClick={() => navigate('/admin/betterselect/fixtures')} className="text-pb-accent underline">Add or sync fixtures</button> first.
        </div>
      </BetterSelectLayout>
    )
  }

  return (
    <BetterSelectLayout
      title="Availability"
      actions={canEdit && (
        <Btn variant="primary" sm icon="selection" onClick={() => navigate('/admin/betterselect/selection')}>Pick this weekend</Btn>
      )}
    >
      {/* Filter bar — one compact row */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <Search value={search} onChange={setSearch} placeholder="Search players…" />
        <Segmented value={roster} onChange={setRoster} options={[
          { value: 'current', label: 'Current squad' },
          { value: 'all', label: 'All' },
        ]} />
        {squadOptions.length > 0 && (
          <select value={squadFilter} onChange={(e) => setSquadFilter(e.target.value)}
            title="Filter to one squad"
            className="bg-pb-surface2 border pb-hairline rounded-lg px-2.5 h-[38px] text-pb-text text-sm focus:outline-none focus:border-pb-accent">
            <option value="">All squads</option>
            {squadOptions.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        )}
        <RecencySelect value={years} onChange={setYears} />
        <div className="flex flex-wrap gap-1.5">
          {AVAIL_ORDER.map((s) => (
            <Chip key={s} label={AVAILABILITY[s].label} dot={AVAILABILITY[s].cssVar}
              active={respFilter === s} onClick={() => setRespFilter(respFilter === s ? null : s)} />
          ))}
        </div>
        <button onClick={() => setRangeOn((v) => !v)}
          className={`ml-auto inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] transition-colors ${rangeOn ? 'border-pb-accent text-pb-accent bg-pb-accent/10' : 'border-pb-hairline2 text-pb-dim hover:text-pb-text'}`}>
          <Icon name="fixtures" size={14} /> Date range {rangeOn ? '▲' : '▼'}
        </button>
      </div>

      {/* Date-range panel: narrows the shown columns (Apply) and scopes the
          bulk-fill. Staged From/To only take effect on Apply, so the column
          count changes when you commit — not while you're still choosing. */}
      {rangeOn && (
        <div className="pb-card p-3 mb-4 flex flex-wrap items-center gap-3">
          <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Show weeks</span>
          <select value={rangeFrom || ''} onChange={(e) => setRangeFrom(e.target.value)}
            className="bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent">
            {allDates.map((d) => <option key={d.date} value={d.date}>{fmtDay(d.date)}</option>)}
          </select>
          <span className="text-pb-faint">→</span>
          <select value={rangeTo || ''} onChange={(e) => setRangeTo(e.target.value)}
            className="bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent">
            {allDates.map((d) => <option key={d.date} value={d.date}>{fmtDay(d.date)}</option>)}
          </select>
          <Btn variant="primary" sm onClick={applyRange}>Apply ({stagedDates.length} week{stagedDates.length === 1 ? '' : 's'})</Btn>
          {rangeApplied && <Btn variant="ghost" sm onClick={clearRange}>Show all {allDates.length}</Btn>}
          <span className="ml-auto inline-flex items-center gap-1.5 text-[11px] text-pb-faint">
            <Icon name="info" size={13} /> {rangeApplied ? `Showing ${dates.length} of ${allDates.length} weeks` : `Showing all ${allDates.length} weeks`}
          </span>
        </div>
      )}

      {/* Bulk action bar — appears once players are ticked */}
      {canEdit && selected.size > 0 && (
        <div className="pb-card p-3 mb-4 flex flex-wrap items-center gap-3 border" style={{ borderColor: 'var(--pb-accent)' }}>
          <span className="font-mono text-[11px] text-pb-accent">{selected.size} selected</span>
          <span className="text-sm text-pb-dim">mark</span>
          <Segmented sm value={bulkStatus} onChange={setBulkStatus}
            options={AVAIL_ORDER.map((s) => ({ value: s, label: AVAILABILITY[s].short }))} />
          {rangeApplied ? (
            <span className="inline-flex items-center gap-2 text-sm text-pb-dim">
              across
              <span className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs text-pb-accent bg-pb-accent/10 border border-pb-accent/30">
                {fmtDay(rangeApplied.from)} → {fmtDay(rangeApplied.to)} <span className="font-mono">· {dates.length} games</span>
              </span>
            </span>
          ) : (
            <span className="inline-flex items-center gap-2 text-sm text-pb-dim">
              for
              <select value={selDate || ''} onChange={(e) => setSelDate(e.target.value)}
                className="bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent">
                {dates.map((d) => <option key={d.date} value={d.date}>{fmtDay(d.date)}</option>)}
              </select>
            </span>
          )}
          <input value={bulkReason} onChange={(e) => setBulkReason(e.target.value)}
            placeholder="Reason (optional)"
            className="bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent min-w-[150px]" />
          <Btn variant="primary" sm onClick={applyBulk} disabled={applying}>{applying ? 'Applying…' : 'Apply'}</Btn>
          <Btn variant="ghost" sm onClick={() => { setSelected(new Set()); setBulkReason('') }}>Clear</Btn>
        </div>
      )}

      {/* Matrix */}
      <div className="pb-card overflow-auto">
        <table className="border-separate w-full" style={{ borderSpacing: 0, minWidth: 760 }}>
          <thead>
            <tr>
              <th className="sticky left-0 top-0 z-30 bg-pb-surface2 text-left px-4 py-3 border-b pb-hairline" style={{ minWidth: 170 }}>
                <div className="flex items-center gap-2.5">
                  {canEdit && (
                    <input type="checkbox" checked={allSelected} onChange={toggleSelAll}
                      className="accent-pb-accent" style={{ width: 15, height: 15 }} title="Select all shown" />
                  )}
                  <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Player</span>
                  <span className="ml-auto font-mono text-[11px] text-pb-faint">{players.length}</span>
                </div>
              </th>
              {dates.map((d) => {
                const sel = d.date === selDate
                const sub = fixtureSub(d)
                return (
                  <th key={d.date} onClick={() => setSelDate(d.date)}
                    className="sticky top-0 z-20 px-3 py-2.5 border-b border-l pb-hairline text-center cursor-pointer"
                    style={{
                      minWidth: 120,
                      background: sel ? 'color-mix(in srgb, var(--pb-accent) 7%, var(--pb-surface2))' : 'var(--pb-surface2)',
                      borderTop: sel ? '2px solid var(--pb-accent)' : '2px solid transparent',
                    }}>
                    <div className="flex items-center justify-center gap-1.5">
                      <span className="inline-block rounded-full" style={{
                        width: 8, height: 8,
                        border: `1.5px solid ${sel ? 'var(--pb-accent)' : 'var(--pb-faintest)'}`,
                        background: sel ? 'var(--pb-accent)' : 'transparent',
                      }} />
                      <span className="font-display font-bold text-[13px]" style={{ color: sel ? 'var(--pb-accent)' : 'var(--pb-text)' }}>{fmtDay(d.date)}</span>
                    </div>
                    {sub && <div className="text-[10px] text-pb-faint mt-0.5 truncate" title={sub} style={{ maxWidth: 112, margin: '2px auto 0' }}>{sub}</div>}
                    <div className="mt-2"><AvailSummary players={colPlayers(d.date)} compact hideTotal /></div>
                    <div className="font-mono text-[10px] text-pb-dim mt-1.5"><b className="text-pb-accent">{colInCount(d.date)}</b> in</div>
                    {sel ? (
                      <Btn variant="primary" sm className="mt-2 w-full justify-center"
                        onClick={(e) => { e.stopPropagation(); navigate('/admin/betterselect/selection') }}>
                        Pick XI <Icon name="arrow" size={13} />
                      </Btn>
                    ) : (
                      <div className="mt-2 text-[10px] text-pb-faintest py-1">select week</div>
                    )}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {players.length === 0 && (
              <tr>
                <td colSpan={dates.length + 1} className="border-t pb-hairline px-4 py-8 text-center">
                  <Empty>No players match these filters. Try clearing the search/response filter, or switch to “All”.</Empty>
                </td>
              </tr>
            )}
            {players.map((p) => (
              <tr key={p.id} style={{ background: selected.has(p.id) ? 'color-mix(in srgb, var(--pb-accent) 5%, transparent)' : 'transparent' }}>
                <td className="sticky left-0 z-10 px-4 py-1.5 border-b pb-hairline"
                  style={{ background: selected.has(p.id) ? 'var(--pb-surface2)' : 'var(--pb-surface)' }}>
                  <div className="flex items-center gap-2.5">
                    {canEdit && (
                      <input type="checkbox" checked={selected.has(p.id)} onChange={() => toggleSel(p.id)}
                        className="accent-pb-accent" style={{ width: 15, height: 15 }} />
                    )}
                    <Avatar player={p} size={28} />
                    <span className="text-sm font-medium truncate">{p.display_name}</span>
                    {p.is_dormant && <span className="font-mono text-[9px] text-amber-300/80 uppercase shrink-0" title={`Dormant${p.last_played ? ' since ' + fmtYear(p.last_played) : ''}`}>dormant</span>}
                    {p.is_inactive && <span className="font-mono text-[9px] text-pb-red/80 uppercase shrink-0" title="Marked inactive">inactive</span>}
                  </div>
                </td>
                {dates.map((d) => {
                  const cell = avail[p.id]?.[d.date]
                  const st = cell?.status || 'NO_RESPONSE'
                  const meta = AVAILABILITY[st]
                  const fromPeriod = cell?.source === 'period'
                  const empty = st === 'NO_RESPONSE'
                  const sel = d.date === selDate
                  const title = fromPeriod
                    ? `${meta.label}${cell.note ? ' · ' + cell.note : ''} — from a period${canEdit ? ' (click to override)' : ''}`
                    : meta.label
                  return (
                    <td key={d.date} className="text-center border-b border-l pb-hairline"
                      style={{
                        padding: '6px 0',
                        background: sel ? 'color-mix(in srgb, var(--pb-accent) 4%, transparent)' : 'transparent',
                      }}>
                      <button
                        onClick={() => canEdit && setModal({ pid: p.id, date: d.date })}
                        disabled={!canEdit}
                        title={title}
                        className={`inline-flex items-center justify-center font-mono text-sm transition-transform active:scale-90 ${canEdit ? 'cursor-pointer' : 'cursor-default'}`}
                        style={{
                          width: 38, height: 30, borderRadius: 7, fontWeight: 600,
                          color: empty ? 'var(--pb-faintest)' : meta.cssVar,
                          background: empty ? 'transparent' : `color-mix(in srgb, ${meta.cssVar} 14%, transparent)`,
                          border: fromPeriod ? `1.5px dashed ${meta.cssVar}` : `1px solid ${empty ? 'var(--pb-hairline)' : 'transparent'}`,
                        }}>
                        {meta.glyph}
                      </button>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Quick-update modal — set one player's availability on one date */}
      {modal && (() => {
        const pl = (data.players || []).find((p) => p.id === modal.pid)
        const cur = avail[modal.pid]?.[modal.date]?.status || 'NO_RESPONSE'
        const dObj = dates.find((d) => d.date === modal.date)
        const sub = dObj ? fixtureSub(dObj) : ''
        return (
          <QuickAvailModal
            player={pl}
            dateLabel={`${fmtDay(modal.date)}${sub ? ' · ' + sub : ''}`}
            current={cur}
            onPick={(s) => setCell(modal.pid, modal.date, s)}
            onClose={() => setModal(null)}
          />
        )
      })()}
    </BetterSelectLayout>
  )
}
