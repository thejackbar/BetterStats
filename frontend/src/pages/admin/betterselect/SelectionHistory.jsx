// The audit trail for one side: who confirmed, locked or unlocked it, who was
// called up out of it, and the players each time. A selector can read a version
// back and load it onto the board (it is only a draft until they confirm it).
import { useEffect, useState } from 'react'
import { api } from '../../../lib/api'
import { useAdminNameFormat } from '../../../lib/useAdminNameFormat'
import { Icon, Btn } from './ui'

const when = (iso) => {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })
  } catch { return iso }
}

const LABEL = {
  confirmed: 'Confirmed the side',
  locked: 'Locked the side',
  unlocked: 'Unlocked the side',
  called_up_out: 'Player called up out of this side',
}

function summary(ev, fmt) {
  const d = ev.detail || {}
  const names = (xs) => (xs || []).map((n) => fmt(n)).join(', ')
  const bits = []
  if (ev.action === 'confirmed' || ev.action === 'called_up_out') {
    if (d.added?.length) bits.push(`In: ${names(d.added)}`)
    if (d.removed?.length) bits.push(`Out: ${names(d.removed)}`)
    if (d.captain) bits.push(`Captain: ${fmt(d.captain)}`)
    if (d.keeper) bits.push(`Keeper: ${fmt(d.keeper)}`)
    if (d.reordered) bits.push('Batting order changed')
    if (!bits.length) bits.push('No change to the players')
    if (ev.action === 'confirmed' && d.locked) bits.push('Locked')
  } else if (d.after?.length) {
    bits.push(`${d.after.length} players`)
  }
  return bits.join(' · ')
}

export default function SelectionHistory({ fixtureId, title, canRestore, onRestore, onClose }) {
  const fmt = useAdminNameFormat()
  const [events, setEvents] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let live = true
    api.bsSelectionHistory(fixtureId)
      .then((r) => { if (live) setEvents(r.events || []) })
      .catch((e) => { if (live) { setError(e.message); setEvents([]) } })
    return () => { live = false }
  }, [fixtureId])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} data-selection-history
        className="w-[560px] max-w-full max-h-[86%] flex flex-col bg-pb-surface rounded-2xl border border-pb-hairline2 overflow-hidden shadow-2xl">
        <div className="flex items-center justify-between px-5 py-3 border-b pb-hairline">
          <h3 className="font-mono text-[11px] uppercase tracking-wide3 text-pb-faint min-w-0 truncate">Selection history{title ? ` · ${title}` : ''}</h3>
          <button onClick={onClose} className="text-pb-faint hover:text-pb-text shrink-0" aria-label="Close"><Icon name="close" size={16} /></button>
        </div>
        <div className="overflow-auto pb-scroll p-3">
          {events === null && <div className="p-6 text-center text-pb-faint text-sm">Loading…</div>}
          {error && <div className="p-4 text-pb-red text-sm">{error}</div>}
          {events && !events.length && !error && (
            <div className="p-6 text-center text-pb-faint text-sm">Nothing recorded yet. Changes to this side from now on will show here.</div>
          )}
          <ul className="flex flex-col gap-2">
            {(events || []).map((ev) => (
              <li key={ev.id} data-history-row={ev.action} className="rounded-lg border border-pb-hairline bg-pb-surface2 px-3 py-2">
                <div className="flex flex-wrap items-baseline gap-x-2">
                  <span className="font-display font-semibold text-[13px]">{LABEL[ev.action] || ev.action}</span>
                  <span className="text-[11.5px] text-pb-faint">{ev.by || 'Someone'} · {when(ev.at)}</span>
                </div>
                <div className="text-[12.5px] text-pb-dim mt-0.5">{summary(ev, fmt)}</div>
                {canRestore && ev.detail?.after?.length > 0 && ev.action !== 'called_up_out' && (
                  <div className="mt-1.5">
                    <Btn variant="ghost" sm icon="reset" onClick={() => onRestore(ev)}>Load this side onto the board</Btn>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
