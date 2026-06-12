/* BetterIQ — search EVERY club on PlayHQ, not just opponents we've met.
 *
 * The picker lists only clubs in our game history, which goes blank the moment
 * the target sits outside our competitions (new opposition after relegation or
 * promotion, a different association, idle curiosity). This box searches
 * Cricket Australia's whole club registry (the same `searchOrgs` lookup club
 * onboarding uses) and hands back `{ id, name }`, where `id` is the CA org
 * GUID — the dossier pipeline discovers an unknown club's teams from that GUID
 * alone, so anyone is scoutable.
 */
import { useState, useEffect, useRef } from 'react'
import Dropdown from '../../../components/Dropdown'
import { api } from '../../../lib/api'
import { Search } from './ui'

export default function AnyClubSearch({ onPick, placeholder = 'Search any club in Australia…', className = '' }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const t = q.trim()
    if (t.length < 3) { setResults([]); return }
    let alive = true
    const timer = setTimeout(() => {
      setSearching(true)
      api.searchOrgs(t)
        .then(r => { if (alive) { setResults(Array.isArray(r) ? r : []); setOpen(true) } })
        .catch(() => { if (alive) setResults([]) })
        .finally(() => { if (alive) setSearching(false) })
    }, 350)
    return () => { alive = false; clearTimeout(timer) }
  }, [q])

  const pick = (org) => {
    if (!org.id) return
    onPick({ id: org.id, name: org.name || org.shortName || 'Unknown club' })
    setQ(''); setResults([]); setOpen(false)
  }

  return (
    <div ref={ref} className={`relative ${className}`}
      onFocusCapture={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}>
      <Search value={q} onChange={setQ} placeholder={placeholder} className="w-full" />
      {searching && <span className="absolute right-9 top-1/2 -translate-y-1/2 iq-mono text-pb-faintest animate-pulse" style={{ fontSize: 9 }}>…</span>}
      <Dropdown
        anchorRef={ref}
        open={open && q.trim().length >= 3}
        onClose={() => setOpen(false)}
        maxHeight={300}
        className="iq-card p-1 iq-scroll shadow-lg"
        style={{ background: 'var(--pb-surface)' }}
      >
        {results.length === 0
          ? <div className="px-2.5 py-2 text-pb-faint text-sm">{searching ? 'Searching…' : 'No club found on PlayHQ.'}</div>
          : results.slice(0, 20).map((org, i) => (
            <button key={org.id || i} type="button" onMouseDown={e => e.preventDefault()} onClick={() => pick(org)}
              className="w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg hover:bg-pb-surface2 text-left">
              {(org.logoURL || org.logo_url) && (
                <img src={org.logoURL || org.logo_url} alt="" className="w-6 h-6 rounded object-contain shrink-0"
                  style={{ background: 'var(--pb-surface2)' }} onError={e => { e.target.style.display = 'none' }} />
              )}
              <span className="font-medium truncate flex-1">{org.name}</span>
              {org.shortName && <span className="iq-mono text-pb-faintest shrink-0" style={{ fontSize: 9 }}>{org.shortName}</span>}
            </button>
          ))}
      </Dropdown>
    </div>
  )
}
