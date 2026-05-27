import { useState } from 'react'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import Reveal from '../../components/marketing/Reveal'
import { FORMSPREE_ID, SUPPORT_EMAIL } from '../../data/marketing'
import { usePageMeta } from '../../hooks/usePageMeta'

const FORMSPREE_URL = `https://formspree.io/f/${FORMSPREE_ID}`

function Field({ label, id, required, error, children }) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium mb-1.5">
        {label}{required && <span className="text-accent ml-0.5">*</span>}
      </label>
      {children}
      {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
    </div>
  )
}

function ContactForm() {
  const [fields, setFields] = useState({ name: '', club: '', email: '', message: '' })
  const [errors, setErrors] = useState({})
  const [status, setStatus] = useState('idle') // idle | submitting | success | error

  function validate() {
    const e = {}
    if (!fields.name.trim())    e.name    = 'Your name is required.'
    if (!fields.club.trim())    e.club    = 'Club name is required.'
    if (!fields.email.trim())   e.email   = 'Email address is required.'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(fields.email)) e.email = 'Please enter a valid email.'
    if (!fields.message.trim()) e.message = 'Please tell us a bit about what you need.'
    return e
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }
    setErrors({})
    setStatus('submitting')
    try {
      const res = await fetch(FORMSPREE_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({
          name:    fields.name,
          club:    fields.club,
          email:   fields.email,
          message: fields.message,
          // Formspree subject line
          _subject: `BetterStats enquiry — ${fields.club}`,
        }),
      })
      const data = await res.json()
      if (res.ok && data.ok !== false) {
        setStatus('success')
      } else {
        setStatus('error')
      }
    } catch {
      setStatus('error')
    }
  }

  const inputClass = (field) =>
    `w-full bg-pb-surface2/50 border ${errors[field] ? 'border-red-500/60' : 'border-pb-hairline'} rounded-lg px-4 py-2.5 text-sm text-pb-text placeholder:text-pb-faint focus:outline-none focus:border-accent/60 transition-colors`

  if (status === 'success') {
    return (
      <div className="surface p-8 lg:p-10 text-center">
        <div className="w-14 h-14 rounded-full bg-accent/15 border border-accent/40 flex items-center justify-center mx-auto mb-5 text-2xl">✓</div>
        <h2 className="text-2xl font-bold mb-2">We've got it!</h2>
        <p className="text-pb-dim mb-6">
          Thanks for reaching out. We'll get back to you within 24 hours, usually the same day.
        </p>
        <button
          onClick={() => { setStatus('idle'); setFields({ name: '', club: '', email: '', message: '' }) }}
          className="cta-secondary !text-sm"
        >
          Send another message
        </button>
      </div>
    )
  }

  return (
    <div className="surface p-7 lg:p-9">
      <div className="mb-6">
        <h2 className="text-2xl font-bold mb-1">Get in touch</h2>
        <p className="text-sm text-pb-dim">Tell us about your club and we'll get back to you within 24 hours.</p>
      </div>

      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {/* Honeypot — hidden from real users, catches bots */}
        <input type="text" name="_gotcha" className="hidden" tabIndex="-1" autoComplete="off" />

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Your name" id="name" required error={errors.name}>
            <input
              id="name" type="text" name="name" autoComplete="name"
              placeholder="Jack Barendse"
              value={fields.name}
              onChange={e => setFields(f => ({ ...f, name: e.target.value }))}
              className={inputClass('name')}
            />
          </Field>
          <Field label="Club name" id="club" required error={errors.club}>
            <input
              id="club" type="text" name="club"
              placeholder="Applecross CC"
              value={fields.club}
              onChange={e => setFields(f => ({ ...f, club: e.target.value }))}
              className={inputClass('club')}
            />
          </Field>
        </div>

        <Field label="Email address" id="email" required error={errors.email}>
          <input
            id="email" type="email" name="email" autoComplete="email"
            placeholder="jack@applecrosscc.com.au"
            value={fields.email}
            onChange={e => setFields(f => ({ ...f, email: e.target.value }))}
            className={inputClass('email')}
          />
        </Field>

        <Field label="How can we help?" id="message" required error={errors.message}>
          <textarea
            id="message" name="message" rows={4}
            placeholder="Tell us about your club — which competition you play in, what you're hoping to get out of BetterStats, and anything else that's useful."
            value={fields.message}
            onChange={e => setFields(f => ({ ...f, message: e.target.value }))}
            className={`${inputClass('message')} resize-none`}
          />
        </Field>

        {status === 'error' && (
          <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3">
            Something went wrong — please try again or email us directly at{' '}
            <a href={`mailto:${SUPPORT_EMAIL}`} className="underline">{SUPPORT_EMAIL}</a>.
          </p>
        )}

        <button
          type="submit"
          disabled={status === 'submitting'}
          className="cta-primary w-full justify-center !py-3.5 disabled:opacity-60 disabled:cursor-not-allowed disabled:transform-none"
          aria-label="Send message"
        >
          {status === 'submitting' ? (
            <span className="flex items-center gap-2">
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Sending…
            </span>
          ) : 'Send message →'}
        </button>

        <p className="text-xs text-pb-faint text-center">
          We respond within 24 hours, usually same day.
        </p>
      </form>
    </div>
  )
}

function ContactPanel() {
  return (
    <section className="relative pt-32 pb-20 px-4 sm:px-6 lg:px-10 overflow-hidden">
      <div className="absolute inset-0 hero-glow opacity-70 pointer-events-none" />
      <div className="max-w-[1000px] mx-auto relative">
        <div className="grid grid-cols-12 gap-10">
          <div className="col-span-12 lg:col-span-5">
            <p className="pill mb-6 inline-flex"><span className="dot" />Reply within 24 hours</p>
            <h1 className="font-display font-bold text-[40px] sm:text-[52px] lg:text-[60px] tracking-tight leading-[0.95] mb-6">
              Tell us about <span className="gradient-text">your club.</span>
            </h1>
            <p className="text-lg text-pb-dim leading-relaxed mb-8">
              Drop your details and we'll come back within 24 hours with a short demo specific to your club, your colours, and (if you give us a PlayHQ URL) your actual data.
            </p>

            <div className="space-y-4">
              <div className="flex items-start gap-3">
                <div className="icon-tile flex-shrink-0">✉</div>
                <div>
                  <p className="text-sm font-semibold mb-0.5">Email</p>
                  <a href={`mailto:${SUPPORT_EMAIL}`} className="text-sm text-accent hover:underline">{SUPPORT_EMAIL}</a>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <div className="icon-tile flex-shrink-0">⚲</div>
                <div>
                  <p className="text-sm font-semibold mb-0.5">Based in</p>
                  <p className="text-sm text-pb-dim">Perth, WA · We work with clubs Australia-wide.</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <div className="icon-tile flex-shrink-0">⏱</div>
                <div>
                  <p className="text-sm font-semibold mb-0.5">Response time</p>
                  <p className="text-sm text-pb-dim">Within 24 hours, usually same day.</p>
                </div>
              </div>
            </div>
          </div>

          <div className="col-span-12 lg:col-span-7">
            <Reveal>
              <ContactForm />
            </Reveal>
          </div>
        </div>
      </div>
    </section>
  )
}

export default function Contact() {
  usePageMeta({
    title: 'Contact — Request Access for Your Cricket Club | BetterStats',
    description: 'Request access for your Australian cricket club, ask a question, or email the BetterStats team directly at betterstatsau@gmail.com.',
    image: 'https://betterstats.cricket/og-image.png',
    url: 'https://betterstats.cricket/contact',
  })
  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <MarketingNav />
      <div id="main-content" tabIndex="-1">
        <ContactPanel />
      </div>
      <MarketingFooter />
    </div>
  )
}
