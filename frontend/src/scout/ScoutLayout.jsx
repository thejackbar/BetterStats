import { Outlet, useNavigate } from 'react-router-dom'
import { useScoutAuth } from './contexts/ScoutAuthContext'

export default function ScoutLayout() {
  const { user, logout } = useScoutAuth()
  const navigate = useNavigate()

  const doLogout = async () => {
    await logout()
    navigate('/betterscout/login')
  }

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <header className="border-b border-pb-hairline bg-pb-surface">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-baseline gap-3">
            <span className="font-bold">Better<span className="pb-gradient-text">Scout</span></span>
            <span className="text-sm text-pb-dim">{user?.scout_org_name}</span>
          </div>
          <button onClick={doLogout} className="text-sm text-pb-dim hover:text-pb-text">
            Log out
          </button>
        </div>
      </header>
      <main className="max-w-5xl mx-auto px-4 py-8">
        <Outlet />
      </main>
    </div>
  )
}
