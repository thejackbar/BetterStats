import { MILESTONE_WINDOWS, milestoneUnit, milestoneValueText, formatMilestoneDate, visibleMilestones } from '../../../social/milestoneItems'
import { MILESTONE_MAX } from '../../../social/milestone-templates'
import { useAdminNameFormat } from '../../../lib/useAdminNameFormat'

// The milestones to feature on a post: pick a window, then tick or untick. Ticking
// order is the order on the post. Everything the club has recorded is listed; the
// window only narrows what is shown, so a tick made under one window survives a
// change to another.
export default function MilestonePicker({ status, rows, picks, windowKey, search, onWindow, onSearch, onToggle, onTickShown, onClear, onLoad }) {
  const fmt = useAdminNameFormat()
  const shown = visibleMilestones(rows, windowKey, search)
  const picked = new Set(picks)
  const full = picks.length >= MILESTONE_MAX
  return (
    <div data-testid="milestone-picker">
      {status === 'loading' && <p className="font-mono text-[10px] text-pb-faint">Loading milestones…</p>}
      {status && status !== 'loading' && status !== 'ok' && (
        <div className="mb-2">
          <p className="font-mono text-[10px] text-amber-400">Could not load milestones: {status}</p>
          <button onClick={onLoad} className="mt-1.5 px-3 py-1.5 rounded text-xs font-mono tracking-wide2" style={{ background: 'var(--pb-accent)', color: 'var(--pb-bg)' }}>Try again</button>
        </div>
      )}
      {status === 'ok' && (
        <>
          <div className="flex flex-wrap gap-1.5 mb-2" role="group" aria-label="Milestones from">
            {MILESTONE_WINDOWS.map((w) => (
              <button key={w.key} type="button" onClick={() => onWindow(w.key)} aria-pressed={windowKey === w.key}
                className={`font-mono text-[10px] tracking-wide2 px-2 py-1 rounded border pb-hairline transition-colors ${windowKey === w.key ? '' : 'text-pb-faint hover:text-pb-text'}`}
                style={windowKey === w.key ? { borderColor: 'var(--pb-accent)', color: 'var(--pb-accent)' } : {}}>{w.label}</button>
            ))}
          </div>
          <input value={search} onChange={(e) => onSearch(e.target.value)} placeholder="Search a player"
            className="w-full min-w-0 bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-xs text-pb-text placeholder:text-pb-faintest mb-2" />
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mb-2">
            <span className="font-mono text-[10px] text-pb-dim" data-testid="milestone-count">{picks.length} of {MILESTONE_MAX} ticked</span>
            <button type="button" onClick={() => onTickShown(shown)} disabled={shown.length === 0}
              className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text disabled:opacity-40">Tick shown</button>
            <button type="button" onClick={onClear} disabled={picks.length === 0}
              className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text disabled:opacity-40">Untick all</button>
          </div>
          {full && <p className="font-mono text-[9px] text-amber-400 mb-2">The post holds {MILESTONE_MAX} milestones. Untick one to add another.</p>}
          {shown.length === 0 ? (
            <p className="text-[11px] text-pb-faint leading-relaxed" data-testid="milestone-empty">
              {rows.length === 0
                ? 'No milestones are recorded for the club yet. They appear here after a sync.'
                : windowKey === 'all' || search
                  ? 'No milestones match that search.'
                  : 'No milestones with a date in this window. Pick a longer one, or All time to include milestones without a date.'}
            </p>
          ) : (
            <div className="flex flex-col max-h-72 overflow-auto pb-scroll border pb-hairline rounded">
              {shown.map((r) => {
                const on = picked.has(r.key)
                const disabled = !on && full
                return (
                  <label key={r.key} data-testid="milestone-row"
                    className={`flex items-center gap-2 px-2.5 py-1.5 border-b pb-hairline last:border-0 ${disabled ? 'opacity-45' : 'cursor-pointer hover:bg-pb-surface2'}`}>
                    <input type="checkbox" checked={on} disabled={disabled} onChange={() => onToggle(r.key)} className="shrink-0" />
                    <span className="flex-1 min-w-0">
                      <span className="block text-xs text-pb-text truncate">{fmt(r.player_name)}</span>
                      <span className="block font-mono text-[10px] text-pb-faint truncate">{milestoneValueText(r)} · {milestoneUnit(r)}</span>
                    </span>
                    <span className="font-mono text-[10px] text-pb-faintest shrink-0">{formatMilestoneDate(r.achieved_at) || 'no date'}</span>
                  </label>
                )
              })}
            </div>
          )}
        </>
      )}
    </div>
  )
}
MilestonePicker.displayName = 'MilestonePicker'
