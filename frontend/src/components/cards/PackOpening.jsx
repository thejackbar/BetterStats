// Opening a pack, full screen: a sealed foil pack shakes and tears open in a flash, then the cards are
// turned over one at a time, lowest rarity first so the best is last. A card's frame glows through its
// back in the tier's colour before it turns (a gold back is an Epic), and the bigger the card the bigger
// the reveal: a silver flash for a Rare, a gold burst and a shake for an Epic, the room dimming for a
// Legendary, and a spotlight with holo for a Special. A summary of the pack follows, marking the cards
// that are new to the collection. Built on GSAP, which the site already ships. For a player who has asked
// their device for less motion every effect collapses to a plain turn.
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import gsap from 'gsap'
import { CardBack, CardView, ScaledCard, CARD_H, CARD_W, DEFAULT_DISPLAY } from './CardFaces'
import { PACKS, QUALITY_STARS, TIERS, TIER_ORDER, packName } from './cardTheme'
import { hexWithAlpha, onColor } from '../PlayerTradingCard'

const reduced = () => typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
const MONO = "'JetBrains Mono', monospace"

function packLook(source, accent, label, design, quality) {
  const p = PACKS[source] || PACKS.weekly
  return {
    label: label || p.label,
    line: design?.line || p.line,
    stars: quality in QUALITY_STARS ? QUALITY_STARS[quality] : (p.stars || 0),
    a: design?.a || p.a || `color-mix(in srgb, ${accent} 70%, #fff)`,
    b: design?.b || p.b || `color-mix(in srgb, ${accent} 55%, #000)`,
    on: design?.on || p.on || onColor(accent),
  }
}

// The pack is drawn once at a fixed size and scaled to fit, so it is the same shape wherever it sits: the tiny ones in the
// list of ways to earn a pack and the big one that tears open. (Sizing the type from the width squashed the names.)
const DESIGN_W = 220
const DESIGN_H = 330
// How big a club's centre image is, as a box inside the pack's 192px of room.
const ART_BOX = { s: 84, m: 126, l: 176 }

// A name that fits: the longer it is the smaller it sets, down to a floor, and it may wrap onto a second or third line.
function nameSize(text) {
  const n = (text || '').length
  if (n <= 10) return 30
  if (n <= 20) return 26
  if (n <= 28) return 21
  return 17
}

// A sealed foil pack. `stripRef` is the crimped top that tears away. `label` overrides the name (a scheduled event).
// `design` is the club's own look for this pack (services/player_card_designs.py): a background image, a centre image, its
// colours, how dark the background is laid down, whether the name and the club logo are drawn, and where the centre image sits.
export function PackArt({ source, club, accent, display = DEFAULT_DISPLAY, width = 220, stripRef, bodyRef, glow = false, label, design, quality, size }) {
  const look = packLook(source, accent, label, design, quality)
  const scale = width / DESIGN_W
  const strip = Math.round(DESIGN_H * 0.075)
  const crimp = 'repeating-linear-gradient(90deg, rgba(255,255,255,.55) 0 3px, rgba(0,0,0,.18) 3px 6px)'
  const bg = design?.background_url || null
  const art = design?.art_url || null
  const showName = design ? design.show_name !== false : true
  const showLogo = design ? design.show_logo !== false : true
  const pos = design?.art_position || 'center'
  const box = ART_BOX[design?.art_size] || ART_BOX.m
  const shade = bg ? { textShadow: '0 2px 10px rgba(0,0,0,.55)' } : null
  const mark = art
    ? <img src={art} alt="" data-pack-design-art style={{ width: box, height: box, objectFit: 'contain', filter: 'drop-shadow(0 6px 14px rgba(0,0,0,.4))' }} />
    : !showLogo ? null
      : source === 'duck'
        ? <div style={{ font: `800 italic 100px/1 ${display}`, textShadow: '0 4px 14px rgba(0,0,0,.25)' }}>0</div>
        : club?.logo_url
          ? <img src={club.logo_url} alt="" style={{ width: 100, height: 100, objectFit: 'contain', filter: 'drop-shadow(0 6px 14px rgba(0,0,0,.35))' }} />
          : <div style={{ font: `800 italic 64px/1 ${display}` }}>{initials(club?.name || club?.short_name)}</div>
  const words = showName && (
    <>
      {look.stars > 0 && <div aria-hidden data-pack-stars={look.stars} style={{ font: `700 14px/1 ${MONO}`, letterSpacing: 4, opacity: 0.9, ...shade }}>{'★'.repeat(look.stars)}</div>}
      <div data-pack-name style={{ font: `800 italic ${nameSize(look.label)}px/1.1 ${display}`, textTransform: 'uppercase', letterSpacing: 1, maxWidth: '100%', overflowWrap: 'anywhere', ...shade }}>{look.label}</div>
      <div style={{ font: `600 11px/1.25 ${MONO}`, letterSpacing: 1.5, textTransform: 'uppercase', opacity: 0.85, maxWidth: '100%', ...shade }}>{look.line}</div>
      <div style={{ font: `600 9px ${MONO}`, letterSpacing: 2, textTransform: 'uppercase', opacity: 0.65, ...shade }}>{size || 5} cards</div>
    </>
  )
  return (
    <div data-pack-art={source} data-pack-designed={design ? 'yes' : 'no'} style={{ position: 'relative', width, height: Math.round(DESIGN_H * scale), flex: 'none', filter: `drop-shadow(0 ${Math.round(18 * scale)}px ${Math.round(30 * scale)}px rgba(0,0,0,.5))${glow ? ` drop-shadow(0 0 ${Math.round(22 * scale)}px ${hexWithAlpha(accent, 0.7)})` : ''}` }}>
      <div style={{ position: 'absolute', left: 0, top: 0, width: DESIGN_W, height: DESIGN_H, transform: `scale(${scale})`, transformOrigin: 'top left' }}>
        <div ref={stripRef} style={{ position: 'absolute', left: 0, right: 0, top: 0, height: strip, background: `${crimp}, linear-gradient(180deg, ${look.a}, ${look.b})`, borderRadius: '10px 10px 0 0', zIndex: 2 }} />
        <div ref={bodyRef} style={{ position: 'absolute', left: 0, right: 0, top: strip - 1, bottom: 0, background: `linear-gradient(165deg, ${look.a} 0%, ${look.b} 100%)`, borderRadius: '0 0 12px 12px', overflow: 'hidden', color: look.on }}>
          {bg
            ? <div data-pack-design-bg style={{ position: 'absolute', inset: 0, background: `center / cover no-repeat url("${bg}")` }} />
            : <div style={{ position: 'absolute', inset: 0, background: 'repeating-linear-gradient(115deg, rgba(255,255,255,.14) 0 14px, transparent 14px 34px)' }} />}
          {bg && design.overlay > 0 && <div aria-hidden style={{ position: 'absolute', inset: 0, background: `rgba(0,0,0,${design.overlay})` }} />}
          <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: strip, background: crimp, opacity: 0.8 }} />
          <div style={{ position: 'absolute', inset: `0 14px ${strip}px`, display: 'flex', flexDirection: pos === 'bottom' ? 'column-reverse' : 'column', alignItems: 'center', justifyContent: pos === 'center' ? 'center' : pos === 'top' ? 'flex-start' : 'flex-end', gap: 10, textAlign: 'center', minWidth: 0, paddingTop: pos === 'top' ? 16 : 0, paddingBottom: pos === 'bottom' ? 16 : 0 }}>
            {mark}
            {words && <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, maxWidth: '100%', minWidth: 0 }}>{words}</div>}
          </div>
          <div className="cc-sheen" aria-hidden />
        </div>
      </div>
    </div>
  )
}

// A handful of sparks thrown out from the middle of `host`.
function burst(host, color, count = 18) {
  if (!host || reduced()) return
  for (let i = 0; i < count; i += 1) {
    const s = document.createElement('span')
    s.style.cssText = `position:absolute;left:50%;top:50%;width:${4 + Math.random() * 6}px;height:${4 + Math.random() * 6}px;border-radius:50%;background:${color};pointer-events:none;box-shadow:0 0 10px ${color}`
    host.appendChild(s)
    const a = Math.random() * Math.PI * 2
    const d = 90 + Math.random() * 140
    gsap.to(s, { x: Math.cos(a) * d, y: Math.sin(a) * d, opacity: 0, scale: 0.2, duration: 0.7 + Math.random() * 0.5, ease: 'power2.out', onComplete: () => s.remove() })
  }
}

const rank = (c) => TIER_ORDER.indexOf(c.tier)
const initials = (name) => (name || '?').split(/\s+/).filter(Boolean).map((w) => w[0]).join('').slice(0, 3).toUpperCase()

export default function PackOpening({ pack, packsLeft, club, accent, display = DEFAULT_DISPLAY, sponsor, owned, openPack, onClose, onNext }) {
  const [stage, setStage] = useState('ready') // ready | opening | reveal | summary
  const [cards, setCards] = useState([])
  const [idx, setIdx] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [error, setError] = useState('')
  const [cardW, setCardW] = useState(300)
  const busy = useRef(false)
  const refs = { pack: useRef(null), strip: useRef(null), body: useRef(null), flash: useRef(null), shell: useRef(null), flip: useRef(null), wrap: useRef(null), dim: useRef(null), rays: useRef(null), fx: useRef(null) }
  const [leftAfter, setLeftAfter] = useState(packsLeft)

  // The card fills the screen, within reason.
  useLayoutEffect(() => {
    const fit = () => setCardW(Math.max(220, Math.min(320, window.innerWidth - 56, (window.innerHeight - 190) * (CARD_W / CARD_H))))
    fit()
    window.addEventListener('resize', fit)
    return () => window.removeEventListener('resize', fit)
  }, [])

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape' && stage !== 'opening') onClose?.() }
    document.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = prev }
  }, [onClose, stage])

  // The sealed pack idles with a gentle float; killed the moment it is opened.
  useEffect(() => {
    if (stage !== 'ready' || reduced()) return undefined
    const t = gsap.to(refs.pack.current, { y: -8, rotation: 1.2, duration: 1.7, ease: 'sine.inOut', yoyo: true, repeat: -1 })
    return () => { t.kill(); gsap.set(refs.pack.current, { y: 0, rotation: 0 }) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage])

  const tear = () => new Promise((resolve) => {
    if (reduced()) { gsap.set(refs.pack.current, { opacity: 0 }); resolve(); return }
    const tl = gsap.timeline({ onComplete: resolve })
    tl.to(refs.pack.current, { x: 7, duration: 0.05, repeat: 9, yoyo: true, ease: 'none' })
      .to(refs.pack.current, { scale: 1.08, duration: 0.18, ease: 'power2.in' })
      .to(refs.strip.current, { x: 150, y: -120, rotation: 38, opacity: 0, duration: 0.5, ease: 'power2.out' }, '<')
      .fromTo(refs.flash.current, { opacity: 0, scale: 0.2 }, { opacity: 1, scale: 3, duration: 0.32, ease: 'power2.out' }, '<0.05')
      .to(refs.body.current, { scaleY: 0.9, y: 40, opacity: 0, duration: 0.4, ease: 'power2.in' }, '<0.05')
      .to(refs.flash.current, { opacity: 0, duration: 0.35 }, '>-0.05')
  })

  const start = async () => {
    if (busy.current || stage !== 'ready') return
    busy.current = true
    setError('')
    setStage('opening')
    const request = openPack()
    try {
      await tear()
      const res = await request
      const got = [...(res.cards || [])].sort((a, b) => rank(a) - rank(b) || (a.rarity || 0) - (b.rarity || 0))
      setLeftAfter(res.packs_left ?? 0)
      setCards(got)
      setIdx(0)
      setFlipped(false)
      setStage('reveal')
    } catch (e) {
      setError(e?.message || 'That pack could not be opened. Try again.')
      setStage('ready')
      gsap.set([refs.pack.current, refs.strip.current, refs.body.current], { clearProps: 'all' })
    } finally {
      busy.current = false
    }
  }

  // Each new card slides up face down.
  useLayoutEffect(() => {
    if (stage !== 'reveal' || !refs.wrap.current) return
    gsap.set(refs.flip.current, { rotationY: 0 })
    if (!reduced()) gsap.fromTo(refs.wrap.current, { y: 80, opacity: 0, scale: 0.92 }, { y: 0, opacity: 1, scale: 1, duration: 0.42, ease: 'power3.out' })
    else gsap.set(refs.wrap.current, { clearProps: 'all' })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx, stage])

  const current = cards[idx]

  const reveal = () => {
    if (busy.current || flipped || !current) return
    busy.current = true
    const tier = current.tier
    const t = TIERS[tier] || TIERS.common
    const big = tier === 'legendary' || tier === 'special'
    if (reduced()) {
      gsap.set(refs.flip.current, { rotationY: 180 })
      setFlipped(true)
      busy.current = false
      return
    }
    // The card counts as turned (and tappable for the next one) the moment it lands; the room lighting
    // fades back on its own afterwards instead of holding the player up.
    const tl = gsap.timeline({ onComplete: () => { setFlipped(true); busy.current = false } })
    if (big) {
      tl.to(refs.dim.current, { opacity: tier === 'special' ? 0.88 : 0.7, duration: 0.5 })
      if (tier === 'special') {
        tl.to(refs.rays.current, { opacity: 1, duration: 0.5 }, '<')
        gsap.fromTo(refs.rays.current, { rotation: 0 }, { rotation: 90, duration: 6, ease: 'none' })
      }
      tl.to(refs.flip.current, { scale: 1.06, duration: 0.45, yoyo: true, repeat: 1, ease: 'sine.inOut' })
    } else if (tier === 'epic') {
      tl.to(refs.flip.current, { y: -6, duration: 0.12, yoyo: true, repeat: 3 })
    }
    tl.to(refs.flip.current, { rotationY: 180, duration: big ? 0.95 : 0.6, ease: 'power2.inOut' })
    if (tier !== 'common') {
      tl.fromTo(refs.fx.current, { opacity: 0, scale: 0.3 }, { opacity: 1, scale: big ? 3.2 : 2.2, duration: 0.35, ease: 'power2.out' }, '-=0.35')
      tl.add(() => gsap.to(refs.fx.current, { opacity: 0, duration: 0.5 }))
      tl.add(() => burst(refs.shell.current, t.glow, tier === 'rare' ? 10 : 26), '-=0.6')
      if (tier !== 'rare') tl.add(() => { refs.shell.current?.classList.add('cc-shake'); setTimeout(() => refs.shell.current?.classList.remove('cc-shake'), 520) }, '-=0.7')
    }
    if (big) tl.add(() => gsap.to([refs.dim.current, refs.rays.current], { opacity: 0, delay: 0.5, duration: 0.8 }))
  }

  const next = () => {
    if (busy.current || !flipped) return
    if (idx >= cards.length - 1) { setStage('summary'); return }
    busy.current = true
    const done = () => { setIdx((i) => i + 1); setFlipped(false); busy.current = false }
    if (reduced()) { done(); return }
    gsap.to(refs.wrap.current, { x: -160, opacity: 0, rotation: -8, duration: 0.28, ease: 'power2.in', onComplete: () => { gsap.set(refs.wrap.current, { clearProps: 'x,rotation' }); done() } })
  }

  const tap = () => { if (stage === 'reveal') (flipped ? next() : reveal()) }
  const skip = () => { if (!busy.current) { setFlipped(true); setStage('summary') } }

  const summary = useMemo(() => {
    const counts = new Map()
    return cards.map((c) => {
      const seen = counts.get(c.key) || 0
      counts.set(c.key, seen + 1)
      return { card: c, isNew: !owned.has(c.key) && seen === 0 }
    })
  }, [cards, owned])

  const best = cards.length ? cards[cards.length - 1] : null
  const bestTier = best ? (TIERS[best.tier] || TIERS.common) : null

  const ui = (
    <div role="dialog" aria-modal="true" aria-label="Opening a pack" data-pack-overlay
      style={{ position: 'fixed', inset: 0, zIndex: 80, background: `radial-gradient(circle at 50% 40%, color-mix(in srgb, ${accent} 30%, #0b1018), #04070b 78%)`, color: '#fff', overflow: 'clip', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <div aria-hidden style={{ position: 'absolute', inset: 0, overflow: 'hidden', pointerEvents: 'none', zIndex: 1 }}>
      <div ref={refs.dim} style={{ position: 'absolute', inset: 0, background: '#000', opacity: 0, pointerEvents: 'none' }} />
      <div ref={refs.rays} style={{ position: 'absolute', left: '50%', top: '46%', width: 900, height: 900, marginLeft: -450, marginTop: -450, opacity: 0, pointerEvents: 'none', background: 'repeating-conic-gradient(rgba(125,211,252,.28) 0deg 8deg, transparent 8deg 22deg)', maskImage: 'radial-gradient(circle, #000 0%, transparent 65%)', WebkitMaskImage: 'radial-gradient(circle, #000 0%, transparent 65%)' }} />
      </div>

      <div style={{ position: 'relative', zIndex: 3, width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 16px' }}>
        <div style={{ font: `600 11px ${MONO}`, letterSpacing: 1.6, textTransform: 'uppercase', opacity: 0.85 }}>
          {packName(pack.source, pack.label)}{stage === 'reveal' && cards.length ? `  ·  ${idx + 1} of ${cards.length}` : ''}
        </div>
        {stage !== 'opening' && <button type="button" onClick={onClose} aria-label="Close" data-pack-close style={{ width: 36, height: 36, borderRadius: 18, border: '1px solid rgba(255,255,255,.3)', background: 'rgba(255,255,255,.08)', color: '#fff', fontSize: 16 }}>✕</button>}
      </div>

      <div ref={refs.shell} style={{ position: 'relative', zIndex: 2, flex: 1, width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 0 }}>
        <div ref={refs.fx} style={{ position: 'absolute', left: '50%', top: '50%', width: 220, height: 220, marginLeft: -110, marginTop: -110, borderRadius: '50%', pointerEvents: 'none', opacity: 0, zIndex: 4, background: `radial-gradient(circle, ${hexWithAlpha((TIERS[current?.tier] || TIERS.rare).glow, 0.95)}, transparent 68%)` }} />

        {(stage === 'ready' || stage === 'opening') && (
          <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 22 }}>
            <button type="button" ref={refs.pack} onClick={start} disabled={stage === 'opening'} data-pack-sealed aria-label="Open this pack"
              style={{ position: 'relative', background: 'none', border: 0, padding: 0, cursor: 'pointer' }}>
              <PackArt source={pack.source} label={pack.label} design={pack.design} quality={pack.quality} size={pack.size} club={club} accent={accent} display={display} width={Math.min(240, cardW * 0.8)} stripRef={refs.strip} bodyRef={refs.body} glow />
              <div ref={refs.flash} style={{ position: 'absolute', left: '50%', top: '30%', width: 180, height: 180, marginLeft: -90, marginTop: -90, borderRadius: '50%', opacity: 0, background: 'radial-gradient(circle, #fff, rgba(255,255,255,0) 68%)', pointerEvents: 'none' }} />
            </button>
            {stage === 'ready' && <div className="cc-pulse" style={{ font: `700 12px ${MONO}`, letterSpacing: 2, textTransform: 'uppercase' }}>Tap the pack to open it</div>}
            {stage === 'opening' && <div className="cc-pulse" style={{ font: `700 12px ${MONO}`, letterSpacing: 2, textTransform: 'uppercase' }}>Opening…</div>}
            {error && <div role="alert" data-pack-error style={{ maxWidth: 300, textAlign: 'center', fontSize: 13, color: '#fecaca' }}>{error}</div>}
          </div>
        )}

        {stage === 'reveal' && current && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14 }}>
            <div ref={refs.wrap} style={{ perspective: 1400 }}>
              <div ref={refs.flip} role="button" tabIndex={0} onClick={tap} data-pack-card={idx} data-pack-card-tier={current.tier} data-flipped={flipped ? 'yes' : 'no'}
                aria-label={flipped ? `${current.name}, ${(TIERS[current.tier] || TIERS.common).label}. Next card` : 'Turn the card over'}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); tap() } }}
                style={{ position: 'relative', width: cardW, height: cardW * (CARD_H / CARD_W), transformStyle: 'preserve-3d', cursor: 'pointer', outline: 'none' }}>
                <div style={{ position: 'absolute', inset: 0, backfaceVisibility: 'hidden', WebkitBackfaceVisibility: 'hidden' }}>
                  <ScaledCard width={cardW}><CardBack club={club} accent={accent} tier={current.tier === 'special' ? 'special' : current.tier} display={display} /></ScaledCard>
                </div>
                <div style={{ position: 'absolute', inset: 0, backfaceVisibility: 'hidden', WebkitBackfaceVisibility: 'hidden', transform: 'rotateY(180deg)' }}>
                  <ScaledCard width={cardW}><CardView card={current} club={club} accent={accent} display={display} sponsor={sponsor} /></ScaledCard>
                </div>
              </div>
            </div>
            <div aria-live="polite" style={{ minHeight: 40, textAlign: 'center' }}>
              {!flipped
                ? <div className="cc-pulse" style={{ font: `700 11px ${MONO}`, letterSpacing: 2, textTransform: 'uppercase' }}>Tap to turn it over</div>
                : (
                  <>
                    <div style={{ font: `800 italic 22px ${display}`, letterSpacing: 1, textTransform: 'uppercase', color: (TIERS[current.tier] || TIERS.common).ink }}>
                      {current.kind === 'special' ? `Special: ${current.title}` : (TIERS[current.tier] || TIERS.common).label}
                      {!owned.has(current.key) && <span data-new-badge style={{ marginLeft: 8, padding: '2px 7px', borderRadius: 6, background: '#22c55e', color: '#052e16', font: `700 10px ${MONO}`, letterSpacing: 1, verticalAlign: 'middle' }}>NEW</span>}
                    </div>
                    <div style={{ font: `600 11px ${MONO}`, letterSpacing: 1.5, textTransform: 'uppercase', opacity: 0.75, marginTop: 4 }}>{idx < cards.length - 1 ? 'Tap for the next card' : 'Tap to see the lot'}</div>
                  </>
                )}
            </div>
            <div style={{ display: 'flex', gap: 6 }} aria-hidden>
              {cards.map((c, i) => <span key={i} style={{ width: i === idx ? 18 : 7, height: 7, borderRadius: 4, background: i <= idx ? (TIERS[c.tier] || TIERS.common).glow : 'rgba(255,255,255,.25)', transition: 'width .2s' }} />)}
            </div>
          </div>
        )}

        {stage === 'summary' && (
          <div data-pack-summary style={{ width: '100%', maxWidth: 560, padding: '0 14px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14, overflowY: 'auto', maxHeight: '100%' }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ font: `800 italic 28px ${display}`, textTransform: 'uppercase', letterSpacing: 1.5 }}>Your pack</div>
              {bestTier && <div style={{ font: `700 11px ${MONO}`, letterSpacing: 1.6, textTransform: 'uppercase', color: bestTier.ink, marginTop: 3 }}>Best pull: {best.kind === 'special' ? `${best.name} (${best.title})` : `${best.name}, ${bestTier.label}`}</div>}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 10 }}>
              {summary.map(({ card, isNew }, i) => (
                <div key={i} style={{ position: 'relative' }} data-summary-card={card.tier}>
                  <ScaledCard width={Math.min(104, (Math.min(window.innerWidth, 560) - 56) / 3)}>
                    <CardView card={card} club={club} accent={accent} display={display} sponsor={sponsor} holo={false} />
                  </ScaledCard>
                  <span style={{ position: 'absolute', left: '50%', top: -7, transform: 'translateX(-50%)', padding: '1px 6px', borderRadius: 5, font: `700 9px ${MONO}`, letterSpacing: 1, background: isNew ? '#22c55e' : 'rgba(5,10,12,.75)', color: isNew ? '#052e16' : '#e2e8f0' }}>{isNew ? 'NEW' : 'DUPE'}</span>
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', justifyContent: 'center', paddingBottom: 18 }}>
              {leftAfter > 0 && <button type="button" onClick={onNext} data-pack-next style={{ padding: '12px 20px', borderRadius: 12, background: accent, color: onColor(accent), font: `700 12px ${MONO}`, letterSpacing: 1.4, textTransform: 'uppercase' }}>Open another ({leftAfter} left)</button>}
              <button type="button" onClick={onClose} data-pack-done style={{ padding: '12px 20px', borderRadius: 12, border: '1px solid rgba(255,255,255,.35)', background: 'rgba(255,255,255,.08)', color: '#fff', font: `700 12px ${MONO}`, letterSpacing: 1.4, textTransform: 'uppercase' }}>Done</button>
            </div>
          </div>
        )}
      </div>

      {stage === 'reveal' && (
        <button type="button" onClick={skip} data-pack-skip style={{ position: 'relative', zIndex: 3, margin: '0 0 16px', padding: '8px 14px', font: `600 11px ${MONO}`, letterSpacing: 1.4, textTransform: 'uppercase', color: 'rgba(255,255,255,.7)', background: 'none', border: 0, textDecoration: 'underline' }}>Skip to the results</button>
      )}
    </div>
  )
  return createPortal(ui, document.body)
}
