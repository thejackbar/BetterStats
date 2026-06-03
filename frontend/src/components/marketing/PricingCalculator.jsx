import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  MODULES_MARKETING,
  TIER_INFO,
  requiredTierForModules,
  modulesInTier,
} from '../../data/modules-marketing'

/**
 * Module-picker → tier + price calculator.
 *
 * Pick the modules you want; we resolve the lowest tier that unlocks them all
 * (the same tier → module map the app enforces) and show the price. `billing`
 * ('monthly' | 'annual') is owned by the parent so it tracks the page toggle.
 */
export default function PricingCalculator({ billing = 'annual' }) {
  const [selected, setSelected] = useState(() => new Set())

  const toggle = (key) =>
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })

  const tierKey = requiredTierForModules([...selected])
  const tier = TIER_INFO[tierKey]
  const isAnnual = billing === 'annual'
  const price = isAnnual ? tier.annual : tier.monthly
  const included = modulesInTier(tierKey)

  return (
    <div className="surface p-6 lg:p-8">
      <div className="grid grid-cols-12 gap-8 items-start">
        {/* Picker */}
        <div className="col-span-12 lg:col-span-7">
          <p className="text-xs uppercase tracking-wide3 font-mono text-pb-faint mb-1">Build your plan</p>
          <h3 className="text-2xl font-bold mb-1.5">Pick the modules you want.</h3>
          <p className="text-sm text-pb-dim mb-6">
            Core (BetterStats) is always included. Choose your add-ons and we’ll show the tier you need.
          </p>

          <div className="space-y-2.5">
            {/* Core — always on, not toggleable */}
            <div className="flex items-center gap-3 p-3 rounded-xl border border-accent/30 bg-accent/[0.05]">
              <span className="w-9 h-9 rounded-lg bg-accent/15 border border-accent/40 flex items-center justify-center text-accent text-lg flex-shrink-0">◆</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold">BetterStats <span className="text-pb-faint font-normal">· Core</span></p>
                <p className="text-xs text-pb-dim">Reconciled stats + your public club site</p>
              </div>
              <span className="text-[11px] font-mono text-accent uppercase tracking-wide3">Always in</span>
            </div>

            {MODULES_MARKETING.map((m) => {
              const on = selected.has(m.key)
              return (
                <button
                  key={m.key}
                  type="button"
                  onClick={() => toggle(m.key)}
                  aria-pressed={on}
                  className={`w-full flex items-center gap-3 p-3 rounded-xl border text-left transition-colors ${
                    on ? 'border-accent/50 bg-accent/[0.07]' : 'border-pb-hairline hover:border-accent/30 bg-pb-surface2/20'
                  }`}
                >
                  <span
                    className={`w-9 h-9 rounded-lg flex items-center justify-center text-lg flex-shrink-0 border ${
                      on ? 'border-transparent text-navy-950' : 'border-pb-hairline text-pb-dim'
                    }`}
                    style={on ? { background: m.accent } : undefined}
                  >
                    {m.icon}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold">{m.name}</p>
                    <p className="text-xs text-pb-dim truncate">{m.tagline}</p>
                  </div>
                  <span className={`w-6 h-6 rounded-full flex items-center justify-center text-sm flex-shrink-0 ${on ? 'bg-accent text-navy-950' : 'bg-pb-surface2 text-pb-faint'}`}>
                    {on ? '✓' : '+'}
                  </span>
                </button>
              )
            })}
          </div>
        </div>

        {/* Result */}
        <div className="col-span-12 lg:col-span-5">
          <div className="lg:sticky lg:top-24 surface-strong p-6 text-center">
            <p className="text-xs uppercase tracking-wide3 font-mono text-pb-faint mb-2">You need the</p>
            <p className="text-3xl font-display font-bold mb-1 gradient-text">{tier.label}</p>
            <p className="text-sm text-pb-dim mb-5">{tier.tagline}</p>

            <div className="flex items-baseline justify-center gap-1.5 mb-1">
              <span className="text-5xl font-bold tabular-nums">${price}</span>
              <span className="text-sm text-pb-faint">/ {isAnnual ? 'year' : 'month'}</span>
            </div>
            <p className="text-[11px] text-pb-faint mb-5">AUD · flat rate, 1 team or 50</p>

            <div className="text-left border-t pb-hairline pt-4 mb-5">
              <p className="text-[10px] uppercase tracking-wide3 font-mono text-pb-faint mb-2.5">Includes</p>
              <ul className="space-y-1.5">
                <li className="flex items-center gap-2 text-sm"><span className="tick">✓</span>BetterStats <span className="text-pb-faint">(Core)</span></li>
                {included.map((m) => (
                  <li key={m.key} className="flex items-center gap-2 text-sm"><span className="tick">✓</span>{m.name}</li>
                ))}
              </ul>
            </div>

            <Link to="/contact" className="cta-primary w-full justify-center">Get the {tier.label} plan →</Link>
          </div>
        </div>
      </div>
    </div>
  )
}
