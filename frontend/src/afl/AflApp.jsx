import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from '../contexts/AuthContext'
import { ThemeProvider } from '../contexts/ThemeContext'
import { ToastProvider } from '../contexts/ToastContext'
import ErrorBoundary from '../components/ErrorBoundary'
import ScrollToTop from '../components/ScrollToTop'
import ClubLayout from './ClubLayout'
import Dashboard from './pages/Dashboard'
import Players from './pages/Players'
import PlayerProfile from './pages/PlayerProfile'
import Games from './pages/Games'
import Match from './pages/Match'
import Records from './pages/Records'
import Leaderboard from './pages/Leaderboard'
import Compare from './pages/Compare'
import Premierships from './pages/Premierships'
import HonourBoard from './pages/HonourBoard'
import AflLogin from './pages/AflLogin'
import AflPublicVoting from './pages/AflPublicVoting'
import TeamLists from './pages/TeamLists'
import AflAdminLayout from './AflAdminLayout'
import AflAdminSync from './pages/admin/AflAdminSync'
import AflAdminPlayers from './pages/admin/AflAdminPlayers'
import AflAdminPlayerImport from './pages/admin/AflAdminPlayerImport'
import AflAdminImport from './pages/admin/AflAdminImport'
import AflAdminResultsImport from './pages/admin/AflAdminResultsImport'
import AflAdminAwardsImport from './pages/admin/AflAdminAwardsImport'
import AflAdminSeasons from './pages/admin/AflAdminSeasons'
import AflAdminManualEntries from './pages/admin/AflAdminManualEntries'
import AflAdminMergePlayers from './pages/admin/AflAdminMergePlayers'
import AflAdminMergeGrades from './pages/admin/AflAdminMergeGrades'
import AflAdminAwardDefinitions from './pages/admin/AflAdminAwardDefinitions'
import AflAdminAwards from './pages/admin/AflAdminAwards'
import AflAdminSponsors from './pages/admin/AflAdminSponsors'
import AflAdminUsers from './pages/admin/AflAdminUsers'
import AflAdminSettings from './pages/admin/AflAdminSettings'
import AflAdminVotes from './pages/admin/AflAdminVotes'
import AflAdminSuperUsers from './pages/admin/AflAdminSuperUsers'
import AflAdminSuperClubs from './pages/admin/AflAdminSuperClubs'

/**
 * BetterStats AFL — the bs-afl-frontend app tree, mounted by App.jsx when the
 * build sets VITE_SPORT=afl (see docs/afl-betterstats-plan.md). One codebase,
 * per-sport silos: this reuses the shared contexts, theme system and
 * components; only the pages are AFL-shaped.
 */
export default function AflApp() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <ToastProvider>
          <AuthProvider>
            <ScrollToTop />
            <div className="min-h-screen bg-pb-bg">
              <Routes>
                <Route path="/login" element={<AflLogin />} />
                {/* Standalone, outside the club layout: a voter follows this
                    link with no account and no club chrome. */}
                <Route path="/vote/:token" element={<AflPublicVoting />} />
                <Route path="/admin" element={<AflAdminLayout />}>
                  <Route index element={<AflAdminSync />} />
                  <Route path="players" element={<AflAdminPlayers />} />
                  <Route path="players/import" element={<AflAdminPlayerImport />} />
                  <Route path="import" element={<AflAdminImport />} />
                  <Route path="import-results" element={<AflAdminResultsImport />} />
                  <Route path="import-awards" element={<AflAdminAwardsImport />} />
                  <Route path="seasons" element={<AflAdminSeasons />} />
                  <Route path="manual-entries" element={<AflAdminManualEntries />} />
                  <Route path="merge" element={<AflAdminMergePlayers />} />
                  <Route path="merge-grades" element={<AflAdminMergeGrades />} />
                  <Route path="award-definitions" element={<AflAdminAwardDefinitions />} />
                  <Route path="awards" element={<AflAdminAwards />} />
                  <Route path="sponsors" element={<AflAdminSponsors />} />
                  <Route path="users" element={<AflAdminUsers />} />
                  <Route path="votes" element={<AflAdminVotes />} />
                  <Route path="settings" element={<AflAdminSettings />} />
                  <Route path="super/users" element={<AflAdminSuperUsers />} />
                  <Route path="super/clubs" element={<AflAdminSuperClubs />} />
                </Route>
                <Route path="/:clubSlug" element={<ClubLayout />}>
                  <Route index element={<Dashboard />} />
                  <Route path="players" element={<Players />} />
                  <Route path="players/:playerId" element={<PlayerProfile />} />
                  <Route path="games" element={<Games />} />
                  <Route path="games/:gameId" element={<Match />} />
                  <Route path="team-lists" element={<TeamLists />} />
                  <Route path="records" element={<Records />} />
                  <Route path="leaderboard" element={<Leaderboard />} />
                  <Route path="premierships" element={<Premierships />} />
                  <Route path="honour-board" element={<HonourBoard />} />
                  <Route path="compare" element={<Compare />} />
                </Route>
                <Route path="/" element={<Navigate to="/login" replace />} />
                <Route path="*" element={<Navigate to="/login" replace />} />
              </Routes>
            </div>
          </AuthProvider>
        </ToastProvider>
      </ThemeProvider>
    </ErrorBoundary>
  )
}
