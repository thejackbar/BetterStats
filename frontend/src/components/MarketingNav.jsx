import { Link, useLocation } from 'react-router-dom'
import { useEffect, useRef, useState } from 'react'
import BrandLogo from './BrandLogo'
import ModuleLockup, { ModuleWordmark } from './ModuleLockup'
import { FORM_URL } from '../data/marketing'
import { CORE_MARKETING, MODULES_MARKETING } from '../data/modules-marketing'

const LINKS = [
  { to: '/pricing', label: 'Pricing' },
  { to: '/compare', label: 'Compare' },
  { to: '/about', label: 'About' },
  { to: '/faq', label: 'FAQ' },
  { to: '/contact', label: 'Contact' },
]

// Core + bolt-on modules, for the "Modules" dropdown.
const MODULE_LINKS = [
  { slug: CORE_MARKETING.slug, name: CORE_MARKETING.name, icon: CORE_MARKETING.icon, logo: CORE_MARKETING.logo, accent: CORE_MARKETING.accent, tagline: CORE_MARKETING.tagline, to: CORE_MARKETING.to },
  ...MODULES_MARKETING.map((m) => ({ slug: m.slug, name: m.name, icon: m.icon, logo: m.logo, accent: m.accent, tagline: m.tagline, to: `/modules/${m.slug}` })),
]

export default function MarketingNav() {
  const { pathname, hash } = useLocation()
  const [open, setOpen] = useState(false)       // mobile menu
  const [scrolled, setScrolled] = useState(false)
  const [modOpen, setModOpen] = useState(false)  // desktop Modules dropdown
  const modRef = useRef(null)
  const isHome = pathname === '/'

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
  }, [pathname])

  // Close the desktop dropdown on outside click / Escape.
  useEffect(() => {
    if (!modOpen) return
    const onDoc = (e) => {
      if (modRef.current && !modRef.current.contains(e.target)) setModOpen(false)
    }
    const onKey = (e) => {
      if (e.key === 'Escape') setModOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [modOpen])

  // Home page gets a transparent nav until scrolled; other pages get a solid one.
  const navBg =
    isHome && !scrolled
      ? 'bg-transparent'
      : 'bg-pb-bg/85 backdrop-blur-md border-b pb-hairline'

  const modulesActive =
    pathname === '/modules' || pathname.startsWith('/modules/') || pathname === '/features'

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
        <Link to="/" className="flex items-center gap-2.5 group" aria-label="Better Cricket home">
          <BrandLogo className="w-7 h-7 object-contain" />
          <span className="font-bold text-base tracking-tight text-pb-text group-hover:text-accent transition-colors">
            Better<span className="text-accent"> Cricket</span>
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

          {LINKS.map((link) => {
            const active = link.to === pathname || link.to === `${pathname}${hash}`
            return (
              <Link
                key={link.to}
                to={link.to}
                className={`px-3 py-2 rounded text-sm font-medium transition-colors whitespace-nowrap ${
                  active ? 'text-pb-text' : 'text-pb-dim hover:text-pb-text'
                }`}
              >
                {link.label}
              </Link>
            )
          })}
          <a
            href={FORM_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-3 cta-primary !text-[13px] !py-2.5 !px-4 whitespace-nowrap"
            aria-label="Request access for your club (opens in new tab)"
          >
            Request access
          </a>
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
          <a
            href={FORM_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2 cta-primary !py-3 justify-center"
            onClick={() => setOpen(false)}
          >
            Request access
          </a>
        </div>
      )}
    </nav>
  )
}
