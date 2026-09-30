import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'

// Messages BetterCricket sends to club admins (routers/admin_broadcasts.py),
// drawn as a stack of one-line notices at the top of the admin dashboard.
//
// The server decides who sees what; this only draws it, reports that it was
// shown (which is what a view-once message runs on), and lets a recipient
// close one they are allowed to close.

// Each tone is a WORD as well as a colour, so the four never rely on colour
// alone. The ink is the tone mixed towards the page's own text colour, which
// darkens it on a light theme and lightens it on a dark one.
export const BROADCAST_TONES = {
  info: { label: 'Notice', glyph: 'i', hex: '#4f8ef7' },
  success: { label: 'Good news', glyph: '✓', hex: 'var(--pb-positive)' },
  warning: { label: 'Heads up', glyph: '!', hex: 'var(--pb-amber)' },
  critical: { label: 'Important', glyph: '!', hex: 'var(--pb-red)' },
}

const ink = hex => `color-mix(in srgb, ${hex} 72%, var(--pb-text))`

function MessageLink({ url, label }) {
  if (!url) return null
  const text = `${label || 'Open'} →`
  const cls = 'font-semibold underline underline-offset-2 whitespace-nowrap'
  if (url.startsWith('/')) return <Link to={url} className={cls}>{text}</Link>
  return <a href={url} target="_blank" rel="noopener noreferrer" className={cls}>{text}</a>
}

// One message. Exported so the super admin's composer previews exactly what
// the club will see.
export function BroadcastLine({ item, onDismiss, footer }) {
  const t = BROADCAST_TONES[item.tone] || BROADCAST_TONES.info
  return (
    <div
      role={item.tone === 'critical' ? 'alert' : 'status'}
      data-testid="admin-broadcast"
      className="flex items-start gap-3 rounded-lg border px-3.5 py-3"
      style={{
        background: `color-mix(in srgb, ${t.hex} 10%, var(--pb-surface))`,
        borderColor: `color-mix(in srgb, ${t.hex} 40%, transparent)`,
        borderLeftWidth: 4,
        borderLeftColor: t.hex,
      }}
    >
      <span
        aria-hidden="true"
        className="shrink-0 mt-px w-5 h-5 rounded-full flex items-center justify-center font-bold text-[12px] leading-none"
        style={{ background: t.hex, color: '#0a0d14' }}
      >
        {t.glyph}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[13.5px] leading-[1.5] text-pb-text" style={{ overflowWrap: 'anywhere' }}>
          <span className="font-mono text-[10px] tracking-wide2 uppercase mr-2" style={{ color: ink(t.hex) }}>
            {t.label}
          </span>
          {item.message}
          {item.link_url && (
            <>
              {' '}
              <span style={{ color: ink(t.hex) }}><MessageLink url={item.link_url} label={item.link_label} /></span>
            </>
          )}
        </p>
        {footer}
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss this message"
          title="Dismiss"
          className="shrink-0 -my-1.5 -mr-1.5 w-9 h-9 rounded-lg flex items-center justify-center text-pb-faint hover:text-pb-text hover:bg-pb-surface2 transition-colors"
        >
          ✕
        </button>
      )}
    </div>
  )
}

const AUDIENCE_TEXT = {
  all: 'every club',
  clubs: 'chosen clubs',
  users: 'named users',
}

export default function AdminBroadcastBanner() {
  const [items, setItems] = useState([])
  const [preview, setPreview] = useState(false)
  const [hidden, setHidden] = useState(() => new Set())
  // Recorded once per mount. A view-once message is gone on the next load,
  // which is the rule working, so a remount must not report it twice.
  const reported = useRef(new Set())

  useEffect(() => {
    let alive = true
    api.getAdminBroadcasts()
      .then(d => {
        if (!alive) return
        const list = Array.isArray(d?.items) ? d.items : []
        setItems(list)
        setPreview(!!d?.preview)
        if (d?.preview) return
        const fresh = list.map(i => i.id).filter(id => !reported.current.has(id))
        fresh.forEach(id => reported.current.add(id))
        if (fresh.length) api.markAdminBroadcastsSeen(fresh).catch(() => {})
      })
      .catch(() => {})
    return () => { alive = false }
  }, [])

  const shown = items.filter(i => !hidden.has(i.id))
  if (!shown.length) return null

  const dismiss = (item) => {
    setHidden(h => new Set(h).add(item.id))
    if (!preview) api.dismissAdminBroadcast(item.id).catch(() => {})
  }

  return (
    <section aria-label="Messages from BetterCricket" className="space-y-2 mb-6">
      {shown.map(item => (
        <BroadcastLine
          key={item.id}
          item={item}
          // A preview can always be hidden from the screen; a recipient only
          // when the message allows it.
          onDismiss={preview || item.dismissible ? () => dismiss(item) : undefined}
          footer={preview && (
            <p className="font-mono text-[10px] text-pb-faint mt-1">
              PREVIEW · what this club’s admins see · sent to {AUDIENCE_TEXT[item.audience] || 'clubs'}
              {' · '}hiding it here does not dismiss it for them
            </p>
          )}
        />
      ))}
    </section>
  )
}
