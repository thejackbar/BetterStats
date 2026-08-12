import { Routes, Route, Navigate } from 'react-router-dom'
import { ThemeProvider } from '../contexts/ThemeContext'
import { ToastProvider } from '../contexts/ToastContext'
import ErrorBoundary from '../components/ErrorBoundary'
import ScrollToTop from '../components/ScrollToTop'
import { ScoutAuthProvider } from './contexts/ScoutAuthContext'
import ScoutProtectedRoute from './components/ScoutProtectedRoute'
import ScoutLogin from './pages/ScoutLogin'
import ScoutLayout from './ScoutLayout'
import ScoutDashboard from './pages/ScoutDashboard'

/**
 * BetterScout — the bs-scout-frontend app tree, mounted by App.jsx when the
 * build sets VITE_PRODUCT=scout. Same silo mechanism as the AFL app tree
 * (VITE_SPORT=afl), but a different tenant type entirely — its own auth
 * context (ScoutAuthProvider, not the shared club AuthProvider), reusing
 * only the sport/club-agnostic shared pieces: ThemeProvider, ToastProvider,
 * ErrorBoundary, ScrollToTop.
 */
export default function ScoutApp() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <ToastProvider>
          <ScoutAuthProvider>
            <ScrollToTop />
            <div className="min-h-screen bg-pb-bg">
              <Routes>
                <Route path="/login" element={<ScoutLogin />} />
                <Route
                  path="/app"
                  element={
                    <ScoutProtectedRoute>
                      <ScoutLayout />
                    </ScoutProtectedRoute>
                  }
                >
                  <Route index element={<ScoutDashboard />} />
                </Route>
                <Route path="/" element={<Navigate to="/app" replace />} />
                <Route path="*" element={<Navigate to="/app" replace />} />
              </Routes>
            </div>
          </ScoutAuthProvider>
        </ToastProvider>
      </ThemeProvider>
    </ErrorBoundary>
  )
}
