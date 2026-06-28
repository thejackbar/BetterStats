import { useEffect, useState } from 'react'
import { useLocation, Link } from 'react-router-dom'

// Bottom-of-screen "Want this for your club?" banner shown to visitors who
// arrived through a tagged link. It bridges campaign / share traffic landing on
// a club's public site (e.g. /applecross) to the request-access form, without
// ever showing to a club's own members browsing organically.
//
// Trigger: ANY UTM parameter on the landing URL. Marketing, ad, email and
// social links all carry at least one utm_* tag, so this catches every tagged
// visit — not only paid Meta traffic. Once seen in a session it sticks (stored
// in sessionStorage) so the banner follows the visitor as they browse on.

const UTM_KEYS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'utm_id']
const VISITOR_KEY = 'bc:utmVisitor'
const QUERY_KEY = 'bc:utmQuery'
const DISMISS_KEY = 'bc:utmCtaDismissed'

function isUtmVisitor() {
  try {
    const params = new URLSearchParams(window.location.search)
    const taggedNow = UTM_KEYS.some((k) => params.get(k))
    if (taggedNow) {
      sessionStorage.setItem(VISITOR_KEY, '1')
      if (!sessionStorage.getItem(QUERY_KEY)) {
        sessionStorage.setItem(QUERY_KEY, window.location.search || '')
      }
    }
    return sessionStorage.getItem(VISITOR_KEY) === '1'
  } catch {
    // Storage blocked (private mode): fall back to checking the current URL only.
    try {
      const params = new URLSearchParams(window.location.search)
      return UTM_KEYS.some((k) => params.get(k))
    } catch {
      return false
    }
  }
}

export default function PaidVisitorCTA() {
  const { pathname } = useLocation()
  const [show, setShow] = useState(false)

  useEffect(() => {
    let dismissed = false
    try { dismissed = sessionStorage.getItem(DISMISS_KEY) === '1' } catch { /* ignore */ }
    const onForm = pathname === '/contact'
    const onAdmin = pathname.startsWith('/admin') || pathname === '/login'
    setShow(isUtmVisitor() && !dismissed && !onForm && !onAdmin)
  }, [pathname])

  if (!show) return null

  const query = (() => {
    try { return sessionStorage.getItem(QUERY_KEY) || '' } catch { return '' }
  })()
  const to = `/contact${query}`

  function dismiss() {
    try { sessionStorage.setItem(DISMISS_KEY, '1') } catch { /* ignore */ }
    setShow(false)
  }

  return (
    <div
      role="region"
      aria-label="Request access for your club"
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
        <Link
          to={to}
          style={{
            background: '#34d399', color: '#0b1220', fontWeight: 700,
            padding: '10px 18px', borderRadius: 10, textDecoration: 'none',
            fontSize: 15, whiteSpace: 'nowrap',
          }}
        >
          Request access →
        </Link>
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
  )
}
