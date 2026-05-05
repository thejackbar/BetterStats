import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'

export default function Onboard() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [selected, setSelected] = useState(null) // { id, name }
  const [showResults, setShowResults] = useState(false)
  const [searching, setSearching] = useState(false)
  const [status, setStatus] = useState(null) // null | 'loading' | 'success' | 'error'
  const [message, setMessage] = useState('')
  const [result, setResult] = useState(null)
  const navigate = useNavigate()
  const debounceRef = useRef(null)
  const wrapperRef = useRef(null)

  useEffect(() => {
    function handleClickOutside(e) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setShowResults(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

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
    const id = org.organisationGuid || org.id
    setSelected({ id, name: org.name || org.shortName || id })
    setQuery(org.name || org.shortName || id)
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
    <div className="max-w-2xl mx-auto px-4 py-16">
      <div className="mb-10">
        <div className="accent-bar mb-4" />
        <h1 className="display-heading text-4xl text-white mb-2">ADD YOUR CLUB</h1>
        <p className="text-slate-400">
          Search for your cricket club by name to connect it to BetterStats.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div ref={wrapperRef} className="relative">
          <label className="section-label block mb-2">Search Club Name</label>
          <div className="relative">
            <input
              type="text"
              value={query}
              onChange={handleQueryChange}
              onFocus={() => results.length > 0 && setShowResults(true)}
              placeholder="e.g. Applecross Cricket Club"
              className="w-full bg-navy-800 border border-navy-600 text-white placeholder-slate-600 text-sm rounded-lg px-4 py-3 focus:outline-none focus:border-accent transition-colors pr-10"
              disabled={status === 'loading' || status === 'success'}
              autoComplete="off"
            />
            {searching && (
              <div className="absolute right-3 top-1/2 -translate-y-1/2">
                <span className="w-4 h-4 border-2 border-accent/40 border-t-accent rounded-full animate-spin block" />
              </div>
            )}
            {selected && (
              <div className="absolute right-3 top-1/2 -translate-y-1/2 text-accent text-lg">✓</div>
            )}
          </div>

          {showResults && results.length > 0 && (
            <ul className="absolute z-10 mt-1 w-full bg-navy-800 border border-navy-600 rounded-lg shadow-xl max-h-60 overflow-y-auto">
              {results.map((org) => (
                <li key={org.organisationGuid || org.id}>
                  <button
                    type="button"
                    onClick={() => handleSelect(org)}
                    className="w-full text-left px-4 py-3 text-sm text-white hover:bg-navy-700 transition-colors border-b border-navy-700 last:border-0"
                  >
                    <div className="font-medium">{orgName(org)}</div>
                    {org.shortName && org.shortName !== org.name && (
                      <div className="text-slate-400 text-xs">{org.shortName}</div>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}

          {showResults && !searching && results.length === 0 && query.length >= 2 && (
            <div className="absolute z-10 mt-1 w-full bg-navy-800 border border-navy-600 rounded-lg px-4 py-3 text-sm text-slate-400">
              No clubs found for "{query}"
            </div>
          )}
        </div>

        {message && (
          <div className={`rounded-lg px-4 py-3 text-sm ${status === 'error' ? 'bg-red-500/10 border border-red-500/30 text-red-400' : 'bg-accent/10 border border-accent/30 text-accent'}`}>
            {message}
          </div>
        )}

        {status !== 'success' ? (
          <button
            type="submit"
            disabled={status === 'loading' || !selected}
            className="btn-primary w-full py-3 text-base disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {status === 'loading' ? (
              <span className="flex items-center justify-center gap-2">
                <span className="w-4 h-4 border-2 border-navy-950/40 border-t-navy-950 rounded-full animate-spin" />
                Connecting…
              </span>
            ) : 'Add Club & Start Sync'}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => result && navigate(`/dashboard/${result.org_id}`)}
            className="btn-primary w-full py-3 text-base"
          >
            View Dashboard →
          </button>
        )}
      </form>
    </div>
  )
}
