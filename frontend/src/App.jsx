import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { ThemeProvider } from './contexts/ThemeContext'
import ProtectedRoute from './components/ProtectedRoute'

// Marketing
import Landing from './pages/marketing/Landing'
import Features from './pages/marketing/Features'
import Pricing from './pages/marketing/Pricing'
import About from './pages/marketing/About'
import Contact from './pages/marketing/Contact'
import Terms from './pages/marketing/Terms'
import Privacy from './pages/marketing/Privacy'
import FAQ from './pages/marketing/FAQ'

// Auth
import Login from './pages/Login'

// Admin
import AdminDashboard from './pages/admin/AdminDashboard'
import AdminPlayers from './pages/admin/AdminPlayers'
import AdminGames from './pages/admin/AdminGames'
import AdminSeasons from './pages/admin/AdminSeasons'
import AdminSettings from './pages/admin/AdminSettings'
import SuperClubs from './pages/admin/SuperClubs'
import SuperUsers from './pages/admin/SuperUsers'

// Admin wrappers for existing tools
import AdminAwards from './pages/admin/AdminAwards'
import AdminAwardDefinitions from './pages/admin/AdminAwardDefinitions'
import AdminMerge from './pages/admin/AdminMerge'
import AdminGrades from './pages/admin/AdminGrades'
import AdminSync from './pages/admin/AdminSync'
import AdminPartnershipRecords from './pages/admin/AdminPartnershipRecords'
import AdminMilestones from './pages/admin/AdminMilestones'

// Public club pages (slug-based)
import Dashboard from './pages/Dashboard'
import Players from './pages/Players'
import PlayerProfile from './pages/PlayerProfile'
import PlayerComparison from './pages/PlayerComparison'
import Leaderboard from './pages/Leaderboard'
import Records from './pages/Records'
import ShareCard from './pages/ShareCard'
import StatLab from './pages/StatLab'
import Yearbook from './pages/Yearbook'
import AdminYearbook from './pages/admin/AdminYearbook'
import AdminYearbookDetail from './pages/admin/AdminYearbookDetail'

import GamesPage from './pages/GamesPage'

// Game pages (game-level, UUID-based — no slug needed)
import MatchScorecard from './pages/MatchScorecard'
import MatchOverview from './pages/MatchOverview'
import PlayHQScorecard from './pages/PlayHQScorecard'

// Misc
import ClubInactive from './pages/ClubInactive'
import Onboard from './pages/Onboard'
import Navbar from './components/Navbar'
import SponsorFooter from './components/SponsorFooter'
import AdminSponsors from './pages/admin/AdminSponsors'
import AdminSocialPost from './pages/admin/AdminSocialPost'

export default function App() {
  return (
    <AuthProvider>
      <ThemeProvider>
      <div className="min-h-screen bg-pb-bg">
        <Navbar />
      <Routes>
        {/* Marketing site */}
        <Route path="/" element={<Landing />} />
        <Route path="/features" element={<Features />} />
        <Route path="/pricing" element={<Pricing />} />
        <Route path="/about" element={<About />} />
        <Route path="/contact" element={<Contact />} />
        <Route path="/faq" element={<FAQ />} />
        <Route path="/terms" element={<Terms />} />
        <Route path="/privacy" element={<Privacy />} />

        {/* Auth */}
        <Route path="/login" element={<Login />} />

        {/* Admin (protected) */}
        <Route path="/admin" element={<ProtectedRoute><AdminDashboard /></ProtectedRoute>} />
        <Route path="/admin/players" element={<ProtectedRoute><AdminPlayers /></ProtectedRoute>} />
        <Route path="/admin/games" element={<ProtectedRoute><AdminGames /></ProtectedRoute>} />
        <Route path="/admin/seasons" element={<ProtectedRoute><AdminSeasons /></ProtectedRoute>} />
        <Route path="/admin/awards" element={<ProtectedRoute><AdminAwards /></ProtectedRoute>} />
        <Route path="/admin/award-definitions" element={<ProtectedRoute><AdminAwardDefinitions /></ProtectedRoute>} />
        <Route path="/admin/merge" element={<ProtectedRoute><AdminMerge /></ProtectedRoute>} />
        <Route path="/admin/grades" element={<ProtectedRoute><AdminGrades /></ProtectedRoute>} />
        <Route path="/admin/sync" element={<ProtectedRoute><AdminSync /></ProtectedRoute>} />
        <Route path="/admin/partnerships" element={<ProtectedRoute><AdminPartnershipRecords /></ProtectedRoute>} />
        <Route path="/admin/milestones" element={<ProtectedRoute><AdminMilestones /></ProtectedRoute>} />
        <Route path="/admin/settings" element={<ProtectedRoute><AdminSettings /></ProtectedRoute>} />
        <Route path="/admin/sponsors" element={<ProtectedRoute><AdminSponsors /></ProtectedRoute>} />
        <Route path="/admin/social-post" element={<ProtectedRoute><AdminSocialPost /></ProtectedRoute>} />
        <Route path="/admin/yearbook" element={<ProtectedRoute><AdminYearbook /></ProtectedRoute>} />
        <Route path="/admin/yearbook/:seasonId" element={<ProtectedRoute><AdminYearbookDetail /></ProtectedRoute>} />
        <Route path="/admin/super/clubs" element={<ProtectedRoute requireRole="super_admin"><SuperClubs /></ProtectedRoute>} />
        <Route path="/admin/super/users" element={<ProtectedRoute requireRole="super_admin"><SuperUsers /></ProtectedRoute>} />

        {/* Game-level pages (UUID in URL, club not needed in path) */}
        <Route path="/games/:gameId" element={<MatchScorecard />} />
        <Route path="/match/:gameId" element={<MatchOverview />} />
        <Route path="/scorecards/:gameId" element={<PlayHQScorecard />} />

        {/* Public club pages (slug-based) */}
        <Route path="/club-inactive" element={<ClubInactive />} />
        <Route path="/onboard" element={<ProtectedRoute><Onboard /></ProtectedRoute>} />
        <Route path="/:clubSlug/dashboard" element={<Dashboard />} />
        <Route path="/:clubSlug/players" element={<Players />} />
        <Route path="/:clubSlug/compare" element={<PlayerComparison />} />
        <Route path="/:clubSlug/leaderboard" element={<Leaderboard />} />
        <Route path="/:clubSlug/records" element={<Records />} />
        <Route path="/:clubSlug/statlab" element={<StatLab />} />
        <Route path="/:clubSlug/statlab/r/:reportSlug" element={<StatLab />} />
        <Route path="/:clubSlug/games" element={<GamesPage />} />
        <Route path="/:clubSlug/yearbook" element={<Yearbook />} />
        <Route path="/:clubSlug/yearbook/:seasonSlug" element={<Yearbook />} />
        <Route path="/players/:playerId" element={<PlayerProfile />} />
        <Route path="/players/:playerId/share" element={<ShareCard />} />

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <SponsorFooter />
      </div>
      </ThemeProvider>
    </AuthProvider>
  )
}
