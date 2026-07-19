import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../../../lib/api'
import BetterCommsLayout from '../../../components/admin/BetterCommsLayout'
import EmailEditorTabs from '../../../components/admin/EmailEditorTabs'

const REQUEST_TEMPLATE_EMAIL = 'support@bettersports.com.au'
const REQUEST_TEMPLATE_BODY = `Hi BetterCricket team,

I've come across an email template I'd like to see added to BetterComms.

Paste the HTML below, or forward the original email to ${REQUEST_TEMPLATE_EMAIL}, and we'll take a look at adding it to the template library.

Thanks`
const REQUEST_TEMPLATE_MAILTO = `mailto:${REQUEST_TEMPLATE_EMAIL}?subject=${encodeURIComponent('New email template')}&body=${encodeURIComponent(REQUEST_TEMPLATE_BODY)}`

function fmtWhen(s) {
  if (!s) return ''
  try { return new Date(s).toLocaleString('en-AU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) }
  catch { return '' }
}

// Who, by name/email, is behind this campaign's bounced / unsub / spam counts —
// the aggregate badge on the Emails list has no drill-down otherwise. Tabs are
// lazy-loaded (only the filtered subset the operator actually wants, not the
// full send for a large campaign) and default to whichever problem exists.
function RecipientsPanel({ campaignId, unsubCount, bouncedCount }) {
  const [tab, setTab] = useState(unsubCount > 0 ? 'unsub_supp' : (bouncedCount > 0 ? 'bounced' : null))
  const [rows, setRows] = useState(null)
  const [loading, setLoading] = useState(false)
  const [loadedTab, setLoadedTab] = useState(null)

  useEffect(() => {
    if (!tab || tab === loadedTab) return
    setLoading(true)
    api.commsCampaignRecipients(campaignId, tab === 'all' ? null : tab)
      .then(r => { setRows(r.recipients || []); setLoadedTab(tab) })
      .catch(() => setRows([]))
      .finally(() => setLoading(false))
  }, [tab, campaignId, loadedTab])

  const TABS = [
    ['unsub_supp', `Unsubscribed / spam (${unsubCount})`],
    ['bounced', `Bounced (${bouncedCount})`],
    ['all', 'All recipients'],
  ]

  return (
    <div className="mt-4 pt-4 pb-hairline-t">
      <div className="flex items-center gap-1.5 mb-2 flex-wrap">
        <span className="text-pb-faintest text-[11px] uppercase tracking-wide2 mr-1">Recipients</span>
        {TABS.map(([v, label]) => (
          <button key={v} type="button" onClick={() => setTab(v)}
            className={`px-2.5 py-1 rounded text-xs border pb-hairline ${tab === v ? 'text-white' : 'text-pb-faint hover:text-pb-text'}`}
            style={tab === v ? { background: 'var(--pb-accent)' } : undefined}>
            {label}
          </button>
        ))}
      </div>
      {tab && (
        loading ? <div className="text-pb-faint text-sm">Loading…</div>
        : !rows || rows.length === 0 ? <div className="text-pb-faint text-sm">No contacts here.</div>
        : (
          <div className="pb-card overflow-hidden max-h-80 overflow-y-auto">
            {rows.map((r, i) => (
              <div key={r.id || r.email} className={`px-3 py-2 text-sm ${i > 0 ? 'pb-hairline-t' : ''}`}>
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0 truncate">
                    <span className="text-pb-text">{r.name || r.email}</span>
                    {r.name && <span className="text-pb-faintest text-xs ml-1.5">{r.email}</span>}
                  </div>
                  <div className="flex gap-1 shrink-0">
                    {r.unsubscribed && <span className="text-[10px] uppercase px-1.5 py-0.5 rounded border border-amber-500/40 text-amber-500">unsub</span>}
                    {r.complained && <span className="text-[10px] uppercase px-1.5 py-0.5 rounded border border-pb-red/40 text-pb-red">spam</span>}
                    {r.bounced && <span className="text-[10px] uppercase px-1.5 py-0.5 rounded border border-pb-red/40 text-pb-red">bounced</span>}
                  </div>
                </div>
                {r.events?.length > 0 && (
                  <div className="text-pb-faintest text-[11px] mt-0.5 truncate"
                    title={r.events.map(e => `${e.type}${e.subtype ? ` (${e.subtype})` : ''}${e.reason ? ` — ${e.reason}` : ''}`).join(' · ')}>
                    {r.events.map(e => `${e.type}${e.at ? ` · ${fmtWhen(e.at)}` : ''}`).join(' · ')}
                  </div>
                )}
              </div>
            ))}
          </div>
        )
      )}
    </div>
  )
}

export default function CommsCompose() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [campaign, setCampaign] = useState(null)
  const [subject, setSubject] = useState('')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [body, setBody] = useState('')
  const [audienceCount, setAudienceCount] = useState(null)
  // Start unselected — sending to "all subscribed" must be a deliberate choice.
  const [audience, setAudience] = useState({ type: '' })
  const [segments, setSegments] = useState([])
  const [lists, setLists] = useState([])
  const [templates, setTemplates] = useState([])
  const [templateId, setTemplateId] = useState('')
  const [knownVars, setKnownVars] = useState(null) // Set of valid merge-variable names
  const [utm, setUtm] = useState({})
  const [isMarketing, setIsMarketing] = useState(false)
  const [testEmail, setTestEmail] = useState('')
  const [live, setLive] = useState(true)
  const [busy, setBusy] = useState('')          // 'save' | 'test' | 'send'
  const [msg, setMsg] = useState(null)          // { kind, text }
  const [loading, setLoading] = useState(true)
  const [sentHtml, setSentHtml] = useState(null)   // rendered HTML for a sent email view
  const [editorKey, setEditorKey] = useState(0) // bumped to force-remount the editor when body is replaced wholesale
  const pollRef = useRef(null)
  const editorRef = useRef(null)
  const subjectInputRef = useRef(null)

  const load = useCallback(async () => {
    const c = await api.commsGetCampaign(id)
    setCampaign(c)
    setSubject(c.subject || '')
    setName(c.name || '')
    setDescription(c.description || '')
    setBody(c.body_html || '')
    setAudience(c.audience && ['all', 'segment', 'saved_list', 'list', 'squad'].includes(c.audience.type) ? c.audience : { type: '' })
    setUtm(c.utm || {})
    setTemplateId(c.template_id || '')
    setEditorKey(k => k + 1)
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

  // An audience is "selected" only once the user picks a concrete option (all,
  // or a specific segment/list). Empty type = not chosen yet.
  const audienceSelected = (
    audience.type === 'all'
    || (audience.type === 'segment' && audience.segment_id)
    || (audience.type === 'saved_list' && audience.list_id)
    || (audience.type === 'squad' && audience.team_id)
    || (audience.type === 'list' && (audience.contact_ids || []).length)
  )

  // Re-count whenever the chosen audience changes — but only once one is chosen.
  useEffect(() => {
    setAudienceCount(null)
    if (!audienceSelected) return
    api.commsAudiencePreview(audience).then(r => setAudienceCount(r.count)).catch(() => setAudienceCount(null))
  }, [audience, audienceSelected])

  // Send is only allowed once a subject, some content (a message or a template)
  // and a deliberate audience are all present — no accidental blasts to everyone.
  const sendMissing = []
  if (!subject.trim()) sendMissing.push('a subject')
  if (!(templateId || body.trim())) sendMissing.push('a message or template')
  if (!audienceSelected) sendMissing.push('an audience')
  const canSend = sendMissing.length === 0 && !!audienceCount

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

  const save = async (bodyOverride) => {
    const finalBody = bodyOverride ?? body
    const c = await api.commsUpdateCampaign(id, { subject, name, description, body_html: finalBody, audience, utm, template_id: templateId || null })
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
  // Saves the draft first (with the freshest content) so the server renders it.
  const onEnterPreview = async ({ html: currentBody, index }) => {
    await save(currentBody)
    const r = await api.commsPreviewCampaign(id, index)
    return {
      html: r.html || '',
      total: r.total || 1,
      index: r.index ?? index,
      label: r.contact
        ? `To ${r.contact.name || r.contact.email} · contact ${(r.index ?? index) + 1} of ${r.total}`
        : 'No audience selected yet — showing a sample recipient.',
    }
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
      setEditorKey(k => k + 1)
    } catch (e) { setMsg({ kind: 'error', text: e.message }) }
  }

  const onSave = async () => {
    setBusy('save'); setMsg(null)
    try { await save(editorRef.current?.flush()); setMsg({ kind: 'ok', text: 'Draft saved.' }) }
    catch (e) { setMsg({ kind: 'error', text: e.message }) }
    finally { setBusy('') }
  }

  const onTest = async () => {
    if (!testEmail.trim()) { setMsg({ kind: 'error', text: 'Enter an email to send the test to.' }); return }
    setBusy('test'); setMsg(null)
    try {
      await save(editorRef.current?.flush())
      const r = await api.commsTestCampaign(id, testEmail.trim())
      setMsg({ kind: 'ok', text: r.live ? `Test sent to ${testEmail.trim()}.` : `Test rendered (preview mode — not delivered).` })
    } catch (e) { setMsg({ kind: 'error', text: e.message }) }
    finally { setBusy('') }
  }

  const onSend = async () => {
    const finalBody = editorRef.current?.flush() ?? body
    if (!subject.trim()) { setMsg({ kind: 'error', text: 'Add a subject before sending.' }); return }
    if (!audienceSelected) { setMsg({ kind: 'error', text: 'Choose an audience before sending.' }); return }
    if (!(templateId || finalBody.trim())) { setMsg({ kind: 'error', text: 'Add a message (or pick a template) before sending.' }); return }
    const n = audienceCount ?? 0
    const who = audience.type === 'all' ? 'ALL subscribed contacts' : 'the selected audience'
    if (!window.confirm(`Send this email to ${n} contact${n === 1 ? '' : 's'} (${who})?`)) return
    setBusy('send'); setMsg(null)
    try {
      await save(finalBody)
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
            <div className="text-pb-text font-medium">{campaign.name || campaign.subject || '(no subject)'}</div>
            {campaign.description && <div className="text-pb-faint text-xs mt-0.5">{campaign.description}</div>}
            {campaign.name && campaign.subject && campaign.name !== campaign.subject && (
              <div className="text-pb-faintest text-xs mt-0.5">Subject: {campaign.subject}</div>
            )}
            <div className="grid grid-cols-3 gap-3 mt-4 text-center">
              <div className="pb-card p-3"><div className="text-xl font-display font-bold text-pb-text">{st.recipients ?? 0}</div><div className="text-pb-faintest text-xs">recipients</div></div>
              <div className="pb-card p-3"><div className="text-xl font-display font-bold text-green-500">{st.sent ?? 0}</div><div className="text-pb-faintest text-xs">delivered</div></div>
              <div className="pb-card p-3"><div className="text-xl font-display font-bold text-pb-red">{st.failed ?? 0}</div><div className="text-pb-faintest text-xs">failed</div></div>
            </div>
            {campaign.status === 'sending' && <div className="text-pb-faint text-sm mt-3">Sending in progress…</div>}
            {campaign.error && <div className="text-pb-red text-sm mt-3">{campaign.error}</div>}
            {campaign.status !== 'sending' && (
              <RecipientsPanel campaignId={id}
                unsubCount={campaign.engagement?.unsub_supp ?? 0}
                bouncedCount={campaign.engagement?.bounced ?? 0} />
            )}
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
            <input ref={subjectInputRef} value={subject} onChange={e => setSubject(e.target.value)} placeholder="e.g. Round 5 — training this Thursday"
              className="w-full pb-input mb-4 px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline" />

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
              <div>
                <label className="block text-sm text-pb-faint mb-1">Name <span className="text-pb-faintest">(optional)</span></label>
                <input value={name} onChange={e => setName(e.target.value)}
                  placeholder="Leave blank to auto-name from the subject + date/time"
                  className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm" />
              </div>
              <div>
                <label className="block text-sm text-pb-faint mb-1">Description <span className="text-pb-faintest">(optional)</span></label>
                <input value={description} onChange={e => setDescription(e.target.value)}
                  placeholder="A short note about this email"
                  className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm" />
              </div>
            </div>

            <div className="mb-3">
              <label className="block text-xs text-pb-faint mb-1">Template</label>
              <div className="flex items-center gap-2">
                {templates.length > 0 ? (
                  <select value={templateId} onChange={e => onPickTemplate(e.target.value)}
                    className="flex-1 min-w-0 px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm">
                    <option value="">No template — write from scratch</option>
                    {templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                  </select>
                ) : (
                  <div className="flex-1 min-w-0 px-3 py-2 rounded bg-pb-surface2 text-pb-faint border pb-hairline text-sm">
                    No templates yet
                  </div>
                )}
                <a href={REQUEST_TEMPLATE_MAILTO}
                  className="shrink-0 px-3 py-2 rounded text-sm border pb-hairline text-pb-text hover:bg-pb-surface2 whitespace-nowrap">
                  Request a template
                </a>
              </div>
            </div>

            <label className="block text-sm text-pb-faint mb-1">Message</label>
            <EmailEditorTabs key={editorKey} ref={editorRef} html={body} onChange={setBody} onEnterPreview={onEnterPreview} height={560}
              subject={subject} onSubjectChange={setSubject} subjectInputRef={subjectInputRef} />
            <div className="text-pb-faintest text-xs mb-3 mt-1">
              Personalise with <code className="text-pb-faint">{'{{first_name}}'}</code> and <code className="text-pb-faint">{'{{club}}'}</code>.
              Switching out of HTML mode tidies the code automatically; Preview renders it exactly as a send would.
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
                  : audience.type === 'saved_list' ? `list:${audience.list_id}`
                  : audience.type === 'all' ? 'all' : ''}
                onChange={e => {
                  const v = e.target.value
                  if (v.startsWith('segment:')) setAudience({ type: 'segment', segment_id: v.slice(8) })
                  else if (v.startsWith('list:')) setAudience({ type: 'saved_list', list_id: v.slice(5) })
                  else if (v === 'all') setAudience({ type: 'all' })
                  else setAudience({ type: '' })
                }}
                className={`w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border text-sm ${audienceSelected ? 'pb-hairline' : 'border-amber-500/60'}`}>
                <option value="" disabled>Choose an audience…</option>
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
                {!audienceSelected
                  ? <span className="text-amber-500">Choose who this goes to before sending.</span>
                  : audienceCount != null
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

            <div className="flex flex-wrap items-center gap-2 mb-2">
              <button onClick={onSave} disabled={busy === 'save'}
                className="px-3 py-2 rounded text-sm border pb-hairline text-pb-text hover:bg-pb-surface2 disabled:opacity-60">
                {busy === 'save' ? 'Saving…' : 'Save draft'}
              </button>
              <button onClick={onSend} disabled={!!busy || !canSend}
                title={sendMissing.length ? `Add ${sendMissing.join(', ')} to send` : ''}
                className="px-4 py-2 rounded text-sm font-medium text-white disabled:opacity-50"
                style={{ background: 'var(--pb-accent)' }}>
                {busy === 'send' ? 'Sending…' : `Send${audienceSelected && audienceCount != null ? ` to ${audienceCount}` : ''}`}
              </button>
              <button onClick={onDelete} className="px-3 py-2 rounded text-sm text-pb-faint hover:text-pb-red ml-auto">Delete</button>
            </div>
            <div className="text-pb-faintest text-xs mb-6">
              {sendMissing.length > 0 ? <>Add {sendMissing.join(', ')} to enable Send.</> : <>&nbsp;</>}
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
