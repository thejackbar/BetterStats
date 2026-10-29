// "Player Cards" on the player's dashboard: a small card with their own card, the packs waiting and the swaps asking, and
// one button to the Player Cards page, where everything else lives. It reads its own data so the dashboard's first paint
// does not wait on it, and keeps the section header's "packs to open" count honest through `onReady`.
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useClubSponsors } from '../../lib/useClubSponsors'
import { cardSponsor, onColor } from '../../components/PlayerTradingCard'
import { CARD_H, CARD_W, CardView, ScaledCard } from '../../components/cards/CardFaces'
import { useCardStyle } from '../../components/cards/useCardStyle'

const MONO = "'JetBrains Mono', monospace"

export default function CardsSummary({ token, club, swapsWaiting = 0, onReady }) {
  const [data, setData] = useState(null)
  const [failed, setFailed] = useState(false)
  const { accent, display } = useCardStyle(club)
  const sponsor = cardSponsor(useClubSponsors(club?.slug), 'player_cards')
  useEffect(() => {
    let alive = true
    api.availPublicCards(token).then((d) => { if (alive) { setData(d); onReady?.(d.packs.length) } }).catch(() => { if (alive) setFailed(true) })
    return () => { alive = false }
  }, [token, onReady])
  if (failed) return <div className="text-sm text-pb-faint" data-cards-failed>Your cards could not load. Reload to try again.</div>
  if (!data) return <div className="text-sm text-pb-faint" data-cards-loading>Loading your cards…</div>
  const mine = data.cards.find((c) => c.mine)
  const packs = data.packs.length
  return (
    <div data-cards-module className="flex flex-wrap items-center gap-5">
      {mine && (
        <div data-my-card style={{ flex: 'none', width: 120, height: 120 * (CARD_H / CARD_W) }}>
          <ScaledCard width={120}><CardView card={mine} club={club} accent={accent} display={display} sponsor={sponsor} holo={false} /></ScaledCard>
        </div>
      )}
      <div className="flex-1 min-w-[200px]">
        <div data-packs-ready style={{ font: `800 22px/1.1 ${display}`, textTransform: 'uppercase', letterSpacing: 1 }}>
          {packs > 0 ? `${packs} ${packs === 1 ? 'pack' : 'packs'} to open` : 'No packs to open'}
        </div>
        <div className="text-sm text-pb-dim mt-1.5">
          {swapsWaiting > 0 ? `${swapsWaiting} ${swapsWaiting === 1 ? 'swap' : 'swaps'} asking you.` : 'Swap, search the whole club, and open your packs.'}
        </div>
        <Link to={`/playerdash/${token}/cards`} data-open-cards-page className="inline-block mt-3" style={{ padding: '11px 18px', borderRadius: 12, background: accent, color: onColor(accent), font: `700 12px ${MONO}`, letterSpacing: 1.4, textTransform: 'uppercase', textDecoration: 'none' }}>Open Player Cards</Link>
      </div>
    </div>
  )
}
