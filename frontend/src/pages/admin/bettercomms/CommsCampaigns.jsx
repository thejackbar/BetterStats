import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../../lib/api'
import BetterCommsLayout from '../../../components/admin/BetterCommsLayout'

const STATUS_STYLE = {
  draft: 'text-pb-faint border-pb-faint/30',
  sending: 'text-pb-accent border-pb-accent/40',
  sent: 'text-green-500 border-green-500/40',
  error: 'text-pb-red border-pb-red/40',
}

function fmtDate(s) {
  if (!s) return ''
  try { return new Date(s).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' }) }
  catch { return '' }
}

export default function CommsCampaigns() {
  const navigate = useNavigate()
  const [campaigns, setCampaigns] = useState([])
  const [settings, setSettings] = useState(null)
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([
      api.commsListCampaigns().then(setCampaigns).catch(e => setError(e.message)),
      api.commsGetSettings().then(setSettings).catch(() => {}),
    ]).finally(() => setLoading(false))
  }, [])

  // A send runs as a background task on the server, so a freshly-sent email sits
  // at "sending" here until it flips to "sent". Poll while anything is in flight
  // so the badge updates on its own without a manual refresh.
  const anySending = campaigns.some(c => c.status === 'sending')
  useEffect(() => {
    if (!anySending) return
    const id = setInterval(() => {
      api.commsListCampaigns().then(setCampaigns).catch(() => {})
    }, 3000)
    return () => clearInterval(id)
  }, [anySending])

  const newEmail = async () => {
    setCreating(true)
    setError('')
    try {
      const c = await api.commsCreateCampaign({ subject: '', body_html: '', audience: { type: '' } })
      navigate(`/admin/comms/${c.id}`)
    } catch (e) {
      setError(e.message)
      setCreating(false)
    }
  }

  const remove = async (c) => {
    const label = c.subject?.trim() || 'this email'
    if (!window.confirm(`Delete ${c.status === 'draft' ? 'draft' : ''} "${label}"? This can't be undone.`)) return
    setError('')
    try {
      await api.commsDeleteCampaign(c.id)
      setCampaigns(list => list.filter(x => x.id !== c.id))
    } catch (e) { setError(e.message) }
  }

  const live = settings?.provider?.live

  return (
    <BetterCommsLayout
      title="Emails"
      actions={
        <button onClick={newEmail} disabled={creating}
          className="px-3 py-1.5 rounded text-sm font-medium text-white disabled:opacity-60"
          style={{ background: 'var(--pb-accent)' }}>
          {creating ? 'Creating…' : '+ New email'}
        </button>
      }
    >
      {error && <div className="pb-card p-3 mb-4 text-pb-red text-sm">{error}</div>}

      {settings && !live && (
        <div className="pb-card p-3 mb-4 text-sm text-pb-faint border-l-2 border-amber-500/50">
          <span className="text-amber-500 font-medium">Preview mode.</span> No email provider is connected yet, so
          sends are logged but <strong>not delivered</strong>. Connect a free provider in{' '}
          <a href="/admin/comms/settings" className="underline" style={{ color: 'var(--pb-accent)' }}>Settings</a> to go live.
        </div>
      )}

      {loading ? (
        <div className="text-pb-faint text-sm">Loading…</div>
      ) : campaigns.length === 0 ? (
        <div className="pb-card p-8 text-center">
          <div className="text-pb-text font-medium mb-1">No emails yet</div>
          <div className="text-pb-faint text-sm mb-4">Send your first newsletter or announcement to the club.</div>
          <button onClick={newEmail} disabled={creating}
            className="px-4 py-2 rounded text-sm font-medium text-white disabled:opacity-60"
            style={{ background: 'var(--pb-accent)' }}>
            {creating ? 'Creating…' : '+ New email'}
          </button>
        </div>
      ) : (
        <div className="pb-card overflow-hidden">
          {campaigns.map((c, i) => {
            const st = c.stats || {}
            return (
              <div key={c.id}
                className={`w-full flex items-center justify-between gap-4 px-5 py-3.5 hover:bg-pb-surface2 transition-colors ${i > 0 ? 'pb-hairline-t' : ''}`}>
                <button onClick={() => navigate(`/admin/comms/${c.id}`)} className="min-w-0 flex-1 text-left">
                  <div className="text-pb-text text-sm truncate">{c.name || c.subject || <span className="text-pb-faintest italic">(no subject)</span>}</div>
                  {c.description && <div className="text-pb-faint text-xs mt-0.5 truncate" title={c.description}>{c.description}</div>}
                  {c.name && c.subject && c.name !== c.subject && (
                    <div className="text-pb-faintest text-[11px] mt-0.5 truncate">Subject: {c.subject}</div>
                  )}
                  {c.utm?.utm_campaign && (
                    <div className="text-[11px] font-mono mt-0.5 truncate" title={`utm_campaign=${c.utm.utm_campaign}`}>
                      <span className="text-pb-faintest">utm_campaign=</span><span className="text-pb-faint">{c.utm.utm_campaign}</span>
                    </div>
                  )}
                  {c.audience_label && (
                    <div className="text-pb-faint text-[11px] mt-0.5 truncate">Audience: {c.audience_label}</div>
                  )}
                  <div className="text-pb-faintest text-xs mt-0.5">
                    {c.status === 'sent' && c.sent_at ? `Sent ${fmtDate(c.sent_at)}` : `Created ${fmtDate(c.created_at)}`}
                    {(c.status === 'sent' || c.status === 'error' || c.status === 'sending') && c.engagement && (c.engagement.sent > 0 || c.engagement.bounced > 0 || c.engagement.unsub_supp > 0) && (
                      <> · {c.engagement.sent} sent
                        {c.engagement.bounced > 0 && <> · <span className="text-pb-red">{c.engagement.bounced} bounced</span></>}
                        {c.engagement.unsub_supp > 0 && <> · <span className="text-amber-500">{c.engagement.unsub_supp} unsub/spam</span></>}
                      </>
                    )}
                  </div>
                  {c.warnings?.length > 0 && (
                    <div className="text-amber-500 text-[11px] mt-0.5 truncate" title={c.warnings.join('\n')}>
                      ⚠ {c.warnings.length} consistency warning{c.warnings.length === 1 ? '' : 's'}
                    </div>
                  )}
                </button>
                <div className="shrink-0 flex items-center gap-3">
                  <span className={`font-mono text-[10px] uppercase tracking-wide2 border rounded px-2 py-0.5 ${STATUS_STYLE[c.status] || STATUS_STYLE.draft}`}>
                    {c.status}
                  </span>
                  {c.status !== 'sending' && (
                    <button onClick={() => remove(c)} title="Delete"
                      className="text-pb-faintest hover:text-pb-red text-sm px-1">✕</button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </BetterCommsLayout>
  )
}
