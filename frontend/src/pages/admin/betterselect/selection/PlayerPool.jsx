import { AVAIL_META, ROW_TINT, rowState, Avatar, roleText } from './shared'

// The pickable pool (already filtered + sorted by the container). Row-tinted by
// salient state; clicking a row adds the player (blocked rows can't be added).
export default function PlayerPool({ available, canEdit, onAdd }) {
  return (
    <div className="pb-card overflow-hidden">
      <div className="px-4 py-2.5 border-b pb-hairline">
        <h3 className="font-mono text-[11px] uppercase tracking-wide2 text-pb-faint">Available · {available.length}</h3>
      </div>
      <div className="overflow-auto max-h-[62vh]">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-pb-faintest font-mono text-[9px] uppercase tracking-wide2">
              <th className="text-left px-2 py-1.5 w-8">AVL</th>
              <th className="text-left px-1 py-1.5">Player</th>
              <th className="text-left px-1 py-1.5">Roles</th>
              <th className="text-left px-1 py-1.5">Squad</th>
            </tr>
          </thead>
          <tbody>
            {available.length === 0 && (
              <tr><td colSpan={4} className="px-4 py-8 text-center text-pb-faint">No players match these filters.</td></tr>
            )}
            {available.map(p => {
              const m = AVAIL_META[p.availability] || AVAIL_META.NO_RESPONSE
              const blocked = p.clash?.length > 0
              const tint = ROW_TINT[rowState(p)] || ''
              return (
                <tr key={p.id}
                  onClick={() => onAdd(p)}
                  title={blocked ? `Already picked for ${p.clash.join(', ')}` : undefined}
                  className={`border-t pb-hairline ${tint} ${canEdit && !blocked ? 'cursor-pointer hover:brightness-125' : blocked ? 'opacity-70 cursor-not-allowed' : ''}`}>
                  <td className="px-2 py-1.5"><span className={`inline-block w-2.5 h-2.5 rounded-full ${m.dot}`} title={m.label} /></td>
                  <td className="px-1 py-1.5">
                    <span className="flex items-center gap-2 min-w-0">
                      <Avatar p={p} />
                      <span className="truncate">
                        {p.display_name}
                        {p.is_dormant && <span className="ml-1.5 font-mono text-[9px] text-amber-300/70 uppercase">dormant</span>}
                        {blocked && <span className="ml-1.5 font-mono text-[9px] text-pb-red/90">⛔ {p.clash.join(', ')}</span>}
                      </span>
                    </span>
                  </td>
                  <td className="px-1 py-1.5 text-pb-faint text-xs">{roleText(p)}</td>
                  <td className="px-1 py-1.5 text-pb-faintest text-xs truncate max-w-[140px]">{p.squads?.join(' · ') || '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
