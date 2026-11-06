import { onColor } from '../PlayerTradingCard'
import { CardView, ScaledCard } from './CardFaces'
import { TIERS } from './cardTheme'

const MONO = "'JetBrains Mono', monospace"

// What an "open all" found, without listing hundreds of cards.
export default function AllSummary({ result, club, accent, display, sponsor, onClose }) {
  return (
    <div role="dialog" aria-modal="true" aria-label="Packs opened" data-open-all-summary onClick={onClose}
      style={{ position: 'fixed', inset: 0, zIndex: 80, background: 'rgba(3,6,10,.9)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16, overflowY: 'auto' }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: '100%', maxWidth: 560, textAlign: 'center' }}>
        <div style={{ font: `800 italic 30px ${display}`, textTransform: 'uppercase', letterSpacing: 1.5 }}>{result.opened} {result.opened === 1 ? 'pack' : 'packs'} opened</div>
        <div style={{ font: `600 12px ${MONO}`, letterSpacing: 1.4, textTransform: 'uppercase', opacity: 0.8, margin: '6px 0 14px' }}>{result.total} cards added</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 8, marginBottom: 16 }}>
          {Object.entries(result.by_tier || {}).filter(([, n]) => n > 0).map(([t, n]) => (
            <span key={t} data-tier-count={t} style={{ padding: '4px 11px', borderRadius: 999, border: `1px solid ${(TIERS[t] || TIERS.common).glow}`, color: (TIERS[t] || TIERS.common).ink, font: `700 11px ${MONO}`, letterSpacing: 1, textTransform: 'uppercase' }}>{n} {(TIERS[t] || TIERS.common).label}</span>
          ))}
        </div>
        {(result.best || []).length > 0 && <div style={{ font: `700 11px ${MONO}`, letterSpacing: 1.6, textTransform: 'uppercase', opacity: 0.85, marginBottom: 8 }}>Best pulls</div>}
        <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 10 }}>
          {(result.best || []).map((c) => (
            <ScaledCard key={c.key} width={Math.min(104, (Math.min(window.innerWidth, 560) - 56) / 3)}>
              <CardView card={c} club={club} accent={accent} display={display} sponsor={sponsor} holo={false} />
            </ScaledCard>
          ))}
        </div>
        <button type="button" onClick={onClose} data-open-all-done style={{ marginTop: 18, padding: '12px 22px', borderRadius: 12, background: accent, color: onColor(accent), font: `700 12px ${MONO}`, letterSpacing: 1.4, textTransform: 'uppercase' }}>See my card book</button>
      </div>
    </div>
  )
}
