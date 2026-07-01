// Notifications — a synthesised activity feed (deadline, price moves, rank moves,
// top scorer). Read state is local to the device (no per-manager table), keyed by
// each item's stable id.
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { DISP, tintBg, mix, GREEN, AMBER } from './ui'
import { ScreenTitle } from './shell'

const SEEN_KEY = 'bfc-notif-seen'

export function loadSeen() {
  try { return new Set(JSON.parse(localStorage.getItem(SEEN_KEY) || '[]')) } catch { return new Set() }
}
export function markSeen(ids) {
  try {
    const cur = loadSeen()
    ids.forEach(id => cur.add(id))
    localStorage.setItem(SEEN_KEY, JSON.stringify([...cur]))
  } catch { /* private mode */ }
}
export function unreadCount(items) {
  const seen = loadSeen()
  return (items || []).filter(n => !seen.has(n.id)).length
}

const toneColor = (t) => t === 'green' ? GREEN : t === 'amber' ? AMBER : t === 'accent' ? 'var(--accent-strong)' : 'var(--dim)'
const toneBg = (t) => t === 'green' ? mix(GREEN, 15) : t === 'amber' ? mix(AMBER, 15) : t === 'accent' ? tintBg(16) : 'var(--surface2)'

export default function Notifications({ token, onSeen }) {
  const [items, setItems] = useState(null)
  const [seen, setSeen] = useState(loadSeen())

  useEffect(() => { api.fanNotifications(token).then(d => setItems(d.notifications || [])).catch(() => setItems([])) }, [token])

  const markAll = () => {
    if (!items) return
    markSeen(items.map(n => n.id))
    setSeen(loadSeen())
    onSeen && onSeen()
  }

  if (!items) return <p style={{ color: 'var(--faint)', font: `500 13px 'Hanken Grotesk'` }}>Loading…</p>

  return (
    <div>
      <ScreenTitle title="Activity" right={items.length ? <button onClick={markAll} style={{ background: 'none', border: 'none', color: 'var(--accent-strong)', font: `600 11px 'Hanken Grotesk'`, cursor: 'pointer' }}>Mark all read</button> : null} />
      {!items.length
        ? <p style={{ font: `500 13px 'Hanken Grotesk'`, color: 'var(--faint)', paddingTop: 16 }}>Nothing new right now.</p>
        : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 14 }}>
            {items.map(n => {
              const unread = !seen.has(n.id)
              return (
                <div key={n.id} style={{ display: 'flex', gap: 11, padding: '12px 13px', background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 13 }}>
                  <div style={{ width: 32, height: 32, borderRadius: 9, flex: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', font: `800 14px ${DISP}`, color: toneColor(n.tone), background: toneBg(n.tone) }}>{n.badge}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ font: `700 12.5px 'Hanken Grotesk'`, color: 'var(--text)' }}>{n.title}</div>
                    <div style={{ font: `500 11px 'Hanken Grotesk'`, color: 'var(--faint)', marginTop: 2, lineHeight: 1.4 }}>{n.body}</div>
                  </div>
                  {unread && <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--pb-accent, #06B6D4)', flex: 'none', marginTop: 4 }} />}
                </div>
              )
            })}
          </div>
        )}
    </div>
  )
}
