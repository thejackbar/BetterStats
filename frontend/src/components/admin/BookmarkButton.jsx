import { useState, useEffect, useRef } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useBookmarks } from '../../hooks/useBookmarks'

function prettifyPath(path) {
  const seg = (path || '').split('/').filter(Boolean).pop() || 'Page'
  return seg.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

const BookmarkIcon = ({ filled, size = 16 }) => (
  <svg
    width={size} height={size} viewBox="0 0 24 24"
    fill={filled ? 'currentColor' : 'none'}
    stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
  >
    <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
  </svg>
)

// Shared header control for bookmarking the current admin page, plus a
// quick-access menu of every page the user has bookmarked. Self-contained
// (manages its own state via useBookmarks) so it drops into any admin layout's
// header unchanged — the core admin nav and every module surface. `pageLabel` is
// the name to store when bookmarking the current page; the host layout passes
// the one it already knows (its page title / nav label).
// `drop` — which way the menu opens. Default hangs below (a page header);
// 'up' is for the module sidebar footer, where below is off-screen.
export default function BookmarkButton({ pageLabel, drop = 'down' }) {
  const location = useLocation()
  const { bookmarks, isBookmarked, toggle, remove } = useBookmarks(true)
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  const currentPath = location.pathname
  const bookmarked = isBookmarked(currentPath)
  const label = pageLabel || prettifyPath(currentPath)

  // Close on outside click or Escape.
  useEffect(() => {
    if (!open) return
    const onDown = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  // Close when the route changes (e.g. a bookmark was clicked).
  useEffect(() => { setOpen(false) }, [currentPath])

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(o => !o)}
        className="w-6 h-6 flex items-center justify-center rounded text-pb-faint hover:text-pb-text hover:bg-pb-surface2 transition"
        title="Bookmarks"
        aria-label="Bookmarks"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <span style={bookmarked ? { color: 'var(--pb-accent)' } : undefined}>
          <BookmarkIcon filled={bookmarked} />
        </span>
      </button>

      {open && (
        <div
          className={`absolute w-64 max-h-[70vh] overflow-y-auto rounded-lg border border-pb-hairline bg-pb-surface shadow-xl z-50 py-1 ${drop === 'up' ? 'bottom-full mb-2 left-0' : 'right-0 mt-2'}`}
          role="menu"
        >
          <button
            onClick={() => toggle(currentPath, label)}
            className="w-full flex items-center gap-2 px-3 py-2 text-left text-sm text-pb-text hover:bg-pb-surface2 transition"
            role="menuitem"
          >
            <span style={{ color: 'var(--pb-accent)' }}><BookmarkIcon filled={bookmarked} size={15} /></span>
            <span className="flex-1 min-w-0 truncate">
              {bookmarked ? 'Remove this page' : 'Bookmark this page'}
            </span>
          </button>

          <div className="my-1 border-t border-pb-hairline" />

          <div className="px-3 py-1 font-mono text-[10px] tracking-wide2 text-pb-faint uppercase">
            Bookmarks
          </div>
          {bookmarks.length === 0 ? (
            <div className="px-3 py-2 text-xs text-pb-faint">
              No bookmarks yet. Bookmark a page to pin it here.
            </div>
          ) : (
            bookmarks.map(bm => {
              const active = location.pathname === bm.path
              return (
                <div key={bm.path} className="group relative flex items-center">
                  <Link
                    to={bm.path}
                    onClick={() => setOpen(false)}
                    title={bm.label}
                    className={`flex-1 min-w-0 block pl-3 pr-8 py-1.5 text-[13px] truncate transition ${
                      active ? '' : 'text-pb-faint hover:text-pb-text hover:bg-pb-surface2'
                    }`}
                    style={active ? { color: 'var(--pb-accent)' } : undefined}
                    role="menuitem"
                  >
                    {bm.label}
                  </Link>
                  <button
                    onClick={(e) => { e.preventDefault(); e.stopPropagation(); remove(bm.path) }}
                    className="absolute right-1.5 w-5 h-5 flex items-center justify-center rounded text-pb-faintest hover:text-pb-text hover:bg-pb-surface2 transition opacity-100 md:opacity-0 md:group-hover:opacity-100"
                    title={`Remove ${bm.label}`}
                    aria-label={`Remove ${bm.label}`}
                  >
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                      <path d="M6 6l12 12M18 6L6 18" />
                    </svg>
                  </button>
                </div>
              )
            })
          )}
        </div>
      )}
    </div>
  )
}
