// BetterSelect → Audit History. Every change to a player in selection,
// availability and squads: who made it, when, and what changed. Searchable,
// filterable by area, action, who, squad and date, and exported as a CSV with
// the same filters. Read-only: nothing here edits the trail.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { PbSpinner } from '../../../lib/presskit'
import usePersistedState from '../../../lib/usePersistedState'
import { Icon, Btn, Search, Chip, Empty } from './ui'

const PAGE = 100
const AREAS = [['selection', 'Selection'], ['availability', 'Availability'], ['squads', 'Squads']]
const TONE = { selection: 'var(--pb-accent)', availability: 'var(--pb-amber)', squads: 'var(--pb-positive)' }
const tz = () => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone } catch { return undefined } }

const fmtDate = (iso) => {
  if (!iso) return ''
  try { return new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }) } catch { return iso }
}
const fmtTime = (t) => (t || '').slice(0, 5)

export default function AuditHistory() {
  const toast = useToast()
  const [q, setQ] = useState('')
  const [debounced, setDebounced] = useState('')
  const [areas, setAreas] = useState([])               // [] = all
  const [actions, setActions] = useState([])
  const [who, setWho] = useState('')
  const [team, setTeam] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [facets, setFacets] = useState({ users: [], teams: [], actions: [] })
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [more, setMore] = useState(false)
  const [open, setOpen] = usePersistedState('audit.filtersOpen', true, (v) => typeof v === 'boolean')
  const seq = useRef(0)

  useEffect(() => { const t = setTimeout(() => setDebounced(q), 250); return () => clearTimeout(t) }, [q])
  useEffect(() => { api.bsAuditFacets().then(setFacets).catch(() => {}) }, [])

  const filters = useMemo(() => ({
    q: debounced.trim() || undefined,
    area: areas.length === 1 ? areas[0] : undefined,
    action: actions.length ? actions.join(',') : undefined,
    user: who || undefined, team: team || undefined,
    date_from: from || undefined, date_to: to || undefined, tz: tz(),
  }), [debounced, areas, actions, who, team, from, to])

  // Two areas ticked is "either of them": the server takes one, so the second is
  // applied to what comes back (the page count stays honest because it is one query per change).
  const matchesAreas = useCallback((e) => areas.length < 2 || areas.includes(e.area), [areas])

  const load = useCallback(async (offset = 0) => {
    const mine = ++seq.current
    if (offset === 0) setLoading(true); else setMore(true)
    try {
      const r = await api.bsAuditEvents({ ...filters, limit: PAGE, offset })
      if (mine !== seq.current) return
      setRows((prev) => (offset === 0 ? r.events : [...prev, ...r.events]))
      setTotal(r.total)
    } catch (e) {
      if (mine === seq.current) { toast.error(e.message); if (offset === 0) { setRows([]); setTotal(0) } }
    } finally {
      if (mine === seq.current) { setLoading(false); setMore(false) }
    }
  }, [filters])  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load(0) }, [load])

  const shown = rows.filter(matchesAreas)
  const toggle = (list, setList, v) => setList(list.includes(v) ? list.filter((x) => x !== v) : [...list, v])
  const anyFilter = !!(debounced || areas.length || actions.length || who || team || from || to)
  const clear = () => { setQ(''); setAreas([]); setActions([]); setWho(''); setTeam(''); setFrom(''); setTo('') }

  const [exporting, setExporting] = useState(false)
  const exportCsv = async () => {
    setExporting(true)
    try { await api.bsAuditExport(filters) } catch (e) { toast.error('Export failed: ' + e.message) } finally { setExporting(false) }
  }

  // Group by day so a long list scans like a diary.
  const days = useMemo(() => {
    const out = []
    shown.forEach((e) => {
      const last = out[out.length - 1]
      if (last && last.date === e.local_date) last.items.push(e); else out.push({ date: e.local_date, items: [e] })
    })
    return out
  }, [shown])

  const actions_ = (
    <Btn variant="soft" sm icon="download" onClick={exportCsv} disabled={exporting || !total} data-audit-export>
      {exporting ? 'Exporting…' : 'Export CSV'}
    </Btn>
  )

  return (
    <BetterSelectLayout title="Audit History" actions={actions_}>
      <p className="text-[12.5px] text-pb-faint mb-3 max-w-3xl">
        Every change to a player in selection, availability and squads, with who made it and when. Players moving up and down the batting order, captain and wicket-keeper changes, squad moves and every recorded answer are here. The export uses the filters below.
      </p>

      <div className="pb-card p-3 mb-3 flex flex-col gap-3" data-audit-filters>
        <div className="flex flex-wrap items-center gap-2">
          <Search value={q} onChange={setQ} placeholder="Search players, people, squads, games…" className="flex-1 min-w-[220px]" />
          <Btn variant="ghost" sm icon="filter" onClick={() => setOpen(!open)} aria-expanded={open}>{open ? 'Hide filters' : 'Filters'}</Btn>
          {anyFilter && <Btn variant="ghost" sm onClick={clear} data-audit-clear>Clear</Btn>}
        </div>
        {open && (
          <>
            <div className="flex flex-wrap items-center gap-1.5" data-audit-areas>
              <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mr-1">Area</span>
              {AREAS.map(([k, l]) => <Chip key={k} label={l} dot={TONE[k]} active={areas.includes(k)} onClick={() => toggle(areas, setAreas, k)} />)}
            </div>
            <div className="flex flex-wrap items-center gap-1.5" data-audit-actions>
              <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mr-1">What</span>
              {facets.actions.filter((a) => !areas.length || areas.some((ar) => ACTION_AREA[a.value] === ar)).map((a) => (
                <Chip key={a.value} label={a.label} active={actions.includes(a.value)} onClick={() => toggle(actions, setActions, a.value)} />
              ))}
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1 text-[11px] text-pb-faint">Changed by
                <select value={who} onChange={(e) => setWho(e.target.value)} aria-label="Changed by" data-audit-who
                  className="bg-pb-surface2 border border-pb-hairline rounded-md text-[13px] px-2 py-1.5 text-pb-text min-w-[150px]">
                  <option value="">Anyone</option>
                  {facets.users.map((u) => <option key={u} value={u}>{u}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-[11px] text-pb-faint">Squad or team
                <select value={team} onChange={(e) => setTeam(e.target.value)} aria-label="Squad or team" data-audit-team
                  className="bg-pb-surface2 border border-pb-hairline rounded-md text-[13px] px-2 py-1.5 text-pb-text min-w-[150px]">
                  <option value="">All</option>
                  {facets.teams.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-[11px] text-pb-faint">From
                <input type="date" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} aria-label="From date" data-audit-from
                  className="bg-pb-surface2 border border-pb-hairline rounded-md text-[13px] px-2 py-1 text-pb-text" />
              </label>
              <label className="flex flex-col gap-1 text-[11px] text-pb-faint">To
                <input type="date" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} aria-label="To date" data-audit-to
                  className="bg-pb-surface2 border border-pb-hairline rounded-md text-[13px] px-2 py-1 text-pb-text" />
              </label>
            </div>
          </>
        )}
      </div>

      <div className="text-[12px] text-pb-faint mb-2" data-audit-count>
        {loading ? 'Loading…' : `${total.toLocaleString()} change${total === 1 ? '' : 's'}${anyFilter ? ' match these filters' : ''}`}
      </div>

      {loading && !rows.length ? <PbSpinner /> : !shown.length ? (
        <Empty className="pb-card p-6 text-center">{anyFilter ? 'Nothing matches these filters.' : 'Nothing has been recorded yet. Changes made from now on appear here.'}</Empty>
      ) : (
        <div className="flex flex-col gap-4" data-audit-list>
          {days.map((d) => (
            <section key={d.date}>
              <h3 className="font-mono text-[11px] uppercase tracking-wide2 text-pb-faint mb-1.5 sticky top-0 bg-pb-bg/90 backdrop-blur py-1">{fmtDate(d.date)}</h3>
              <div className="pb-card divide-y divide-pb-hairline">
                {d.items.map((e) => (
                  <div key={e.id} data-audit-row data-audit-action={e.action} className="flex items-start gap-3 px-3 py-2.5">
                    <span className="font-mono text-[11.5px] text-pb-dim w-[44px] shrink-0 pt-0.5 pb-num">{fmtTime(e.local_time)}</span>
                    <span className="w-2 h-2 rounded-full shrink-0 mt-[7px]" style={{ background: TONE[e.area] }} title={e.area} />
                    <div className="min-w-0 flex-1">
                      <div className="text-[13.5px] text-pb-text break-words">{e.summary}</div>
                      <div className="text-[11.5px] text-pb-faint mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5">
                        <span><Icon name="player" size={11} /> {e.by}{e.via === 'player link' ? ' (their own link)' : ''}</span>
                        <span>{e.action_label}</span>
                        {e.team && <span>{e.team}</span>}
                        {e.game && <span>{e.game}</span>}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ))}
          {rows.length < total && (
            <div className="text-center">
              <Btn variant="ghost" sm onClick={() => load(rows.length)} disabled={more} data-audit-more>{more ? 'Loading…' : `Show ${Math.min(PAGE, total - rows.length)} more`}</Btn>
            </div>
          )}
        </div>
      )}
    </BetterSelectLayout>
  )
}

// Which area each action belongs to, so the "What" chips follow the Area chips.
const ACTION_AREA = {
  added_to_xi: 'selection', removed_from_xi: 'selection', batting_order_changed: 'selection', made_captain: 'selection',
  removed_captain: 'selection', made_keeper: 'selection', removed_keeper: 'selection', side_confirmed: 'selection',
  side_locked: 'selection', side_unlocked: 'selection', called_up_out: 'selection', restored_to_board: 'selection',
  availability_set: 'availability', availability_period_added: 'availability', availability_period_removed: 'availability',
  added_to_squad: 'squads', removed_from_squad: 'squads', moved_squad: 'squads', squad_created: 'squads', squad_updated: 'squads', squad_deleted: 'squads',
}
