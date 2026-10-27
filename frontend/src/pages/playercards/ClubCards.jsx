import { useNavigate } from 'react-router-dom'
import CatalogueTab from '../../components/cards/CatalogueTab'
import PageHead from './PageHead'
import { CardsSwitch } from './nav'
import { usePC } from './context'

export default function ClubCards() {
  const { token, club, accent, display, sponsor, basePath } = usePC()
  const navigate = useNavigate()
  return (
    <div data-screen="club">
      <CardsSwitch />
      <PageHead title="Club cards" sub="Every card in the club, held or not. Hold one up to see who could swap you a copy." />
      <CatalogueTab intro={false} panel token={token} club={club} accent={accent} display={display} sponsor={sponsor}
        onAsk={(a) => navigate(`${basePath}/swaps/new`, { state: { ask: a } })} />
    </div>
  )
}
