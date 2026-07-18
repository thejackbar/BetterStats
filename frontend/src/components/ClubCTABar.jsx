import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { isMarketingPath } from '../App'
import QuickEnquiryModal from './QuickEnquiryModal'
import SelfServeTrialModal from './admin/SelfServeTrialModal'
import { useSelfServeTrialGate } from '../hooks/useSelfServeTrialGate'

// Sticky bottom "Get your club on BetterCricket" bar. Opens the public
// self-serve trial wizard when self-serve trials are switched on (All Clubs
// -> General Settings -> "Self-serve trials enabled"); otherwise falls back
// to the short enquiry modal (see QuickEnquiryModal), its original behaviour.
//
// Visibility:
// - BetterCricket's own marketing pages (MARKETING_PATHS, minus /contact — those
//   visitors are already converting): shown to every visitor, every time. These
//   are our sales pages, so a persistent ask is exactly what we want.
// - A club's public site (/:clubSlug and its subpages): shown ONLY to visitors
//   who arrived via a paid Meta ad (utm_source=meta or utm_medium=paid_social),
//   remembered for the session — so a club's own members/visitors never see a
//   "switch to us" pitch on the club's own page. Applecross is our demo, so ad
//   traffic there still sees it, which is what we want.
// - Never on /contact (already converting) or /admin*, /login.
// - ?cta=form on any BetterCricket marketing page pops the short form open
//   after a short delay (once per session) — for campaign links that should
//   land on the form rather than on the sticky bar (e.g. a social post CTA).
//   The delay gives a video/post visitor a moment to land on the page before
//   a modal covers it.

const AD_VISITOR_KEY = 'bc:adVisitor'
const DISMISS_KEY = 'bc:ctaDismissed'
const QUERY_KEY = 'bc:utmQuery'
const AUTO_OPEN_KEY = 'bc:ctaAutoOpened'
const AUTO_OPEN_DELAY_MS = 15000

function isPaidVisitor() {
  const params = (() => {
    try { return new URLSearchParams(window.location.search) } catch { return new URLSearchParams() }
  })()
  const source = (params.get('utm_source') || '').toLowerCase()
  const medium = (params.get('utm_medium') || '').toLowerCase()
  const isAdHit = source === 'meta' || medium === 'paid_social'
  try {
    if (isAdHit) {
      sessionStorage.setItem(AD_VISITOR_KEY, '1')
      if (!sessionStorage.getItem(QUERY_KEY)) {
        sessionStorage.setItem(QUERY_KEY, window.location.search || '')
      }
    }
    return sessionStorage.getItem(AD_VISITOR_KEY) === '1'
  } catch {
    return isAdHit
  }
}

export default function ClubCTABar() {
  const { pathname } = useLocation()
  const [show, setShow] = useState(false)
  const [quickModalOpen, setQuickModalOpen] = useState(false)
  const {
    enabled: selfServeEnabled,
    modalOpen: selfServeModalOpen,
    setModalOpen: setSelfServeModalOpen,
    defaultTrialDays,
  } = useSelfServeTrialGate()

  useEffect(() => {
    const onContact = pathname === '/contact'
    const onAdmin = pathname.startsWith('/admin') || pathname === '/login'
    if (onContact || onAdmin) { setShow(false); return }

    let dismissed = false
    try { dismissed = sessionStorage.getItem(DISMISS_KEY) === '1' } catch { /* ignore */ }
    if (dismissed) { setShow(false); return }

    setShow(isMarketingPath(pathname) || isPaidVisitor())
  }, [pathname])

  // Jump straight to the short form, once per session, for links tagged
  // ?cta=form — e.g. a social post CTA that should land on the form open
  // rather than making the visitor find and click the sticky bar.
  useEffect(() => {
    const onContact = pathname === '/contact'
    const onAdmin = pathname.startsWith('/admin') || pathname === '/login'
    if (onContact || onAdmin || !isMarketingPath(pathname)) return

    let params
    try { params = new URLSearchParams(window.location.search) } catch { return }
    if (params.get('cta') !== 'form') return

    try {
      if (sessionStorage.getItem(AUTO_OPEN_KEY) === '1') return
      sessionStorage.setItem(AUTO_OPEN_KEY, '1')
    } catch { /* ignore */ }

    const timer = setTimeout(() => setQuickModalOpen(true), AUTO_OPEN_DELAY_MS)
    return () => clearTimeout(timer)
  }, [pathname])

  if (!show) return null

  function dismiss() {
    try { sessionStorage.setItem(DISMISS_KEY, '1') } catch { /* ignore */ }
    setShow(false)
  }

  return (
    <>
      <div
        role="region"
        aria-label="Get your club on BetterCricket"
        style={{
          position: 'fixed', left: 0, right: 0, bottom: 0, zIndex: 9999,
          background: 'rgba(11,18,32,0.96)', backdropFilter: 'blur(8px)',
          borderTop: '1px solid rgba(52,211,153,0.35)',
          boxShadow: '0 -8px 30px rgba(0,0,0,0.45)',
        }}
      >
        <div
          style={{
            maxWidth: 980, margin: '0 auto', padding: '12px 16px',
            display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap',
            color: '#e6eaf2', fontFamily: 'Inter, system-ui, sans-serif',
          }}
        >
          <span style={{ flex: '1 1 220px', fontSize: 15, lineHeight: 1.4 }}>
            <strong style={{ color: '#fff' }}>Want this for your club?</strong>{' '}
            Turn your club's full cricket history into a site like this.
          </span>
          <button
            onClick={() => { if (selfServeEnabled) setSelfServeModalOpen(true); else setQuickModalOpen(true) }}
            style={{
              background: '#34d399', color: '#0b1220', fontWeight: 700,
              padding: '10px 18px', borderRadius: 10, border: 'none',
              fontSize: 15, whiteSpace: 'nowrap', cursor: 'pointer',
            }}
          >
            Get your club on BetterCricket →
          </button>
          <button
            onClick={dismiss}
            aria-label="Dismiss"
            style={{
              background: 'transparent', border: 'none', color: '#9aa6b8',
              fontSize: 22, lineHeight: 1, cursor: 'pointer', padding: '4px 6px',
            }}
          >
            ×
          </button>
        </div>
      </div>
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
}
