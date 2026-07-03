import React from 'react'

/**
 * BetterSocials — grunge social-post background system.
 *
 * A single square background you drop behind any social-post content.
 * The graphic is club-colour driven; overlay your own stats / headline /
 * photo as children.
 *
 *   import { SocialBackground, SocialBackgroundDefs, SOCIAL_BACKGROUNDS } from './SocialBackgrounds'
 *
 *   // Mount the SVG filter defs ONCE, high in the tree (they're shared by id):
 *   <SocialBackgroundDefs />
 *
 *   // Then any number of backgrounds:
 *   <SocialBackground
 *     variant="ink-splatter"
 *     colors={{ secondary: org.accent_color }}   // club colours; see DEFAULT_COLORS
 *     size={1080}                                  // rendered px (square)
 *   >
 *     <YourPostContent />                          // absolutely-positioned overlay
 *   </SocialBackground>
 *
 * Fonts used (Anton / Barlow Condensed / JetBrains Mono) are already loaded
 * by index.html. All colour comes from the `colors` prop — nothing is baked in.
 */

export const DEFAULT_COLORS = {
  primary:   'var(--pb-bg, #0d1117)',     // dark base
  secondary: 'var(--pb-accent, #16c784)', // club accent
  tertiary:  'var(--pb-amber, #f59e0b)',  // secondary accent
  paper:     '#ece4d3',                    // light / print stock
  ink:       '#070a10',                    // near-black
}

// Picker metadata — key, human label, and a rough grouping for a variant menu.
export const SOCIAL_BACKGROUNDS = [
  { key: 'ink-splatter',     label: 'Ink Splatter',      group: 'Splatter & Spray' },
  { key: 'spray-stencil',    label: 'Spray Stencil',     group: 'Splatter & Spray' },
  { key: 'paint-sweep',      label: 'Paint Sweep',       group: 'Splatter & Spray' },
  { key: 'drip-curtain',     label: 'Drip Curtain',      group: 'Splatter & Spray' },
  { key: 'graffiti',         label: 'Graffiti Chaos',    group: 'Splatter & Spray' },
  { key: 'concrete-grit',    label: 'Concrete Grit',     group: 'Grit & Grunge' },
  { key: 'chevron-grit',     label: 'Chevron Grit',      group: 'Grit & Grunge' },
  { key: 'airbrush-glow',    label: 'Airbrush Glow',     group: 'Grit & Grunge' },
  { key: 'spotlight',        label: 'Photo Spotlight',   group: 'Grit & Grunge' },
  { key: 'torn-halftone',    label: 'Torn Halftone',     group: 'Print' },
  { key: 'halftone-ramp',    label: 'Halftone Ramp',     group: 'Print' },
  { key: 'poster-solid',     label: 'Poster Solid',      group: 'Print' },
  { key: 'led',              label: 'LED Scoreboard',    group: 'Print' },
  { key: 'riso-geometric',   label: 'Riso Geometric',    group: 'Geometric' },
  { key: 'gradient-linework',label: 'Gradient Linework', group: 'Geometric' },
  { key: 'bolt',             label: 'Bolt Energy',       group: 'Geometric' },
  { key: 'shard',            label: 'Shard Cut',         group: 'Geometric' },
  { key: 'contour-rings',    label: 'Contour Rings',     group: 'Geometric' },
]

const abs = (o) => ({ position: 'absolute', ...o })
const full = { position: 'absolute', inset: 0 }

// Reusable texture layers ---------------------------------------------------
const Grain = ({ blend = 'overlay', opacity = 0.5, fill }) => (
  <svg width={1080} height={1080} style={{ ...full, mixBlendMode: blend, opacity, pointerEvents: 'none' }}>
    <rect width="1080" height="1080" fill={fill} filter="url(#fx-grain)" />
  </svg>
)
const Tex = ({ id, fill, opacity = 1, blend, transform }) => (
  <svg width={1080} height={1080} style={{ ...full, ...(blend ? { mixBlendMode: blend } : {}), ...(transform ? { transform } : {}), opacity }}>
    <rect width="1080" height="1080" fill={fill} filter={`url(#${id})`} />
  </svg>
)
const Drip = ({ x, y, w, h, c }) => (
  <div style={abs({ left: x, top: y, width: w, height: h, background: c, borderRadius: `0 0 ${w}px ${w}px` })}>
    <div style={abs({ bottom: -w * 0.7, left: -w * 0.45, width: w * 1.9, height: w * 1.9, borderRadius: '50%', background: c })} />
  </div>
)

// Variant background layers (content-free) ----------------------------------
const VARIANTS = {
  'ink-splatter': (p) => (
    <React.Fragment>
      <div style={{ ...full, background: `radial-gradient(120% 120% at 12% 8%, ${p.primary}, ${p.ink} 70%)` }} />
      <Tex id="fx-splatter" fill={p.secondary} opacity={1} />
      <Tex id="fx-splatter2" fill={p.tertiary} opacity={0.95} transform="translate(180px,-120px) rotate(30deg)" />
      <Tex id="fx-spray" fill={p.secondary} opacity={0.9} />
      <div style={abs({ left: -40, top: 450, width: 1200, height: 190, background: p.secondary, filter: 'url(#fx-swipe)', transform: 'rotate(-6deg)', opacity: 0.34 })} />
      <Grain fill="#fff" />
    </React.Fragment>
  ),
  'spray-stencil': (p) => (
    <React.Fragment>
      <div style={{ ...full, background: '#1b1d21' }} />
      <Tex id="fx-grit" fill="#000" opacity={0.55} blend="multiply" />
      <div style={{ ...full, background: 'linear-gradient(200deg, rgba(0,0,0,0) 30%, rgba(0,0,0,.55))' }} />
      <div style={abs({ left: -60, top: 250, width: 1240, height: 300, background: p.secondary, filter: 'url(#fx-torn)', transform: 'rotate(-4deg)' })} />
      <Tex id="fx-spray" fill={p.secondary} opacity={0.85} transform="translateY(120px)" />
      <Drip x={170} y={540} w={9} h={150} c={p.secondary} />
      <Drip x={640} y={560} w={7} h={210} c={p.secondary} />
      <Drip x={900} y={545} w={8} h={110} c={p.secondary} />
      <Grain fill="#fff" opacity={0.55} />
    </React.Fragment>
  ),
  'concrete-grit': (p) => (
    <React.Fragment>
      <div style={{ ...full, background: 'linear-gradient(160deg, #23262c, #15171b)' }} />
      <Tex id="fx-grit" fill="#fff" opacity={0.7} blend="soft-light" />
      <Tex id="fx-grit" fill="#000" opacity={0.45} blend="multiply" />
      <div style={abs({ right: -120, top: -120, width: 520, height: 520, border: `26px solid ${p.secondary}`, borderRadius: '50%', opacity: 0.9, filter: 'url(#fx-rough)' })} />
      <div style={abs({ left: 0, bottom: 0, width: '100%', height: 14, background: `repeating-linear-gradient(90deg, ${p.tertiary} 0 46px, transparent 46px 92px)`, opacity: 0.8 })} />
      <Grain fill="#fff" />
    </React.Fragment>
  ),
  'torn-halftone': (p) => (
    <React.Fragment>
      <div style={{ ...full, background: p.paper }} />
      <div style={{ ...full, backgroundImage: `radial-gradient(${p.primary} 30%, transparent 32%)`, backgroundSize: '20px 20px', opacity: 0.14 }} />
      <div style={abs({ left: 0, top: 0, width: '100%', height: 560, background: p.primary, filter: 'url(#fx-torn)' })} />
      <div style={abs({ left: 0, top: 360, width: 640, height: 360, background: p.secondary, filter: 'url(#fx-torn)', transform: 'rotate(-2deg)' })} />
      <div style={abs({ right: 60, top: 80, width: 360, height: 360, backgroundImage: `radial-gradient(${p.paper} 32%, transparent 34%)`, backgroundSize: '22px 22px', opacity: 0.5 })} />
      <Grain fill="#000" blend="multiply" opacity={0.4} />
    </React.Fragment>
  ),
  'riso-geometric': (p) => (
    <React.Fragment>
      <div style={{ ...full, background: p.primary }} />
      <div style={abs({ right: -160, top: -160, width: 760, height: 760, borderRadius: '50%', background: p.secondary })} />
      <div style={abs({ left: -120, bottom: -220, width: 600, height: 600, background: p.tertiary, transform: 'rotate(45deg)' })} />
      <div style={abs({ right: -140, top: -140, width: 720, height: 720, borderRadius: '50%', backgroundImage: `radial-gradient(${p.primary} 30%, transparent 32%)`, backgroundSize: '26px 26px', opacity: 0.28, transform: 'translate(30px,30px)' })} />
      <div style={abs({ left: 0, top: '52%', width: '100%', height: 120, background: p.primary, transform: 'skewY(-4deg)' })} />
      <Grain fill="#000" blend="multiply" opacity={0.6} />
    </React.Fragment>
  ),
  'gradient-linework': (p) => (
    <React.Fragment>
      <div style={{ ...full, background: `linear-gradient(135deg, ${p.ink}, ${p.primary} 55%, ${p.secondary})` }} />
      <div style={{ ...full, backgroundImage: 'repeating-linear-gradient(115deg, rgba(255,255,255,.05) 0 2px, transparent 2px 34px)' }} />
      <div style={abs({ right: -80, bottom: -80, width: 620, height: 620, backgroundImage: 'radial-gradient(rgba(255,255,255,.5) 20%, transparent 22%)', backgroundSize: '24px 24px', opacity: 0.18 })} />
      <div style={abs({ left: -20, top: 300, width: 1120, height: 130, background: p.tertiary, filter: 'url(#fx-swipe)', transform: 'rotate(-7deg)', opacity: 0.9 })} />
      <Grain fill="#fff" opacity={0.4} />
    </React.Fragment>
  ),
  'bolt': (p) => (
    <React.Fragment>
      <div style={{ ...full, background: `radial-gradient(130% 100% at 80% 20%, ${p.primary}, ${p.ink})` }} />
      <div style={{ ...full, backgroundImage: 'repeating-linear-gradient(-24deg, transparent 0 60px, rgba(255,255,255,.03) 60px 64px)' }} />
      <div style={abs({ left: '50%', top: '50%', width: 820, height: 820, transform: 'translate(-50%,-50%) rotate(-16deg)', background: p.secondary, clipPath: 'polygon(55% 0,30% 46%,52% 46%,32% 100%,78% 40%,54% 40%)', opacity: 0.92 })} />
      <div style={abs({ left: '50%', top: '50%', width: 820, height: 820, transform: 'translate(-50%,-50%) rotate(-16deg) translate(18px,10px)', clipPath: 'polygon(55% 0,30% 46%,52% 46%,32% 100%,78% 40%,54% 40%)', backgroundImage: `radial-gradient(${p.ink} 30%, transparent 32%)`, backgroundSize: '22px 22px', opacity: 0.25 })} />
      <Tex id="fx-spray" fill={p.secondary} opacity={0.6} />
      <Grain fill="#fff" />
    </React.Fragment>
  ),
  'graffiti': (p) => (
    <React.Fragment>
      <div style={{ ...full, background: '#101216' }} />
      <Tex id="fx-grit" fill="#000" opacity={0.5} blend="multiply" />
      <div style={abs({ left: -80, top: 120, width: 1260, height: 280, background: p.tertiary, filter: 'url(#fx-torn)', transform: 'rotate(-7deg)' })} />
      <div style={abs({ left: -80, top: 560, width: 1260, height: 230, background: p.secondary, filter: 'url(#fx-torn)', transform: 'rotate(5deg)' })} />
      <Tex id="fx-splatter" fill="#fff" opacity={0.9} />
      <Tex id="fx-splatter2" fill={p.secondary} opacity={0.85} transform="translate(-140px,220px) rotate(140deg)" />
      <Grain fill="#fff" opacity={0.55} />
    </React.Fragment>
  ),
  'spotlight': (p) => (
    <React.Fragment>
      <div style={{ ...full, background: `radial-gradient(120% 120% at 80% 10%, ${p.primary}, ${p.ink} 72%)` }} />
      <Tex id="fx-splatter" fill={p.secondary} opacity={0.85} transform="translate(-160px,120px)" />
      <div style={abs({ left: 0, bottom: 250, width: 760, height: 120, background: p.secondary, filter: 'url(#fx-swipe)', transform: 'rotate(-5deg)', opacity: 0.9 })} />
      <Grain fill="#fff" opacity={0.45} />
    </React.Fragment>
  ),
  'poster-solid': (p) => (
    <React.Fragment>
      <div style={{ ...full, background: p.secondary }} />
      <div style={{ ...full, backgroundImage: 'radial-gradient(rgba(0,0,0,.35) 28%, transparent 30%)', backgroundSize: '24px 24px', opacity: 0.16 }} />
      <Grain fill="#000" blend="multiply" opacity={0.55} />
    </React.Fragment>
  ),
  'led': (p) => (
    <React.Fragment>
      <div style={{ ...full, background: '#07090c' }} />
      <div style={{ ...full, backgroundImage: 'radial-gradient(rgba(255,255,255,.07) 40%, transparent 42%)', backgroundSize: '16px 16px' }} />
      <div style={{ ...full, background: `radial-gradient(80% 60% at 50% 46%, ${p.secondary}22, transparent 70%)` }} />
      <Grain fill="#fff" opacity={0.4} />
    </React.Fragment>
  ),
  'shard': (p) => (
    <React.Fragment>
      <div style={{ ...full, background: p.ink }} />
      <div style={abs({ inset: 0, background: p.secondary, clipPath: 'polygon(0 0,100% 0,100% 34%,0 58%)' })} />
      <div style={abs({ inset: 0, background: p.primary, clipPath: 'polygon(0 58%,100% 34%,100% 40%,0 64%)' })} />
      <div style={abs({ inset: 0, background: p.tertiary, clipPath: 'polygon(0 88%,100% 70%,100% 78%,0 96%)' })} />
      <div style={abs({ inset: 0, backgroundImage: `radial-gradient(${p.ink} 30%, transparent 32%)`, backgroundSize: '22px 22px', opacity: 0.16, clipPath: 'polygon(0 0,100% 0,100% 34%,0 58%)' })} />
      <Tex id="fx-spray" fill={p.secondary} opacity={0.5} />
      <Grain fill="#fff" />
    </React.Fragment>
  ),
  'paint-sweep': (p) => (
    <React.Fragment>
      <div style={{ ...full, background: `radial-gradient(130% 130% at 20% 15%, ${p.primary}, ${p.ink} 74%)` }} />
      <div style={abs({ left: -80, top: 360, width: 1260, height: 360, background: p.secondary, filter: 'url(#fx-swipe)', transform: 'rotate(-9deg)' })} />
      <div style={abs({ left: -80, top: 430, width: 1260, height: 120, background: p.tertiary, filter: 'url(#fx-swipe)', transform: 'rotate(-9deg)', opacity: 0.9 })} />
      <Tex id="fx-splatter" fill={p.secondary} opacity={0.85} transform="translate(-260px,-260px)" />
      <Tex id="fx-splatter2" fill={p.tertiary} opacity={0.8} transform="translate(300px,320px) rotate(90deg)" />
      <Tex id="fx-spray" fill={p.secondary} opacity={0.55} />
      <Grain fill="#fff" />
    </React.Fragment>
  ),
  'halftone-ramp': (p) => (
    <React.Fragment>
      <div style={{ ...full, background: `linear-gradient(145deg, ${p.secondary}, ${p.primary} 64%, ${p.ink})` }} />
      <div style={{ ...full, backgroundImage: `radial-gradient(${p.ink} 30%, transparent 32%)`, backgroundSize: '26px 26px', WebkitMaskImage: 'linear-gradient(145deg,#000,transparent 60%)', maskImage: 'linear-gradient(145deg,#000,transparent 60%)', opacity: 0.5 }} />
      <div style={{ ...full, backgroundImage: `radial-gradient(${p.secondary} 26%, transparent 28%)`, backgroundSize: '22px 22px', WebkitMaskImage: 'linear-gradient(325deg,#000,transparent 55%)', maskImage: 'linear-gradient(325deg,#000,transparent 55%)', opacity: 0.35 }} />
      <div style={abs({ left: 0, top: '50%', width: '100%', height: 3, background: p.tertiary, opacity: 0.9, transform: 'translateY(-50%) rotate(-6deg)' })} />
      <Grain fill="#fff" opacity={0.4} />
    </React.Fragment>
  ),
  'contour-rings': (p) => {
    const rings = [
      [1720, 0.45, 2, p.secondary], [1420, 0.55, 2, p.secondary], [1140, 0.65, 3, p.secondary],
      [880, 0.78, 3, p.secondary], [640, 1, 4, p.tertiary], [420, 0.9, 3, p.secondary],
    ]
    return (
      <React.Fragment>
        <div style={{ ...full, background: p.primary }} />
        <div style={abs({ left: 760, top: 820, transform: 'translate(-50%,-50%)' })}>
          {rings.map(([d, o, b, c], i) => (
            <div key={i} style={abs({ width: d, height: d, border: `${b}px solid ${c}`, borderRadius: '50%', left: -d / 2, top: -d / 2, opacity: o })} />
          ))}
          <div style={abs({ width: 220, height: 220, background: p.secondary, borderRadius: '50%', left: -110, top: -110, opacity: 0.9 })} />
        </div>
        <Tex id="fx-spray" fill={p.secondary} opacity={0.6} />
        <Grain fill="#fff" opacity={0.45} />
      </React.Fragment>
    )
  },
  'airbrush-glow': (p) => (
    <React.Fragment>
      <div style={{ ...full, background: p.ink }} />
      <div style={{ ...full, background: `radial-gradient(75% 75% at 74% 26%, ${p.secondary} 0%, transparent 60%)` }} />
      <div style={{ ...full, background: `radial-gradient(30% 30% at 74% 26%, ${p.tertiary} 0%, transparent 60%)` }} />
      <div style={{ ...full, background: 'radial-gradient(13% 13% at 74% 26%, #fff 0%, rgba(255,255,255,0) 70%)' }} />
      <Tex id="fx-spray" fill={p.secondary} opacity={0.78} />
      <Tex id="fx-spray" fill="#000" opacity={0.5} />
    </React.Fragment>
  ),
  'chevron-grit': (p) => (
    <React.Fragment>
      <div style={{ ...full, background: p.primary }} />
      <div style={abs({ inset: -60, background: `repeating-linear-gradient(-45deg, ${p.secondary} 0 64px, transparent 64px 150px)`, opacity: 0.9 })} />
      <div style={abs({ inset: -60, background: `repeating-linear-gradient(-45deg, ${p.tertiary} 0 10px, transparent 10px 150px)`, opacity: 0.8, transform: 'translateX(30px)' })} />
      <div style={abs({ left: '50%', top: '50%', width: 560, height: 560, transform: 'translate(-50%,-50%)', background: p.primary, boxShadow: '0 40px 120px rgba(0,0,0,.5)' })} />
      <Tex id="fx-grit" fill="#fff" opacity={0.5} blend="soft-light" />
      <Grain fill="#fff" />
    </React.Fragment>
  ),
  'drip-curtain': (p) => (
    <React.Fragment>
      <div style={{ ...full, background: p.ink }} />
      <div style={abs({ left: 0, top: 0, width: '100%', height: 230, background: p.secondary, filter: 'url(#fx-torn)', transform: 'scaleY(-1)' })} />
      <Drip x={90} y={200} w={12} h={280} c={p.secondary} />
      <Drip x={300} y={200} w={9} h={430} c={p.secondary} />
      <Drip x={540} y={200} w={11} h={330} c={p.tertiary} />
      <Drip x={770} y={200} w={8} h={520} c={p.secondary} />
      <Drip x={970} y={200} w={10} h={250} c={p.secondary} />
      <Tex id="fx-splatter" fill={p.secondary} opacity={0.8} transform="translateY(300px)" />
      <Grain fill="#fff" />
    </React.Fragment>
  ),
}

export function SocialBackground({ variant = 'ink-splatter', colors, size = 1080, height, radius = 0, className, style, children }) {
  const p = { ...DEFAULT_COLORS, ...(colors || {}) }
  const render = VARIANTS[variant] || VARIANTS['ink-splatter']
  const px = Number(size) || 1080
  // height defaults to size (the original square case). For a non-square
  // canvas (e.g. a 1920×1080 scorecard) the fixed 1080×1080 design space is
  // scaled up to *cover* the box (like CSS background-size:cover) and
  // centred, cropping the excess on whichever axis overflows, rather than
  // stretching it non-uniformly (which would turn every circle into an
  // ellipse and skew every diagonal).
  const py = Number(height) || px
  const scale = Math.max(px, py) / 1080
  const offsetX = (px - 1080 * scale) / 2
  const offsetY = (py - 1080 * scale) / 2
  return (
    <div className={className} style={{ position: 'relative', width: px, height: py, overflow: 'hidden', borderRadius: radius, background: '#000', ...style }}>
      {/* fixed 1080 design space, scaled to cover the requested box */}
      <div style={{ position: 'absolute', top: offsetY, left: offsetX, width: 1080, height: 1080, transformOrigin: 'top left', transform: `scale(${scale})` }}>
        {render(p)}
      </div>
      {/* content overlay in the caller's own coordinate space */}
      {children != null && <div style={{ position: 'absolute', inset: 0 }}>{children}</div>}
    </div>
  )
}

/**
 * Shared SVG turbulence filters. Render exactly ONE of these per page — every
 * <SocialBackground> references these by id.
 */
export function SocialBackgroundDefs() {
  return (
    <svg aria-hidden="true" width="0" height="0" style={{ position: 'absolute' }}>
      <defs>
        <filter id="fx-grain" x="0" y="0" width="100%" height="100%">
          <feTurbulence type="fractalNoise" baseFrequency="0.82" numOctaves="2" stitchTiles="stitch" result="n" />
          <feColorMatrix in="n" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0.7 0.7 0.7 0 0" />
        </filter>
        <filter id="fx-grit" x="-10%" y="-10%" width="120%" height="120%">
          <feTurbulence type="fractalNoise" baseFrequency="0.011" numOctaves="5" seed="8" stitchTiles="stitch" result="n" />
          <feColorMatrix in="n" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1.4 -0.25" />
        </filter>
        <filter id="fx-spray" x="-20%" y="-20%" width="140%" height="140%">
          <feTurbulence type="fractalNoise" baseFrequency="0.42" numOctaves="1" seed="11" result="n" />
          <feColorMatrix in="n" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 16 -7.6" result="d" />
          <feComposite in="d" in2="SourceGraphic" operator="in" />
        </filter>
        <filter id="fx-splatter" x="-30%" y="-30%" width="160%" height="160%">
          <feTurbulence type="fractalNoise" baseFrequency="0.016 0.021" numOctaves="3" seed="5" result="n" />
          <feColorMatrix in="n" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 22 -9.5" result="d" />
          <feComposite in="d" in2="SourceGraphic" operator="in" />
        </filter>
        <filter id="fx-splatter2" x="-30%" y="-30%" width="160%" height="160%">
          <feTurbulence type="fractalNoise" baseFrequency="0.021 0.028" numOctaves="3" seed="19" result="n" />
          <feColorMatrix in="n" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 24 -10.5" result="d" />
          <feComposite in="d" in2="SourceGraphic" operator="in" />
        </filter>
        <filter id="fx-torn" x="-8%" y="-8%" width="116%" height="116%">
          <feTurbulence type="fractalNoise" baseFrequency="0.009 0.05" numOctaves="3" seed="3" result="n" />
          <feDisplacementMap in="SourceGraphic" in2="n" scale="34" xChannelSelector="R" yChannelSelector="G" />
        </filter>
        <filter id="fx-rough" x="-8%" y="-8%" width="116%" height="116%">
          <feTurbulence type="fractalNoise" baseFrequency="0.09 0.11" numOctaves="2" seed="7" result="n" />
          <feDisplacementMap in="SourceGraphic" in2="n" scale="7" xChannelSelector="R" yChannelSelector="G" />
        </filter>
        <filter id="fx-swipe" x="-10%" y="-10%" width="120%" height="120%">
          <feTurbulence type="fractalNoise" baseFrequency="0.006 0.16" numOctaves="2" seed="14" result="n" />
          <feDisplacementMap in="SourceGraphic" in2="n" scale="46" xChannelSelector="R" yChannelSelector="G" />
        </filter>
      </defs>
    </svg>
  )
}

export default SocialBackground
