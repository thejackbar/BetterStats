// BetterFootball — the page a player casts their B&F votes on.
//
// Reached by a link the club shares, one per medal. No account: pick your
// name, prove it with the last 4 digits of your phone, then tap out your
// ballot. Nothing here ever shows a tally — the count stays inside the admin
// app, because a club keeps its Best & Fairest secret until presentation
// night.
//
// One screen for the ballot, not a stepper: the values sit above the team
// list, tapping a name fills the next empty one, tapping a filled slot clears
// it. On a phone in a clubroom that beats paging through positions.
import { useCallback, useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { aflApi, mediaUrl } from '../aflApi'

const NOT_OPEN = {
  awaiting_team: "Voting opens once the team list for this game is in.",
  upcoming: "This game hasn't been played yet.",
  closed: 'Voting has closed for this game.',
  locked: 'Voting has closed for this game.',
}
const REASON = {
  captain_only: 'Only the captain submits votes for this club. Ask your skipper.',
  did_not_play: 'Only players named for this game can vote.',
  verify_required: 'Find your name below and verify to vote.',
}

const initials = (n) => (n || '').split(' ').filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase()

export default function AflPublicVoting() {
  const { token } = useParams()
  const [params, setParams] = useSearchParams()
  const gameParam = params.get('game') || ''

  const [landing, setLanding] = useState(null)
  const [me, setMe] = useState(null)
  const [step, setStep] = useState('loading')  // loading|dead|games|pin|ballot|done
  const [pinFor, setPinFor] = useState(null)
  const [pin, setPin] = useState('')
  const [name, setName] = useState('')
  const [game, setGame] = useState(null)
  const [picks, setPicks] = useState([])
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    aflApi.votePublicLanding(token)
      .then((d) => {
        setLanding(d)
        setMe(d.me || null)
        setStep((s) => (s === 'loading' ? 'games' : s))
      })
      .catch(() => setStep('dead'))
  }, [token])
  useEffect(() => { load() }, [load])

  // A ?game= link opens straight into that ballot — a club shares one link per
  // round rather than asking everyone to find the game themselves.
  useEffect(() => {
    if (landing && gameParam && !game) openGame(gameParam)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [landing, gameParam])

  async function openGame(id) {
    setError(null)
    try {
      const d = await aflApi.votePublicGame(token, id)
      setGame(d)
      setPicks(d.my_ballot?.length ? d.my_ballot : (d.ballot_values || []).map(() => ''))
      setStep('ballot')
      setParams({ game: id }, { replace: true })
    } catch (e) { setError(e.message) }
  }

  function backToGames() {
    setGame(null); setPicks([]); setError(null)
    setParams({}, { replace: true })
    setStep('games')
  }

  async function verify(playerId, code) {
    setBusy(true); setError(null)
    try {
      const d = await aflApi.votePublicVerify(token, playerId, code)
      setMe(d.me); setPin(''); setPinFor(null)
      if (game) await openGame(game.game.id); else setStep('games')
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  // Tap a name to fill the next empty slot; tap a chosen name or a filled slot
  // to clear it. No drag, no long-press — this gets used one-handed.
  const tapPlayer = (pid) => {
    const at = picks.indexOf(pid)
    if (at >= 0) { setPicks(picks.map((x, i) => (i === at ? '' : x))); return }
    const next = picks.indexOf('')
    if (next < 0) return
    setPicks(picks.map((x, i) => (i === next ? pid : x)))
  }

  async function submit() {
    setBusy(true); setError(null)
    try {
      await aflApi.votePublicSubmit(token, game.game.id, {
        picks, voter_name: me ? undefined : name.trim() || undefined,
      })
      setStep('done')
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  if (step === 'loading') return <Shell><p className="text-pb-faint text-sm">Loading…</p></Shell>
  if (step === 'dead') {
    return (
      <Shell>
        <h1 className="font-display font-bold text-lg mb-1">This voting link isn't active</h1>
        <p className="text-pb-faint text-sm">Check with your club for the current link.</p>
      </Shell>
    )
  }

  const club = landing.club
  const values = (game?.ballot_values || landing.ballot_values || [])
  const full = picks.length > 0 && picks.every(Boolean)

  return (
    <Shell accent={club?.accent_color}>
      <header className="flex items-center gap-3 mb-6">
        {club?.logo_url
          ? <img src={mediaUrl(club.logo_url)} alt="" className="w-10 h-10 rounded-xl object-contain bg-pb-surface2 p-1" />
          : <span className="w-10 h-10 rounded-xl grid place-items-center font-display font-bold text-sm text-pb-on-accent"
              style={{ background: 'var(--pb-accent)' }}>{initials(club?.name)}</span>}
        <div className="min-w-0">
          <div className="font-display font-bold text-[15px] leading-tight truncate">{club?.name}</div>
          {/* Named because a club can run several counts on separate links. */}
          <div className="font-mono text-[10px] tracking-wide2 text-pb-faint mt-0.5 truncate">
            {(landing.medal?.name || 'Best & fairest votes').toUpperCase()}
          </div>
        </div>
        {me && (
          <button onClick={async () => {
            try { await aflApi.votePublicSwitch(token) } catch { /* best effort */ }
            setMe(null); backToGames()
          }} className="ml-auto text-xs text-pb-faint underline shrink-0">Not you?</button>
        )}
      </header>

      {error && <div className="mb-4 text-sm text-pb-red">{error}</div>}

      {step === 'games' && (
        <div>
          {landing.games.length === 0 && (
            <p className="text-pb-faint text-sm">No games are open for voting right now.</p>
          )}
          <div className="space-y-2">
            {landing.games.map((g) => (
              <button key={g.id} disabled={!g.open} onClick={() => openGame(g.id)}
                className={`w-full text-left pb-card px-4 py-3 ${g.open ? '' : 'opacity-50'}`}>
                <div className="font-medium text-sm">v {g.opponent}</div>
                <div className="text-[12px] text-pb-faint">
                  {[g.round, g.grade].filter(Boolean).join(' · ')}
                  {!g.open && ` · ${NOT_OPEN[g.state] || 'Closed'}`}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {step === 'pin' && pinFor && (
        <div className="pb-card px-4 py-4">
          <div className="font-display font-bold text-[15px] mb-1">{pinFor.display_name}</div>
          <p className="text-[12.5px] text-pb-faint mb-3">
            {pinFor.has_phone
              ? 'Enter the last 4 digits of your mobile number.'
              : "We don't have a mobile number for you. Ask your club to add one."}
          </p>
          <div className="flex gap-2">
            <input value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 4))}
              inputMode="numeric" autoFocus placeholder="0000"
              className="w-24 text-center font-mono bg-pb-surface2 border pb-hairline rounded-lg px-3 py-2" />
            <button disabled={busy || pin.length < 4} onClick={() => verify(pinFor.id, pin)}
              className="px-4 py-2 rounded-lg text-sm bg-pb-accent text-pb-on-accent disabled:opacity-50">
              Verify
            </button>
            <button onClick={() => { setPinFor(null); setPin(''); setStep(game ? 'ballot' : 'games') }}
              className="px-3 py-2 text-sm text-pb-faint">Cancel</button>
          </div>
        </div>
      )}

      {step === 'ballot' && game && (
        <div>
          <button onClick={backToGames} className="text-[12.5px] text-pb-faint underline mb-3">
            ← All games
          </button>
          <div className="font-display font-bold text-lg leading-tight">v {game.game.opponent}</div>
          <div className="text-[12.5px] text-pb-faint mb-4">
            {[game.game.round, game.game.grade].filter(Boolean).join(' · ')}
          </div>

          {game.game.state !== 'open' ? (
            <p className="text-sm text-pb-faint">{NOT_OPEN[game.game.state] || 'Voting has closed.'}</p>
          ) : game.role === 'none' ? (
            <div>
              <p className="text-sm text-pb-faint mb-4">{REASON[game.reason] || "You can't vote on this game."}</p>
              {game.reason === 'verify_required' && (
                <div className="space-y-1.5">
                  {landing.players.map((p) => (
                    <button key={p.id} onClick={() => {
                      if (landing.require_pin) { setPinFor(p); setStep('pin') } else verify(p.id, '')
                    }} className="w-full text-left pb-card px-3 py-2 text-sm">
                      {p.display_name}
                      {landing.require_pin && !p.has_phone && (
                        <span className="ml-2 text-[11px] text-pb-faintest">no mobile on file</span>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div>
              <div className="flex gap-2 mb-4">
                {values.map((v, i) => {
                  const pid = picks[i]
                  const player = game.players.find((p) => p.id === pid)
                  return (
                    <button key={i} onClick={() => pid && tapPlayer(pid)}
                      className={`flex-1 rounded-xl px-2 py-3 text-center border pb-hairline ${
                        pid ? 'bg-pb-accent text-pb-on-accent border-transparent' : 'bg-pb-surface2'}`}>
                      <div className="font-display font-bold text-lg leading-none">{v}</div>
                      <div className="text-[11px] mt-1 truncate">{player?.name || 'tap a name'}</div>
                    </button>
                  )
                })}
              </div>

              {!me && (
                <input value={name} onChange={(e) => setName(e.target.value)}
                  placeholder="Your name"
                  className="w-full mb-3 bg-pb-surface2 border pb-hairline rounded-lg px-3 py-2 text-sm" />
              )}

              <div className="space-y-1 mb-4">
                {game.players.map((p) => {
                  const at = picks.indexOf(p.id)
                  return (
                    <button key={p.id} onClick={() => tapPlayer(p.id)}
                      className={`w-full flex items-center gap-2 pb-card px-3 py-2 text-sm text-left ${
                        at >= 0 ? 'ring-1 ring-pb-accent' : ''}`}>
                      <span className="flex-1 truncate">{p.name}</span>
                      {at >= 0 && (
                        <span className="font-display font-bold text-pb-accent-ink">{values[at]}</span>
                      )}
                    </button>
                  )
                })}
              </div>

              <button disabled={!full || busy || (!me && name.trim().length < 2)} onClick={submit}
                className="w-full py-3 rounded-xl bg-pb-accent text-pb-on-accent font-display font-bold disabled:opacity-50">
                {full ? 'Submit my votes' : `Pick ${picks.filter((x) => !x).length} more`}
              </button>
            </div>
          )}
        </div>
      )}

      {step === 'done' && (
        <div className="text-center py-8">
          <div className="font-display font-bold text-xl mb-2">Thanks, votes in.</div>
          <p className="text-sm text-pb-faint mb-5">
            Your ballot is with the club. You can come back and change it while voting stays open.
          </p>
          <button onClick={backToGames} className="text-sm text-pb-accent underline">Back to games</button>
        </div>
      )}
    </Shell>
  )
}

function Shell({ children, accent }) {
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text"
      style={accent ? { '--pb-accent': accent } : undefined}>
      <div className="max-w-md mx-auto px-4 py-8">{children}</div>
    </div>
  )
}
