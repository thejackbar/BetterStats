import { useState, useEffect, useRef, useMemo } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import { api } from '../../lib/api'

// Super-admin (Better staff) club switcher — lets staff re-scope the whole
// admin app to any club without logging out. Renders nothing for non-super
// accounts. The club list is fetched lazily the first time the menu opens.
export default function ClubSwitcher() {
  const { user, switchClub } = useAuth()
  const [open, setOpen] = useState(false)
  const [clubs, setClubs] = useState(null) // null = not loaded yet
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const wrapRef = useRef(null)

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return
    const onClick = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  // Lazy-load clubs on first open.
  useEffect(() => {
    if (!open || clubs !== null) return
    api.superListClubs()
      .then(rows => setClubs(Array.isArray(rows) ? rows : []))
      .catch(() => setClubs([]))
  }, [open, clubs])

  const filtered = useMemo(() => {
    if (!clubs) return []
    const q = query.trim().toLowerCase()
    if (!q) return clubs
    return clubs.filter(c =>
      (c.name || '').toLowerCase().includes(q) || (c.slug || '').toLowerCase().includes(q)
    )
  }, [clubs, query])

  if (!user?.can_switch_clubs) return null

  const pick = async (clubId) => {
    setBusy(true)
    setError('')
    try {
      await switchClub(clubId) // hard-reloads on success
    } catch (e) {
      setError(e?.message || 'Could not switch club')
      setBusy(false)
    }
  }

  const currentName = user.club_name || user.club_slug || 'Select club'

  return (
    <div ref={wrapRef} className="relative">
      <button
        onClick={() => setOpen(o => !o)}
        title="Switch which club you're managing"
        className="flex items-center gap-1.5 font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors border pb-hairline rounded px-2.5 py-1.5 max-w-[180px]"
      >
        <svg className="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0H5m14 0h2M5 21H3m4-14h2m-2 4h2m-2 4h2m4-8h2m-2 4h2m-2 4h2" />
        </svg>
        <span className="truncate uppercase">{currentName}</span>
        {user.acting_as_club && (
          <span className="text-[8px] px-1 py-px rounded shrink-0" style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}>
            ACTING
          </span>
        )}
        <svg className="w-3 h-3 shrink-0 opacity-60" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute right-0 mt-1.5 w-72 bg-pb-surface border pb-hairline rounded-lg shadow-xl z-50 overflow-hidden">
          <div className="px-3 py-2 border-b pb-hairline-b">
            <div className="font-mono text-[9px] tracking-wide3 text-pb-faint uppercase mb-1.5">Managing club</div>
            <input
              autoFocus
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search clubs…"
              className="w-full bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-xs focus:outline-none focus:border-pb-accent"
            />
          </div>

          {user.acting_as_club && (
            <button
              disabled={busy}
              onClick={() => pick(null)}
              className="w-full text-left px-3 py-2 text-xs text-pb-faint hover:bg-pb-surface2 transition-colors border-b pb-hairline-b disabled:opacity-50"
            >
              ↩ Return to home club{user.home_club_name ? ` (${user.home_club_name})` : ''}
            </button>
          )}

          <div className="max-h-72 overflow-y-auto">
            {clubs === null && (
              <div className="px-3 py-3 font-mono text-[11px] text-pb-faint">Loading…</div>
            )}
            {clubs !== null && filtered.length === 0 && (
              <div className="px-3 py-3 font-mono text-[11px] text-pb-faint">No clubs found</div>
            )}
            {filtered.map(c => {
              const isCurrent = c.id === user.club_id
              return (
                <button
                  key={c.id}
                  disabled={busy || isCurrent}
                  onClick={() => pick(c.id)}
                  className={`w-full text-left px-3 py-2 hover:bg-pb-surface2 transition-colors flex items-center justify-between gap-2 ${isCurrent ? 'bg-pb-surface2/60' : ''} disabled:cursor-default`}
                >
                  <span className="min-w-0">
                    <span className="block text-sm text-pb-text truncate">{c.name}</span>
                    <span className="block font-mono text-[10px] text-pb-faintest truncate">/{c.slug}</span>
                  </span>
                  <span className="flex items-center gap-1.5 shrink-0">
                    {!c.is_active && (
                      <span className="font-mono text-[8px] uppercase text-pb-faint border pb-hairline rounded px-1 py-px">Inactive</span>
                    )}
                    {isCurrent && (
                      <span className="text-xs" style={{ color: 'var(--pb-accent)' }}>✓</span>
                    )}
                  </span>
                </button>
              )
            })}
          </div>

          {error && (
            <div className="px-3 py-2 border-t pb-hairline-t font-mono text-[10px] text-pb-red">{error}</div>
          )}
        </div>
      )}
    </div>
  )
}
