import { useMemo, useState } from 'react'

// Where a club's engagement score came from, drawn rather than listed. The
// backend (services/engagement_sources.py) decides what a source is worth and
// what it is called; this file only decides how it looks, so a new source
// appears here the moment the scorer starts awarding it.
//
// One bar per category, not one per source: a reader wants "half of this is
// their own browsing, half is the ads" before they want the fifth decimal of
// an email open. The rows underneath carry the detail.

// Four hues, one per category, deliberately far apart so the segments read
// apart at 8px tall. Each is a real colour rather than an accent mix — this
// chart sits inside both the amber admin chrome and the violet BetterIQ one,
// and a category that changes hue with its surroundings can't be learned.
export const CATEGORY_STYLE = {
  engagement: { label: 'Engagement signals', colour: '#16c784', text: 'text-emerald-300' },
  intent: { label: 'Buying intent', colour: '#38bdf8', text: 'text-sky-300' },
  setup: { label: 'Setup & registration', colour: '#f5b542', text: 'text-amber-300' },
  account: { label: 'Customer account', colour: '#a78bfa', text: 'text-violet-300' },
}
const CATEGORY_ORDER = ['engagement', 'intent', 'setup', 'account']

const catOf = (c) => (CATEGORY_STYLE[c?.category] ? c.category : 'engagement')
const styleOf = (c) => CATEGORY_STYLE[catOf(c)]

// A segment narrower than this reads as a line rather than a block, so it is
// given a floor and the rest share what's left. The bar is a proportion, not a
// measurement — the exact points are on the row beneath it.
const MIN_SEGMENT_PCT = 1.5

function segments(items, total) {
  if (!total) return []
  const raw = items.map(c => ({ c, pct: (c.points / total) * 100 }))
  const short = raw.filter(r => r.pct < MIN_SEGMENT_PCT)
  if (!short.length) return raw
  const borrowed = short.reduce((n, r) => n + (MIN_SEGMENT_PCT - r.pct), 0)
  const longTotal = raw.filter(r => r.pct >= MIN_SEGMENT_PCT).reduce((n, r) => n + r.pct, 0)
  return raw.map(r => r.pct < MIN_SEGMENT_PCT ? { ...r, pct: MIN_SEGMENT_PCT }
    : { ...r, pct: r.pct - borrowed * (r.pct / (longTotal || 1)) })
}

/** The composition bar: every scoring source, in category order, sized by share. */
function ScoreBar({ items, total, hovered, onHover }) {
  const segs = segments(items, total)
  if (!segs.length) return null
  return (
    <div className="flex h-2.5 rounded-full overflow-hidden bg-pb-surface2" role="img"
      aria-label={`Score composition: ${items.map(c => `${c.label} ${c.points}`).join(', ')}`}>
      {segs.map(({ c, pct }) => (
        <div key={c.key} style={{ width: `${pct}%`, background: styleOf(c).colour,
          opacity: hovered && hovered !== c.key ? 0.3 : 1 }}
          className="transition-opacity first:rounded-l-full last:rounded-r-full"
          onMouseEnter={() => onHover?.(c.key)} onMouseLeave={() => onHover?.(null)}
          title={`${c.label} — ${c.points} of ${Math.round(total)}`} />
      ))}
    </div>
  )
}

/** One source: its own share as a bar, its points, and the counts behind it. */
function SourceRow({ c, total, hovered, onHover }) {
  const st = styleOf(c)
  const share = total ? Math.round((c.points / total) * 100) : 0
  const dim = hovered && hovered !== c.key
  return (
    <div className={`flex items-start gap-2 py-1 transition-opacity ${dim ? 'opacity-40' : ''}`}
      onMouseEnter={() => onHover?.(c.key)} onMouseLeave={() => onHover?.(null)}>
      <span className="mt-[5px] w-2 h-2 rounded-full shrink-0"
        style={{ background: c.present_only ? 'transparent' : st.colour,
          border: c.present_only ? `1px solid ${st.colour}` : undefined }} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="text-[12px] text-pb-text truncate">{c.label}</span>
          {!c.present_only && (
            <div className="h-1 rounded-full flex-1 min-w-[24px] bg-pb-surface2 overflow-hidden">
              <div className="h-full rounded-full" style={{ width: `${share}%`, background: st.colour }} />
            </div>
          )}
        </div>
        {c.detail && <div className="text-[10.5px] text-pb-faintest leading-snug">{c.detail}</div>}
      </div>
      <span className={`font-display font-bold text-[12px] whitespace-nowrap shrink-0 ${
        c.present_only ? 'text-pb-faintest' : st.text}`}>
        {c.present_only ? 'no points' : `+${c.points}`}
      </span>
    </div>
  )
}

/**
 * The whole "where is this score coming from" panel, shared by the CRM deal
 * card and the Sales Workspace drawer so the two can't drift apart.
 *
 * `data` is one `GET /clubs/{id}/engagement-breakdown` payload. Both callers
 * already hold one — the drawer's arrives inside its own fetch — so this
 * component never fetches anything itself.
 */
export default function EngagementSources({ data, compact = false }) {
  const [hovered, setHovered] = useState(null)
  const [showQuiet, setShowQuiet] = useState(false)

  const { scoring, quiet, total, byCategory } = useMemo(() => {
    const all = data?.contributions || []
    const scoring = all.filter(c => !c.present_only)
    const quiet = all.filter(c => c.present_only)
    const total = scoring.reduce((n, c) => n + c.points, 0)
    const byCategory = CATEGORY_ORDER
      .map(cat => ({ cat, items: scoring.filter(c => catOf(c) === cat) }))
      .filter(g => g.items.length)
    return { scoring, quiet, total, byCategory }
  }, [data])

  if (!data) return <p className="text-[12px] text-pb-faintest">No engagement data for this club yet.</p>

  const ordered = byCategory.flatMap(g => g.items)

  return (
    <div className="space-y-2.5">
      <ScoreBar items={ordered} total={total} hovered={hovered} onHover={setHovered} />

      {/* Category totals — the answer to "roughly, where is this coming from"
          before any single source is read. */}
      {byCategory.length > 1 && (
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          {byCategory.map(({ cat, items }) => {
            const sum = items.reduce((n, c) => n + c.points, 0)
            return (
              <span key={cat} className="flex items-center gap-1.5 text-[11px]">
                <span className="w-2 h-2 rounded-full" style={{ background: CATEGORY_STYLE[cat].colour }} />
                <span className="text-pb-faint">{CATEGORY_STYLE[cat].label}</span>
                <span className={`font-display font-bold ${CATEGORY_STYLE[cat].text}`}>
                  {Math.round(sum)}
                </span>
                <span className="text-pb-faintest">
                  ({total ? Math.round((sum / total) * 100) : 0}%)
                </span>
              </span>
            )
          })}
        </div>
      )}

      {scoring.length ? (
        <div className={compact ? '' : 'space-y-2'}>
          {byCategory.map(({ cat, items }) => (
            <div key={cat}>
              {!compact && byCategory.length > 1 && (
                <div className={`text-[10px] uppercase tracking-wide font-bold mb-0.5 ${CATEGORY_STYLE[cat].text}`}>
                  {CATEGORY_STYLE[cat].label}
                </div>
              )}
              <div className="divide-y divide-pb-hairline/50">
                {items.map(c => (
                  <SourceRow key={c.key} c={c} total={total} hovered={hovered} onHover={setHovered} />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-[12px] text-pb-faintest">
          Nothing is adding to this score right now.
        </p>
      )}

      {/* Signals the club really gave us that today's score isn't made of —
          the ad click behind a club whose enquiry now pins it at 80. Folded
          away by default so they can't be read as contributions. */}
      {quiet.length > 0 && (
        <div>
          <button type="button" onClick={() => setShowQuiet(v => !v)}
            className="text-[11px] text-pb-faint hover:text-pb-text">
            {showQuiet ? '▾' : '▸'} {quiet.length} other signal{quiet.length === 1 ? '' : 's'} on
            file, not adding to the score right now
          </button>
          {showQuiet && (
            <div className="mt-1 divide-y divide-pb-hairline/50 pl-1">
              {quiet.map(c => (
                <SourceRow key={c.key} c={c} total={total} hovered={hovered} onHover={setHovered} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
