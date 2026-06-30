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
import FaviconManager from './components/FaviconManager'
import PaidVisitorCTA from './components/PaidVisitorCTA'
import { usePageView } from './hooks/usePageView'

// Marketing pages have their own MarketingNav — suppress the global Navbar on those routes
const MARKETING_PATHS = ['/', '/overview', '/features', '/pricing', '/compare', '/modules', '/about', '/contact', '/faq', '/terms', '/privacy', '/blog']
function ConditionalNavbar() {
  const { pathname } = useLocation()
  const isMarketing =
    MARKETING_PATHS.includes(pathname) || pathname.startsWith('/blog/') || pathname.startsWith('/modules/')
  // The public self-service availability page is a standalone, white-labelled
  // mobile page — it renders its own minimal header, no club nav.
  const isStandalone = pathname.startsWith('/avail/') || pathname.startsWith('/fantasy/')
  return (isMarketing || isStandalone) ? null : <Navbar />
}

// Mounted once at the App root; pings /api/usage/event whenever the
// React Router location changes so we can see what people look at.
function PageViewBeacon() {
  usePageView()
  return null
}

// Marketing — kept synchronous for instant first paint
import Landing from './pages/marketing/Landing'
import Overview from './pages/marketing/Overview'
import Features from './pages/marketing/Features'
import Pricing from './pages/marketing/Pricing'
import Compare from './pages/marketing/Compare'
import Modules from './pages/marketing/Modules'
import ModuleDetail from './pages/marketing/ModuleDetail'
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
const AdminScorecardUpload = lazy(() => import('./pages/admin/AdminScorecardUpload'))
const AdminImport = lazy(() => import('./pages/admin/AdminImport'))
const AdminPlayerImport = lazy(() => import('./pages/admin/AdminPlayerImport'))
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
const BetterMerchHome = lazy(() => import('./pages/admin/bettermerch/BetterMerchHome'))
const MerchStock = lazy(() => import('./pages/admin/bettermerch/MerchStock'))
const MerchAssets = lazy(() => import('./pages/admin/bettermerch/MerchAssets'))
const MerchActivity = lazy(() => import('./pages/admin/bettermerch/MerchActivity'))
const MerchReports = lazy(() => import('./pages/admin/bettermerch/MerchReports'))
const MerchSquare = lazy(() => import('./pages/admin/bettermerch/MerchSquare'))
const AdminSponsors = lazy(() => import('./pages/admin/AdminSponsors'))
const AdminSocialPost = lazy(() => import('./pages/admin/AdminSocialPost'))
const AdminYearbook = lazy(() => import('./pages/admin/AdminYearbook'))
const AdminYearbookDetail = lazy(() => import('./pages/admin/AdminYearbookDetail'))
const SuperOverview = lazy(() => import('./pages/admin/SuperOverview'))
const SuperClubs = lazy(() => import('./pages/admin/SuperClubs'))
const SuperUsers = lazy(() => import('./pages/admin/SuperUsers'))
const SuperOnboarding = lazy(() => import('./pages/admin/SuperOnboarding'))
const SuperMarketing = lazy(() => import('./pages/admin/SuperMarketing'))
const SuperAnnounce = lazy(() => import('./pages/admin/SuperAnnounce'))
const KlubproMigration = lazy(() => import('./pages/admin/klubpro/KlubproMigration'))
const BetterSelectHome = lazy(() => import('./pages/admin/betterselect/BetterSelectHome'))
const BsPlayers = lazy(() => import('./pages/admin/betterselect/BetterSelectPlayers'))
const BsFixtures = lazy(() => import('./pages/admin/betterselect/AdminFixtures'))
const BsTeams = lazy(() => import('./pages/admin/betterselect/AdminTeams'))
const BsAvailability = lazy(() => import('./pages/admin/betterselect/AdminAvailability'))
const BsSelection = lazy(() => import('./pages/admin/betterselect/AdminSelection'))
const BsSelectionOverview = lazy(() => import('./pages/admin/betterselect/AdminSelectionOverview'))
const BsLadders = lazy(() => import('./pages/admin/betterselect/AdminLadders'))
const BsNets = lazy(() => import('./pages/admin/betterselect/Nets'))
const BsNetSession = lazy(() => import('./pages/admin/betterselect/NetSession'))
const BetterIQHome = lazy(() => import('./pages/admin/betteriq/BetterIQHome'))
const IqOpposition = lazy(() => import('./pages/admin/betteriq/OppositionScout'))
const IqOppositionPlayer = lazy(() => import('./pages/admin/betteriq/OppositionPlayer'))
const IqSelection = lazy(() => import('./pages/admin/betteriq/SelectionAnalysis'))
const IqTrends = lazy(() => import('./pages/admin/betteriq/PlayerTrends'))
const IqTeammates = lazy(() => import('./pages/admin/betteriq/Teammates'))
const IqPlayerHub = lazy(() => import('./pages/admin/betteriq/PlayerHub'))
const IqAsk = lazy(() => import('./pages/admin/betteriq/AskIQ'))
const IqTeam = lazy(() => import('./pages/admin/betteriq/TeamAnalysis'))
const IqReview = lazy(() => import('./pages/admin/betteriq/MatchReview'))
const IqPreview = lazy(() => import('./pages/admin/betteriq/MatchPreview'))
const IqCheatSheet = lazy(() => import('./pages/admin/betteriq/CheatSheet'))
// BetterFantasyCricket (admin surface)
const FantasyHome = lazy(() => import('./pages/admin/fantasy/FantasyHome'))
const FantasySettings = lazy(() => import('./pages/admin/fantasy/FantasySettings'))
const FantasyScoring = lazy(() => import('./pages/admin/fantasy/FantasyScoring'))
const FantasyPool = lazy(() => import('./pages/admin/fantasy/FantasyPool'))
const FantasyPlayers = lazy(() => import('./pages/admin/fantasy/FantasyPlayers'))
const FantasyLeagues = lazy(() => import('./pages/admin/fantasy/FantasyLeagues'))

// BetterAdmin umbrella (BetterFees + BetterComms + future BetterMerch)
const BetterAdminHome = lazy(() => import('./pages/admin/BetterAdminHome'))
// BetterSocials umbrella (Website + Post Designer)
const BetterSocialsHome = lazy(() => import('./pages/admin/BetterSocialsHome'))
const CommsCampaigns = lazy(() => import('./pages/admin/bettercomms/CommsCampaigns'))
const CommsCompose = lazy(() => import('./pages/admin/bettercomms/CommsCompose'))
const CommsContacts = lazy(() => import('./pages/admin/bettercomms/CommsContacts'))
const CommsSegments = lazy(() => import('./pages/admin/bettercomms/CommsSegments'))
const CommsLists = lazy(() => import('./pages/admin/bettercomms/CommsLists'))
const CommsTemplates = lazy(() => import('./pages/admin/bettercomms/CommsTemplates'))
const CommsSettings = lazy(() => import('./pages/admin/bettercomms/CommsSettings'))

// Public club pages — lazy loaded (not needed for marketing visitors)
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Players = lazy(() => import('./pages/Players'))
const PlayerProfile = lazy(() => import('./pages/PlayerProfile'))
const PlayerComparison = lazy(() => import('./pages/PlayerComparison'))
const Leaderboard = lazy(() => import('./pages/Leaderboard'))
const Records = lazy(() => import('./pages/Records'))
const Ladders = lazy(() => import('./pages/Ladders'))
const ShareCard = lazy(() => import('./pages/ShareCard'))
const StatLab = lazy(() => import('./pages/StatLab'))
const Yearbook = lazy(() => import('./pages/Yearbook'))
const GamesPage = lazy(() => import('./pages/GamesPage'))
const MatchScorecard = lazy(() => import('./pages/MatchScorecard'))
const ClubInactive = lazy(() => import('./pages/ClubInactive'))
const Onboard = lazy(() => import('./pages/Onboard'))

// Front-end Website (public club site) — lazy loaded
const WebsiteHome = lazy(() => import('./pages/website/WebsiteHome'))
const WebsiteNews = lazy(() => import('./pages/website/WebsiteNews'))
const WebsiteArticle = lazy(() => import('./pages/website/WebsiteArticle'))
const WebsitePage = lazy(() => import('./pages/website/WebsitePage'))
const WebsiteHonours = lazy(() => import('./pages/website/WebsiteHonours'))
const WebsiteCommittee = lazy(() => import('./pages/website/WebsiteCommittee'))
const WebsiteGallery = lazy(() => import('./pages/website/WebsiteGallery'))
const AdminWebsite = lazy(() => import('./pages/admin/website/AdminWebsite'))

// Public, login-free self-service availability (BetterSelect magic link + PIN)
const PublicAvailability = lazy(() => import('./pages/PublicAvailability'))
// Public, login-free fantasy play (BetterFantasyCricket magic link + PIN)
const PublicFantasy = lazy(() => import('./pages/PublicFantasy'))

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
        <PaidVisitorCTA />
        <FaviconManager />
        <ConditionalNavbar />
        <Suspense fallback={<PageLoader />}>
        <Routes>
          {/* Marketing site */}
          <Route path="/" element={<Landing />} />
          <Route path="/overview" element={<Overview />} />
          <Route path="/features" element={<Features />} />
          <Route path="/pricing" element={<Pricing />} />
          <Route path="/compare" element={<Compare />} />
          <Route path="/modules" element={<Modules />} />
          {/* Legacy module slug → BetterAdmin umbrella */}
          <Route path="/modules/betterfees" element={<Navigate to="/modules/betteradmin" replace />} />
          <Route path="/modules/:slug" element={<ModuleDetail />} />
          <Route path="/about" element={<About />} />
          <Route path="/contact" element={<Contact />} />
          <Route path="/faq" element={<FAQ />} />
          <Route path="/terms" element={<Terms />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/blog" element={<Blog />} />
          <Route path="/blog/:slug" element={<BlogPost />} />

          {/* Auth */}
          <Route path="/login" element={<Login />} />

          {/* Public self-service availability (no login — magic link + PIN) */}
          <Route path="/avail/:token" element={<PublicAvailability />} />
          {/* Public fantasy play (no login — magic link + PIN) */}
          <Route path="/fantasy/:token" element={<PublicFantasy />} />

          {/* Admin (protected) */}
          <Route path="/admin" element={<ProtectedRoute><AdminDashboard /></ProtectedRoute>} />
          <Route path="/admin/players" element={<ProtectedRoute><AdminPlayers /></ProtectedRoute>} />
          <Route path="/admin/players/import" element={<ProtectedRoute><AdminPlayerImport /></ProtectedRoute>} />
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
          <Route path="/admin/upload-scorecard" element={<ProtectedRoute><AdminScorecardUpload /></ProtectedRoute>} />
          <Route path="/admin/import" element={<ProtectedRoute><AdminImport /></ProtectedRoute>} />
          <Route path="/admin/milestones" element={<ProtectedRoute><AdminMilestones /></ProtectedRoute>} />
          <Route path="/admin/activity" element={<ProtectedRoute><AdminActivityLog /></ProtectedRoute>} />
          <Route path="/admin/changelog" element={<ProtectedRoute><AdminChangelog /></ProtectedRoute>} />
          <Route path="/admin/users" element={<ProtectedRoute><AdminUsers /></ProtectedRoute>} />
          <Route path="/admin/reports" element={<ProtectedRoute><AdminReports /></ProtectedRoute>} />
          <Route path="/admin/fees" element={<ProtectedRoute requireModule="fees"><AdminFeesMembers /></ProtectedRoute>} />
          <Route path="/admin/fees/schedule" element={<ProtectedRoute requireModule="fees"><AdminFeeSchedule /></ProtectedRoute>} />
          <Route path="/admin/fees/payments" element={<ProtectedRoute requireModule="fees"><AdminFeePayments /></ProtectedRoute>} />
          <Route path="/admin/fees/payments/import" element={<ProtectedRoute requireModule="fees"><AdminFeePaymentImport /></ProtectedRoute>} />
          <Route path="/admin/fees/payments/bulk" element={<ProtectedRoute requireModule="fees"><AdminFeeBulkPayment /></ProtectedRoute>} />
          <Route path="/admin/fees/reports" element={<ProtectedRoute requireModule="fees"><AdminFeeReports /></ProtectedRoute>} />
          <Route path="/admin/fees/member/:memberId" element={<ProtectedRoute requireModule="fees"><AdminFeeMemberDetail /></ProtectedRoute>} />
          <Route path="/admin/merch" element={<ProtectedRoute requireModule="merch"><BetterMerchHome /></ProtectedRoute>} />
          <Route path="/admin/merch/stock" element={<ProtectedRoute requireModule="merch"><MerchStock /></ProtectedRoute>} />
          <Route path="/admin/merch/equipment" element={<ProtectedRoute requireModule="merch"><MerchAssets /></ProtectedRoute>} />
          <Route path="/admin/merch/activity" element={<ProtectedRoute requireModule="merch"><MerchActivity /></ProtectedRoute>} />
          <Route path="/admin/merch/reports" element={<ProtectedRoute requireModule="merch"><MerchReports /></ProtectedRoute>} />
          <Route path="/admin/merch/square" element={<ProtectedRoute requireModule="merch"><MerchSquare /></ProtectedRoute>} />
          <Route path="/admin/fantasy" element={<ProtectedRoute requireModule="fantasy"><FantasyHome /></ProtectedRoute>} />
          <Route path="/admin/fantasy/settings" element={<ProtectedRoute requireModule="fantasy"><FantasySettings /></ProtectedRoute>} />
          <Route path="/admin/fantasy/scoring" element={<ProtectedRoute requireModule="fantasy"><FantasyScoring /></ProtectedRoute>} />
          <Route path="/admin/fantasy/pool" element={<ProtectedRoute requireModule="fantasy"><FantasyPool /></ProtectedRoute>} />
          <Route path="/admin/fantasy/players" element={<ProtectedRoute requireModule="fantasy"><FantasyPlayers /></ProtectedRoute>} />
          <Route path="/admin/fantasy/leagues" element={<ProtectedRoute requireModule="fantasy"><FantasyLeagues /></ProtectedRoute>} />
          <Route path="/admin/settings" element={<ProtectedRoute><AdminSettings /></ProtectedRoute>} />
          <Route path="/admin/sponsors" element={<ProtectedRoute><AdminSponsors /></ProtectedRoute>} />
          <Route path="/admin/website" element={<ProtectedRoute><AdminWebsite /></ProtectedRoute>} />
          <Route path="/admin/social-post" element={<ProtectedRoute requireModule="socials"><AdminSocialPost /></ProtectedRoute>} />
          <Route path="/admin/yearbook" element={<ProtectedRoute><AdminYearbook /></ProtectedRoute>} />
          <Route path="/admin/yearbook/:seasonId" element={<ProtectedRoute><AdminYearbookDetail /></ProtectedRoute>} />
          <Route path="/admin/usage" element={<ProtectedRoute requireRole="super_admin"><AdminUsage /></ProtectedRoute>} />
          <Route path="/admin/super" element={<ProtectedRoute requireRole="super_admin"><SuperOverview /></ProtectedRoute>} />
          <Route path="/admin/super/clubs" element={<ProtectedRoute requireRole="super_admin"><SuperClubs /></ProtectedRoute>} />
          <Route path="/admin/super/users" element={<ProtectedRoute requireRole="super_admin"><SuperUsers /></ProtectedRoute>} />
          <Route path="/admin/super/onboarding" element={<ProtectedRoute requireRole="super_admin"><SuperOnboarding /></ProtectedRoute>} />
          <Route path="/admin/super/marketing" element={<ProtectedRoute requireRole="super_admin"><SuperMarketing /></ProtectedRoute>} />
          <Route path="/admin/super/announce" element={<ProtectedRoute requireRole="super_admin"><SuperAnnounce /></ProtectedRoute>} />
          <Route path="/admin/super/migration" element={<ProtectedRoute requireRole="super_admin"><KlubproMigration /></ProtectedRoute>} />

          {/* BetterSelect module */}
          <Route path="/admin/betterselect" element={<ProtectedRoute requireModule="select"><BetterSelectHome /></ProtectedRoute>} />
          <Route path="/admin/betterselect/players" element={<ProtectedRoute requireModule="select"><BsPlayers /></ProtectedRoute>} />
          <Route path="/admin/betterselect/fixtures" element={<ProtectedRoute requireModule="select"><BsFixtures /></ProtectedRoute>} />
          <Route path="/admin/betterselect/teams" element={<ProtectedRoute requireModule="select"><BsTeams /></ProtectedRoute>} />
          <Route path="/admin/betterselect/availability" element={<ProtectedRoute requireModule="select"><BsAvailability /></ProtectedRoute>} />
          <Route path="/admin/betterselect/selection" element={<ProtectedRoute requireModule="select"><BsSelectionOverview /></ProtectedRoute>} />
          <Route path="/admin/betterselect/select/:fixtureId" element={<ProtectedRoute requireModule="select"><BsSelection /></ProtectedRoute>} />
          <Route path="/admin/betterselect/nets" element={<ProtectedRoute requireModule="select"><BsNets /></ProtectedRoute>} />
          <Route path="/admin/betterselect/nets/:id" element={<ProtectedRoute requireModule="select"><BsNetSession /></ProtectedRoute>} />
          <Route path="/admin/betterselect/ladders" element={<ProtectedRoute requireModule="select"><BsLadders /></ProtectedRoute>} />

          {/* BetterIQ module */}
          <Route path="/admin/betteriq" element={<ProtectedRoute requireModule="iq"><BetterIQHome /></ProtectedRoute>} />
          <Route path="/admin/betteriq/opposition" element={<ProtectedRoute requireModule="iq"><IqOpposition /></ProtectedRoute>} />
          <Route path="/admin/betteriq/opposition/cheatsheet" element={<ProtectedRoute requireModule="iq"><IqCheatSheet /></ProtectedRoute>} />
          <Route path="/admin/betteriq/opposition-player" element={<ProtectedRoute requireModule="iq"><IqOppositionPlayer /></ProtectedRoute>} />
          <Route path="/admin/betteriq/selection" element={<ProtectedRoute requireModule="iq"><IqSelection /></ProtectedRoute>} />
          <Route path="/admin/betteriq/player" element={<ProtectedRoute requireModule="iq"><IqPlayerHub /></ProtectedRoute>} />
          <Route path="/admin/betteriq/ask" element={<ProtectedRoute requireModule="iq"><IqAsk /></ProtectedRoute>} />
          <Route path="/admin/betteriq/trends" element={<ProtectedRoute requireModule="iq"><IqTrends /></ProtectedRoute>} />
          <Route path="/admin/betteriq/teammates" element={<ProtectedRoute requireModule="iq"><IqTeammates /></ProtectedRoute>} />
          <Route path="/admin/betteriq/team" element={<ProtectedRoute requireModule="iq"><IqTeam /></ProtectedRoute>} />
          <Route path="/admin/betteriq/review" element={<ProtectedRoute requireModule="iq"><IqReview /></ProtectedRoute>} />
          <Route path="/admin/betteriq/preview" element={<ProtectedRoute requireModule="iq"><IqPreview /></ProtectedRoute>} />

          {/* BetterSocials umbrella (Website + Post Designer) — Website is Core, so the hub is open to all */}
          <Route path="/admin/bettersocials" element={<ProtectedRoute><BetterSocialsHome /></ProtectedRoute>} />

          {/* BetterAdmin umbrella + BetterComms (bulk email) */}
          <Route path="/admin/betteradmin" element={<ProtectedRoute><BetterAdminHome /></ProtectedRoute>} />
          <Route path="/admin/comms" element={<ProtectedRoute requireModule="comms"><CommsCampaigns /></ProtectedRoute>} />
          <Route path="/admin/comms/contacts" element={<ProtectedRoute requireModule="comms"><CommsContacts /></ProtectedRoute>} />
          <Route path="/admin/comms/segments" element={<ProtectedRoute requireModule="comms"><CommsSegments /></ProtectedRoute>} />
          <Route path="/admin/comms/lists" element={<ProtectedRoute requireModule="comms"><CommsLists /></ProtectedRoute>} />
          <Route path="/admin/comms/templates" element={<ProtectedRoute requireModule="comms"><CommsTemplates /></ProtectedRoute>} />
          <Route path="/admin/comms/settings" element={<ProtectedRoute requireModule="comms"><CommsSettings /></ProtectedRoute>} />
          <Route path="/admin/comms/:id" element={<ProtectedRoute requireModule="comms"><CommsCompose /></ProtectedRoute>} />

          {/* Game-level pages */}
          <Route path="/games/:gameId" element={<MatchScorecard />} />

          {/* Public club pages (slug-based) */}
          <Route path="/club-inactive" element={<ClubInactive />} />
          <Route path="/onboard" element={<ProtectedRoute><Onboard /></ProtectedRoute>} />
          <Route path="/:clubSlug" element={<Dashboard />} />
          <Route path="/:clubSlug/dashboard" element={<DashboardRedirect />} />
          <Route path="/:clubSlug/players" element={<Players />} />
          <Route path="/:clubSlug/compare" element={<PlayerComparison />} />
          <Route path="/:clubSlug/leaderboard" element={<Leaderboard />} />
          <Route path="/:clubSlug/records" element={<Records />} />
          <Route path="/:clubSlug/ladders" element={<Ladders />} />
          <Route path="/:clubSlug/statlab" element={<StatLab />} />
          <Route path="/:clubSlug/statlab/r/:reportSlug" element={<StatLab />} />
          <Route path="/:clubSlug/games" element={<GamesPage />} />
          <Route path="/:clubSlug/yearbook" element={<Yearbook />} />

          {/* Front-end Website (public club site) */}
          <Route path="/:clubSlug/website" element={<WebsiteHome />} />
          <Route path="/:clubSlug/website/news" element={<WebsiteNews />} />
          <Route path="/:clubSlug/website/news/:newsSlug" element={<WebsiteArticle />} />
          <Route path="/:clubSlug/website/page/:pageSlug" element={<WebsitePage />} />
          <Route path="/:clubSlug/website/honours" element={<WebsiteHonours />} />
          <Route path="/:clubSlug/website/committee" element={<WebsiteCommittee />} />
          <Route path="/:clubSlug/website/gallery" element={<WebsiteGallery />} />
          <Route path="/:clubSlug/website/gallery/:albumId" element={<WebsiteGallery />} />
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
