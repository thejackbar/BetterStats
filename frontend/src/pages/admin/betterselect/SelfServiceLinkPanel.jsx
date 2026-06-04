// BetterSelect → Availability — the self-service link admin panel.
//
// Players set their own availability via a per-club magic link + a last-4-of-
// phone PIN (no logins). This card is where the admin turns that on, shares the
// link/QR, and keeps an eye on how many players can actually self-serve.
import { useState, useEffect, useCallback } from 'react'
import QRCode from 'qrcode'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { Icon, Btn, Segmented } from './ui'

export default function SelfServiceLinkPanel() {
  const { hasCapability } = useAuth()
  const toast = useToast()
  const canEdit = hasCapability(CAP.MANAGE_SELECTIONS)

  const [open, setOpen] = useState(false)
  const [cfg, setCfg] = useState(null)
  const [busy, setBusy] = useState(false)
  const [qr, setQr] = useState(null)

  const fullUrl = cfg?.token ? `${window.location.origin}/avail/${cfg.token}` : ''
  const message = fullUrl ? `🏏 Set your availability: ${fullUrl}` : ''

  const load = useCallback(() => {
    api.bsGetSelfService().then(setCfg).catch(() => setCfg(null))
  }, [])
  useEffect(() => { load() }, [load])

  // Render the QR client-side whenever the link changes (and the card is open).
  useEffect(() => {
    if (!open || !fullUrl) { setQr(null); return }
    let alive = true
    QRCode.toDataURL(fullUrl, { margin: 1, width: 240, errorCorrectionLevel: 'M' })
      .then((u) => { if (alive) setQr(u) })
      .catch(() => { if (alive) setQr(null) })
    return () => { alive = false }
  }, [open, fullUrl])

  const update = async (patch) => {
    if (!canEdit) return
    setBusy(true)
    try {
      setCfg(await api.bsSetSelfService(patch))
    } catch (e) {
      toast.error(e.message || 'Update failed')
    } finally { setBusy(false) }
  }

  const regenerate = async () => {
    if (!canEdit) return
    if (!window.confirm('Generate a new link? The old link and QR code will stop working immediately.')) return
    setBusy(true)
    try {
      setCfg(await api.bsRegenerateSelfService())
      toast.success('New link generated — reshare it with your players.')
    } catch (e) {
      toast.error(e.message || 'Regenerate failed')
    } finally { setBusy(false) }
  }

  const copy = async (text, what) => {
    try {
      await navigator.clipboard.writeText(text)
      toast.success(`${what} copied`)
    } catch {
      toast.error('Copy failed — select and copy manually')
    }
  }

  if (!cfg) return null

  const enabled = !!cfg.enabled
  const cov = cfg.phone_coverage || { with_phone: 0, total: 0 }
  const noPhone = Math.max(0, (cov.total || 0) - (cov.with_phone || 0))

  return (
    <div className="pb-card mb-4">
      {/* Header / summary — click to expand */}
      <button onClick={() => setOpen((o) => !o)} className="w-full flex items-center gap-3 px-4 py-3 text-left">
        <span className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style={{ background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)', color: 'var(--pb-accent)' }}>
          <Icon name="availability" size={17} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="font-display font-bold text-[15px] flex items-center gap-2">
            Self-service link
            <span className="font-mono text-[10px] px-2 py-0.5 rounded-full" style={enabled
              ? { background: 'color-mix(in srgb, var(--pb-positive) 16%, transparent)', color: 'var(--pb-positive)' }
              : { background: 'var(--pb-surface2)', color: 'var(--pb-faintest)' }}>
              {enabled ? 'ON' : 'OFF'}
            </span>
          </div>
          <div className="text-[12.5px] text-pb-faint mt-0.5">
            Let players set their own availability with a link + PIN — no logins.
          </div>
        </div>
        <span className="text-pb-faint shrink-0">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 border-t pb-hairline pt-4 flex flex-col gap-4">
          {/* Enable + PIN toggles */}
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
            <div className="flex items-center gap-2.5">
              <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Status</span>
              <Segmented sm value={enabled ? 'on' : 'off'} onChange={(v) => update({ enabled: v === 'on' })}
                options={[{ value: 'on', label: 'Enabled' }, { value: 'off', label: 'Off' }]} />
            </div>
            {enabled && (
              <div className="flex items-center gap-2.5">
                <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">PIN</span>
                <Segmented sm value={cfg.require_pin ? 'pin' : 'nopin'} onChange={(v) => update({ require_pin: v === 'pin' })}
                  options={[{ value: 'pin', label: 'Last-4 PIN' }, { value: 'nopin', label: 'No PIN' }]} />
              </div>
            )}
          </div>

          {!enabled ? (
            <p className="text-sm text-pb-faint">
              Turn this on to generate a shareable link. Players open it, find their name, prove it’s them with the last 4 digits of their mobile, and tap their availability for the weekend.
            </p>
          ) : (
            <>
              {/* The link */}
              <div>
                <label className="block font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1.5">Shareable link</label>
                <div className="flex flex-wrap items-center gap-2">
                  <input readOnly value={fullUrl} onFocus={(e) => e.target.select()}
                    className="flex-1 min-w-[220px] bg-pb-surface2 border pb-hairline rounded-lg px-3 py-2 text-sm font-mono text-pb-dim" />
                  <Btn sm onClick={() => copy(fullUrl, 'Link')}>Copy link</Btn>
                  <Btn sm onClick={() => copy(message, 'Message')}>Copy message</Btn>
                  {canEdit && <Btn sm variant="ghost" onClick={regenerate} disabled={busy}>Regenerate</Btn>}
                </div>
                <p className="text-[11px] text-pb-faintest mt-1.5">
                  Pin it in your team’s group chat or Facebook group. Anyone with the link still needs a player’s own PIN to set their availability.
                </p>
              </div>

              {/* QR + coverage */}
              <div className="flex flex-wrap items-start gap-5">
                {qr && (
                  <div className="text-center">
                    <img src={qr} alt="Availability link QR code" className="w-40 h-40 rounded-lg bg-white p-2" />
                    <div className="font-mono text-[10px] text-pb-faintest mt-1.5">Scan to open</div>
                  </div>
                )}
                <div className="flex-1 min-w-[200px]">
                  <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1.5">Phone coverage</div>
                  <div className="text-sm text-pb-dim">
                    <b className="text-pb-text">{cov.with_phone}</b> of <b className="text-pb-text">{cov.total}</b> active players have a mobile on file{cfg.require_pin ? ' and can self-serve.' : '.'}
                  </div>
                  {cfg.require_pin && noPhone > 0 && (
                    <div className="mt-2 text-[12.5px] rounded-lg px-3 py-2" style={{ background: 'color-mix(in srgb, var(--pb-amber) 12%, transparent)', color: 'var(--pb-amber)' }}>
                      {noPhone} player{noPhone === 1 ? '' : 's'} can’t self-serve without a mobile number.{' '}
                      <a href="/admin/betterselect/players" className="underline">Add numbers</a> so they can.
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
