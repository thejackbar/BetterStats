import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(username.trim(), password)
      navigate('/admin')
    } catch (err) {
      setError(err.message || 'Invalid username or password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-pb-bg flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Brand */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2.5 mb-3">
            <span
              className="w-8 h-8 rounded font-mono font-bold text-sm flex items-center justify-center text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              BC
            </span>
            <span className="font-display font-bold text-xl tracking-wider uppercase text-pb-text">
              Better Cricket
            </span>
          </div>
          <p className="font-mono text-[11px] tracking-wide3 text-pb-faint">CLUB ADMIN LOGIN</p>
        </div>

        <form onSubmit={handleSubmit} className="pb-card p-6 space-y-4">
          <div>
            <label className="block font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1.5">
              Username
            </label>
            <input
              type="text"
              autoComplete="username"
              value={username}
              onChange={e => setUsername(e.target.value)}
              required
              className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent placeholder-pb-faintest"
            />
          </div>

          <div>
            <label className="block font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1.5">
              Password
            </label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2.5 pr-14 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
              />
              <button
                type="button"
                onClick={() => setShowPassword(s => !s)}
                className="absolute right-3 top-1/2 -translate-y-1/2 font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors"
              >
                {showPassword ? 'HIDE' : 'SHOW'}
              </button>
            </div>
          </div>

          {error && (
            <p className="font-mono text-[11px] text-pb-red">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 rounded font-mono text-[11px] tracking-wide3 font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed text-pb-bg"
            style={{ background: 'var(--pb-accent)' }}
          >
            {loading ? 'SIGNING IN…' : 'SIGN IN'}
          </button>
        </form>

        <p className="text-center font-mono text-[10px] tracking-wide2 text-pb-faintest mt-6">
          Forgot your password? Contact{' '}
          <a href="mailto:betterstatsau@gmail.com" className="text-pb-faint hover:text-pb-text transition-colors">
            betterstatsau@gmail.com
          </a>
        </p>
      </div>
    </div>
  )
}
