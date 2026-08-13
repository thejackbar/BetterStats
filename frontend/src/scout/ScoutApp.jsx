import { Outlet } from 'react-router-dom'
import { ScoutAuthProvider } from './contexts/ScoutAuthContext'

/**
 * BetterScout's route-group wrapper. BetterScout lives inside the SAME
 * single-page app as the rest of BetterCricket now (not a separate
 * VITE_PRODUCT build) — this is just a pathless layout route (see App.jsx's
 * `/betterscout/*` routes) that scopes ScoutAuthProvider to the scout routes
 * without adding a URL segment of its own. Everything else (ThemeProvider,
 * ToastProvider, ErrorBoundary, ScrollToTop) is already provided once by the
 * outer app tree in App.jsx.
 */
export default function ScoutApp() {
  return (
    <ScoutAuthProvider>
      <Outlet />
    </ScoutAuthProvider>
  )
}
