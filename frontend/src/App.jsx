import { Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'
import Home from './pages/Home'
import Dashboard from './pages/Dashboard'
import Players from './pages/Players'
import PlayerProfile from './pages/PlayerProfile'
import PlayerComparison from './pages/PlayerComparison'
import Leaderboard from './pages/Leaderboard'
import MatchScorecard from './pages/MatchScorecard'
import MatchOverview from './pages/MatchOverview'
import PlayHQScorecard from './pages/PlayHQScorecard'
import Records from './pages/Records'
import Onboard from './pages/Onboard'
import ShareCard from './pages/ShareCard'
import MergeTools from './pages/MergeTools'

export default function App() {
  return (
    <div className="min-h-screen bg-navy-950">
      <Navbar />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/dashboard/:orgId" element={<Dashboard />} />
        <Route path="/players/:orgId/list" element={<Players />} />
        <Route path="/players/:playerId" element={<PlayerProfile />} />
        <Route path="/players/:playerId/share" element={<ShareCard />} />
        <Route path="/compare/:orgId" element={<PlayerComparison />} />
        <Route path="/leaderboard/:orgId" element={<Leaderboard />} />
        <Route path="/games/:gameId" element={<MatchScorecard />} />
        <Route path="/match/:gameId" element={<MatchOverview />} />
        <Route path="/scorecards/:gameId" element={<PlayHQScorecard />} />
        <Route path="/records/:orgId" element={<Records />} />
        <Route path="/onboard" element={<Onboard />} />
        <Route path="/merge/:orgId" element={<MergeTools />} />
      </Routes>
    </div>
  )
}
