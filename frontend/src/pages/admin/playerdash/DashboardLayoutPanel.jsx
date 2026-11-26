// BetterStats > Player Dashboard > Card order: the order of every card on the player's dashboard
// grid, the built-in sections and the club's own modules together. Two across on a wide screen
// (read left to right, then down), one column on a phone. A card players cannot see right now
// stays in the list, greyed, so its place is kept for when it comes back.
import { Btn } from '../betterselect/ui'

export default function DashboardLayoutPanel({ layout, busy, onChange }) {
  const ids = layout.map((c) => c.id)
  const move = (i, dir) => {
    const j = i + dir
    if (j < 0 || j >= ids.length) return
    const next = [...ids]
    ;[next[i], next[j]] = [next[j], next[i]]
    onChange(next)
  }
  return (
    <div data-dashboard-layout className="pt-4 border-t pb-hairline">
      <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1">Card order</div>
      <p className="text-[12px] text-pb-faintest mb-1.5">
        The order of the cards on a player's dashboard. On a wide screen they sit two across, read left to right; on a phone, one under the other. A section with nothing in it for a player drops out for them.
      </p>
      {layout.map((c, i) => (
        <div key={c.id} data-layout-row={c.id} data-shown={c.shown ? 'yes' : 'no'}
          className={`flex items-center gap-3 py-2 border-t pb-hairline first:border-t-0 ${c.shown ? '' : 'opacity-60'}`}>
          <span className="w-6 text-right font-mono text-[11px] text-pb-faint shrink-0">{i + 1}</span>
          <div className="min-w-0 flex-1">
            <div className="text-[13.5px] font-semibold break-words">
              {c.type === 'custom' && c.emoji ? `${c.emoji} ` : ''}{c.label}
            </div>
            <div className="text-[12px] text-pb-faint">
              {c.type === 'custom' ? `Your module · ${c.kind_label}` : 'Built-in'}
              {c.note ? ` · Not showing. ${c.note}` : ''}
            </div>
          </div>
          <div className="flex shrink-0 gap-1">
            <Btn sm disabled={busy || i === 0} onClick={() => move(i, -1)} title="Move up" aria-label={`Move ${c.label} up`}>↑</Btn>
            <Btn sm disabled={busy || i === layout.length - 1} onClick={() => move(i, 1)} title="Move down" aria-label={`Move ${c.label} down`}>↓</Btn>
          </div>
        </div>
      ))}
    </div>
  )
}
