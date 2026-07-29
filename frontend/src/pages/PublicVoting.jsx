// BetterSelect — best-player vote collection (public, no login).
//
// Reached via a per-club magic link (/vote/:token) — the voting sibling of the
// self-service availability page, sharing its mobile-first shape: pick the
// game → prove who you are (players: name + last-4-of-mobile PIN; permitted
// non-players: type your name) → hand out your votes one position at a time
// (who gets the 3? the 2? the 1?) → review and submit. A signed cookie keeps a
// player verified (~30 days). No tallies are ever shown here — the count stays
// with the club's admins.
import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../lib/api'

function fmtDay(d) {
  try {
    return new Date(d + 'T00:00:00').toLocaleDateString(undefined, {
      weekday: 'long', day: 'numeric', month: 'short',
    })
  } catch { return d }
}

function ClubHeader({ club }) {
  const initials = (club?.name || 'Club').split(' ').map((w) => w[0]).join('').slice(0, 3).toUpperCase()
  return (
    <div className="flex flex-col items-center text-center gap-3 mb-6">
      {club?.logo_url
        ? <img src={club.logo_url} alt="" className="w-16 h-16 rounded-xl object-contain bg-pb-surface2 p-1" />
        : <span className="w-16 h-16 rounded-xl flex items-center justify-center font-display font-bold text-xl text-pb-bg" style={{ background: 'var(--pb-accent)' }}>{initials}</span>}
      <div>
        <div className="font-display font-bold text-xl leading-tight">{club?.name || 'Vote'}</div>
        <div className="font-mono text-[11px] tracking-wide2 text-pb-faint mt-1">BEST-PLAYER VOTES</div>
      </div>
    </div>
  )
}

function Banner({ tone = 'error', children }) {
  if (!children) return null
  const color = tone === 'error' ? 'var(--pb-red)' : tone === 'ok' ? 'var(--pb-positive)' : 'var(--pb-amber)'
  return (
    <div className="rounded-lg px-3.5 py-2.5 mb-4 text-sm" style={{ background: `color-mix(in srgb, ${color} 12%, transparent)`, color, border: `1px solid color-mix(in srgb, ${color} 35%, transparent)` }}>
      {children}
    </div>
  )
}

const STATE_LABEL = {
  open: null, // votable — no caption needed
  awaiting_sync: 'Scorecard not in yet',
  closed: 'Voting closed',
  locked: 'Voting closed',
}

export default function PublicVoting() {
  const { token } = useParams()
  const [step, setStep] = useState('loading') // loading | dead | games | pick | pin | name | ballot | done
  const [landing, setLanding] = useState(null)
  const [me, setMe] = useState(null) // verified player {id, display_name}
  const [supporterName, setSupporterName] = useState('')
  const [fixture, setFixture] = useState(null) // votePublicFixture payload
  const [search, setSearch] = useState('')
  const [chosen, setChosen] = useState(null)
  const [pin, setPin] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [picks, setPicks] = useState([]) // player ids, position 1 first
  const [posIndex, setPosIndex] = useState(0)
  const [reviewing, setReviewing] = useState(false)
  const pinRef = useRef(null)

  const club = landing?.club
  const accent = club?.accent_color || club?.primary_color || null

  useEffect(() => {
    let alive = true
    api.votePublicLanding(token)
      .then((d) => {
        if (!alive) return
        setLanding(d)
        setMe(d.me)
        setStep('games')
      })
      .catch(() => { if (alive) setStep('dead') })
    return () => { alive = false }
  }, [token])

  useEffect(() => { if (step === 'pin' && pinRef.current) pinRef.current.focus() }, [step])

  const openFixture = useCallback(async (fid) => {
    setError('')
    setBusy(true)
    try {
      const d = await api.votePublicFixture(token, fid)
      setFixture(d)
      if (d.me && !me) setMe(d.me)
      setReviewing(false)
      // Not identified yet: players verify with their PIN first; the pick step
      // offers the "I didn't play" escape hatch when the club allows it. A
      // supporter who already gave their name this session skips straight in.
      if (!d.me && !supporterName) {
        setPicks([]); setPosIndex(0)
        setStep('pick')
        return
      }
      if (d.role === 'none') {
        setPicks([]); setPosIndex(0)
        setStep('ballot') // shows the reason they can't vote
        return
      }
      const existing = (d.my_ballot || []).slice(0, (d.ballot_values || []).length)
      setPicks(existing)
      setPosIndex(existing.length ? existing.length : 0)
      setReviewing(existing.length === (d.ballot_values || []).length)
      setStep('ballot')
    } catch (e) {
      setError(e.message || 'Something went wrong. Try again.')
    } finally { setBusy(false) }
  }, [token, me, supporterName])

  const doVerify = async (player, pinValue) => {
    setBusy(true)
    setError('')
    try {
      const r = await api.votePublicVerify(token, player.id, pinValue)
      setMe(r.player)
      if (fixture) await reopenAfterVerify()
      else setStep('games')
    } catch (e) {
      setError(e.message || 'That didn’t match. Please try again.')
    } finally { setBusy(false) }
  }

  const reopenAfterVerify = async () => {
    const d = await api.votePublicFixture(token, fixture.fixture.id)
    setFixture(d)
    if (d.role === 'none') { setStep('ballot'); return } // ballot step shows the reason
    const existing = (d.my_ballot || []).slice(0, (d.ballot_values || []).length)
    setPicks(existing)
    setPosIndex(existing.length ? existing.length : 0)
    setReviewing(existing.length === (d.ballot_values || []).length)
    setStep('ballot')
  }

  const pickPlayer = async (p) => {
    setChosen(p)
    setPin('')
    setError('')
    if (landing?.require_pin) { setStep('pin'); return }
    await doVerify(p, '')
  }

  const switchPlayer = async () => {
    try { await api.votePublicSwitch(token) } catch { /* cookie clear is best-effort */ }
    setMe(null); setChosen(null); setPin(''); setSearch(''); setError('')
    setStep('games')
  }

  const submitPin = (e) => {
    e.preventDefault()
    if (!chosen || pin.length < 4) return
    doVerify(chosen, pin)
  }

  const values = fixture?.ballot_values || landing?.ballot_values || [3, 2, 1]
  const votable = useMemo(() => {
    const players = fixture?.players || []
    if (me && !fixture?.allow_self_vote) return players.filter((p) => p.id !== me.id)
    return players
  }, [fixture, me])

  const assign = (pid) => {
    const next = [...picks]
    next[posIndex] = pid
    setPicks(next)
    if (posIndex + 1 >= values.length) setReviewing(true)
    else setPosIndex(posIndex + 1)
  }

  const restart = () => { setPicks([]); setPosIndex(0); setReviewing(false) }

  const submitBallot = async () => {
    setBusy(true)
    setError('')
    try {
      await api.votePublicSubmit(token, fixture.fixture.id, {
        picks,
        voter_name: me ? undefined : supporterName,
      })
      setStep('done')
    } catch (e) {
      setError(e.message || 'Couldn’t save your votes. Please try again.')
    } finally { setBusy(false) }
  }

  const nameById = (pid) => (fixture?.players || []).find((p) => p.id === pid)?.name || '—'

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    const players = landing?.players || []
    if (!q) return players
    return players.filter((p) => p.display_name.toLowerCase().includes(q))
  }, [landing, search])

  const reasonText = {
    captain_only: 'Only the captain submits votes for this club. Ask your skipper to cast them.',
    did_not_play: 'Only players who played in this game can vote at this club.',
  }

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text" style={accent ? { '--pb-accent': accent } : undefined}>
      <div className="max-w-md mx-auto px-4 py-8 sm:py-12">
        {step === 'loading' && <div className="py-24 text-center text-pb-faint text-sm">Loading…</div>}

        {step === 'dead' && (
          <div className="py-20 text-center">
            <div className="text-3xl mb-3">🔗</div>
            <div className="font-display font-bold text-lg">This link isn’t active</div>
            <p className="text-pb-faint text-sm mt-2">It may have been turned off or replaced. Ask your club for the current voting link.</p>
          </div>
        )}

        {step !== 'loading' && step !== 'dead' && <ClubHeader club={club} />}

        {/* Pick the game */}
        {step === 'games' && landing && (
          <div>
            {me && (
              <div className="flex items-center justify-between mb-4">
                <div>
                  <div className="font-mono text-[11px] text-pb-faint">Voting as</div>
                  <div className="font-display font-bold text-lg">{me.display_name}</div>
                </div>
                <button onClick={switchPlayer} className="text-pb-faint text-xs hover:text-pb-text underline shrink-0">Not you?</button>
              </div>
            )}
            <Banner>{error}</Banner>
            {landing.fixtures.length === 0 && (
              <div className="rounded-xl border pb-hairline px-4 py-10 text-center text-pb-faint text-sm">
                No games to vote on yet. Check back after the weekend.
              </div>
            )}
            <div className="flex flex-col gap-3">
              {landing.fixtures.map((f) => {
                const open = f.state === 'open'
                const caption = STATE_LABEL[f.state]
                return (
                  <button key={f.id} onClick={() => open && openFixture(f.id)} disabled={!open || busy}
                    className={`rounded-xl border pb-hairline p-3.5 text-left transition-colors ${open ? 'hover:border-pb-accent' : 'opacity-55'}`}>
                    <div className="flex items-baseline justify-between gap-2">
                      <div>
                        <div className="font-display font-bold text-[15px]">
                          {f.round} · {f.home_away === 'AWAY' ? '@' : 'vs'} {f.opponent || 'TBC'}
                        </div>
                        <div className="text-[12px] text-pb-faint mt-0.5">{fmtDay(f.date)}</div>
                      </div>
                      <span className="font-mono text-[10px] shrink-0" style={{ color: open ? 'var(--pb-positive)' : 'var(--pb-faintest)' }}>
                        {open ? 'VOTE →' : caption}
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

        {/* Verify: pick your name */}
        {step === 'pick' && landing && (
          <div>
            <div className="text-center mb-4 text-sm text-pb-faint">Find your name to vote</div>
            <Banner>{error}</Banner>
            <input
              autoFocus value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search your name…"
              className="w-full bg-pb-surface2 border pb-hairline rounded-xl px-4 py-3 text-base focus:outline-none focus:border-pb-accent mb-3"
            />
            <div className="rounded-xl border pb-hairline overflow-hidden divide-y divide-pb-hairline max-h-[45vh] overflow-y-auto">
              {filtered.length === 0 && (
                <div className="px-4 py-6 text-center text-pb-faint text-sm">No players match “{search}”.</div>
              )}
              {filtered.map((p) => (
                <button key={p.id} onClick={() => pickPlayer(p)}
                  className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-pb-surface2 transition-colors">
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
            <button onClick={() => setStep('games')} className="block mx-auto mt-3 text-pb-faint text-sm hover:text-pb-text">← Back to games</button>
          </div>
        )}

        {/* Verify: PIN */}
        {step === 'pin' && chosen && (
          <form onSubmit={submitPin}>
            <div className="text-center mb-5">
              <div className="text-sm text-pb-faint">Hi</div>
              <div className="font-display font-bold text-2xl">{chosen.display_name}</div>
            </div>
            <Banner>{error}</Banner>
            {!chosen.has_phone ? (
              <div className="text-center text-pb-faint text-sm py-4">
                There’s no mobile number on file for you yet. Ask your club admin to add it, or to record your votes for you.
                <div className="mt-5"><button type="button" onClick={() => setStep('pick')} className="text-pb-accent text-sm underline">← Pick a different name</button></div>
              </div>
            ) : (
              <>
                <label className="block text-center font-mono text-[11px] tracking-wide2 text-pb-faint uppercase mb-2">
                  Last 4 digits of your mobile
                </label>
                <input
                  ref={pinRef} value={pin}
                  onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 4))}
                  inputMode="numeric" autoComplete="one-time-code" placeholder="••••"
                  className="w-full text-center tracking-[0.6em] text-2xl font-mono bg-pb-surface2 border pb-hairline rounded-xl px-4 py-3.5 focus:outline-none focus:border-pb-accent"
                />
                <button type="submit" disabled={pin.length < 4 || busy}
                  className="w-full mt-4 py-3.5 rounded-xl font-semibold text-pb-bg transition disabled:opacity-50"
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

        {/* Non-player: type your name */}
        {step === 'name' && (
          <div>
            <div className="text-center mb-4">
              <div className="font-display font-bold text-lg">Who’s voting?</div>
              <p className="text-pb-faint text-sm mt-1">This club lets non-players vote. Enter your name so the club knows whose ballot this is.</p>
            </div>
            <Banner>{error}</Banner>
            <input
              autoFocus value={supporterName} onChange={(e) => setSupporterName(e.target.value)}
              placeholder="Your name (e.g. Coach Dave)"
              className="w-full bg-pb-surface2 border pb-hairline rounded-xl px-4 py-3 text-base focus:outline-none focus:border-pb-accent"
            />
            <button
              onClick={() => (fixture ? (setStep('ballot'), restart()) : setStep('games'))}
              disabled={supporterName.trim().length < 2}
              className="w-full mt-4 py-3.5 rounded-xl font-semibold text-pb-bg transition disabled:opacity-50"
              style={{ background: 'var(--pb-accent)' }}>
              Continue
            </button>
            <button onClick={() => setStep(landing?.players?.length ? 'pick' : 'games')} className="block mx-auto mt-4 text-pb-faint text-sm hover:text-pb-text">← Back</button>
          </div>
        )}

        {/* Ballot */}
        {step === 'ballot' && fixture && (
          <div>
            <div className="mb-4">
              <div className="font-display font-bold text-[16px]">
                {fixture.fixture.round} · vs {fixture.fixture.opponent || 'TBC'}
              </div>
              <div className="text-[12px] text-pb-faint mt-0.5">
                {fmtDay(fixture.fixture.date)}
                {me ? <> · voting as <b className="text-pb-text">{me.display_name}</b></> : supporterName ? <> · voting as <b className="text-pb-text">{supporterName}</b></> : null}
              </div>
            </div>
            <Banner>{error}</Banner>

            {fixture.role === 'none' ? (
              <div className="rounded-xl border pb-hairline px-4 py-8 text-center text-pb-faint text-sm">
                {reasonText[fixture.reason] || 'You can’t vote on this game.'}
                <div className="mt-4"><button onClick={() => setStep('games')} className="text-pb-accent underline">← Back to games</button></div>
              </div>
            ) : reviewing ? (
              <div>
                <div className="rounded-xl border pb-hairline divide-y divide-pb-hairline overflow-hidden mb-4">
                  {values.map((v, i) => (
                    <div key={i} className="flex items-center gap-3 px-4 py-3">
                      <span className="w-9 h-9 rounded-lg flex items-center justify-center font-display font-bold text-lg shrink-0"
                        style={{ background: 'color-mix(in srgb, var(--pb-accent) 15%, transparent)', color: 'var(--pb-accent)' }}>{v}</span>
                      <span className="text-[15px] font-medium">{nameById(picks[i])}</span>
                    </div>
                  ))}
                </div>
                <button onClick={submitBallot} disabled={busy}
                  className="w-full py-3.5 rounded-xl font-semibold text-pb-bg transition disabled:opacity-50"
                  style={{ background: 'var(--pb-accent)' }}>
                  {busy ? 'Saving…' : fixture.my_ballot?.length ? 'Update my votes' : 'Submit my votes'}
                </button>
                <button onClick={restart} className="block mx-auto mt-3 text-pb-faint text-sm hover:text-pb-text underline">Start again</button>
                <button onClick={() => setStep('games')} className="block mx-auto mt-3 text-pb-faint text-sm hover:text-pb-text">← Back to games</button>
              </div>
            ) : (
              <div>
                <div className="text-center mb-3">
                  <div className="font-display font-bold text-2xl" style={{ color: 'var(--pb-accent)' }}>
                    Who gets your {values[posIndex]}?
                  </div>
                  <div className="text-[12px] text-pb-faint mt-1">
                    {values.map((v, i) => (
                      <span key={i} className="font-mono mx-0.5" style={{ opacity: i === posIndex ? 1 : 0.4 }}>
                        {i < posIndex ? '●' : i === posIndex ? v : '○'}
                      </span>
                    ))}
                    {' '}· best player gets the {values[0]}
                  </div>
                </div>
                <div className="rounded-xl border pb-hairline overflow-hidden divide-y divide-pb-hairline max-h-[50vh] overflow-y-auto">
                  {votable.filter((p) => !picks.slice(0, posIndex).includes(p.id)).map((p) => (
                    <button key={p.id} onClick={() => assign(p.id)}
                      className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-pb-surface2 transition-colors">
                      <span className="text-[15px] font-medium">{p.name}</span>
                      <span className="text-pb-faintest shrink-0">→</span>
                    </button>
                  ))}
                </div>
                {posIndex > 0 && (
                  <button onClick={() => setPosIndex(posIndex - 1)} className="block mx-auto mt-4 text-pb-faint text-sm hover:text-pb-text">
                    ← Back to the {values[posIndex - 1]}
                  </button>
                )}
                <button onClick={() => setStep('games')} className="block mx-auto mt-3 text-pb-faint text-sm hover:text-pb-text">← Back to games</button>
              </div>
            )}
          </div>
        )}

        {/* Done */}
        {step === 'done' && (
          <div className="py-14 text-center">
            <div className="text-4xl mb-4">🗳️</div>
            <div className="font-display font-bold text-xl">Votes in!</div>
            <p className="text-pb-faint text-sm mt-2">
              Thanks{me ? `, ${me.display_name.split(' ')[0]}` : supporterName ? `, ${supporterName.split(' ')[0]}` : ''}. Your ballot is with the club.
              You can come back and change it while voting stays open.
            </p>
            <button onClick={() => { setFixture(null); setStep('games') }}
              className="mt-6 px-6 py-3 rounded-xl font-semibold text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}>
              Back to games
            </button>
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
