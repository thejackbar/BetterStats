// One net session's own check-in link and the squads it is for.
//
// The club-wide link (Nets > Self check-in) joins every session that is on. This
// one is for THIS session only, so a code printed for Thursday's juniors cannot
// check anybody into Tuesday's seniors, and it can be limited to squads so the
// list a player picks their name from is the right short list.
import { useEffect, useState } from 'react'
import QRCode from 'qrcode'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import { Icon, Btn, Chip } from './ui'

export default function SessionLinkModal({ sessionId, squads, squadIds, canEdit, ended, onSquadsChanged, onClose }) {
  const toast = useToast()
  const [link, setLink] = useState(null)
  const [qr, setQr] = useState(null)
  const [busy, setBusy] = useState(false)
  const url = link?.path ? `${window.location.origin}${link.path}` : ''

  useEffect(() => {
    let live = true
    api.nmSessionCheckInLink(sessionId).then((l) => { if (live) setLink(l) }).catch((e) => toast.error(e.message))
    return () => { live = false }
  }, [sessionId])  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!url) { setQr(null); return undefined }
    let live = true
    QRCode.toDataURL(url, { margin: 2, width: 512, errorCorrectionLevel: 'H' })
      .then((u) => { if (live) setQr(u) }).catch(() => { if (live) setQr(null) })
    return () => { live = false }
  }, [url])

  const copy = async (text, what) => {
    try { await navigator.clipboard.writeText(text); toast.success(`${what} copied`) }
    catch { toast.error('Copy failed — select and copy manually') }
  }
  const regenerate = async () => {
    if (!window.confirm('Make a new link for this session? The QR code or tag you already printed for it stops working. Other sessions are not affected.')) return
    setBusy(true)
    try { setLink(await api.nmRegenerateSessionCheckInLink(sessionId)); toast.success('New link made for this session') }
    catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  const toggleSquad = async (id) => {
    const next = squadIds.includes(id) ? squadIds.filter((x) => x !== id) : [...squadIds, id]
    setBusy(true)
    try { const r = await api.nmUpdateSession(sessionId, { squad_team_ids: next }); onSquadsChanged(r) }
    catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  return (
    <div onClick={onClose} className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4 bg-black/60 backdrop-blur-sm">
      <div onClick={(e) => e.stopPropagation()} data-session-link
        className="w-full sm:w-[520px] max-h-[90vh] bg-pb-surface sm:rounded-2xl rounded-t-2xl border border-pb-hairline2 overflow-hidden shadow-2xl flex flex-col">
        <div className="flex items-center gap-3 px-4 py-3.5 border-b pb-hairline">
          <div className="flex-1 min-w-0">
            <div className="font-mono text-[10px] uppercase tracking-wide3 text-pb-accent">This session</div>
            <div className="font-display font-bold text-[16px]">Check-in link and squads</div>
          </div>
          <button onClick={onClose} className="text-pb-faint hover:text-pb-text p-1" aria-label="Close"><Icon name="close" size={18} /></button>
        </div>
        <div className="overflow-y-auto px-4 py-4 flex flex-col gap-5">
          {squads.length > 0 && (
            <div>
              <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1.5">Who is this session for?</div>
              <div className="flex flex-wrap gap-1.5">
                {squads.map((sq) => (
                  <Chip key={sq.id} label={sq.label} active={squadIds.includes(sq.id)}
                    onClick={canEdit && !busy ? () => toggleSquad(sq.id) : undefined} />
                ))}
              </div>
              <p className="text-[11.5px] text-pb-faint mt-1.5">
                {squadIds.length
                  ? 'The check-in list on this session’s link shows only players in the ticked squads, and your own check-in list starts on them.'
                  : 'None ticked: everyone is on the list. Tick the squads training tonight to shorten it.'}
              </p>
            </div>
          )}

          {link?.enabled === false && (
            <div className="text-[12.5px] rounded-lg px-3 py-2" style={{ background: 'color-mix(in srgb, var(--pb-amber) 12%, transparent)', color: 'var(--pb-amber)' }}>
              Self check-in is switched off for the club, so this link will not open. Turn it on under Nets, Self check-in.
            </div>
          )}
          {ended && <p className="text-[12.5px] text-pb-faint">This session has ended, so its link no longer checks anybody in. Reopen the session to use it again.</p>}

          <div>
            <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1.5">Link for this session only</div>
            <div className="flex flex-wrap items-center gap-2">
              <input readOnly value={url} onFocus={(e) => e.target.select()} data-session-link-url
                className="flex-1 min-w-[200px] bg-pb-surface2 border pb-hairline rounded-lg px-3 py-2 text-sm font-mono text-pb-dim" />
              <Btn sm onClick={() => copy(url, 'Link')} disabled={!url}>Copy</Btn>
              <Btn sm variant="ghost" href={url || undefined} target="_blank" disabled={!url || ended}>Open</Btn>
              {canEdit && <Btn sm variant="ghost" onClick={regenerate} disabled={busy || !url}>New link</Btn>}
            </div>
            <p className="text-[11.5px] text-pb-faint mt-1.5">
              Checks people into this session and no other. The club-wide link under Nets still joins everyone to every session that is on.
            </p>
          </div>

          {qr && (
            <div className="text-center">
              <img src={qr} alt="Check-in QR code for this session" className="w-40 h-40 mx-auto rounded-lg bg-white p-2" />
              <div className="mt-2"><Btn sm href={qr} download={`net-session-${link.token?.slice(0, 6) || 'qr'}.png`}>Download QR</Btn></div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
