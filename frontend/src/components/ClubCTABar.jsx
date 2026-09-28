import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { isMarketingPath, rendersOwnMarketingNav } from '../lib/marketingPaths'
import { publicClubSlug } from '../lib/clubPath'
import { getLandingParams } from '../lib/visitor'
import { api } from '../lib/api'
import { useAuth } from '../contexts/AuthContext'
import QuickEnquiryModal from './QuickEnquiryModal'
import SelfServeTrialModal from './admin/SelfServeTrialModal'
import { useSelfServeTrialGate } from '../hooks/useSelfServeTrialGate'

// The prospect call to action. Opens the public self-serve trial wizard when
// self-serve trials are switched on (All Clubs -> General Settings ->
// "Self-serve trials enabled"), whose success is the one place the
// CompleteRegistration pixel event fires; otherwise the short enquiry form.
//
// Visibility:
// - BetterCricket's own marketing pages (MARKETING_PATHS, minus /contact):
//   a generic bar for every visitor, until they dismiss it for the session.
// - A club's public site (/:clubSlug and its subpages): a bar that names the
//   club being viewed, shown ONLY to prospects — anyone this session who came
//   from a paid Meta click or who passed through /trial — and never to anyone
//   signed in. A club's own members reading their paying club's site must
//   never be sold to. Dismissing it only minimises it to a "Start free" pill,
//   because a visitor searching their way to a club is the funnel's
//   highest-intent moment and the ask should stay one tap away.
// - Never on /trial or /demo (conversion pages with their own call to
//   action), /contact, /admin*, /login or /betterscout*.
// - ?cta=form on any BetterCricket marketing page pops the short form open
//   after a short delay (once per session), for campaign links that should
//   land on the form.
//
// THE CLUB ON SCREEN IS ALREADY ON BETTERCRICKET. /trial only sends a search
// result to its dashboard when the club is already registered, and the
// registration backend refuses that club (409, "talk to your admin"). So the
// bar never offers to set up the club being viewed: it sells the visitor's
// OWN club, and the wizard opens on a blank search.

const AD_VISITOR_KEY = 'bc:adVisitor'
const VIA_TRIAL_KEY = 'bc:viaTrial'
const DISMISS_KEY = 'bc:ctaDismissed'
const CLUB_MIN_KEY = 'bc:clubCtaMinimised'
const AUTO_OPEN_KEY = 'bc:ctaAutoOpened'
const AUTO_OPEN_DELAY_MS = 15000
const PAID_SOURCES = new Set(['meta', 'facebook', 'fb', 'instagram', 'ig'])

function readSession(key) {
  try { return sessionStorage.getItem(key) } catch { return null }
}
function writeSession(key, value) {
  try { sessionStorage.setItem(key, value) } catch { /* storage blocked */ }
}

// Read off the session's landing params rather than the current URL: by the
// time a visitor reaches a club's dashboard the query string is long gone
// from the address bar.
function isProspectVisitor() {
  const landing = getLandingParams() || {}
  const source = (landing.utm_source || '').toLowerCase()
  const medium = (landing.utm_medium || '').toLowerCase()
  if (PAID_SOURCES.has(source) || medium === 'paid_social' || landing.fbclid || landing.igshid) {
    writeSession(AD_VISITOR_KEY, '1')
  }
  return readSession(AD_VISITOR_KEY) === '1' || readSession(VIA_TRIAL_KEY) === '1'
}

const BAR_STYLE = {
  position: 'fixed', left: 0, right: 0, bottom: 0, zIndex: 9999,
  background: 'rgba(11,18,32,0.97)', backdropFilter: 'blur(8px)',
  boxShadow: '0 -10px 34px rgba(0,0,0,0.5)',
}
const ROW_STYLE = {
  margin: '0 auto', padding: '12px 16px',
  display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap',
  color: '#e6eaf2', fontFamily: 'Inter, system-ui, sans-serif',
}
const PRIMARY_STYLE = {
  background: '#34d399', color: '#0b1220', fontWeight: 700,
  padding: '11px 20px', borderRadius: 10, border: 'none',
  fontSize: 15, whiteSpace: 'nowrap', cursor: 'pointer',
}
const CLOSE_STYLE = {
  background: 'transparent', border: 'none', color: '#9aa6b8',
  fontSize: 22, lineHeight: 1, cursor: 'pointer', padding: '4px 6px',
}

export default function ClubCTABar() {
  const { pathname } = useLocation()
  const { user } = useAuth()
  const clubSlug = publicClubSlug(pathname)
  const [show, setShow] = useState(false)
  const [club, setClub] = useState(null)
  const [minimised, setMinimised] = useState(() => readSession(CLUB_MIN_KEY) === '1')
  const [quickModalOpen, setQuickModalOpen] = useState(false)
  const {
    enabled: selfServeEnabled,
    modalOpen: selfServeModalOpen,
    setModalOpen: setSelfServeModalOpen,
    defaultTrialDays,
  } = useSelfServeTrialGate()

  useEffect(() => {
    // Arriving at /trial marks the session as a prospect, so the club
    // dashboard they search their way to carries the prompt.
    if (rendersOwnMarketingNav(pathname)) {
      if (pathname === '/trial') writeSession(VIA_TRIAL_KEY, '1')
      setShow(false)
      return
    }
    const onContact = pathname === '/contact'
    const onAdmin = pathname.startsWith('/admin') || pathname === '/login' || pathname.startsWith('/betterscout')
    if (onContact || onAdmin) { setShow(false); return }

    if (clubSlug) {
      setShow(!user && isProspectVisitor())
      return
    }

    if (readSession(DISMISS_KEY) === '1') { setShow(false); return }
    setShow(isMarketingPath(pathname))
  }, [pathname, clubSlug, user])

  // The club's name for the club-page copy. Keyed on slug, so moving between
  // one club's pages doesn't refetch; a club that fails to load gets the
  // generic wording.
  useEffect(() => {
    if (!show || !clubSlug) { setClub(null); return undefined }
    let cancelled = false
    api.getClubBySlug(clubSlug)
      .then((c) => { if (!cancelled) setClub(c || null) })
      .catch(() => { if (!cancelled) setClub(null) })
    return () => { cancelled = true }
  }, [show, clubSlug])

  useEffect(() => {
    const onContact = pathname === '/contact'
    const onAdmin = pathname.startsWith('/admin') || pathname === '/login' || pathname.startsWith('/betterscout')
    if (onContact || onAdmin || !isMarketingPath(pathname)) return undefined

    let params
    try { params = new URLSearchParams(window.location.search) } catch { return undefined }
    if (params.get('cta') !== 'form') return undefined
    if (readSession(AUTO_OPEN_KEY) === '1') return undefined
    writeSession(AUTO_OPEN_KEY, '1')

    const timer = setTimeout(() => setQuickModalOpen(true), AUTO_OPEN_DELAY_MS)
    return () => clearTimeout(timer)
  }, [pathname])

  // Rendered whatever the bar is doing, so minimising or navigating while the
  // wizard is open never unmounts it mid-registration.
  const modals = (
    <>
      {quickModalOpen && <QuickEnquiryModal onClose={() => setQuickModalOpen(false)} />}
      {selfServeModalOpen && (
        <SelfServeTrialModal
          publicMode
          defaultTrialDays={defaultTrialDays}
          onClose={() => setSelfServeModalOpen(false)}
        />
      )}
    </>
  )

  if (!show) return modals

  const start = () => {
    if (selfServeEnabled) setSelfServeModalOpen(true)
    else setQuickModalOpen(true)
  }

  if (clubSlug) {
    if (minimised) {
      return (
        <>
          <button
            type="button"
            data-testid="club-cta-pill"
            onClick={start}
            style={{
              ...PRIMARY_STYLE,
              position: 'fixed', right: 16, bottom: 16, zIndex: 9999,
              borderRadius: 999, padding: '12px 18px',
              fontFamily: 'Inter, system-ui, sans-serif',
              boxShadow: '0 8px 24px rgba(0,0,0,0.45)',
            }}
          >
            Start free →
          </button>
          {modals}
        </>
      )
    }
    const clubName = club?.name || club?.short_name || null
    const days = defaultTrialDays || 14
    return (
      <>
        <div
          role="region"
          aria-label="Get your club on BetterCricket"
          data-testid="club-cta"
          style={{ ...BAR_STYLE, borderTop: '2px solid #34d399' }}
        >
          <div style={{ ...ROW_STYLE, maxWidth: 1080 }}>
            <span style={{ flex: '1 1 260px', fontSize: 15, lineHeight: 1.45 }}>
              <strong style={{ color: '#fff' }} data-testid="club-cta-headline">
                {clubName
                  ? `This is ${clubName}’s real history on BetterCricket.`
                  : 'This is a real club’s history on BetterCricket.'}
              </strong>{' '}
              Get your own club live for your committee. Free {days}-day trial, no card.
            </span>
            <button type="button" data-testid="club-cta-start" onClick={start} style={PRIMARY_STYLE}>
              Start free →
            </button>
            <button
              type="button"
              aria-label="Minimise"
              onClick={() => { writeSession(CLUB_MIN_KEY, '1'); setMinimised(true) }}
              style={CLOSE_STYLE}
            >
              ×
            </button>
          </div>
        </div>
        {modals}
      </>
    )
  }

  const dismiss = () => {
    writeSession(DISMISS_KEY, '1')
    setShow(false)
  }

  return (
    <>
      <div
        role="region"
        aria-label="Get your club on BetterCricket"
        style={{ ...BAR_STYLE, borderTop: '1px solid rgba(52,211,153,0.35)' }}
      >
        <div style={{ ...ROW_STYLE, maxWidth: 980 }}>
          <span style={{ flex: '1 1 220px', fontSize: 15, lineHeight: 1.4 }}>
            <strong style={{ color: '#fff' }}>Want this for your club?</strong>{' '}
            Turn your club's full cricket history into a site like this.
          </span>
          <button type="button" onClick={start} style={PRIMARY_STYLE}>
            Get your club on BetterCricket →
          </button>
          <button type="button" onClick={dismiss} aria-label="Dismiss" style={CLOSE_STYLE}>
            ×
          </button>
        </div>
      </div>
      {modals}
    </>
  )
}
