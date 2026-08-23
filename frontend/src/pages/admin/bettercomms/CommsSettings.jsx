import { useState, useEffect } from 'react'
import { api } from '../../../lib/api'
import BetterCommsLayout from '../../../components/admin/BetterCommsLayout'
import { Button, Caption, SectionHeading, Checkbox, Badge, Empty, INPUT_CLS } from '../../../components/admin/ui'

const SUPPRESSION_LABEL = {
  hard_bounce: 'Bounced (address undeliverable)',
  complaint: 'Marked as spam',
  manual: 'Suppressed manually',
}

// One label/value row in the Bounces & unsubscribes card. `bad`/`warn` colour a
// non-zero value red/amber so a problem stands out.
function EngRow({ label, value, bad, warn }) {
  const v = Number(value || 0)
  const tone = v > 0 && bad ? 'text-pb-red' : v > 0 && warn ? 'text-amber-500' : 'text-pb-text'
  return (
    <div className="flex justify-between gap-2">
      <span className="text-pb-faint">{label}</span>
      <span className={tone}>{v.toLocaleString()}</span>
    </div>
  )
}

export default function CommsSettings() {
  const [s, setS] = useState(null)
  const [fromName, setFromName] = useState('')
  const [fromLocal, setFromLocal] = useState('')
  const [replyTo, setReplyTo] = useState('')
  const [footer, setFooter] = useState('')
  const [autoRemove, setAutoRemove] = useState(true)
  const [autoRemoveBusy, setAutoRemoveBusy] = useState(false)
  const [msg, setMsg] = useState(null)
  const [saving, setSaving] = useState(false)
  const [suppressions, setSuppressions] = useState(null)
  const [ses, setSes] = useState(null)            // super-admin SES status (null = not loaded / not super)
  const [testEmail, setTestEmail] = useState('')
  const [testBusy, setTestBusy] = useState(false)
  const [limits, setLimits] = useState(null)      // sending tier + usage + deliverability
  const [engagement, setEngagement] = useState(null)   // bounced / unsub per last + all campaigns
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
      setAutoRemove(d.auto_remove_unsubscribed !== false)
    }).catch(e => setMsg({ kind: 'error', text: e.message }))
    api.commsListSuppressions().then(setSuppressions).catch(() => setSuppressions([]))
    // Super-admin only; a 403 for club admins just leaves the panel hidden.
    api.commsSesStatus().then(setSes).catch(() => setSes(null))
    api.commsGetLimits().then(setLimits).catch(() => setLimits(null))
    api.commsCampaignEngagement().then(setEngagement).catch(() => setEngagement(null))
  }, [])

  const provisionTenants = async () => {
    setTenantBusy(true); setMsg(null)
    try {
      const r = await api.commsProvisionTenants(false)
      let text = `Tenants: ${r.provisioned || 0} provisioned, ${r.failed || 0} failed of ${r.total || 0}.`
      if (r.failed && r.errors?.length) {
        const e0 = r.errors[0]
        text += ` First failure: ${e0.club}: ${e0.reason || 'see logs'}. ${r.failed > 1 ? 'Run again to retry the rest.' : ''}`
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
      setMsg({ kind: 'ok', text: r.live ? `Test sent to ${testEmail.trim()} via ${r.provider}.` : 'Test rendered (preview mode, not delivered until a provider is connected).' })
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

  // Standalone toggle — saved on change (it lives near the top of the page, well
  // above the main Save button, so it persists itself rather than waiting on it).
  const toggleAutoRemove = async (next) => {
    setAutoRemove(next); setAutoRemoveBusy(true); setMsg(null)
    try {
      await api.commsSetSettings({ auto_remove_unsubscribed: next })
      setMsg({ kind: 'ok', text: next
        ? 'On. Unsubscribed and bounced contacts will be removed from all lists automatically.'
        : 'Off. Unsubscribed and bounced contacts stay on their lists (they\'re still skipped when sending).' })
    } catch (e) {
      setAutoRemove(!next)  // revert on failure
      setMsg({ kind: 'error', text: e.message })
    } finally { setAutoRemoveBusy(false) }
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
                  : <>Preview mode. Emails are rendered and logged but <strong>not delivered</strong>.</>}
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
                <div className="flex justify-between gap-2"><span className="text-pb-faint">Remaining today</span><span className="text-pb-text">{limits.daily_remaining == null ? 'Unlimited' : limits.daily_remaining}</span></div>
                <div className="flex justify-between gap-2"><span className="text-pb-faint">Delivered (30d)</span><span className="text-pb-text">{m.delivered ?? 0}</span></div>
                {limits.monthly_cap != null && (
                  <>
                    <div className="flex justify-between gap-2"><span className="text-pb-faint">Sent this month</span><span className="text-pb-text">{limits.sent_this_month ?? 0}</span></div>
                    <div className="flex justify-between gap-2"><span className="text-pb-faint">Monthly limit</span><span className="text-pb-text">{limits.monthly_cap}</span></div>
                  </>
                )}
                <div className="flex justify-between gap-2"><span className="text-pb-faint">Bounce rate</span><span className={`${m.bounce_rate >= 0.05 ? 'text-pb-red' : 'text-pb-text'}`}>{pct(m.bounce_rate)}</span></div>
                <div className="flex justify-between gap-2"><span className="text-pb-faint">Spam rate</span><span className={`${m.complaint_rate >= 0.001 ? 'text-pb-red' : 'text-pb-text'}`}>{pct(m.complaint_rate)}</span></div>
              </div>
              {!m.sufficient_sample && (m.sent ?? 0) < (m.min_sample ?? 50) && (
                <div className="text-pb-faintest text-[11px] leading-relaxed mb-2">
                  Bounce and spam rates are over the last {m.window_days || 30} days ({m.sent ?? 0} sent). They settle
                  into a reliable read once you've sent past {m.min_sample ?? 50}.
                </div>
              )}
              <div className="text-pb-faintest text-xs leading-relaxed mb-3">
                {limits.tier === 'sandbox'
                  ? `New clubs start with a ${limits.daily_cap}-a-day limit while your sending settles in. Once you've sent cleanly, ask BetterCricket to lift it.`
                  : limits.tier === 'suspended'
                    ? 'Sending is paused because too many emails bounced or were marked as spam. Contact BetterCricket to review and restore it.'
                    : 'Anything over the daily limit sends automatically the next day, so nothing is lost.'}
              </div>

              {limits.open_request ? (
                <div className="text-xs text-pb-faint border-t pb-hairline-t pt-3">
                  Request pending review, sent {limits.open_request.requested_at ? new Date(limits.open_request.requested_at).toLocaleDateString() : ''}.
                </div>
              ) : limits.can_request ? (
                <div className="border-t pb-hairline-t pt-3">
                  <div className="text-xs text-pb-text font-medium mb-1">Request an upgrade to Production</div>
                  <div className="text-pb-faintest text-xs mb-2 leading-relaxed">
                    You're on the Sandbox limit ({limits.daily_cap}/day). Ask BetterCricket to move you to
                    the Production limit once your sending has settled in. A note about your club helps us review it.
                  </div>
                  <textarea value={reqReason} onChange={e => setReqReason(e.target.value)} rows={2}
                    placeholder="e.g. 300-member club, weekly newsletter to our own members"
                    className={`${INPUT_CLS} mb-2`} />
                  <Button variant="primary" onClick={requestLimit} disabled={reqBusy}>
                    {reqBusy ? 'Sending…' : 'Request Production limit'}
                  </Button>
                </div>
              ) : null}
            </div>
          )
        })()}

        {/* Bounces & unsubscribes — last email and all emails */}
        {engagement && (
          <div className="pb-card p-4 mb-4">
            <SectionHeading className="mb-3">Bounces &amp; unsubscribes</SectionHeading>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <Caption className="mb-1.5 truncate">
                  Last email{engagement.last?.name ? `, ${engagement.last.name}` : ''}
                </Caption>
                {engagement.last ? (
                  <div className="text-sm space-y-1">
                    <EngRow label="Sent" value={engagement.last.sent} />
                    <EngRow label="Bounced" value={engagement.last.bounced} bad />
                    <EngRow label="Unsubscribed / spam" value={engagement.last.unsub_supp} warn />
                  </div>
                ) : <div className="text-pb-faintest text-sm">No emails sent yet.</div>}
              </div>
              <div>
                <Caption className="mb-1.5">All emails</Caption>
                <div className="text-sm space-y-1">
                  <EngRow label="Sent" value={engagement.all.sent} />
                  <EngRow label="Bounced" value={engagement.all.bounced} bad />
                  <EngRow label="Unsubscribed / spam" value={engagement.all.unsub_supp} warn />
                </div>
              </div>
            </div>
            <div className="text-pb-faintest text-[11px] leading-relaxed mt-3">
              Bounced = the address couldn't be delivered to. Unsubscribed / spam = people who opted
              out via the email or marked it as spam. Both are removed from future sends.
            </div>
          </div>
        )}

        {/* Auto-remove unsubscribed/bounced contacts from all lists */}
        <div className="pb-card p-4 mb-4">
          <Checkbox checked={autoRemove} disabled={autoRemoveBusy} onChange={toggleAutoRemove}
            hint="When on, a contact that unsubscribes or is bounced or marks spam is removed from every list it is on, so your lists only hold contactable people. They are always skipped when sending regardless, so this just keeps the lists themselves tidy.">
            <span className="text-pb-text font-semibold">Remove unsubscribed and bounced contacts from all lists</span>
          </Checkbox>
        </div>

        {/* AWS SES status — super admins only (the panel is hidden otherwise) */}
        {isPlatform && (
          <div className="pb-card p-4 mb-4">
            <div className="flex items-center justify-between mb-2">
              <SectionHeading>Amazon SES (platform)</SectionHeading>
              <Badge toneKey={ses.ses?.access_key_configured ? 'ok' : 'warn'}>
                {ses.ses?.access_key_configured ? 'Connected' : 'Not configured'}
              </Badge>
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
                <Button size="sm" onClick={provisionTenants} disabled={tenantBusy}>
                  {tenantBusy ? 'Provisioning…' : 'Provision club tenants'}
                </Button>
                <span className="text-pb-faintest text-xs">Creates an SES tenant for every club (idempotent).</span>
              </div>
            )}
          </div>
        )}

        {/* Sender identity */}
        <div className="pb-card p-4 mb-4">
          <SectionHeading className="mb-3">Sender</SectionHeading>
          <Caption className="mb-1.5">From name</Caption>
          <input value={fromName} onChange={e => setFromName(e.target.value)} placeholder={s.from_name}
            className={`${INPUT_CLS} mb-3`} />
          {p.live && p.provider === 'ses' && (
            <>
              <Caption className="mb-1.5">Sending address</Caption>
              <div className="flex items-center gap-2 mb-1">
                <input value={fromLocal} onChange={e => setFromLocal(e.target.value.toLowerCase().replace(/[^a-z0-9._-]/g, ''))}
                  placeholder={(s.from_address || '').split('@')[0] || 'hello'}
                  className={INPUT_CLS} />
                <span className="text-pb-faint text-sm shrink-0">@{(s.from_address || '').split('@')[1] || ''}</span>
              </div>
              <div className="text-pb-faintest text-xs mb-3">
                The part before the @. Blank uses your club's short code. Currently sending from <span className="text-pb-faint">{s.from_address}</span>.
              </div>
            </>
          )}
          <Checkbox className="mb-2.5" checked={noReply}
            onChange={on => setReplyTo(on ? 'noreply@betteradmin-comms.work' : '')}>
            No-reply address, so replies are not monitored
          </Checkbox>
          <Caption className="mb-1.5">Reply-to email</Caption>
          <input value={replyTo} onChange={e => setReplyTo(e.target.value)} placeholder="committee@yourclub.org.au" type="email"
            className={INPUT_CLS} />
          <div className="text-pb-faintest text-xs mt-1">Replies go here. Defaults to your club contact email. Tick no-reply to send from an unmonitored address.</div>
        </div>

        {/* Compliance footer */}
        <div className="pb-card p-4 mb-4">
          <SectionHeading className="mb-1.5">Email footer</SectionHeading>
          <div className="text-pb-faintest text-xs mb-3 leading-relaxed">
            Australian law (Spam Act 2003) requires every email to identify the sender and offer a one-click
            unsubscribe. The unsubscribe link is added automatically. Put your club's legal name and a
            contact or postal line here so recipients know who it's from.
          </div>
          <textarea value={footer} onChange={e => setFooter(e.target.value)} rows={3}
            placeholder={`${s.from_name} Cricket Club\nABN 00 000 000 000 · PO Box 1, Suburb WA 6000`}
            className={INPUT_CLS} />
        </div>

        <div className="flex items-center gap-3">
          <Button variant="primary" size="lg" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : 'Save settings'}
          </Button>
          <span className="text-pb-faintest text-xs">{s.subscribed_contacts} subscribed contact{s.subscribed_contacts === 1 ? '' : 's'}</span>
        </div>

        {/* Send a test email */}
        <div className="pb-card p-4 mt-4">
          <SectionHeading className="mb-1.5">Send a test email</SectionHeading>
          <div className="text-pb-faintest text-xs mb-3">Checks the connection by sending a test to an address you choose, using the current sender settings. Save your changes first.</div>
          <div className="flex gap-2">
            <input value={testEmail} onChange={e => setTestEmail(e.target.value)} placeholder="you@example.com" type="email"
              className={INPUT_CLS} />
            <Button onClick={sendTest} disabled={testBusy}>{testBusy ? 'Sending…' : 'Send test'}</Button>
          </div>
          {!p.live && <div className="text-pb-faintest text-xs mt-2">Preview mode. The test is rendered but not delivered until a provider is connected.</div>}
        </div>

        {/* Deliverability — blocked addresses (Phase 1) */}
        <div className="pb-card p-4 mt-4">
          <SectionHeading className="mb-1.5">Deliverability</SectionHeading>
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
                  <Button size="sm" onClick={() => unsuppress(r.email)}>Allow again</Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </BetterCommsLayout>
  )
}
