// BetterSelect → Nets — the self check-in link admin panel.
//
// Players check themselves in at the nets by scanning a QR code on the fence or
// tapping an NFC tag beside it. Both hold the SAME URL — an NFC tag stores a
// URL and nothing else — so this card manages one link, shows the QR to print,
// and gives the address to write to a tag.
import { useState, useEffect, useCallback } from 'react'
import QRCode from 'qrcode'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { Icon, Btn, Segmented } from './ui'

export default function NetCheckInPanel({ onChanged }) {
  const { hasCapability } = useAuth()
  const toast = useToast()
  const canEdit = hasCapability(CAP.MANAGE_SELECTIONS)

  const [open, setOpen] = useState(false)
  const [cfg, setCfg] = useState(null)
  const [busy, setBusy] = useState(false)
  const [qr, setQr] = useState(null)

  const fullUrl = cfg?.token ? `${window.location.origin}${cfg.path}` : ''
  const message = fullUrl ? `🏏 Check in to nets: ${fullUrl}` : ''

  const load = useCallback(() => {
    api.nmGetCheckInLink().then(setCfg).catch(() => setCfg(null))
  }, [])
  useEffect(() => { load() }, [load])

  // Bigger than the availability QR: this one gets printed and stuck on a fence,
  // then scanned in the dark from arm's length. H error correction so it still
  // reads once it has been rained on.
  useEffect(() => {
    if (!open || !fullUrl) { setQr(null); return }
    let alive = true
    QRCode.toDataURL(fullUrl, { margin: 2, width: 512, errorCorrectionLevel: 'H' })
      .then((u) => { if (alive) setQr(u) })
      .catch(() => { if (alive) setQr(null) })
    return () => { alive = false }
  }, [open, fullUrl])

  const update = async (patch) => {
    if (!canEdit) return
    setBusy(true)
    try {
      setCfg(await api.nmSetCheckInLink(patch))
      onChanged?.()
    } catch (e) {
      toast.error(e.message || 'Update failed')
    } finally { setBusy(false) }
  }

  const regenerate = async () => {
    if (!canEdit) return
    if (!window.confirm('Generate a new link? Every QR code you have printed and every NFC tag you have written stops working immediately, and will need redoing.')) return
    setBusy(true)
    try {
      setCfg(await api.nmRegenerateCheckInLink())
      toast.success('New link generated. Reprint the QR code and rewrite your tags.')
    } catch (e) {
      toast.error(e.message || 'Regenerate failed')
    } finally { setBusy(false) }
  }

  const copy = async (text, what) => {
    try {
      await navigator.clipboard.writeText(text)
      toast.success(`${what} copied`)
    } catch {
      toast.error('Copy failed. Select and copy manually')
    }
  }

  if (!cfg) return null

  const enabled = !!cfg.enabled
  const cov = cfg.phone_coverage || { with_phone: 0, total: 0 }
  const noPhone = Math.max(0, (cov.total || 0) - (cov.with_phone || 0))

  return (
    <div className="pb-card mb-4">
      <button onClick={() => setOpen((o) => !o)} className="w-full flex items-center gap-3 px-4 py-3 text-left">
        <span className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)', color: 'var(--pb-accent)' }}>
          <Icon name="availability" size={17} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="font-display font-bold text-[15px] flex items-center gap-2">
            Self check-in (QR / NFC)
            <span className="font-mono text-[10px] px-2 py-0.5 rounded-full" style={enabled
              ? { background: 'color-mix(in srgb, var(--pb-positive) 16%, transparent)', color: 'var(--pb-positive)' }
              : { background: 'var(--pb-surface2)', color: 'var(--pb-faintest)' }}>
              {enabled ? 'ON' : 'OFF'}
            </span>
          </div>
          <div className="text-[12.5px] text-pb-faint mt-0.5">
            Players scan a code or tap a tag and check themselves in, no logins.
          </div>
        </div>
        <span className="text-pb-faint shrink-0">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 border-t pb-hairline pt-4 flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
            <div className="flex items-center gap-2.5">
              <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Status</span>
              <Segmented sm value={enabled ? 'on' : 'off'} onChange={(v) => update({ enabled: v === 'on' })}
                options={[{ value: 'on', label: 'Enabled' }, { value: 'off', label: 'Off' }]} />
            </div>
            {enabled && (
              <>
                <div className="flex items-center gap-2.5">
                  <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">PIN</span>
                  <Segmented sm value={cfg.require_pin ? 'pin' : 'nopin'} onChange={(v) => update({ require_pin: v === 'pin' })}
                    options={[{ value: 'pin', label: 'Last-4 PIN' }, { value: 'nopin', label: 'No PIN' }]} />
                </div>
                <div className="flex items-center gap-2.5">
                  <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">New players</span>
                  <Segmented sm value={cfg.allow_registration ? 'yes' : 'no'} onChange={(v) => update({ allow_registration: v === 'yes' })}
                    options={[{ value: 'yes', label: 'Can register' }, { value: 'no', label: 'Roster only' }]} />
                </div>
              </>
            )}
          </div>

          {!enabled ? (
            <p className="text-sm text-pb-faint">
              Turn this on to generate a link. Print it as a QR code or write it to an NFC tag, stick it where players walk in, and they check themselves in on the way past. Straight into whatever session is running.
            </p>
          ) : (
            <>
              <div>
                <label className="block font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1.5">Check-in link</label>
                <div className="flex flex-wrap items-center gap-2">
                  <input readOnly value={fullUrl} onFocus={(e) => e.target.select()}
                    className="flex-1 min-w-[220px] bg-pb-surface2 border pb-hairline rounded-lg px-3 py-2 text-sm font-mono text-pb-dim" />
                  <Btn sm onClick={() => copy(fullUrl, 'Link')}>Copy link</Btn>
                  <Btn sm onClick={() => copy(message, 'Message')}>Copy message</Btn>
                  {canEdit && <Btn sm variant="ghost" onClick={regenerate} disabled={busy}>Regenerate</Btn>}
                </div>
                <p className="text-[11px] text-pb-faintest mt-1.5">
                  Checking in adds a player to every net session running at the time, so nobody has to know which one they are in.
                </p>
              </div>

              <div className="flex flex-wrap items-start gap-5">
                {qr && (
                  <div className="text-center">
                    <img src={qr} alt="Net check-in QR code" className="w-40 h-40 rounded-lg bg-white p-2" />
                    <div className="mt-2">
                      <Btn sm href={qr} download={`net-checkin-${cfg.token?.slice(0, 8) || 'qr'}.png`}>Download QR</Btn>
                    </div>
                  </div>
                )}
                <div className="flex-1 min-w-[220px] flex flex-col gap-3">
                  <div>
                    <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1.5">Writing an NFC tag</div>
                    <p className="text-[12.5px] text-pb-dim">
                      Copy the link above and write it to the tag as a URL record, using any NFC writer app. It is the same address as the QR code, so a tag and a printed code sit side by side and do the same thing. Rewritable tags mean you can redo them if you ever regenerate the link.
                    </p>
                  </div>
                  <div>
                    <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1.5">Phone coverage</div>
                    <div className="text-sm text-pb-dim">
                      <b className="text-pb-text">{cov.with_phone}</b> of <b className="text-pb-text">{cov.total}</b> active players have a mobile on file{cfg.require_pin ? ' and can check themselves in.' : '.'}
                    </div>
                    {cfg.require_pin && noPhone > 0 && (
                      <div className="mt-2 text-[12.5px] rounded-lg px-3 py-2" style={{ background: 'color-mix(in srgb, var(--pb-amber) 12%, transparent)', color: 'var(--pb-amber)' }}>
                        {noPhone} player{noPhone === 1 ? '' : 's'} can’t check in without a mobile number.{' '}
                        <a href="/admin/betterselect/players" className="underline">Add numbers</a>, or turn the PIN off.
                      </div>
                    )}
                    {!cfg.require_pin && (
                      <div className="mt-2 text-[12.5px] text-pb-faintest">
                        With the PIN off, anyone holding the link can check in under any name on the list. That is usually the right trade at a net session. Worth knowing before the code goes somewhere public.
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
