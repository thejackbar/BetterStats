// Website sub-navigation with dropdown support for menu groups.
// Top-level items render as links; items with children render as a dropdown
// (panel portaled to <body> so the horizontally-scrolling bar can't clip it).
import { useState, useRef, useEffect } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { createPortal } from 'react-dom'

const linkBase = 'px-3 py-2 text-[12px] font-mono font-semibold tracking-wide2 whitespace-nowrap border-b-2 transition-colors'

function SubNavLink({ to, children, end }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) => `${linkBase} ${isActive ? 'text-pb-text border-pb-accent' : 'text-pb-faint border-transparent hover:text-pb-text'}`}
      style={({ isActive }) => (isActive ? { borderColor: 'var(--pb-accent)' } : {})}
    >
      {children}
    </NavLink>
  )
}

export default function WebsiteNav({ slug, pages, sections }) {
  const { pathname } = useLocation()
  const [open, setOpen] = useState(null)        // index of the open dropdown
  const [pos, setPos] = useState({ top: 0, left: 0 })
  const btnRefs = useRef({})

  useEffect(() => { setOpen(null) }, [pathname])
  useEffect(() => {
    if (open == null) return
    const close = () => setOpen(null)
    window.addEventListener('scroll', close, { passive: true })
    const onDown = (e) => {
      const panel = document.getElementById('web-nav-panel')
      if (panel && panel.contains(e.target)) return
      const trigger = btnRefs.current[open]
      if (trigger && trigger.contains(e.target)) return
      setOpen(null)
    }
    document.addEventListener('mousedown', onDown)
    return () => { window.removeEventListener('scroll', close); document.removeEventListener('mousedown', onDown) }
  }, [open])

  const toggle = (i, e) => {
    e.preventDefault(); e.stopPropagation()
    if (open === i) return setOpen(null)
    const r = e.currentTarget.getBoundingClientRect()
    setPos({ top: r.bottom, left: r.left })
    setOpen(i)
  }

  const pageHref = (s) => `/${slug}/website/page/${s}`
  const dropActive = (item) =>
    [item.slug, ...item.children.map(c => c.slug)].some(s => s && pathname.startsWith(pageHref(s)))

  return (
    <div className="border-b pb-hairline-b bg-pb-surface sticky top-14 z-40">
      <div className="max-w-5xl mx-auto px-4 flex items-center gap-1 overflow-x-auto">
        <SubNavLink to={`/${slug}/website`} end>Home</SubNavLink>
        {sections.news && <SubNavLink to={`/${slug}/website/news`}>News</SubNavLink>}

        {pages.map((item, i) => {
          if (!item.children?.length) {
            return item.slug ? <SubNavLink key={i} to={pageHref(item.slug)}>{item.label}</SubNavLink> : null
          }
          const active = dropActive(item)
          return (
            <button
              key={i}
              ref={el => { btnRefs.current[i] = el }}
              onClick={e => toggle(i, e)}
              className={`${linkBase} flex items-center gap-1 ${active || open === i ? 'text-pb-text border-pb-accent' : 'text-pb-faint border-transparent hover:text-pb-text'}`}
              style={active ? { borderColor: 'var(--pb-accent)' } : {}}
            >
              {item.label}
              <svg width="8" height="5" viewBox="0 0 8 5" fill="currentColor" className={`transition-transform ${open === i ? 'rotate-180' : ''}`}><path d="M0 0l4 5 4-5z" /></svg>
            </button>
          )
        })}

        {sections.honours && <SubNavLink to={`/${slug}/website/honours`}>Honours</SubNavLink>}
        {sections.committee && <SubNavLink to={`/${slug}/website/committee`}>Committee</SubNavLink>}
        {sections.gallery && <SubNavLink to={`/${slug}/website/gallery`}>Gallery</SubNavLink>}
        <span className="flex-1" />
        <Link to={`/${slug}`} className="px-3 py-2 text-[11px] font-mono tracking-wide2 text-pb-faint hover:text-pb-accent whitespace-nowrap">
          CRICKET &amp; STATS →
        </Link>
      </div>

      {open != null && pages[open]?.children?.length > 0 && createPortal(
        <div
          id="web-nav-panel"
          style={{ position: 'fixed', top: pos.top, left: pos.left, zIndex: 200 }}
          className="bg-pb-surface border pb-hairline rounded-b shadow-xl py-1 min-w-[160px]"
        >
          {/* A parent that also has its own page links to it first. */}
          {pages[open].slug && (
            <Link to={pageHref(pages[open].slug)} onClick={() => setOpen(null)} className="block px-4 py-2 text-[12px] font-mono tracking-wide2 text-pb-faint hover:text-pb-text hover:bg-pb-surface2">
              {pages[open].label}
            </Link>
          )}
          {pages[open].children.map((c, j) => (
            <NavLink
              key={j}
              to={pageHref(c.slug)}
              onClick={() => setOpen(null)}
              className={({ isActive }) => `block px-4 py-2 text-[12px] font-mono tracking-wide2 ${isActive ? 'text-pb-text' : 'text-pb-faint hover:text-pb-text'} hover:bg-pb-surface2`}
            >
              {c.label}
            </NavLink>
          ))}
        </div>,
        document.body,
      )}
    </div>
  )
}
