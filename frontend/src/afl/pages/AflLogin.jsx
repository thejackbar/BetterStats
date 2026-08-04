import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'

export default function AflLogin() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(username, password)
      navigate('/admin')
    } catch (err) {
      setError(err.message || 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text flex items-center justify-center px-4">
      <form onSubmit={submit} className="pb-card p-6 w-full max-w-sm space-y-4">
        <div>
          <h1 className="text-xl font-bold">Better<span className="pb-gradient-text">Football</span></h1>
          <p className="text-sm text-pb-faint">Club admin sign in</p>
        </div>
        {error && <p className="text-sm text-[var(--pb-negative)]">{error}</p>}
        <label className="block text-sm">
          <span className="text-pb-dim">Username</span>
          <input value={username} onChange={e => setUsername(e.target.value)} autoFocus
                 className="mt-1 w-full bg-pb-surface2 border border-pb-hairline rounded px-3 py-2" />
        </label>
        <label className="block text-sm">
          <span className="text-pb-dim">Password</span>
          <input type="password" value={password} onChange={e => setPassword(e.target.value)}
                 className="mt-1 w-full bg-pb-surface2 border border-pb-hairline rounded px-3 py-2" />
        </label>
        <button disabled={busy || !username || !password}
                className="w-full py-2 rounded font-semibold bg-[var(--pb-accent)] text-black disabled:opacity-50">
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
