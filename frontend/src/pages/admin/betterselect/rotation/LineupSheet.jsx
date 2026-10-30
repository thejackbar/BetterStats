// Junior Rotation: one lineup, drawn the same everywhere. The coach's print page
// and the parents' link both hand it plain names, so neither can show more than
// the other was given. Key positions say KEY in words as well as a tint.
//
// batting: ['Sam T.', ...] first to bat first
// changes: [{ slots: [{ position, key, name }], resting: ['Ava B.'] }, ...]

export function formatRoundDate(iso) {
  if (!iso) return ''
  try { return new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }) }
  catch { return iso }
}

export default function LineupSheet({ batting = [], changes = [], bats = true, className = '' }) {
  const showBatting = bats && batting.length > 0
  return (
    <div className={`grid gap-6 ${showBatting && changes.length ? 'md:grid-cols-2' : ''} ${className}`}>
      {showBatting && (
        <section data-batting-order>
          <h3 className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-2">Batting order</h3>
          <ol className="divide-y divide-pb-hairline border border-pb-hairline rounded-lg overflow-hidden">
            {batting.map((name, i) => (
              <li key={`${i}-${name}`} data-bat-row className="flex items-center gap-3 px-3 py-2">
                <span className="w-6 text-right font-display font-bold pb-num text-pb-faint">{i + 1}</span>
                <span className="font-display font-semibold text-[15px] min-w-0 break-words">{name}</span>
              </li>
            ))}
          </ol>
        </section>
      )}
      {changes.length > 0 && (
        <section className="flex flex-col gap-4 min-w-0">
          {changes.map((change, ci) => (
            <div key={ci} data-field-change>
              <h3 className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-2">
                {changes.length > 1 ? `Fielding, change ${ci + 1}` : 'Fielding'}
              </h3>
              <ul className="divide-y divide-pb-hairline border border-pb-hairline rounded-lg overflow-hidden">
                {change.slots.map((s) => (
                  <li key={s.position} data-slot className="flex items-center gap-3 px-3 py-2">
                    <span className="w-32 shrink-0 text-[13px] text-pb-dim flex items-center gap-1.5 min-w-0">
                      <span className="truncate">{s.position}</span>
                      {s.key && <span className="font-mono text-[9px] font-bold tracking-wide2 text-pb-accent">KEY</span>}
                    </span>
                    <span className={`font-display font-semibold text-[15px] min-w-0 break-words ${s.name ? '' : 'text-pb-faint font-normal italic'}`}>
                      {s.name || 'Nobody'}
                    </span>
                  </li>
                ))}
              </ul>
              {change.resting.length > 0 && (
                <p data-resting className="text-[13px] text-pb-dim mt-2">
                  <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mr-1.5">Resting</span>
                  {change.resting.join(', ')}
                </p>
              )}
            </div>
          ))}
        </section>
      )}
    </div>
  )
}

// A stored round (ids) into the plain shape above, with the group's own names.
export function roundToLineup(round, group, players) {
  const name = new Map(players.map((p) => [p.id, p.name]))
  const positions = group.positions || []
  const changes = (round.fielding || []).map((change) => ({
    slots: positions.map((pos) => {
      const who = Object.keys(change).find((k) => change[k] === pos.id)
      return { position: pos.name, key: !!pos.key, name: who ? name.get(who) : null }
    }),
    resting: Object.keys(change).filter((k) => change[k] === null && name.has(k)).map((k) => name.get(k)),
  }))
  return {
    batting: (round.batting_order || []).filter((id) => name.has(id)).map((id) => name.get(id)),
    changes,
  }
}
