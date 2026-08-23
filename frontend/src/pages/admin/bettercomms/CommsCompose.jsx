import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { api } from '../../../lib/api'
import { Button, Caption, SectionHeading, Note, Badge, Empty, FilterPill, INPUT_CLS } from '../../../components/admin/ui'
import EmailEditorTabs from '../../../components/admin/EmailEditorTabs'
import { RecordTitleRow, CountBar, SaveRow } from '../clubhouse/crudShell'

// One email, in the detail pane of the Emails screen.
//
// This was its own page at /admin/comms/:id, with its own header and a "← All
// emails" button as the only way back. It is the right-hand pane of the Emails
// master–detail now (CommsCampaigns.jsx), so the club's other emails stay
// visible beside the one being written — the same shape Segments, Lists and
// Templates use. The URL is unchanged: /admin/comms/:id still opens straight
// onto this record, which is what every "Email these N now" button relies on.
//
// Nothing about what it does changed: subject, name, description, template,
// message, audience, UTM tracking, warnings, test send, send, delete, and the
// sent-email summary with its recipient drill-down are all still here.

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
        <Caption className="mr-1">Recipients</Caption>
        {TABS.map(([v, label]) => (
          <FilterPill key={v} active={tab === v} onClick={() => setTab(v)}>{label}</FilterPill>
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
                    {r.unsubscribed && <Badge toneKey="warn">Unsub</Badge>}
                    {r.complained && <Badge toneKey="block">Spam</Badge>}
                    {r.bounced && <Badge toneKey="block">Bounced</Badge>}
                  </div>
                </div>
                {r.events?.length > 0 && (
                  <div className="text-pb-faintest text-[11px] mt-0.5 truncate"
                    title={r.events.map(e => `${e.type}${e.subtype ? ` (${e.subtype})` : ''}${e.reason ? `, ${e.reason}` : ''}`).join(' · ')}>
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

export default function EmailDetail({ id, onChanged, onDeleted, onSent }) {
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
    onChanged?.()
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
      .map(v => `Unknown variable {{${v}}}. It won't be replaced.`)
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
      subject: r.subject || '',
      total: r.total || 1,
      index: r.index ?? index,
      label: r.contact
        ? `To ${r.contact.name || r.contact.email} · contact ${(r.index ?? index) + 1} of ${r.total}`
        : 'No audience selected yet, showing a sample recipient.',
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
      setMsg({ kind: 'ok', text: r.live ? `Test sent to ${testEmail.trim()}.` : `Test rendered (preview mode, not delivered).` })
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
      // Sending runs in the background; hand back to the Emails list, where the
      // campaign shows its live sending → sent status.
      onSent?.(r.recipients)
      return
    } catch (e) { setMsg({ kind: 'error', text: e.message }) }
    finally { setBusy('') }
  }

  // Drafts and sent emails are both deletable — the Emails list used to carry
  // the delete for anything that was not mid-send, and a sent email's record is
  // the club's to keep or clear. Only a send in flight is off limits.
  const onDelete = async () => {
    const sent = campaign && campaign.status !== 'draft'
    const label = campaign?.name?.trim() || campaign?.subject?.trim() || 'this email'
    const prompt = sent
      ? `Delete "${label}"? It has already been sent. This removes the club's record of it and can't be undone.`
      : 'Delete this draft?'
    if (!window.confirm(prompt)) return
    try { await api.commsDeleteCampaign(id); onDeleted?.() }
    catch (e) { setMsg({ kind: 'error', text: e.message }) }
  }

  if (loading) return <Empty>Loading…</Empty>
  if (!campaign) return <Note toneKey="block">{msg?.text || 'Not found.'}</Note>

  const isDraft = campaign.status === 'draft'
  const st = campaign.stats || {}

  return (
    <>
      {msg && (
        <Note toneKey={msg.kind === 'error' ? 'block' : 'ok'} className="mb-4">{msg.text}</Note>
      )}

      {!isDraft ? (
        // ── Sent / sending / error summary ────────────────────────────────
        <>
          <RecordTitleRow
            readOnly name={campaign.name || campaign.subject} placeholder="(no subject)"
            blurb={campaign.description || (
              campaign.status === 'sending' ? 'This email is going out now.'
                : campaign.status === 'error' ? 'This send hit an error. The detail is below.'
                : "This email has gone out. It is the club's record of what was sent, so nothing here can be edited."
            )}
            actions={<Badge toneKey={campaign.status === 'error' ? 'block' : campaign.status === 'sending' ? 'accent' : 'ok'}>
              {campaign.status}
            </Badge>}
          />
          {campaign.name && campaign.subject && campaign.name !== campaign.subject && (
            <div className="text-pb-faintest text-xs mt-2">Subject: {campaign.subject}</div>
          )}
          {campaign.utm?.utm_campaign && (
            <div className="text-[11px] font-mono mt-1 truncate" title={`utm_campaign=${campaign.utm.utm_campaign}`}>
              <span className="text-pb-faintest">utm_campaign=</span><span className="text-pb-faint">{campaign.utm.utm_campaign}</span>
            </div>
          )}

          {/* Nothing on a sent email can be edited, so there is no Save — but it
              can still be deleted, which is what the Emails list used to offer
              on the row itself. */}
          {campaign.status !== 'sending' && (
            <SaveRow onDelete={onDelete} deleteLabel="Delete this email" />
          )}

          <div className="pb-card p-5 mt-5 max-w-2xl">
            <div className="grid grid-cols-3 gap-3 text-center">
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
        </>
      ) : (
        // ── Draft editor ──────────────────────────────────────────────────
        <>
          {/* The subject is the email's identity the way a name is a segment's,
              so it is edited where it is read. Name and description stay as
              their own fields below: they label the email for the club's own
              records, the subject is what a recipient sees. */}
          <RecordTitleRow
            name={subject} onName={setSubject} inputRef={subjectInputRef}
            placeholder="e.g. Round 5: training this Thursday"
            blurb="The subject line recipients see in their inbox."
            actions={<Button variant="primary" onClick={onSend} disabled={!!busy || !canSend}
              title={sendMissing.length ? `Add ${sendMissing.join(', ')} to send` : ''}>
              {busy === 'send' ? 'Sending…' : `Send${audienceSelected && audienceCount != null ? ` to ${audienceCount}` : ''}`}
            </Button>}
          />

          <div className="max-w-2xl">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-5 mb-4">
              <div>
                <Caption className="mb-1.5">Name (optional)</Caption>
                <input value={name} onChange={e => setName(e.target.value)}
                  placeholder="Leave blank to auto-name from the subject + date/time"
                  className={INPUT_CLS} />
              </div>
              <div>
                <Caption className="mb-1.5">Description (optional)</Caption>
                <input value={description} onChange={e => setDescription(e.target.value)}
                  placeholder="A short note about this email"
                  className={INPUT_CLS} />
              </div>
            </div>

            <div className="mb-3">
              <Caption className="mb-1.5">Template</Caption>
              <div className="flex items-center gap-2">
                {templates.length > 0 ? (
                  <select value={templateId} onChange={e => onPickTemplate(e.target.value)}
                    className={`${INPUT_CLS} cursor-pointer flex-1 min-w-0`}>
                    <option value="">No template: write from scratch</option>
                    {templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                  </select>
                ) : (
                  <div className={`${INPUT_CLS} flex-1 min-w-0 text-pb-faint`}>No templates yet</div>
                )}
                <Button as="a" href={REQUEST_TEMPLATE_MAILTO}>Request a template</Button>
              </div>
            </div>

            <Caption className="mb-1.5">Message</Caption>
            <EmailEditorTabs key={editorKey} ref={editorRef} html={body} onChange={setBody} onEnterPreview={onEnterPreview} height={560}
              subject={subject} onSubjectChange={setSubject} subjectInputRef={subjectInputRef} />
            <div className="text-pb-faintest text-xs mb-3 mt-1">
              Personalise with <code className="text-pb-faint">{'{{first_name}}'}</code> and <code className="text-pb-faint">{'{{club}}'}</code>.
              Switching out of HTML mode tidies the code automatically; Preview renders it exactly as a send would.
            </div>

            {warnings.length > 0 && (
              <Note toneKey="warn" title="Check these before sending" className="mb-5">
                <ul className="space-y-0.5 list-disc pl-4">
                  {warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              </Note>
            )}

            <div className="pb-card p-4 mb-4">
              {/* One slot, filled by one of the club's segments or lists. That
                  is the whole vocabulary: an email has an audience; the
                  audience is a segment or a list. */}
              <SectionHeading className="mb-2">Audience</SectionHeading>
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
                className={`${INPUT_CLS} cursor-pointer ${audienceSelected ? '' : '!border-amber-500/60'}`}>
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
                <a href="/admin/comms/segments" className="underline" style={{ color: 'var(--pb-accent-ink)' }}>Segments</a>
                {' · '}
                <a href="/admin/comms/lists" className="underline" style={{ color: 'var(--pb-accent-ink)' }}>Lists</a>
              </div>
            </div>

            {isMarketing && (
              <div className="pb-card p-4 mb-4">
                <SectionHeading className="mb-1.5">UTM link tracking</SectionHeading>
                <div className="text-pb-faintest text-xs mb-3">
                  BetterCricket marketing only. Two ways to use these: leave them and they are added to every untagged link
                  automatically, or place them yourself in a link, e.g.{' '}
                  <code className="text-pb-faint">?utm_source=&#123;&#123;utm_code&#125;&#125;&amp;utm_medium=&#123;&#123;utm_medium&#125;&#125;&amp;utm_campaign=&#123;&#123;utm_campaign&#125;&#125;</code>.
                  A link you tag by hand is left as-is.
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  {[['utm_source', 'Source', 'e.g. bettercricket'], ['utm_medium', 'Medium', 'e.g. email'], ['utm_campaign', 'Campaign', 'e.g. winter-2026']].map(([k, label, ph]) => (
                    <div key={k}>
                      <Caption className="mb-1.5">{label}</Caption>
                      <input value={utm[k] || ''} onChange={e => setUtm(u => ({ ...u, [k]: e.target.value }))}
                        placeholder={ph} className={INPUT_CLS} />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* The same live readout a segment gives, answering the same
                question: who is this actually going to, right now. */}
            <CountBar>
              {sendMissing.length > 0 ? (
                <span className="text-pb-dim">Add {sendMissing.join(', ')} to enable Send.</span>
              ) : (
                <span className="text-pb-dim">
                  <b style={{ color: 'var(--pb-accent-ink)' }}>{audienceCount ?? '—'}</b>
                  {' '}contact{audienceCount === 1 ? '' : 's'} will receive this. Nothing sends until you press Send.
                </span>
              )}
            </CountBar>

            <SaveRow
              onSave={onSave} busy={busy === 'save'}
              saveLabel={busy === 'save' ? 'Saving…' : 'Save draft'}
              onDelete={onDelete} deleteLabel="Delete"
            />

            <SectionHeading className="mt-8 mb-2.5">Send a test to yourself first</SectionHeading>
            <div className="pb-card p-4">
              <div className="flex gap-2">
                <input value={testEmail} onChange={e => setTestEmail(e.target.value)} placeholder="you@example.com" type="email"
                  className={INPUT_CLS} />
                <Button onClick={onTest} disabled={busy === 'test'}>{busy === 'test' ? 'Sending…' : 'Send test'}</Button>
              </div>
              {!live && <div className="text-pb-faintest text-xs mt-2">Preview mode. Tests are rendered but not delivered until a provider is connected in Settings.</div>}
            </div>
          </div>
        </>
      )}
    </>
  )
}
