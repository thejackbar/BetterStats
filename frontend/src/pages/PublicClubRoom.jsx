// Club Room Mode — public link (no login).
//
// Reached via a per-club link (/room/:token) set by a club admin or Super
// Admin — pinned to a TV/Chromebook in the club room so the show can run
// without anyone staying logged into an admin session on that browser. A
// signed cookie remembers a correct PIN for ~30 days, so re-opening the same
// browser tab (a TV rebooting, say) doesn't ask again.
//
// Once unlocked this renders exactly the same stage the authenticated admin
// preview does — see ClubRoomStage.jsx, which owns all the actual slideshow
// rendering/rotation/timing.
import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../lib/api'
import ClubRoomStage from './admin/ClubRoomStage'

function Banner({ tone = 'error', children }) {
  if (!children) return null
  const color = tone === 'error' ? 'var(--pb-red)' : 'var(--pb-amber)'
  return (
    <div className="rounded-lg px-3.5 py-2.5 mb-4 text-sm"
      style={{ background: `color-mix(in srgb, ${color} 12%, transparent)`, color, border: `1px solid color-mix(in srgb, ${color} 35%, transparent)` }}>
      {children}
    </div>
  )
}

export default function PublicClubRoom() {
  const { token } = useParams()
  const [step, setStep] = useState('loading') // loading | dead | pin | show
  const [landing, setLanding] = useState(null)
  const [pin, setPin] = useState('')
  const [error, setError] = useState('')
  const [verifying, setVerifying] = useState(false)
  const pinRef = useRef(null)

  useEffect(() => {
    let alive = true
    api.publicClubRoomLanding(token)
      .then((d) => {
        if (!alive) return
        setLanding(d)
        setStep(d.unlocked ? 'show' : 'pin')
      })
      .catch(() => alive && setStep('dead'))
    return () => { alive = false }
  }, [token])

  useEffect(() => { if (step === 'pin' && pinRef.current) pinRef.current.focus() }, [step])

  // Stable across re-renders (only changes if the token itself changes,
  // which it won't for the life of this page) — ClubRoomStage re-fetches
  // whenever this reference changes, so an unstable one would restart the
  // poll loop on every render.
  const fetchPlay = useCallback(() => api.publicClubRoomPlay(token), [token])

  const submitPin = async (e) => {
    e.preventDefault()
    if (pin.length < 4 || verifying) return
    setVerifying(true)
    setError('')
    try {
      await api.publicClubRoomVerify(token, pin)
      setStep('show')
    } catch (e2) {
      setError(e2.status === 429 ? e2.message : 'Wrong PIN. Try again.')
      setPin('')
    } finally {
      setVerifying(false)
    }
  }

  if (step === 'show') {
    return <ClubRoomStage fetchPlay={fetchPlay} />
  }

  const initials = (landing?.club_name || landing?.club_short || 'Club').slice(0, 3).toUpperCase()

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text flex items-center justify-center px-4">
      <div className="w-full max-w-sm py-8">
        {step === 'loading' && <div className="py-24 text-center text-pb-faint text-sm">Loading…</div>}

        {step === 'dead' && (
          <div className="py-20 text-center">
            <div className="font-display font-bold text-lg">This link isn't active</div>
            <p className="text-pb-faint text-sm mt-2">
              It may have been turned off or replaced. Ask your club for the current Club Room link.
            </p>
          </div>
        )}

        {step === 'pin' && landing && (
          <form onSubmit={submitPin}>
            <div className="flex flex-col items-center text-center gap-3 mb-6">
              {landing.logo_url
                ? <img src={landing.logo_url} alt="" className="w-16 h-16 rounded-xl object-contain bg-pb-surface2 p-1" />
                : <span className="w-16 h-16 rounded-xl flex items-center justify-center font-display font-bold text-xl" style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}>{initials}</span>}
              <div>
                <div className="font-display font-bold text-xl leading-tight">{landing.club_name || 'Club Room'}</div>
                <div className="font-mono text-[11px] tracking-wide2 text-pb-faint mt-1">CLUB ROOM MODE</div>
              </div>
            </div>
            <Banner>{error}</Banner>
            <label className="block text-center font-mono text-[11px] tracking-wide2 text-pb-faint uppercase mb-2">
              Enter the access PIN
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
              {verifying ? 'Checking…' : 'Unlock'}
            </button>
            <p className="text-center text-pb-faintest text-[11px] mt-5">
              Ask your club admin for the PIN if you don't have it.
            </p>
          </form>
        )}
      </div>
    </div>
  )
}
