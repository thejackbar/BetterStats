import { useState, useEffect, useCallback, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { nameMatchesSearch } from '../../../lib/nameFormat'
import { PbSpinner, Btn } from '../../../lib/presskit'

const AVAIL_META = {
  AVAILABLE:   { g: '✓', cls: 'text-pb-accent', label: 'Available' },
  UNAVAILABLE: { g: '✕', cls: 'text-pb-red', label: 'Unavailable' },
  MAYBE:       { g: '?', cls: 'text-amber-300', label: 'Maybe' },
  NO_RESPONSE: { g: '–', cls: 'text-pb-faintest', label: 'No response' },
}
// Sort the pool so the most pickable players float up.
const AVAIL_RANK = { AVAILABLE: 0, MAYBE: 1, NO_RESPONSE: 2, UNAVAILABLE: 3 }

function fmtFixture(fx) {
  if (!fx) return ''
  const opp = fx.opponent_name || fx.label || 'TBC'
  const prefix = fx.home_away === 'AWAY' ? '@ ' : 'vs '
  return prefix + opp
}

export default function AdminSelection() {
  const { fixtureId } = useParams()
  const { hasCapability } = useAuth()
  const toast = useToast()
  const canEdit = hasCapability(CAP.MANAGE_SELECTIONS)

  const [data, setData] = useState(null)
  // selection state: ordered array of { player_id, is_captain, is_wicket_keeper }
  const [picked, setPicked] = useState([])
  const [search, setSearch] = useState('')
  const [hideUnavailable, setHideUnavailable] = useState(true)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)

  const load = useCallback(() => {
    setData(null)
    api.bsGetSelection(fixtureId)
      .then(d => {
        setData(d)
        setPicked((d.lineup || []).map(l => ({
          player_id: l.player_id, is_captain: l.is_captain, is_wicket_keeper: l.is_wicket_keeper,
        })))
        setDirty(false)
      })
      .catch(e => { toast.error(e.message); setData({ pool: [], lineup: [], fixture: null }) })
  }, [fixtureId, toast])

  useEffect(() => { load() }, [load])

  const poolById = useMemo(() => {
    const m = {}
    ;(data?.pool || []).forEach(p => { m[p.id] = p })
    return m
  }, [data])

  const pickedIds = useMemo(() => new Set(picked.map(p => p.player_id)), [picked])

  // Available pool = not-yet-picked players, filtered + sorted.
  const available = useMemo(() => {
    let list = (data?.pool || []).filter(p => !pickedIds.has(p.id))
    if (hideUnavailable) list = list.filter(p => p.availability !== 'UNAVAILABLE')
    if (search.trim()) list = list.filter(p => nameMatchesSearch(p.display_name, search))
    return list.sort((a, b) => {
      const ra = AVAIL_RANK[a.availability] ?? 9, rb = AVAIL_RANK[b.availability] ?? 9
      if (ra !== rb) return ra - rb
      return a.display_name.localeCompare(b.display_name)
    })
  }, [data, pickedIds, hideUnavailable, search])

  const add = (p) => {
    if (!canEdit) return
    setPicked(prev => [...prev, { player_id: p.id, is_captain: false, is_wicket_keeper: false }])
    setDirty(true)
  }
  const remove = (pid) => {
    setPicked(prev => prev.filter(p => p.player_id !== pid))
    setDirty(true)
  }
  const move = (idx, dir) => {
    setPicked(prev => {
      const next = [...prev]
      const j = idx + dir
      if (j < 0 || j >= next.length) return prev
      ;[next[idx], next[j]] = [next[j], next[idx]]
      return next
    })
    setDirty(true)
  }
  // Captain is exclusive; WK is exclusive.
  const toggleFlag = (pid, flag) => {
    setPicked(prev => prev.map(p => {
      if (p.player_id === pid) return { ...p, [flag]: !p[flag] }
      if (flag === 'is_captain') return { ...p, is_captain: false } // only one C
      if (flag === 'is_wicket_keeper') return { ...p, is_wicket_keeper: false } // only one WK
      return p
    }))
    setDirty(true)
  }

  const save = async () => {
    setSaving(true)
    try {
      const players = picked.map((p, i) => ({
        player_id: p.player_id,
        batting_order: i + 1,
        is_captain: p.is_captain,
        is_wicket_keeper: p.is_wicket_keeper,
      }))
      const r = await api.bsSetSelection(fixtureId, players)
      toast.success(`Saved ${r.count} player${r.count === 1 ? '' : 's'}`)
      setDirty(false)
    } catch (e) { toast.error('Save failed: ' + e.message) }
    finally { setSaving(false) }
  }

  if (data === null) return <BetterSelectLayout title="Selection"><PbSpinner message="Loading selection…" /></BetterSelectLayout>

  const fx = data.fixture
  const actions = canEdit && (
    <Btn primary onClick={save} disabled={saving || !dirty}>
      {saving ? 'Saving…' : dirty ? `Save XI (${picked.length})` : 'Saved'}
    </Btn>
  )

  return (
    <BetterSelectLayout title="Selection" actions={actions}>
      <div className="mb-3 flex items-center gap-2 flex-wrap">
        <Link to="/admin/betterselect/fixtures" className="text-pb-faint hover:text-pb-text text-xs">← Fixtures</Link>
        <span className="text-pb-faintest">/</span>
        <span className="font-medium text-sm">{fmtFixture(fx)}</span>
        {fx?.played_on && <span className="font-mono text-[11px] text-pb-faint">{fx.played_on}</span>}
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        {/* Available pool */}
        <div className="pb-card overflow-hidden flex flex-col">
          <div className="px-4 py-3 border-b pb-hairline">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-mono text-[11px] uppercase tracking-wide2 text-pb-faint">Available · {available.length}</h3>
              <label className="flex items-center gap-1.5 text-[11px] text-pb-faint cursor-pointer">
                <input type="checkbox" checked={hideUnavailable} onChange={e => setHideUnavailable(e.target.checked)} className="accent-pb-accent" />
                Hide unavailable
              </label>
            </div>
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search players…"
              className="w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent" />
          </div>
          <div className="overflow-auto max-h-[60vh]">
            {available.length === 0 && <div className="px-4 py-6 text-center text-pb-faint text-sm">No players to show.</div>}
            {available.map(p => {
              const m = AVAIL_META[p.availability] || AVAIL_META.NO_RESPONSE
              return (
                <button key={p.id} onClick={() => add(p)} disabled={!canEdit}
                  className="w-full text-left px-4 py-2 border-t pb-hairline hover:bg-pb-surface2/50 flex items-center justify-between gap-2 disabled:cursor-default">
                  <span className="min-w-0">
                    <span className="text-sm">{p.display_name}</span>
                    {p.player_role && <span className="ml-1.5 font-mono text-[9px] text-pb-faintest uppercase">{p.player_role}</span>}
                    {p.is_dormant && <span className="ml-1.5 font-mono text-[9px] text-amber-300/70 uppercase">dormant</span>}
                    {p.clash?.length > 0 && <span className="ml-1.5 font-mono text-[9px] text-pb-red/80" title={`Also picked: ${p.clash.join(', ')}`}>⚠ clash</span>}
                    {p.squads?.length > 0 && <span className="block text-[10px] text-pb-faintest truncate">{p.squads.join(' · ')}</span>}
                  </span>
                  <span className={`font-mono text-sm shrink-0 ${m.cls}`} title={m.label}>{m.g}</span>
                </button>
              )
            })}
          </div>
        </div>

        {/* Selected XI */}
        <div className="pb-card overflow-hidden flex flex-col">
          <div className="px-4 py-3 border-b pb-hairline">
            <h3 className="font-mono text-[11px] uppercase tracking-wide2 text-pb-faint">Selected XI · {picked.length}</h3>
          </div>
          <div className="overflow-auto max-h-[60vh]">
            {picked.length === 0 && <div className="px-4 py-6 text-center text-pb-faint text-sm">Click players on the left to build your side.</div>}
            {picked.map((sel, i) => {
              const p = poolById[sel.player_id]
              if (!p) return null
              const m = AVAIL_META[p.availability] || AVAIL_META.NO_RESPONSE
              return (
                <div key={sel.player_id} className="px-4 py-2 border-t pb-hairline flex items-center gap-2">
                  <span className="font-mono text-[11px] text-pb-faintest w-5 text-right">{i + 1}</span>
                  <span className={`font-mono text-sm ${m.cls}`} title={m.label}>{m.g}</span>
                  <span className="flex-1 min-w-0 text-sm truncate">{p.display_name}</span>
                  {canEdit && <>
                    <button onClick={() => toggleFlag(sel.player_id, 'is_captain')}
                      className={`font-mono text-[10px] px-1.5 py-0.5 rounded border ${sel.is_captain ? 'bg-pb-accent/15 text-pb-accent border-pb-accent/40' : 'pb-hairline text-pb-faintest'}`}
                      title="Captain">C</button>
                    <button onClick={() => toggleFlag(sel.player_id, 'is_wicket_keeper')}
                      className={`font-mono text-[10px] px-1.5 py-0.5 rounded border ${sel.is_wicket_keeper ? 'bg-pb-accent/15 text-pb-accent border-pb-accent/40' : 'pb-hairline text-pb-faintest'}`}
                      title="Wicket-keeper">WK</button>
                    <span className="flex flex-col">
                      <button onClick={() => move(i, -1)} disabled={i === 0} className="text-pb-faintest hover:text-pb-text disabled:opacity-30 text-[10px] leading-none">▲</button>
                      <button onClick={() => move(i, 1)} disabled={i === picked.length - 1} className="text-pb-faintest hover:text-pb-text disabled:opacity-30 text-[10px] leading-none">▼</button>
                    </span>
                    <button onClick={() => remove(sel.player_id)} className="text-pb-faintest hover:text-pb-red text-xs" title="Remove">✕</button>
                  </>}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </BetterSelectLayout>
  )
}
