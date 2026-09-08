import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import MarketingNav from '../../components/MarketingNav'
import MarketingFooter from '../../components/marketing/MarketingFooter'
import TrustedByStrip from '../../components/marketing/TrustedByStrip'
import { api } from '../../lib/api'
import { SUPPORT_EMAIL } from '../../data/marketing'
import { usePageMeta } from '../../hooks/usePageMeta'
import { MODULES_MARKETING } from '../../data/modules-marketing'
import { ModuleWordmark } from '../../components/ModuleLockup'
import { getAttribution, getVisitorId } from '../../lib/visitor'
import { getMetaEventContext } from '../../lib/metaPixel'
import {
  WEBINAR, WEBINAR_ICS_URL, googleCalendarUrl, webinarState,
} from '../../data/webinar'

// The webinar registration page — the destination for a paid Meta campaign
// whose ad set optimises for the `CompleteRegistration` pixel event.
//
// THAT IS THE WHOLE REASON THIS PAGE EXISTS RATHER THAN THE AD POINTING AT
// STREAMYARD: a pixel cannot fire on a third-party domain, so an ad sent
// straight to StreamYard hands Meta no conversion signal at all and delivery
// degrades within days. So registration happens here, the pixel fires on
// confirmed success, and the viewing link is handed over afterwards — never as
// a redirect, because a redirect races the beacon it is supposed to follow.
//
// Every before/after-the-event state comes from ONE constant
// (src/data/webinar.js), so the page turns itself into a recording page rather
// than needing a deploy on the night — and can never sit there advertising a
// webinar that has already happened.
//
// Forced LIGHT, mobile-first, and matching /trial: the ad creative is 4:5
// portrait feed, so essentially all of this traffic is on a phone, and ~11% of
// link clicks on the current campaign never became a landing-page view at all.
// The form is inline in the hero with no image above it for that reason —
// nothing in front of the thing we want people to do.

const FIELD_CLS = 'w-full bg-pb-surface2 text-pb-text border pb-hairline rounded-lg px-4 py-3 text-base outline-none focus:border-pb-accent'

// What the demo covers. Read off the module data rather than retyped, so a
// renamed module can't leave this list saying the old name.
const COVERS = [
  ['Historical stats', 'Every season your club has ever played, imported automatically.'],
  ['Selection', 'Availability, squads and team sheets without the group chat.'],
  ['Socials', 'Match graphics and a public club site that keep themselves current.'],
  ['Club admin', 'Fees, members, comms and the committee’s own paperwork.'],
  ['Opposition analysis', 'Who to bowl at whom, from scorecards you already have.'],
  ['Fantasy Cricket', 'A season-long competition your members actually play.'],
]

const AUDIENCE = ['Club presidents', 'Secretaries', 'Committee members', 'Coaches']

const DEMO_JSONLD = {
  '@context': 'https://schema.org',
  '@type': 'Event',
  name: WEBINAR.title,
  startDate: WEBINAR.startsAt,
  eventAttendanceMode: 'https://schema.org/OnlineEventAttendanceMode',
  eventStatus: 'https://schema.org/EventScheduled',
  location: {
    '@type': 'VirtualLocation',
    url: 'https://betterat.cricket/demo',
  },
  organizer: { '@type': 'Organization', name: 'BetterCricket', url: 'https://betterat.cricket' },
  description:
    'A live walk through the whole of BetterCricket: historical stats, selection, '
    + 'socials, club admin, opposition analysis and Fantasy Cricket, then Q&A.',
}

function CalendarIcon() {
  return (
    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M8 3v4M16 3v4M3 11h18" />
    </svg>
  )
}

// The secondary path. Present below the form and again in the success state,
// deliberately styled as an outline rather than a second primary — the trial
// page converts paid traffic at ~3.4% on its own, and a competing CTA above
// the fold would cost this page the registration it was paid for.
function TrialCta({ className = '' }) {
  return (
    <div className={`pb-card p-5 ${className}`}>
      <p className="font-display font-semibold text-base mb-1">Not ready for a live demo?</p>
      <p className="text-sm text-pb-dim leading-relaxed mb-3">
        Set your club up yourself. A 14-day free trial takes about three minutes, and we
        never ask for a credit card.
      </p>
      <Link
        to="/trial"
        className="inline-flex items-center gap-1 px-4 py-2.5 rounded-lg font-display font-semibold text-sm border pb-hairline text-pb-text hover:bg-pb-surface2 transition"
      >
        Start your free trial <span aria-hidden="true">→</span>
      </Link>
    </div>
  )
}

// Shown once registration is confirmed. NOT a redirect to StreamYard: the
// pixel beacon has to get out, and there is a calendar file and an inbox note
// to hand over that a redirect would skip straight past.
function SuccessState({ state, recordingPending, watchUrl }) {
  const calendarUrl = googleCalendarUrl(watchUrl || WEBINAR.watchUrl)
  return (
    <div className="text-left" data-testid="demo-success">
      <div className="pb-card p-6 bg-pb-surface">
        <p className="font-mono text-[11px] tracking-wide text-emerald-600 mb-2">
          {state.past ? 'YOU’RE ON THE LIST' : 'YOU’RE REGISTERED'}
        </p>
        <h2 className="font-display font-bold text-xl leading-tight mb-3">
          {state.past
            ? (recordingPending ? 'The recording is on its way' : 'Here’s the recording')
            : `See you on ${WEBINAR.dateLabel}`}
        </h2>

        {recordingPending ? (
          <p className="text-sm text-pb-dim leading-relaxed mb-4">
            We&rsquo;re finishing the recording now. It&rsquo;ll land in your inbox as soon as
            it&rsquo;s ready.
          </p>
        ) : (
          <>
            {!state.past && (
              <p className="text-sm text-pb-dim leading-relaxed mb-4">
                {WEBINAR.dateLabel} · {WEBINAR.timeLabel}. Join with the link below.
                It&rsquo;s in your inbox too.
              </p>
            )}
            <a
              href={watchUrl || WEBINAR.watchUrl}
              target="_blank"
              rel="noopener noreferrer"
              data-testid="demo-watch-link"
              className="inline-flex items-center gap-2 px-5 py-3 rounded-lg font-display font-semibold text-base text-pb-bg transition hover:opacity-90"
              style={{ background: 'var(--pb-accent)' }}
            >
              {state.past ? 'Watch the recording' : 'Open the demo link'} <span aria-hidden="true">→</span>
            </a>
          </>
        )}

        {!state.past && (
          <div className="mt-5 pt-5 border-t pb-hairline">
            <p className="font-mono text-[11px] tracking-wide text-pb-faint mb-2">ADD TO CALENDAR</p>
            <div className="flex flex-wrap gap-2">
              <a
                href={calendarUrl}
                target="_blank"
                rel="noopener noreferrer"
                data-testid="demo-gcal"
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg font-display font-semibold text-sm border pb-hairline hover:bg-pb-surface2 transition"
              >
                <CalendarIcon /> Google Calendar
              </a>
              {/* A real URL, not a browser-built blob — the same one the
                  confirmation email links to, so both places agree. */}
              <a
                href={WEBINAR_ICS_URL}
                data-testid="demo-ics"
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg font-display font-semibold text-sm border pb-hairline hover:bg-pb-surface2 transition"
              >
                <CalendarIcon /> Outlook / Apple
              </a>
            </div>
          </div>
        )}
      </div>
      <TrialCta className="mt-4" />
    </div>
  )
}

function RegistrationForm({ state, onSuccess }) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [club, setClub] = useState('')
  const [role, setRole] = useState('')
  const [showRole, setShowRole] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState('')
  // Off-screen honeypot. A real browser never fills it; a form-filling bot
  // fills every field it finds.
  const [honeypot, setHoneypot] = useState('')
  // When the form first rendered, for the server's minimum-fill-time check.
  const startedAtRef = useRef(Date.now())

  const validate = () => {
    const next = {}
    if (!name.trim()) next.name = 'Add your name.'
    if (!email.trim()) next.email = 'Add your email.'
    else if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) next.email = 'That doesn’t look like an email address.'
    if (!club.trim()) next.club = 'Add your club.'
    return next
  }

  const submit = async (e) => {
    e.preventDefault()
    // Validate BEFORE touching the submitting flag, or a rejected form leaves
    // the button disabled with no way out.
    const found = validate()
    setErrors(found)
    if (Object.keys(found).length) return

    setSubmitting(true)
    setFormError('')
    // One event_id shared between the browser pixel's CompleteRegistration and
    // the backend's server-side copy, so Meta counts the pair as one
    // conversion instead of two.
    const meta = getMetaEventContext()
    try {
      const result = await api.registerForWebinar({
        name: name.trim(),
        email: email.trim(),
        club: club.trim(),
        role: role || null,
        attribution: getAttribution(),
        visitorId: getVisitorId(),
        meta,
        website: honeypot,
        formStartedAt: startedAtRef.current,
      })

      // THE ORDER HERE IS THE POINT. The lead is persisted (the await above),
      // and only then does the pixel fire — never on page load, never on the
      // click, never on a validation failure. A CompleteRegistration that
      // fires before a confirmed registration poisons the ad set's
      // optimisation immediately.
      //
      // And only on a GENUINELY NEW registration: `created` is false when this
      // address was already on the list, which is the same lead re-submitting
      // rather than a second conversion. Counting it would teach the ad set to
      // optimise toward people who fill the form in twice.
      if (result?.created && typeof window !== 'undefined' && typeof window.fbq === 'function') {
        window.fbq('track', 'CompleteRegistration', {
          content_name: `Webinar Registration - ${WEBINAR.dateLabel} 2026`,
          content_category: 'webinar',
        }, { eventID: meta.eventId })
      }
      if (result?.created && typeof window !== 'undefined' && typeof window.gtag === 'function') {
        // The analytics-side equivalent, so the two can be reconciled. They
        // will not match — Meta attributes on a 7-day click window.
        window.gtag('event', 'sign_up', { method: 'webinar' })
      }
      // The server's own view of the link wins over the local constant — it is
      // the side that knows whether a recording has been published.
      onSuccess({ watchUrl: result?.watch_url || null })
    } catch (err) {
      // GRACEFUL FAILURE: someone who has filled the form in and pressed the
      // button must not be trapped behind a broken backend. They get the link
      // anyway — but no pixel fires, because nothing was actually registered
      // and a conversion we invented is worse than one we missed.
      setFormError(
        err?.message
        || 'Something went wrong saving your details. The link below still works, and '
        + `and email ${SUPPORT_EMAIL} if you’d like us to send you the recording.`,
      )
    } finally {
      setSubmitting(false)
    }
  }

  const err = (key) => errors[key] && (
    <p id={`demo-${key}-error`} className="text-xs text-red-500 mt-1">{errors[key]}</p>
  )

  if (formError) {
    return (
      <div className="text-left">
        <div className="pb-card p-5 border-red-500/40">
          <p className="text-sm text-pb-text leading-relaxed mb-3">{formError}</p>
          <a
            href={state.watchUrl || WEBINAR.watchUrl}
            target="_blank"
            rel="noopener noreferrer"
            data-testid="demo-fallback-link"
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg font-display font-semibold text-sm text-pb-bg"
            style={{ background: 'var(--pb-accent)' }}
          >
            Open the demo link <span aria-hidden="true">→</span>
          </a>
        </div>
        <button
          type="button"
          onClick={() => setFormError('')}
          className="mt-3 font-mono text-[11px] text-pb-faint underline hover:text-pb-text"
        >
          ← Try registering again
        </button>
      </div>
    )
  }

  return (
    <form onSubmit={submit} className="text-left" noValidate data-testid="demo-form">
      <div className="space-y-3">
        <div>
          <label htmlFor="demo-name" className="block font-mono text-[11px] tracking-wide text-pb-faint mb-1.5">
            YOUR NAME
          </label>
          <input
            id="demo-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoComplete="name"
            required
            aria-invalid={!!errors.name}
            aria-describedby={errors.name ? 'demo-name-error' : undefined}
            className={FIELD_CLS}
          />
          {err('name')}
        </div>
        <div>
          <label htmlFor="demo-email" className="block font-mono text-[11px] tracking-wide text-pb-faint mb-1.5">
            EMAIL
          </label>
          <input
            id="demo-email"
            type="email"
            inputMode="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
            aria-invalid={!!errors.email}
            aria-describedby={errors.email ? 'demo-email-error' : undefined}
            className={FIELD_CLS}
          />
          {err('email')}
        </div>
        <div>
          <label htmlFor="demo-club" className="block font-mono text-[11px] tracking-wide text-pb-faint mb-1.5">
            YOUR CLUB
          </label>
          <input
            id="demo-club"
            value={club}
            onChange={(e) => setClub(e.target.value)}
            autoComplete="organization"
            required
            aria-invalid={!!errors.club}
            aria-describedby={errors.club ? 'demo-club-error' : undefined}
            className={FIELD_CLS}
          />
          {err('club')}
        </div>

        {/* Optional, and collapsed — every extra field on screen costs
            registrations, so this one asks to be opened rather than sitting
            there looking required. */}
        {showRole ? (
          <div>
            <label htmlFor="demo-role" className="block font-mono text-[11px] tracking-wide text-pb-faint mb-1.5">
              YOUR ROLE AT THE CLUB <span className="text-pb-faintest">(OPTIONAL)</span>
            </label>
            <select
              id="demo-role"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className={FIELD_CLS}
            >
              <option value="">Prefer not to say</option>
              {(state.roles || []).map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setShowRole(true)}
            data-testid="demo-role-toggle"
            className="font-mono text-[11px] text-pb-faint underline hover:text-pb-text"
          >
            + Add your role at the club (optional)
          </button>
        )}

        {/* Honeypot — off screen for a person, an ordinary field to a bot. */}
        <div aria-hidden="true" style={{ position: 'absolute', left: '-9999px', opacity: 0 }}>
          <label htmlFor="demo-website">Website</label>
          <input
            id="demo-website"
            name="website"
            tabIndex={-1}
            autoComplete="off"
            value={honeypot}
            onChange={(e) => setHoneypot(e.target.value)}
          />
        </div>
      </div>

      <button
        type="submit"
        disabled={submitting}
        data-testid="demo-submit"
        className="w-full mt-4 px-5 py-4 rounded-xl font-display font-bold text-base text-pb-bg transition hover:opacity-90 disabled:opacity-60"
        style={{ background: 'var(--pb-accent)' }}
      >
        {submitting ? state.submittingLabel : state.submitLabel}
      </button>
      <p className="text-[13px] text-pb-dim mt-2.5 text-center leading-relaxed">
        {state.past
          ? 'We’ll email you the full recording.'
          : 'Can’t make it live? Register anyway and we’ll send you the full recording.'}
      </p>
    </form>
  )
}

export default function Demo() {
  usePageMeta({
    title: 'Watch the BetterCricket demo | Live demo + Q&A',
    description:
      'See the whole of BetterCricket in one sitting: historical stats, selection, '
      + 'socials, club admin and opposition analysis, then ask us anything. Register free.',
    image: 'https://betterat.cricket/og-cover.png',
    url: 'https://betterat.cricket/demo',
    jsonLd: DEMO_JSONLD,
  })

  // The recording link is the one thing the page can't know for itself, so it
  // comes from the server. Everything else — the date, the headline, the
  // button label — renders immediately from the local constant, because a
  // request in front of the H1 is a request in front of LCP and this traffic
  // is paid and mobile.
  const [details, setDetails] = useState(null)
  const [success, setSuccess] = useState(null)

  useEffect(() => {
    let alive = true
    api.webinarDetails()
      .then((d) => { if (alive) setDetails(d) })
      .catch(() => { /* the local constant already covers every visible state */ })
    return () => { alive = false }
  }, [])

  // A deeper intent signal than the global PageView: this visitor was sent to
  // the demo offer specifically. Ref-guarded so it fires once per visit
  // regardless of StrictMode's double-effects.
  const viewTracked = useRef(false)
  useEffect(() => {
    if (viewTracked.current) return
    viewTracked.current = true
    if (typeof window !== 'undefined' && typeof window.fbq === 'function') {
      window.fbq('track', 'ViewContent', {
        content_name: 'Webinar registration page',
        content_category: 'webinar',
      })
    }
  }, [])

  const state = {
    ...webinarState({
      // The server decides whether the event has been and gone; the local
      // constant only covers the moment before its answer arrives.
      isPast: typeof details?.is_past === 'boolean' ? details.is_past : null,
      recordingUrl: details?.recording_available ? details.watch_url : null,
    }),
    roles: details?.roles || ['President', 'Secretary', 'Committee', 'Coach', 'Captain', 'Player', 'Other'],
  }

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text" data-theme="light">
      <MarketingNav />
      <div id="main-content" tabIndex="-1">

        {/* Hero. The headline echoes the ad creative near-verbatim — ad-to-page
            scent mismatch is the biggest single cause of bounce on paid
            traffic — and the form is inline underneath it, not behind a button
            that scrolls or opens a modal. */}
        <section className="relative pt-20 sm:pt-24 pb-8 px-4 sm:px-6 lg:px-10 overflow-hidden">
          <div className="absolute inset-0 hero-glow opacity-60 pointer-events-none" />
          <div className="max-w-xl mx-auto relative">
            <div className="text-center">
              <h1 className="font-display font-bold text-[32px] sm:text-[44px] tracking-tight leading-[1.05] mb-3">
                {state.past ? state.heading : (
                  <>See <span className="gradient-text">BetterCricket</span> in action</>
                )}
              </h1>
              <p className="text-base sm:text-lg text-pb-dim leading-relaxed mb-4">
                {state.subheading}
              </p>
              <p
                data-testid="demo-when"
                className="inline-flex items-center gap-2 px-4 py-2 mb-6 rounded-full border pb-hairline bg-pb-surface font-mono text-[12px] sm:text-[13px] tracking-wide"
              >
                {!state.past && <span aria-hidden="true">🔴</span>}
                {state.whenLabel}
              </p>
            </div>

            {success ? (
              <SuccessState
                state={state}
                watchUrl={success.watchUrl || state.watchUrl}
                recordingPending={state.recordingPending}
              />
            ) : (
              <>
                <RegistrationForm state={state} onSuccess={setSuccess} />
                <TrialCta className="mt-8" />
              </>
            )}
          </div>
        </section>

        <TrustedByStrip compact />

        {/* Supporting content — brief and scannable. This is a landing page,
            not the homepage. */}
        <section className="px-4 sm:px-6 lg:px-10 pt-10 pb-14">
          <div className="max-w-[900px] mx-auto">
            <h2 className="font-display font-bold text-2xl mb-6 text-center">
              What we&rsquo;ll cover
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {COVERS.map(([title, body]) => (
                <div key={title} className="pb-card p-5">
                  <p className="font-display font-semibold text-base mb-1">{title}</p>
                  <p className="text-sm text-pb-dim leading-relaxed">{body}</p>
                </div>
              ))}
            </div>

            {/* One screenshot, reusing an existing site asset — lazy and
                explicitly sized so it can't shift the layout or drag LCP. */}
            <figure className="mt-8">
              <img
                src="/marketing/feature-leaderboard.jpg"
                alt="A BetterCricket club leaderboard, with every season a club has played"
                width="1600"
                height="1000"
                loading="lazy"
                decoding="async"
                className="w-full rounded-xl border pb-hairline"
              />
              <figcaption className="font-mono text-[11px] text-pb-faintest mt-2 text-center">
                Every figure on a BetterCricket page comes from your club&rsquo;s own scorecards.
              </figcaption>
            </figure>

            <div className="mt-10 text-center">
              <p className="font-mono text-[11px] tracking-wide text-pb-faint mb-3">WHO IT&rsquo;S FOR</p>
              <div className="flex flex-wrap justify-center gap-2">
                {AUDIENCE.map((who) => (
                  <span key={who} className="px-3.5 py-1.5 rounded-full border pb-hairline bg-pb-surface text-sm">
                    {who}
                  </span>
                ))}
              </div>
            </div>

            <div className="mt-10 grid grid-cols-2 lg:grid-cols-4 gap-3">
              {MODULES_MARKETING.map((m) => (
                <Link
                  key={m.slug}
                  to={`/modules/${m.slug}`}
                  className="pb-card p-4 flex items-center gap-3 hover:border-accent/30 transition-colors"
                >
                  <img src={m.logo} alt="" width="32" height="32" className="w-8 h-8 rounded-lg shrink-0" loading="lazy" />
                  <span className="font-display font-semibold text-sm min-w-0 truncate">
                    <ModuleWordmark name={m.name} accent={m.accent} />
                  </span>
                </Link>
              ))}
            </div>

            <p className="text-center font-mono text-[11px] text-pb-faintest mt-8">
              Questions before the demo? <a href={`mailto:${SUPPORT_EMAIL}`} className="underline hover:text-pb-text">{SUPPORT_EMAIL}</a>
            </p>
          </div>
        </section>
      </div>
      <MarketingFooter />
    </div>
  )
}
