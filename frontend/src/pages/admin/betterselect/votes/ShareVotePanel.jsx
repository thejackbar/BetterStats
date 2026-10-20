import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import QRCode from 'qrcode'
import { useToast } from '../../../../contexts/ToastContext'
import { Btn, Icon } from '../ui'

// One place to share a vote. Every target composes from the SAME pre-filtered
// link, so a player only ever lands on the games that apply to them:
//   /vote/:token                      whole club
//   /vote/:token?team=<grade_id>      one grade
//   /vote/:token?fixture=<fixture_id> straight into one ballot
const TARGETS = [
  { key: 'whatsapp', label: 'WhatsApp group', dot: 'var(--pb-positive)' },
  { key: 'sms',      label: 'SMS the XI',     dot: 'var(--pb-accent)' },
  { key: 'copy',     label: 'Copy message',   dot: 'var(--pb-dim)' },
  { key: 'qr',       label: 'QR for the clubroom', dot: 'var(--pb-dim)' },
  { key: 'social',   label: 'Post to socials', dot: '#EC4899' },
]

export function voteUrl(token, { fixtureId, gradeId, roundKey } = {}) {
  const u = new URL(`/vote/${token}`, window.location.origin)
  if (fixtureId) u.searchParams.set('fixture', fixtureId)
  else if (gradeId) u.searchParams.set('team', gradeId)
  if (roundKey && !fixtureId) u.searchParams.set('round', roundKey)
  return u.toString()
}

// [3, 2, 1] reads "3, 2 and 1".
function ballotWords(values) {
  const v = (values?.length ? values : [3, 2, 1]).map(String)
  return v.length === 1 ? v[0] : `${v.slice(0, -1).join(', ')} and ${v[v.length - 1]}`
}

// `onEnable` is passed only by the Settings tab, where the switch lives; on
// every other screen the notice points there instead.
export default function ShareVotePanel({ settings, scope, fixtures = [], onPostToSocials, onEnable, busy }) {
  const toast = useToast()
  const navigate = useNavigate()
  const [qr, setQr] = useState(null)
  const [draft, setDraft] = useState(null)

  const url = settings?.enabled && settings?.token ? voteUrl(settings.token, scope) : ''
  const canShare = typeof navigator !== 'undefined' && typeof navigator.share === 'function'

  // The message names a game only when the link opens exactly one. A link for a
  // whole club or team lists several games, so naming the first row would
  // promise players a game the link does not take them to.
  const defaultMessage = useMemo(() => {
    const fx = scope?.fixtureId || fixtures.length === 1 ? fixtures[0] : null
    const what = fx
      ? `${fx.round} v ${fx.opponent || 'TBC'}`
      : scope?.gradeId || scope?.roundKey ? scope?.label : "this week's games"
    const closes = fx?.closes_on ? `\nCloses ${new Date(fx.closes_on + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })}.` : ''
    return `Votes are open for ${what}. 30 seconds, no login. Pick your ${ballotWords(settings?.ballot_values)}.\n${url}${closes}`
  }, [fixtures, url, scope, settings?.ballot_values])

  const message = draft ?? defaultMessage

  useEffect(() => {
    if (!url) { setQr(null); return }
    let alive = true
    QRCode.toDataURL(url, { margin: 1, width: 240, errorCorrectionLevel: 'M' })
      .then((u) => alive && setQr(u)).catch(() => alive && setQr(null))
    return () => { alive = false }
  }, [url])

  const send = async (key) => {
    if (!url) { toast.error('Turn the voting link on under Settings first.'); return }
    if (key === 'whatsapp') { window.open(`https://wa.me/?text=${encodeURIComponent(message)}`, '_blank', 'noopener'); return }
    if (key === 'sms') { window.location.href = `sms:?&body=${encodeURIComponent(message)}`; return }
    if (key === 'social') {
      // The BetterSocials post designer doesn't have a standings-card renderer
      // yet (README, "Suggested build order" #9) — deep-link into the plain
      // post composer with the message ready to paste in, rather than nothing.
      if (onPostToSocials) { onPostToSocials(message, url); return }
      try { await navigator.clipboard.writeText(message) } catch { /* best-effort */ }
      toast.success('Message copied — paste it into your post')
      navigate('/admin/social-post')
      return
    }
    if (key === 'qr') { setQr((q) => q); return }
    try { await navigator.clipboard.writeText(message); toast.success('Message copied') }
    catch { toast.error('Copy failed. Select and copy manually.') }
  }

  const copyLink = async () => {
    try { await navigator.clipboard.writeText(url); toast.success('Link copied') }
    catch { toast.error('Copy failed. Select and copy manually.') }
  }

  // The phone's own share sheet (WhatsApp, Messenger, Facebook, email, AirDrop).
  const shareNative = async () => {
    try { await navigator.share({ title: 'Player vote', text: message }) }
    catch (e) { if (e?.name !== 'AbortError') toast.error('Sharing failed. Use Copy link instead.') }
  }

  const covers = scope?.fixtureId
    ? 'This link opens that one game and nothing else.'
    : scope?.gradeId || scope?.roundKey
      ? `This link opens ${scope.label || 'the games'} only. It changes when you change the filters above.`
      : 'This link lists every open game in the club. Pick a team or round above to make a narrower link.'

  if (!settings?.enabled) {
    return (
      <div className="pb-card px-4 py-4 text-[12.5px] text-pb-amber">
        {onEnable
          ? "The voting link is off, so players can't vote yet. Admins can still enter ballots by hand."
          : "The voting link is off, so players can't vote yet. Turn it on under Settings — admins can still enter ballots by hand."}
        {onEnable && (
          <div className="mt-3">
            <Btn sm variant="primary" onClick={onEnable} disabled={busy}>Turn on voting link</Btn>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="pb-card px-4 py-4">
      <div className="flex items-center justify-between mb-3">
        <div className="font-display font-bold text-[14.5px]">Share this week's vote</div>
        <span className="font-mono text-[10px] text-pb-faintest uppercase tracking-wide2">
          {scope?.label || 'Whole club'}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2 mb-3" data-vote-link-row>
        <input readOnly value={url} onFocus={(e) => e.target.select()} aria-label="Voting link"
          className="flex-1 min-w-[220px] bg-pb-surface2 border border-pb-hairline2 rounded-lg px-3 py-2 text-sm font-mono text-pb-dim" />
        <Btn sm variant="primary" onClick={copyLink}>Copy link</Btn>
        {canShare && <Btn sm onClick={shareNative}>Share</Btn>}
      </div>

      <div className="flex flex-wrap gap-2">
        {TARGETS.map((t) => (
          <button key={t.key} onClick={() => send(t.key)}
            className="inline-flex items-center gap-2 px-3.5 py-2.5 rounded-[10px] text-[13px] font-medium
                       bg-pb-surface2 border border-pb-hairline2 text-pb-text
                       hover:border-pb-accent transition-colors">
            <span className="w-[7px] h-[7px] rounded-full" style={{ background: t.dot }} />
            {t.label}
          </button>
        ))}
      </div>

      <div className="mt-3.5 rounded-[10px] border border-dashed border-pb-hairline2 bg-pb-bg px-3.5 py-3">
        <div className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faintest mb-1.5">
          Message preview · editable
        </div>
        <textarea rows={3} value={message} onChange={(e) => setDraft(e.target.value)}
          className="w-full bg-transparent border-0 outline-none resize-none text-[13.5px] leading-relaxed text-pb-dim" />
      </div>

      {qr && (
        <div className="mt-3 flex items-center gap-3">
          <img src={qr} alt="Voting link QR code" className="w-24 h-24 rounded-lg bg-white p-1.5" />
          <div className="text-[12px] text-pb-faint">
            Print it for the clubroom wall. Scanning opens the same pre-filtered link.
          </div>
        </div>
      )}

      <div className="flex items-start gap-2 mt-3 text-[12px] text-pb-faint">
        <Icon name="info" size={14} className="mt-0.5 shrink-0" />
        {covers}
      </div>
    </div>
  )
}
