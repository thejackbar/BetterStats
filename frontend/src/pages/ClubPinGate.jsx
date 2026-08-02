import { useState } from 'react'
import MarketingFooter from '../components/marketing/MarketingFooter'
import { BRAND } from '../data/marketing'

/**
 * Shown when a public club page is password-protected (423 from the API) —
 * see useClub.js's `locked` state. Two copy variants driven by
 * lockInfo.reason (set server-side, never client-chosen):
 *  - 'draft'       — voluntary privacy. Plain PIN entry, no request form (the
 *                     admin already knows their own PIN).
 *  - 'trial_ended' — the sales-conversion gate. PIN entry PLUS an "email me
 *                     for access" request form that creates a lead for
 *                     Super Admin to follow up.
 * Styled like ClubInactive.jsx's hero treatment for visual consistency with
 * the other "can't show you the real page" states.
 */
export default function ClubPinGate({ slug, lockInfo, unlock, requestAccess }) {
  const [pin, setPin] = useState('')
  const [pinError, setPinError] = useState('')
  const [unlocking, setUnlocking] = useState(false)

  const [showRequest, setShowRequest] = useState(false)
  const [email, setEmail] = useState('')
  const [message, setMessage] = useState('')
  const [requestSent, setRequestSent] = useState(false)
  const [requestError, setRequestError] = useState('')
  const [sending, setSending] = useState(false)

  const name = lockInfo?.name || lockInfo?.short_name
  const isTrialEnded = lockInfo?.reason === 'trial_ended'

  const submitPin = async (e) => {
    e.preventDefault()
    if (pin.length !== 4) return
    setUnlocking(true)
    setPinError('')
    try {
      await unlock(pin)
    } catch (err) {
      setPinError(err.message || "That PIN didn't match. Try again.")
      setPin('')
    } finally {
      setUnlocking(false)
    }
  }

  const submitRequest = async (e) => {
    e.preventDefault()
    if (!email.trim()) return
    setSending(true)
    setRequestError('')
    try {
      await requestAccess(email.trim(), message.trim())
      setRequestSent(true)
    } catch (err) {
      setRequestError(err.message || 'Could not send your request — try again shortly.')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text flex flex-col">
      <section className="relative flex-1 flex items-center overflow-hidden px-4 sm:px-6 lg:px-10 pt-28 pb-24">
        <div className="absolute inset-0 hero-glow opacity-70 pointer-events-none" />

        <div className="max-w-[520px] mx-auto relative z-10 text-center">
          <p className="pill mb-7 inline-flex"><span className="dot" />Private page</p>

          {lockInfo?.logo_url && (
            <img src={lockInfo.logo_url} alt={name} className="w-16 h-16 rounded-full object-cover mx-auto mb-5 border-pb-hairline border" />
          )}

          <h1 className="font-display font-bold text-[32px] sm:text-[40px] tracking-tight leading-[0.95] mb-4">
            {name ? `${name} is` : 'This page is'} <span className="gradient-text">private.</span>
          </h1>

          <p className="text-base text-pb-dim leading-relaxed mb-8">
            {lockInfo?.message || 'This club’s page is currently private. Enter the access PIN to view it.'}
          </p>

          <form onSubmit={submitPin} className="pb-card p-6 mb-5 text-left">
            <label className="block text-xs font-mono tracking-wide2 text-pb-faint mb-2">4-DIGIT ACCESS PIN</label>
            <div className="flex gap-3 items-center">
              <input
                type="text"
                inputMode="numeric"
                pattern="\d{4}"
                maxLength={4}
                autoFocus
                value={pin}
                onChange={e => { setPin(e.target.value.replace(/\D/g, '').slice(0, 4)); setPinError('') }}
                className="flex-1 bg-pb-surface2 border pb-hairline rounded px-4 py-3 text-center text-2xl tracking-[0.5em] font-mono text-pb-text focus:outline-none focus:border-pb-accent"
                placeholder="••••"
              />
              <button
                type="submit"
                disabled={pin.length !== 4 || unlocking}
                className="cta-primary whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {unlocking ? 'Checking…' : 'Unlock'}
              </button>
            </div>
            {pinError && <p className="text-sm text-pb-red mt-3">{pinError}</p>}
          </form>

          {isTrialEnded && (
            <div className="pb-card p-6 text-left">
              {requestSent ? (
                <p className="text-sm text-pb-text">
                  Thanks — someone from {BRAND} will be in touch shortly.
                </p>
              ) : showRequest ? (
                <form onSubmit={submitRequest}>
                  <label className="block text-xs font-mono tracking-wide2 text-pb-faint mb-2">DON'T HAVE THE PIN? REQUEST ACCESS</label>
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text focus:outline-none focus:border-pb-accent mb-2"
                  />
                  <textarea
                    value={message}
                    onChange={e => setMessage(e.target.value)}
                    placeholder="Anything you'd like to add (optional)"
                    rows={2}
                    className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text focus:outline-none focus:border-pb-accent mb-3"
                  />
                  {requestError && <p className="text-sm text-pb-red mb-3">{requestError}</p>}
                  <button type="submit" disabled={sending} className="cta-secondary w-full disabled:opacity-50">
                    {sending ? 'Sending…' : 'Send request'}
                  </button>
                </form>
              ) : (
                <button onClick={() => setShowRequest(true)} className="text-sm text-pb-accent hover:underline">
                  Don't have the PIN? Request access →
                </button>
              )}
            </div>
          )}
        </div>
      </section>

      <MarketingFooter />
    </div>
  )
}
