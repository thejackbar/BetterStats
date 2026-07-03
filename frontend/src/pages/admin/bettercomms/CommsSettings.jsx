import { useState, useEffect } from 'react'
import { api } from '../../../lib/api'
import BetterCommsLayout from '../../../components/admin/BetterCommsLayout'

const SUPPRESSION_LABEL = {
  hard_bounce: 'Bounced (address undeliverable)',
  complaint: 'Marked as spam',
  manual: 'Suppressed manually',
}

export default function CommsSettings() {
  const [s, setS] = useState(null)
  const [fromName, setFromName] = useState('')
  const [fromLocal, setFromLocal] = useState('')
  const [replyTo, setReplyTo] = useState('')
  const [footer, setFooter] = useState('')
  const [msg, setMsg] = useState(null)
  const [saving, setSaving] = useState(false)
  const [suppressions, setSuppressions] = useState(null)
  const [ses, setSes] = useState(null)            // super-admin SES status (null = not loaded / not super)
  const [testEmail, setTestEmail] = useState('')
  const [testBusy, setTestBusy] = useState(false)
  const [limits, setLimits] = useState(null)      // sending tier + usage + deliverability
  const [reqReason, setReqReason] = useState('')
  const [reqBusy, setReqBusy] = useState(false)
  const [tenantBusy, setTenantBusy] = useState(false)

  useEffect(() => {
    api.commsGetSettings().then(d => {
      setS(d)
      setFromName(d.from_name || '')
      setFromLocal(d.from_local || '')
      setReplyTo(d.reply_to || '')
      setFooter(d.sender_footer || '')
    }).catch(e => setMsg({ kind: 'error', text: e.message }))
    api.commsListSuppressions().then(setSuppressions).catch(() => setSuppressions([]))
    // Super-admin only; a 403 for club admins just leaves the panel hidden.
    api.commsSesStatus().then(setSes).catch(() => setSes(null))
    api.commsGetLimits().then(setLimits).catch(() => setLimits(null))
  }, [])

  const provisionTenants = async () => {
    setTenantBusy(true); setMsg(null)
    try {
      const r = await api.commsProvisionTenants(false)
      let text = `Tenants: ${r.provisioned || 0} provisioned, ${r.failed || 0} failed of ${r.total || 0}.`
      if (r.failed && r.errors?.length) {
        const e0 = r.errors[0]
        text += ` First failure — ${e0.club}: ${e0.reason || 'see logs'}. ${r.failed > 1 ? 'Run again to retry the rest.' : ''}`
      }
      setMsg({ kind: r.failed ? 'error' : 'ok', text })
      api.commsSesStatus().then(setSes).catch(() => {})
    } catch (e) { setMsg({ kind: 'error', text: e.message }) }
    finally { setTenantBusy(false) }
  }

  const requestLimit = async () => {
    setReqBusy(true); setMsg(null)
    try {
      await api.commsRequestLimit({ reason: reqReason.trim() || null })
      setReqReason('')
      const fresh = await api.commsGetLimits()
      setLimits(fresh)
      setMsg({ kind: 'ok', text: 'Request sent to BetterCricket. We\'ll review your sending and lift the limit if all looks healthy.' })
    } catch (e) { setMsg({ kind: 'error', text: e.message }) }
    finally { setReqBusy(false) }
  }

  const sendTest = async () => {
    if (!testEmail.trim()) { setMsg({ kind: 'error', text: 'Enter an email to send the test to.' }); return }
    setTestBusy(true); setMsg(null)
    try {
      const r = await api.commsSendTestEmail(testEmail.trim())
      setMsg({ kind: 'ok', text: r.live ? `Test sent to ${testEmail.trim()} via ${r.provider}.` : 'Test rendered (preview mode — not delivered until a provider is connected).' })
    } catch (e) { setMsg({ kind: 'error', text: e.message }) }
    finally { setTestBusy(false) }
  }

  const noReply = (replyTo || '').toLowerCase().startsWith('noreply@')

  const unsuppress = async (email) => {
    setMsg(null)
    try {
      await api.commsRemoveSuppression(email)
      setSuppressions(list => (list || []).filter(r => r.email !== email))
      setMsg({ kind: 'ok', text: `${email} can be emailed again.` })
    } catch (e) { setMsg({ kind: 'error', text: e.message }) }
  }

  const save = async () => {
    setSaving(true); setMsg(null)
    try {
      const r = await api.commsSetSettings({ from_name: fromName, reply_to: replyTo, sender_footer: footer, from_local: fromLocal })
      if (r?.from_address) setS(prev => prev ? { ...prev, from_address: r.from_address } : prev)
      setMsg({ kind: 'ok', text: 'Saved.' })
    } catch (e) { setMsg({ kind: 'error', text: e.message }) }
    finally { setSaving(false) }
  }

  if (!s) return <BetterCommsLayout title="Settings"><div className="text-pb-faint text-sm">Loading…</div></BetterCommsLayout>

  const p = s.provider || {}
  // Platform (super-admin, BetterCricket marketing context) sees the underlying
  // mail-service internals; an ordinary club only sees that email is connected.
  const isPlatform = !!ses && !!limits?.is_outreach

  return (
    <BetterCommsLayout title="Settings">
      <div className="max-w-2xl">
        {msg && <div className={`pb-card p-3 mb-4 text-sm ${msg.kind === 'error' ? 'text-pb-red' : 'text-green-500'}`}>{msg.text}</div>}

        {/* Provider / connection status */}
        <div className="pb-card p-4 mb-4">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm text-pb-text font-medium">Email delivery</div>
              <div className="text-pb-faint text-sm mt-0.5">
                {p.live
                  ? (isPlatform
                      ? <>Connected via <span className="text-pb-text capitalize">{p.provider}</span> · sending from <span className="text-pb-text">{s.from_address || p.from_address}</span></>
                      : <>Your club's outbound email is live and being delivered.</>)
                  : <>Preview mode — emails are rendered and logged but <strong>not delivered</strong>.</>}
              </div>
            </div>
            <span className={`font-mono text-[10px] uppercase tracking-wide2 border rounded px-2 py-0.5 ${p.live ? 'text-green-500 border-green-500/40' : 'text-amber-500 border-amber-500/40'}`}>
              {p.live ? 'Live' : 'Preview'}
            </span>
          </div>
          {!p.live && (
            <div className="text-pb-faintest text-xs mt-3 leading-relaxed">
              To go live (free): create a Brevo or Resend account, then set <code className="text-pb-faint">EMAIL_PROVIDER</code> and
              <code className="text-pb-faint"> EMAIL_API_KEY</code> on the server and verify the sending domain's DNS (SPF/DKIM/DMARC).
              This is a one-time server step.
            </div>
          )}
        </div>

        {/* Sending limits — the club's tier, daily usage and deliverability */}
        {limits && (() => {
          const TIER_LABEL = { sandbox: 'Sandbox', production: 'Production', suspended: 'Suspended' }
          const TIER_STYLE = {
            sandbox: 'text-amber-500 border-amber-500/40',
            production: 'text-green-500 border-green-500/40',
            suspended: 'text-pb-red border-pb-red/40',
          }
          const m = limits.metrics || {}
          const pct = (v) => `${((v || 0) * 100).toFixed(v >= 0.01 ? 1 : 2)}%`
          return (
            <div className="pb-card p-4 mb-4">
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm text-pb-text font-medium">Sending limits</div>
                <span className={`font-mono text-[10px] uppercase tracking-wide2 border rounded px-2 py-0.5 ${TIER_STYLE[limits.tier] || ''}`}>
                  {TIER_LABEL[limits.tier] || limits.tier}
                </span>
              </div>

              {limits.blocked && (
                <div className="text-pb-red text-xs mb-3 leading-relaxed">{limits.blocked}</div>
              )}

              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm mb-3">
                <div className="flex justify-between gap-2"><span className="text-pb-faint">Sent today</span><span className="text-pb-text">{limits.sent_today}</span></div>
                <div className="flex justify-between gap-2"><span className="text-pb-faint">Daily limit</span><span className="text-pb-text">{limits.daily_cap == null ? 'Unlimited' : limits.daily_cap}</span></div>
                <div className="flex justify-between gap-2"><span className="text-pb-faint">Bounce rate</span><span className="text-pb-text">{m.sufficient_sample ? pct(m.bounce_rate) : '—'}</span></div>
                <div className="flex justify-between gap-2"><span className="text-pb-faint">Spam rate</span><span className="text-pb-text">{m.sufficient_sample ? pct(m.complaint_rate) : '—'}</span></div>
              </div>
              <div className="text-pb-faintest text-xs leading-relaxed mb-3">
                {limits.tier === 'sandbox'
                  ? `New clubs start with a ${limits.daily_cap}-a-day limit while your sending settles in. Once you've sent cleanly, ask BetterCricket to lift it.`
                  : limits.tier === 'suspended'
                    ? 'Sending is paused because too many emails bounced or were marked as spam. Contact BetterCricket to review and restore it.'
                    : 'Anything over the daily limit sends automatically the next day, so nothing is lost.'}
              </div>

              {limits.open_request ? (
                <div className="text-xs text-pb-faint border-t pb-hairline-t pt-3">
                  Request pending review — sent {limits.open_request.requested_at ? new Date(limits.open_request.requested_at).toLocaleDateString() : ''}.
                </div>
              ) : limits.can_request ? (
                <div className="border-t pb-hairline-t pt-3">
                  <label className="block text-xs text-pb-faint mb-1">Ask BetterCricket to lift your limit (optional note)</label>
                  <textarea value={reqReason} onChange={e => setReqReason(e.target.value)} rows={2}
                    placeholder="e.g. 300-member club, weekly newsletter to our own members"
                    className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm mb-2" />
                  <button onClick={requestLimit} disabled={reqBusy}
                    className="px-3 py-2 rounded text-sm font-medium text-white disabled:opacity-60" style={{ background: 'var(--pb-accent)' }}>
                    {reqBusy ? 'Sending…' : 'Request higher limit'}
                  </button>
                </div>
              ) : null}
            </div>
          )
        })()}

        {/* AWS SES status — super admins only (the panel is hidden otherwise) */}
        {isPlatform && (
          <div className="pb-card p-4 mb-4">
            <div className="flex items-center justify-between mb-2">
              <div className="text-sm text-pb-text font-medium">Amazon SES (platform)</div>
              <span className={`font-mono text-[10px] uppercase tracking-wide2 border rounded px-2 py-0.5 ${ses.ses?.access_key_configured ? 'text-green-500 border-green-500/40' : 'text-amber-500 border-amber-500/40'}`}>
                {ses.ses?.access_key_configured ? 'Connected' : 'Not configured'}
              </span>
            </div>
            <div className="text-pb-faintest text-xs mb-3 leading-relaxed">
              AWS credentials live in server config and are never shown here. This is read-only status. To change them, update the server <code className="text-pb-faint">SES_*</code> environment values.
            </div>
            {[
              ['Active provider', ses.provider],
              ['Region', ses.ses?.region],
              ['Club sending domain', ses.ses?.club_domain],
              ['Marketing sending domain', ses.ses?.marketing_domain],
              ['Campaign configuration set', ses.ses?.configuration_set || 'not set'],
              ['Transactional configuration set', ses.ses?.configuration_set_transactional || 'not set'],
              ['SNS signature verification', ses.ses?.sns_signature_verification ? 'on' : 'off'],
              ['Event webhook token', ses.ses?.event_webhook_token_set ? 'set' : 'not set'],
              ['Per-club tenants', ses.tenants?.provisioning_configured
                ? `${ses.tenants.provisioned_clubs} provisioned${ses.tenants.paused_clubs ? `, ${ses.tenants.paused_clubs} paused` : ''}`
                : 'not configured'],
              ['Tenant sends', ses.tenants?.sends_enabled ? 'enabled' : 'off (provisioning only)'],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3 py-0.5 text-sm">
                <span className="text-pb-faint">{k}</span>
                <span className="text-pb-text truncate">{String(v ?? '—')}</span>
              </div>
            ))}
            {ses.tenants?.provisioning_configured && (
              <div className="mt-3 pt-3 border-t pb-hairline flex items-center gap-2">
                <button onClick={provisionTenants} disabled={tenantBusy}
                  className="px-3 py-1.5 rounded text-xs border pb-hairline text-pb-text hover:bg-pb-surface2 disabled:opacity-60">
                  {tenantBusy ? 'Provisioning…' : 'Provision club tenants'}
                </button>
                <span className="text-pb-faintest text-xs">Creates an SES tenant for every club (idempotent).</span>
              </div>
            )}
          </div>
        )}

        {/* Sender identity */}
        <div className="pb-card p-4 mb-4">
          <div className="text-sm text-pb-text font-medium mb-3">Sender</div>
          <label className="block text-xs text-pb-faint mb-1">From name</label>
          <input value={fromName} onChange={e => setFromName(e.target.value)} placeholder={s.from_name}
            className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm mb-3" />
          {p.live && p.provider === 'ses' && (
            <>
              <label className="block text-xs text-pb-faint mb-1">Sending address</label>
              <div className="flex items-center gap-2 mb-1">
                <input value={fromLocal} onChange={e => setFromLocal(e.target.value.toLowerCase().replace(/[^a-z0-9._-]/g, ''))}
                  placeholder={(s.from_address || '').split('@')[0] || 'hello'}
                  className="flex-1 px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm" />
                <span className="text-pb-faint text-sm shrink-0">@{(s.from_address || '').split('@')[1] || ''}</span>
              </div>
              <div className="text-pb-faintest text-xs mb-3">
                The part before the @. Blank uses your club's short code. Currently sending from <span className="text-pb-faint">{s.from_address}</span>.
              </div>
            </>
          )}
          <label className="flex items-center gap-2 mb-2 text-xs text-pb-faint cursor-pointer">
            <input type="checkbox" checked={noReply}
              onChange={e => setReplyTo(e.target.checked ? 'noreply@betteradmin-comms.work' : '')} />
            No-reply address (replies are not monitored)
          </label>
          <label className="block text-xs text-pb-faint mb-1">Reply-to email</label>
          <input value={replyTo} onChange={e => setReplyTo(e.target.value)} placeholder="committee@yourclub.org.au" type="email"
            className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm" />
          <div className="text-pb-faintest text-xs mt-1">Replies go here. Defaults to your club contact email. Tick no-reply to send from an unmonitored address.</div>
        </div>

        {/* Compliance footer */}
        <div className="pb-card p-4 mb-4">
          <div className="text-sm text-pb-text font-medium mb-1">Email footer</div>
          <div className="text-pb-faintest text-xs mb-3 leading-relaxed">
            Australian law (Spam Act 2003) requires every email to identify the sender and offer a one-click
            unsubscribe. The unsubscribe link is added automatically — put your club's legal name and a
            contact or postal line here so recipients know who it's from.
          </div>
          <textarea value={footer} onChange={e => setFooter(e.target.value)} rows={3}
            placeholder={`${s.from_name} Cricket Club\nABN 00 000 000 000 · PO Box 1, Suburb WA 6000`}
            className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm" />
        </div>

        <div className="flex items-center gap-3">
          <button onClick={save} disabled={saving}
            className="px-4 py-2 rounded text-sm font-medium text-white disabled:opacity-60" style={{ background: 'var(--pb-accent)' }}>
            {saving ? 'Saving…' : 'Save settings'}
          </button>
          <span className="text-pb-faintest text-xs">{s.subscribed_contacts} subscribed contact{s.subscribed_contacts === 1 ? '' : 's'}</span>
        </div>

        {/* Send a test email */}
        <div className="pb-card p-4 mt-4">
          <div className="text-sm text-pb-text font-medium mb-1">Send a test email</div>
          <div className="text-pb-faintest text-xs mb-3">Checks the connection by sending a test to an address you choose, using the current sender settings. Save your changes first.</div>
          <div className="flex gap-2">
            <input value={testEmail} onChange={e => setTestEmail(e.target.value)} placeholder="you@example.com" type="email"
              className="flex-1 px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm" />
            <button onClick={sendTest} disabled={testBusy}
              className="px-3 py-2 rounded text-sm border pb-hairline text-pb-text hover:bg-pb-surface2 disabled:opacity-60">
              {testBusy ? 'Sending…' : 'Send test'}
            </button>
          </div>
          {!p.live && <div className="text-pb-faintest text-xs mt-2">Preview mode — the test is rendered but not delivered until a provider is connected.</div>}
        </div>

        {/* Deliverability — blocked addresses (Phase 1) */}
        <div className="pb-card p-4 mt-4">
          <div className="text-sm text-pb-text font-medium mb-1">Deliverability</div>
          <div className="text-pb-faintest text-xs mb-3 leading-relaxed">
            Addresses that bounced or marked an email as spam are blocked automatically so they never get another send.
            If someone has fixed their inbox, you can let them back in.
          </div>
          {suppressions === null ? (
            <div className="text-pb-faint text-sm">Loading…</div>
          ) : suppressions.length === 0 ? (
            <div className="text-pb-faintest text-sm">No blocked addresses. Good standing.</div>
          ) : (
            <div>
              {suppressions.map((r, i) => (
                <div key={r.email} className={`flex items-center justify-between gap-3 py-2 ${i > 0 ? 'pb-hairline-t' : ''}`}>
                  <div className="min-w-0">
                    <div className="text-pb-text text-sm truncate">{r.email}</div>
                    <div className="text-pb-faintest text-xs">{SUPPRESSION_LABEL[r.reason] || r.reason}</div>
                  </div>
                  <button onClick={() => unsuppress(r.email)}
                    className="shrink-0 px-2.5 py-1 rounded text-xs border pb-hairline text-pb-faint hover:text-pb-text">
                    Allow again
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </BetterCommsLayout>
  )
}
