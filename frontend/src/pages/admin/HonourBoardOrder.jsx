import { useState, useEffect, useMemo, useCallback } from 'react'
import { api } from '../../lib/api'
import { Label, PbSpinner } from '../../lib/presskit'

// The order a club's public Honour Board lists its groups, roles and people in.
// The server sends every group, role and person in the order the club has them
// now (the standard order until a layout is saved) and takes the whole order
// back on Save. Nothing here changes who held what, only the order it is read in.
//
// Arrow buttons rather than drag and drop: this is used on a phone as often as
// a laptop, and a drag list is the part of a screen that is hardest to use there.

const NEWEST = 'newest'
const OLDEST = 'oldest'
const MANUAL = 'manual'

const SORTS = [
  { id: NEWEST, label: 'Newest first', hint: 'Most recent term first. This is the standard order.' },
  { id: OLDEST, label: 'Oldest first', hint: 'The first term each person started goes first.' },
  { id: MANUAL, label: 'Manual', hint: 'You set the order for everyone on this list.' },
]

const boardKey = (group, role) => `${group}\u0001${role}`
const lc = (s) => (s || '').trim().toLowerCase().replace(/\s+/g, ' ')

// The server's own rule, so the list re-sorts on screen the moment a sort or an
// arrow changes. A person with no year is last in both season orders. `order`
// is the club's position for each person; it only breaks ties between people
// on the same season, except under Manual where it is the whole order.
export function sortHolders(holders, mode, order) {
  const rank = new Map(order.map((k, i) => [k, i]))
  const placed = (h) => (rank.has(h.key) ? rank.get(h.key) : order.length)
  const end = (h) => h.to_year || h.from_year || 0
  const byName = (a, b) => (a.name || '').localeCompare(b.name || '')
  const list = [...holders]
  list.sort((a, b) => {
    if (mode === MANUAL) {
      return placed(a) - placed(b)
        || (a.from_year == null) - (b.from_year == null)
        || end(b) - end(a)
        || byName(a, b)
    }
    const noYear = (a.from_year == null) - (b.from_year == null)
    if (noYear) return noYear
    const season = mode === OLDEST ? (a.from_year || 0) - (b.from_year || 0) : end(b) - end(a)
    return season || placed(a) - placed(b) || byName(a, b)
  })
  return list
}

// Two people can swap places under a season order only when they share the season
// the order is read by.
function sameSeason(a, b, mode) {
  if (!a || !b || a.from_year == null || b.from_year == null) return false
  return mode === OLDEST ? a.from_year === b.from_year : (a.to_year || a.from_year) === (b.to_year || b.from_year)
}

function Arrows({ label, onUp, onDown, canUp, canDown }) {
  const cls = 'w-8 h-8 grid place-items-center rounded border pb-hairline bg-pb-surface text-pb-dim text-xs transition-colors hover:text-pb-text hover:border-pb-accent disabled:opacity-30 disabled:hover:text-pb-dim disabled:hover:border-transparent'
  return (
    <span className="flex gap-1 shrink-0">
      <button type="button" className={cls} disabled={!canUp} onClick={onUp} aria-label={`Move ${label} up`}>↑</button>
      <button type="button" className={cls} disabled={!canDown} onClick={onDown} aria-label={`Move ${label} down`}>↓</button>
    </span>
  )
}

function moved(list, i, delta) {
  const j = i + delta
  if (j < 0 || j >= list.length) return list
  const next = [...list]
  ;[next[i], next[j]] = [next[j], next[i]]
  return next
}

export default function HonourBoardOrder({ slug }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)

  const [groupOrder, setGroupOrder] = useState([])
  const [roleOrder, setRoleOrder] = useState({})
  const [people, setPeople] = useState({})
  const [touched, setTouched] = useState(() => new Set())
  const [sel, setSel] = useState(null)

  const adopt = useCallback((view) => {
    setData(view)
    setGroupOrder(view.groups.map(g => g.group))
    setRoleOrder(Object.fromEntries(view.groups.map(g => [g.group, g.boards.map(b => b.role)])))
    const next = {}
    for (const g of view.groups) {
      for (const b of g.boards) {
        next[boardKey(g.group, b.role)] = { sort: b.sort || NEWEST, order: b.holders.map(h => h.key) }
      }
    }
    setPeople(next)
    setTouched(new Set())
    setDirty(false)
  }, [])

  useEffect(() => {
    api.adminGetHonourBoardLayout().then(adopt).catch(e => setError(e.message || 'Could not load the Honour Board order.'))
  }, [adopt])

  // Every board and the people on it, by key, straight from the server.
  const boards = useMemo(() => {
    const m = new Map()
    for (const g of data?.groups || []) {
      for (const b of g.boards) m.set(boardKey(g.group, b.role), { group: g.group, ...b })
    }
    return m
  }, [data])

  // The order the club has saved for a board, so a board it already placed
  // people on is sent back even when this visit never touched it.
  const hadSaved = useMemo(() => {
    const out = new Set()
    for (const [g, byRole] of Object.entries(data?.layout?.holders || {})) {
      for (const r of Object.keys(byRole)) out.add(boardKey(lc(g), lc(r)))
    }
    return out
  }, [data])

  const flat = useMemo(() => groupOrder.flatMap(g => (roleOrder[g] || []).map(r => ({ group: g, role: r }))), [groupOrder, roleOrder])
  const current = sel && boards.has(sel) ? sel : (flat[0] ? boardKey(flat[0].group, flat[0].role) : null)
  const board = current ? boards.get(current) : null
  const setting = current ? people[current] : null

  const shown = useMemo(() => {
    if (!board || !setting) return []
    return sortHolders(board.holders, setting.sort, setting.order)
  }, [board, setting])

  const change = (fn) => { fn(); setDirty(true); setNotice(null) }

  const moveGroup = (i, d) => change(() => setGroupOrder(o => moved(o, i, d)))
  const moveRole = (group, i, d) => change(() => setRoleOrder(r => ({ ...r, [group]: moved(r[group] || [], i, d) })))
  const setSort = (sort) => change(() => {
    setPeople(p => ({ ...p, [current]: { ...p[current], sort } }))
    setTouched(t => new Set(t).add(current))
  })
  const movePerson = (i, d) => change(() => {
    const keys = shown.map(h => h.key)
    setPeople(p => ({ ...p, [current]: { ...p[current], order: moved(keys, i, d) } }))
    setTouched(t => new Set(t).add(current))
  })

  const canMovePerson = (i, d) => {
    const other = shown[i + d]
    if (!other) return false
    return setting.sort === MANUAL || sameSeason(shown[i], other, setting.sort)
  }

  const payload = () => {
    const holders = {}
    for (const { group, role } of flat) {
      const k = boardKey(group, role)
      const s = people[k]
      if (!s) continue
      const saved = hadSaved.has(boardKey(lc(group), lc(role)))
      if (s.sort === NEWEST && !touched.has(k) && !saved) continue
      holders[group] = { ...(holders[group] || {}), [role]: { sort: s.sort, order: s.order } }
    }
    return { groups: groupOrder, roles: roleOrder, holders }
  }

  const save = async () => {
    setSaving(true); setError(null); setNotice(null)
    try {
      adopt(await api.adminPutHonourBoardLayout(payload()))
      setNotice('Saved. Your public Honour Board now lists things in this order.')
    } catch (e) {
      setError(e.message || 'Could not save the order.')
    } finally {
      setSaving(false)
    }
  }

  const reset = async () => {
    if (!window.confirm('Go back to the standard order? Your own order for groups, roles and people will be cleared. The honours themselves are not touched.')) return
    setSaving(true); setError(null); setNotice(null)
    try {
      adopt(await api.adminPutHonourBoardLayout({}))
      setNotice('Back to the standard order.')
    } catch (e) {
      setError(e.message || 'Could not reset the order.')
    } finally {
      setSaving(false)
    }
  }

  if (!data && !error) return <PbSpinner message="Loading the Honour Board order…" />
  if (!data) return <div className="p-3 bg-pb-surface2 border border-pb-red rounded font-mono text-[11px] text-pb-red">{error}</div>

  if (flat.length === 0) {
    return (
      <div className="pb-card p-6 text-sm text-pb-dim">
        No Office Bearer or Life Membership awards are recorded yet, so there is nothing to put in order.
        Record them under Admin, Awards and they appear here.
      </div>
    )
  }

  const rowCls = 'flex items-center gap-2.5 px-3 py-2 rounded border pb-hairline bg-pb-surface2 mb-1.5'
  const sortHint = SORTS.find(s => s.id === setting?.sort)?.hint

  return (
    <div>
      <div className="mb-4 px-3.5 py-2.5 rounded text-[12.5px] text-pb-dim"
           style={{ background: 'color-mix(in srgb, var(--pb-accent) 8%, transparent)', border: '1px solid color-mix(in srgb, var(--pb-accent) 25%, transparent)' }}>
        This sets the order on your public Honour Board. Until you save a change, every group, role and person
        is listed in the standard order. Anything you record later is added after what you have placed.
      </div>

      {error && (
        <div className="mb-4 p-3 bg-pb-surface2 border border-pb-red rounded font-mono text-[11px] text-pb-red">
          {error} <button onClick={() => setError(null)} className="ml-2 underline">dismiss</button>
        </div>
      )}
      {notice && (
        <div className="mb-4 p-3 bg-pb-surface2 border pb-hairline rounded text-[12.5px] text-pb-accent" role="status">{notice}</div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="hbo-groups" className="min-w-0">
          <div id="hbo-groups" className="mb-2"><Label>1 · Groups and roles</Label></div>
          {groupOrder.map((g, gi) => (
            <div key={g}>
              <div className={`${rowCls} font-semibold`}
                   style={{ background: 'color-mix(in srgb, var(--pb-accent) 8%, var(--pb-surface2))' }}>
                <span className="min-w-0 flex-1 truncate">{g}</span>
                <span className="font-mono text-[11px] text-pb-faint">{(roleOrder[g] || []).length}</span>
                <Arrows label={g} canUp={gi > 0} canDown={gi < groupOrder.length - 1}
                        onUp={() => moveGroup(gi, -1)} onDown={() => moveGroup(gi, 1)} />
              </div>
              {(roleOrder[g] || []).map((r, ri, arr) => (
                <div key={r} className={`${rowCls} ml-5 sm:ml-7`}>
                  <span className="min-w-0 flex-1 truncate">{r}</span>
                  <Arrows label={r} canUp={ri > 0} canDown={ri < arr.length - 1}
                          onUp={() => moveRole(g, ri, -1)} onDown={() => moveRole(g, ri, 1)} />
                </div>
              ))}
            </div>
          ))}
        </section>

        <section aria-labelledby="hbo-people" className="min-w-0">
          <div id="hbo-people" className="mb-2"><Label>2 · People under a role</Label></div>
          <label htmlFor="hbo-board" className="sr-only">Role</label>
          <select id="hbo-board" value={current || ''} onChange={e => setSel(e.target.value)}
                  className="w-full mb-3 bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent">
            {flat.map(({ group, role }) => {
              const k = boardKey(group, role)
              return <option key={k} value={k}>{group}: {role} ({boards.get(k)?.holder_count ?? 0})</option>
            })}
          </select>

          <div className="inline-flex flex-wrap border pb-hairline rounded overflow-hidden mb-2" role="group" aria-label="Sort order">
            {SORTS.map(s => (
              <button key={s.id} type="button" onClick={() => setSort(s.id)} aria-pressed={setting.sort === s.id}
                      className={`px-3 py-1.5 text-xs transition-colors ${setting.sort === s.id ? 'text-pb-accent' : 'text-pb-dim bg-pb-surface hover:text-pb-text'}`}
                      style={setting.sort === s.id ? { background: 'color-mix(in srgb, var(--pb-accent) 18%, transparent)' } : undefined}>
                {s.label}
              </button>
            ))}
          </div>
          <p className="text-xs text-pb-faint mb-3">
            {sortHint}{setting.sort !== MANUAL && ' People on the same season can be moved up and down; everyone else stays in season order.'}
          </p>

          {shown.map((h, i) => {
            const tied = setting.sort !== MANUAL && (canMovePerson(i, -1) || canMovePerson(i, 1))
            return (
              <div key={h.key} className={rowCls}
                   style={tied ? { borderColor: 'color-mix(in srgb, var(--pb-accent) 40%, var(--pb-hairline))' } : undefined}>
                <span className="font-mono text-[11px] text-pb-faint w-10 shrink-0">{h.from_year ?? '—'}</span>
                <span className="min-w-0 flex-1 truncate">{h.name}</span>
                <Arrows label={h.name} canUp={canMovePerson(i, -1)} canDown={canMovePerson(i, 1)}
                        onUp={() => movePerson(i, -1)} onDown={() => movePerson(i, 1)} />
              </div>
            )
          })}
          {setting.sort !== MANUAL && shown.some((_, i) => canMovePerson(i, -1) || canMovePerson(i, 1)) && (
            <p className="text-xs text-pb-faint mt-2">Outlined rows share a season, so the order between them is yours to set.</p>
          )}
        </section>
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-2">
        <button type="button" onClick={save} disabled={!dirty || saving}
                className="px-4 py-2 rounded font-mono text-[11px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-40"
                style={{ background: 'var(--pb-accent)' }}>
          {saving ? 'Saving…' : 'Save order'}
        </button>
        {slug && (
          <a href={`/${slug}/honour-board`} target="_blank" rel="noreferrer"
             className="px-4 py-2 rounded font-mono text-[11px] tracking-wide2 border pb-hairline text-pb-dim hover:text-pb-text transition-colors">
            View Honour Board
          </a>
        )}
        <button type="button" onClick={reset} disabled={saving || !data.customised}
                className="px-4 py-2 rounded font-mono text-[11px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text transition-colors disabled:opacity-40 sm:ml-auto">
          Reset to standard order
        </button>
        {dirty && <span className="text-xs text-pb-faint w-full sm:w-auto">You have changes that are not saved yet.</span>}
      </div>
    </div>
  )
}
