import { useEffect, useRef, useState } from 'react'
import { FORMSPREE_ID } from '../data/marketing'
import { api } from '../lib/api'
import { getVisitorId } from '../lib/visitor'

const FORMSPREE_URL = `https://formspree.io/f/${FORMSPREE_ID}`

const EMPTY = { club: '', email: '', name: '', message: '' }

// Short capture form opened from ClubCTABar — the fast path for a cold ad
// visitor who won't sit through the full /contact form. Same delivery as
// Contact.jsx (Formspree + best-effort onboarding row + the Lead pixel), just
// three required characters shorter: club and email only.
export default function QuickEnquiryModal({ onClose }) {
  const [fields, setFields] = useState(EMPTY)
  const [errors, setErrors] = useState({})
  const [status, setStatus] = useState('idle') // idle | submitting | success | error
  const dialogRef = useRef(null)
  const firstFieldRef = useRef(null)

  useEffect(() => {
    firstFieldRef.current?.focus()
    const handleKey = (e) => {
      if (e.key === 'Escape') { onClose(); return }
      if (e.key !== 'Tab') return
      const focusable = dialogRef.current?.querySelectorAll(
        'input, textarea, button:not([disabled])'
      )
      if (!focusable || focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault(); last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus()
      }
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [onClose])

  const set = (key) => (e) => setFields((f) => ({ ...f, [key]: e.target.value }))

  function validate() {
    const e = {}
    if (!fields.club.trim()) e.club = 'Club name is required.'
    if (!fields.email.trim()) e.email = 'Email address is required.'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(fields.email)) e.email = 'Please enter a valid email.'
    return e
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }
    setErrors({})
    setStatus('submitting')

    api.submitOnboarding({
      name: fields.name,
      club: fields.club,
      email: fields.email,
      message: fields.message,
      source: 'cta_quick_form',
      visitorId: getVisitorId(),
    }).catch(() => {})

    try {
      const res = await fetch(FORMSPREE_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({
          name: fields.name || '—',
          club: fields.club,
          email: fields.email,
          message: fields.message || '—',
          _subject: `BetterCricket quick enquiry — ${fields.club}`,
        }),
      })
      const data = await res.json()
      if (res.ok && data.ok !== false) {
        setStatus('success')
        if (typeof window !== 'undefined' && typeof window.fbq === 'function') {
          window.fbq('track', 'Lead', {
            content_name: 'Request access',
            content_category: 'club_enquiry',
            value: 399,
            currency: 'AUD',
          })
        }
      } else {
        setStatus('error')
      }
    } catch {
      setStatus('error')
    }
  }

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center p-4"
      onMouseDown={onClose}
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="quick-enquiry-title"
        onMouseDown={(e) => e.stopPropagation()}
        className="surface relative w-full max-w-md p-6 sm:p-7 rounded-2xl"
      >
        <button
          onClick={onClose}
          aria-label="Close"
          className="absolute top-4 right-4 p-1 rounded text-pb-faint hover:text-pb-text hover:bg-pb-surface2 transition"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>

        {status === 'success' ? (
          <div className="text-center py-4">
            <div className="w-14 h-14 rounded-full bg-accent/15 border border-accent/40 flex items-center justify-center mx-auto mb-5 text-2xl">✓</div>
            <h2 className="text-xl font-bold mb-2">We've got it</h2>
            <p className="text-pb-dim text-sm">We'll be in touch within 24 hours.</p>
            <button onClick={onClose} className="cta-secondary !text-sm mt-6">Close</button>
          </div>
        ) : (
          <>
            <h2 id="quick-enquiry-title" className="text-xl font-bold mb-1.5">Get your club on BetterCricket</h2>
            <p className="text-sm text-pb-dim mb-5">Two fields, that's it. We'll take it from there.</p>

            <form onSubmit={handleSubmit} noValidate className="space-y-3.5">
              <input type="text" name="_gotcha" className="hidden" tabIndex="-1" autoComplete="off" />

              <div>
                <label htmlFor="qe-club" className="block text-sm font-medium mb-1.5">
                  Club name<span className="text-accent ml-0.5">*</span>
                </label>
                <input
                  id="qe-club" ref={firstFieldRef} type="text" name="club"
                  placeholder="Applecross CC"
                  value={fields.club} onChange={set('club')}
                  className={`w-full rounded-lg px-4 py-2.5 text-sm text-white placeholder:text-pb-faint bg-[#161b27] border ${errors.club ? 'border-red-500/60' : 'border-pb-hairline'} focus:outline-none focus:border-accent/60 transition-colors`}
                />
                {errors.club && <p className="mt-1 text-xs text-red-400">{errors.club}</p>}
              </div>

              <div>
                <label htmlFor="qe-email" className="block text-sm font-medium mb-1.5">
                  Email address<span className="text-accent ml-0.5">*</span>
                </label>
                <input
                  id="qe-email" type="email" name="email" autoComplete="email"
                  placeholder="adam@applecrosscc.com"
                  value={fields.email} onChange={set('email')}
                  className={`w-full rounded-lg px-4 py-2.5 text-sm text-white placeholder:text-pb-faint bg-[#161b27] border ${errors.email ? 'border-red-500/60' : 'border-pb-hairline'} focus:outline-none focus:border-accent/60 transition-colors`}
                />
                {errors.email && <p className="mt-1 text-xs text-red-400">{errors.email}</p>}
              </div>

              <div>
                <label htmlFor="qe-name" className="block text-sm font-medium mb-1.5">
                  Your name <span className="text-pb-faint text-xs font-normal">(optional)</span>
                </label>
                <input
                  id="qe-name" type="text" name="name" autoComplete="name"
                  placeholder="Adam Gilchrist"
                  value={fields.name} onChange={set('name')}
                  className="w-full rounded-lg px-4 py-2.5 text-sm text-white placeholder:text-pb-faint bg-[#161b27] border border-pb-hairline focus:outline-none focus:border-accent/60 transition-colors"
                />
              </div>

              <div>
                <label htmlFor="qe-message" className="block text-sm font-medium mb-1.5">
                  Anything we should know? <span className="text-pb-faint text-xs font-normal">(optional)</span>
                </label>
                <input
                  id="qe-message" type="text" name="message"
                  placeholder="e.g. we've got 60 years of scorebooks to get in"
                  value={fields.message} onChange={set('message')}
                  className="w-full rounded-lg px-4 py-2.5 text-sm text-white placeholder:text-pb-faint bg-[#161b27] border border-pb-hairline focus:outline-none focus:border-accent/60 transition-colors"
                />
              </div>

              {status === 'error' && (
                <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3">
                  Something went wrong. Please try again.
                </p>
              )}

              <button
                type="submit"
                disabled={status === 'submitting'}
                className="cta-primary w-full justify-center !py-3 disabled:opacity-60 disabled:cursor-not-allowed disabled:transform-none"
              >
                {status === 'submitting' ? 'Sending…' : 'Send →'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
