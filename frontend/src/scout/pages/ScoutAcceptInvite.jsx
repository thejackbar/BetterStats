import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { scoutApi } from '../lib/scoutApi'

// Standalone, no session, no ScoutModuleLayout — the invited person isn't
// signed in yet. Mirrors ScoutLogin.jsx's bare-card styling.
export default function ScoutAcceptInvite() {
  const { token } = useParams()
  const navigate = useNavigate()
  const [preview, setPreview] = useState(undefined) // undefined = loading, null = invalid
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    scoutApi.previewInvite(token).then(setPreview).catch(() => setPreview(null))
  }, [token])

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await scoutApi.acceptInvite(token, username, password, displayName || undefined)
      navigate('/betterscout/login', { state: { justAccepted: true } })
    } catch (err) {
      setError(err.message || 'Could not accept this invite')
    } finally {
      setBusy(false)
    }
  }

  if (preview === undefined) {
    return <div className="min-h-screen bg-pb-bg flex items-center justify-center text-pb-dim text-sm">Loading…</div>
  }
  if (preview === null) {
    return (
      <div className="min-h-screen bg-pb-bg text-pb-text flex items-center justify-center px-4">
        <div className="pb-card p-6 w-full max-w-sm text-center space-y-2">
          <h1 className="text-lg font-bold">Invite not found</h1>
          <p className="text-sm text-pb-dim">This invite link isn't valid. It may have already been used or expired. Ask whoever invited you for a fresh one.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text flex items-center justify-center px-4">
      <form onSubmit={submit} className="pb-card p-6 w-full max-w-sm space-y-4">
        <div>
          <h1 className="text-xl font-bold">Better<span style={{ color: '#C026D3' }}>Scout</span></h1>
          <p className="text-sm text-pb-faint">
            Join <span className="text-pb-text">{preview.scout_org_name}</span> as {preview.role === 'owner' ? 'an owner' : 'a viewer'} ({preview.email})
          </p>
        </div>
        {error && <p className="text-sm text-pb-red">{error}</p>}
        <label className="block text-sm">
          <span className="text-pb-dim">Your name</span>
          <input value={displayName} onChange={(e) => setDisplayName(e.target.value)}
            className="mt-1 w-full bg-pb-surface2 border border-pb-hairline rounded px-3 py-2" />
        </label>
        <label className="block text-sm">
          <span className="text-pb-dim">Choose a username</span>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus
            className="mt-1 w-full bg-pb-surface2 border border-pb-hairline rounded px-3 py-2" />
        </label>
        <label className="block text-sm">
          <span className="text-pb-dim">Choose a password</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full bg-pb-surface2 border border-pb-hairline rounded px-3 py-2" />
        </label>
        <button disabled={busy || !username || password.length < 8}
          className="w-full py-2 rounded font-semibold disabled:opacity-50"
          style={{ background: '#C026D3', color: '#0a0d14' }}>
          {busy ? 'Joining…' : 'Join'}
        </button>
      </form>
    </div>
  )
}
