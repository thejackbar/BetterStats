import { Navigate, useLocation } from 'react-router-dom'
import { useScoutAuth } from '../contexts/ScoutAuthContext'

// Minimal analog of components/ProtectedRoute.jsx — just the loading/redirect
// shape. No trial banners, no module/capability gates: those are club
// concepts that don't apply to a Scout Org.
export default function ScoutProtectedRoute({ children }) {
  const { user } = useScoutAuth()
  const location = useLocation()

  if (user === undefined) {
    return (
      <div className="min-h-screen bg-pb-bg flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-t-transparent rounded-full animate-spin"
             style={{ borderColor: 'var(--pb-accent)', borderTopColor: 'transparent' }} />
      </div>
    )
  }

  if (!user) return <Navigate to="/betterscout/login" replace state={{ from: location }} />

  return children
}
