import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../../../lib/api'
import { Button, Select, TextInput } from '../ui'
import Suggest from './Suggest'

// The words people use to name a match. The same panel sits on every step of Card review and on
// Find a match, and the server reads the same query parameters for all of them, so a person who
// narrows one step to a player or a grade can carry the same words to the next.
export const FILTER_KEYS = ['q', 'player', 'grade', 'competition', 'season', 'date_from', 'date_to']
export const EMPTY_FILTERS = { q: '', player: '', grade: '', competition: '', season: '', date_from: '', date_to: '' }

export const filterParams = f => Object.fromEntries(FILTER_KEYS.filter(k => (f?.[k] || '').trim()).map(k => [k, f[k].trim()]))
export const hasFilters = f => FILTER_KEYS.some(k => (f?.[k] || '').trim())

// The filters live in the address bar, so a search can be shared, reloaded and followed by the
// browser's Back button, and moving between steps keeps them.
export function useFilterParams() {
  const [search, setSearch] = useSearchParams()
  // MEMOISED ON THE ADDRESS. The pages load from an effect that depends on this object, so a new
  // object on every render made every response start the next request and throw the last one away:
  // the list never settled, and with no results the spinner never left.
  const key = search.toString()
  const value = useMemo(
    () => ({ ...EMPTY_FILTERS, ...Object.fromEntries(FILTER_KEYS.map(k => [k, search.get(k) || ''])) }),
    [key], // eslint-disable-line react-hooks/exhaustive-deps
  )
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

export default function MatchFilters({ value, onApply, hint, extra, playerNote }) {
  const [draft, setDraft] = useState(value)
  const [opts, setOpts] = useState(optionsCache)
  useEffect(() => { setDraft(value) }, [value])
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
        <Suggest label="Opposition or team" value={draft.q} onChange={v => setDraft(d => ({ ...d, q: v }))}
          items={opts?.oppositions || []} placeholder="e.g. Warnbro" testId="f-q" />
        <Suggest label="Player" value={draft.player} onChange={v => setDraft(d => ({ ...d, player: v }))}
          items={opts?.players || []} placeholder="Batted or bowled" minChars={2} testId="f-player" />
        <Suggest label="Grade" value={draft.grade} onChange={v => setDraft(d => ({ ...d, grade: v }))}
          items={opts?.grades || []} placeholder="e.g. B Grade" showAll testId="f-grade" />
        <div className="min-w-0">
          <label htmlFor="f-competition" className="block text-[11.5px] text-pb-dim">Competition</label>
          <Select id="f-competition" className="mt-1" value={draft.competition} onChange={set('competition')} data-testid="f-competition">
            <option value="">Any competition</option>
            {(opts?.competitions || []).map(c => <option key={c} value={c}>{c}</option>)}
          </Select>
        </div>
        <div className="min-w-0">
          <label htmlFor="f-season" className="block text-[11.5px] text-pb-dim">Season</label>
          <Select id="f-season" className="mt-1" value={draft.season} onChange={set('season')} data-testid="f-season">
            <option value="">Any season</option>
            {(opts?.seasons || []).map(c => <option key={c} value={c}>{c}</option>)}
          </Select>
        </div>
        <div className="min-w-0">
          <label htmlFor="f-from" className="block text-[11.5px] text-pb-dim">From</label>
          <TextInput id="f-from" className="mt-1" type="date" value={draft.date_from} onChange={set('date_from')} data-testid="f-from" />
        </div>
        <div className="min-w-0">
          <label htmlFor="f-to" className="block text-[11.5px] text-pb-dim">To</label>
          <TextInput id="f-to" className="mt-1" type="date" value={draft.date_to} onChange={set('date_to')} data-testid="f-to" />
        </div>
        {extra}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button type="submit" variant="primary" size="sm" data-testid="f-apply">{dirty || !hasFilters(value) ? 'Search' : 'Search again'}</Button>
        {hasFilters(value) && <Button size="sm" onClick={() => onApply(EMPTY_FILTERS)} data-testid="f-clear">Clear</Button>}
        {hint && <span className="text-[12px] text-pb-dim">{hint}</span>}
      </div>
      {playerNote && (
        <p className="mt-2.5 text-[12.5px]" style={{ color: '#f5b542' }} data-testid="player-note">
          {playerNote.matched.length === 0
            ? `No player at this club matches "${playerNote.query}". Check the spelling, or pick a name from the list as you type.`
            : `No player is named "${playerNote.query}". Showing the closest: ${playerNote.matched.join('; ')}.`}
        </p>
      )}
    </form>
  )
}
