import { useState } from 'react'
import Reveal from './Reveal'
import { COMPARISON_3WAY, COMPETITORS, FORM_URL } from '../../data/marketing'

/**
 * 3-way comparison: PlayHQ / CricketStatz / BetterStats.
 *
 * Cell shapes:
 *   true / false         → green tick / grey dash
 *   'partial' / 'manual' → amber pill
 *   '—'                  → literal em dash
 *   {monthly, annual}    → driven by the billing toggle
 *   any other string     → literal text
 *
 * Pass `heading` / `sub` as React nodes to override the defaults.
 */

function Cell({ value, accent, billing }) {
  // billing-toggle cell
  if (value && typeof value === 'object' && (value.monthly || value.annual)) {
    return (
      <span className={`text-sm font-semibold ${accent ? 'text-accent' : 'text-pb-text'}`}>
        {billing === 'annual' ? value.annual : value.monthly}
      </span>
    )
  }
  if (typeof value === 'string') {
    if (value === 'partial') {
      return (
        <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-500/10 border border-amber-500/30">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
          <span className="text-[11px] font-medium text-amber-300">Partial</span>
        </div>
      )
    }
    if (value === 'manual') {
      return (
        <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-500/10 border border-amber-500/30">
          <span className="text-[11px] font-medium text-amber-300">Manual</span>
        </div>
      )
    }
    if (value === '—') {
      return <span className="text-sm text-pb-faint">—</span>
    }
    return <span className={`text-sm font-semibold ${accent ? 'text-accent' : 'text-pb-text'}`}>{value}</span>
  }
  if (value === true) {
    return (
      <span className={`inline-flex items-center justify-center w-7 h-7 rounded-full ${accent ? 'bg-accent text-navy-950' : 'bg-accent/15 text-accent'} font-bold`}>
        ✓
      </span>
    )
  }
  return (
    <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-pb-surface2 text-pb-faintest font-bold">
      ✗
    </span>
  )
}

export default function Comparison3Way({ id = 'compare', heading, sub, showCTA = true }) {
  const [billing, setBilling] = useState('annual')
  return (
    <section id={id} className="px-4 sm:px-6 lg:px-10 py-24 border-t pb-hairline-t">
      <div className="max-w-[1200px] mx-auto">
        <Reveal>
          <div className="text-center mb-10">
            <p className="pill-neutral inline-flex mb-5">Compare</p>
            <h2 className="font-display font-bold text-4xl md:text-6xl mb-4 tracking-tight leading-[1.05]">
              {heading || (<>You have options. <span className="gradient-text">Here's the honest version.</span></>)}
            </h2>
            <p className="text-lg text-pb-dim max-w-2xl mx-auto">
              {sub || 'PlayHQ is the system of record. CricketStatz is the old-school stats package. BetterStats is the layer that turns both into a club site your members will use.'}
            </p>
          </div>
        </Reveal>

        <Reveal>
          <div className="flex justify-center mb-6">
            <div className="tabbar">
              <button className={billing === 'monthly' ? 'active' : ''} onClick={() => setBilling('monthly')}>Monthly cost</button>
              <button className={billing === 'annual' ? 'active' : ''} onClick={() => setBilling('annual')}>Annual cost</button>
            </div>
          </div>
        </Reveal>

        <Reveal>
          <div className="surface overflow-hidden">
            {/* Header row */}
            <div className="grid grid-cols-[2fr,1fr,1fr,1.1fr] md:grid-cols-[2.2fr,1fr,1fr,1.2fr] gap-2 px-4 lg:px-7 py-5 border-b pb-hairline bg-black/20">
              <div />
              <div className="text-center">
                <p className="text-[10px] font-mono uppercase tracking-wide3 text-pb-faint mb-1">Incumbent</p>
                <p className="text-base font-bold">{COMPETITORS.playhq.name}</p>
                <p className="hidden md:block text-[11px] text-pb-dim mt-0.5">{COMPETITORS.playhq.tag}</p>
              </div>
              <div className="text-center">
                <p className="text-[10px] font-mono uppercase tracking-wide3 text-pb-faint mb-1">Competitor</p>
                <p className="text-base font-bold">{COMPETITORS.cstatz.name}</p>
                <p className="hidden md:block text-[11px] text-pb-dim mt-0.5">{COMPETITORS.cstatz.tag}</p>
              </div>
              <div className="text-center bg-accent/10 -m-2 p-2 rounded-lg border border-accent/30 relative">
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-2 py-0.5 bg-accent text-navy-950 rounded-full text-[9px] font-bold uppercase tracking-wide3 whitespace-nowrap">★ Recommended</div>
                <p className="text-[10px] font-mono uppercase tracking-wide3 text-accent mb-1 mt-1">Us</p>
                <p className="text-base font-bold">{COMPETITORS.us.name}</p>
                <p className="hidden md:block text-[11px] text-pb-dim mt-0.5">{COMPETITORS.us.tag}</p>
              </div>
            </div>

            {/* Sections */}
            {COMPARISON_3WAY.map((section, sIdx) => (
              <div key={section.section}>
                <div className="px-4 lg:px-7 py-3 bg-pb-surface2/30 border-b pb-hairline">
                  <p className="text-[10px] font-mono uppercase tracking-wide3 font-semibold text-accent">
                    {String(sIdx + 1).padStart(2, '0')} · {section.section}
                  </p>
                </div>
                {section.rows.map((row, rIdx) => (
                  <div
                    key={row.feature}
                    className={`grid grid-cols-[2fr,1fr,1fr,1.1fr] md:grid-cols-[2.2fr,1fr,1fr,1.2fr] gap-2 px-4 lg:px-7 py-4 items-center ${
                      rIdx < section.rows.length - 1 || sIdx < COMPARISON_3WAY.length - 1
                        ? 'border-b pb-hairline'
                        : ''
                    } hover:bg-pb-surface2/40 transition-colors`}
                  >
                    <div>
                      <p className="text-sm font-medium">{row.feature}</p>
                      {row.tip && (
                        <p className="text-xs text-pb-faint mt-0.5 leading-snug">{row.tip}</p>
                      )}
                    </div>
                    <div className="flex justify-center"><Cell value={row.playhq} billing={billing} /></div>
                    <div className="flex justify-center"><Cell value={row.cstatz} billing={billing} /></div>
                    <div className="flex justify-center bg-accent/[0.04]"><Cell value={row.us} accent billing={billing} /></div>
                  </div>
                ))}
              </div>
            ))}

            {/* Footer summary */}
            <div className="px-4 lg:px-7 py-6 bg-black/20 border-t pb-hairline">
              <div className="grid grid-cols-[2fr,1fr,1fr,1.1fr] md:grid-cols-[2.2fr,1fr,1fr,1.2fr] gap-2 items-center">
                <p className="text-sm text-pb-dim">Best for</p>
                <p className="text-xs text-center text-pb-faint">Live scoring on Saturday</p>
                <p className="text-xs text-center text-pb-faint">Solo stats hobbyist</p>
                <p className="text-xs text-center text-accent font-semibold">Whole-club platform</p>
              </div>
            </div>
          </div>
        </Reveal>

        {showCTA && (
          <Reveal>
            <div className="text-center mt-10">
              <p className="text-base text-pb-dim mb-5 max-w-2xl mx-auto">
                You don't have to pick one — BetterStats syncs <span className="text-pb-text">on top of</span> PlayHQ. Keep scoring there. Just give your club somewhere worth showing it off.
              </p>
              <a href={FORM_URL} target="_blank" rel="noopener noreferrer" className="cta-primary">Get your club on BetterStats →</a>
            </div>
          </Reveal>
        )}
      </div>
    </section>
  )
}
