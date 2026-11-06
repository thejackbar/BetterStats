import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'

// A grand final the club won, on its own scorecard: which flag it was and a way into the
// Premierships page. Reads the honours the sync wrote from this game (services/premierships.py),
// so it shows for exactly the games the Premierships page links back to, and for no other.
export default function PremiershipBanner({ gameId, orgId }) {
  const [rows, setRows] = useState([])

  useEffect(() => {
    let live = true
    api.getGamePremierships(gameId)
      .then(r => { if (live) setRows(r?.premierships || []) })
      .catch(() => { if (live) setRows([]) })
    return () => { live = false }
  }, [gameId])

  if (!rows.length) return null
  // A grand final between two clubs that both recorded it: the club the visitor came from, else the first.
  const row = rows.find(r => r.org_id === orgId) || rows[0]
  const what = [row.team, row.season].filter(Boolean).join(' · ')

  return (
    <div data-testid="premiership-banner"
         className="pb-card mb-5 px-4 sm:px-5 py-3 flex flex-wrap items-baseline gap-x-4 gap-y-1"
         style={{ borderLeft: '3px solid var(--pb-accent)' }}>
      <span className="font-mono text-[10px] tracking-wide3 uppercase" style={{ color: 'var(--pb-accent)' }}>
        Premiership
      </span>
      <span className="text-[14px] text-pb-text">
        {row.club_name} won the {what ? `${what} ` : ''}grand final
        {row.players ? ` with ${row.players} player${row.players === 1 ? '' : 's'}` : ''}.
      </span>
      {row.slug && (
        <Link to={`/${row.slug}/premierships`}
              className="sm:ml-auto font-mono text-[11px] hover:underline whitespace-nowrap"
              style={{ color: 'var(--pb-accent)' }}>
          All premierships →
        </Link>
      )}
    </div>
  )
}
