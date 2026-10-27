// Player Cards as a page of its own, at /playerdash/:token/cards. It is reached from the player's dashboard, uses the
// same PIN sign in (PublicAvailability checks that before this renders), and has a sidebar, a rail or a bottom bar
// depending on the screen. The page is drawn in the club's colours on a dark ground whatever the site theme, the way the
// cards and the pack opening already are.
import { Route, Routes, Navigate } from 'react-router-dom'
import AllSummary from '../../components/cards/AllSummary'
import PackOpening from '../../components/cards/PackOpening'
import { api } from '../../lib/api'
import { PlayerCardsProvider, usePC } from './context'
import { BottomBar, Rail, Sidebar } from './nav'
import Home from './Home'
import MyCards from './MyCards'
import ClubCards from './ClubCards'
import Packs from './Packs'
import Swaps from './Swaps'
import NewSwap from './NewSwap'
import HowItWorks from './HowItWorks'
import Wishlist from './Wishlist'
import Spares from './Spares'
import CardPage from './CardPage'
import Settings from './Settings'
import Sets from './Sets'
import SetPage from './SetPage'
import Showcase from './Showcase'

function Overlays() {
  const { token, club, accent, display, sponsor, pack, owned, packsCount, closePack, nextPack, allResult, setAllResult, load } = usePC()
  return (
    <>
      {pack && <PackOpening key={pack.id} pack={pack} packsLeft={Math.max(0, packsCount - 1)} club={club} accent={accent} display={display} sponsor={sponsor} owned={owned}
        openPack={() => api.availPublicOpenCard(token, pack.id)} onClose={closePack} onNext={nextPack} />}
      {allResult && <AllSummary result={allResult} club={club} accent={accent} display={display} sponsor={sponsor} onClose={() => { setAllResult(null); load() }} />}
    </>
  )
}

function Shell() {
  const { club, accent, basePath, base } = usePC()
  return (
    <div data-theme="dark" data-cards-page className="min-h-screen bg-pb-bg text-pb-text" style={{ '--pb-accent': accent }}>
      {/* A phone has no sidebar, so the page names itself and the way back at the top. */}
      <header className="md:hidden flex items-center justify-between gap-3 px-4 py-3 border-b pb-hairline">
        <span className="font-display font-bold truncate">{club?.name || 'Player Cards'}</span>
        <span className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faint">Player Cards</span>
      </header>
      <div className="flex">
        <Sidebar />
        <Rail />
        <main data-cards-main className="flex-1 min-w-0 px-4 py-5 md:px-6 lg:px-8 lg:py-8 pb-28 md:pb-10">
          <div className="max-w-[1100px] mx-auto">
            <Routes>
              <Route path="cards" element={<Home />} />
              <Route path="cards/book" element={<MyCards />} />
              <Route path="cards/club" element={<ClubCards />} />
              <Route path="cards/packs" element={<Packs />} />
              <Route path="cards/swaps" element={<Swaps tab="asking" />} />
              <Route path="cards/swaps/sent" element={<Swaps tab="sent" />} />
              <Route path="cards/swaps/history" element={<Swaps tab="history" />} />
              <Route path="cards/swaps/new" element={<NewSwap />} />
              <Route path="cards/wishlist" element={<Wishlist />} />
              <Route path="cards/spares" element={<Spares />} />
              <Route path="cards/card/:key" element={<CardPage />} />
              <Route path="cards/showcase" element={<Showcase />} />
              <Route path="cards/sets" element={<Sets tab="sets" />} />
              <Route path="cards/sets/board" element={<Sets tab="board" />} />
              <Route path="cards/sets/week" element={<Sets tab="week" />} />
              <Route path="cards/set/:key" element={<SetPage />} />
              <Route path="cards/how" element={<HowItWorks />} />
              <Route path="cards/settings" element={<Settings />} />
              <Route path="cards/*" element={<Navigate to={basePath} replace />} />
              <Route path="*" element={<Navigate to={base} replace />} />
            </Routes>
          </div>
        </main>
      </div>
      <BottomBar />
      <Overlays />
    </div>
  )
}

export default function PlayerCardsApp({ token, club, me, onSwitch }) {
  return (
    <PlayerCardsProvider token={token} club={club} me={me} onSwitch={onSwitch}>
      <Shell />
    </PlayerCardsProvider>
  )
}
