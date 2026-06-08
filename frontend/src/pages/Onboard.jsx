import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import Dropdown from '../components/Dropdown'

export default function Onboard() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [selected, setSelected] = useState(null)
  const [showResults, setShowResults] = useState(false)
  const [searching, setSearching] = useState(false)
  const [status, setStatus] = useState(null)
  const [message, setMessage] = useState('')
  const [result, setResult] = useState(null)
  const navigate = useNavigate()
  const debounceRef = useRef(null)
  const wrapperRef = useRef(null)

  useEffect(() => {
    if (selected) return
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (!query || query.trim().length < 2) {
      setResults([])
      setShowResults(false)
      return
    }
    debounceRef.current = setTimeout(async () => {
      setSearching(true)
      try {
        const data = await api.searchOrgs(query.trim())
        setResults(Array.isArray(data) ? data : [])
        setShowResults(true)
      } catch {
        setResults([])
      } finally {
        setSearching(false)
      }
    }, 350)
    return () => clearTimeout(debounceRef.current)
  }, [query, selected])

  const handleSelect = (org) => {
    setSelected(org)
    setQuery(org.name || org.shortName || org.id)
    setShowResults(false)
    setResults([])
  }

  const handleQueryChange = (e) => {
    setSelected(null)
    setQuery(e.target.value)
    setStatus(null)
    setMessage('')
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!selected) return
    setStatus('loading')
    setMessage('')
    try {
      const data = await api.onboard(selected.id, selected.name || selected.shortName || '')
      setResult(data)
      setStatus('success')
      setMessage(`${data.name} is being synced. This may take a few minutes.`)
    } catch (err) {
      setStatus('error')
      setMessage(err.message || 'Failed to add club. Please try again.')
    }
  }

  const orgName = (org) => org.name || org.shortName || org.organisationName || org.id || ''

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <div className="max-w-2xl mx-auto px-4 py-16">
        <div className="mb-10">
          <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-4 uppercase">Get started</p>
          <h1 className="font-display font-bold text-[40px] md:text-[56px] text-pb-text leading-none mb-4 tracking-tight">
            ADD YOUR<br />
            <span style={{ color: 'var(--pb-accent)' }}>CLUB.</span>
          </h1>
          <p className="text-pb-dim">
            Search for your cricket club by name to connect it to BetterStats.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div ref={wrapperRef} className="relative">
            <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase block mb-2">
              Search Club Name
            </label>
            <div className="relative">
              <input
                type="text"
                value={query}
                onChange={handleQueryChange}
                onFocus={() => results.length > 0 && setShowResults(true)}
                placeholder="e.g. Applecross Cricket Club"
                className="w-full bg-pb-surface2 border pb-hairline text-pb-text placeholder-pb-faintest text-sm rounded px-4 py-3 focus:outline-none focus:border-pb-accent transition-colors pr-10"
                disabled={status === 'loading' || status === 'success'}
                autoComplete="off"
              />
              {searching && (
                <div className="absolute right-3 top-1/2 -translate-y-1/2">
                  <span className="w-4 h-4 border-2 border-pb-accent/40 border-t-pb-accent rounded-full animate-spin block" />
                </div>
              )}
              {selected && (
                <div className="absolute right-3 top-1/2 -translate-y-1/2 text-sm" style={{ color: 'var(--pb-accent)' }}>✓</div>
              )}
            </div>

            <Dropdown
              anchorRef={wrapperRef}
              open={showResults && results.length > 0}
              onClose={() => setShowResults(false)}
              maxHeight={240}
              className="bg-pb-surface border pb-hairline rounded shadow-xl"
            >
              <ul>
                {results.map((org) => (
                  <li key={org.id}>
                    <button
                      type="button"
                      onClick={() => handleSelect(org)}
                      className="w-full text-left px-4 py-3 text-sm text-pb-text hover:bg-pb-surface2 transition-colors pb-hairline-b last:border-0"
                    >
                      <div className="font-medium">{orgName(org)}</div>
                      {org.shortName && org.shortName !== org.name && (
                        <div className="text-pb-faint text-xs mt-0.5">{org.shortName}</div>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            </Dropdown>

            <Dropdown
              anchorRef={wrapperRef}
              open={showResults && !searching && results.length === 0 && query.length >= 2}
              onClose={() => setShowResults(false)}
              className="bg-pb-surface border pb-hairline rounded px-4 py-3 text-sm text-pb-faint"
            >
              No clubs found for "{query}"
            </Dropdown>
          </div>

          {message && (
            <div className={`rounded px-4 py-3 font-mono text-[11px] ${
              status === 'error'
                ? 'bg-pb-red/10 border border-pb-red/30 text-pb-red'
                : 'border text-pb-accent'
            }`}
            style={status !== 'error' ? { borderColor: 'var(--pb-accent)', background: 'color-mix(in srgb, var(--pb-accent) 10%, transparent)' } : {}}
            >
              {message}
            </div>
          )}

          {status !== 'success' ? (
            <button
              type="submit"
              disabled={status === 'loading' || !selected}
              className="w-full py-3 rounded font-mono text-[11px] tracking-wide3 font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              {status === 'loading' ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-4 h-4 border-2 border-pb-bg/40 border-t-pb-bg rounded-full animate-spin" />
                  Connecting…
                </span>
              ) : 'ADD CLUB & START SYNC'}
            </button>
          ) : (
            <button
              type="button"
              onClick={() => result && navigate(`/${result.slug}`)}
              className="w-full py-3 rounded font-mono text-[11px] tracking-wide3 font-semibold transition text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              VIEW DASHBOARD →
            </button>
          )}
        </form>
      </div>
    </div>
  )
}
