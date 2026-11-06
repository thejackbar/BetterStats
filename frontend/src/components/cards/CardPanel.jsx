// A card held up beside the book instead of over it: the card (turn it over), then whatever goes with it (who could swap
// one). Used on a wide screen so the book stays in view while you look at a card; a phone holds the card up over the book
// instead (the Viewer in CardGallery).
import { useEffect, useState } from 'react'
import FlipCard from '../FlipCard'
import { CARD_H, CARD_W, CardInfoBack, CardView } from './CardFaces'

const MONO = "'JetBrains Mono', monospace"

export default function CardPanel({ card, club, accent, display, sponsor, extra, onClose, width = 300 }) {
  const [flipped, setFlipped] = useState(false)
  useEffect(() => { setFlipped(false) }, [card.key])
  const k = width / CARD_W
  return (
    <aside data-card-panel aria-label={`${card.name} card`} className="rounded-2xl border pb-hairline bg-pb-surface p-4" style={{ position: 'sticky', top: 16 }}>
      <div className="flex justify-between items-center mb-3">
        <span className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint">Held up</span>
        <button type="button" onClick={onClose} aria-label="Put the card down" data-card-panel-close className="w-8 h-8 rounded-full border pb-hairline text-pb-dim hover:text-pb-text">✕</button>
      </div>
      <div style={{ width, height: CARD_H * k, margin: '0 auto' }}>
        <div style={{ width: CARD_W, height: CARD_H, transform: `scale(${k})`, transformOrigin: 'top left' }}>
          <FlipCard width={CARD_W} height={CARD_H} flipped={flipped} onFlip={() => setFlipped((f) => !f)}
            label={flipped ? 'Showing the details. Turn the card back over' : 'Showing the card. Turn it over for the details'}
            front={<CardView card={card} club={club} accent={accent} display={display} sponsor={sponsor} />}
            back={<CardInfoBack card={card} club={club} accent={accent} display={display} />} />
        </div>
      </div>
      <div className="text-center mt-2" style={{ font: `600 10px ${MONO}`, letterSpacing: 1.4, textTransform: 'uppercase', opacity: 0.65 }}>Tap the card to turn it over</div>
      {extra && <div className="mt-3">{extra}</div>}
    </aside>
  )
}
