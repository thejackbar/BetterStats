import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import Reveal from '../../components/marketing/Reveal'
import ClubSearchField from '../../components/marketing/ClubSearchField'
import { FORMSPREE_ID, SUPPORT_EMAIL } from '../../data/marketing'
import { api } from '../../lib/api'
import { getVisitorId } from '../../lib/visitor'
import { getMetaEventContext } from '../../lib/metaPixel'
import { usePageMeta } from '../../hooks/usePageMeta'

const FORMSPREE_URL = `https://formspree.io/f/${FORMSPREE_ID}`

const GRADES_OPTIONS = ['1 to 2 grades', '3 to 5 grades', '6 to 9 grades', '10+ grades']

const STORAGE_OPTIONS = [
  'Spreadsheets only',
  'Spreadsheets + a club website',
  'Another stats tool',
  'Word/PDF',
  'Hard Copy',
  'A mix',
  'Not sure',
  'Other',
]

const TIMELINE_OPTIONS = [
  'As soon as possible',
  'Before next season',
  'Just exploring for now',
]

const PLAYHQ_OPTIONS = ['Yes', 'No', 'Only recent data']
const HISTORICAL_OPTIONS = ['Yes', 'No']
const CONTACT_METHOD_OPTIONS = ['Email', 'Phone']
const INTEREST_OPTIONS = [
  'Player statistics',
  'Team statistics',
  'Historical statistics',
  'Automatic data syncing',
  'Automatic yearbooks',
  'Player availability',
  'Team selection',
  'Net management',
  'Social media posts',
  'Club website',
  'Fee tracking',
  'Bulk email to members',
  'Opposition analysis (BetterIQ)',
  'Fantasy Cricket',
  'Other',
]

const EMPTY_FIELDS = {
  // `club` is the club's name as it will be stored. `clubOrgId` is its Cricket
  // Australia organisation guid when it was picked from the club search, and
  // `clubSource` records which of the two paths got us here ('search' |
  // 'manual') so a hand-typed name is never taken for a confirmed one.
  name: '', club: '', clubOrgId: null, clubSource: null, email: '', phone: '',
  role: '', founded: '',
  association: '', grades: '',
  playhq: '', historical: '',
  storage: '', interests: [],
  timeline: '', contactMethod: '',
  clubUrl: '', heard: '', message: '',
}

function Field({ label, id, required, optional, hint, error, children }) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium mb-1.5">
        {label}
        {required && <span className="text-accent ml-0.5">*</span>}
        {optional && <span className="text-pb-faint text-xs font-normal ml-1">(optional)</span>}
      </label>
      {children}
      {hint && !error && <p className="mt-1 text-xs text-pb-faint">{hint}</p>}
      {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
    </div>
  )
}

// Shared styles — solid dark background so typed text is always legible
const BASE_INPUT = [
  'w-full rounded-lg px-4 py-2.5 text-sm',
  'text-white placeholder:text-pb-faint',       // explicit white for typed text
  'bg-[#161b27] border border-pb-hairline',      // solid surface, no opacity
  'focus:outline-none focus:border-accent/60 transition-colors',
].join(' ')

function inputCls(field, errors) {
  return `${BASE_INPUT} ${errors[field] ? 'border-red-500/60' : ''}`
}

function selectCls(field, errors) {
  return `${inputCls(field, errors)} appearance-none`
}

const ChevronIcon = () => (
  <svg className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-pb-faint"
    fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
  </svg>
)

function ContactForm() {
  const [searchParams] = useSearchParams()
  // Seeds the club search rather than filling the club in — see ClubSearchField.
  const prefillClub = searchParams.get('club') || ''
  const [fields, setFields] = useState(EMPTY_FIELDS)
  const [errors, setErrors] = useState({})
  const [status, setStatus] = useState('idle') // idle | submitting | success | error

  const set = (key) => (e) => setFields(f => ({ ...f, [key]: e.target.value }))

  const toggleInterest = (opt) => setFields(f => ({
    ...f,
    interests: f.interests.includes(opt) ? f.interests.filter(x => x !== opt) : [...f.interests, opt],
  }))

  function validate() {
    const e = {}
    if (!fields.name.trim())        e.name        = 'Your name is required.'
    if (!fields.club.trim())        e.club        = 'Please find and select your club, or type its name in yourself.'
    if (!fields.email.trim())       e.email       = 'Email address is required.'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(fields.email)) e.email = 'Please enter a valid email.'
    if (!fields.phone.trim())       e.phone       = 'Phone number is required.'
    if (!fields.role.trim())        e.role        = 'Your role at the club is required.'
    if (!fields.association.trim()) e.association = 'Association or competition is required.'
    if (!fields.grades)             e.grades      = 'Please select the number of grades.'
    if (!fields.playhq)             e.playhq      = 'Please tell us about your PlayHQ data.'
    if (!fields.historical)         e.historical  = 'Please tell us about your historical data.'
    if (!fields.timeline)           e.timeline    = 'Please select a timeline.'
    if (!fields.contactMethod)      e.contactMethod = 'Please choose a preferred contact method.'
    return e
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }
    setErrors({})
    setStatus('submitting')
    // One event_id shared between the browser pixel (below) and the backend's
    // server-side Conversions API call, so Meta dedupes the pair into one Lead.
    const meta = getMetaEventContext()
    // Also store the enquiry in the BetterStats DB so it shows up in the
    // super-admin onboarding list. Best-effort: Formspree (below) is the primary
    // delivery and drives success/error, so a failure here never blocks the form.
    api.submitOnboarding({
      name: fields.name, club: fields.club, email: fields.email, phone: fields.phone,
      // The club's real Cricket Australia id when they picked it from the
      // search, so the enquiry lands on the right club downstream whatever the
      // name was spelled like.
      clubOrgId: fields.clubOrgId, clubSource: fields.clubSource,
      role: fields.role, founded: fields.founded,
      association: fields.association, grades: fields.grades,
      playhq: fields.playhq, historical: fields.historical,
      storage: fields.storage, interests: fields.interests.join(', '),
      timeline: fields.timeline, contactMethod: fields.contactMethod,
      clubUrl: fields.clubUrl, heard: fields.heard, message: fields.message,
      // Links this enquiry to the anonymous browsing journey behind it.
      visitorId: getVisitorId(),
      meta,
    }).catch(() => {})
    try {
      const res = await fetch(FORMSPREE_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({
          name:          fields.name,
          club:          fields.club,
          // Tells whoever reads the email whether the club name is one we
          // matched to a real club record or one typed in by hand.
          clubMatch:     fields.clubSource === 'search'
            ? `Matched (${fields.clubOrgId})`
            : 'Typed in by hand, not in the Cricket Australia list',
          email:         fields.email,
          phone:         fields.phone,
          role:          fields.role,
          founded:       fields.founded || '—',
          association:   fields.association,
          grades:        fields.grades,
          playhq:        fields.playhq,
          historical:    fields.historical || '—',
          storage:       fields.storage,
          interests:     fields.interests.join(', ') || '—',
          timeline:      fields.timeline,
          contactMethod: fields.contactMethod,
          clubUrl:       fields.clubUrl || '—',
          heard:         fields.heard || '—',
          message:       fields.message || '—',
          _subject: `BetterCricket enquiry: ${fields.club} · ${fields.association}`,
        }),
      })
      const data = await res.json()
      if (res.ok && data.ok !== false) {
        setStatus('success')
        // Meta Pixel: a completed request-access form is our key conversion.
        // eventID matches the server-side Conversions API call above so Meta
        // dedupes the two into one Lead instead of double-counting it.
        if (typeof window !== 'undefined' && typeof window.fbq === 'function') {
          window.fbq('track', 'Lead', {
            content_name: 'Request access',
            content_category: 'club_enquiry',
            value: 399,
            currency: 'AUD',
          }, { eventID: meta.eventId })
        }
      } else {
        setStatus('error')
      }
    } catch {
      setStatus('error')
    }
  }

  if (status === 'success') {
    return (
      <div className="surface p-8 lg:p-10 text-center">
        <div className="w-14 h-14 rounded-full bg-accent/15 border border-accent/40 flex items-center justify-center mx-auto mb-5 text-2xl">✓</div>
        <h2 className="text-2xl font-bold mb-2">We've got it!</h2>
        <p className="text-pb-dim mb-6">
          Thanks for reaching out. We'll be in touch within 24 hours, usually the same day.
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
            <input id="name" type="text" name="name" autoComplete="name"
              placeholder="Adam Gilchrist"
              value={fields.name} onChange={set('name')}
              className={inputCls('name', errors)} />
          </Field>
          <Field label="Club name" id="club" required error={errors.club}>
            <ClubSearchField
              inputId="club"
              initialQuery={prefillClub}
              value={{ club: fields.club, clubOrgId: fields.clubOrgId, clubSource: fields.clubSource }}
              onChange={(v) => setFields(f => ({ ...f, ...v }))}
              inputClassName={inputCls('club', errors)}
            />
          </Field>
        </div>

        {/* Email + Phone */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Email address" id="email" required error={errors.email}>
            <input id="email" type="email" name="email" autoComplete="email"
              placeholder="adam@applecrosscc.com"
              value={fields.email} onChange={set('email')}
              className={inputCls('email', errors)} />
          </Field>
          <Field label="Phone number" id="phone" required error={errors.phone}>
            <input id="phone" type="tel" name="phone" autoComplete="tel"
              placeholder="0400 000 000"
              value={fields.phone} onChange={set('phone')}
              className={inputCls('phone', errors)} />
          </Field>
        </div>

        {/* Role + Year founded */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Your role at the club" id="role" required error={errors.role}>
            <input id="role" type="text" name="role"
              placeholder="e.g. President, Secretary, Statistician"
              value={fields.role} onChange={set('role')}
              className={inputCls('role', errors)} />
          </Field>
          <Field label="What year was your club founded?" id="founded" optional>
            <input id="founded" type="text" name="founded" inputMode="numeric"
              placeholder="e.g. 1923"
              value={fields.founded} onChange={set('founded')}
              className={inputCls('founded', errors)} />
          </Field>
        </div>

        {/* Association + Grades */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Association / competition" id="association" required error={errors.association}>
            <input id="association" type="text" name="association"
              placeholder="e.g. WACA Sub-District, SACA"
              value={fields.association} onChange={set('association')}
              className={inputCls('association', errors)} />
          </Field>
          <Field label="How many grades do you field?" id="grades" required error={errors.grades}>
            <div className="relative">
              <select id="grades" name="grades"
                value={fields.grades} onChange={set('grades')}
                className={selectCls('grades', errors)}>
                <option value="" disabled>Select…</option>
                {GRADES_OPTIONS.map(g => <option key={g} value={g}>{g}</option>)}
              </select>
              <ChevronIcon />
            </div>
          </Field>
        </div>

        {/* Data location: PlayHQ + historical */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Is your club's data already in PlayHQ?" id="playhq" required error={errors.playhq}>
            <div className="relative">
              <select id="playhq" name="playhq"
                value={fields.playhq} onChange={set('playhq')}
                className={selectCls('playhq', errors)}>
                <option value="" disabled>Select…</option>
                {PLAYHQ_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
              <ChevronIcon />
            </div>
          </Field>
          <Field label="Do you have historical data for your club?" id="historical" required error={errors.historical}>
            <div className="relative">
              <select id="historical" name="historical"
                value={fields.historical} onChange={set('historical')}
                className={selectCls('historical', errors)}>
                <option value="" disabled>Select…</option>
                {HISTORICAL_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
              <ChevronIcon />
            </div>
          </Field>
        </div>

        {/* Current stats storage */}
        <Field label="How do you currently store your historical data?" id="storage" optional>
          <div className="relative">
            <select id="storage" name="storage"
              value={fields.storage} onChange={set('storage')}
              className={selectCls('storage', errors)}>
              <option value="" disabled>Select…</option>
              {STORAGE_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <ChevronIcon />
          </div>
        </Field>

        {/* What they're most interested in */}
        <Field label="What are you most interested in?" id="interests" optional
          hint="Tick anything that's a priority, it helps us tailor your demo.">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {INTEREST_OPTIONS.map(opt => {
              const on = fields.interests.includes(opt)
              return (
                <button key={opt} type="button" onClick={() => toggleInterest(opt)}
                  aria-pressed={on}
                  className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-left border transition-colors ${
                    on ? 'border-accent/60 bg-accent/[0.08] text-white' : 'border-pb-hairline bg-[#161b27] text-pb-dim hover:border-accent/30'
                  }`}>
                  <span className={`w-4 h-4 rounded flex items-center justify-center text-[10px] flex-shrink-0 border ${on ? 'bg-accent text-navy-950 border-accent' : 'border-pb-hairline'}`}>{on ? '✓' : ''}</span>
                  {opt}
                </button>
              )
            })}
          </div>
        </Field>

        {/* Timeline + preferred contact method */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="When are you hoping to get started?" id="timeline" required error={errors.timeline}>
            <div className="relative">
              <select id="timeline" name="timeline"
                value={fields.timeline} onChange={set('timeline')}
                className={selectCls('timeline', errors)}>
                <option value="" disabled>Select…</option>
                {TIMELINE_OPTIONS.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
              <ChevronIcon />
            </div>
          </Field>
          <Field label="Preferred contact method" id="contactMethod" required error={errors.contactMethod}>
            <div className="relative">
              <select id="contactMethod" name="contactMethod"
                value={fields.contactMethod} onChange={set('contactMethod')}
                className={selectCls('contactMethod', errors)}>
                <option value="" disabled>Select…</option>
                {CONTACT_METHOD_OPTIONS.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
              <ChevronIcon />
            </div>
          </Field>
        </div>

        {/* Club URL + how they heard — optional */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Your club's website or association" id="clubUrl" optional
            hint="Helps us build a demo with your real data.">
            <input id="clubUrl" type="url" name="clubUrl"
              placeholder="e.g. yourclubcc.com.au"
              value={fields.clubUrl} onChange={set('clubUrl')}
              className={inputCls('clubUrl', errors)} />
          </Field>
          <Field label="How did you hear about us?" id="heard" optional>
            <input id="heard" type="text" name="heard"
              placeholder="e.g. a mate's club, Facebook, search"
              value={fields.heard} onChange={set('heard')}
              className={inputCls('heard', errors)} />
          </Field>
        </div>

        {/* Message — optional */}
        <Field label="Anything else we should know?" id="message" optional>
          <textarea id="message" name="message" rows={3}
            placeholder="Any extra context about your club's history, current setup, or what you're hoping to get out of BetterCricket."
            value={fields.message} onChange={set('message')}
            className={`${inputCls('message', errors)} resize-none`} />
        </Field>

        {status === 'error' && (
          <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3">
            Something went wrong. Please try again, or email us at{' '}
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
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
          <div className="col-span-1 lg:col-span-4">
            <p className="pill mb-6 inline-flex"><span className="dot" />Reply within 24 hours</p>
            <h1 className="font-display font-bold text-[40px] sm:text-[52px] lg:text-[56px] tracking-tight leading-[0.95] mb-6">
              Tell us about <span className="gradient-text">your club.</span>
            </h1>
            <p className="text-lg text-pb-dim leading-relaxed mb-8">
              Drop your details and we'll come back with a short demo built on your club's own data, in your colours and with your real players in it.
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

          <div className="col-span-1 lg:col-span-8">
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
    title: 'Contact: Request Access for Your Cricket Club | BetterCricket',
    description: 'Request access for your Australian cricket club, ask a question, or email the BetterCricket team directly at support@bettersports.com.au.',
    image: 'https://betterat.cricket/og-cover.png',
    url: 'https://betterat.cricket/contact',
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
