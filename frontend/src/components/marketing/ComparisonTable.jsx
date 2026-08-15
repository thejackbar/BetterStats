import { useState } from 'react'
import { Link } from 'react-router-dom'
import Reveal from './Reveal'

/**
 * Generic, data-driven comparison table.
 *
 * Drives every "vs" section on the marketing site from a COMPARISONS entry
 * (see src/data/marketing.js). Renders N competitor columns plus the
 * highlighted "us" column, so the same component powers the whole-platform
 * comparison on the home page and the per-module comparisons (BetterStats,
 * BetterSocials, BetterSelect, BetterAdmin).
 *
 * Cell shapes (per column key, read from row.values[col.key]):
 *   true / false         → green tick / grey cross
 *   'partial' / 'manual' → amber pill
 *   '—'                  → literal em dash
 *   {monthly, annual}    → driven by the billing toggle
 *   any other string     → literal text
 */

function Cell({ value, accent, billing }) {
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
    if (value === '—') return <span className="text-sm text-pb-faint">—</span>
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

export default function ComparisonTable({
  comparison,
  id = 'compare',
  heading,
  sub,
  showCTA = true,
  showBillingToggle = false,
}) {
  const [billing, setBilling] = useState('annual')
  if (!comparison) return null

  const cols = comparison.columns || []
  // CSS grid: feature column (wide) + one fr per data column, with "us" a touch wider.
  const gridCols = `minmax(0,2.1fr) ${cols.map((c) => (c.us ? '1.2fr' : '1fr')).join(' ')}`

  const cta = comparison.cta

  return (
    <section id={id} className="px-4 sm:px-6 lg:px-10 py-24 border-t pb-hairline-t">
      <div className="max-w-[1200px] mx-auto">
        <Reveal>
          <div className="text-center mb-10">
            <p className="pill-neutral inline-flex mb-5">{comparison.eyebrow || 'Compare'}</p>
            <h2 className="font-display font-bold text-4xl md:text-6xl mb-4 tracking-tight leading-[1.05]">
              {heading || comparison.heading}
            </h2>
            <p className="text-lg text-pb-dim max-w-2xl mx-auto">{sub || comparison.sub}</p>
          </div>
        </Reveal>

        {showBillingToggle && (
          <Reveal>
            <div className="flex justify-center mb-6">
              <div className="tabbar">
                <button className={billing === 'monthly' ? 'active' : ''} onClick={() => setBilling('monthly')}>Monthly cost</button>
                <button className={billing === 'annual' ? 'active' : ''} onClick={() => setBilling('annual')}>Annual cost</button>
              </div>
            </div>
          </Reveal>
        )}

        <Reveal>
          <div className="surface overflow-hidden">
            {/* Header row */}
            <div className="grid gap-2 px-4 lg:px-7 py-5 border-b pb-hairline bg-black/20 items-end" style={{ gridTemplateColumns: gridCols }}>
              <div />
              {cols.map((c) => (
                c.us ? (
                  <div key={c.key} className="text-center bg-accent/10 -m-2 p-2 rounded-lg border border-accent/30 relative">
                    <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-2 py-0.5 bg-accent text-navy-950 rounded-full text-[9px] font-bold uppercase tracking-wide3 whitespace-nowrap">★ Recommended</div>
                    <p className="text-[10px] font-mono uppercase tracking-wide3 text-accent mb-1 mt-1">Us</p>
                    <p className="text-base font-bold leading-tight">{c.name}</p>
                    {c.tag && <p className="hidden md:block text-[11px] text-pb-dim mt-0.5">{c.tag}</p>}
                  </div>
                ) : (
                  <div key={c.key} className="text-center">
                    {c.label && <p className="text-[10px] font-mono uppercase tracking-wide3 text-pb-faint mb-1">{c.label}</p>}
                    <p className="text-base font-bold leading-tight">{c.name}</p>
                    {c.tag && <p className="hidden md:block text-[11px] text-pb-dim mt-0.5">{c.tag}</p>}
                  </div>
                )
              ))}
            </div>

            {/* Sections */}
            {(comparison.sections || []).map((section, sIdx) => (
              <div key={section.section}>
                <div className="px-4 lg:px-7 py-3 bg-pb-surface2/30 border-b pb-hairline">
                  <p className="text-[10px] font-mono uppercase tracking-wide3 font-semibold text-accent">
                    {String(sIdx + 1).padStart(2, '0')} · {section.section}
                  </p>
                </div>
                {section.rows.map((row, rIdx) => (
                  <div
                    key={row.feature}
                    className={`grid gap-2 px-4 lg:px-7 py-4 items-center ${
                      rIdx < section.rows.length - 1 || sIdx < comparison.sections.length - 1
                        ? 'border-b pb-hairline'
                        : ''
                    } hover:bg-pb-surface2/40 transition-colors`}
                    style={{ gridTemplateColumns: gridCols }}
                  >
                    <div>
                      <p className="text-sm font-medium">{row.feature}</p>
                      {row.tip && <p className="text-xs text-pb-faint mt-0.5 leading-snug">{row.tip}</p>}
                    </div>
                    {cols.map((c) => (
                      <div key={c.key} className={`flex justify-center ${c.us ? 'bg-accent/[0.04]' : ''}`}>
                        <Cell value={row.values?.[c.key]} accent={c.us} billing={billing} />
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            ))}

            {/* Footer summary (optional "Best for" row) */}
            {comparison.bestFor && (
              <div className="px-4 lg:px-7 py-6 bg-black/20 border-t pb-hairline">
                <div className="grid gap-2 items-center" style={{ gridTemplateColumns: gridCols }}>
                  <p className="text-sm text-pb-dim">Best for</p>
                  {cols.map((c) => (
                    <p key={c.key} className={`text-xs text-center ${c.us ? 'text-accent font-semibold' : 'text-pb-faint'}`}>
                      {comparison.bestFor[c.key] || '—'}
                    </p>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Reveal>

        {showCTA && cta && (
          <Reveal>
            <div className="text-center mt-10">
              <p className="text-base text-pb-dim mb-5 max-w-2xl mx-auto">{cta.line}</p>
              <Link to={cta.to} className="cta-primary">{cta.label}</Link>
            </div>
          </Reveal>
        )}
      </div>
    </section>
  )
}
