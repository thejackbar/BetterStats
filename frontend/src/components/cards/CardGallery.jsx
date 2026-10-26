// The collection as a book. Cards sit in a binder, nine a page on a wide screen (two pages open like a
// spread) and four to a page on a phone, with a grey slot for every card the player has not found yet so
// the size of the set is always in front of them. Sort by any of the six figures, rarity, name or newest;
// filter to specials or doubles. Tap a card to hold it up and turn it over. Pages turn by button, key or
// swipe.
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import gsap from 'gsap'
import FlipCard from '../FlipCard'
import { CARD_H, CARD_W, CardBack, CardInfoBack, CardView, DEFAULT_DISPLAY, ScaledCard } from './CardFaces'
import { TIERS, TIER_ORDER, sortKeys } from './cardTheme'
import { onColor, splitName } from '../PlayerTradingCard'

const MONO = "'JetBrains Mono', monospace"
const reduced = () => typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

const surname = (c) => (splitName(c.name).last || c.name || '').toLowerCase()
const byTier = (a, b) => TIER_ORDER.indexOf(b.tier) - TIER_ORDER.indexOf(a.tier)
// A missing figure always sorts last, whichever way the sort runs.
const num = (k, dir) => (a, b) => {
  const x = a[k]; const y = b[k]
  if (x == null && y == null) return 0
  if (x == null) return 1
  if (y == null) return -1
  return dir * (x - y)
}

const SORTERS = {
  recent: (a, b) => (b.obtained_at || '').localeCompare(a.obtained_at || '') || surname(a).localeCompare(surname(b)),
  name: (a, b) => surname(a).localeCompare(surname(b)) || (a.name || '').localeCompare(b.name || ''),
  rarity: (a, b) => byTier(a, b) || ((b.rarity || 0) - (a.rarity || 0)) || surname(a).localeCompare(surname(b)),
  matches: num('matches', -1),
  runs: num('runs', -1),
  bat_avg: num('bat_avg', -1),
  wickets: num('wickets', -1),
  bowl_avg: num('bowl_avg', 1), // a lower bowling average is the better one
  dismissals: num('dismissals', -1),
}

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'regular', label: 'Players' },
  { key: 'special', label: 'Specials' },
  { key: 'doubles', label: 'Doubles' },
]

function EmptySlot({ width, accent }) {
  return (
    <div data-empty-slot aria-label="Not collected yet" style={{ width, height: width * (CARD_H / CARD_W), borderRadius: width * 0.07, border: '2px dashed rgba(148,163,184,.4)', background: 'repeating-linear-gradient(45deg, rgba(148,163,184,.07) 0 6px, transparent 6px 14px)', display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 'none' }}>
      <svg width={width * 0.4} height={width * 0.4} viewBox="0 0 24 24" fill="none" stroke="rgba(148,163,184,.55)" strokeWidth="1.4" aria-hidden="true">
        <circle cx="12" cy="8" r="3.6" /><path d="M4.5 20.5c.8-4 3.7-6 7.5-6s6.7 2 7.5 6" strokeLinecap="round" />
      </svg>
    </div>
  )
}

function Viewer({ card, club, accent, display, sponsor, onClose }) {
  const [flipped, setFlipped] = useState(false)
  const [w, setW] = useState(300)
  useLayoutEffect(() => {
    const fit = () => setW(Math.max(220, Math.min(340, window.innerWidth - 48, (window.innerHeight - 150) * (CARD_W / CARD_H))))
    fit()
    window.addEventListener('resize', fit)
    return () => window.removeEventListener('resize', fit)
  }, [])
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = prev }
  }, [onClose])
  const k = w / CARD_W
  return createPortal(
    <div role="dialog" aria-modal="true" aria-label={`${card.name} card`} data-card-viewer onClick={onClose}
      style={{ position: 'fixed', inset: 0, zIndex: 80, background: 'rgba(3,6,10,.88)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 14 }}>
      <button type="button" onClick={onClose} aria-label="Close" style={{ position: 'absolute', right: 14, top: 14, width: 38, height: 38, borderRadius: 19, border: '1px solid rgba(255,255,255,.3)', background: 'rgba(255,255,255,.08)', color: '#fff' }}>✕</button>
      <div onClick={(e) => e.stopPropagation()} style={{ width: w, height: CARD_H * k }}>
        <div style={{ width: CARD_W, height: CARD_H, transform: `scale(${k})`, transformOrigin: 'top left' }}>
          <FlipCard width={CARD_W} height={CARD_H} flipped={flipped} onFlip={() => setFlipped((f) => !f)}
            label={flipped ? 'Showing the details. Turn the card back over' : 'Showing the card. Turn it over for the details'}
            front={<CardView card={card} club={club} accent={accent} display={display} sponsor={sponsor} />}
            back={<CardInfoBack card={card} club={club} accent={accent} display={display} />} />
        </div>
      </div>
      <div style={{ font: `600 11px ${MONO}`, letterSpacing: 1.6, textTransform: 'uppercase', color: 'rgba(255,255,255,.75)', textAlign: 'center' }}>
        {(card.copies || 1) > 1 ? `${card.copies} copies  ·  ` : ''}Tap the card to turn it over
      </div>
    </div>,
    document.body,
  )
}

export default function CardGallery({ cards, totals, club, accent, display = DEFAULT_DISPLAY, sponsor }) {
  const [sort, setSort] = useState('recent')
  const [filter, setFilter] = useState('all')
  const [page, setPage] = useState(0)
  const [open, setOpen] = useState(null)
  const [box, setBox] = useState(360)
  const hostRef = useRef(null)
  const bookRef = useRef(null)
  const touch = useRef(null)

  // Layout follows the width it is given: 2 x 2 on a phone, 3 x 2 on a tablet, two such pages side by side when wide.
  useLayoutEffect(() => {
    const el = hostRef.current
    if (!el || typeof ResizeObserver === 'undefined') return undefined
    const fit = () => setBox(el.clientWidth || 360)
    fit()
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const mode = box < 560 ? 'phone' : box < 900 ? 'tablet' : 'spread'
  const cols = mode === 'phone' ? 2 : 3
  const rows = mode === 'phone' ? 2 : 3
  const perPage = cols * rows
  const pagesShown = mode === 'spread' ? 2 : 1
  const gap = mode === 'phone' ? 10 : 14
  const pageW = mode === 'spread' ? (box - 24) / 2 : box
  const cardW = Math.floor((pageW - 36 - gap * (cols - 1)) / cols)

  const owned = totals?.regular_owned ?? 0
  const specialOwned = totals?.special_owned ?? 0

  const list = useMemo(() => {
    let items = cards.slice()
    if (filter === 'regular') items = items.filter((c) => c.kind === 'player')
    if (filter === 'special') items = items.filter((c) => c.kind === 'special')
    if (filter === 'doubles') items = items.filter((c) => (c.copies || 1) > 1)
    items.sort(SORTERS[sort] || SORTERS.recent)
    const empties = filter === 'doubles' ? 0
      : filter === 'regular' ? Math.max(0, (totals?.regular_total || 0) - owned)
        : filter === 'special' ? Math.max(0, (totals?.special_total || 0) - specialOwned)
          : Math.max(0, (totals?.regular_total || 0) - owned) + Math.max(0, (totals?.special_total || 0) - specialOwned)
    return [...items, ...Array.from({ length: empties }, (_, i) => ({ empty: true, key: `empty-${i}` }))]
  }, [cards, filter, sort, totals, owned, specialOwned])

  const slotsPerSpread = perPage * pagesShown
  const spreads = Math.max(1, Math.ceil(list.length / slotsPerSpread))
  const at = Math.min(page, spreads - 1)
  useEffect(() => { if (page > spreads - 1) setPage(spreads - 1) }, [page, spreads])
  useEffect(() => { setPage(0) }, [sort, filter, mode])

  const turn = (dir) => {
    const next = Math.max(0, Math.min(spreads - 1, at + dir))
    if (next === at) return
    if (reduced() || !bookRef.current) { setPage(next); return }
    gsap.to(bookRef.current, {
      rotationY: dir * -14, x: dir * -28, opacity: 0.15, duration: 0.2, ease: 'power2.in',
      onComplete: () => {
        setPage(next)
        gsap.fromTo(bookRef.current, { rotationY: dir * 14, x: dir * 28, opacity: 0.15 }, { rotationY: 0, x: 0, opacity: 1, duration: 0.3, ease: 'power2.out' })
      },
    })
  }
  const onKey = (e) => { if (e.key === 'ArrowRight') turn(1); if (e.key === 'ArrowLeft') turn(-1) }
  const down = (e) => { touch.current = e.clientX }
  const up = (e) => {
    if (touch.current == null) return
    const dx = e.clientX - touch.current
    touch.current = null
    if (Math.abs(dx) > 60) turn(dx < 0 ? 1 : -1)
  }

  const slice = (p) => list.slice(at * slotsPerSpread + p * perPage, at * slotsPerSpread + (p + 1) * perPage)
  const paper = 'linear-gradient(180deg, #151d29, #0f1620)'
  const sel = { background: 'var(--pb-surface2, #1a2330)', color: 'var(--pb-text, #fff)', border: '1px solid var(--pb-hairline, rgba(255,255,255,.18))', borderRadius: 8, padding: '6px 8px', fontSize: 13 }
  const pct = totals?.regular_total ? Math.round((owned / totals.regular_total) * 100) : 0

  return (
    <div data-card-gallery ref={hostRef} style={{ width: '100%' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <div style={{ minWidth: 0, flex: '1 1 200px' }}>
          <div data-collected style={{ font: `700 12px ${MONO}`, letterSpacing: 1.2, textTransform: 'uppercase' }}>
            Collected {owned} / {totals?.regular_total ?? 0}
            {totals?.special_total > 0 && <span style={{ opacity: 0.7 }}>  ·  Specials {specialOwned} / {totals.special_total}</span>}
          </div>
          <div style={{ height: 6, borderRadius: 3, background: 'rgba(148,163,184,.25)', marginTop: 6, overflow: 'hidden' }}>
            <div style={{ width: `${pct}%`, height: '100%', background: accent }} />
          </div>
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
          <span style={{ opacity: 0.7 }}>Sort</span>
          <select aria-label="Sort cards" value={sort} onChange={(e) => setSort(e.target.value)} style={sel} data-gallery-sort>
            {sortKeys.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
        </label>
      </div>
      <div role="tablist" aria-label="Show" style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
        {FILTERS.map((f) => (
          <button key={f.key} type="button" role="tab" aria-selected={filter === f.key} onClick={() => setFilter(f.key)} data-gallery-filter={f.key}
            style={{ padding: '5px 12px', borderRadius: 999, fontSize: 12, fontWeight: 600, border: '1px solid var(--pb-hairline, rgba(255,255,255,.2))', background: filter === f.key ? accent : 'transparent', color: filter === f.key ? onColor(accent) : 'inherit' }}>
            {f.label}
          </button>
        ))}
      </div>

      <div className="cc-book" tabIndex={0} onKeyDown={onKey} onPointerDown={down} onPointerUp={up} aria-label="Card binder. Use the arrow keys to turn the page" style={{ outline: 'none', touchAction: 'pan-y' }}>
        <div ref={bookRef} data-book data-mode={mode} style={{ display: 'flex', gap: 0, borderRadius: 16, background: '#0a0f17', padding: 6, boxShadow: '0 10px 30px rgba(0,0,0,.35)', position: 'relative' }}>
          {Array.from({ length: pagesShown }).map((_, p) => {
            const slots = slice(p)
            return (
              <div key={p} data-page={at * pagesShown + p + 1} style={{ flex: 1, minWidth: 0, borderRadius: p === 0 ? '12px 4px 4px 12px' : '4px 12px 12px 4px', background: paper, padding: '16px 18px', minHeight: rows * (cardW * (CARD_H / CARD_W) + gap) + 20, position: 'relative' }}>
                {pagesShown === 2 && <div aria-hidden style={{ position: 'absolute', top: 0, bottom: 0, [p === 0 ? 'right' : 'left']: 0, width: 26, background: `linear-gradient(${p === 0 ? '90deg' : '270deg'}, rgba(0,0,0,0), rgba(0,0,0,.45))`, pointerEvents: 'none' }} />}
                <div style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, ${cardW}px)`, gap, justifyContent: 'center' }}>
                  {slots.map((c) => (c.empty
                    ? <EmptySlot key={c.key} width={cardW} accent={accent} />
                    : (
                      <button key={c.key} type="button" onClick={() => setOpen(c)} data-slot-card={c.key} data-tier={c.tier} aria-label={`${c.name}${c.kind === 'special' ? `, ${c.title}` : `, ${(TIERS[c.tier] || TIERS.common).label}`}${(c.copies || 1) > 1 ? `, ${c.copies} copies` : ''}`}
                        style={{ position: 'relative', padding: 0, border: 0, background: 'none', cursor: 'pointer', width: cardW, height: cardW * (CARD_H / CARD_W), flex: 'none', textAlign: 'left' }}>
                        <ScaledCard width={cardW}><CardView card={c} club={club} accent={accent} display={display} sponsor={sponsor} /></ScaledCard>
                        {(c.copies || 1) > 1 && <span data-copies style={{ position: 'absolute', right: 6, bottom: '22%', padding: '1px 7px', borderRadius: 999, background: '#0b1018', border: '1px solid rgba(255,255,255,.5)', color: '#fff', font: `700 11px ${MONO}` }}>×{c.copies}</span>}
                      </button>
                    )))}
                </div>
                <div style={{ position: 'absolute', bottom: 4, left: 0, right: 0, textAlign: 'center', font: `500 10px ${MONO}`, letterSpacing: 1.4, opacity: 0.45 }}>{at * pagesShown + p + 1}</div>
              </div>
            )
          })}
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 14, marginTop: 12 }}>
        <button type="button" onClick={() => turn(-1)} disabled={at === 0} data-gallery-prev style={{ padding: '8px 16px', borderRadius: 10, border: '1px solid var(--pb-hairline, rgba(255,255,255,.2))', opacity: at === 0 ? 0.4 : 1 }}>← Prev</button>
        <span style={{ font: `600 11px ${MONO}`, letterSpacing: 1.2, textTransform: 'uppercase', opacity: 0.8 }} data-gallery-pages>{pagesShown === 2 ? `Pages ${at * 2 + 1}-${at * 2 + 2}` : `Page ${at + 1}`} of {spreads * pagesShown}</span>
        <button type="button" onClick={() => turn(1)} disabled={at >= spreads - 1} data-gallery-next style={{ padding: '8px 16px', borderRadius: 10, border: '1px solid var(--pb-hairline, rgba(255,255,255,.2))', opacity: at >= spreads - 1 ? 0.4 : 1 }}>Next →</button>
      </div>
      {list.length === 0 && <p style={{ textAlign: 'center', fontSize: 13, opacity: 0.7, marginTop: 10 }}>Nothing here yet.</p>}

      {open && <Viewer card={open} club={club} accent={accent} display={display} sponsor={sponsor} onClose={() => setOpen(null)} />}
    </div>
  )
}
