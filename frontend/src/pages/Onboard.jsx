import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'

const SYNC_STEPS = [
  'Connecting to Play Cricket…',
  'Fetching seasons…',
  'Loading player data…',
  'Building statistics…',
  'Almost there…',
]

export default function Onboard() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [selected, setSelected] = useState(null) // { id, name }
  const [showResults, setShowResults] = useState(false)
  const [searching, setSearching] = useState(false)
  const [status, setStatus] = useState(null) // null | 'loading' | 'syncing' | 'error'
  const [message, setMessage] = useState('')
  const [orgId, setOrgId] = useState(null)
  const [syncStep, setSyncStep] = useState(0)
  const [syncElapsed, setSyncElapsed] = useState(0)
  const navigate = useNavigate()
  const debounceRef = useRef(null)
  const wrapperRef = useRef(null)
  const pollRef = useRef(null)
  const stepRef = useRef(null)
  const elapsedRef = useRef(null)

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

  // Poll for seasons after sync starts
  useEffect(() => {
    if (status !== 'syncing' || !orgId) return

    // Cycle through status messages
    stepRef.current = setInterval(() => {
      setSyncStep(s => Math.min(s + 1, SYNC_STEPS.length - 1))
    }, 6000)

    // Track elapsed time
    elapsedRef.current = setInterval(() => {
      setSyncElapsed(s => s + 1)
    }, 1000)

    // Poll for seasons data
    pollRef.current = setInterval(async () => {
      try {
        const seasons = await api.getOrgSeasons(orgId)
        if (seasons && seasons.length > 0) {
          clearInterval(pollRef.current)
          clearInterval(stepRef.current)
          clearInterval(elapsedRef.current)
          navigate(`/dashboard/${orgId}`)
        }
      } catch {
        // keep polling
      }
    }, 4000)

    return () => {
      clearInterval(pollRef.current)
      clearInterval(stepRef.current)
      clearInterval(elapsedRef.current)
    }
  }, [status, orgId, navigate])

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
      const data = await api.onboard(selected.id, selected.name || '')
      setOrgId(data.org_id)
      setSyncStep(0)
      setSyncElapsed(0)
      setStatus('syncing')
    } catch (err) {
      setStatus('error')
      setMessage(err.message || 'Failed to add club. Please try again.')
    }
  }

  if (status === 'syncing' && orgId) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16">
        <div className="mb-10">
          <div className="accent-bar mb-4" />
          <h1 className="display-heading text-4xl text-white mb-2">SYNCING DATA</h1>
          <p className="text-slate-400">
            Pulling stats for <span className="text-white font-medium">{selected?.name}</span> from Play Cricket.
          </p>
        </div>

        <div className="card p-8 text-center space-y-6">
          {/* Spinner */}
          <div className="flex justify-center">
            <div className="w-16 h-16 border-4 border-navy-600 border-t-accent rounded-full animate-spin" />
          </div>

          {/* Status message */}
          <div>
            <p className="text-white font-medium mb-1">{SYNC_STEPS[syncStep]}</p>
            <p className="text-slate-500 text-sm">{syncElapsed}s elapsed</p>
          </div>

          {/* Progress bar */}
          <div className="w-full bg-navy-700 rounded-full h-1.5">
            <div
              className="bg-accent h-1.5 rounded-full transition-all duration-1000"
              style={{ width: `${Math.min((syncStep / (SYNC_STEPS.length - 1)) * 85 + (syncElapsed % 6) * 2, 95)}%` }}
            />
          </div>

          <p className="text-slate-500 text-xs">
            This usually takes 1–3 minutes for a full season of data.
          </p>

          {/* Manual skip after 30s */}
          {syncElapsed >= 30 && (
            <button
              onClick={() => navigate(`/dashboard/${orgId}`)}
              className="text-accent text-sm hover:underline"
            >
              Go to dashboard now →
            </button>
          )}
        </div>
      </div>
    )
  }

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
              disabled={status === 'loading'}
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
                    <div className="font-medium">{org.name || org.shortName}</div>
                    {org.suburb && (
                      <div className="text-slate-400 text-xs">{org.suburb}{org.stateName ? `, ${org.stateName}` : ''}</div>
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
          <div className="rounded-lg px-4 py-3 text-sm bg-red-500/10 border border-red-500/30 text-red-400">
            {message}
          </div>
        )}

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
      </form>
    </div>
  )
}
