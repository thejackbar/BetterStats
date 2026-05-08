import { Navigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export default function ProtectedRoute({ children, requireRole }) {
  const { user } = useAuth()

  // Still loading session
  if (user === undefined) {
    return (
      <div className="min-h-screen bg-navy-950 flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (!user) return <Navigate to="/login" replace />

  if (requireRole && user.role !== requireRole && user.role !== 'super_admin') {
    return <Navigate to="/admin" replace />
  }

  return children
}
