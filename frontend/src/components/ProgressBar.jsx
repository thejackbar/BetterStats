import { useEffect, useState } from 'react'

/* App-wide loading progress.

   Two flavours:
   - <ProgressBar pct={...}> — a determinate bar for loads where we KNOW the
     real completeness (e.g. a sync run reporting games processed / total).
   - <LoadingBar expectedMs={...}> — for plain fetches with no server-side
     progress signal. Shows a percentage that climbs quickly at first then
     crawls toward 94% on a curve scaled by the call's typical duration, so
     the number keeps moving without ever claiming "done". Mount it only
     while loading — it disappears with the placeholder when data lands.

   Both theme off the pb-* CSS vars, so they look right on the admin shell
   and inside BetterIQ's violet accent override alike. */

export function useLoadingProgress(expectedMs = 6000) {
  const [pct, setPct] = useState(0)
  useEffect(() => {
    const started = performance.now()
    const id = setInterval(() => {
      const t = (performance.now() - started) / Math.max(expectedMs, 500)
      setPct(Math.min(94, Math.round(94 * (1 - Math.exp(-1.6 * t)))))
    }, 150)
    return () => clearInterval(id)
  }, [expectedMs])
  return pct
}

export function ProgressBar({
  pct,
  label,
  labelClassName = 'text-pb-faint text-[12.5px]',
  color = 'var(--pb-accent)',
  h = 6,
  className = '',
}) {
  const clamped = Math.max(0, Math.min(100, Math.round(Number(pct) || 0)))
  return (
    <div
      className={className}
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={typeof label === 'string' ? label : undefined}
    >
      {label != null && label !== '' && <div className={`mb-1.5 ${labelClassName}`}>{label}</div>}
      <div className="flex items-center gap-2.5">
        <div className="flex-1 rounded-full overflow-hidden" style={{ height: h, background: 'var(--pb-surface2)' }}>
          <div style={{ height: '100%', width: `${clamped}%`, background: color, borderRadius: 99, transition: 'width .4s ease' }} />
        </div>
        <span className="font-mono tabular-nums text-[11px] shrink-0 text-right" style={{ color: 'var(--pb-faint)', minWidth: 36 }}>
          {clamped}%
        </span>
      </div>
    </div>
  )
}

export default function LoadingBar({ expectedMs = 6000, ...barProps }) {
  const pct = useLoadingProgress(expectedMs)
  return <ProgressBar pct={pct} {...barProps} />
}
