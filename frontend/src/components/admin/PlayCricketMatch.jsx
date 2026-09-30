/**
 * Match a new player to their PlayCricket profile.
 *
 * A player created by hand has no Cricket Australia identity, so when they play
 * their first game the sync cannot find them and creates a SECOND player. The
 * one the club set up (the one in a squad, a lineup or a Fantasy team) then sits
 * empty. Picking the person here stores their PlayCricket id on the record, and
 * the first synced game lands on it.
 *
 * The admin has to make one of two choices before the form can be submitted:
 *   - pick a person and confirm they are joining THIS club, or
 *   - say they are not on PlayCricket yet.
 * `value` is null until they have, which is what lets a form hold its submit
 * button back. A person already in the roster is offered as "open that player",
 * never as a second record.
 *
 * value: null
 *      | { kind: 'linked', participant_id, name, clubs: [{id, name}] }
 *      | { kind: 'none' }
 */
import { useEffect, useRef, useState } from 'react'
import { api } from '../../lib/api'
import { useAuth } from '../../contexts/AuthContext'

const MIN_CHARS = 3
const DEBOUNCE_MS = 450

function Clubs({ clubs, ourId }) {
  const shown = (clubs || []).slice(0, 4)
  const more = (clubs || []).length - shown.length
  if (!shown.length) return <span className="text-[11px] text-pb-faintest">No clubs listed</span>
  return (
    <span className="flex flex-wrap gap-1">
      {shown.map((c) => (
        <span key={c.id}
          className="px-1.5 py-0.5 rounded text-[10.5px] bg-pb-surface2 border border-pb-hairline2 text-pb-dim">
          {c.name}
        </span>
      ))}
      {more > 0 && <span className="text-[10.5px] text-pb-faintest self-center">+{more} more</span>}
    </span>
  )
}

export default function PlayCricketMatch({ name = '', value, onChange, onUseExisting, compact = false, allowNone = true }) {
  const { user } = useAuth() || {}
  const clubName = user?.club_name || 'your club'
  const [q, setQ] = useState(name)
  const edited = useRef(false)
  const [state, setState] = useState({ loading: false, done: false, candidates: [], capped: false, error: '' })
  const [clubFilter, setClubFilter] = useState('')
  const [picked, setPicked] = useState(null) // the candidate being confirmed
  const reqId = useRef(0)

  // Follow the name being typed into the form until the admin types here.
  useEffect(() => { if (!edited.current) setQ(name) }, [name])

  useEffect(() => {
    const term = (q || '').trim()
    if (term.length < MIN_CHARS) { setState({ loading: false, done: false, candidates: [], capped: false, error: '' }); return }
    const id = ++reqId.current
    setClubFilter('')
    setState((s) => ({ ...s, loading: true, error: '' }))
    const t = setTimeout(() => {
      api.playerIdentitySearch(term)
        .then((r) => { if (id === reqId.current) setState({ loading: false, done: true, candidates: r.candidates || [], capped: !!r.capped, error: '' }) })
        .catch((e) => { if (id === reqId.current) setState({ loading: false, done: true, candidates: [], capped: false, error: e.message || 'Search failed' }) })
    }, DEBOUNCE_MS)
    return () => clearTimeout(t)
  }, [q])

  const linked = value?.kind === 'linked' ? value : null
  const none = value?.kind === 'none'

  // The club filter only exists (and only applies) for a capped search; a stale
  // value from an earlier search must never hide results behind a box that is not
  // on screen.
  const filtered = state.candidates.filter((c) => {
    const f = state.capped ? clubFilter.trim().toLowerCase() : ""
    return !f || (c.clubs || []).some((cl) => (cl.name || '').toLowerCase().includes(f))
  })

  const pick = (c) => { setPicked(c); if (value) onChange(null) }
  const confirm = (on) => {
    onChange(on && picked ? { kind: 'linked', participant_id: picked.participant_id, name: picked.name, clubs: picked.clubs } : null)
  }
  const chooseNone = (on) => { if (on) setPicked(null); onChange(on ? { kind: 'none' } : null) }

  const box = 'rounded-lg border border-pb-hairline bg-pb-surface2'

  return (
    <div className={`${box} ${compact ? 'p-3' : 'p-4'}`} data-testid="pc-match">
      <div className="flex items-center justify-between gap-2 mb-1">
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Match to PlayCricket</p>
        {(linked || none) && (
          <span className="font-mono text-[10px] tracking-wide2" style={{ color: 'var(--pb-accent)' }} data-testid="pc-match-done">
            {linked ? 'MATCHED' : 'NOT ON PLAYCRICKET YET'}
          </span>
        )}
      </div>
      <p className="text-[11.5px] text-pb-faint mb-2.5">
        Find them so their stats and games attach to this player, not a second copy created when they first play.
      </p>

      {linked ? (
        <div className="rounded-md border border-pb-hairline2 bg-pb-surface p-2.5 mb-2" data-testid="pc-match-linked">
          <div className="text-[13.5px] text-pb-text font-semibold">{linked.name}</div>
          <div className="mt-1"><Clubs clubs={linked.clubs} /></div>
          <button type="button" onClick={() => { setPicked(null); onChange(null) }}
            className="mt-2 text-[11.5px] underline text-pb-faint hover:text-pb-text">Choose someone else</button>
        </div>
      ) : picked ? (
        <div className="rounded-md border p-3 mb-2" style={{ borderColor: 'var(--pb-accent)' }} data-testid="pc-match-confirm">
          <div className="text-[13.5px] text-pb-text font-semibold">{picked.name}</div>
          <div className="mt-1 mb-2"><Clubs clubs={picked.clubs} /></div>
          <label className="flex items-start gap-2 text-[12.5px] text-pb-text cursor-pointer">
            <input type="checkbox" checked={false} onChange={(e) => confirm(e.target.checked)} className="mt-0.5 accent-pb-accent"
              data-testid="pc-match-confirm-box" />
            <span>
              Yes, this is the same person and they are joining <strong>{clubName}</strong>.
              {picked.at_this_club && <span className="text-pb-faint"> PlayCricket already lists them here.</span>}
            </span>
          </label>
          <button type="button" onClick={() => setPicked(null)}
            className="mt-2 text-[11.5px] underline text-pb-faint hover:text-pb-text">Not them, back to results</button>
        </div>
      ) : (
        <>
          <input type="text" value={q} data-testid="pc-match-search"
            onChange={(e) => { edited.current = true; setQ(e.target.value) }}
            placeholder="Search PlayCricket, e.g. Spencer Green"
            className="w-full bg-pb-surface border border-pb-hairline2 rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent" />
          {state.loading && <p className="text-[11.5px] text-pb-faintest mt-1.5">Searching…</p>}
          {state.error && <p className="text-[11.5px] text-pb-red mt-1.5">{state.error}</p>}
          {state.done && !state.loading && !state.error && state.candidates.length === 0 && (
            <p className="text-[11.5px] text-pb-faint mt-1.5" data-testid="pc-match-empty">
              Nobody found. Check the spelling as it appears on PlayCricket, or say they are not on it yet below.
            </p>
          )}
          {state.capped && (
            <input type="text" value={clubFilter} onChange={(e) => setClubFilter(e.target.value)}
              placeholder="Lots of matches: narrow by club name…" data-testid="pc-match-club-filter"
              className="w-full mt-2 bg-pb-surface border border-pb-hairline2 rounded px-2.5 py-1.5 text-pb-text text-xs focus:outline-none focus:border-pb-accent" />
          )}
          {filtered.length > 0 && (
            <ul className="mt-2 max-h-56 overflow-auto divide-y divide-pb-hairline" data-testid="pc-match-results">
              {filtered.map((c) => (
                <li key={c.participant_id} className="py-2 flex items-start justify-between gap-3" data-testid="pc-match-candidate">
                  <div className="min-w-0">
                    <div className="text-[13px] text-pb-text">{c.name}</div>
                    <div className="mt-0.5"><Clubs clubs={c.clubs} /></div>
                    {c.at_this_club && !c.existing_player && (
                      <div className="text-[11px] mt-0.5" style={{ color: 'var(--pb-accent)' }}>Already registered at {clubName}</div>
                    )}
                    {c.existing_player && (
                      <div className="text-[11px] mt-0.5 text-pb-faint" data-testid="pc-match-existing">
                        Already in your club as {c.existing_player.name}.
                        {onUseExisting && (
                          <> <button type="button" className="underline hover:text-pb-text" onClick={() => onUseExisting(c.existing_player)}>Open that player</button></>
                        )}
                      </div>
                    )}
                  </div>
                  {!c.existing_player && (
                    <button type="button" onClick={() => pick(c)}
                      className="shrink-0 px-2.5 py-1 rounded text-[11.5px] font-semibold text-pb-bg" style={{ background: 'var(--pb-accent)' }}>
                      This is them
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {allowNone && !linked && !picked && (
        <label className="flex items-start gap-2 text-[12px] text-pb-dim cursor-pointer mt-3">
          <input type="checkbox" checked={none} onChange={(e) => chooseNone(e.target.checked)} className="mt-0.5 accent-pb-accent"
            data-testid="pc-match-none" />
          <span>They are not on PlayCricket yet (new to cricket). The sync will match them by name once they have played.</span>
        </label>
      )}
    </div>
  )
}
