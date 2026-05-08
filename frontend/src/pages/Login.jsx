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
    <div className="min-h-screen bg-navy-950 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 mb-2">
            <span className="w-8 h-8 rounded bg-accent flex items-center justify-center">
              <svg viewBox="0 0 24 24" className="w-5 h-5 fill-navy-950">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="4" x2="12" y2="20" stroke="#070b14" strokeWidth="2" />
                <line x1="4" y1="12" x2="20" y2="12" stroke="#070b14" strokeWidth="2" />
              </svg>
            </span>
            <span className="font-display font-bold text-2xl tracking-wider uppercase text-white">
              Better<span className="text-accent">Stats</span>
            </span>
          </div>
          <p className="text-slate-400 text-sm">Club admin login</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-navy-900 border border-navy-700 rounded-lg p-6 space-y-4">
          <div>
            <label className="block text-sm text-slate-400 mb-1">Username</label>
            <input
              type="text"
              autoComplete="username"
              value={username}
              onChange={e => setUsername(e.target.value)}
              required
              className="w-full bg-navy-800 border border-navy-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-accent"
            />
          </div>

          <div>
            <label className="block text-sm text-slate-400 mb-1">Password</label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                className="w-full bg-navy-800 border border-navy-600 rounded px-3 py-2 pr-10 text-white text-sm focus:outline-none focus:border-accent"
              />
              <button
                type="button"
                onClick={() => setShowPassword(s => !s)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white text-xs px-1"
              >
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </div>
          </div>

          {error && (
            <p className="text-red-400 text-sm">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="text-center text-slate-600 text-xs mt-6">
          Forgot your password? Contact{' '}
          <a href="mailto:jack@klubpro.com" className="text-slate-400 hover:text-white">
            jack@klubpro.com
          </a>
        </p>
      </div>
    </div>
  )
}
