// The medal picker that sits above the Votes tabs.
//
// A club counts votes towards one award or several — "Club Champion" on 3-2-1,
// a "Colts Medal" on 5-4-3-2-1 — and every tab below shows exactly one of them,
// so which medal is selected has to be visible and switchable from anywhere on
// the screen rather than buried in Settings.
//
// It draws nothing at all for a club with one medal and no rights to add
// another: a picker offering a single choice is just noise.
import { Btn } from '../ui'

export default function MedalBar({ medals = [], medalId, onSelect, onAdd, canManage }) {
  if (medals.length <= 1 && !canManage) return null
  if (medals.length <= 1 && !onAdd) return null

  return (
    <div className="flex flex-wrap items-center gap-1.5 mb-4">
      {medals.map((m) => {
        const active = m.medal_id === medalId
        return (
          <button
            key={m.medal_id}
            onClick={() => onSelect(m.medal_id)}
            className={`px-3 py-1.5 rounded-full text-[13px] font-medium transition-colors border pb-hairline ${
              active
                ? 'bg-pb-accent text-pb-on-accent border-transparent'
                : 'bg-pb-surface2 text-pb-faint hover:text-pb-text'
            }`}
            title={m.grade_names?.length ? m.grade_names.join(', ') : 'Every grade'}
          >
            {m.medal_name}
            {!m.enabled && (
              <span className={`ml-1.5 text-[10px] ${active ? 'opacity-70' : 'text-pb-faintest'}`}>
                off
              </span>
            )}
          </button>
        )
      })}
      {canManage && onAdd && (
        <Btn sm variant="ghost" onClick={onAdd}>+ New medal</Btn>
      )}
    </div>
  )
}
