import { useState, useEffect } from 'react'
import { api } from '../../../lib/api'
import BetterCommsLayout from '../../../components/admin/BetterCommsLayout'

export default function CommsSettings() {
  const [s, setS] = useState(null)
  const [fromName, setFromName] = useState('')
  const [replyTo, setReplyTo] = useState('')
  const [footer, setFooter] = useState('')
  const [msg, setMsg] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.commsGetSettings().then(d => {
      setS(d)
      setFromName(d.from_name || '')
      setReplyTo(d.reply_to || '')
      setFooter(d.sender_footer || '')
    }).catch(e => setMsg({ kind: 'error', text: e.message }))
  }, [])

  const save = async () => {
    setSaving(true); setMsg(null)
    try {
      await api.commsSetSettings({ from_name: fromName, reply_to: replyTo, sender_footer: footer })
      setMsg({ kind: 'ok', text: 'Saved.' })
    } catch (e) { setMsg({ kind: 'error', text: e.message }) }
    finally { setSaving(false) }
  }

  if (!s) return <BetterCommsLayout title="Settings"><div className="text-pb-faint text-sm">Loading…</div></BetterCommsLayout>

  const p = s.provider || {}

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
                  ? <>Connected via <span className="text-pb-text capitalize">{p.provider}</span> · sending from <span className="text-pb-text">{p.from_address}</span></>
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

        {/* Sender identity */}
        <div className="pb-card p-4 mb-4">
          <div className="text-sm text-pb-text font-medium mb-3">Sender</div>
          <label className="block text-xs text-pb-faint mb-1">From name</label>
          <input value={fromName} onChange={e => setFromName(e.target.value)} placeholder={s.from_name}
            className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm mb-3" />
          <label className="block text-xs text-pb-faint mb-1">Reply-to email</label>
          <input value={replyTo} onChange={e => setReplyTo(e.target.value)} placeholder="committee@yourclub.org.au" type="email"
            className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm" />
          <div className="text-pb-faintest text-xs mt-1">Replies go here. Defaults to your club contact email.</div>
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
      </div>
    </BetterCommsLayout>
  )
}
