import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CORE, PRICED_MODULES, priceFor } from '../../data/pricing'
import { ModuleWordmark } from './../ModuleLockup'

/**
 * Modular plan builder. BetterStats is always in; tick the modules
 * you want and the annual price updates live, including the bundle discount
 * (two modules 5% off, all four 10%). This is the main way the Pricing page
 * shows what Better Cricket costs.
 */
export default function PricingCalculator() {
  const [selected, setSelected] = useState(() => new Set())

  const toggle = (key) =>
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })

  const { rate, discount, total, moduleCount, modules } = priceFor([...selected])

  return (
    <div className="surface p-6 lg:p-8">
      <div className="grid grid-cols-12 gap-8 items-start">
        {/* Picker */}
        <div className="col-span-12 lg:col-span-7">
          <p className="text-xs uppercase tracking-wide3 font-mono text-pb-faint mb-1">Build your plan</p>
          <h3 className="text-2xl font-bold mb-1.5">Pick the modules you want.</h3>
          <p className="text-sm text-pb-dim mb-6">
            BetterStats is always included. Add any modules and the price updates as you go.
            Take any two for 5% off, or all four for 10%.
          </p>

          <div className="space-y-2.5">
            {/* Core — always on, not toggleable */}
            <div className="flex items-center gap-3 p-3 rounded-xl border border-accent/30 bg-accent/[0.05]">
              <img src={CORE.logo} alt="" className="w-9 h-9 rounded-lg flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold"><ModuleWordmark name="BetterStats" accent={CORE.accent} /> <span className="text-pb-faint font-normal">· Core</span></p>
                <p className="text-xs text-pb-dim">{CORE.blurb}</p>
              </div>
              <span className="text-sm font-semibold tabular-nums mr-1">${CORE.price}</span>
              <span className="text-[11px] font-mono text-accent uppercase tracking-wide3">In</span>
            </div>

            {PRICED_MODULES.map((m) => {
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
                  <img
                    src={m.logo}
                    alt=""
                    className={`w-9 h-9 rounded-lg flex-shrink-0 transition-all ${on ? '' : 'grayscale opacity-60'}`}
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold"><ModuleWordmark name={m.name} accent={m.accent} /></p>
                    <p className="text-xs text-pb-dim truncate">{m.blurb}</p>
                  </div>
                  <span className="text-sm font-semibold tabular-nums mr-1">${m.price}</span>
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
          <div className="lg:sticky lg:top-24 surface-strong p-6">
            <p className="text-xs uppercase tracking-wide3 font-mono text-pb-faint mb-2 text-center">Your plan</p>
            <div className="flex items-baseline justify-center gap-1.5 mb-1">
              <span className="text-5xl font-bold tabular-nums">${total}</span>
              <span className="text-sm text-pb-faint">/ year</span>
            </div>
            <p className="text-[11px] text-pb-faint text-center mb-5">AUD · flat rate, 1 team or 50</p>

            <div className="text-left border-t pb-hairline pt-4 mb-4 space-y-1.5 text-sm">
              <div className="flex justify-between">
                <span className="text-pb-dim">BetterStats <span className="text-pb-faint">(Core)</span></span>
                <span className="tabular-nums">${CORE.price}</span>
              </div>
              {modules.map((m) => (
                <div key={m.key} className="flex justify-between">
                  <span className="text-pb-dim">{m.name}</span>
                  <span className="tabular-nums">${m.price}</span>
                </div>
              ))}
              {discount > 0 && (
                <div className="flex justify-between text-accent">
                  <span>Bundle discount ({Math.round(rate * 100)}%)</span>
                  <span className="tabular-nums">-${discount}</span>
                </div>
              )}
              <div className="flex justify-between font-bold border-t pb-hairline pt-2 mt-2">
                <span>Total / year</span>
                <span className="tabular-nums">${total}</span>
              </div>
            </div>

            {moduleCount < 2 && (
              <p className="text-[11px] text-pb-faint text-center mb-4">Add another module to unlock 5% off.</p>
            )}
            {moduleCount >= 2 && moduleCount < 4 && (
              <p className="text-[11px] text-accent text-center mb-4">5% bundle discount applied. Add all four for 10%.</p>
            )}
            {moduleCount === 4 && (
              <p className="text-[11px] text-accent text-center mb-4">Everything in, 10% off.</p>
            )}

            <Link to="/contact" className="cta-primary w-full justify-center">Get this plan →</Link>
          </div>
        </div>
      </div>
    </div>
  )
}
