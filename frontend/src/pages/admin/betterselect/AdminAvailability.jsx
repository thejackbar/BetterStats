import { useState, useEffect, useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { nameMatchesSearch } from '../../../lib/nameFormat'
import { useAdminNameFormat } from '../../../lib/useAdminNameFormat'
import { PbSpinner } from '../../../lib/presskit'
import { AVAILABILITY, AVAIL_ORDER } from '../../../lib/availability'
import { useAllowMaybe, useSelectConfig, useWeekNames } from '../../../lib/useAvailabilityConfig'
import { useMediaQuery } from '../../../hooks/useMediaQuery'
import { useFitHeight } from './useFitHeight'
import {
  Icon, Avatar, RoleChips, Btn, Segmented, Empty, AvailSummary, QuickAvailModal,
  playedWithinYears, RuleTags, Chip, RecencySelect, RECENCY_OPTIONS, RECENCY_OVER, recencyOf, monthsAgoISO,
} from './ui'
import { useFilters, FilterBar } from './filters'
import { normGender } from './selectionMeta'
import usePersistedState from '../../../lib/usePersistedState'
import SelfServiceLinkPanel from './SelfServiceLinkPanel'

// "Not set" finds the players whose gender nobody has recorded, so they are
// never silently dropped by Men or Women.
const GENDER_FACET_OPTS = [
  { value: 'male', label: 'Men' }, { value: 'female', label: 'Women' }, { value: 'unset', label: 'Not set' },
]
const genderKey = (g) => normGender(g) || 'unset'

const ROLE_OPTS = [
  { value: 'Batter', label: 'Batter' }, { value: 'Bowler', label: 'Bowler' },
  { value: 'All Rounder', label: 'All-rounder' }, { value: 'Wicketkeeper', label: 'Keeper' },
]

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

// The shortest the fitted matrix card may be: the date row (about 100px) plus
// room for roughly eight players.
const MATRIX_MIN_H = 440

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
function fixtureSub(dateObj, names) {
  const fxs = dateObj.fixtures || []
  if (!fxs.length) return ''
  return fxs.map((f) => {
    const opp = f.opponent_name || f.label || 'TBC'
    const prefix = f.home_away === 'AWAY' ? '@ ' : f.home_away === 'BYE' ? '' : 'vs '
    const d1d2 = f.two_day ? (f.role === 'day1' ? `${names?.w1 || 'W1'} ` : f.role === 'day2' ? `${names?.w2 || 'W2'} ` : '') : ''
    return `${d1d2}${prefix}${opp}`
  }).join(' · ')
}

export default function AdminAvailability() {
  const fmt = useAdminNameFormat()
  const { hasCapability, canEditCap } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const canEdit = canEditCap(CAP.SELECT_AVAILABILITY, CAP.MANAGE_SELECTIONS)
  const isPhone = useMediaQuery('(max-width: 1023px)')

  const [data, setData] = useState(null)
  const [avail, setAvail] = useState({}) // {playerId: {date: {status, source, note, ...}}}

  // Filters — roster + recency are quiet view controls; the rest are facets.
  // Remembered on this device so they survive moving to another screen.
  const [roster, setRoster] = usePersistedState('avail.roster', 'current', (v) => v === 'current' || v === 'all') // 'current' hides dormant/inactive; 'all' shows everyone
  // How far back a player may have last played to be listed is a club setting (Settings, Players listed).
  const years = useSelectConfig().playedYears?.availability ?? 0
  // Junior grades (per Manage Grades) are left out until asked for.
  // Whether junior grades show is a Settings choice now, not a switch on this screen.
  const [showJuniors] = usePersistedState('select.juniors', false, (v) => typeof v === 'boolean')
  // "Hasn't played since": a RECENCY_OVER + N value (last played more than N years
  // ago), 0 for off. Sits beside the club's own "played within" window, never replaces it.
  const [lapsed, setLapsed] = usePersistedState('avail.lapsed', 0, (v) => Number.isInteger(v) && (v === 0 || v > RECENCY_OVER))
  const [selectedIds, setSelectedIds] = useState(() => new Set()) // picked in any XI this round

  // Selected week (column) — drives the Pick XI handoff and single-week bulk.
  const [selDate, setSelDate] = useState(null)

  // Columns the Availability filter judges. Empty = follow the selected week;
  // otherwise the picked weeks, combined by `colMatch` (every one or any one).
  const [filterCols, setFilterCols] = useState([])
  const [colMatch, setColMatch] = usePersistedState('avail.colMatch', 'all', (v) => v === 'all' || v === 'any')

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
  const allowMaybe = useAllowMaybe()
  const weekNames = useWeekNames()
  // Switching Maybe off while it was the chosen bulk answer falls back to Available.
  useEffect(() => { if (!allowMaybe && bulkStatus === 'MAYBE') setBulkStatus('AVAILABLE') }, [allowMaybe, bulkStatus])
  const [bulkReason, setBulkReason] = useState('')
  const [applying, setApplying] = useState(false)

  // Quick-update modal: { pid, date }
  const [modal, setModal] = useState(null)

  const load = useCallback(() => {
    setData(null)
    api.bsAvailabilityMatrix({ juniors: showJuniors })
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
  }, [toast, showJuniors])

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
  // The Squad facet lists only squads worth picking: a squad someone in the shown
  // roster belongs to, not switched off, and (unless Show juniors is on) not junior.
  // The server says which names are off or junior; a name it knows nothing about stays.
  const squadOptions = useMemo(() => {
    const meta = data?.squad_meta || {}
    const inRoster = new Set()
    for (const p of data?.players || []) {
      if (roster === 'current' && !p.is_current) continue
      for (const s of p.squads || []) inRoster.add(s)
    }
    return (data?.all_squads || []).filter((s) => (
      inRoster.has(s) && meta[s]?.active !== false && (showJuniors || !meta[s]?.junior)
    ))
  }, [data, roster, showJuniors])

  // "Last played more than N years ago" choices that can still return someone:
  // narrower than the club's played-within window, and (on Current squad) inside
  // the dormancy window that roster is already limited to.
  const lapsedOptions = useMemo(() => {
    const maxYears = Math.min(
      years < 0 ? 0 : (years || Infinity),
      roster === 'current' ? (data?.dormancy_months || 24) / 12 : Infinity,
    )
    return RECENCY_OPTIONS.filter((o) => o.value > RECENCY_OVER && o.value - RECENCY_OVER < maxYears)
  }, [years, roster, data])
  const lapsedYears = lapsedOptions.some((o) => o.value === lapsed) ? lapsed : 0

  // Competitions the club has games in from here on (server: matrix `competitions`).
  // Facet values are the names, so a remembered pick still reads as a name.
  const competitions = useMemo(() => data?.competitions || [], [data])
  const compNameById = useMemo(() => Object.fromEntries(competitions.map((c) => [c.id, c.name])), [competitions])
  const compsOf = useCallback((p) => (p.competitions || []).map((id) => compNameById[id]).filter(Boolean), [compNameById])
  // Offer Gender once anyone shown has one recorded; before that it has nothing to split.
  const showGender = useMemo(() => (data?.players || []).some(
    (p) => (roster !== 'current' || p.is_current) && normGender(p.gender),
  ), [data, roster])

  const facets = useMemo(() => [
    { key: 'squad', label: 'Squad', type: 'multi', options: squadOptions.map((s) => ({ value: s, label: s })) },
    ...(competitions.length ? [
      { key: 'comp', label: 'Competition', type: 'multi', options: competitions.map((c) => ({ value: c.name, label: c.name })) },
      { key: 'notComp', label: 'Leave out', type: 'multi', options: competitions.map((c) => ({ value: c.name, label: c.name })) },
    ] : []),
    ...(showGender ? [{ key: 'gender', label: 'Gender', type: 'single', options: GENDER_FACET_OPTS }] : []),
    { key: 'avail', label: 'Availability', type: 'multi', options: AVAIL_ORDER.map((s) => ({ value: s, label: AVAILABILITY[s].label, dot: AVAILABILITY[s].cssVar })) },
    { key: 'role', label: 'Role', type: 'multi', options: ROLE_OPTS },
    { key: 'selected', label: 'Selected', type: 'single', options: [
      { value: 'selected', label: 'Selected this round' }, { value: 'unselected', label: 'Not selected' },
    ] },
  ], [squadOptions, competitions, showGender])
  const filters = useFilters(facets, { persist: 'availability' })
  const { values, search } = filters

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

  // Who's named in any saved XI for the selected week's round — powers "Selected".
  useEffect(() => {
    if (!selDate) { setSelectedIds(new Set()); return }
    let live = true
    api.bsSelectedPlayers(selDate)
      .then((d) => { if (live) setSelectedIds(new Set(d?.player_ids || [])) })
      .catch(() => { if (live) setSelectedIds(new Set()) })
    return () => { live = false }
  }, [selDate])

  // The weeks the Availability filter looks at: the picked weeks that are still
  // shown, else the selected week. A date range that hides a picked week drops it.
  const filterDates = useMemo(() => {
    const shown = new Set(dates.map((d) => d.date))
    const picked = filterCols.filter((dt) => shown.has(dt))
    if (picked.length) return picked
    return selDate && shown.has(selDate) ? [selDate] : []
  }, [dates, filterCols, selDate])

  const toggleFilterCol = (date) => setFilterCols((prev) => {
    const next = filterDates.includes(date) ? filterDates.filter((x) => x !== date) : [...filterDates, date]
    if (!next.length) return prev // keep at least one week to judge
    return dates.map((d) => d.date).filter((x) => next.includes(x))
  })

  // A player's response for the (multi-select) availability facet: matches when
  // their status for the filtered week(s) is one of the chosen statuses.
  const matchesResponse = useCallback((p) => {
    const sel = values.avail || []
    if (!sel.length || !filterDates.length) return true
    const byDate = avail[p.id] || {}
    const hit = (dt) => sel.includes(byDate[dt]?.status || 'NO_RESPONSE')
    return colMatch === 'any' ? filterDates.some(hit) : filterDates.every(hit)
  }, [values.avail, avail, filterDates, colMatch])

  const players = useMemo(() => {
    return (data?.players || []).filter((p) => {
      // Roster visibility — 'current' hides dormant (and never-played inactive).
      if (roster === 'current' && !p.is_current) return false
      if (values.squad?.length && !values.squad.some((s) => (p.squads || []).includes(s))) return false
      if (values.role?.length && !values.role.includes(p.player_role)) return false
      if (values.gender && genderKey(p.gender) !== values.gender) return false
      if (values.comp?.length && !compsOf(p).some((c) => values.comp.includes(c))) return false
      // Leave out hides a player only when every competition they are in is left out:
      // someone who also plays in another competition stays. No known competition stays too.
      if (values.notComp?.length) {
        const cs = compsOf(p)
        if (cs.length && cs.every((c) => values.notComp.includes(c))) return false
      }
      if (values.selected === 'selected' && !selectedIds.has(p.id)) return false
      if (values.selected === 'unselected' && selectedIds.has(p.id)) return false
      if (!playedWithinYears(recencyOf(p), years)) return false
      if (!playedWithinYears(p.last_played, lapsedYears)) return false
      if (search.trim() && !nameMatchesSearch(p.display_name, search)) return false
      if (!matchesResponse(p)) return false
      return true
    })
  }, [data, roster, values, years, lapsedYears, search, selectedIds, matchesResponse, compsOf])

  // Per-date player list as objects carrying a flat `availability` status, so we
  // can hand the matched-player set straight to <AvailSummary statusOf=…>.
  const colPlayers = useCallback((date) =>
    players.map((p) => ({ availability: avail[p.id]?.[date]?.status || 'NO_RESPONSE' })),
  [players, avail])
  const colInCount = useCallback((date) =>
    players.reduce((n, p) => n + ((avail[p.id]?.[date]?.status || 'NO_RESPONSE') === 'AVAILABLE' ? 1 : 0), 0),
  [players, avail])

  // "No longer dormant" (active) or dormant again. The server stamps the day; the
  // row is patched in place so the screen keeps its scroll and filters.
  const dormantCutoff = useMemo(() => monthsAgoISO(data?.dormancy_months || 24), [data?.dormancy_months])
  const setDormancy = async (p, active) => {
    if (!canEdit) return
    try {
      const r = await api.bsSetDormancy(p.id, active)
      const cleared = r?.dormancy_cleared_on || null
      setData((d) => ({
        ...d,
        players: d.players.map((x) => {
          if (x.id !== p.id) return x
          const dormant = !!x.last_played && (cleared && cleared > x.last_played ? cleared : x.last_played) < dormantCutoff
          return { ...x, dormancy_cleared_on: cleared, is_dormant: dormant && !x.is_inactive, is_current: !x.is_inactive && !dormant }
        }),
      }))
      toast.success(active ? `${p.display_name} is no longer dormant` : `${p.display_name} is dormant again`)
    } catch (e) { toast.error('Could not change that: ' + e.message) }
  }

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

  // The matrix card scrolls inside itself, so the date row (sticky top-0) stays
  // put while the players scroll. It needs a height to scroll against: measured
  // from where the card starts to the bottom of the window, like the whiteboard.
  // Only measured once the card exists (not on the spinner or empty screens).
  // `min` is the room the players are owed: on a short window the filter rows
  // above can eat everything, and a card that only fits 3 players is no use, so
  // the page scrolls a little instead (the date row still freezes in the card).
  const [matrixRef, matrixH] = useFitHeight({ enabled: !isPhone && data !== null && dates.length > 0, bottom: 20, min: MATRIX_MIN_H })

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
      {/* Self-service: players set their own availability via link + PIN */}
      {canEdit && <SelfServiceLinkPanel />}

      {/* Filter bar — shared FilterBar (facets) + quiet view controls */}
      <FilterBar
        filters={filters} facets={facets} searchPlaceholder="Search players…"
        count={players.length} total={data.players?.length} className="mb-3"
        right={(<>
          <Segmented value={roster} onChange={setRoster} sm options={[
            { value: 'current', label: 'Current squad' },
            { value: 'all', label: 'All' },
          ]} />
          {lapsedOptions.length > 0 && (
            <RecencySelect value={lapsedYears} onChange={setLapsed}
              title={roster === 'current' ? "Only players who haven't played since. Switch to All to look further back." : "Only players who haven't played since"}
              options={[{ value: 0, label: "Hasn't played: any time" }, ...lapsedOptions.map((o) => ({ ...o, group: undefined }))]} />
          )}
          <button onClick={() => setRangeOn((v) => !v)}
            className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12.5px] transition-colors ${rangeOn ? 'border-pb-accent text-pb-accent bg-pb-accent/10' : 'border-pb-hairline2 text-pb-dim hover:text-pb-text'}`}>
            <Icon name="fixtures" size={14} /> Date range {rangeOn ? '▲' : '▼'}
          </button>
        </>)}
      />

      {/* One-tap "leave out" for a competition (the Veterans, say). Only worth a row
          when there is something left to show. */}
      {competitions.length > 1 && (
        <div data-leave-out className="flex flex-wrap items-center gap-1.5 -mt-1 mb-3">
          <span className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faintest">Leave out</span>
          {competitions.map((c) => (
            <Chip key={c.id} label={c.name} active={(values.notComp || []).includes(c.name)}
              onClick={() => filters.toggle('notComp', c.name)} />
          ))}
          <span className="text-[11.5px] text-pb-faint">Hides players whose only competition is that one. Anyone who also plays in another stays.</span>
        </div>
      )}

      {/* Which week(s) the Availability filter judges. Follows the selected
          column by default; pick several to match across them. */}
      {(values.avail || []).length > 0 && (
        <div className="pb-card p-3 mb-4 flex flex-wrap items-center gap-x-3 gap-y-2">
          <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Availability for</span>
          <div className="flex flex-wrap gap-1.5">
            {dates.map((d) => (
              <Chip key={d.date} label={fmtDay(d.date)} active={filterDates.includes(d.date)}
                onClick={() => toggleFilterCol(d.date)} />
            ))}
          </div>
          {filterDates.length > 1 && (
            <Segmented sm value={colMatch} onChange={setColMatch} options={[
              { value: 'all', label: 'Every week' }, { value: 'any', label: 'Any week' },
            ]} />
          )}
          {filterCols.length > 0 && (
            <Btn variant="ghost" sm onClick={() => setFilterCols([])}>Use selected week</Btn>
          )}
          <span className="basis-full text-[11px] text-pb-faint">
            {filterCols.length === 0
              ? 'Following the selected week. Click a week header to change it, or pick several weeks here.'
              : `Matching ${filterDates.length === 1 ? 'this week only' : colMatch === 'all' ? 'players who fit in every picked week' : 'players who fit in any picked week'}.`}
          </span>
        </div>
      )}

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
            options={AVAIL_ORDER.filter((s) => allowMaybe || s !== 'MAYBE').map((s) => ({ value: s, label: AVAILABILITY[s].short }))} />
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
      <div ref={matrixRef} data-avail-matrix data-fit={matrixH != null ? 'on' : 'off'} className="pb-card overflow-auto"
        style={matrixH != null ? { height: matrixH } : undefined}>
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
                const sub = fixtureSub(d, weekNames)
                return (
                  <th key={d.date} onClick={() => { setSelDate(d.date); setFilterCols([]) }}
                    className="sticky top-0 z-20 px-3 py-2 border-b border-l pb-hairline text-center cursor-pointer"
                    style={{
                      minWidth: 140,
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
                    {sub && <div className="text-[10px] text-pb-faint truncate" title={sub} style={{ maxWidth: 124, margin: '1px auto 0' }}>{sub}</div>}
                    <div className="mt-1.5"><AvailSummary players={colPlayers(d.date)} inline hideTotal /></div>
                    {/* The date row is frozen above the players, so it stays short:
                        "N in" and, on the picked week, a small Pick XI beside it. */}
                    <div className="mt-1 flex items-center justify-center gap-2 font-mono text-[10px] text-pb-dim" style={{ minHeight: 22 }}>
                      <span><b className="text-pb-accent">{colInCount(d.date)}</b> in</span>
                      {sel && (
                        <Btn variant="primary" sm data-pick-xi className="!px-2 !py-1 !text-[11px] !gap-1"
                          onClick={(e) => { e.stopPropagation(); navigate('/admin/betterselect/selection') }}>
                          Pick XI <Icon name="arrow" size={11} />
                        </Btn>
                      )}
                    </div>
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {players.length === 0 && (
              <tr>
                <td colSpan={dates.length + 1} className="border-t pb-hairline px-4 py-8 text-center">
                  <Empty>No players match these filters. Try clearing the search or response filter, picking another week for it, or switching to “All”.</Empty>
                </td>
              </tr>
            )}
            {players.map((p) => (
              <tr key={p.id} style={{ background: selected.has(p.id) ? 'color-mix(in srgb, var(--pb-accent) 5%, transparent)' : 'transparent' }}>
                <td className="sticky left-0 z-10 px-4 py-1 border-b pb-hairline"
                  style={{ background: selected.has(p.id) ? 'var(--pb-surface2)' : 'var(--pb-surface)' }}>
                  <div className="flex items-center gap-2.5">
                    {canEdit && (
                      <input type="checkbox" checked={selected.has(p.id)} onChange={() => toggleSel(p.id)}
                        className="accent-pb-accent" style={{ width: 15, height: 15 }} />
                    )}
                    <Avatar player={p} size={28} />
                    <span className="text-sm font-medium truncate">{fmt(p.display_name)}</span>
                    <RuleTags player={p} />
                    {p.is_dormant && <span className="font-mono text-[9px] text-amber-300/80 uppercase shrink-0" title={`Dormant${p.last_played ? ' since ' + fmtYear(p.last_played) : ''}`}>dormant</span>}
                    {canEdit && p.is_dormant && (
                      <button type="button" onClick={() => setDormancy(p, true)} data-not-dormant
                        title="No longer dormant: they will be listed in availability, the squads board and selection"
                        className="shrink-0 rounded border border-pb-hairline2 px-1.5 py-0.5 text-[10px] font-display font-semibold text-pb-accent hover:bg-pb-accent/10 [@media(pointer:coarse)]:px-2.5 [@media(pointer:coarse)]:py-2">
                        Not dormant
                      </button>
                    )}
                    {!p.is_dormant && !p.is_inactive && p.dormancy_cleared_on && p.last_played && p.last_played < dormantCutoff && (
                      <>
                        <span className="font-mono text-[9px] text-pb-accent/80 uppercase shrink-0" title={`Marked no longer dormant on ${p.dormancy_cleared_on}. Last game ${p.last_played}.`}>returning</span>
                        {canEdit && (
                          <button type="button" onClick={() => setDormancy(p, false)} data-dormant-again
                            title="Mark dormant again"
                            className="shrink-0 text-[10px] text-pb-faint underline underline-offset-2 hover:text-pb-accent [@media(pointer:coarse)]:px-2 [@media(pointer:coarse)]:py-2">
                            undo
                          </button>
                        )}
                      </>
                    )}
                    {p.is_inactive && <span className="font-mono text-[9px] text-pb-red/80 uppercase shrink-0" title="Marked inactive">inactive</span>}
                  </div>
                </td>
                {dates.map((d) => {
                  const cell = avail[p.id]?.[d.date]
                  const st = cell?.status || 'NO_RESPONSE'
                  const meta = AVAILABILITY[st]
                  const fromPeriod = cell?.source === 'period'
                  const fromSelf = cell?.source === 'self'
                  const empty = st === 'NO_RESPONSE'
                  const sel = d.date === selDate
                  const title = fromPeriod
                    ? `${meta.label}${cell.note ? ' · ' + cell.note : ''} — from a period${canEdit ? ' (click to override)' : ''}`
                    : fromSelf
                      ? `${meta.label}${cell.note ? ' · ' + cell.note : ''} — set by the player${canEdit ? ' (click to override)' : ''}`
                      : meta.label
                  return (
                    <td key={d.date} className="text-center border-b border-l pb-hairline"
                      style={{
                        padding: '3px 0',
                        background: sel ? 'color-mix(in srgb, var(--pb-accent) 4%, transparent)' : 'transparent',
                      }}>
                      <span className="relative inline-block">
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
                        {/* A player-reported answer gets a small corner dot so the
                            admin can tell self-service cells from ones they set. */}
                        {fromSelf && (
                          <span title="Set by the player" style={{
                            position: 'absolute', top: -1, right: -1, width: 7, height: 7,
                            borderRadius: '50%', background: 'var(--pb-accent)',
                            border: '1.5px solid var(--pb-surface)',
                          }} />
                        )}
                      </span>
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
        const sub = dObj ? fixtureSub(dObj, weekNames) : ''
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
