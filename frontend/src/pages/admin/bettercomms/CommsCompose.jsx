import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../../../lib/api'
import BetterCommsLayout from '../../../components/admin/BetterCommsLayout'

// Render the compose body for preview: plain text → escaped + <br>; if the
// author already wrote HTML, trust it. Mirrors the backend _body_to_html.
function bodyToHtml(body) {
  const b = body || ''
  if (b.includes('<') && b.includes('>')) return b
  const esc = b.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return esc.replace(/\n/g, '<br>')
}
function mergeSample(s) {
  return (s || '')
    .replace(/\{\{\s*first_name\s*\}\}/g, 'there')
    .replace(/\{\{\s*name\s*\}\}/g, 'there')
    .replace(/\{\{\s*club_name\s*\}\}/g, 'your club')
    .replace(/\{\{\s*email\s*\}\}/g, 'you@example.com')
}

export default function CommsCompose() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [campaign, setCampaign] = useState(null)
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [audienceCount, setAudienceCount] = useState(null)
  const [audience, setAudience] = useState({ type: 'all' })
  const [segments, setSegments] = useState([])
  const [lists, setLists] = useState([])
  const [testEmail, setTestEmail] = useState('')
  const [showPreview, setShowPreview] = useState(false)
  const [live, setLive] = useState(true)
  const [busy, setBusy] = useState('')          // 'save' | 'test' | 'send'
  const [msg, setMsg] = useState(null)          // { kind, text }
  const [loading, setLoading] = useState(true)
  const pollRef = useRef(null)

  const load = useCallback(async () => {
    const c = await api.commsGetCampaign(id)
    setCampaign(c)
    setSubject(c.subject || '')
    setBody(c.body_html || '')
    setAudience(c.audience && c.audience.type ? c.audience : { type: 'all' })
    return c
  }, [id])

  useEffect(() => {
    load()
      .then(c => {
        if (c.status === 'sending') startPolling()
      })
      .catch(e => setMsg({ kind: 'error', text: e.message }))
      .finally(() => setLoading(false))
    api.commsListSegments().then(setSegments).catch(() => {})
    api.commsListLists().then(setLists).catch(() => {})
    api.commsGetSettings().then(s => setLive(!!s?.provider?.live)).catch(() => {})
    return () => clearInterval(pollRef.current)
  }, [load])

  // Re-count whenever the chosen audience changes.
  useEffect(() => {
    setAudienceCount(null)
    api.commsAudiencePreview(audience).then(r => setAudienceCount(r.count)).catch(() => setAudienceCount(null))
  }, [audience])

  const startPolling = () => {
    clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.commsCampaignStatus(id)
        setCampaign(c => ({ ...c, status: s.status, stats: s.stats, error: s.error }))
        if (s.status !== 'sending') clearInterval(pollRef.current)
      } catch { /* keep polling */ }
    }, 2000)
  }

  const save = async () => {
    const c = await api.commsUpdateCampaign(id, { subject, body_html: body, audience })
    setCampaign(c)
    return c
  }

  const onSave = async () => {
    setBusy('save'); setMsg(null)
    try { await save(); setMsg({ kind: 'ok', text: 'Draft saved.' }) }
    catch (e) { setMsg({ kind: 'error', text: e.message }) }
    finally { setBusy('') }
  }

  const onTest = async () => {
    if (!testEmail.trim()) { setMsg({ kind: 'error', text: 'Enter an email to send the test to.' }); return }
    setBusy('test'); setMsg(null)
    try {
      await save()
      const r = await api.commsTestCampaign(id, testEmail.trim())
      setMsg({ kind: 'ok', text: r.live ? `Test sent to ${testEmail.trim()}.` : `Test rendered (preview mode — not delivered).` })
    } catch (e) { setMsg({ kind: 'error', text: e.message }) }
    finally { setBusy('') }
  }

  const onSend = async () => {
    if (!subject.trim()) { setMsg({ kind: 'error', text: 'Add a subject before sending.' }); return }
    const n = audienceCount ?? 0
    if (!window.confirm(`Send this email to ${n} subscribed contact${n === 1 ? '' : 's'}?`)) return
    setBusy('send'); setMsg(null)
    try {
      await save()
      const r = await api.commsSendCampaign(id)
      setCampaign(c => ({ ...c, status: 'sending', stats: { recipients: r.recipients, sent: 0, failed: 0 } }))
      startPolling()
      setMsg({ kind: 'ok', text: r.live ? `Sending to ${r.recipients}…` : `Sending ${r.recipients} (preview mode — not delivered)…` })
    } catch (e) { setMsg({ kind: 'error', text: e.message }) }
    finally { setBusy('') }
  }

  const onDelete = async () => {
    if (!window.confirm('Delete this draft?')) return
    try { await api.commsDeleteCampaign(id); navigate('/admin/comms') }
    catch (e) { setMsg({ kind: 'error', text: e.message }) }
  }

  if (loading) return <BetterCommsLayout title="Email"><div className="text-pb-faint text-sm">Loading…</div></BetterCommsLayout>
  if (!campaign) return <BetterCommsLayout title="Email"><div className="text-pb-red text-sm">Not found.</div></BetterCommsLayout>

  const isDraft = campaign.status === 'draft'
  const st = campaign.stats || {}

  return (
    <BetterCommsLayout
      title={isDraft ? 'Compose email' : 'Email'}
      actions={<button onClick={() => navigate('/admin/comms')} className="text-sm text-pb-faint hover:text-pb-text underline">← All emails</button>}
    >
      <div className="max-w-2xl">
        {msg && (
          <div className={`pb-card p-3 mb-4 text-sm ${msg.kind === 'error' ? 'text-pb-red' : 'text-green-500'}`}>{msg.text}</div>
        )}

        {!isDraft ? (
          // ── Sent / sending / error summary ──────────────────────────────
          <div className="pb-card p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Status</span>
              <span className="font-mono text-xs text-pb-text uppercase">{campaign.status}</span>
            </div>
            <div className="text-pb-text font-medium">{campaign.subject || '(no subject)'}</div>
            <div className="grid grid-cols-3 gap-3 mt-4 text-center">
              <div className="pb-card p-3"><div className="text-xl font-display font-bold text-pb-text">{st.recipients ?? 0}</div><div className="text-pb-faintest text-xs">recipients</div></div>
              <div className="pb-card p-3"><div className="text-xl font-display font-bold text-green-500">{st.sent ?? 0}</div><div className="text-pb-faintest text-xs">delivered</div></div>
              <div className="pb-card p-3"><div className="text-xl font-display font-bold text-pb-red">{st.failed ?? 0}</div><div className="text-pb-faintest text-xs">failed</div></div>
            </div>
            {campaign.status === 'sending' && <div className="text-pb-faint text-sm mt-3">Sending in progress…</div>}
            {campaign.error && <div className="text-pb-red text-sm mt-3">{campaign.error}</div>}
            <div className="mt-4 pt-4 pb-hairline-t" />
            <div className="text-pb-faint text-sm whitespace-pre-wrap" dangerouslySetInnerHTML={{ __html: bodyToHtml(campaign.body_html || '') }} />
          </div>
        ) : (
          // ── Draft editor ────────────────────────────────────────────────
          <>
            <label className="block text-sm text-pb-faint mb-1">Subject</label>
            <input value={subject} onChange={e => setSubject(e.target.value)} placeholder="e.g. Round 5 — training this Thursday"
              className="w-full pb-input mb-4 px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline" />

            <div className="flex items-center justify-between mb-1">
              <label className="block text-sm text-pb-faint">Message</label>
              <button onClick={() => setShowPreview(p => !p)} className="text-xs text-pb-faint hover:text-pb-text underline">
                {showPreview ? 'Edit' : 'Preview'}
              </button>
            </div>

            {showPreview ? (
              <div className="pb-card p-4 mb-2 min-h-[180px]">
                <div className="font-medium text-pb-text mb-2">{mergeSample(subject) || '(no subject)'}</div>
                <div className="text-pb-faint text-sm" dangerouslySetInnerHTML={{ __html: mergeSample(bodyToHtml(body)) }} />
                <div className="mt-4 pt-3 pb-hairline-t text-pb-faintest text-xs">
                  Your club footer + a one-click unsubscribe link are added automatically.
                </div>
              </div>
            ) : (
              <textarea value={body} onChange={e => setBody(e.target.value)} rows={10}
                placeholder={'Hi {{first_name}},\n\nWrite your message here…'}
                className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline font-sans text-sm mb-2" />
            )}
            <div className="text-pb-faintest text-xs mb-5">
              Personalise with <code className="text-pb-faint">{'{{first_name}}'}</code> and <code className="text-pb-faint">{'{{club_name}}'}</code>.
            </div>

            <div className="pb-card p-4 mb-4">
              <div className="text-sm text-pb-text mb-2">Audience</div>
              <select
                value={audience.type === 'segment' ? `segment:${audience.segment_id}`
                  : audience.type === 'saved_list' ? `list:${audience.list_id}` : 'all'}
                onChange={e => {
                  const v = e.target.value
                  if (v.startsWith('segment:')) setAudience({ type: 'segment', segment_id: v.slice(8) })
                  else if (v.startsWith('list:')) setAudience({ type: 'saved_list', list_id: v.slice(5) })
                  else setAudience({ type: 'all' })
                }}
                className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm">
                <option value="all">All subscribed contacts</option>
                {segments.length > 0 && (
                  <optgroup label="Segments">
                    {segments.map(s => <option key={s.id} value={`segment:${s.id}`}>{s.name}</option>)}
                  </optgroup>
                )}
                {lists.length > 0 && (
                  <optgroup label="Lists">
                    {lists.map(l => <option key={l.id} value={`list:${l.id}`}>{l.name}</option>)}
                  </optgroup>
                )}
              </select>
              <div className="text-pb-faintest text-xs mt-2">
                {audienceCount != null
                  ? <><span className="text-pb-faint">{audienceCount}</span> contact{audienceCount === 1 ? '' : 's'} will receive this.</>
                  : 'Counting…'}{' '}
                <a href="/admin/comms/segments" className="underline" style={{ color: 'var(--pb-accent)' }}>Segments</a>
                {' · '}
                <a href="/admin/comms/lists" className="underline" style={{ color: 'var(--pb-accent)' }}>Lists</a>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2 mb-6">
              <button onClick={onSave} disabled={busy === 'save'}
                className="px-3 py-2 rounded text-sm border pb-hairline text-pb-text hover:bg-pb-surface2 disabled:opacity-60">
                {busy === 'save' ? 'Saving…' : 'Save draft'}
              </button>
              <button onClick={onSend} disabled={!!busy || !audienceCount}
                className="px-4 py-2 rounded text-sm font-medium text-white disabled:opacity-50"
                style={{ background: 'var(--pb-accent)' }}>
                {busy === 'send' ? 'Sending…' : `Send${audienceCount != null ? ` to ${audienceCount}` : ''}`}
              </button>
              <button onClick={onDelete} className="px-3 py-2 rounded text-sm text-pb-faint hover:text-pb-red ml-auto">Delete</button>
            </div>

            <div className="pb-card p-4">
              <div className="text-sm text-pb-text mb-2">Send a test to yourself first</div>
              <div className="flex gap-2">
                <input value={testEmail} onChange={e => setTestEmail(e.target.value)} placeholder="you@example.com" type="email"
                  className="flex-1 px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm" />
                <button onClick={onTest} disabled={busy === 'test'}
                  className="px-3 py-2 rounded text-sm border pb-hairline text-pb-text hover:bg-pb-surface2 disabled:opacity-60">
                  {busy === 'test' ? 'Sending…' : 'Send test'}
                </button>
              </div>
              {!live && <div className="text-pb-faintest text-xs mt-2">Preview mode — tests are rendered but not delivered until a provider is connected in Settings.</div>}
            </div>
          </>
        )}
      </div>
    </BetterCommsLayout>
  )
}
