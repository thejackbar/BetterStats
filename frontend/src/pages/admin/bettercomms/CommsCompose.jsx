import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
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
  const [templates, setTemplates] = useState([])
  const [templateId, setTemplateId] = useState('')
  const [knownVars, setKnownVars] = useState(null) // Set of valid merge-variable names
  const [utm, setUtm] = useState({})
  const [isMarketing, setIsMarketing] = useState(false)
  const [preview, setPreview] = useState(null) // { total, index, html, subject, contact }
  const [previewBusy, setPreviewBusy] = useState(false)
  const [testEmail, setTestEmail] = useState('')
  const [showPreview, setShowPreview] = useState(false)
  const [live, setLive] = useState(true)
  const [busy, setBusy] = useState('')          // 'save' | 'test' | 'send'
  const [msg, setMsg] = useState(null)          // { kind, text }
  const [loading, setLoading] = useState(true)
  const [sentHtml, setSentHtml] = useState(null)   // rendered HTML for a sent email view
  const pollRef = useRef(null)

  const load = useCallback(async () => {
    const c = await api.commsGetCampaign(id)
    setCampaign(c)
    setSubject(c.subject || '')
    setBody(c.body_html || '')
    setAudience(c.audience && c.audience.type ? c.audience : { type: 'all' })
    setUtm(c.utm || {})
    setTemplateId(c.template_id || '')
    return c
  }, [id])

  useEffect(() => {
    load()
      .then(c => {
        if (c.status === 'sending') startPolling()
        // For a sent/sending email, render it exactly as recipients see it
        // (through the same server render path), not the raw source.
        if (c.status !== 'draft') {
          api.commsPreviewCampaign(id, 0).then(r => setSentHtml(r.html)).catch(() => {})
        }
      })
      .catch(e => setMsg({ kind: 'error', text: e.message }))
      .finally(() => setLoading(false))
    api.commsListSegments().then(setSegments).catch(() => {})
    api.commsListLists().then(setLists).catch(() => {})
    api.commsListTemplates().then(setTemplates).catch(() => {})
    api.commsMergeVariables().then(v => {
      const names = new Set((v.variables || []).map(x => x.name))
      names.add('club_name')
      setKnownVars(names)
    }).catch(() => {})
    api.commsGetContext().then(c => setIsMarketing(!!c?.current?.is_marketing)).catch(() => {})
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
    const c = await api.commsUpdateCampaign(id, { subject, body_html: body, audience, utm, template_id: templateId || null })
    setCampaign(c)
    return c
  }

  // Consistency warnings, mirrored from the backend campaign_warnings() so the
  // editor and the Emails list agree: {{vars}} that aren't known merge variables,
  // and substituted UTM variables with no value set in UTM link tracking.
  const warnings = useMemo(() => {
    if (!knownVars) return campaign?.warnings || []
    const re = /\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g
    const used = new Set()
    let m
    while ((m = re.exec(`${subject || ''} ${body || ''}`)) !== null) used.add(m[1])
    const out = [...used].filter(v => !knownVars.has(v)).sort()
      .map(v => `Unknown variable {{${v}}} — it won't be replaced.`)
    for (const [key, label] of [['utm_source', 'Source'], ['utm_medium', 'Medium'], ['utm_campaign', 'Campaign']]) {
      if (used.has(key) && !String(utm[key] || '').trim()) {
        out.push(`Template uses {{${key}}} but no ${label} is set in UTM link tracking.`)
      }
    }
    return out
  }, [knownVars, subject, body, utm, campaign])

  // Render the email exactly as a real recipient in the audience will see it.
  // Saves the draft first so the server renders current content.
  const openPreview = async () => {
    setPreviewBusy(true); setMsg(null)
    try {
      await save()
      setPreview(await api.commsPreviewCampaign(id, 0))
    } catch (e) { setMsg({ kind: 'error', text: e.message }) }
    finally { setPreviewBusy(false) }
  }
  const pagePreview = async (delta) => {
    if (!preview) return
    const next = Math.max(0, Math.min((preview.total || 1) - 1, (preview.index || 0) + delta))
    if (next === preview.index) return
    setPreviewBusy(true)
    try { setPreview(await api.commsPreviewCampaign(id, next)) }
    catch (e) { setMsg({ kind: 'error', text: e.message }) }
    finally { setPreviewBusy(false) }
  }

  // Pick a template from the dropdown. Selecting the one that's already assigned
  // is a no-op (no spurious replace prompt); switching to a different one warns
  // only when there's existing content to overwrite.
  const onPickTemplate = async (tid) => {
    if (tid === templateId) return
    if (tid && body.trim() && !window.confirm('Replace the current message with this template?')) return
    setTemplateId(tid)
    if (!tid) return
    try {
      const t = await api.commsGetTemplate(tid)
      setBody(t.html || '')
    } catch (e) { setMsg({ kind: 'error', text: e.message }) }
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
      // Sending runs in the background; return to the Emails list where the
      // campaign shows its live sending → sent status (don't leave the user
      // stuck on the compose page).
      navigate('/admin/comms', { state: { sent: r.recipients } })
      return
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
            <div className="text-pb-faintest text-xs mb-2">Email as recipients see it</div>
            {sentHtml
              ? <iframe title="sent email" srcDoc={sentHtml} className="w-full rounded border pb-hairline bg-white" style={{ height: 520 }} />
              : <div className="text-pb-faint text-sm">Loading preview…</div>}
          </div>
        ) : (
          // ── Draft editor ────────────────────────────────────────────────
          <>
            <label className="block text-sm text-pb-faint mb-1">Subject</label>
            <input value={subject} onChange={e => setSubject(e.target.value)} placeholder="e.g. Round 5 — training this Thursday"
              className="w-full pb-input mb-4 px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline" />

            {templates.length > 0 && (
              <div className="mb-3">
                <label className="block text-xs text-pb-faint mb-1">Template</label>
                <select value={templateId} onChange={e => onPickTemplate(e.target.value)}
                  className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm">
                  <option value="">No template — write from scratch</option>
                  {templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
              </div>
            )}

            <div className="flex items-center justify-between mb-1">
              <label className="block text-sm text-pb-faint">Message</label>
              <button onClick={openPreview} disabled={previewBusy} className="text-xs text-pb-faint hover:text-pb-text underline disabled:opacity-50">
                {previewBusy ? 'Loading…' : 'Preview email'}
              </button>
            </div>

            <textarea value={body} onChange={e => setBody(e.target.value)} rows={10}
              placeholder={'Hi {{first_name}},\n\nWrite your message here…'}
              className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline font-sans text-sm mb-2" />
            <div className="text-pb-faintest text-xs mb-3">
              Personalise with <code className="text-pb-faint">{'{{first_name}}'}</code> and <code className="text-pb-faint">{'{{club}}'}</code>.
            </div>

            {warnings.length > 0 && (
              <div className="pb-card p-3 mb-5 border-l-2 border-amber-500/50">
                <div className="text-amber-500 text-xs font-medium mb-1">Check these before sending</div>
                <ul className="text-pb-faint text-xs space-y-0.5 list-disc pl-4">
                  {warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              </div>
            )}

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

            {isMarketing && (
              <div className="pb-card p-4 mb-4">
                <div className="text-sm text-pb-text mb-1">UTM link tracking</div>
                <div className="text-pb-faintest text-xs mb-3">
                  BetterCricket marketing only. Two ways to use these: leave them and they are added to every untagged link
                  automatically, or place them yourself in a link, e.g.{' '}
                  <code className="text-pb-faint">?utm_source=&#123;&#123;utm_code&#125;&#125;&amp;utm_medium=&#123;&#123;utm_medium&#125;&#125;&amp;utm_campaign=&#123;&#123;utm_campaign&#125;&#125;</code>.
                  A link you tag by hand is left as-is.
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  {[['utm_source', 'Source', 'e.g. bettercricket'], ['utm_medium', 'Medium', 'e.g. email'], ['utm_campaign', 'Campaign', 'e.g. winter-2026']].map(([k, label, ph]) => (
                    <div key={k}>
                      <label className="block text-xs text-pb-faint mb-1">{label}</label>
                      <input value={utm[k] || ''} onChange={e => setUtm(u => ({ ...u, [k]: e.target.value }))}
                        placeholder={ph}
                        className="w-full px-2 py-1.5 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm" />
                    </div>
                  ))}
                </div>
              </div>
            )}

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

      {preview && (
        <div className="fixed inset-0 z-50 flex items-start justify-center p-4 overflow-y-auto" style={{ background: 'rgba(0,0,0,0.5)' }} onClick={() => setPreview(null)}>
          <div className="bg-pb-surface border pb-hairline rounded-lg shadow-xl w-full max-w-2xl mt-[6vh]" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-3 pb-hairline-b gap-3">
              <div className="min-w-0">
                <div className="text-pb-text font-medium truncate">{preview.subject || '(no subject)'}</div>
                <div className="text-pb-faintest text-xs truncate">
                  {preview.contact
                    ? <>To {preview.contact.name || preview.contact.email} · contact {(preview.index || 0) + 1} of {preview.total}</>
                    : 'No audience selected yet — showing a sample recipient.'}
                </div>
              </div>
              <button onClick={() => setPreview(null)} className="text-pb-faint hover:text-pb-text text-lg px-1 shrink-0">✕</button>
            </div>
            <div className="p-3">
              <iframe title="email preview" srcDoc={preview.html} className="w-full rounded border pb-hairline bg-white" style={{ height: 460 }} />
              {preview.total > 1 && (
                <div className="flex items-center justify-between mt-3">
                  <button onClick={() => pagePreview(-1)} disabled={previewBusy || preview.index <= 0}
                    className="px-3 py-1.5 rounded text-sm border pb-hairline text-pb-text hover:bg-pb-surface2 disabled:opacity-40">← Previous</button>
                  <span className="text-pb-faintest text-xs">{(preview.index || 0) + 1} / {preview.total}</span>
                  <button onClick={() => pagePreview(1)} disabled={previewBusy || preview.index >= preview.total - 1}
                    className="px-3 py-1.5 rounded text-sm border pb-hairline text-pb-text hover:bg-pb-surface2 disabled:opacity-40">Next →</button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </BetterCommsLayout>
  )
}
