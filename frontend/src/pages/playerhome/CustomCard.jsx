// A card the club wrote itself for the Player Dashboard (BetterStats > Player Dashboard >
// Your own modules): a link button, an announcement, an event with a countdown, or an image
// banner. Each is its own cell in the grid, in the order the club set. It is not a collapsible
// section like the built-in ones: a link that has to be opened before it can be tapped is no
// use, so the content is always shown.
//
// A link opens in a new tab, so the page stays where it was, and the tap is counted for the
// club (a plain tally; the call is fire-and-forget and never stops the link opening). The
// server only ever sends http(s) addresses.
import { api } from '../../lib/api'

function localDate(iso) {
  if (!iso) return null
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d)
}

function fmtEventDate(iso) {
  const d = localDate(iso)
  return d ? d.toLocaleDateString('en-AU', { weekday: 'short', day: 'numeric', month: 'short' }) : ''
}

function fmtTime(hhmm) {
  if (!hhmm) return ''
  const [h, m] = hhmm.split(':').map(Number)
  const suffix = h >= 12 ? 'pm' : 'am'
  const h12 = h % 12 || 12
  return m ? `${h12}:${String(m).padStart(2, '0')}${suffix}` : `${h12}${suffix}`
}

// Whole days from today to the event, on the player's own calendar.
export function daysUntil(iso, now = new Date()) {
  const d = localDate(iso)
  if (!d) return null
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  return Math.round((d - today) / 86400000)
}

function countdownText(days) {
  if (days == null || days < 0) return null
  if (days === 0) return 'Today'
  if (days === 1) return 'Tomorrow'
  if (days < 14) return `In ${days} days`
  const weeks = Math.floor(days / 7)
  return `In ${weeks} weeks`
}

function LinkButton({ token, m, fallback }) {
  if (!m.url) return null
  return (
    <a href={m.url} target="_blank" rel="noopener noreferrer" data-custom-link={m.id}
      onClick={() => { api.availPublicCustomClick(token, m.id).catch(() => {}) }}
      className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-[14px] font-semibold text-center"
      style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}>
      <span className="min-w-0 truncate">{m.button_label || fallback}</span>
      <span aria-hidden="true" className="shrink-0">↗</span>
    </a>
  )
}

function Body({ text }) {
  if (!text) return null
  return <p className="text-[13.5px] text-pb-dim mt-1.5 whitespace-pre-line break-words" data-custom-body>{text}</p>
}

export default function CustomCard({ token, m }) {
  if (m.kind === 'image') {
    const img = <img src={m.image_url} alt={m.title} loading="lazy" className="block w-full h-auto max-h-[480px] object-contain rounded-xl bg-pb-surface2" />
    return (
      <section data-group={`custom:${m.id}`} data-custom-card={m.kind} className="rounded-2xl border pb-hairline min-w-0 p-3">
        {m.url ? (
          <a href={m.url} target="_blank" rel="noopener noreferrer" data-custom-link={m.id} aria-label={m.title}
            onClick={() => { api.availPublicCustomClick(token, m.id).catch(() => {}) }}>{img}</a>
        ) : img}
        {(m.body || m.button_label) && (
          <div className="px-1 pt-2">
            <div className="font-display font-bold text-[15px]">{m.title}</div>
            <Body text={m.body} />
          </div>
        )}
      </section>
    )
  }

  const days = m.kind === 'event' ? daysUntil(m.event_date) : null
  const countdown = countdownText(days)
  const when = m.kind === 'event'
    ? [fmtEventDate(m.event_date), fmtTime(m.event_time), m.location].filter(Boolean).join(' · ')
    : ''
  const fallback = m.kind === 'event' ? 'Get tickets' : m.kind === 'text' ? 'Find out more' : 'Open'

  return (
    <section data-group={`custom:${m.id}`} data-custom-card={m.kind} className="rounded-2xl border pb-hairline min-w-0 px-4 py-3">
      <div className="flex items-start gap-3">
        {m.emoji && <span aria-hidden="true" className="text-[22px] leading-none shrink-0 pt-0.5">{m.emoji}</span>}
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2">
            <div className="font-display font-bold text-[16px] min-w-0 flex-1 break-words">{m.title}</div>
            {countdown && (
              <span data-custom-countdown className="shrink-0 rounded-full px-2.5 py-0.5 text-[11.5px] font-semibold"
                style={{ background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)', color: 'var(--pb-accent)' }}>
                {countdown}
              </span>
            )}
          </div>
          {when && <div className="text-[12.5px] text-pb-faint mt-0.5" data-custom-when>{when}</div>}
          <Body text={m.body} />
        </div>
      </div>
      <LinkButton token={token} m={m} fallback={fallback} />
    </section>
  )
}
