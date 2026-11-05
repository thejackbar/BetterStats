import { useMemo } from 'react'
import Aurora from './Aurora'

// A soft Aurora glow along the top of a hero. It starts below the fixed nav and
// is masked to fade out before the copy, because at full strength it washes the
// text out. Pass `colorStops` for a custom ramp, or `accent` (a hex colour) to
// get a single-hue aurora: a deeper tone, the colour itself, then a lighter one.

const mix = (a, b, t) => {
  const p = (h) => [1, 3, 5].map((i) => parseInt(h.replace('#', '').slice(i - 1, i + 1), 16))
  const [ar, ag, ab] = p(a)
  const [br, bg, bb] = p(b)
  const c = (x, y) => Math.round(x + (y - x) * t).toString(16).padStart(2, '0')
  return `#${c(ar, br)}${c(ag, bg)}${c(ab, bb)}`
}

export function accentStops(hex) {
  return [mix(hex, '#0a0d14', 0.45), hex, mix(hex, '#ffffff', 0.3)]
}

export default function AuroraHero({ colorStops, accent }) {
  const stops = useMemo(
    () => colorStops || (accent ? accentStops(accent) : ['#16c784', '#3b82f6', '#16c784']),
    [colorStops, accent],
  )
  return (
    <div
      className="absolute inset-x-0 top-16 h-[460px] sm:h-[540px] z-0 pointer-events-none"
      style={{
        WebkitMaskImage: 'linear-gradient(to bottom, #000 35%, transparent 100%)',
        maskImage: 'linear-gradient(to bottom, #000 35%, transparent 100%)',
      }}
    >
      <Aurora
        colorStops={stops}
        amplitude={0.9}
        blend={0.55}
        speed={0.6}
        height={0.32}
        glow={0.45}
        brightness={0.75}
        opacity={0.8}
        layers={2}
        dpr={1.5}
      />
    </div>
  )
}
