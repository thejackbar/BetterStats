import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../../lib/api'
import brandWhite from '../../assets/bettercricket-white.svg'

// The picture a club's teaser link is sold with. NOT a page anyone is sent to:
// the backend renderer (services/club_teaser_images.py) opens
// /preview/<token>/card/<format> in headless Chromium and screenshots the
// element marked data-card. One design in one place, so the picture in an email
// and the page behind it are the same product.
//
// The sizes and the names flag MUST match club_teaser_images.FORMATS (a backend
// check reads this file to prove they do). Names: the email card goes to the
// club's own people, who know who their top run-scorer is; the two ad sizes
// leave the player's name off, because putting a named individual into public
// paid creative is the club's decision to make, not ours.
//
// Ready signal: data-card-ready="1" is set only when the figures, the fonts and
// the club's logo (if it has one) have all settled. The renderer waits for it,
// so a half-drawn card is never saved.
export const CARD_FORMATS = {
  card: { width: 1200, height: 630, names: true },
  feed: { width: 1080, height: 1350, names: false },
  story: { width: 1080, height: 1920, names: false },
}

const LOGO_WAIT_MS = 5000
// A card whose text is longer than the layout allows for is shrunk, in 5% steps,
// until it fits. Below this it is left to overflow, and the renderer refuses it.
// The margin kept clear on every side; the fit check holds the content inside it.
const padFor = (spec) => (spec.width > spec.height ? 56 : 72)
const FIT_STEP = 0.05
const FIT_MIN = 0.6
const fmtNum = (n) => Number(n || 0).toLocaleString()

// Words that tell you nothing about which club it is, left out of the crest.
const CREST_SKIP = new Set(['cricket', 'club', 'cc', 'the', 'of', 'and', '&', 'inc', 'incorporated'])
export function initials(name) {
  const words = String(name || '').split(/[\s\-_/]+/).filter((w) => w && !CREST_SKIP.has(w.toLowerCase()))
  const pick = words.length ? words : String(name || '?').split(/\s+/)
  return pick.slice(0, 2).map((w) => w[0]).join('').toUpperCase() || '?'
}

// A club name has no fixed length; shrink the type to keep it to two lines.
function nameSize(name, base) {
  const n = String(name || '').length
  if (n <= 20) return base
  if (n <= 30) return Math.round(base * 0.82)
  if (n <= 42) return Math.round(base * 0.68)
  return Math.round(base * 0.56)
}

// Up to three supporting facts, each one a figure the club will not mind seeing.
// The same rules as the page (club_teaser.presentation): the record only where
// it flatters, ladder places only the top half.
export function pickFacts(data, names) {
  const facts = []
  const { hero, record, ladders_shown: ladders } = data
  const bat = data.batting?.[0]
  const bowl = data.bowling?.[0]
  if (hero?.kind === 'runs' && bowl?.wickets >= 5) {
    facts.push({ label: 'Leading wicket-taker', value: `${fmtNum(bowl.wickets)} wkts`, who: names ? bowl.name : null })
  } else if (hero?.kind === 'wickets' && bat?.runs >= 100) {
    facts.push({ label: 'Top run-scorer', value: `${fmtNum(bat.runs)} runs`, who: names ? bat.name : null })
  }
  if (record) facts.push({ label: 'The season', value: `Won ${record.won} of ${record.played}`, who: null })
  if (ladders?.length) {
    facts.push({ label: ladders[0].grade, value: `${ladders[0].place} of ${ladders[0].teams}`, who: null, ladder: true })
  }
  if (facts.length < 3 && data.records?.[0]) {
    const r = data.records[0]
    facts.push({ label: r.label, value: String(r.value), who: names ? r.player : null })
  }
  return facts.slice(0, 3)
}

function Crest({ name, logo, size, onDone }) {
  const [failed, setFailed] = useState(false)
  const settled = useRef(false)   // the logo loaded or errored: the give-up timer must not undo it
  useEffect(() => {
    if (!logo) { onDone(); return undefined }
    // A logo host that hangs fires neither load nor error. Give it a few
    // seconds, then draw without it (the crest of initials shows) rather than
    // holding the whole card, and every picture behind it, for the browser's
    // own much longer timeout.
    const t = setTimeout(() => { if (!settled.current) { setFailed(true); onDone() } }, LOGO_WAIT_MS)
    return () => clearTimeout(t)
  }, [logo])   // eslint-disable-line react-hooks/exhaustive-deps
  const box = {
    width: size, height: size, borderRadius: size * 0.22, flex: 'none',
    display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden',
  }
  if (logo && !failed) {
    return (
      <div style={{ ...box, background: '#ffffff' }}>
        <img src={logo} alt="" crossOrigin="anonymous"
             onLoad={() => { settled.current = true; onDone() }}
             onError={() => { settled.current = true; setFailed(true); onDone() }}
             style={{ width: '88%', height: '88%', objectFit: 'contain' }} />
      </div>
    )
  }
  return (
    <div style={{ ...box, background: 'color-mix(in srgb, #16c784 22%, #0d1117)', border: '2px solid #16c784',
                  color: '#16c784', fontWeight: 800, fontSize: size * 0.42, letterSpacing: '0.02em' }}>
      {initials(name)}
    </div>
  )
}

export default function TeaserCard() {
  const { token, fmt } = useParams()
  const spec = CARD_FORMATS[fmt]
  const [data, setData] = useState(null)
  const [logoDone, setLogoDone] = useState(false)
  const [fontsDone, setFontsDone] = useState(false)
  const [fit, setFit] = useState(1)          // how far the content has been shrunk to fit
  const [fitted, setFitted] = useState(false) // the fit has been measured with the real fonts
  const inner = useRef(null)

  useEffect(() => {
    let alive = true
    api.publicTeaser(token).then((d) => { if (alive) setData(d) }).catch(() => { if (alive) setData(false) })
    return () => { alive = false }
  }, [token])

  useEffect(() => {
    // A screenshot target, not a page: keep it out of search results.
    let el = document.querySelector('meta[name="robots"]#teaser-robots')
    if (!el) {
      document.querySelectorAll('meta[name="robots"]').forEach((m) => m.remove())
      el = document.createElement('meta')
      el.name = 'robots'
      el.id = 'teaser-robots'
      document.head.appendChild(el)
    }
    el.setAttribute('content', 'noindex, nofollow')
  }, [])

  useEffect(() => {
    let alive = true
    const done = () => { if (alive) setFontsDone(true) }
    if (document.fonts?.ready) document.fonts.ready.then(done, done)
    else done()
    return () => { alive = false }
  }, [])

  const facts = useMemo(() => (data && spec ? pickFacts(data, spec.names) : []), [data, spec])

  // Measure once the fonts are in (a font changes line breaks): while the
  // content is taller or wider than its frame, shrink it a step and measure
  // again. Never grows back, so it settles.
  useLayoutEffect(() => {
    const el = inner.current
    if (!el || !fontsDone || !spec) return
    // Is any part of the content outside the padded area? Measured on the
    // content's own boxes (not the frame's scroll size) so the margin survives:
    // content that merely reaches into the bottom margin is shrunk too.
    const pad = padFor(spec)
    const box = el.getBoundingClientRect()
    // All in the picture's real pixels: the margin is `pad` laid-out pixels and
    // so shrinks with the zoom.
    const margin = pad * fit
    const over = [...el.children].some((c) => {
      const r = c.getBoundingClientRect()
      return r.bottom - box.top > box.height - margin + 1 || r.right - box.left > box.width - margin + 1
    })
    if (over && fit > FIT_MIN) setFit(Math.max(FIT_MIN, Math.round((fit - FIT_STEP) * 100) / 100))
    else setFitted(true)
  }, [data, fontsDone, fit, spec])

  if (!spec) return <div data-testid="teaser-card-unknown">Unknown card</div>
  if (data === false) return <div data-testid="teaser-card-missing">Not found</div>
  if (!data) return <div data-testid="teaser-card-loading" />

  const { width: W, height: H, names } = spec
  const wide = W > H
  const { club, season, hero } = data
  const place = [club.suburb, club.state].filter(Boolean).join(', ')
  const ready = fontsDone && logoDone && fitted
  const unitLabel = hero ? (hero.kind === 'runs' ? 'Top run-scorer' : 'Leading wicket-taker') : null
  const pad = padFor(spec)
  const story = fmt === 'story'
  const heroSize = wide ? 150 : (story ? 260 : 190)
  const nameBase = wide ? 60 : (story ? 78 : 68)
  const factSize = wide ? 34 : (story ? 50 : 42)

  return (
    <div data-theme="dark" style={{ background: '#070b14', width: W, height: H, overflow: 'hidden' }}>
      <div data-card data-card-ready={ready ? '1' : '0'} data-format={fmt} data-card-fit={fit}
           style={{
             width: W, height: H, position: 'relative', overflow: 'hidden',
             background: 'radial-gradient(120% 90% at 0% 0%, #12332b 0%, #0d1117 55%, #070b14 100%)',
           }}>
       {/* The content is laid out in a box 1/fit larger than the frame and zoomed
           back down, so shrinking it re-flows the text rather than just clipping.
           (zoom, not a transform: a transform leaves the frame's scroll size at the
           unscaled layout, and the renderer's clipping check reads that size.) */}
       <div ref={inner}
           style={{
             width: W / fit, height: H / fit, zoom: fit,
             boxSizing: 'border-box', padding: pad, position: 'relative',
             display: 'flex', flexDirection: wide ? 'row' : 'column', gap: wide ? 48 : 0,
             justifyContent: wide ? 'flex-start' : 'space-between',
             color: '#e8edf5', fontFamily: 'var(--pb-font-body)',
             // Free text with no break in it (a long name, a long code) wraps, so it
             // makes its box taller and the fit sees it, instead of running off the side.
             overflowWrap: 'anywhere',
           }}>
        {/* club + hero */}
        <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
                      flex: wide ? '1 1 0' : 'none', minWidth: 0, gap: wide ? 0 : 36 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: wide ? 22 : 32 }}>
            <Crest name={club.name} logo={club.logo_url} size={wide ? 92 : 140} onDone={() => setLogoDone(true)} />
            <div style={{ minWidth: 0 }}>
              <div data-card-season style={{ color: '#16c784', fontFamily: 'var(--pb-font-mono)', fontSize: wide ? 20 : 28,
                                             letterSpacing: '0.14em', textTransform: 'uppercase' }}>
                {season?.name || 'This season'}
              </div>
              <div data-card-club style={{ fontWeight: 800, lineHeight: 1.05, fontSize: nameSize(club.name, nameBase),
                                           marginTop: 6, overflowWrap: 'anywhere' }}>
                {club.name}
              </div>
              <div style={{ color: '#9aa7ba', fontSize: wide ? 22 : 30, marginTop: 8 }}>
                {[place, club.association].filter(Boolean).join(' · ')}
              </div>
            </div>
          </div>

          {hero && (
            <div data-card-hero style={{ marginTop: wide ? 0 : 20 }}>
              <div style={{ color: '#9aa7ba', fontFamily: 'var(--pb-font-mono)', fontSize: wide ? 20 : 30,
                            letterSpacing: '0.12em', textTransform: 'uppercase' }}>
                {unitLabel}
              </div>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 18, marginTop: 4 }}>
                <span data-card-value style={{ fontSize: heroSize, fontWeight: 800, lineHeight: 0.95,
                                               fontVariantNumeric: 'tabular-nums' }}>{fmtNum(hero.value)}</span>
                <span style={{ color: '#9aa7ba', fontSize: wide ? 36 : 54, paddingBottom: heroSize * 0.08 }}>{hero.unit}</span>
              </div>
              {names && <div data-card-player style={{ fontSize: wide ? 38 : 52, fontWeight: 700, marginTop: 8 }}>{hero.player}</div>}
              {hero.detail && (
                <div style={{ color: '#9aa7ba', fontSize: wide ? 24 : 34, marginTop: 6 }}>{hero.detail}</div>
              )}
            </div>
          )}
        </div>

        {/* facts + call to action */}
        <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
                      width: wide ? 380 : 'auto', flex: 'none', gap: wide ? 0 : 36 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: wide ? 16 : (story ? 26 : 18) }}>
            {facts.map((f) => (
              <div key={f.label + f.value} data-card-fact
                   style={{ borderRadius: 20, padding: wide ? '16px 22px' : (story ? '28px 36px' : '20px 32px'),
                            background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.12)' }}>
                <div style={{ color: '#9aa7ba', fontSize: wide ? 18 : 28, fontWeight: 600,
                              letterSpacing: '0.08em', textTransform: 'uppercase',
                              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{f.label}</div>
                <div style={{ fontSize: factSize, fontWeight: 800, marginTop: 2 }}>{f.value}</div>
                {f.who && <div style={{ color: '#9aa7ba', fontSize: wide ? 20 : 30 }}>{f.who}</div>}
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: wide ? 14 : 24 }}>
            <div data-card-cta style={{ flex: 1, background: '#16c784', color: '#08110b', fontWeight: 800, textAlign: 'center',
                                        borderRadius: 16, padding: wide ? '14px 12px' : (story ? '30px 24px' : '24px 20px'),
                                        fontSize: wide ? 24 : (story ? 40 : 36) }}>
              {names ? 'See the whole season' : 'Is this your club? Claim it free'}
            </div>
            <img src={brandWhite} alt="BetterCricket" style={{ width: wide ? 64 : (story ? 120 : 104), height: wide ? 64 : (story ? 120 : 104), flex: 'none' }} />
          </div>
        </div>
       </div>
      </div>
    </div>
  )
}
