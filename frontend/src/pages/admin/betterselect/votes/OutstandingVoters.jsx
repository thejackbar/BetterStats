import { useState } from 'react'
import { useToast } from '../../../../contexts/ToastContext'
import { api } from '../../../../lib/api'
import { Avatar } from '../ui'

// Who is eligible to vote on this fixture but hasn't. Expects
// fixture.outstanding = [{ id, name, photo_url, channel }] where channel is
// 'email' | 'none' (this codebase has no SMS/WhatsApp send integration, so a
// nudge can only ever be an email reminder — see services/votes.py::send_nudge).
export default function OutstandingVoters({ fixture, onNudged }) {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const list = fixture?.outstanding || []

  const nudge = async (playerIds) => {
    setBusy(true)
    try {
      const r = await api.votesNudge(fixture.id, { player_ids: playerIds })
      const skipped = (r.failed || []).length
      toast.success(`Reminder sent to ${r.sent} player${r.sent === 1 ? '' : 's'}${skipped ? ` (${skipped} skipped)` : ''}`)
      onNudged?.()
    } catch (e) { toast.error(e.message) }
    finally { setBusy(false) }
  }

  if (!fixture) return null

  return (
    <div className="pb-card px-4 py-4">
      <div className="font-display font-bold text-[14.5px]">Still to vote</div>
      <div className="text-[12px] text-pb-faint mb-3">
        {fixture.round} v {fixture.opponent || 'TBC'} · {list.length} of {fixture.voters_expected || 0}
      </div>

      {list.length === 0 ? (
        <div className="text-sm text-pb-positive">Everyone's in. Nice.</div>
      ) : (
        <>
          <div className="flex flex-col">
            {list.map((p) => (
              <div key={p.id} className="flex items-center gap-2.5 py-2.5 border-t pb-hairline">
                <Avatar player={p} size={28} />
                <span className="text-[13.5px] flex-1 truncate">{p.name}</span>
                <span className="font-mono text-[10px] text-pb-faintest uppercase">
                  {p.channel === 'none' ? 'no email' : p.channel}
                </span>
              </div>
            ))}
          </div>
          <button onClick={() => nudge(list.map((p) => p.id))} disabled={busy}
            className="w-full mt-3.5 py-2.5 rounded-[10px] text-[13px] font-semibold disabled:opacity-50"
            style={{ background: 'var(--pb-amber)', color: 'var(--pb-bg)' }}>
            {busy ? 'Sending…' : `Nudge all ${list.length}`}
          </button>
        </>
      )}
    </div>
  )
}
