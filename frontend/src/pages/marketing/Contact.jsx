import { useState } from 'react'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import Reveal from '../../components/marketing/Reveal'
import { FORMSPREE_ID, SUPPORT_EMAIL } from '../../data/marketing'
import { usePageMeta } from '../../hooks/usePageMeta'

const FORMSPREE_URL = `https://formspree.io/f/${FORMSPREE_ID}`

const AU_STATES = ['WA', 'NSW', 'VIC', 'QLD', 'SA', 'TAS', 'NT', 'ACT']

const GRADES_OPTIONS = ['1–2 grades', '3–5 grades', '6–9 grades', '10+ grades']

const REFERRAL_OPTIONS = [
  'Word of mouth / referral',
  'Social media (Instagram, Facebook, X)',
  'Google search',
  'Cricket association or district',
  'Other',
]

const EMPTY_FIELDS = {
  name: '', club: '', email: '', phone: '',
  state: '', grades: '', playhq: '', referral: '', message: '',
}

function Field({ label, id, required, optional, error, children }) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium mb-1.5">
        {label}
        {required && <span className="text-accent ml-0.5">*</span>}
        {optional && <span className="text-pb-faint text-xs font-normal ml-1">(optional)</span>}
      </label>
      {children}
      {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
    </div>
  )
}

function ContactForm() {
  const [fields, setFields] = useState(EMPTY_FIELDS)
  const [errors, setErrors] = useState({})
  const [status, setStatus] = useState('idle') // idle | submitting | success | error

  const set = (key) => (e) => setFields(f => ({ ...f, [key]: e.target.value }))

  function validate() {
    const e = {}
    if (!fields.name.trim())  e.name  = 'Your name is required.'
    if (!fields.club.trim())  e.club  = 'Club name is required.'
    if (!fields.email.trim()) e.email = 'Email address is required.'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(fields.email)) e.email = 'Please enter a valid email.'
    if (!fields.state)        e.state = 'Please select your state.'
    return e
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }
    setErrors({})
    setStatus('submitting')
    try {
      const state = fields.state || '?'
      const res = await fetch(FORMSPREE_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({
          name:     fields.name,
          club:     fields.club,
          email:    fields.email,
          phone:    fields.phone    || '—',
          state:    fields.state,
          grades:   fields.grades   || '—',
          playhq:   fields.playhq   || '—',
          referral: fields.referral || '—',
          message:  fields.message  || '—',
          _subject: `BetterStats enquiry — ${fields.club} (${state})`,
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

  const inputCls = (field) =>
    `w-full bg-pb-surface2/50 border ${errors[field] ? 'border-red-500/60' : 'border-pb-hairline'} rounded-lg px-4 py-2.5 text-sm text-pb-text placeholder:text-pb-faint focus:outline-none focus:border-accent/60 transition-colors`

  const selectCls = (field) =>
    `w-full bg-pb-surface2/50 border ${errors[field] ? 'border-red-500/60' : 'border-pb-hairline'} rounded-lg px-4 py-2.5 text-sm text-pb-text focus:outline-none focus:border-accent/60 transition-colors appearance-none`

  if (status === 'success') {
    return (
      <div className="surface p-8 lg:p-10 text-center">
        <div className="w-14 h-14 rounded-full bg-accent/15 border border-accent/40 flex items-center justify-center mx-auto mb-5 text-2xl">✓</div>
        <h2 className="text-2xl font-bold mb-2">We've got it!</h2>
        <p className="text-pb-dim mb-6">
          Thanks for reaching out. We'll be in touch within 24 hours — usually the same day.
        </p>
        <button
          onClick={() => { setStatus('idle'); setFields(EMPTY_FIELDS) }}
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
        <p className="text-sm text-pb-dim">The more you tell us, the better we can prepare for your demo.</p>
      </div>

      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {/* Honeypot */}
        <input type="text" name="_gotcha" className="hidden" tabIndex="-1" autoComplete="off" />

        {/* Name + Club */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Your name" id="name" required error={errors.name}>
            <input
              id="name" type="text" name="name" autoComplete="name"
              placeholder="Jack Barendse"
              value={fields.name} onChange={set('name')}
              className={inputCls('name')}
            />
          </Field>
          <Field label="Club name" id="club" required error={errors.club}>
            <input
              id="club" type="text" name="club"
              placeholder="Applecross CC"
              value={fields.club} onChange={set('club')}
              className={inputCls('club')}
            />
          </Field>
        </div>

        {/* Email + Phone */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Email address" id="email" required error={errors.email}>
            <input
              id="email" type="email" name="email" autoComplete="email"
              placeholder="jack@applecrosscc.com.au"
              value={fields.email} onChange={set('email')}
              className={inputCls('email')}
            />
          </Field>
          <Field label="Phone" id="phone" optional>
            <input
              id="phone" type="tel" name="phone" autoComplete="tel"
              placeholder="0400 000 000"
              value={fields.phone} onChange={set('phone')}
              className={inputCls('phone')}
            />
          </Field>
        </div>

        {/* State + Number of grades */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="State / territory" id="state" required error={errors.state}>
            <div className="relative">
              <select
                id="state" name="state"
                value={fields.state} onChange={set('state')}
                className={selectCls('state')}
              >
                <option value="" disabled>Select state…</option>
                {AU_STATES.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
              <svg className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-pb-faint" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
            </div>
          </Field>
          <Field label="How many grades do you field?" id="grades" optional>
            <div className="relative">
              <select
                id="grades" name="grades"
                value={fields.grades} onChange={set('grades')}
                className={selectCls('grades')}
              >
                <option value="">Not sure yet…</option>
                {GRADES_OPTIONS.map(g => <option key={g} value={g}>{g}</option>)}
              </select>
              <svg className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-pb-faint" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
            </div>
          </Field>
        </div>

        {/* PlayHQ URL */}
        <Field label="PlayHQ club URL" id="playhq" optional>
          <input
            id="playhq" type="url" name="playhq"
            placeholder="e.g. play.cricket.com.au/club/..."
            value={fields.playhq} onChange={set('playhq')}
            className={inputCls('playhq')}
          />
          <p className="mt-1 text-xs text-pb-faint">Lets us pull your real data for a personalised demo.</p>
        </Field>

        {/* How did you hear */}
        <Field label="How did you hear about BetterStats?" id="referral" optional>
          <div className="relative">
            <select
              id="referral" name="referral"
              value={fields.referral} onChange={set('referral')}
              className={selectCls('referral')}
            >
              <option value="">Select one…</option>
              {REFERRAL_OPTIONS.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
            <svg className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-pb-faint" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
          </div>
        </Field>

        {/* Message */}
        <Field label="Anything else we should know?" id="message" optional>
          <textarea
            id="message" name="message" rows={3}
            placeholder="What are you hoping to get out of BetterStats? Any context about your club's history or current setup is useful."
            value={fields.message} onChange={set('message')}
            className={`${inputCls('message')} resize-none`}
          />
        </Field>

        {status === 'error' && (
          <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3">
            Something went wrong — please try again or email us at{' '}
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
      <div className="max-w-[1100px] mx-auto relative">
        <div className="grid grid-cols-12 gap-10">
          <div className="col-span-12 lg:col-span-4">
            <p className="pill mb-6 inline-flex"><span className="dot" />Reply within 24 hours</p>
            <h1 className="font-display font-bold text-[40px] sm:text-[52px] lg:text-[56px] tracking-tight leading-[0.95] mb-6">
              Tell us about <span className="gradient-text">your club.</span>
            </h1>
            <p className="text-lg text-pb-dim leading-relaxed mb-8">
              Drop your details and we'll come back with a short demo using your club's actual data — your colours, your players, your records.
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

          <div className="col-span-12 lg:col-span-8">
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
