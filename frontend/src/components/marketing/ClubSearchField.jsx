import { useEffect, useRef, useState } from 'react'
import { api } from '../../lib/api'

/**
 * Club name field for the public marketing forms — a search over the Cricket
 * Australia club list rather than a free-text box.
 *
 * A typed club name is a guess: an abbreviation, a misspelling, or the
 * association's name instead of the club's. Everything downstream then has to
 * match that string back to a real club, and two spellings of one club read as
 * two clubs. Picking from the list carries the club's real CA organisation
 * guid through with it, so the match is on identity rather than spelling.
 *
 * The typed name stays available on purpose. The CA list only covers Australia,
 * and a club in England or New Zealand has to be able to reach us — so "I can't
 * find my club" hands back a plain text field instead of a dead end. Which path
 * was taken is reported back through `source`, so a hand-typed name is never
 * mistaken for a confirmed one.
 *
 * Controlled. `value` is { club, clubOrgId, clubSource }; `onChange` gets the
 * same shape back on every edit. One invariant holds it together: `club` is
 * only ever set once `clubSource` is — a half-typed search term is the field's
 * own local state, never a club name the form thinks it has. That is what makes
 * the form's own "Club name is required" check block a search nobody finished.
 */

const orgName = (org) => org.name || org.shortName || ''

export default function ClubSearchField({
  value,
  onChange,
  inputClassName = '',
  inputId = 'club',
  initialQuery = '',
}) {
  const { club = '', clubSource = null } = value || {}
  const picked = clubSource === 'search' && !!club
  const manual = clubSource === 'manual'

  // A club name carried in on the URL (a club's own inactive page links here
  // with its name) seeds the search rather than being taken as an answer —
  // searching it is what turns a name into a matched club.
  const [query, setQuery] = useState(initialQuery)
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [active, setActive] = useState(-1)   // keyboard-highlighted result

  const debounceRef = useRef(null)
  const wrapRef = useRef(null)
  const inputRef = useRef(null)

  // Close the result list on an outside click, the way a select would.
  useEffect(() => {
    const onDown = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [])

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (picked || manual) return
    const q = query.trim()
    if (q.length < 2) {
      setResults([])
      setOpen(false)
      setSearchError('')
      return
    }
    debounceRef.current = setTimeout(async () => {
      setSearching(true)
      setSearchError('')
      try {
        const data = await api.contactClubSearch(q)
        const list = Array.isArray(data) ? data : []
        setResults(list)
        setActive(-1)
        setOpen(true)
      } catch (e) {
        setResults([])
        setSearchError(e?.message || 'Club search is unavailable right now.')
        setOpen(false)
      } finally {
        setSearching(false)
      }
    }, 350)
    return () => clearTimeout(debounceRef.current)
  }, [query, picked, manual])

  const pick = (org) => {
    setOpen(false)
    setResults([])
    onChange({ club: orgName(org), clubOrgId: org.id || null, clubSource: 'search' })
  }

  const clearPick = () => {
    onChange({ club: '', clubOrgId: null, clubSource: null })
    setQuery('')
    setResults([])
    setOpen(false)
    // Focus lands back in the search box, so changing your mind is one click
    // and then straight into typing.
    requestAnimationFrame(() => inputRef.current?.focus())
  }

  const startManual = () => {
    onChange({ club: query.trim(), clubOrgId: null, clubSource: 'manual' })
    setOpen(false)
    requestAnimationFrame(() => inputRef.current?.focus())
  }

  const backToSearch = () => {
    setQuery(club)
    onChange({ club: '', clubOrgId: null, clubSource: null })
    requestAnimationFrame(() => inputRef.current?.focus())
  }

  const onKeyDown = (e) => {
    if (!open || results.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((i) => (i + 1) % results.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((i) => (i <= 0 ? results.length - 1 : i - 1))
    } else if (e.key === 'Enter' && active >= 0) {
      // Only swallow Enter when a result is actually highlighted — otherwise
      // it stays the form's own submit key.
      e.preventDefault()
      pick(results[active])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  // ── Picked from the list ────────────────────────────────────────────────
  if (picked) {
    return (
      <div className="rounded-lg border border-accent/40 bg-accent/[0.06] px-4 py-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm text-white font-medium truncate">{club}</p>
          <p className="text-xs text-pb-faint mt-0.5">Matched to your club's record</p>
        </div>
        <button type="button" onClick={clearPick}
          className="text-xs text-accent hover:underline flex-shrink-0 mt-0.5">
          Change
        </button>
      </div>
    )
  }

  // ── Typed in by hand ────────────────────────────────────────────────────
  if (manual) {
    return (
      <div>
        <input
          id={inputId} ref={inputRef} type="text" name="club"
          placeholder="Your club's full name"
          value={club}
          onChange={(e) => onChange({ club: e.target.value, clubOrgId: null, clubSource: 'manual' })}
          className={inputClassName}
        />
        <button type="button" onClick={backToSearch}
          className="mt-1.5 text-xs text-accent hover:underline">
          Search for your club instead
        </button>
      </div>
    )
  }

  // ── Searching ───────────────────────────────────────────────────────────
  const q = query.trim()
  const noResults = open && !searching && results.length === 0 && q.length >= 2

  return (
    <div ref={wrapRef} className="relative">
      <input
        id={inputId} ref={inputRef} type="text" name="club"
        role="combobox" aria-expanded={open} aria-controls="club-search-results"
        aria-autocomplete="list" autoComplete="off"
        placeholder="Start typing your club's name…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => { if (results.length > 0) setOpen(true) }}
        onKeyDown={onKeyDown}
        className={inputClassName}
      />

      {open && results.length > 0 && (
        <ul
          id="club-search-results" role="listbox"
          className="absolute z-20 mt-1 w-full max-h-72 overflow-y-auto rounded-lg border border-pb-hairline bg-[#161b27] shadow-xl"
        >
          {results.map((org, i) => {
            const location = [org.suburb, org.stateName].filter(Boolean).join(', ')
            return (
              <li key={org.id || orgName(org)} role="option" aria-selected={i === active}>
                <button
                  type="button"
                  onClick={() => pick(org)}
                  onMouseEnter={() => setActive(i)}
                  className={`w-full text-left px-4 py-2.5 border-b border-pb-hairline last:border-b-0 transition-colors ${
                    i === active ? 'bg-accent/[0.08]' : 'hover:bg-white/[0.04]'
                  }`}
                >
                  <span className="flex items-start justify-between gap-3">
                    {/* Wraps rather than truncates — the club name is the one
                        thing being chosen between, and plenty of real ones are
                        longer than this column is wide. */}
                    <span className="text-sm text-white">{orgName(org)}</span>
                    {org.already_registered && (
                      <span className="text-[10px] uppercase tracking-widest text-pb-faint flex-shrink-0 mt-0.5">
                        Registered
                      </span>
                    )}
                  </span>
                  {org.shortName && org.shortName !== org.name && (
                    <span className="block text-xs text-pb-faint mt-0.5">{org.shortName}</span>
                  )}
                  {location && (
                    <span className="block text-xs text-pb-faint mt-0.5">{location}</span>
                  )}
                </button>
              </li>
            )
          })}
        </ul>
      )}

      {noResults && (
        <div className="absolute z-20 mt-1 w-full rounded-lg border border-pb-hairline bg-[#161b27] px-4 py-3 shadow-xl">
          <p className="text-xs text-pb-dim">No clubs found for "{q}".</p>
          <button type="button" onClick={startManual}
            className="mt-1.5 text-xs text-accent hover:underline">
            Use "{q}" anyway →
          </button>
        </div>
      )}

      {searching && <p className="mt-1 text-xs text-pb-faint">Searching…</p>}
      {searchError && <p className="mt-1 text-xs text-pb-faint">{searchError}</p>}

      {!searching && !noResults && (
        <button type="button" onClick={startManual}
          className="mt-1.5 text-xs text-pb-faint hover:text-accent transition-colors">
          Can't find your club? Type the name in yourself
        </button>
      )}
    </div>
  )
}
