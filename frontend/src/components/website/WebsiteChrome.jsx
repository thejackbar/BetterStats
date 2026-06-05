// WebsiteChrome — shared shell for the public club website (/{slug}/website/*).
//
// Fetches the club + site config once, applies the club's theme, and renders a
// website sub-nav + a branded footer (social links, contact, a subtle
// "Powered by BetterStats" credit) around the page. The site config is exposed
// via context so the homepage doesn't have to re-fetch it. If the club hasn't
// enabled its website, we bounce to the stats dashboard.
import { createContext, useContext, useEffect, useState } from 'react'
import { Link, NavLink, Navigate } from 'react-router-dom'
import { api } from '../../lib/api'
import { useClub } from '../../hooks/useClub'
import { useClubTheme } from '../../hooks/useClubTheme'
import { PbSpinner } from '../../lib/presskit'

const WebsiteContext = createContext(null)
export const useWebsite = () => useContext(WebsiteContext)

const SOCIAL = {
  facebook: { label: 'Facebook', path: 'M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z' },
  instagram: { label: 'Instagram', path: 'M2 2m5 0h10a5 5 0 0 1 5 5v10a5 5 0 0 1-5 5H7a5 5 0 0 1-5-5V7a5 5 0 0 1 5-5z M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z M17.5 6.5h.01' },
  x: { label: 'X', path: 'M4 4l16 16M20 4L4 20' },
  twitter: { label: 'Twitter', path: 'M4 4l16 16M20 4L4 20' },
  youtube: { label: 'YouTube', path: 'M22 8.6a3 3 0 0 0-2.1-2.1C18 6 12 6 12 6s-6 0-7.9.5A3 3 0 0 0 2 8.6 31 31 0 0 0 2 12a31 31 0 0 0 .1 3.4 3 3 0 0 0 2.1 2.1C6 18 12 18 12 18s6 0 7.9-.5a3 3 0 0 0 2.1-2.1A31 31 0 0 0 22 12a31 31 0 0 0-.1-3.4z M10 15l5-3-5-3z' },
  tiktok: { label: 'TikTok', path: 'M16 3v9a4 4 0 1 1-4-4M16 3a5 5 0 0 0 5 5' },
  linkedin: { label: 'LinkedIn', path: 'M16 8a6 6 0 0 1 6 6v6h-4v-6a2 2 0 0 0-4 0v6h-4v-6a6 6 0 0 1 6-6z M6 9H2v11h4z M4 6a2 2 0 1 0 0-4 2 2 0 0 0 0 4z' },
  website: { label: 'Website', path: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z M2 12h20 M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20z' },
}

function SocialLink({ network, url }) {
  const meta = SOCIAL[network]
  if (!meta) return null
  const href = url.startsWith('http') || url.startsWith('mailto:') ? url : `https://${url}`
  return (
    <a
      href={href} target="_blank" rel="noopener noreferrer" title={meta.label} aria-label={meta.label}
      className="w-9 h-9 flex items-center justify-center rounded-full border pb-hairline text-pb-faint hover:text-pb-text hover:border-pb-accent transition-colors"
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d={meta.path} />
      </svg>
    </a>
  )
}

function SubNavLink({ to, children, end }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `px-3 py-2 text-[12px] font-mono font-semibold tracking-wide2 whitespace-nowrap border-b-2 transition-colors ${
          isActive
            ? 'text-pb-text border-pb-accent'
            : 'text-pb-faint border-transparent hover:text-pb-text'
        }`
      }
      style={({ isActive }) => (isActive ? { borderColor: 'var(--pb-accent)' } : {})}
    >
      {children}
    </NavLink>
  )
}

export default function WebsiteChrome({ slug, active, children }) {
  const { club, inactive, loading: clubLoading } = useClub(slug)
  useClubTheme(club)
  const [site, setSite] = useState(null)
  const [loading, setLoading] = useState(true)
  const [notEnabled, setNotEnabled] = useState(false)

  useEffect(() => {
    if (!slug) return
    let cancelled = false
    setLoading(true)
    api.webGetSite(slug)
      .then(s => { if (!cancelled) { setSite(s); setLoading(false) } })
      .catch(() => { if (!cancelled) { setNotEnabled(true); setLoading(false) } })
    return () => { cancelled = true }
  }, [slug])

  // Website off (or club missing) → send visitors to the stats dashboard.
  if (notEnabled || inactive) return <Navigate to={`/${slug}`} replace />
  if (loading || clubLoading || !site) {
    return <div className="max-w-5xl mx-auto px-4 py-20"><PbSpinner message="Loading…" /></div>
  }

  const pages = site.pages || []
  const sections = site.sections || {}
  const social = site.social || {}
  const hasSocial = Object.keys(social).length > 0

  return (
    <WebsiteContext.Provider value={{ slug, club, site }}>
      {/* Website sub-navigation */}
      <div className="border-b pb-hairline-b bg-pb-surface sticky top-14 z-40">
        <div className="max-w-5xl mx-auto px-4 flex items-center gap-1 overflow-x-auto">
          <SubNavLink to={`/${slug}/website`} end>Home</SubNavLink>
          {sections.news && <SubNavLink to={`/${slug}/website/news`}>News</SubNavLink>}
          {pages.map(p => (
            <SubNavLink key={p.slug} to={`/${slug}/website/page/${p.slug}`}>{p.label}</SubNavLink>
          ))}
          {sections.honours && <SubNavLink to={`/${slug}/website/honours`}>Honours</SubNavLink>}
          {sections.committee && <SubNavLink to={`/${slug}/website/committee`}>Committee</SubNavLink>}
          {sections.gallery && <SubNavLink to={`/${slug}/website/gallery`}>Gallery</SubNavLink>}
          <span className="flex-1" />
          <Link
            to={`/${slug}`}
            className="px-3 py-2 text-[11px] font-mono tracking-wide2 text-pb-faint hover:text-pb-accent whitespace-nowrap"
          >
            CRICKET &amp; STATS →
          </Link>
        </div>
      </div>

      <main className="min-h-[60vh]">{children}</main>

      {/* Branded website footer */}
      <footer className="border-t pb-hairline-t mt-16 bg-pb-surface">
        <div className="max-w-5xl mx-auto px-4 py-10">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6">
            <div className="flex items-center gap-3">
              {club?.logo_url && <img src={club.logo_url} alt="" className="w-10 h-10 rounded object-contain" />}
              <div>
                <div className="font-display font-bold text-pb-text">{site.name}</div>
                {site.contact_email && (
                  <a href={`mailto:${site.contact_email}`} className="text-[12px] text-pb-faint hover:text-pb-accent">
                    {site.contact_email}
                  </a>
                )}
              </div>
            </div>
            {hasSocial && (
              <div className="flex items-center gap-2">
                {Object.entries(social).map(([network, url]) => (
                  <SocialLink key={network} network={network} url={url} />
                ))}
              </div>
            )}
          </div>
          <div className="mt-8 pt-6 border-t pb-hairline-t flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-[11px] font-mono tracking-wide2 text-pb-faintest">
            <span>© {new Date().getFullYear()} {site.name}</span>
            <a href="https://betterstats.cricket" target="_blank" rel="noopener noreferrer" className="hover:text-pb-faint">
              Powered by BetterStats
            </a>
          </div>
        </div>
      </footer>
    </WebsiteContext.Provider>
  )
}
