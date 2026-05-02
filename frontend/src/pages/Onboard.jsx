import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'

export default function Onboard() {
  const [orgId, setOrgId] = useState('')
  const [status, setStatus] = useState(null) // null | 'loading' | 'success' | 'error'
  const [message, setMessage] = useState('')
  const [result, setResult] = useState(null)
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!orgId.trim()) return
    setStatus('loading')
    setMessage('')
    try {
      const data = await api.onboard(orgId.trim())
      setResult(data)
      setStatus('success')
      setMessage(`${data.name} is being synced. This may take a few minutes.`)
    } catch (err) {
      setStatus('error')
      setMessage(err.message || 'Organisation not found. Check your Organisation ID.')
    }
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-16">
      <div className="mb-10">
        <div className="accent-bar mb-4" />
        <h1 className="display-heading text-4xl text-white mb-2">ADD YOUR CLUB</h1>
        <p className="text-slate-400">
          Enter your PlayHQ Organisation ID to start pulling stats automatically.
          You can find this in your club admin URL at{' '}
          <a href="https://ca.playhq.com" target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">
            ca.playhq.com
          </a>
        </p>
      </div>

      {/* Where to find org ID */}
      <div className="card p-5 mb-8 border-accent/20">
        <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <span className="w-5 h-5 rounded-full bg-accent/20 text-accent text-xs flex items-center justify-center font-bold">?</span>
          Where to find your Organisation ID
        </h3>
        <ol className="space-y-2 text-sm text-slate-400">
          <li>1. Log into <span className="text-white font-medium">ca.playhq.com</span></li>
          <li>2. Navigate to your club's organisation page</li>
          <li>3. Copy the UUID from the URL — it looks like:<br />
            <code className="font-mono text-accent text-xs bg-navy-900 px-2 py-1 rounded mt-1 inline-block">
              /organisations/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
            </code>
          </li>
        </ol>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="section-label block mb-2">PlayHQ Organisation ID</label>
          <input
            type="text"
            value={orgId}
            onChange={e => setOrgId(e.target.value)}
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            className="w-full bg-navy-800 border border-navy-600 text-white placeholder-slate-600 font-mono text-sm rounded-lg px-4 py-3 focus:outline-none focus:border-accent transition-colors"
            disabled={status === 'loading' || status === 'success'}
          />
        </div>

        {message && (
          <div className={`rounded-lg px-4 py-3 text-sm ${status === 'error' ? 'bg-red-500/10 border border-red-500/30 text-red-400' : 'bg-accent/10 border border-accent/30 text-accent'}`}>
            {message}
          </div>
        )}

        {status !== 'success' ? (
          <button
            type="submit"
            disabled={status === 'loading' || !orgId.trim()}
            className="btn-primary w-full py-3 text-base disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {status === 'loading' ? (
              <span className="flex items-center justify-center gap-2">
                <span className="w-4 h-4 border-2 border-navy-950/40 border-t-navy-950 rounded-full animate-spin" />
                Connecting to PlayHQ…
              </span>
            ) : 'Add Club & Start Sync'}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => result && navigate(`/dashboard/${result.org_id}`)}
            className="btn-primary w-full py-3 text-base"
          >
            View Dashboard →
          </button>
        )}
      </form>
    </div>
  )
}
