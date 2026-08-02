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
import ClubCTABar from './components/ClubCTABar'
import { usePageView } from './hooks/usePageView'
import { useHeartbeat } from './hooks/useHeartbeat'
import { MARKETING_PATHS, isMarketingPath } from './lib/marketingPaths'

// Marketing pages have their own MarketingNav — suppress the global Navbar on those routes.
// Also the reference list for ClubCTABar (which BetterCricket pages vs. club public
// pages get the "get your club on BetterCricket" bar shown to every visitor).
export { MARKETING_PATHS, isMarketingPath }
function ConditionalNavbar() {
  const { pathname } = useLocation()
  const isMarketing = isMarketingPath(pathname)
  // The public self-service availability page is a standalone, white-labelled
  // mobile page — it renders its own minimal header, no club nav. The BetterPosts
  // editor is a full-viewport takeover with its own header, so suppress the club
  // nav there too.
  const isStandalone = pathname.startsWith('/avail/') || pathname.startsWith('/vote/') || pathname.startsWith('/fantasy/') || pathname.startsWith('/events/') || pathname.startsWith('/portal/') || pathname.startsWith('/shop/') || pathname.startsWith('/admin/social-post')
  return (isMarketing || isStandalone) ? null : <Navbar />
}

// Mounted once at the App root; pings /api/usage/event whenever the
// React Router location changes so we can see what people look at.
function PageViewBeacon() {
  usePageView()
  return null
}

// Mounted alongside PageViewBeacon; keeps pinging /api/usage/heartbeat every
// ~25s while the tab is open and visible, so "Active now" on the Usage page
// reflects someone actually having a page open rather than a recent nav.
function HeartbeatBeacon() {
  useHeartbeat()
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
import Trial from './pages/marketing/Trial'
import Terms from './pages/marketing/Terms'
import Privacy from './pages/marketing/Privacy'
import FAQ from './pages/marketing/FAQ'
import Blog from './pages/marketing/Blog'
import BlogPost from './pages/marketing/BlogPost'

// Auth
import Login from './pages/Login'

// Admin — lazy loaded (behind auth, not needed on first paint)
const AdminDashboard = lazy(() => import('./pages/admin/AdminDashboard'))
const BetterStatsHome = lazy(() => import('./pages/admin/BetterStatsHome'))
const BetterClubManagerHome = lazy(() => import('./pages/admin/BetterClubManagerHome'))
const SetupWizard = lazy(() => import('./pages/admin/setup/SetupWizard'))
const AdminPlayers = lazy(() => import('./pages/admin/AdminPlayers'))
const AdminGames = lazy(() => import('./pages/admin/AdminGames'))
const AdminSeasons = lazy(() => import('./pages/admin/AdminSeasons'))
const AdminSettings = lazy(() => import('./pages/admin/AdminSettings'))
const AdminAccount = lazy(() => import('./pages/admin/AdminAccount'))
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
const AdminFeesSquare = lazy(() => import('./pages/admin/AdminFeesSquare'))
const AdminFeesXero = lazy(() => import('./pages/admin/AdminFeesXero'))
const AdminMembershipTypes = lazy(() => import('./pages/admin/AdminMembershipTypes'))
const AdminCommittee = lazy(() => import('./pages/admin/AdminCommittee'))
const AdminVolunteers = lazy(() => import('./pages/admin/AdminVolunteers'))
const AdminRoles = lazy(() => import('./pages/admin/AdminRoles'))
const AdminActivities = lazy(() => import('./pages/admin/AdminActivities'))
const AdminQualifications = lazy(() => import('./pages/admin/AdminQualifications'))
const AdminEvents = lazy(() => import('./pages/admin/AdminEvents'))
const AdminAssets = lazy(() => import('./pages/admin/AdminAssets'))
const AdminMemberPortal = lazy(() => import('./pages/admin/AdminMemberPortal'))
const AdminClubDiary = lazy(() => import('./pages/admin/AdminClubDiary'))
const BetterMerchHome = lazy(() => import('./pages/admin/bettermerch/BetterMerchHome'))
const MerchStock = lazy(() => import('./pages/admin/bettermerch/MerchStock'))
const MerchAssets = lazy(() => import('./pages/admin/bettermerch/MerchAssets'))
const MerchActivity = lazy(() => import('./pages/admin/bettermerch/MerchActivity'))
const MerchReports = lazy(() => import('./pages/admin/bettermerch/MerchReports'))
const MerchSquare = lazy(() => import('./pages/admin/bettermerch/MerchSquare'))
const MerchOrders = lazy(() => import('./pages/admin/bettermerch/MerchOrders'))
const BetterCrmHome = lazy(() => import('./pages/admin/bettercrm/BetterCrmHome'))
const BetterCrmTracker = lazy(() => import('./pages/admin/bettercrm/BetterCrmTracker'))
const BetterCrmPeople = lazy(() => import('./pages/admin/bettercrm/BetterCrmPeople'))
const SuperCrm = lazy(() => import('./pages/admin/SuperCrm'))
const SuperCrmTargets = lazy(() => import('./pages/admin/SuperCrmTargets'))
const SuperCrmAutomation = lazy(() => import('./pages/admin/SuperCrmAutomation'))
const AdminSponsors = lazy(() => import('./pages/admin/AdminSponsors'))
const AdminSocialPost = lazy(() => import('./pages/admin/AdminSocialPost'))
const AdminYearbook = lazy(() => import('./pages/admin/AdminYearbook'))
const AdminYearbookDetail = lazy(() => import('./pages/admin/AdminYearbookDetail'))
const SuperOverview = lazy(() => import('./pages/admin/SuperOverview'))
const SuperHub = lazy(() => import('./pages/admin/SuperHub'))
const SuperClubs = lazy(() => import('./pages/admin/SuperClubs'))
const SuperClubMerge = lazy(() => import('./pages/admin/SuperClubMerge'))
const SuperUsers = lazy(() => import('./pages/admin/SuperUsers'))
const SuperOnboarding = lazy(() => import('./pages/admin/SuperOnboarding'))
const SuperUnpauseRequests = lazy(() => import('./pages/admin/SuperUnpauseRequests'))
const SuperBackups = lazy(() => import('./pages/admin/SuperBackups'))
const SuperCoupons = lazy(() => import('./pages/admin/SuperCoupons'))
const SuperDiscountReport = lazy(() => import('./pages/admin/SuperDiscountReport'))
const SuperWizardAnalytics = lazy(() => import('./pages/admin/SuperWizardAnalytics'))
const SuperSelfServeTrial = lazy(() => import('./pages/admin/SuperSelfServeTrial'))
const SuperMetaAds = lazy(() => import('./pages/admin/SuperMetaAds'))
const SuperLoginAttempts = lazy(() => import('./pages/admin/SuperLoginAttempts'))
const SuperModuleRequests = lazy(() => import('./pages/admin/SuperModuleRequests'))
const SuperCommsLimits = lazy(() => import('./pages/admin/SuperCommsLimits'))
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
const BsVotes = lazy(() => import('./pages/admin/betterselect/AdminVotes'))
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
const FixturesPage = lazy(() => import('./pages/FixturesPage'))
const LineupsPage = lazy(() => import('./pages/LineupsPage'))
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
const PublicVoting = lazy(() => import('./pages/PublicVoting'))
// Public, login-free fantasy play (BetterFantasyCricket magic link + PIN)
const PublicFantasy = lazy(() => import('./pages/PublicFantasy'))
// Public, login-free event registration (Events/Ticketing — event-id link)
const PublicEventRegister = lazy(() => import('./pages/PublicEventRegister'))
// Public, login-free member self-service portal (emailed magic link)
const PublicMemberPortal = lazy(() => import('./pages/PublicMemberPortal'))
// Public, login-free merch storefront
const PublicMerchStore = lazy(() => import('./pages/PublicMerchStore'))

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
        <HeartbeatBeacon />
        <ClubCTABar />
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
          <Route path="/trial" element={<Trial />} />
          <Route path="/faq" element={<FAQ />} />
          <Route path="/terms" element={<Terms />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/blog" element={<Blog />} />
          <Route path="/blog/:slug" element={<BlogPost />} />

          {/* Auth */}
          <Route path="/login" element={<Login />} />

          {/* Public self-service availability (no login — magic link + PIN) */}
          <Route path="/avail/:token" element={<PublicAvailability />} />
          <Route path="/vote/:token" element={<PublicVoting />} />
          {/* Public fantasy play (no login — magic link + PIN) */}
          <Route path="/fantasy/:token" element={<PublicFantasy />} />
          {/* Public event registration (no login — event-id link) */}
          <Route path="/events/:eventId" element={<PublicEventRegister />} />
          {/* Public member self-service portal (no login — emailed magic link) */}
          <Route path="/portal/:slug" element={<PublicMemberPortal />} />
          {/* Public merch storefront (no login) */}
          <Route path="/shop/:slug" element={<PublicMerchStore />} />

          {/* Admin (protected) */}
          <Route path="/admin" element={<ProtectedRoute><AdminDashboard /></ProtectedRoute>} />
          <Route path="/admin/betterstats" element={<ProtectedRoute requireCore><BetterStatsHome /></ProtectedRoute>} />
          <Route path="/admin/betterstats/:group" element={<ProtectedRoute requireCore><BetterStatsHome /></ProtectedRoute>} />
          <Route path="/admin/betterclub" element={<ProtectedRoute requireRole="super_admin"><BetterClubManagerHome /></ProtectedRoute>} />
          <Route path="/admin/betterclub/:group" element={<ProtectedRoute requireRole="super_admin"><BetterClubManagerHome /></ProtectedRoute>} />
          <Route path="/admin/setup" element={<ProtectedRoute requireActivePlan><SetupWizard /></ProtectedRoute>} />
          <Route path="/admin/setup/:stepKey" element={<ProtectedRoute requireActivePlan><SetupWizard /></ProtectedRoute>} />
          <Route path="/admin/players" element={<ProtectedRoute requireCore><AdminPlayers /></ProtectedRoute>} />
          <Route path="/admin/players/import" element={<ProtectedRoute requireCore><AdminPlayerImport /></ProtectedRoute>} />
          <Route path="/admin/games" element={<ProtectedRoute requireCore><AdminGames /></ProtectedRoute>} />
          <Route path="/admin/seasons" element={<ProtectedRoute requireCore><AdminSeasons /></ProtectedRoute>} />
          <Route path="/admin/awards" element={<ProtectedRoute requireCore><AdminAwards /></ProtectedRoute>} />
          <Route path="/admin/award-definitions" element={<ProtectedRoute requireCore><AdminAwardDefinitions /></ProtectedRoute>} />
          <Route path="/admin/merge" element={<ProtectedRoute requireCore><AdminMerge /></ProtectedRoute>} />
          <Route path="/admin/families" element={<ProtectedRoute requireRole="super_admin"><AdminFamilies /></ProtectedRoute>} />
          <Route path="/admin/committee" element={<ProtectedRoute requireRole="super_admin"><AdminCommittee /></ProtectedRoute>} />
          <Route path="/admin/volunteers" element={<ProtectedRoute requireRole="super_admin"><AdminVolunteers /></ProtectedRoute>} />
          <Route path="/admin/roles" element={<ProtectedRoute requireRole="super_admin"><AdminRoles /></ProtectedRoute>} />
          <Route path="/admin/activities" element={<ProtectedRoute requireRole="super_admin"><AdminActivities /></ProtectedRoute>} />
          <Route path="/admin/qualifications" element={<ProtectedRoute requireRole="super_admin"><AdminQualifications /></ProtectedRoute>} />
          <Route path="/admin/events" element={<ProtectedRoute requireRole="super_admin"><AdminEvents /></ProtectedRoute>} />
          <Route path="/admin/assets" element={<ProtectedRoute requireRole="super_admin"><AdminAssets /></ProtectedRoute>} />
          <Route path="/admin/member-portal" element={<ProtectedRoute requireRole="super_admin"><AdminMemberPortal /></ProtectedRoute>} />
          <Route path="/admin/club-diary" element={<ProtectedRoute requireRole="super_admin"><AdminClubDiary /></ProtectedRoute>} />
          <Route path="/admin/grades" element={<ProtectedRoute requireCore><AdminGrades /></ProtectedRoute>} />
          <Route path="/admin/sync" element={<ProtectedRoute requireCore><AdminSync /></ProtectedRoute>} />
          <Route path="/admin/partnerships" element={<ProtectedRoute requireCore><AdminPartnershipRecords /></ProtectedRoute>} />
          <Route path="/admin/manual-entries" element={<ProtectedRoute requireCore><AdminManualEntries /></ProtectedRoute>} />
          <Route path="/admin/upload-scorecard" element={<ProtectedRoute requireCore><AdminScorecardUpload /></ProtectedRoute>} />
          <Route path="/admin/import" element={<ProtectedRoute requireCore><AdminImport /></ProtectedRoute>} />
          <Route path="/admin/milestones" element={<ProtectedRoute requireCore><AdminMilestones /></ProtectedRoute>} />
          <Route path="/admin/activity" element={<ProtectedRoute requireActivePlan><AdminActivityLog /></ProtectedRoute>} />
          <Route path="/admin/changelog" element={<ProtectedRoute><AdminChangelog /></ProtectedRoute>} />
          <Route path="/admin/users" element={<ProtectedRoute><AdminUsers /></ProtectedRoute>} />
          <Route path="/admin/reports" element={<ProtectedRoute requireCore><AdminReports /></ProtectedRoute>} />
          <Route path="/admin/fees" element={<ProtectedRoute requireModule="fees"><AdminFeesMembers /></ProtectedRoute>} />
          <Route path="/admin/fees/schedule" element={<ProtectedRoute requireModule="fees"><AdminFeeSchedule /></ProtectedRoute>} />
          <Route path="/admin/fees/payments" element={<ProtectedRoute requireModule="fees"><AdminFeePayments /></ProtectedRoute>} />
          <Route path="/admin/fees/payments/import" element={<ProtectedRoute requireModule="fees"><AdminFeePaymentImport /></ProtectedRoute>} />
          <Route path="/admin/fees/payments/bulk" element={<ProtectedRoute requireModule="fees"><AdminFeeBulkPayment /></ProtectedRoute>} />
          <Route path="/admin/fees/reports" element={<ProtectedRoute requireModule="fees"><AdminFeeReports /></ProtectedRoute>} />
          <Route path="/admin/fees/square" element={<ProtectedRoute requireModule="fees"><AdminFeesSquare /></ProtectedRoute>} />
          <Route path="/admin/fees/xero" element={<ProtectedRoute requireModule="fees"><AdminFeesXero /></ProtectedRoute>} />
          <Route path="/admin/fees/membership-types" element={<ProtectedRoute requireModule="fees"><AdminMembershipTypes /></ProtectedRoute>} />
          <Route path="/admin/fees/member/:memberId" element={<ProtectedRoute requireModule="fees"><AdminFeeMemberDetail /></ProtectedRoute>} />
          <Route path="/admin/merch" element={<ProtectedRoute requireModule="merch"><BetterMerchHome /></ProtectedRoute>} />
          <Route path="/admin/merch/stock" element={<ProtectedRoute requireModule="merch"><MerchStock /></ProtectedRoute>} />
          <Route path="/admin/merch/equipment" element={<ProtectedRoute requireModule="merch"><MerchAssets /></ProtectedRoute>} />
          <Route path="/admin/merch/activity" element={<ProtectedRoute requireModule="merch"><MerchActivity /></ProtectedRoute>} />
          <Route path="/admin/merch/reports" element={<ProtectedRoute requireModule="merch"><MerchReports /></ProtectedRoute>} />
          <Route path="/admin/merch/square" element={<ProtectedRoute requireModule="merch"><MerchSquare /></ProtectedRoute>} />
          <Route path="/admin/merch/orders" element={<ProtectedRoute requireModule="merch"><MerchOrders /></ProtectedRoute>} />
          <Route path="/admin/crm" element={<ProtectedRoute requireModule="crm"><BetterCrmHome /></ProtectedRoute>} />
          <Route path="/admin/crm/people" element={<ProtectedRoute requireModule="crm"><BetterCrmPeople /></ProtectedRoute>} />
          <Route path="/admin/crm/:pipelineId" element={<ProtectedRoute requireModule="crm"><BetterCrmTracker /></ProtectedRoute>} />
          <Route path="/admin/super/crm" element={<ProtectedRoute requireRole="super_admin"><SuperCrm /></ProtectedRoute>} />
          <Route path="/admin/super/crm/targets" element={<ProtectedRoute requireRole="super_admin"><SuperCrmTargets /></ProtectedRoute>} />
          <Route path="/admin/super/crm/automation" element={<ProtectedRoute requireRole="super_admin"><SuperCrmAutomation /></ProtectedRoute>} />
          <Route path="/admin/fantasy" element={<ProtectedRoute requireModule="fantasy"><FantasyHome /></ProtectedRoute>} />
          <Route path="/admin/fantasy/settings" element={<ProtectedRoute requireModule="fantasy"><FantasySettings /></ProtectedRoute>} />
          <Route path="/admin/fantasy/scoring" element={<ProtectedRoute requireModule="fantasy"><FantasyScoring /></ProtectedRoute>} />
          <Route path="/admin/fantasy/pool" element={<ProtectedRoute requireModule="fantasy"><FantasyPool /></ProtectedRoute>} />
          <Route path="/admin/fantasy/players" element={<ProtectedRoute requireModule="fantasy"><FantasyPlayers /></ProtectedRoute>} />
          <Route path="/admin/fantasy/leagues" element={<ProtectedRoute requireModule="fantasy"><FantasyLeagues /></ProtectedRoute>} />
          <Route path="/admin/settings" element={<ProtectedRoute requireActivePlan><AdminSettings /></ProtectedRoute>} />
          <Route path="/admin/account" element={<ProtectedRoute><AdminAccount /></ProtectedRoute>} />
          <Route path="/admin/sponsors" element={<ProtectedRoute requireCore><AdminSponsors /></ProtectedRoute>} />
          <Route path="/admin/website" element={<ProtectedRoute requireCore><AdminWebsite /></ProtectedRoute>} />
          <Route path="/admin/social-post" element={<ProtectedRoute requireModule="socials"><AdminSocialPost /></ProtectedRoute>} />
          <Route path="/admin/yearbook" element={<ProtectedRoute requireCore><AdminYearbook /></ProtectedRoute>} />
          <Route path="/admin/yearbook/:seasonId" element={<ProtectedRoute requireCore><AdminYearbookDetail /></ProtectedRoute>} />
          <Route path="/admin/usage" element={<ProtectedRoute requireRole="super_admin"><AdminUsage /></ProtectedRoute>} />
          <Route path="/admin/super" element={<ProtectedRoute requireRole="super_admin"><SuperOverview /></ProtectedRoute>} />
          <Route path="/admin/super/hub/:sectionKey" element={<ProtectedRoute requireRole="super_admin"><SuperHub /></ProtectedRoute>} />
          <Route path="/admin/super/clubs" element={<ProtectedRoute requireRole="super_admin"><SuperClubs /></ProtectedRoute>} />
          <Route path="/admin/super/merge-clubs" element={<ProtectedRoute requireRole="super_admin"><SuperClubMerge /></ProtectedRoute>} />
          <Route path="/admin/super/users" element={<ProtectedRoute requireRole="super_admin"><SuperUsers /></ProtectedRoute>} />
          <Route path="/admin/super/onboarding" element={<ProtectedRoute requireRole="super_admin"><SuperOnboarding /></ProtectedRoute>} />
          <Route path="/admin/super/unpause-requests" element={<ProtectedRoute requireRole="super_admin"><SuperUnpauseRequests /></ProtectedRoute>} />
          <Route path="/admin/super/backups" element={<ProtectedRoute requireRole="super_admin"><SuperBackups /></ProtectedRoute>} />
          <Route path="/admin/super/coupons" element={<ProtectedRoute requireRole="super_admin"><SuperCoupons /></ProtectedRoute>} />
          <Route path="/admin/super/discount-report" element={<ProtectedRoute requireRole="super_admin"><SuperDiscountReport /></ProtectedRoute>} />
          <Route path="/admin/super/wizard-analytics" element={<ProtectedRoute requireRole="super_admin"><SuperWizardAnalytics /></ProtectedRoute>} />
          <Route path="/admin/super/self-serve" element={<ProtectedRoute requireRole="super_admin"><SuperSelfServeTrial /></ProtectedRoute>} />
          <Route path="/admin/super/meta-ads" element={<ProtectedRoute requireRole="super_admin"><SuperMetaAds /></ProtectedRoute>} />
          <Route path="/admin/super/login-attempts" element={<ProtectedRoute requireRole="super_admin"><SuperLoginAttempts /></ProtectedRoute>} />
          <Route path="/admin/super/module-requests" element={<ProtectedRoute requireRole="super_admin"><SuperModuleRequests /></ProtectedRoute>} />
          <Route path="/admin/super/comms-limits" element={<ProtectedRoute requireRole="super_admin"><SuperCommsLimits /></ProtectedRoute>} />
          <Route path="/admin/super/marketing" element={<ProtectedRoute requireRole="super_admin"><SuperMarketing /></ProtectedRoute>} />
          <Route path="/admin/super/announce" element={<ProtectedRoute requireRole="super_admin"><SuperAnnounce /></ProtectedRoute>} />
          <Route path="/admin/super/migration" element={<ProtectedRoute requireRole="super_admin"><KlubproMigration /></ProtectedRoute>} />

          {/* BetterSelect module */}
          <Route path="/admin/betterselect" element={<ProtectedRoute requireModule="select"><BetterSelectHome /></ProtectedRoute>} />
          {/* Sub-module group page (Your Squad / Match Day / Club Life) — a
              dynamic segment, but React Router ranks the specific tool routes
              below it higher, so /players, /fixtures etc. always win over it. */}
          <Route path="/admin/betterselect/:group" element={<ProtectedRoute requireModule="select"><BetterSelectHome /></ProtectedRoute>} />
          <Route path="/admin/betterselect/players" element={<ProtectedRoute requireModule="select"><BsPlayers /></ProtectedRoute>} />
          <Route path="/admin/betterselect/fixtures" element={<ProtectedRoute requireModule="select"><BsFixtures /></ProtectedRoute>} />
          <Route path="/admin/betterselect/teams" element={<ProtectedRoute requireModule="select"><BsTeams /></ProtectedRoute>} />
          <Route path="/admin/betterselect/availability" element={<ProtectedRoute requireModule="select"><BsAvailability /></ProtectedRoute>} />
          <Route path="/admin/betterselect/selection" element={<ProtectedRoute requireModule="select"><BsSelectionOverview /></ProtectedRoute>} />
          <Route path="/admin/betterselect/select/:fixtureId" element={<ProtectedRoute requireModule="select"><BsSelection /></ProtectedRoute>} />
          <Route path="/admin/betterselect/nets" element={<ProtectedRoute requireModule="select"><BsNets /></ProtectedRoute>} />
          <Route path="/admin/betterselect/nets/:id" element={<ProtectedRoute requireModule="select"><BsNetSession /></ProtectedRoute>} />
          <Route path="/admin/betterselect/ladders" element={<ProtectedRoute requireModule="select"><BsLadders /></ProtectedRoute>} />
          <Route path="/admin/betterselect/votes" element={<ProtectedRoute requireModule="select"><BsVotes /></ProtectedRoute>} />

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
          <Route path="/admin/bettersocials" element={<ProtectedRoute requireCore><BetterSocialsHome /></ProtectedRoute>} />

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
          <Route path="/:clubSlug/fixtures" element={<FixturesPage />} />
          <Route path="/:clubSlug/lineups" element={<LineupsPage />} />
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
