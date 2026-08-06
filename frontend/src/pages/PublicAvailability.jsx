// BetterSelect — self-service player availability (public, no login).
//
// Reached via a per-club magic link (/avail/:token) pinned in a group chat or a
// QR. Three mobile-first steps: pick your name → prove it's you with the last 4
// digits of your mobile → tap Available / Maybe / Unavailable for the weekend.
// A signed cookie keeps you verified (~30 days); "Not you?" clears it.
//
// White-labelled from the club's own colours; the only dependency on the rest of
// the app is the shared availability colour map so a player's chips match the
// admin matrix exactly.
import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { AVAILABILITY } from '../lib/availability'

// The three answers a player can give (NO_RESPONSE is the absence of one).
const CHOICES = ['AVAILABLE', 'MAYBE', 'UNAVAILABLE']

function fmtDay(d) {
  try {
    return new Date(d + 'T00:00:00').toLocaleDateString(undefined, {
      weekday: 'long', day: 'numeric', month: 'short',
    })
  } catch { return d }
}

// "vs Willetton · @ Melville" — one line summarising a date's fixtures.
function fixtureSub(dateObj) {
  const fxs = dateObj.fixtures || []
  if (!fxs.length) return ''
  return fxs.map((f) => {
    const opp = f.opponent_name || f.label || 'TBC'
    const prefix = f.home_away === 'AWAY' ? '@ ' : f.home_away === 'BYE' ? '' : 'vs '
    const d1d2 = f.two_day ? (f.role === 'day1' ? 'D1 ' : f.role === 'day2' ? 'D2 ' : '') : ''
    return `${d1d2}${prefix}${opp}`
  }).join(' · ')
}

function ClubHeader({ club }) {
  const initials = (club?.name || 'Club').split(' ').map((w) => w[0]).join('').slice(0, 3).toUpperCase()
  return (
    <div className="flex flex-col items-center text-center gap-3 mb-6">
      {club?.logo_url
        ? <img src={club.logo_url} alt="" className="w-16 h-16 rounded-xl object-contain bg-pb-surface2 p-1" />
        : <span className="w-16 h-16 rounded-xl flex items-center justify-center font-display font-bold text-xl" style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}>{initials}</span>}
      <div>
        <div className="font-display font-bold text-xl leading-tight">{club?.name || 'Set your availability'}</div>
        <div className="font-mono text-[11px] tracking-wide2 text-pb-faint mt-1">SET YOUR AVAILABILITY</div>
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

export default function PublicAvailability() {
  const { token } = useParams()
  const [step, setStep] = useState('loading') // loading | pick | pin | weekend | dead
  const [club, setClub] = useState(null)
  const [requirePin, setRequirePin] = useState(true)
  const [players, setPlayers] = useState([])
  const [search, setSearch] = useState('')
  const [chosen, setChosen] = useState(null) // {id, display_name, has_phone}
  const [pin, setPin] = useState('')
  const [verifying, setVerifying] = useState(false)
  const [error, setError] = useState('')
  const [me, setMe] = useState(null) // {player, dates, availability}
  const [savingDate, setSavingDate] = useState(null)
  const [savedDate, setSavedDate] = useState(null)
  const pinRef = useRef(null)

  // White-label: re-point --pb-accent (and its rgb form, used by a few tints) to
  // the club's colour for this page only. Falls back to the brand green.
  const accent = club?.accent_color || club?.primary_color || null

  const enterWeekend = useCallback(async () => {
    try {
      const data = await api.availPublicMe(token)
      setMe(data)
      if (data.club) setClub((c) => c || data.club)
      setStep('weekend')
      setError('')
    } catch (e) {
      // Cookie missing/expired — fall back to picking a name.
      setStep('pick')
    }
  }, [token])

  // Load branding + roster, and resume an existing verified session if present.
  useEffect(() => {
    let alive = true
    api.availPublicLanding(token)
      .then(async (d) => {
        if (!alive) return
        setClub(d.club)
        setRequirePin(d.require_pin)
        setPlayers(d.players || [])
        // Already verified on this device? Jump straight to the weekend.
        try {
          const mine = await api.availPublicMe(token)
          if (!alive) return
          setMe(mine)
          setStep('weekend')
        } catch {
          if (alive) setStep('pick')
        }
      })
      .catch(() => { if (alive) setStep('dead') })
    return () => { alive = false }
  }, [token])

  useEffect(() => { if (step === 'pin' && pinRef.current) pinRef.current.focus() }, [step])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return players
    return players.filter((p) => p.display_name.toLowerCase().includes(q))
  }, [players, search])

  const pickPlayer = async (p) => {
    setChosen(p)
    setPin('')
    setError('')
    if (requirePin) {
      setStep('pin')
      return
    }
    // No PIN required — verify with the name alone.
    await doVerify(p, '')
  }

  const doVerify = async (player, pinValue) => {
    setVerifying(true)
    setError('')
    try {
      await api.availPublicVerify(token, player.id, pinValue)
      await enterWeekend()
    } catch (e) {
      setError(e.message || 'That didn’t match. Please try again.')
    } finally {
      setVerifying(false)
    }
  }

  const submitPin = (e) => {
    e.preventDefault()
    if (!chosen || pin.length < 4) return
    doVerify(chosen, pin)
  }

  const switchPlayer = async () => {
    try { await api.availPublicSwitch(token) } catch {}
    setMe(null); setChosen(null); setPin(''); setSearch(''); setError('')
    setStep('pick')
  }

  const setAnswer = async (d, status) => {
    const prev = me
    // Optimistic — reflect the tap immediately.
    setMe((m) => ({ ...m, availability: { ...(m.availability || {}), [d]: { status, source: 'self' } } }))
    setSavingDate(d)
    try {
      await api.availPublicSet(token, { date: d, status })
      setSavedDate(d)
      setTimeout(() => setSavedDate((cur) => (cur === d ? null : cur)), 1600)
    } catch (e) {
      setMe(prev) // roll back
      setError(e.message || 'Couldn’t save — please try again.')
    } finally {
      setSavingDate((cur) => (cur === d ? null : cur))
    }
  }

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text" style={accent ? { '--pb-accent': accent } : undefined}>
      <div className="max-w-md mx-auto px-4 py-8 sm:py-12">
        {step === 'loading' && (
          <div className="py-24 text-center text-pb-faint text-sm">Loading…</div>
        )}

        {step === 'dead' && (
          <div className="py-20 text-center">
            <div className="text-3xl mb-3">🔗</div>
            <div className="font-display font-bold text-lg">This link isn’t active</div>
            <p className="text-pb-faint text-sm mt-2">It may have been turned off or replaced. Ask your club for the current availability link.</p>
          </div>
        )}

        {step !== 'loading' && step !== 'dead' && <ClubHeader club={club} />}

        {/* Step 1 — pick your name */}
        {step === 'pick' && (
          <div>
            <input
              autoFocus
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search your name…"
              className="w-full bg-pb-surface2 border pb-hairline rounded-xl px-4 py-3 text-base focus:outline-none focus:border-pb-accent mb-3"
            />
            <div className="rounded-xl border pb-hairline overflow-hidden divide-y divide-pb-hairline max-h-[55vh] overflow-y-auto">
              {filtered.length === 0 && (
                <div className="px-4 py-6 text-center text-pb-faint text-sm">No players match “{search}”.</div>
              )}
              {filtered.map((p) => (
                <button
                  key={p.id}
                  onClick={() => pickPlayer(p)}
                  className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-pb-surface2 transition-colors"
                >
                  <span className="text-[15px] font-medium">{p.display_name}</span>
                  {requirePin && !p.has_phone
                    ? <span className="font-mono text-[10px] text-pb-faintest uppercase shrink-0">no mobile</span>
                    : <span className="text-pb-faintest shrink-0">→</span>}
                </button>
              ))}
            </div>
            <p className="text-center text-pb-faintest text-[11px] mt-5">
              Can’t find yourself, or no mobile on file? Ask your club admin.
            </p>
          </div>
        )}

        {/* Step 2 — prove it's you */}
        {step === 'pin' && chosen && (
          <form onSubmit={submitPin}>
            <div className="text-center mb-5">
              <div className="text-sm text-pb-faint">Hi</div>
              <div className="font-display font-bold text-2xl">{chosen.display_name}</div>
            </div>
            <Banner>{error}</Banner>
            {!chosen.has_phone ? (
              <div className="text-center text-pb-faint text-sm py-4">
                There’s no mobile number on file for you yet. Ask your club admin to add it, or to set your availability for you.
                <div className="mt-5"><button type="button" onClick={switchPlayer} className="text-pb-accent text-sm underline">← Pick a different name</button></div>
              </div>
            ) : (
              <>
                <label className="block text-center font-mono text-[11px] tracking-wide2 text-pb-faint uppercase mb-2">
                  Last 4 digits of your mobile
                </label>
                <input
                  ref={pinRef}
                  value={pin}
                  onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 4))}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="••••"
                  className="w-full text-center tracking-[0.6em] text-2xl font-mono bg-pb-surface2 border pb-hairline rounded-xl px-4 py-3.5 focus:outline-none focus:border-pb-accent"
                />
                <button
                  type="submit"
                  disabled={pin.length < 4 || verifying}
                  className="w-full mt-4 py-3.5 rounded-xl font-semibold text-pb-bg transition disabled:opacity-50"
                  style={{ background: 'var(--pb-accent)' }}
                >
                  {verifying ? 'Checking…' : 'Continue'}
                </button>
                <button type="button" onClick={switchPlayer} className="block mx-auto mt-4 text-pb-faint text-sm hover:text-pb-text">
                  ← Not you? Pick a different name
                </button>
              </>
            )}
          </form>
        )}

        {/* Step 3 — your weekend */}
        {step === 'weekend' && me && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="font-mono text-[11px] text-pb-faint">Signed in as</div>
                <div className="font-display font-bold text-lg">{me.player?.display_name}</div>
              </div>
              <button onClick={switchPlayer} className="text-pb-faint text-xs hover:text-pb-text underline shrink-0">Not you?</button>
            </div>
            <Banner>{error}</Banner>

            {(me.dates || []).length === 0 && (
              <div className="rounded-xl border pb-hairline px-4 py-10 text-center text-pb-faint text-sm">
                No upcoming fixtures to set availability for yet. Check back soon.
              </div>
            )}

            <div className="flex flex-col gap-3">
              {(me.dates || []).map((d) => {
                const cur = me.availability?.[d.date]?.status || 'NO_RESPONSE'
                const sub = fixtureSub(d)
                return (
                  <div key={d.date} className="rounded-xl border pb-hairline p-3.5">
                    <div className="flex items-baseline justify-between gap-2 mb-3">
                      <div>
                        <div className="font-display font-bold text-[15px]">{fmtDay(d.date)}</div>
                        {sub && <div className="text-[12px] text-pb-faint mt-0.5">{sub}</div>}
                      </div>
                      {savedDate === d.date && <span className="font-mono text-[10px]" style={{ color: 'var(--pb-positive)' }}>SAVED ✓</span>}
                    </div>
                    <div className="grid grid-cols-3 gap-2">
                      {CHOICES.map((s) => {
                        const meta = AVAILABILITY[s]
                        const active = cur === s
                        return (
                          <button
                            key={s}
                            onClick={() => setAnswer(d.date, s)}
                            disabled={savingDate === d.date}
                            className="py-2.5 rounded-lg text-sm font-semibold transition disabled:opacity-60"
                            style={active
                              ? { background: meta.cssVar, color: 'var(--pb-bg)' }
                              : { background: `color-mix(in srgb, ${meta.cssVar} 12%, transparent)`, color: meta.cssVar, border: `1px solid color-mix(in srgb, ${meta.cssVar} 30%, transparent)` }}
                          >
                            {meta.glyph} {meta.label}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </div>
            <p className="text-center text-pb-faintest text-[11px] mt-6">
              Your answers save automatically. One tap covers every game that day.
            </p>
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
