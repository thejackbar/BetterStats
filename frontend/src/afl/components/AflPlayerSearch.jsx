import { useState, useEffect, useMemo, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { aflApi } from '../aflApi'
import { useNameFormat, nameMatchesSearch } from '../../lib/nameFormat'
import { displayName } from './bits'
import Dropdown from '../../components/Dropdown'

const MAX_RESULTS = 8

/**
 * Player search in the club navbar — BetterCricket's NavbarPlayerSearch,
 * pointed at the AFL roster and the club-scoped profile route.
 *
 * The roster is fetched once and filtered in the browser, same as cricket:
 * a football club's whole player list is one small payload, and doing it
 * locally means no request per keystroke and no stale response landing on
 * top of a newer query.
 *
 * Every result carries a career line (games · goals) because a football club
 * has several people with the same surname and often the same first name —
 * the numbers are what tells the two apart in a list of eight.
 */
export default function AflPlayerSearch({ club, variant = 'desktop', onSelect }) {
  const [query, setQuery] = useState('')
  const [players, setPlayers] = useState([])
  const [open, setOpen] = useState(false)
  const [highlight, setHighlight] = useState(0)
  const containerRef = useRef(null)
  const inputRef = useRef(null)
  const navigate = useNavigate()
  const fmt = useNameFormat(club)
  const base = `/${club?.slug}`

  useEffect(() => {
    if (!club?.id) { setPlayers([]); return }
    let cancelled = false
    aflApi.listPlayers(club.id)
      .then(res => { if (!cancelled) setPlayers(res?.players || []) })
      .catch(() => { if (!cancelled) setPlayers([]) })
    return () => { cancelled = true }
  }, [club?.id])

  const matches = useMemo(() => {
    const q = query.trim()
    if (!q) return []
    return players
      .filter(p => nameMatchesSearch(displayName(p), q))
      .slice(0, MAX_RESULTS)
  }, [players, query])

  useEffect(() => { setHighlight(0) }, [query])

  function goTo(p) {
    if (!p) return
    setQuery('')
    setOpen(false)
    inputRef.current?.blur()
    onSelect?.()
    navigate(`${base}/players/${p.player_id}`)
  }

  function onKeyDown(e) {
    if (e.key === 'Escape') {
      setOpen(false)
      inputRef.current?.blur()
      return
    }
    if (!matches.length) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlight(i => Math.min(i + 1, matches.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlight(i => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      goTo(matches[highlight])
    }
  }

  if (!club?.id) return null

  const showDropdown = open && query.trim().length > 0
  const isMobile = variant === 'mobile'

  return (
    <div ref={containerRef} className={isMobile ? 'w-full' : 'relative shrink-0 hidden lg:block'}>
      <div className="relative">
        <svg
          className={`absolute top-1/2 -translate-y-1/2 text-pb-faint pointer-events-none ${
            isMobile ? 'left-3 w-4 h-4' : 'left-2.5 w-3 h-3'
          }`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <input
          ref={inputRef}
          type="text"
          placeholder="Search players…"
          value={query}
          onChange={e => { setQuery(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          className={
            isMobile
              ? 'w-full bg-pb-bg border border-pb-hairline text-pb-text text-[14px] rounded pl-10 pr-10 py-2.5 focus:outline-none focus:border-[var(--pb-accent)] placeholder-pb-faint'
              : 'w-[170px] xl:w-[210px] bg-pb-bg border border-pb-hairline text-pb-text text-[12px] rounded pl-7 pr-7 py-1.5 focus:outline-none focus:border-[var(--pb-accent)] placeholder-pb-faint'
          }
        />
        {query && (
          <button
            type="button"
            onClick={() => { setQuery(''); inputRef.current?.focus() }}
            className={`absolute top-1/2 -translate-y-1/2 text-pb-faint hover:text-pb-text leading-none ${
              isMobile ? 'right-3 text-lg w-8 h-8 flex items-center justify-center' : 'right-2 text-sm'
            }`}
            aria-label="Clear search"
          >
            ×
          </button>
        )}
      </div>
      <Dropdown
        anchorRef={containerRef}
        open={showDropdown}
        onClose={() => setOpen(false)}
        align={isMobile ? 'stretch' : 'end'}
        width={isMobile ? undefined : 280}
        maxHeight={isMobile ? undefined : 400}
        className="bg-pb-surface border border-pb-hairline rounded shadow-lg overflow-hidden"
      >
        {matches.length === 0 ? (
          <div className={isMobile ? 'px-3 py-3 text-pb-faint text-[13px]' : 'px-3 py-2 text-pb-faint text-[12px]'}>
            No players match.
          </div>
        ) : matches.map((p, i) => (
          <Link
            key={p.player_id}
            to={`${base}/players/${p.player_id}`}
            onClick={() => { setQuery(''); setOpen(false); onSelect?.() }}
            onMouseEnter={() => setHighlight(i)}
            className={`flex items-baseline justify-between gap-3 text-pb-text hover:bg-pb-surface2 transition-colors ${
              isMobile ? 'px-3 py-3 text-[14px]' : 'px-3 py-1.5 text-[12px]'
            } ${i === highlight ? 'bg-pb-surface2' : ''}`}
          >
            <span className="truncate">{fmt(displayName(p))}</span>
            <span className="font-mono text-[10px] text-pb-faint shrink-0 whitespace-nowrap">
              {p.games || 0}g · {p.goals || 0}gl
            </span>
          </Link>
        ))}
      </Dropdown>
    </div>
  )
}
