import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../../lib/api'
import { money, kindLabel, Pill, Icon } from './ui'

// Admin-only strip shown at the bottom of the player profile modal: what kit the
// player holds and what they owe for merch. Never on the public profile. Render
// only when the club holds the BetterMerch module and the viewer can manage it.
export default function PlayerMerchPanel({ playerId }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(false)

  useEffect(() => {
    let live = true
    setData(null); setErr(false)
    api.merchPlayer(playerId)
      .then((d) => { if (live) setData(d) })
      .catch(() => { if (live) setErr(true) })
    return () => { live = false }
  }, [playerId])

  if (err) return null
  // Hide entirely when the player has no merch history — keeps the profile clean.
  if (data && data.movements.length === 0 && !data.outstanding) return null

  return (
    <div className="px-5 py-4 border-t border-pb-hairline" style={{ background: 'color-mix(in srgb, var(--pb-accent) 4%, transparent)' }}>
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          <Icon name="list" size={15} className="text-pb-accent" />
          <span className="font-mono text-[10px] tracking-wide2 text-pb-faint uppercase">Merch</span>
        </div>
        {data && data.outstanding > 0 && <Pill tone="amber">owes {money(data.outstanding)}</Pill>}
      </div>
      {!data ? (
        <div className="text-[12px] text-pb-faint">Loading…</div>
      ) : (
        <ul className="space-y-1">
          {data.movements.slice(0, 6).map((m) => (
            <li key={m.id} className="flex items-center justify-between gap-2 text-[12.5px]">
              <span className="truncate">{m.product_name}<span className="text-pb-faint"> · {m.variant_label}</span> <span className="text-pb-faintest">({kindLabel(m.kind)})</span></span>
              {m.amount != null && (m.paid ? <Pill tone="green">paid</Pill> : <Pill tone="amber">{money(m.amount)} owing</Pill>)}
            </li>
          ))}
          {data.movements.length > 6 && (
            <li>
              <Link to={`/admin/merch/activity`} className="text-[11.5px] text-pb-faint hover:text-pb-accent">View all in BetterMerch →</Link>
            </li>
          )}
        </ul>
      )}
    </div>
  )
}
