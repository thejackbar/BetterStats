import { useCallback, useEffect, useState } from 'react'
import QRCode from 'qrcode'
import { api } from '../../lib/api'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import { useToast } from '../../contexts/ToastContext'
import { Btn, Segmented } from './betterselect/ui'
import { PageModules } from './betterselect/SelfServiceLinkPanel'

// Player Dashboard (BetterStats): the page each player opens with a link and the last four digits of
// their mobile. It holds their Player Cards and their season, so it needs BetterStats and nothing
// else. A club that also has BetterSelect keeps a separate switch for availability and votes on the
// same link (BetterSelect > Availability); the two switches do not affect each other.

function Setting({ label, attr, children }) {
  return (
    <div className="flex items-center gap-2.5" {...{ [attr]: true }}>
      <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">{label}</span>
      {children}
    </div>
  )
}

export default function AdminPlayerDashboard() {
  const toast = useToast()
  const [cfg, setCfg] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [qr, setQr] = useState(null)

  const load = useCallback(() => {
    api.getPlayerDashboardSettings().then(setCfg).catch((e) => setError(e?.message || 'Could not load the Player Dashboard settings.'))
  }, [])
  useEffect(() => { load() }, [load])

  const fullUrl = cfg?.token ? `${window.location.origin}/playerdash/${cfg.token}` : ''
  useEffect(() => {
    if (!fullUrl || !cfg?.enabled) { setQr(null); return }
    let alive = true
    QRCode.toDataURL(fullUrl, { margin: 1, width: 240, errorCorrectionLevel: 'M' })
      .then((u) => { if (alive) setQr(u) })
      .catch(() => { if (alive) setQr(null) })
    return () => { alive = false }
  }, [fullUrl, cfg?.enabled])

  const update = async (patch) => {
    setBusy(true)
    try {
      setCfg(await api.setPlayerDashboardSettings(patch))
    } catch (e) {
      toast.error(e.message || 'Update failed')
    } finally { setBusy(false) }
  }

  const regenerate = async () => {
    if (!window.confirm('Generate a new link? The old link and QR code will stop working immediately.')) return
    setBusy(true)
    try {
      setCfg(await api.regeneratePlayerDashboardLink())
      toast.success('New link generated. Reshare it with your players.')
    } catch (e) {
      toast.error(e.message || 'Regenerate failed')
    } finally { setBusy(false) }
  }

  const copy = async (text, what) => {
    try {
      await navigator.clipboard.writeText(text)
      toast.success(`${what} copied`)
    } catch {
      toast.error('Copy failed. Select and copy manually.')
    }
  }

  const enabled = !!cfg?.enabled
  const cov = cfg?.phone_coverage || { with_phone: 0, total: 0 }
  const noPhone = Math.max(0, (cov.total || 0) - (cov.with_phone || 0))

  return (
    <BetterStatsLayout>
      <div className="max-w-3xl" data-player-dashboard-admin>
        <h1 className="font-display font-bold text-2xl text-pb-text">Player Dashboard</h1>
        <p className="text-sm text-pb-faint mt-1 mb-4">
          A page for each player: their Player Cards, their season and where they sit in the club. They open the club's link, find their name and enter the last four digits of their mobile. It needs BetterStats and nothing else.
        </p>
        {error && <div role="alert" className="text-sm text-pb-red mb-4">{error}</div>}
        {!cfg && !error && <div className="text-sm text-pb-faint">Loading…</div>}
        {cfg && (
          <div className="pb-card p-4 flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
              <Setting label="Status" attr="data-dash-enabled-setting">
                <Segmented sm value={enabled ? 'on' : 'off'} onChange={(v) => update({ enabled: v === 'on' })}
                  options={[{ value: 'on', label: 'On' }, { value: 'off', label: 'Off' }]} />
              </Setting>
              <Setting label="PIN" attr="data-dash-pin-setting">
                <Segmented sm value={cfg.require_pin ? 'pin' : 'nopin'} onChange={(v) => update({ require_pin: v === 'pin' })}
                  options={[{ value: 'pin', label: 'Last-4 PIN' }, { value: 'nopin', label: 'No PIN' }]} />
              </Setting>
              <Setting label="Club website button" attr="data-dash-site-setting">
                <Segmented sm value={cfg.show_on_site ? 'on' : 'off'} onChange={(v) => update({ show_on_site: v === 'on' })}
                  options={[{ value: 'on', label: 'Shown' }, { value: 'off', label: 'Hidden' }]} />
              </Setting>
            </div>
            <p className="text-[11.5px] text-pb-faintest -mt-2" data-dash-state-note>
              {enabled
                ? (cfg.show_on_site
                  ? 'Your public site shows a Player Dashboard button beside Admin. Anyone can open it, and each player still needs their PIN.'
                  : 'The Player Dashboard button is hidden on your public site. The link still works wherever you share it.')
                : (cfg.availability_enabled
                  ? 'The dashboard is off. The link still opens for availability and votes, with no Player Cards or season, and the button is not on your public site.'
                  : 'The dashboard is off. Nobody can open it, and the button is not on your public site.')}
            </p>
            {!cfg.require_pin && (
              <p className="text-[12px] rounded-lg px-3 py-2" style={{ background: 'color-mix(in srgb, var(--pb-amber) 12%, transparent)', color: 'var(--pb-amber)' }} data-dash-nopin-note>
                With no PIN, anyone who has the link can open any player's page, including their cards and swaps. Fees are never shown without the PIN.
              </p>
            )}
            {cfg.has_select && (
              <p className="text-[11.5px] text-pb-faintest" data-dash-select-note>
                Your club has BetterSelect, so the same link also carries availability and votes. They have their own switch in BetterSelect &gt; Availability, which is {cfg.availability_enabled ? 'on' : 'off'} now. Turning the dashboard on or off here does not change it.
              </p>
            )}

            {enabled && cfg.path && (
              <div>
                <label className="block font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1.5">Shareable link</label>
                <div className="flex flex-wrap items-center gap-2">
                  <input readOnly value={fullUrl} onFocus={(e) => e.target.select()}
                    className="flex-1 min-w-[220px] bg-pb-surface2 border pb-hairline rounded-lg px-3 py-2 text-sm font-mono text-pb-dim" />
                  <Btn sm onClick={() => copy(fullUrl, 'Link')}>Copy link</Btn>
                  <Btn sm onClick={() => copy(`🏏 Your player dashboard: ${fullUrl}`, 'Message')}>Copy message</Btn>
                  <Btn sm variant="ghost" onClick={regenerate} disabled={busy}>Regenerate</Btn>
                </div>
                <p className="text-[11px] text-pb-faintest mt-1.5">
                  Pin it in your team's group chat or Facebook group. It never picks a name for anybody: each person finds their own and enters the last four digits of their own mobile.
                </p>
              </div>
            )}

            {enabled && (
              <div className="flex flex-wrap items-start gap-5">
                {qr && (
                  <div className="text-center">
                    <img src={qr} alt="Player Dashboard link QR code" className="w-40 h-40 rounded-lg bg-white p-2" />
                    <div className="font-mono text-[10px] text-pb-faintest mt-1.5">Scan to open</div>
                  </div>
                )}
                <div className="flex-1 min-w-[200px]" data-dash-coverage>
                  <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1.5">Phone coverage</div>
                  <div className="text-sm text-pb-dim">
                    <b className="text-pb-text">{cov.with_phone}</b> of <b className="text-pb-text">{cov.total}</b> active players have a mobile on file{cfg.require_pin ? ' and can sign in.' : '.'}
                  </div>
                  {cfg.require_pin && noPhone > 0 && (
                    <div className="mt-2 text-[12.5px] rounded-lg px-3 py-2" style={{ background: 'color-mix(in srgb, var(--pb-amber) 12%, transparent)', color: 'var(--pb-amber)' }}>
                      {noPhone} player{noPhone === 1 ? '' : 's'} can't sign in without a mobile number. Add numbers on the Players page so they can.
                    </div>
                  )}
                </div>
              </div>
            )}

            <PageModules modules={cfg.dashboard_modules || []} canEdit busy={busy}
              onChange={(keys) => update({ dashboard_modules: keys })} />
          </div>
        )}
      </div>
    </BetterStatsLayout>
  )
}
