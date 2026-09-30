import { Link, useLocation } from 'react-router-dom'
import { useEffect, useRef, useState } from 'react'
import BrandLogo from './BrandLogo'
import ModuleLockup, { ModuleWordmark } from './ModuleLockup'
import SelfServeTrialModal from './admin/SelfServeTrialModal'
import { CORE_MARKETING, MODULES_MARKETING } from '../data/modules-marketing'
import { useSelfServeTrialGate } from '../hooks/useSelfServeTrialGate'
import { DEMO, trackDemoClick } from '../data/webinar'

// The desktop row is already 16px over its box at 768px with five links, and a
// sixth takes that to 91px — the overflow slides under the CTA button rather
// than wrapping. So the Watch menu (which replaced a plain Videos link) takes
// the slot Videos had: in the row from 1024px, in the mobile menu below 768px,
// and the footer carries both destinations always.
const LINKS_BEFORE_WATCH = [
  { to: '/pricing', label: 'Pricing' },
  { to: '/compare', label: 'Compare' },
]
const LINKS_AFTER_WATCH = [
  { to: '/about', label: 'About' },
  { to: '/faq', label: 'FAQ' },
  { to: '/contact', label: 'Contact' },
]
const LINKS = [...LINKS_BEFORE_WATCH, ...LINKS_AFTER_WATCH]

// The Watch menu: the whole-platform recording first, the how-to library
// second. One slot for two destinations is what keeps the row from overflowing.
const WATCH_LINKS = [
  {
    to: DEMO.path,
    title: DEMO.title,
    blurb: `Every module in one session · ${DEMO.length}`,
    badge: 'Recording',
    placement: 'nav',
  },
  {
    to: '/videos',
    title: 'How-to videos',
    blurb: 'Short walkthroughs, one job at a time',
  },
]

// Open-on-hover dropdown that also closes on an outside click or Escape.
function useDropdown() {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    if (!open) return
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])
  return [open, setOpen, ref]
}

function Chevron({ open }) {
  return (
    <svg className={`w-3.5 h-3.5 transition-transform duration-200 ${open ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
    </svg>
  )
}

// Core + bolt-on modules, for the "Modules" dropdown.
const MODULE_LINKS = [
  { slug: CORE_MARKETING.slug, name: CORE_MARKETING.name, icon: CORE_MARKETING.icon, logo: CORE_MARKETING.logo, accent: CORE_MARKETING.accent, tagline: CORE_MARKETING.tagline, to: CORE_MARKETING.to },
  ...MODULES_MARKETING.map((m) => ({ slug: m.slug, name: m.name, icon: m.icon, logo: m.logo, accent: m.accent, tagline: m.tagline, to: `/modules/${m.slug}` })),
]

export default function MarketingNav() {
  const { pathname, hash } = useLocation()
  const [open, setOpen] = useState(false)       // mobile menu
  const [scrolled, setScrolled] = useState(false)
  const [modOpen, setModOpen, modRef] = useDropdown()      // desktop Modules dropdown
  const [watchOpen, setWatchOpen, watchRef] = useDropdown() // desktop Watch dropdown
  const isHome = pathname === '/'
  const { trigger: triggerTrial, modalOpen: trialModalOpen, setModalOpen: setTrialModalOpen, defaultTrialDays } = useSelfServeTrialGate()

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 30)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // Close menus on navigation.
  useEffect(() => {
    setOpen(false)
    setModOpen(false)
    setWatchOpen(false)
  }, [pathname, setModOpen, setWatchOpen])

  // Home page gets a transparent nav until scrolled; other pages get a solid one.
  const navBg =
    isHome && !scrolled
      ? 'bg-transparent'
      : 'bg-pb-bg/85 backdrop-blur-md border-b pb-hairline'

  const modulesActive =
    pathname === '/modules' || pathname.startsWith('/modules/') || pathname === '/features'
  const watchActive = pathname === DEMO.path || pathname === '/videos' || pathname.startsWith('/videos/')

  const linkCls = (to) => {
    const active = to === pathname || to === `${pathname}${hash}`
    return `px-3 py-2 rounded text-sm font-medium transition-colors whitespace-nowrap ${
      active ? 'text-pb-text' : 'text-pb-dim hover:text-pb-text'}`
  }

  return (
    <nav className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${navBg}`}>
      {/* Skip to main content — visible on focus for keyboard users */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-[200] focus:px-4 focus:py-2 focus:rounded focus:bg-pb-surface focus:text-pb-text focus:font-mono focus:text-xs focus:border focus:pb-hairline focus:outline-none"
      >
        Skip to main content
      </a>

      <div className="max-w-[1280px] mx-auto px-4 sm:px-6 lg:px-10 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5 group" aria-label="BetterCricket home">
          <BrandLogo className="w-7 h-7 object-contain" />
          <span className="font-bold text-base tracking-tight text-pb-text group-hover:text-accent transition-colors">
            Better<span className="text-accent">Cricket</span>
          </span>
        </Link>

        {/* Desktop */}
        <div className="hidden md:flex items-center gap-1">
          {/* Modules dropdown */}
          <div
            ref={modRef}
            className="relative"
            onMouseEnter={() => setModOpen(true)}
            onMouseLeave={() => setModOpen(false)}
          >
            <button
              type="button"
              onClick={() => setModOpen((o) => !o)}
              aria-haspopup="true"
              aria-expanded={modOpen}
              className={`px-3 py-2 rounded text-sm font-medium transition-colors inline-flex items-center gap-1 whitespace-nowrap ${
                modulesActive ? 'text-pb-text' : 'text-pb-dim hover:text-pb-text'
              }`}
            >
              Modules
              <svg className={`w-3.5 h-3.5 transition-transform duration-200 ${modOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {modOpen && (
              <div className="absolute top-full left-0 pt-2 w-[440px]">
                <div className="bg-pb-surface border pb-hairline rounded-xl p-2 shadow-[0_24px_60px_-15px_rgba(0,0,0,0.85)]">
                  {MODULE_LINKS.map((m) => (
                    <Link key={m.slug} to={m.to} className="flex items-start gap-3 p-2.5 rounded-lg hover:bg-pb-surface2/50 transition-colors group">
                      <img src={m.logo} alt="" className="w-9 h-9 rounded-lg flex-shrink-0" />
                      <div className="min-w-0">
                        <p className="text-sm font-semibold"><ModuleWordmark name={m.name} accent={m.accent} /></p>
                        <p className="text-xs text-pb-dim leading-snug">{m.tagline}</p>
                      </div>
                    </Link>
                  ))}
                  <div className="border-t pb-hairline mt-2 pt-3 flex items-center justify-between px-2.5 pb-1">
                    <Link to="/modules" className="text-xs text-pb-dim hover:text-pb-text">All modules →</Link>
                    <Link to="/pricing" className="text-xs text-accent hover:underline">Compare plans</Link>
                  </div>
                </div>
              </div>
            )}
          </div>

          {LINKS_BEFORE_WATCH.map((link) => (
            <Link key={link.to} to={link.to} className={linkCls(link.to)}>{link.label}</Link>
          ))}

          {/* Watch dropdown — from lg, the slot the plain Videos link had. */}
          <div
            ref={watchRef}
            className="relative hidden lg:block"
            onMouseEnter={() => setWatchOpen(true)}
            onMouseLeave={() => setWatchOpen(false)}
          >
            <button
              type="button"
              onClick={() => setWatchOpen((o) => !o)}
              aria-haspopup="true"
              aria-expanded={watchOpen}
              data-testid="nav-watch"
              className={`px-3 py-2 rounded text-sm font-medium transition-colors inline-flex items-center gap-1 whitespace-nowrap ${
                watchActive ? 'text-pb-text' : 'text-pb-dim hover:text-pb-text'
              }`}
            >
              Watch
              <Chevron open={watchOpen} />
            </button>
            {watchOpen && (
              <div className="absolute top-full left-0 pt-2 w-[340px]">
                <div className="bg-pb-surface border pb-hairline rounded-xl p-2 shadow-[0_24px_60px_-15px_rgba(0,0,0,0.85)]">
                  {WATCH_LINKS.map((w) => (
                    <Link
                      key={w.to}
                      to={w.to}
                      onClick={w.placement ? () => trackDemoClick(w.placement) : undefined}
                      className="flex items-start gap-3 p-2.5 rounded-lg hover:bg-pb-surface2/50 transition-colors"
                    >
                      <span className={`w-9 h-9 rounded-lg flex-shrink-0 flex items-center justify-center ${
                        w.badge ? 'bg-accent text-[var(--pb-on-accent,#08110b)]' : 'bg-pb-surface2 text-pb-dim'}`}
                      >
                        <svg className="w-4 h-4 ml-0.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                          <path d="M8 5.14v13.72a1 1 0 0 0 1.52.85l11.1-6.86a1 1 0 0 0 0-1.7L9.52 4.29A1 1 0 0 0 8 5.14Z" />
                        </svg>
                      </span>
                      <span className="min-w-0">
                        <span className="flex items-center gap-2 text-sm font-semibold text-pb-text">
                          {w.title}
                          {w.badge && (
                            <span className="font-mono text-[9px] tracking-wide2 uppercase text-accent border border-accent/40 rounded px-1.5 py-px">{w.badge}</span>
                          )}
                        </span>
                        <span className="block text-xs text-pb-dim leading-snug">{w.blurb}</span>
                      </span>
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </div>

          {LINKS_AFTER_WATCH.map((link) => (
            <Link key={link.to} to={link.to} className={linkCls(link.to)}>{link.label}</Link>
          ))}
          <button
            type="button"
            onClick={triggerTrial}
            className="ml-3 cta-primary !text-[13px] !py-2.5 !px-4 whitespace-nowrap"
            aria-label="Request access for your club"
          >
            Request access
          </button>
        </div>

        {/* Mobile hamburger */}
        <button
          type="button"
          className="md:hidden text-pb-dim hover:text-pb-text p-2"
          onClick={() => setOpen((o) => !o)}
          aria-label={open ? 'Close navigation' : 'Open navigation'}
          aria-expanded={open}
          aria-controls="mobile-nav"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            {open ? (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            )}
          </svg>
        </button>
      </div>

      {open && (
        <div id="mobile-nav" className="md:hidden border-t pb-hairline bg-pb-surface px-4 py-3 flex flex-col gap-1">
          <p className="px-1 pt-1 pb-1 text-[10px] font-mono uppercase tracking-wide3 text-pb-faint">Modules</p>
          {MODULE_LINKS.map((m) => (
            <Link
              key={m.slug}
              to={m.to}
              className="flex items-center gap-2.5 py-2"
              onClick={() => setOpen(false)}
            >
              <ModuleLockup name={m.name} logo={m.logo} accent={m.accent} size={28} logoClassName="rounded-md" textClassName="text-sm font-display font-bold leading-none" />
            </Link>
          ))}
          <div className="border-t pb-hairline my-2" />
          <p className="px-1 pt-1 pb-1 text-[10px] font-mono uppercase tracking-wide3 text-pb-faint">Watch</p>
          {WATCH_LINKS.map((w) => (
            <Link
              key={w.to}
              to={w.to}
              className="text-sm font-medium text-pb-dim hover:text-pb-text py-2 transition-colors flex items-center gap-2"
              onClick={() => { if (w.placement) trackDemoClick('nav_mobile'); setOpen(false) }}
            >
              {w.title}
              {w.badge && <span className="font-mono text-[9px] tracking-wide2 uppercase text-accent">· {DEMO.length}</span>}
            </Link>
          ))}
          <div className="border-t pb-hairline my-2" />
          {LINKS.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              className="text-sm font-medium text-pb-dim hover:text-pb-text py-2 transition-colors"
              onClick={() => setOpen(false)}
            >
              {link.label}
            </Link>
          ))}
          <button
            type="button"
            onClick={() => { setOpen(false); triggerTrial() }}
            className="mt-2 cta-primary !py-3 justify-center"
          >
            Request access
          </button>
        </div>
      )}
      {trialModalOpen && (
        <SelfServeTrialModal
          publicMode
          defaultTrialDays={defaultTrialDays}
          onClose={() => setTrialModalOpen(false)}
        />
      )}
    </nav>
  )
}
