import { useState, useEffect, useMemo, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useNameFormat, nameMatchesSearch } from '../lib/nameFormat'

const MAX_RESULTS = 8

export default function NavbarPlayerSearch({ orgId, club, variant = 'desktop', onSelect }) {
  const [query, setQuery] = useState('')
  const [players, setPlayers] = useState([])
  const [open, setOpen] = useState(false)
  const [highlight, setHighlight] = useState(0)
  const containerRef = useRef(null)
  const inputRef = useRef(null)
  const navigate = useNavigate()
  const fmt = useNameFormat(club)

  useEffect(() => {
    if (!orgId) { setPlayers([]); return }
    let cancelled = false
    api.listPlayers(orgId)
      .then(rows => { if (!cancelled) setPlayers(rows || []) })
      .catch(() => { if (!cancelled) setPlayers([]) })
    return () => { cancelled = true }
  }, [orgId])

  const matches = useMemo(() => {
    const q = query.trim()
    if (!q) return []
    return players
      .filter(p => nameMatchesSearch(p.display_name || p.name, q))
      .slice(0, MAX_RESULTS)
  }, [players, query])

  useEffect(() => { setHighlight(0) }, [query])

  useEffect(() => {
    function onClick(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  function selectPlayer(p) {
    if (!p) return
    setQuery('')
    setOpen(false)
    inputRef.current?.blur()
    onSelect?.()
    navigate(`/players/${p.id}`)
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
      selectPlayer(matches[highlight])
    }
  }

  if (!orgId) return null

  const showDropdown = open && query.trim().length > 0
  const isMobile = variant === 'mobile'

  return (
    <div
      ref={containerRef}
      className={isMobile ? 'w-full' : 'relative shrink-0 hidden md:block ml-2'}
    >
      <div className="relative">
        <svg
          className={`absolute top-1/2 -translate-y-1/2 text-pb-faint pointer-events-none ${
            isMobile ? 'left-3 w-4 h-4' : 'left-2.5 w-3 h-3'
          }`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
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
              ? 'w-full bg-pb-bg border pb-hairline text-pb-text text-[14px] rounded pl-10 pr-10 py-2.5 focus:outline-none focus:border-pb-accent placeholder-pb-faint'
              : 'w-[180px] lg:w-[220px] bg-pb-bg border pb-hairline text-pb-text text-[12px] rounded pl-7 pr-7 py-1.5 focus:outline-none focus:border-pb-accent placeholder-pb-faint'
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
      {showDropdown && (
        <div className={
          isMobile
            ? 'mt-2 w-full bg-pb-surface pb-hairline rounded shadow-lg overflow-hidden max-h-[60vh] overflow-y-auto'
            : 'absolute top-full right-0 mt-1 w-[260px] bg-pb-surface pb-hairline rounded shadow-lg overflow-hidden z-50 max-h-[400px] overflow-y-auto'
        }>
          {matches.length === 0 ? (
            <div className={isMobile ? 'px-3 py-3 text-pb-faint text-[13px]' : 'px-3 py-2 text-pb-faint text-[12px]'}>
              No players match.
            </div>
          ) : matches.map((p, i) => (
            <Link
              key={p.id}
              to={`/players/${p.id}`}
              onClick={() => { setQuery(''); setOpen(false); onSelect?.() }}
              onMouseEnter={() => setHighlight(i)}
              className={
                isMobile
                  ? `block px-3 py-3 text-[14px] text-pb-text hover:bg-pb-surface2 transition-colors ${i === highlight ? 'bg-pb-surface2' : ''}`
                  : `block px-3 py-1.5 text-[12px] text-pb-text hover:bg-pb-surface2 transition-colors ${i === highlight ? 'bg-pb-surface2' : ''}`
              }
            >
              {fmt(p.display_name || p.name)}
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
