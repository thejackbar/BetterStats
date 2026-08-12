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
// `variant` — 'icon' (default) is the bare square icon button used where space
// is tight (a module sidebar footer, a header already dense with icons). 'bar'
// is a labelled, bordered button ("BOOKMARKS", + a count once any are saved) —
// matching the house style of the other text actions in a page header (VIEW
// PUBLIC PAGE, SETUP GUIDE) — for places where the control needs to read as its
// own clear entry point rather than one more unlabelled icon. 'inline' renders
// the toggle + list directly in the flow, no popover — for a narrow off-canvas
// drawer, where a `w-64` floating panel would overflow (and get clipped: an
// `overflow-y` ancestor forces `overflow-x` to clip too, per the CSS spec) a
// panel much narrower than that. `dense` shrinks the 'bar' variant's padding to
// match a tighter row (e.g. a mobile drawer).
// `onNavigate` — called when a saved bookmark is actually followed (not on the
// toggle-this-page action, which doesn't leave the page), so a host rendering
// this inside its own off-canvas drawer can close that drawer too.
export default function BookmarkButton({ pageLabel, drop = 'down', variant = 'icon', dense = false, onNavigate }) {
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

  // Shared between the floating popover (icon/bar variants) and the inline
  // variant — the toggle-this-page row plus the saved-bookmarks list.
  const renderContents = () => (
    <>
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
                onClick={() => { setOpen(false); onNavigate?.() }}
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
    </>
  )

  if (variant === 'inline') {
    return (
      <div className="w-full rounded-lg border border-pb-hairline bg-pb-surface overflow-hidden">
        <div className="max-h-[45vh] overflow-y-auto py-1">{renderContents()}</div>
      </div>
    )
  }

  return (
    <div className="relative" ref={ref}>
      {variant === 'bar' ? (
        <button
          onClick={() => setOpen(o => !o)}
          className={`inline-flex items-center gap-1.5 font-mono text-[10px] tracking-wide2 transition-colors border pb-hairline rounded ${dense ? 'px-2.5 py-1' : 'px-3 py-1.5'} ${bookmarked ? '' : 'text-pb-faint hover:text-pb-text'}`}
          style={bookmarked ? { color: 'var(--pb-accent)', borderColor: 'var(--pb-accent)' } : undefined}
          title="Bookmarks — save and jump back to admin pages"
          aria-label="Bookmarks"
          aria-haspopup="menu"
          aria-expanded={open}
        >
          <BookmarkIcon filled={bookmarked} size={12} />
          BOOKMARKS
          {bookmarks.length > 0 && (
            <span className="rounded-full px-1.5 leading-[15px]" style={{ background: 'var(--pb-surface2)', color: 'var(--pb-faint)' }}>
              {bookmarks.length}
            </span>
          )}
        </button>
      ) : (
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
      )}

      {open && (
        <div
          className={`absolute w-64 max-h-[70vh] overflow-y-auto rounded-lg border border-pb-hairline bg-pb-surface shadow-xl z-50 py-1 ${drop === 'up' ? 'bottom-full mb-2 left-0' : 'right-0 mt-2'}`}
          role="menu"
        >
          {renderContents()}
        </div>
      )}
    </div>
  )
}
