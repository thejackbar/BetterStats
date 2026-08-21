// BetterSelect — net check-in (public, no login).
//
// Reached by scanning the QR code on the fence or tapping the NFC tag beside
// it — both hold this one URL (/nets-checkin/:token), because a tag stores a
// URL and nothing else.
//
// Someone walking into the nets, phone in one hand and a kit bag in the other,
// gets: pick your name → prove it's you (if the club asks) → you're in. A
// signed cookie keeps them verified for ~30 days, so week two is a single tap
// on a screen that opens straight onto the CHECK IN button.
//
// Not on the list? A short form registers them, checks them in as a GUEST for
// tonight, and flags them to the club. No player row is created from here.
//
// White-labelled from the club's own colours, mobile-first, and deliberately
// silent about who else is checked in — this page is served to whoever holds
// the link.
import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../lib/api'

function ClubHeader({ club }) {
  const initials = (club?.name || 'Club').split(' ').map((w) => w[0]).join('').slice(0, 3).toUpperCase()
  return (
    <div className="flex flex-col items-center text-center gap-3 mb-6">
      {club?.logo_url
        ? <img src={club.logo_url} alt="" className="w-16 h-16 rounded-xl object-contain bg-pb-surface2 p-1" />
        : <span className="w-16 h-16 rounded-xl flex items-center justify-center font-display font-bold text-xl" style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}>{initials}</span>}
      <div>
        <div className="font-display font-bold text-xl leading-tight">{club?.name || 'Net check-in'}</div>
        <div className="font-mono text-[11px] tracking-wide2 text-pb-faint mt-1">NET CHECK-IN</div>
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

// "Tuesday senior nets · Tue 21 Aug" — what they're checking in to.
function sessionLine(s) {
  let when = s.session_date
  try {
    when = new Date(s.session_date + 'T00:00:00').toLocaleDateString(undefined, {
      weekday: 'short', day: 'numeric', month: 'short',
    })
  } catch { /* leave the ISO date */ }
  return s.label ? `${s.label} · ${when}` : when
}

const FIELD = 'w-full bg-pb-surface2 border pb-hairline rounded-xl px-4 py-3 text-base focus:outline-none focus:border-pb-accent'

export default function PublicNetCheckIn() {
  const { token } = useParams()
  // loading | dead | closed | pick | pin | register | done
  const [step, setStep] = useState('loading')
  const [club, setClub] = useState(null)
  const [requirePin, setRequirePin] = useState(true)
  const [allowRegistration, setAllowRegistration] = useState(true)
  const [sessions, setSessions] = useState([])
  const [players, setPlayers] = useState([])
  const [search, setSearch] = useState('')
  const [chosen, setChosen] = useState(null)
  const [pin, setPin] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState(null) // { name, already_in, sessions, isNew }
  const [form, setForm] = useState({ full_name: '', phone: '', email: '', date_of_birth: '', previous_club: '' })
  const pinRef = useRef(null)

  const accent = club?.accent_color || club?.primary_color || null

  const load = useCallback(async () => {
    const d = await api.netsPublicLanding(token)
    setClub(d.club)
    setRequirePin(!!d.require_pin)
    setAllowRegistration(!!d.allow_registration)
    setSessions(d.sessions || [])
    setPlayers(d.players || [])
    return d
  }, [token])

  useEffect(() => {
    let alive = true
    load()
      .then((d) => {
        if (!alive) return
        // No session on means there is nothing to check in to, whoever you
        // are — say so rather than letting someone tap a name and fail.
        if (!(d.sessions || []).length) { setStep('closed'); return }
        if (d.me) {
          // `verified` matters: the cookie has ALREADY proved who they are, so
          // a returning player must not be asked for the PIN a second time.
          // They land on the button, or straight on the confirmation.
          setChosen({ id: d.me.id, display_name: d.me.display_name, has_phone: true, verified: true })
          if (d.me.checked_in) { setDone({ name: d.me.display_name, already_in: true, sessions: d.sessions }); setStep('done') }
          else setStep('pin')
          return
        }
        setStep('pick')
      })
      .catch(() => { if (alive) setStep('dead') })
    return () => { alive = false }
  }, [load])

  useEffect(() => {
    if (step === 'pin' && requirePin && chosen && !chosen.verified) pinRef.current?.focus()
  }, [step, requirePin, chosen])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return players
    return players.filter((p) => (p.display_name || '').toLowerCase().includes(q))
  }, [players, search])

  async function doCheckIn() {
    setBusy(true); setError('')
    try {
      const r = await api.netsPublicCheckIn(token)
      setDone({ name: r.player?.display_name, already_in: !!r.already_in, sessions: r.sessions || sessions })
      setStep('done')
    } catch (e) {
      setError(e.message || 'Could not check you in.')
    } finally { setBusy(false) }
  }

  async function pickPlayer(p) {
    setChosen(p); setPin(''); setError('')
    if (requirePin) { setStep('pin'); return }
    // No PIN on this club: picking the name IS the check-in, so don't make
    // someone standing at the gate tap twice.
    setBusy(true)
    try {
      await api.netsPublicVerify(token, p.id, '')
      await doCheckIn()
    } catch (e) {
      setError(e.message || 'Could not check you in.')
      setStep('pin')
    } finally { setBusy(false) }
  }

  async function submitPin(e) {
    e.preventDefault()
    if (!chosen) return
    setBusy(true); setError('')
    try {
      await api.netsPublicVerify(token, chosen.id, pin)
      await doCheckIn()
    } catch (e) {
      setError(e.message || 'That didn’t match.')
      setPin('')
    } finally { setBusy(false) }
  }

  async function switchPlayer() {
    try { await api.netsPublicSwitch(token) } catch { /* clearing is best-effort */ }
    setChosen(null); setPin(''); setError(''); setDone(null); setStep('pick')
  }

  async function submitRegister(e) {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      const r = await api.netsPublicRegister(token, {
        full_name: form.full_name,
        phone: form.phone || null,
        email: form.email || null,
        date_of_birth: form.date_of_birth || null,
        previous_club: form.previous_club || null,
      })
      setDone({ name: r.name, already_in: false, sessions: r.sessions || sessions, isNew: true })
      setStep('done')
    } catch (e) {
      setError(e.message || 'Could not register you.')
    } finally { setBusy(false) }
  }

  const verified = chosen && step === 'pin'

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
            <p className="text-pb-faint text-sm mt-2">It may have been turned off or replaced. Ask your club for the current check-in link.</p>
          </div>
        )}

        {step !== 'loading' && step !== 'dead' && <ClubHeader club={club} />}

        {step === 'closed' && (
          <div className="py-10 text-center">
            <div className="text-3xl mb-3">🏏</div>
            <div className="font-display font-bold text-lg">No nets on right now</div>
            <p className="text-pb-faint text-sm mt-2">
              Nobody has opened a session yet. Have a word with whoever is running nets, then scan again.
            </p>
            <button onClick={() => { setStep('loading'); load().then((d) => setStep((d.sessions || []).length ? 'pick' : 'closed')).catch(() => setStep('dead')) }}
              className="mt-6 text-pb-accent text-sm underline">
              Check again
            </button>
          </div>
        )}

        {/* Step 1 — who are you */}
        {step === 'pick' && (
          <div>
            {sessions.length > 0 && (
              <p className="text-center text-pb-faint text-sm mb-4">
                Checking in to <span className="text-pb-text font-medium">{sessions.map(sessionLine).join(' and ')}</span>
              </p>
            )}
            <Banner>{error}</Banner>
            <input
              autoFocus
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search your name…"
              className={`${FIELD} mb-3`}
            />
            <div className="rounded-xl border pb-hairline overflow-hidden divide-y divide-pb-hairline max-h-[50vh] overflow-y-auto">
              {filtered.length === 0 && (
                <div className="px-4 py-6 text-center text-pb-faint text-sm">No players match “{search}”.</div>
              )}
              {filtered.map((p) => (
                <button
                  key={p.id}
                  onClick={() => pickPlayer(p)}
                  disabled={busy}
                  className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-pb-surface2 transition-colors disabled:opacity-50"
                >
                  <span className="text-[15px] font-medium">{p.display_name}</span>
                  {requirePin && !p.has_phone
                    ? <span className="font-mono text-[10px] text-pb-faintest uppercase shrink-0">no mobile</span>
                    : <span className="text-pb-faintest shrink-0">→</span>}
                </button>
              ))}
            </div>

            {allowRegistration ? (
              <button
                onClick={() => { setError(''); setForm((f) => ({ ...f, full_name: f.full_name || search.trim() })); setStep('register') }}
                className="w-full mt-4 py-3.5 rounded-xl font-semibold border pb-hairline hover:bg-pb-surface2 transition"
              >
                I’m not on the list
              </button>
            ) : (
              <p className="text-center text-pb-faintest text-[11px] mt-5">
                Can’t find yourself? Ask whoever is running nets to check you in.
              </p>
            )}
          </div>
        )}

        {/* Step 2 — prove it's you, then check in */}
        {verified && (
          <form onSubmit={submitPin}>
            <div className="text-center mb-5">
              <div className="text-sm text-pb-faint">Hi</div>
              <div className="font-display font-bold text-2xl">{chosen.display_name}</div>
            </div>
            <Banner>{error}</Banner>

            {chosen.verified ? (
              // Verified on a previous visit — the cookie is the proof, so this
              // is one tap. This is what week two at the nets looks like.
              <button
                type="button"
                onClick={doCheckIn}
                disabled={busy}
                className="w-full py-4 rounded-xl font-semibold text-lg transition disabled:opacity-50"
                style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}
              >
                {busy ? 'Checking you in…' : 'Check in'}
              </button>
            ) : requirePin && chosen.has_phone === false ? (
              <div className="text-center text-pb-faint text-sm py-4">
                There’s no mobile number on file for you yet. Ask whoever is running nets to check you in.
                <div className="mt-5"><button type="button" onClick={switchPlayer} className="text-pb-accent text-sm underline">← Pick a different name</button></div>
              </div>
            ) : requirePin ? (
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
                  disabled={pin.length < 4 || busy}
                  className="w-full mt-4 py-3.5 rounded-xl font-semibold transition disabled:opacity-50"
                  style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}
                >
                  {busy ? 'Checking you in…' : 'Check in'}
                </button>
              </>
            ) : (
              // Already verified from a previous visit — one tap and done.
              <button
                type="button"
                onClick={doCheckIn}
                disabled={busy}
                className="w-full py-4 rounded-xl font-semibold text-lg transition disabled:opacity-50"
                style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}
              >
                {busy ? 'Checking you in…' : 'Check in'}
              </button>
            )}

            <div className="text-center mt-5">
              <button type="button" onClick={switchPlayer} className="text-pb-faint text-sm underline">Not you?</button>
            </div>
          </form>
        )}

        {/* Not on the list — register and check in as a guest */}
        {step === 'register' && (
          <form onSubmit={submitRegister}>
            <div className="text-center mb-5">
              <div className="font-display font-bold text-xl">New to the club?</div>
              <p className="text-pb-faint text-sm mt-1.5">
                Leave your details and you’re in for tonight. Someone at the club will pick this up and add you properly.
              </p>
            </div>
            <Banner>{error}</Banner>
            <div className="space-y-3">
              <div>
                <label className="block font-mono text-[11px] tracking-wide2 text-pb-faint uppercase mb-1.5">Full name</label>
                <input autoFocus required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} className={FIELD} placeholder="Jack Barendse" />
              </div>
              <div>
                <label className="block font-mono text-[11px] tracking-wide2 text-pb-faint uppercase mb-1.5">Mobile</label>
                <input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} inputMode="tel" autoComplete="tel" className={FIELD} placeholder="0400 000 000" />
              </div>
              <div>
                <label className="block font-mono text-[11px] tracking-wide2 text-pb-faint uppercase mb-1.5">Email</label>
                <input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} inputMode="email" autoComplete="email" className={FIELD} placeholder="you@example.com" />
              </div>
              <div>
                <label className="block font-mono text-[11px] tracking-wide2 text-pb-faint uppercase mb-1.5">Date of birth</label>
                <input type="date" value={form.date_of_birth} onChange={(e) => setForm({ ...form, date_of_birth: e.target.value })} className={FIELD} />
              </div>
              <div>
                <label className="block font-mono text-[11px] tracking-wide2 text-pb-faint uppercase mb-1.5">Previous club</label>
                <input value={form.previous_club} onChange={(e) => setForm({ ...form, previous_club: e.target.value })} className={FIELD} placeholder="Where you played last" />
              </div>
            </div>
            <button
              type="submit"
              disabled={busy || form.full_name.trim().length < 2}
              className="w-full mt-5 py-3.5 rounded-xl font-semibold transition disabled:opacity-50"
              style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}
            >
              {busy ? 'Checking you in…' : 'Check in'}
            </button>
            <p className="text-center text-pb-faintest text-[11px] mt-3">
              Only your club sees these details.
            </p>
            <div className="text-center mt-4">
              <button type="button" onClick={() => { setError(''); setStep('pick') }} className="text-pb-faint text-sm underline">← Back to the list</button>
            </div>
          </form>
        )}

        {/* Done */}
        {step === 'done' && done && (
          <div className="text-center py-6">
            <div
              className="w-20 h-20 rounded-full mx-auto flex items-center justify-center text-4xl mb-5"
              style={{ background: 'color-mix(in srgb, var(--pb-positive) 15%, transparent)' }}
            >
              ✓
            </div>
            <div className="font-display font-bold text-2xl">
              {done.already_in ? 'You’re already checked in' : 'You’re checked in'}
            </div>
            {done.name && <div className="text-pb-faint mt-1.5">{done.name}</div>}
            {(done.sessions || []).length > 0 && (
              <div className="mt-5 rounded-xl border pb-hairline divide-y divide-pb-hairline overflow-hidden text-left">
                {done.sessions.map((s) => (
                  <div key={s.id} className="px-4 py-3 text-sm">{sessionLine(s)}</div>
                ))}
              </div>
            )}
            {done.isNew && (
              <p className="text-pb-faint text-sm mt-5">
                You’re in as a guest for tonight. The club has your details and will add you to the list.
              </p>
            )}
            <p className="text-pb-faint text-sm mt-5">Grab your pads.</p>
            <div className="mt-6">
              <button onClick={switchPlayer} className="text-pb-faint text-sm underline">Checking someone else in?</button>
            </div>
          </div>
        )}

        {step !== 'loading' && step !== 'dead' && (
          <div className="text-center mt-10 font-mono text-[10px] tracking-wide2 text-pb-faintest">
            Powered by BetterCricket
          </div>
        )}
      </div>
    </div>
  )
}
