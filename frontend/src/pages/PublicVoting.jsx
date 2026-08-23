// BetterSelect — best-player vote collection (public, no login).
//
// Same magic-link + last-4 PIN pattern as before, same rules, same endpoints.
// The change is the BALLOT step: instead of one screen per position, a single
// screen shows three slots (3 / 2 / 1) above the full team list. Tapping a name
// fills the next empty slot; tapping a filled slot or a chosen name clears it.
// Three taps and Submit — no stepper, no separate review screen.
//
// No tallies are ever shown here; the count stays with the club's admins.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'

const initialsOf = (n = '') => n.split(/[ ,]+/).filter(Boolean).slice(0, 2).map((s) => s[0]).join('').toUpperCase()

const fmtDay = (d) => {
  try { return new Date(d + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'short' }) }
  catch { return d }
}

const STATE_LABEL = { open: null, awaiting_team: 'Team list not in yet', closed: 'Voting closed', locked: 'Voting closed' }
const NOT_OPEN = {
  upcoming: 'This game hasn’t been played yet.',
  awaiting_team: 'The team list for this game isn’t in yet. Check back soon.',
  closed: 'Voting has closed for this game.',
  locked: 'Voting is closed for this game.',
}
const REASON = {
  captain_only: 'Only the captain submits votes for this club. Ask your skipper to cast them.',
  did_not_play: 'Only players who played in this game can vote at this club.',
}

function Banner({ tone = 'error', children }) {
  if (!children) return null
  const color = tone === 'error' ? 'var(--pb-red)' : tone === 'ok' ? 'var(--pb-positive)' : 'var(--pb-amber)'
  return (
    <div className="rounded-lg px-3.5 py-2.5 mb-4 text-sm"
      style={{ background: `color-mix(in srgb, ${color} 12%, transparent)`, color, border: `1px solid color-mix(in srgb, ${color} 35%, transparent)` }}>
      {children}
    </div>
  )
}

/* ── The one-screen ballot ─────────────────────────────────────────────────── */
function Ballot({ fixture, values, votable, picks, setPicks, onSubmit, busy, voterLabel, onBack }) {
  const nextSlot = picks.findIndex((p) => !p)
  const complete = picks.every(Boolean)
  const nameOf = (id) => votable.find((p) => p.id === id)?.name || ''

  const tap = (id) => {
    const at = picks.indexOf(id)
    if (at >= 0) { setPicks(picks.map((p, i) => (i === at ? null : p))); return }
    if (nextSlot < 0) return
    setPicks(picks.map((p, i) => (i === nextSlot ? id : p)))
  }

  return (
    <div>
      {/* Slots */}
      <div className="flex gap-2 mb-4">
        {values.map((v, i) => {
          const filled = picks[i]
          const isNext = nextSlot === i
          return (
            <button key={i} onClick={() => filled && setPicks(picks.map((p, j) => (j === i ? null : p)))}
              className="flex-1 rounded-xl px-2.5 py-2.5 text-left transition"
              style={filled
                ? { background: 'color-mix(in srgb, var(--pb-accent) 12%, transparent)', border: '1px solid color-mix(in srgb, var(--pb-accent) 45%, transparent)' }
                : { background: 'var(--pb-surface)', border: `1px dashed ${isNext ? 'var(--pb-accent)' : 'var(--pb-hairline2)'}` }}>
              <div className="font-mono text-[10px] font-bold tracking-wide2"
                style={{ color: filled || isNext ? 'var(--pb-accent)' : 'var(--pb-faintest)' }}>
                {v} {v === 1 ? 'VOTE' : 'VOTES'}
              </div>
              <div className="text-[13.5px] font-semibold mt-1 truncate"
                style={{ color: filled ? 'var(--pb-text)' : 'var(--pb-faintest)' }}>
                {filled ? nameOf(filled) : 'Tap a name'}
              </div>
            </button>
          )
        })}
      </div>

      {/* Team list — 44px+ hit targets, one tap each */}
      <div className="rounded-xl border pb-hairline overflow-hidden">
        {votable.map((p) => {
          const at = picks.indexOf(p.id)
          const chosen = at >= 0
          return (
            <button key={p.id} onClick={() => tap(p.id)}
              className="w-full flex items-center gap-3 px-4 py-3 text-left border-b pb-hairline last:border-0 transition-colors"
              style={{ background: chosen ? 'color-mix(in srgb, var(--pb-accent) 7%, transparent)' : 'transparent' }}>
              <span className="w-8 h-8 rounded-full bg-pb-surface2 font-mono text-[11px] font-semibold flex items-center justify-center shrink-0"
                style={{ border: `1.5px solid ${chosen ? 'var(--pb-accent)' : 'var(--pb-hairline2)'}`, color: chosen ? 'var(--pb-accent)' : 'var(--pb-dim)' }}>
                {initialsOf(p.name)}
              </span>
              <span className="flex-1 text-[15.5px] font-medium">{p.name}</span>
              <span className="w-[26px] h-[26px] rounded-lg flex items-center justify-center font-mono text-xs font-bold shrink-0"
                style={chosen
                  ? { background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }
                  : { border: '1px dashed var(--pb-hairline2)', color: 'var(--pb-hairline2)' }}>
                {chosen ? values[at] : (nextSlot >= 0 ? values[nextSlot] : '')}
              </span>
            </button>
          )
        })}
      </div>

      <button onClick={onSubmit} disabled={!complete || busy}
        className="w-full mt-4 py-4 rounded-2xl text-[15.5px] font-bold transition"
        style={complete
          ? { background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }
          : { background: 'var(--pb-surface2)', color: 'var(--pb-faintest)' }}>
        {busy ? 'Saving…' : complete
          ? (fixture.my_ballot?.length ? 'Update my votes' : 'Submit my votes')
          : `Pick ${picks.filter((p) => !p).length} more`}
      </button>
      <div className="text-center text-[11.5px] text-pb-faintest mt-2.5">
        Voting as {voterLabel}. You can change your votes while voting stays open.
      </div>
      <button onClick={onBack} className="block mx-auto mt-3 text-pb-faint text-sm hover:text-pb-text">← Back to games</button>
    </div>
  )
}

export default function PublicVoting() {
  const { token } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const fixtureParam = searchParams.get('fixture') || ''
  const teamParam = searchParams.get('team') || ''
  const roundParam = searchParams.get('round') || ''
  const qParam = searchParams.get('q') || ''

  const [step, setStep] = useState('loading') // loading|dead|games|pick|pin|name|ballot|done
  const [landing, setLanding] = useState(null)
  const [me, setMe] = useState(null)
  const [supporterName, setSupporterName] = useState('')
  const [fixture, setFixture] = useState(null)
  const [search, setSearch] = useState('')
  const [chosen, setChosen] = useState(null)
  const [pin, setPin] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [picks, setPicks] = useState([])
  const pinRef = useRef(null)
  const autoOpened = useRef(false)

  const club = landing?.club
  const accent = club?.accent_color || club?.primary_color || null
  const values = fixture?.ballot_values || landing?.ballot_values || [3, 2, 1]

  useEffect(() => {
    let alive = true
    api.votePublicLanding(token, { team: teamParam || undefined, round_key: roundParam || undefined, q: qParam || undefined })
      .then((d) => { if (!alive) return; setLanding(d); setMe(d.me); setStep((s) => (s === 'loading' ? 'games' : s)) })
      .catch(() => alive && setStep('dead'))
    return () => { alive = false }
  }, [token, teamParam, roundParam, qParam])

  useEffect(() => { if (step === 'pin') pinRef.current?.focus() }, [step])

  const seedPicks = (d) => {
    const n = (d.ballot_values || [3, 2, 1]).length
    const existing = (d.my_ballot || []).slice(0, n)
    setPicks(Array.from({ length: n }, (_, i) => existing[i] || null))
  }

  const openFixture = useCallback(async (fid) => {
    setError(''); setBusy(true)
    try {
      const d = await api.votePublicFixture(token, fid)
      setFixture(d)
      if (d.me && !me) setMe(d.me)
      if (d.fixture?.state !== 'open' || d.role === 'none') { seedPicks(d); setStep('ballot'); return }
      if (!d.me && !supporterName) { seedPicks(d); setStep('pick'); return }
      seedPicks(d); setStep('ballot')
    } catch (e) { setError(e.message || 'Something went wrong. Try again.') }
    finally { setBusy(false) }
  }, [token, me, supporterName])

  useEffect(() => {
    if (landing && fixtureParam && !autoOpened.current) { autoOpened.current = true; openFixture(fixtureParam) }
  }, [landing, fixtureParam, openFixture])

  const updateFilter = useCallback((key, value) => {
    const next = new URLSearchParams(searchParams)
    if (value) next.set(key, value); else next.delete(key)
    if (key === 'team') next.delete('round')
    setSearchParams(next, { replace: true })
  }, [searchParams, setSearchParams])

  const backToGames = useCallback(() => {
    setFixture(null); setError('')
    if (searchParams.get('fixture')) {
      const next = new URLSearchParams(searchParams); next.delete('fixture'); setSearchParams(next, { replace: true })
    }
    setStep('games')
  }, [searchParams, setSearchParams])

  const doVerify = async (player, pinValue) => {
    setBusy(true); setError('')
    try {
      const r = await api.votePublicVerify(token, player.id, pinValue)
      setMe(r.player)
      if (fixture) {
        const d = await api.votePublicFixture(token, fixture.fixture.id)
        setFixture(d); seedPicks(d); setStep('ballot')
      } else setStep('games')
    } catch (e) { setError(e.message || 'That didn’t match. Please try again.') }
    finally { setBusy(false) }
  }

  const votable = useMemo(() => {
    const players = fixture?.players || []
    if (me && !fixture?.allow_self_vote) return players.filter((p) => p.id !== me.id)
    return players
  }, [fixture, me])

  const submitBallot = async () => {
    setBusy(true); setError('')
    try {
      await api.votePublicSubmit(token, fixture.fixture.id, { picks, voter_name: me ? undefined : supporterName })
      setStep('done')
    } catch (e) { setError(e.message || 'Couldn’t save your votes. Please try again.') }
    finally { setBusy(false) }
  }

  const filteredPlayers = useMemo(() => {
    const q = search.trim().toLowerCase()
    const players = landing?.players || []
    return q ? players.filter((p) => p.display_name.toLowerCase().includes(q)) : players
  }, [landing, search])

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text" style={accent ? { '--pb-accent': accent } : undefined}>
      <div className="max-w-md mx-auto px-4 py-8 sm:py-12">
        {step === 'loading' && <div className="py-24 text-center text-pb-faint text-sm">Loading…</div>}

        {step === 'dead' && (
          <div className="py-20 text-center">
            <div className="font-display font-bold text-lg">This link isn’t active</div>
            <p className="text-pb-faint text-sm mt-2">
              It may have been turned off or replaced. Ask your club for the current voting link.
            </p>
          </div>
        )}

        {step !== 'loading' && step !== 'dead' && (
          <div className="flex items-center gap-3 mb-6">
            {club?.logo_url
              ? <img src={club.logo_url} alt="" className="w-10 h-10 rounded-xl object-contain bg-pb-surface2 p-1" />
              : <span className="w-10 h-10 rounded-xl flex items-center justify-center font-display font-bold text-sm text-pb-bg"
                  style={{ background: 'var(--pb-accent)' }}>{initialsOf(club?.name || 'Club')}</span>}
            <div className="min-w-0">
              <div className="font-display font-bold text-[15px] leading-tight truncate">{club?.name || 'Vote'}</div>
              {/* A club can run several counts, each on its own link, so the
                  medal is named here — the ballot shape alone doesn't say
                  which award you're voting for. */}
              <div className="font-mono text-[10px] tracking-wide2 text-pb-faint mt-0.5 truncate">
                {(landing?.medal?.name || 'Best-player votes').toUpperCase()}
              </div>
            </div>
            {me && (
              <button onClick={async () => {
                try { await api.votePublicSwitch(token) } catch { /* cookie clear is best-effort */ }
                setMe(null); setChosen(null); setStep('games')
              }} className="ml-auto text-xs text-pb-faint hover:text-pb-text underline shrink-0">Not you?</button>
            )}
          </div>
        )}

        {step === 'games' && landing && (
          <div>
            <Banner>{error}</Banner>
            {((landing.grades?.length || 0) > 1 || (landing.rounds?.length || 0) > 1) && (
              <div className="flex gap-2 mb-3.5">
                {(landing.grades?.length || 0) > 1 && (
                  <select value={teamParam} onChange={(e) => updateFilter('team', e.target.value)}
                    className="flex-1 bg-pb-surface2 border pb-hairline rounded-lg px-2.5 py-2 text-[13px] focus:outline-none focus:border-pb-accent">
                    <option value="">All teams</option>
                    {landing.grades.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                  </select>
                )}
                {(landing.rounds?.length || 0) > 1 && (
                  <select value={roundParam} onChange={(e) => updateFilter('round', e.target.value)}
                    className="flex-1 bg-pb-surface2 border pb-hairline rounded-lg px-2.5 py-2 text-[13px] focus:outline-none focus:border-pb-accent">
                    <option value="">All rounds</option>
                    {landing.rounds.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
                  </select>
                )}
              </div>
            )}
            {landing.fixtures.length === 0 && (
              <div className="rounded-xl border pb-hairline px-4 py-10 text-center text-pb-faint text-sm">
                {teamParam || roundParam || qParam ? 'No games match these filters.' : 'No games to vote on yet. Check back after the weekend.'}
              </div>
            )}
            <div className="flex flex-col gap-3">
              {landing.fixtures.map((f) => {
                const open = f.state === 'open'
                return (
                  <button key={f.id} onClick={() => open && openFixture(f.id)} disabled={!open || busy}
                    className={`rounded-xl border pb-hairline p-3.5 text-left transition-colors ${open ? 'hover:border-pb-accent' : 'opacity-55'}`}>
                    <div className="flex items-baseline justify-between gap-2">
                      <div>
                        <div className="font-display font-bold text-[15px]">
                          {f.round} · {f.home_away === 'AWAY' ? '@' : 'vs'} {f.opponent || 'TBC'}
                        </div>
                        <div className="text-xs text-pb-faint mt-0.5">{fmtDay(f.date)}</div>
                      </div>
                      <span className="font-mono text-[10px] shrink-0"
                        style={{ color: open ? 'var(--pb-positive)' : 'var(--pb-faintest)' }}>
                        {open ? 'VOTE →' : STATE_LABEL[f.state]}
                      </span>
                    </div>
                  </button>
                )
              })}
            </div>
            <p className="text-center text-pb-faintest text-[11px] mt-5">
              Votes go to your club’s count. Results stay with the club until they’re announced.
            </p>
          </div>
        )}

        {step === 'pick' && landing && (
          <div>
            <div className="text-center mb-4 text-sm text-pb-faint">Find your name to vote</div>
            <Banner>{error}</Banner>
            <input autoFocus value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search your name…"
              className="w-full bg-pb-surface2 border pb-hairline rounded-xl px-4 py-3 text-base focus:outline-none focus:border-pb-accent mb-3" />
            <div className="rounded-xl border pb-hairline overflow-hidden divide-y divide-pb-hairline max-h-[45vh] overflow-y-auto">
              {filteredPlayers.map((p) => (
                <button key={p.id} onClick={() => {
                  setChosen(p); setPin(''); setError('')
                  if (landing.require_pin) setStep('pin'); else doVerify(p, '')
                }} className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-pb-surface2 transition-colors">
                  <span className="text-[15px] font-medium">{p.display_name}</span>
                  {landing.require_pin && !p.has_phone
                    ? <span className="font-mono text-[10px] text-pb-faintest uppercase shrink-0">no mobile</span>
                    : <span className="text-pb-faintest shrink-0">→</span>}
                </button>
              ))}
            </div>
            {landing.allow_non_participants && (
              <button onClick={() => setStep('name')} className="block mx-auto mt-4 text-pb-accent text-sm underline">
                I didn’t play (coach / supporter)
              </button>
            )}
            <button onClick={backToGames} className="block mx-auto mt-3 text-pb-faint text-sm hover:text-pb-text">← Back to games</button>
          </div>
        )}

        {step === 'pin' && chosen && (
          <form onSubmit={(e) => { e.preventDefault(); if (pin.length >= 4) doVerify(chosen, pin) }}>
            <div className="text-center mb-5">
              <div className="text-sm text-pb-faint">Hi</div>
              <div className="font-display font-bold text-2xl">{chosen.display_name}</div>
            </div>
            <Banner>{error}</Banner>
            {!chosen.has_phone ? (
              <div className="text-center text-pb-faint text-sm py-4">
                There’s no mobile number on file for you yet. Ask your club admin to add it, or to record your votes for you.
                <div className="mt-5">
                  <button type="button" onClick={() => setStep('pick')} className="text-pb-accent text-sm underline">← Pick a different name</button>
                </div>
              </div>
            ) : (
              <>
                <label className="block text-center font-mono text-[11px] tracking-wide2 text-pb-faint uppercase mb-2">
                  Last 4 digits of your mobile
                </label>
                <input ref={pinRef} value={pin} inputMode="numeric" autoComplete="one-time-code" placeholder="••••"
                  onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 4))}
                  className="w-full text-center tracking-[0.6em] text-2xl font-mono bg-pb-surface2 border pb-hairline rounded-xl px-4 py-3.5 focus:outline-none focus:border-pb-accent" />
                <button type="submit" disabled={pin.length < 4 || busy}
                  className="w-full mt-4 py-3.5 rounded-xl font-semibold text-pb-bg disabled:opacity-50"
                  style={{ background: 'var(--pb-accent)' }}>
                  {busy ? 'Checking…' : 'Continue'}
                </button>
                <button type="button" onClick={() => setStep('pick')} className="block mx-auto mt-4 text-pb-faint text-sm hover:text-pb-text">
                  ← Not you? Pick a different name
                </button>
              </>
            )}
          </form>
        )}

        {step === 'name' && (
          <div>
            <div className="text-center mb-4">
              <div className="font-display font-bold text-lg">Who’s voting?</div>
              <p className="text-pb-faint text-sm mt-1">
                This club lets non-players vote. Enter your name so the club knows whose ballot this is.
              </p>
            </div>
            <Banner>{error}</Banner>
            <input autoFocus value={supporterName} onChange={(e) => setSupporterName(e.target.value)}
              placeholder="Your name (e.g. Coach Dave)"
              className="w-full bg-pb-surface2 border pb-hairline rounded-xl px-4 py-3 text-base focus:outline-none focus:border-pb-accent" />
            <button onClick={() => (fixture ? setStep('ballot') : setStep('games'))}
              disabled={supporterName.trim().length < 2}
              className="w-full mt-4 py-3.5 rounded-xl font-semibold text-pb-bg disabled:opacity-50"
              style={{ background: 'var(--pb-accent)' }}>Continue</button>
          </div>
        )}

        {step === 'ballot' && fixture && (
          <div>
            <div className="mb-4">
              <div className="font-display font-bold text-[16px]">
                {fixture.fixture.round} · vs {fixture.fixture.opponent || 'TBC'}
              </div>
              <div className="text-xs text-pb-faint mt-0.5">{fmtDay(fixture.fixture.date)}</div>
            </div>
            <Banner>{error}</Banner>

            {fixture.fixture.state !== 'open' ? (
              <div className="rounded-xl border pb-hairline px-4 py-8 text-center text-pb-faint text-sm">
                {NOT_OPEN[fixture.fixture.state] || 'Voting isn’t open for this game.'}
                <div className="mt-4"><button onClick={backToGames} className="text-pb-accent underline">← Back to games</button></div>
              </div>
            ) : fixture.role === 'none' ? (
              <div className="rounded-xl border pb-hairline px-4 py-8 text-center text-pb-faint text-sm">
                {REASON[fixture.reason] || 'You can’t vote on this game.'}
                <div className="mt-4"><button onClick={backToGames} className="text-pb-accent underline">← Back to games</button></div>
              </div>
            ) : (
              <Ballot fixture={fixture} values={values} votable={votable} picks={picks} setPicks={setPicks}
                onSubmit={submitBallot} busy={busy} onBack={backToGames}
                voterLabel={me?.display_name || supporterName} />
            )}
          </div>
        )}

        {step === 'done' && (
          <div className="py-14 text-center">
            <div className="font-display font-bold text-xl">Votes in!</div>
            <p className="text-pb-faint text-sm mt-2">
              Thanks{me ? `, ${me.display_name.split(' ')[0]}` : supporterName ? `, ${supporterName.split(' ')[0]}` : ''}.
              Your ballot is with the club. You can come back and change it while voting stays open.
            </p>
            <button onClick={backToGames} className="mt-6 px-6 py-3 rounded-xl font-semibold text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}>Back to games</button>
          </div>
        )}

        {step !== 'loading' && step !== 'dead' && (
          <div className="text-center mt-10">
            <span className="font-mono text-[10px] tracking-wide2 text-pb-faintest uppercase">Powered by BetterCricket</span>
          </div>
        )}
      </div>
    </div>
  )
}
