import { AVAIL_META, Avatar, roleText } from './shared'

// The picked XI, in batting order. Drag-to-reorder + captain/keeper/remove. All
// mutation lives in the container (it owns `picked` and the drag ref); this just
// renders and reports intent via the on* callbacks.
export default function TeamSheet({ picked, poolById, canEdit, onDragStart, onDragOver, onDrop, onToggleFlag, onRemove }) {
  return (
    <div className="pb-card overflow-hidden">
      <div className="px-4 py-2.5 border-b pb-hairline flex items-center justify-between">
        <h3 className="font-mono text-[11px] uppercase tracking-wide2 text-pb-faint">Team sheet · {picked.length}</h3>
        {canEdit && picked.length > 1 && <span className="font-mono text-[9px] text-pb-faintest">drag to reorder</span>}
      </div>
      <div className="overflow-auto max-h-[62vh]">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-pb-faintest font-mono text-[9px] uppercase tracking-wide2">
              <th className="text-left px-2 py-1.5 w-8">#</th>
              <th className="text-left px-1 py-1.5 w-8">AVL</th>
              <th className="text-left px-1 py-1.5">Player</th>
              <th className="text-left px-1 py-1.5">Roles</th>
              {canEdit && <th className="px-1 py-1.5 w-24"></th>}
            </tr>
          </thead>
          <tbody>
            {picked.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-pb-faint">Add players from the pool →</td></tr>
            )}
            {picked.map((sel, i) => {
              const p = poolById[sel.player_id]
              if (!p) return null
              const m = AVAIL_META[p.availability] || AVAIL_META.NO_RESPONSE
              return (
                <tr key={sel.player_id}
                  draggable={canEdit}
                  onDragStart={() => onDragStart(i)}
                  onDragOver={onDragOver}
                  onDrop={() => onDrop(i)}
                  className={`border-t pb-hairline ${canEdit ? 'cursor-grab active:cursor-grabbing' : ''}`}>
                  <td className="px-2 py-1.5 font-mono text-[11px] text-pb-faintest">{i + 1}</td>
                  <td className="px-1 py-1.5"><span className={`inline-block w-2.5 h-2.5 rounded-full ${m.dot}`} title={m.label} /></td>
                  <td className="px-1 py-1.5">
                    <span className="flex items-center gap-2 min-w-0">
                      {canEdit && <span className="text-pb-faintest text-xs">⠿</span>}
                      <Avatar p={p} />
                      <span className="truncate">
                        {p.display_name}
                        {(sel.is_captain || sel.is_wicket_keeper) && (
                          <span className="ml-1.5 font-mono text-[9px] text-pb-accent">{[sel.is_captain && '(C)', sel.is_wicket_keeper && '(WK)'].filter(Boolean).join(' ')}</span>
                        )}
                      </span>
                    </span>
                  </td>
                  <td className="px-1 py-1.5 text-pb-faint text-xs">{roleText(p)}</td>
                  {canEdit && (
                    <td className="px-1 py-1.5">
                      <span className="flex items-center justify-end gap-1">
                        <button onClick={() => onToggleFlag(sel.player_id, 'is_captain')}
                          className={`font-mono text-[10px] px-1 rounded border ${sel.is_captain ? 'bg-pb-accent/15 text-pb-accent border-pb-accent/40' : 'pb-hairline text-pb-faintest'}`} title="Captain">C</button>
                        <button onClick={() => onToggleFlag(sel.player_id, 'is_wicket_keeper')}
                          className={`font-mono text-[10px] px-1 rounded border ${sel.is_wicket_keeper ? 'bg-pb-accent/15 text-pb-accent border-pb-accent/40' : 'pb-hairline text-pb-faintest'}`} title="Keeper">WK</button>
                        <button onClick={() => onRemove(sel.player_id)} className="text-pb-faintest hover:text-pb-red text-xs" title="Remove">✕</button>
                      </span>
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
