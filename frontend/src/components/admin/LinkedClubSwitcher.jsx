import { useState, useRef } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import Dropdown from '../Dropdown'

// Module level on purpose: a component declared inside the render function is a
// new component every render, so it remounts.
function Tick() {
  return <span className="text-xs shrink-0" style={{ color: 'var(--pb-accent)' }}>✓</span>
}
function HomeTag() {
  return (
    <span className="font-mono text-[8px] uppercase text-pb-faint border pb-hairline rounded px-1 py-px shrink-0">Home</span>
  )
}

// Club Admin switcher for LINKED clubs. A Super Admin links clubs together
// (Better HQ > Clubs & Data > Linked Clubs); every Club Admin of a linked club
// then sees the group here and can choose which club they are working in.
//
// Renders nothing for a club that is not linked to another open club, so a
// club with no link never sees it. The list comes from /auth/me
// (`linked_clubs`, home club first), so there is nothing to fetch. This is
// separate from ClubSwitcher, which is the Better staff switcher over every club.
//
//   variant="bar"   compact dropdown for the header and the mobile drawer
//   variant="card"  the dashboard panel, one button per club
export default function LinkedClubSwitcher({ variant = 'bar' }) {
  const { user, switchClub } = useAuth()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const wrapRef = useRef(null)

  const clubs = Array.isArray(user?.linked_clubs) ? user.linked_clubs : []
  if (user?.role !== 'club_admin' || clubs.length < 2) return null

  const current = clubs.find(c => c.is_current) || clubs.find(c => c.is_home) || clubs[0]

  const pick = async (club) => {
    if (busy || club.is_current) return
    setBusy(true)
    setError('')
    try {
      // The home club is the cleared state, so send null for it. The switch
      // hard-reloads into the dashboard so every page refetches for that club.
      await switchClub(club.is_home ? null : club.id)
    } catch (e) {
      setError(e?.message || 'Could not switch club')
      setBusy(false)
    }
  }

  if (variant === 'card') {
    return (
      <section
        className="border pb-hairline rounded-lg bg-pb-surface px-4 py-3 mb-5"
        aria-label="Your clubs"
        data-testid="linked-clubs-card"
      >
        <div className="font-mono text-[9px] tracking-wide3 text-pb-faint uppercase mb-1">Your clubs</div>
        <p className="text-pb-faint text-xs mb-3">
          You look after more than one club. Pick the club you want to work in.
        </p>
        <div className="flex flex-wrap gap-2">
          {clubs.map(c => (
            <button
              key={c.id}
              type="button"
              disabled={busy || c.is_current}
              onClick={() => pick(c)}
              aria-pressed={!!c.is_current}
              className={`min-w-0 max-w-full flex items-center gap-2 rounded border pb-hairline px-3 py-2 text-left text-sm transition-colors disabled:cursor-default ${
                c.is_current ? 'bg-pb-surface2 text-pb-text' : 'text-pb-faint hover:bg-pb-surface2 hover:text-pb-text'
              }`}
              style={c.is_current ? { borderColor: 'var(--pb-accent)' } : undefined}
            >
              <span className="min-w-0 truncate">{c.name}</span>
              {c.is_home && <HomeTag />}
              {c.is_current && <Tick />}
            </button>
          ))}
        </div>
        {error && <div className="mt-2 font-mono text-[10px] text-pb-red" role="alert">{error}</div>}
      </section>
    )
  }

  return (
    <div ref={wrapRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        title="Switch which of your clubs you are working in"
        aria-haspopup="listbox"
        aria-expanded={open}
        data-testid="linked-club-switcher"
        className="flex items-center gap-1.5 font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors border pb-hairline rounded px-2.5 py-1.5 max-w-[180px]"
      >
        <svg className="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8 7h12m0 0l-4-4m4 4l-4 4M16 17H4m0 0l4-4m-4 4l4 4" />
        </svg>
        <span className="truncate uppercase">{current.name}</span>
        <svg className="w-3 h-3 shrink-0 opacity-60" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      <Dropdown
        anchorRef={wrapRef}
        open={open}
        onClose={() => setOpen(false)}
        align="end"
        width={260}
        gap={6}
        className="bg-pb-surface border pb-hairline rounded-lg shadow-xl overflow-hidden"
      >
        <div className="px-3 py-2 border-b pb-hairline-b font-mono text-[9px] tracking-wide3 text-pb-faint uppercase">
          Your clubs
        </div>
        <div className="max-h-72 overflow-y-auto" role="listbox">
          {clubs.map(c => (
            <button
              key={c.id}
              type="button"
              role="option"
              aria-selected={!!c.is_current}
              disabled={busy || c.is_current}
              onClick={() => pick(c)}
              className={`w-full text-left px-3 py-2 hover:bg-pb-surface2 transition-colors flex items-center justify-between gap-2 disabled:cursor-default ${c.is_current ? 'bg-pb-surface2/60' : ''}`}
            >
              <span className="min-w-0 text-sm text-pb-text truncate">{c.name}</span>
              <span className="flex items-center gap-1.5 shrink-0">
                {c.is_home && <HomeTag />}
                {c.is_current && <Tick />}
              </span>
            </button>
          ))}
        </div>
        {error && <div className="px-3 py-2 border-t pb-hairline-t font-mono text-[10px] text-pb-red">{error}</div>}
      </Dropdown>
    </div>
  )
}
