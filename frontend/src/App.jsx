import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate, useLocation, useParams } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { ThemeProvider } from './contexts/ThemeContext'
import { ToastProvider } from './contexts/ToastContext'
import ErrorBoundary from './components/ErrorBoundary'
import ProtectedRoute from './components/ProtectedRoute'
import LoadingSpinner from './components/LoadingSpinner'
import Navbar from './components/Navbar'
import SponsorFooter from './components/SponsorFooter'
import ScrollToTop from './components/ScrollToTop'
import { usePageView } from './hooks/usePageView'

// Marketing pages have their own MarketingNav — suppress the global Navbar on those routes
const MARKETING_PATHS = ['/', '/features', '/pricing', '/compare', '/about', '/contact', '/faq', '/terms', '/privacy', '/blog']
function ConditionalNavbar() {
  const { pathname } = useLocation()
  const isMarketing = MARKETING_PATHS.includes(pathname) || pathname.startsWith('/blog/')
  return isMarketing ? null : <Navbar />
}

// Mounted once at the App root; pings /api/usage/event whenever the
// React Router location changes so we can see what people look at.
function PageViewBeacon() {
  usePageView()
  return null
}

// Marketing — kept synchronous for instant first paint
import Landing from './pages/marketing/Landing'
import Features from './pages/marketing/Features'
import Pricing from './pages/marketing/Pricing'
import Compare from './pages/marketing/Compare'
import About from './pages/marketing/About'
import Contact from './pages/marketing/Contact'
import Terms from './pages/marketing/Terms'
import Privacy from './pages/marketing/Privacy'
import FAQ from './pages/marketing/FAQ'
import Blog from './pages/marketing/Blog'
import BlogPost from './pages/marketing/BlogPost'

// Auth
import Login from './pages/Login'

// Admin — lazy loaded (behind auth, not needed on first paint)
const AdminDashboard = lazy(() => import('./pages/admin/AdminDashboard'))
const AdminPlayers = lazy(() => import('./pages/admin/AdminPlayers'))
const AdminGames = lazy(() => import('./pages/admin/AdminGames'))
const AdminSeasons = lazy(() => import('./pages/admin/AdminSeasons'))
const AdminSettings = lazy(() => import('./pages/admin/AdminSettings'))
const AdminAwards = lazy(() => import('./pages/admin/AdminAwards'))
const AdminAwardDefinitions = lazy(() => import('./pages/admin/AdminAwardDefinitions'))
const AdminMerge = lazy(() => import('./pages/admin/AdminMerge'))
const AdminFamilies = lazy(() => import('./pages/admin/AdminFamilies'))
const AdminGrades = lazy(() => import('./pages/admin/AdminGrades'))
const AdminSync = lazy(() => import('./pages/admin/AdminSync'))
const AdminPartnershipRecords = lazy(() => import('./pages/admin/AdminPartnershipRecords'))
const AdminManualEntries = lazy(() => import('./pages/admin/AdminManualEntries'))
const AdminMilestones = lazy(() => import('./pages/admin/AdminMilestones'))
const AdminActivityLog = lazy(() => import('./pages/admin/AdminActivityLog'))
const AdminChangelog = lazy(() => import('./pages/admin/AdminChangelog'))
const AdminUsage = lazy(() => import('./pages/admin/AdminUsage'))
const AdminUsers = lazy(() => import('./pages/admin/AdminUsers'))
const AdminReports = lazy(() => import('./pages/admin/AdminReports'))
const AdminFeesMembers = lazy(() => import('./pages/admin/AdminFeesMembers'))
const AdminFeeMemberDetail = lazy(() => import('./pages/admin/AdminFeeMemberDetail'))
const AdminFeeSchedule = lazy(() => import('./pages/admin/AdminFeeSchedule'))
const AdminFeePayments = lazy(() => import('./pages/admin/AdminFeePayments'))
const AdminFeePaymentImport = lazy(() => import('./pages/admin/AdminFeePaymentImport'))
const AdminFeeBulkPayment = lazy(() => import('./pages/admin/AdminFeeBulkPayment'))
const AdminFeeReports = lazy(() => import('./pages/admin/AdminFeeReports'))
const AdminSponsors = lazy(() => import('./pages/admin/AdminSponsors'))
const AdminSocialPost = lazy(() => import('./pages/admin/AdminSocialPost'))
const AdminYearbook = lazy(() => import('./pages/admin/AdminYearbook'))
const AdminYearbookDetail = lazy(() => import('./pages/admin/AdminYearbookDetail'))
const SuperClubs = lazy(() => import('./pages/admin/SuperClubs'))
const SuperUsers = lazy(() => import('./pages/admin/SuperUsers'))
const BetterSelectHome = lazy(() => import('./pages/admin/betterselect/BetterSelectHome'))
const BsFixtures = lazy(() => import('./pages/admin/betterselect/AdminFixtures'))
const BsTeams = lazy(() => import('./pages/admin/betterselect/AdminTeams'))
const BsAvailability = lazy(() => import('./pages/admin/betterselect/AdminAvailability'))
const BsSelection = lazy(() => import('./pages/admin/betterselect/AdminSelection'))
const BsSelectionOverview = lazy(() => import('./pages/admin/betterselect/AdminSelectionOverview'))

// Public club pages — lazy loaded (not needed for marketing visitors)
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Players = lazy(() => import('./pages/Players'))
const PlayerProfile = lazy(() => import('./pages/PlayerProfile'))
const PlayerComparison = lazy(() => import('./pages/PlayerComparison'))
const Leaderboard = lazy(() => import('./pages/Leaderboard'))
const Records = lazy(() => import('./pages/Records'))
const ShareCard = lazy(() => import('./pages/ShareCard'))
const StatLab = lazy(() => import('./pages/StatLab'))
const Yearbook = lazy(() => import('./pages/Yearbook'))
const GamesPage = lazy(() => import('./pages/GamesPage'))
const MatchScorecard = lazy(() => import('./pages/MatchScorecard'))
const MatchOverview = lazy(() => import('./pages/MatchOverview'))
const PlayHQScorecard = lazy(() => import('./pages/PlayHQScorecard'))
const ClubInactive = lazy(() => import('./pages/ClubInactive'))
const Onboard = lazy(() => import('./pages/Onboard'))

const PageLoader = () => (
  <div className="flex justify-center py-24">
    <LoadingSpinner size="lg" />
  </div>
)

// Legacy /:clubSlug/dashboard → canonical /:clubSlug
function DashboardRedirect() {
  const { clubSlug } = useParams()
  return <Navigate to={`/${clubSlug}`} replace />
}

export default function App() {
  return (
    <AuthProvider>
      <ThemeProvider>
      <ToastProvider>
      <ErrorBoundary>
      <div className="min-h-screen bg-pb-bg">
        <ScrollToTop />
        <PageViewBeacon />
        <ConditionalNavbar />
        <Suspense fallback={<PageLoader />}>
        <Routes>
          {/* Marketing site */}
          <Route path="/" element={<Landing />} />
          <Route path="/features" element={<Features />} />
          <Route path="/pricing" element={<Pricing />} />
          <Route path="/compare" element={<Compare />} />
          <Route path="/about" element={<About />} />
          <Route path="/contact" element={<Contact />} />
          <Route path="/faq" element={<FAQ />} />
          <Route path="/terms" element={<Terms />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/blog" element={<Blog />} />
          <Route path="/blog/:slug" element={<BlogPost />} />

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
          <Route path="/admin/families" element={<ProtectedRoute><AdminFamilies /></ProtectedRoute>} />
          <Route path="/admin/grades" element={<ProtectedRoute><AdminGrades /></ProtectedRoute>} />
          <Route path="/admin/sync" element={<ProtectedRoute><AdminSync /></ProtectedRoute>} />
          <Route path="/admin/partnerships" element={<ProtectedRoute><AdminPartnershipRecords /></ProtectedRoute>} />
          <Route path="/admin/manual-entries" element={<ProtectedRoute><AdminManualEntries /></ProtectedRoute>} />
          <Route path="/admin/milestones" element={<ProtectedRoute><AdminMilestones /></ProtectedRoute>} />
          <Route path="/admin/activity" element={<ProtectedRoute><AdminActivityLog /></ProtectedRoute>} />
          <Route path="/admin/changelog" element={<ProtectedRoute><AdminChangelog /></ProtectedRoute>} />
          <Route path="/admin/users" element={<ProtectedRoute><AdminUsers /></ProtectedRoute>} />
          <Route path="/admin/reports" element={<ProtectedRoute><AdminReports /></ProtectedRoute>} />
          <Route path="/admin/fees" element={<ProtectedRoute><AdminFeesMembers /></ProtectedRoute>} />
          <Route path="/admin/fees/schedule" element={<ProtectedRoute><AdminFeeSchedule /></ProtectedRoute>} />
          <Route path="/admin/fees/payments" element={<ProtectedRoute><AdminFeePayments /></ProtectedRoute>} />
          <Route path="/admin/fees/payments/import" element={<ProtectedRoute><AdminFeePaymentImport /></ProtectedRoute>} />
          <Route path="/admin/fees/payments/bulk" element={<ProtectedRoute><AdminFeeBulkPayment /></ProtectedRoute>} />
          <Route path="/admin/fees/reports" element={<ProtectedRoute><AdminFeeReports /></ProtectedRoute>} />
          <Route path="/admin/fees/member/:memberId" element={<ProtectedRoute><AdminFeeMemberDetail /></ProtectedRoute>} />
          <Route path="/admin/settings" element={<ProtectedRoute><AdminSettings /></ProtectedRoute>} />
          <Route path="/admin/sponsors" element={<ProtectedRoute><AdminSponsors /></ProtectedRoute>} />
          <Route path="/admin/social-post" element={<ProtectedRoute><AdminSocialPost /></ProtectedRoute>} />
          <Route path="/admin/yearbook" element={<ProtectedRoute><AdminYearbook /></ProtectedRoute>} />
          <Route path="/admin/yearbook/:seasonId" element={<ProtectedRoute><AdminYearbookDetail /></ProtectedRoute>} />
          <Route path="/admin/usage" element={<ProtectedRoute requireRole="super_admin"><AdminUsage /></ProtectedRoute>} />
          <Route path="/admin/super/clubs" element={<ProtectedRoute requireRole="super_admin"><SuperClubs /></ProtectedRoute>} />
          <Route path="/admin/super/users" element={<ProtectedRoute requireRole="super_admin"><SuperUsers /></ProtectedRoute>} />

          {/* BetterSelect module */}
          <Route path="/admin/betterselect" element={<ProtectedRoute><BetterSelectHome /></ProtectedRoute>} />
          <Route path="/admin/betterselect/fixtures" element={<ProtectedRoute><BsFixtures /></ProtectedRoute>} />
          <Route path="/admin/betterselect/teams" element={<ProtectedRoute><BsTeams /></ProtectedRoute>} />
          <Route path="/admin/betterselect/availability" element={<ProtectedRoute><BsAvailability /></ProtectedRoute>} />
          <Route path="/admin/betterselect/selection" element={<ProtectedRoute><BsSelectionOverview /></ProtectedRoute>} />
          <Route path="/admin/betterselect/select/:fixtureId" element={<ProtectedRoute><BsSelection /></ProtectedRoute>} />

          {/* Game-level pages */}
          <Route path="/games/:gameId" element={<MatchScorecard />} />
          <Route path="/match/:gameId" element={<MatchOverview />} />
          <Route path="/scorecards/:gameId" element={<PlayHQScorecard />} />

          {/* Public club pages (slug-based) */}
          <Route path="/club-inactive" element={<ClubInactive />} />
          <Route path="/onboard" element={<ProtectedRoute><Onboard /></ProtectedRoute>} />
          <Route path="/:clubSlug" element={<Dashboard />} />
          <Route path="/:clubSlug/dashboard" element={<DashboardRedirect />} />
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
        </Suspense>
        <SponsorFooter />
      </div>
      </ErrorBoundary>
      </ToastProvider>
      </ThemeProvider>
    </AuthProvider>
  )
}
