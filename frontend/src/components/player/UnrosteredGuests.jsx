// Guests from recent net sessions who aren't on the club's roster.
//
// A guest row is written two ways: a manager types a name on the live nets
// screen, or somebody scans the QR code and registers. The second kind lands in
// Nets → Check-in with the details they gave. The FIRST kind had nowhere to go —
// they turned up week after week and could only become a player by an admin
// retyping them by hand, which left every night they had already attended
// stranded on rows nothing would read.
//
// This is that missing path, and it lives on the Players screens rather than
// inside Nets because a person who keeps turning up is a roster question.
// Mounted on BOTH (BetterStats → Players and BetterSelect → Players) — an admin
// shouldn't have to know which of the two owns it.
import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { useToast } from '../../contexts/ToastContext'
import { api } from '../../lib/api'
import { CAP } from '../../lib/capabilities'
import { Btn, Icon } from '../../pages/admin/betterselect/ui'

function fmtDate(d) {
  if (!d) return ''
  try { return new Date(d + 'T00:00:00').toLocaleDateString(undefined, { day: 'numeric', month: 'short' }) }
  catch { return d }
}

export default function UnrosteredGuests({ onPromoted }) {
  const { hasModule, hasCapability } = useAuth()
  const toast = useToast()
  // Guests only exist because of net sessions, and the endpoint sits behind
  // require_module("select") — so a club without BetterSelect is never sent to
  // an endpoint that would 402 at it.
  const entitled = hasModule?.('select')
  const canEdit = hasCapability(CAP.MANAGE_PLAYERS) || hasCapability(CAP.MANAGE_SELECTIONS)

  const [data, setData] = useState(null)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(null)
  const [matching, setMatching] = useState(null)   // guest key being matched
  const [q, setQ] = useState('')
  const [roster, setRoster] = useState([])

  const load = useCallback(() => {
    if (!entitled) return
    api.nmUnresolvedGuests()
      .then(setData)
      // A club with the module but no nets yet is an ordinary state, not an
      // error worth a toast on a screen that is about something else.
      .catch(() => setData({ guests: [], pending_registrations: 0 }))
  }, [entitled])
  useEffect(() => { load() }, [load])

  // Fetched once, only when somebody actually goes looking for a match.
  useEffect(() => {
    if (!matching || roster.length) return
    api.nmRoster().then((r) => setRoster(r.players || [])).catch(() => setRoster([]))
  }, [matching, roster.length])

  const matches = useMemo(() => {
    const s = q.trim().toLowerCase()
    if (!s) return roster.slice(0, 8)
    return roster.filter((p) => (p.name || '').toLowerCase().includes(s)).slice(0, 8)
  }, [roster, q])

  const promote = async (key, opts, okMsg) => {
    setBusy(key)
    try {
      const r = await api.nmPromoteGuest(key, opts)
      const moved = r.sessions_moved === 1 ? '1 session' : `${r.sessions_moved} sessions`
      toast.success(`${okMsg(r)}, ${moved} moved across`)
      setMatching(null); setQ('')
      load()
      onPromoted?.()
    } catch (e) {
      toast.error(e.message || 'That didn’t work')
    } finally { setBusy(null) }
  }

  if (!entitled || !data) return null
  const guests = data.guests || []
  const pending = data.pending_registrations || 0
  // Nothing to decide, so nothing on screen: a panel that can only ever say
  // "everyone is on the list" is worse than no panel.
  if (!guests.length && !pending) return null

  return (
    <div className="pb-card mb-4">
      <button onClick={() => setOpen((o) => !o)} className="w-full flex items-center gap-3 px-4 py-3 text-left">
        <span className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: 'color-mix(in srgb, var(--pb-amber) 14%, transparent)', color: 'var(--pb-amber)' }}>
          <Icon name="nets" size={17} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="font-display font-bold text-[15px] flex items-center gap-2">
            Not on the roster
            {guests.length > 0 && (
              <span className="font-mono text-[10px] px-2 py-0.5 rounded-full"
                style={{ background: 'color-mix(in srgb, var(--pb-amber) 16%, transparent)', color: 'var(--pb-amber)' }}>
                {guests.length}
              </span>
            )}
          </div>
          <div className="text-[12.5px] text-pb-faint mt-0.5">
            {guests.length > 0
              ? `${guests.length === 1 ? 'Someone has' : `${guests.length} people have`} been to nets in the last 90 days without being on the list.`
              : 'Everyone at recent nets is on the list.'}
          </div>
        </div>
        <span className="text-pb-faint shrink-0">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 border-t pb-hairline pt-4 flex flex-col gap-2.5">
          {pending > 0 && (
            <div className="text-[12.5px] rounded-lg px-3 py-2 mb-1"
              style={{ background: 'color-mix(in srgb, var(--pb-accent) 10%, transparent)' }}>
              {pending === 1 ? 'One person' : `${pending} people`} checked in and left their details.{' '}
              <Link to="/admin/betterselect/nets" className="underline text-pb-accent">
                Review them in Nets → Check-in
              </Link>
              , their mobile, email and date of birth are there, so they’re better added from that screen.
            </div>
          )}

          {guests.length === 0 && (
            <p className="text-sm text-pb-faint">Nobody else to sort out.</p>
          )}

          {guests.map((g) => (
            <div key={g.key} className="rounded-lg border pb-hairline px-3.5 py-3">
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div className="min-w-0">
                  <div className="font-display font-bold text-[15px]">{g.name}</div>
                  <div className="font-mono text-[10px] text-pb-faintest mt-1 uppercase tracking-wide2">
                    {g.attended} session{g.attended === 1 ? '' : 's'} · last {fmtDate(g.last_attended)}
                  </div>
                </div>
                {canEdit && (
                  <div className="flex items-center gap-2 shrink-0">
                    <Btn sm variant="primary" disabled={busy === g.key}
                      onClick={() => promote(g.key, {}, (r) => `${r.player_name} added`)}>
                      Add as a player
                    </Btn>
                    <Btn sm disabled={busy === g.key}
                      onClick={() => { setMatching(matching === g.key ? null : g.key); setQ('') }}>
                      Already on the list
                    </Btn>
                  </div>
                )}
              </div>

              {matching === g.key && (
                <div className="mt-3 pt-3 border-t pb-hairline">
                  <p className="text-[12.5px] text-pb-faint mb-2">
                    Point this at whoever they already are. Every net session they’ve been to moves onto that player.
                  </p>
                  <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search the roster…"
                    className="w-full bg-pb-surface2 border pb-hairline rounded-lg px-3 py-2 text-sm mb-2" />
                  <div className="flex flex-wrap gap-2">
                    {matches.map((p) => (
                      <Btn key={p.id} sm disabled={busy === g.key}
                        onClick={() => promote(g.key, { playerId: p.id }, () => `Matched to ${p.name}`)}>
                        {p.name}
                      </Btn>
                    ))}
                    {matches.length === 0 && (
                      <span className="text-[12.5px] text-pb-faintest">No players match “{q}”.</span>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}

          {!canEdit && guests.length > 0 && (
            <p className="text-[12.5px] text-pb-faintest">
              You can see who has been turning up, but adding them to the club needs the players or selections permission.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
