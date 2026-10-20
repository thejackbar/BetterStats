import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../../../lib/api'
import { Button, Select, TextInput } from '../ui'

// The words people use to name a match. The same panel sits on every step of Card review and on
// Find a match, and the server reads the same query parameters for all of them, so a person who
// narrows one step to a player or a grade can carry the same words to the next.
export const FILTER_KEYS = ['q', 'player', 'grade', 'competition', 'date_from', 'date_to']
export const EMPTY_FILTERS = { q: '', player: '', grade: '', competition: '', date_from: '', date_to: '' }

export const filterParams = f => Object.fromEntries(FILTER_KEYS.filter(k => (f?.[k] || '').trim()).map(k => [k, f[k].trim()]))
export const hasFilters = f => FILTER_KEYS.some(k => (f?.[k] || '').trim())

// The filters live in the address bar, so a search can be shared, reloaded and followed by the
// browser's Back button, and moving between steps keeps them.
export function useFilterParams() {
  const [search, setSearch] = useSearchParams()
  const value = { ...EMPTY_FILTERS, ...Object.fromEntries(FILTER_KEYS.map(k => [k, search.get(k) || ''])) }
  const apply = next => setSearch(prev => {
    const out = new URLSearchParams(prev)
    FILTER_KEYS.forEach(k => { if ((next[k] || '').trim()) out.set(k, next[k].trim()); else out.delete(k) })
    return out
  }, { replace: true })
  return [value, apply]
}

// Where the "Find a match" link goes from any step, keeping the words already typed.
export const findUrl = f => {
  const q = new URLSearchParams(filterParams(f))
  return `/admin/card-review/find${q.toString() ? `?${q}` : ''}`
}

export function FindLink({ filters, size = 'sm' }) {
  return <Button size={size} as={Link} to={findUrl(filters)} data-testid="find-link">Find a match</Button>
}

let optionsCache = null

export default function MatchFilters({ value, onApply, hint, extra }) {
  const [draft, setDraft] = useState(value)
  const [opts, setOpts] = useState(optionsCache)
  useEffect(() => { setDraft(value) }, [JSON.stringify(value)]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (optionsCache) return
    api.cardReviewFindOptions().then(o => { optionsCache = o; setOpts(o) }).catch(() => {})
  }, [])
  const set = k => e => setDraft(d => ({ ...d, [k]: e.target.value }))
  const dirty = JSON.stringify(filterParams(draft)) !== JSON.stringify(filterParams(value))
  const submit = e => { e.preventDefault(); onApply(draft) }
  return (
    <form onSubmit={submit} className="mb-4 rounded-xl border border-pb-hairline bg-pb-surface px-4 py-3.5" data-testid="match-filters">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <label className="block min-w-0 text-[11.5px] text-pb-dim">Opposition or team
          <TextInput className="mt-1" value={draft.q} onChange={set('q')} placeholder="e.g. Warnbro" data-testid="f-q" />
        </label>
        <label className="block min-w-0 text-[11.5px] text-pb-dim">Player
          <TextInput className="mt-1" value={draft.player} onChange={set('player')} placeholder="Batted or bowled" data-testid="f-player" />
        </label>
        <label className="block min-w-0 text-[11.5px] text-pb-dim">Grade
          <TextInput className="mt-1" value={draft.grade} onChange={set('grade')} placeholder="e.g. B Grade" data-testid="f-grade" />
        </label>
        <label className="block min-w-0 text-[11.5px] text-pb-dim">Competition
          <Select className="mt-1" value={draft.competition} onChange={set('competition')} data-testid="f-competition">
            <option value="">Any competition</option>
            {(opts?.competitions || []).map(c => <option key={c} value={c}>{c}</option>)}
          </Select>
        </label>
        <label className="block min-w-0 text-[11.5px] text-pb-dim">From
          <TextInput className="mt-1" type="date" value={draft.date_from} onChange={set('date_from')} data-testid="f-from" />
        </label>
        <label className="block min-w-0 text-[11.5px] text-pb-dim">To
          <TextInput className="mt-1" type="date" value={draft.date_to} onChange={set('date_to')} data-testid="f-to" />
        </label>
        {extra}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button type="submit" variant="primary" size="sm" data-testid="f-apply">{dirty || !hasFilters(value) ? 'Search' : 'Search again'}</Button>
        {hasFilters(value) && <Button size="sm" onClick={() => onApply(EMPTY_FILTERS)} data-testid="f-clear">Clear</Button>}
        {hint && <span className="text-[12px] text-pb-dim">{hint}</span>}
      </div>
    </form>
  )
}
