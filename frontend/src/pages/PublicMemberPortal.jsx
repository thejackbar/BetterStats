// Member self-service portal (public, no login/app — an emailed magic link
// signs a member in). See services/member_portal_auth.py for the design.
import { useState, useEffect, useCallback } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'

const inp = 'w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
const money = (n) => `$${Number(n || 0).toFixed(2)}`

function Banner({ tone = 'error', children }) {
  if (!children) return null
  const color = tone === 'error' ? 'var(--pb-red)' : tone === 'ok' ? 'var(--pb-positive)' : 'var(--pb-amber)'
  return (
    <div className="rounded-lg px-3.5 py-2.5 mb-4 text-sm" style={{ background: `color-mix(in srgb, ${color} 12%, transparent)`, color, border: `1px solid color-mix(in srgb, ${color} 35%, transparent)` }}>
      {children}
    </div>
  )
}

function LoginScreen({ slug, clubName, onSent }) {
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [sent, setSent] = useState(false)

  async function submit() {
    if (!email.trim()) return
    setBusy(true); setError('')
    try {
      await api.portalRequestLink(slug, email.trim())
      setSent(true)
      onSent?.()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  if (sent) {
    return (
      <div className="pb-card p-5 text-center">
        <div className="text-pb-text font-semibold mb-1">Check your email</div>
        <div className="font-mono text-[11px] text-pb-faint">
          If that address is registered with {clubName || 'the club'}, a sign-in link is on its way. It expires in 20 minutes.
        </div>
      </div>
    )
  }

  return (
    <div className="pb-card p-5">
      {error && <Banner>{error}</Banner>}
      <label className="font-mono text-[10px] tracking-wide2 text-pb-faint block mb-1.5">YOUR EMAIL</label>
      <input className={inp} placeholder="you@example.com" value={email}
        onChange={e => setEmail(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') submit() }} />
      <button onClick={submit} disabled={busy || !email.trim()}
        className="w-full mt-3 py-2.5 rounded font-mono text-[11px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50"
        style={{ background: 'var(--pb-accent)' }}>
        {busy ? 'SENDING…' : 'EMAIL ME A SIGN-IN LINK'}
      </button>
      <p className="font-mono text-[10px] text-pb-faintest mt-2">
        Use the email address the club has on file for you.
      </p>
    </div>
  )
}

function FeesCard({ slug, fees, canPay, onPaid }) {
  const [paying, setPaying] = useState(null)
  if (!fees) {
    return <div className="pb-card p-5 text-center text-pb-dim text-sm">No fee record for this season yet.</div>
  }
  const fin = fees.financials
  async function pay(kind) {
    setPaying(kind)
    try {
      const r = await api.portalPay(slug, kind)
      window.location.assign(r.checkout_url)
    } catch (e) {
      alert(e.message)
      setPaying(null)
    }
  }
  return (
    <div className="pb-card p-5 mb-4">
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-3">MY FEES</div>
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div>
          <div className="font-mono text-[9px] text-pb-faintest mb-1">MEMBERSHIP</div>
          <div className="text-pb-text text-lg font-display font-bold">{money(fin.membership_outstanding)}</div>
          <div className="font-mono text-[10px] text-pb-faintest">of {money(fin.membership_payable)} owing</div>
        </div>
        <div>
          <div className="font-mono text-[9px] text-pb-faintest mb-1">MATCH FEES</div>
          <div className="text-pb-text text-lg font-display font-bold">{money(fin.match_fee_outstanding)}</div>
          <div className="font-mono text-[10px] text-pb-faintest">of {money(fin.match_fee_payable)} owing</div>
        </div>
      </div>
      {fin.in_credit && <div className="font-mono text-[11px] text-pb-accent mb-2">You're in credit: {money(fin.credit)}</div>}
      {canPay ? (
        <div className="flex flex-wrap gap-2">
          {fin.membership_outstanding > 0 && (
            <button onClick={() => pay('membership')} disabled={paying === 'membership'}
              className="px-3 py-2 rounded font-mono text-[10px] tracking-wide2 disabled:opacity-50" style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}>
              {paying === 'membership' ? 'REDIRECTING…' : `PAY MEMBERSHIP ${money(fin.membership_outstanding)}`}
            </button>
          )}
          {fin.match_fee_outstanding > 0 && (
            <button onClick={() => pay('match_day')} disabled={paying === 'match_day'}
              className="px-3 py-2 rounded font-mono text-[10px] tracking-wide2 disabled:opacity-50" style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}>
              {paying === 'match_day' ? 'REDIRECTING…' : `PAY MATCH FEES ${money(fin.match_fee_outstanding)}`}
            </button>
          )}
          {fin.total_outstanding <= 0 && <div className="font-mono text-[11px] text-pb-accent">All square. Nothing owing.</div>}
        </div>
      ) : (
        fin.total_outstanding > 0 && (
          <div className="font-mono text-[10px] text-pb-faintest">Online payment isn't set up yet, pay the usual way, or ask the club.</div>
        )
      )}
    </div>
  )
}

function QualificationsCard({ qualifications }) {
  if (!qualifications) return null
  return (
    <div className="pb-card p-5 mb-4">
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-3">MY QUALIFICATIONS</div>
      {qualifications.length === 0 ? (
        <div className="font-mono text-[11px] text-pb-faintest">Nothing on record.</div>
      ) : (
        <div className="space-y-1.5">
          {qualifications.map(q => (
            <div key={q.id} className="flex items-center justify-between gap-2">
              <span className="text-pb-text text-sm">{q.type_name}</span>
              <span className={`font-mono text-[9px] tracking-wide2 rounded px-1.5 py-0.5 border ${q.is_expired ? 'text-pb-red border-pb-red/40' : q.expires_soon ? 'text-pb-amber border-pb-amber/40' : 'text-pb-faint pb-hairline'}`}>
                {q.expires_at ? (q.is_expired ? `EXPIRED ${q.expires_at}` : `EXPIRES ${q.expires_at}`) : 'NO EXPIRY'}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ContactCard({ slug, member, onSaved }) {
  const [email, setEmail] = useState(member.email || '')
  const [mobile, setMobile] = useState(member.mobile || '')
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)

  async function save() {
    setBusy(true); setSaved(false)
    try {
      await api.portalUpdateMe(slug, { email, mobile })
      setSaved(true)
      onSaved?.()
    } catch (e) { alert(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="pb-card p-5">
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-3">MY DETAILS</div>
      <div className="space-y-2.5">
        <input className={inp} placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} />
        <input className={inp} placeholder="Mobile" value={mobile} onChange={e => setMobile(e.target.value)} />
        <button onClick={save} disabled={busy} className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-dim hover:text-pb-text disabled:opacity-50">
          {busy ? 'SAVING…' : 'SAVE'}
        </button>
        {saved && <span className="font-mono text-[10px] text-pb-accent ml-2">Saved</span>}
      </div>
    </div>
  )
}

export default function PublicMemberPortal() {
  const { slug } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const [status, setStatus] = useState(null)
  const [me, setMe] = useState(null)
  const [checking, setChecking] = useState(true)
  const [error, setError] = useState('')

  const loadMe = useCallback(() => {
    api.portalMe(slug).then(setMe).catch(() => setMe(null))
  }, [slug])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const s = await api.portalStatus(slug)
        if (cancelled) return
        setStatus(s)
        if (!s.enabled) { setChecking(false); return }
        const token = searchParams.get('token')
        if (token) {
          try {
            await api.portalVerify(slug, token)
            setSearchParams(prev => { const p = new URLSearchParams(prev); p.delete('token'); return p }, { replace: true })
          } catch (e) {
            if (!cancelled) setError(e.message)
          }
        }
        await api.portalMe(slug).then(d => { if (!cancelled) setMe(d) }).catch(() => { if (!cancelled) setMe(null) })
      } catch (e) {
        if (!cancelled) setError(e.message || 'Club not found')
      } finally {
        if (!cancelled) setChecking(false)
      }
    })()
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug])

  async function logout() {
    await api.portalLogout(slug).catch(() => {})
    setMe(null)
  }

  if (checking) {
    return <div className="min-h-screen bg-pb-bg flex items-center justify-center"><div className="font-mono text-[11px] text-pb-faint">Loading…</div></div>
  }
  if (error && !status) {
    return (
      <div className="min-h-screen bg-pb-bg flex items-center justify-center px-4">
        <div className="max-w-sm text-center">
          <div className="font-display font-bold text-lg text-pb-text mb-1">Not found</div>
          <div className="font-mono text-[11px] text-pb-faint">{error}</div>
        </div>
      </div>
    )
  }
  if (status && !status.enabled) {
    return (
      <div className="min-h-screen bg-pb-bg flex items-center justify-center px-4">
        <div className="max-w-sm text-center">
          <div className="font-display font-bold text-lg text-pb-text mb-1">Not available yet</div>
          <div className="font-mono text-[11px] text-pb-faint">The member portal isn't switched on for this club yet.</div>
        </div>
      </div>
    )
  }

  const paidParam = searchParams.get('paid')

  return (
    <div className="min-h-screen bg-pb-bg px-4 py-10">
      <div className="max-w-md mx-auto">
        <div className="text-center mb-6">
          <div className="font-mono text-[10px] tracking-wide2 text-pb-faint mb-1">{(status?.club_name || '').toUpperCase()}</div>
          <div className="font-display font-bold text-2xl text-pb-text">Member Portal</div>
        </div>

        {paidParam === '1' && <Banner tone="ok">Payment received, thanks! It may take a minute to show below.</Banner>}
        {paidParam === '0' && <Banner tone="warn">Payment cancelled. Nothing was charged.</Banner>}
        {error && <Banner>{error}</Banner>}

        {!me ? (
          <LoginScreen slug={slug} clubName={status?.club_name} />
        ) : (
          <div>
            <div className="flex items-center justify-between mb-4">
              <div className="text-pb-text font-semibold">Hi {me.member.full_name.split(' ')[0]}</div>
              <button onClick={logout} className="font-mono text-[10px] text-pb-faint hover:text-pb-text">Sign out</button>
            </div>
            <FeesCard slug={slug} fees={me.fees} canPay={me.online_payment_available} />
            <QualificationsCard qualifications={me.qualifications} />
            <ContactCard slug={slug} member={me.member} onSaved={loadMe} />
          </div>
        )}
      </div>
    </div>
  )
}
