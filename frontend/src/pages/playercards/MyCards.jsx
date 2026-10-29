import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import CardGallery from '../../components/cards/CardGallery'
import ShareSheet from '../../components/cards/ShareSheet'
import PageHead, { ghostBtn } from './PageHead'
import { CardsSwitch } from './nav'
import { usePC } from './context'

export default function MyCards() {
  const { data, failed, mine, club, accent, display, sponsor, basePath } = usePC()
  const [share, setShare] = useState(null)
  const navigate = useNavigate()
  if (failed) return <div className="text-sm text-pb-faint" data-cards-failed>Your cards could not load. Reload to try again.</div>
  if (!data) return <div className="text-sm text-pb-faint" data-cards-loading>Loading your cards…</div>
  return (
    <div data-screen="book">
      <CardsSwitch />
      <PageHead title="My cards" sub="Everything you hold. Tap a card to turn it over, share it or put it in a swap."
        actions={mine && <button type="button" onClick={() => setShare(mine)} data-share-mine style={ghostBtn}>Share my card</button>} />
      <CardGallery cards={data.cards} totals={data.totals} club={club} accent={accent} display={display} sponsor={sponsor} meId={mine?.player_id}
        onShare={setShare} onOffer={(c) => navigate(`${basePath}/swaps/new`, { state: { give: c } })} />
      {share && <ShareSheet card={share} club={club} accent={accent} display={display} sponsor={sponsor} onClose={() => setShare(null)} />}
    </div>
  )
}
