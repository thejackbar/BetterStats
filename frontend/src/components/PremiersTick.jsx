import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useAuth } from '../contexts/AuthContext'
import { CAP } from '../lib/capabilities'

// A club admin ticks a match as a premiership the club won: the match-page shortcut for the admin
// Premierships screen's "Grand final, we won" tag (club_match_tags). For a decider Cricket Australia does
// not call a grand final (a "Round 16") or a final washed out and won on the ladder. The server writes the
// flag for everyone on the team sheet (services/premierships.py) and links it to this match, so the
// banner and the Premierships page follow. A match tagged another way on that screen shows as such here.
// Hidden for anyone who cannot manage awards, and for a match that is not the signed-in club's.
export default function PremiersTick({ gameId, onChanged }) {
  const { user, hasCapability } = useAuth()
  const clubId = user?.club_id
  const allowed = !!clubId && hasCapability(CAP.MANAGE_AWARDS)
  const [state, setState] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  useEffect(() => {
    if (!allowed) return undefined
    let live = true
    api.getMatchTag(clubId, gameId)
      .then(s => { if (live) setState(s) })
      .catch(() => { if (live) setState(null) })   // not this club's match: show nothing
    return () => { live = false }
  }, [allowed, clubId, gameId])

  if (!allowed || !state) return null

  async function toggle(on) {
    if (!on && !window.confirm(
      'Take the premiership tag off this match? Premiership honours written because of it are removed. '
      + 'Flags your club typed by hand stay, unlinked from the match.')) return
    setBusy(true); setErr(null)
    try {
      const s = await api.setMatchTag(clubId, gameId, on ? 'grand_final' : null, on)
      setState(s)
      onChanged?.()
    } catch (e) {
      setErr(e.message || 'That did not save.')
    } finally {
      setBusy(false)
    }
  }

  const marked = state.kind === 'grand_final' && state.won
  let note = null
  if (state.kind && !marked) {
    note = state.kind === 'grand_final'
      ? 'Tagged as the grand final on the Premierships screen; the result on the card decides the flag.'
      : `Tagged as ${state.kind === 'final' ? 'a final' : 'a normal game'} on the Premierships screen.`
    if (state.kind === 'grand_final' && state.players) note += ` Premiership recorded for ${state.players} players.`
  } else if (marked && state.players) {
    note = `Premiership recorded for ${state.players} player${state.players === 1 ? '' : 's'} from this match.`
  } else if (marked && state.reason) {
    note = `Ticked, but no flag could be written: ${state.reason}.`
  }

  return (
    <div data-testid="premiers-tick" className="mb-5 -mt-2 flex flex-wrap items-start gap-x-3 gap-y-1 text-[12px]">
      <div className="flex items-start gap-2">
        <input id="premiers-tick" type="checkbox" className="mt-0.5" checked={marked} disabled={busy}
          onChange={e => toggle(e.target.checked)} />
        <label htmlFor="premiers-tick" className="text-pb-dim">
          Premiers: our club won the premiership in this match
          {!marked && (
            <span className="block text-[11px] text-pb-faint">
              For a grand final the automatic premierships missed. Everyone on the team sheet gets the flag.
            </span>
          )}
        </label>
      </div>
      {note && <p className="text-[11px] text-pb-faint basis-full pl-6">{note}</p>}
      {err && <p className="text-[11px] text-pb-red basis-full pl-6">{err}</p>}
    </div>
  )
}
