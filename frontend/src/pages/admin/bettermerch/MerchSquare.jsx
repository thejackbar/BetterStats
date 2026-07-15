import { useState, useEffect, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import BetterMerchLayout from '../../../components/admin/BetterMerchLayout'
import { PbSpinner } from '../../../lib/presskit'
import { Btn, Select, Pill, Icon } from './ui'

function Toggle({ label, hint, checked, onChange }) {
  return (
    <label className="flex items-start gap-3 cursor-pointer py-2">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-1" />
      <span>
        <span className="text-[13.5px] text-pb-text">{label}</span>
        {hint && <span className="block text-[11.5px] text-pb-faint">{hint}</span>}
      </span>
    </label>
  )
}

export default function MerchSquare() {
  const toast = useToast()
  const [params, setParams] = useSearchParams()
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [locations, setLocations] = useState(null)
  const [result, setResult] = useState(null)

  const load = useCallback(async () => {
    try {
      const s = await api.merchSquareStatus()
      setStatus(s)
      if (s.connected && s.needs_location) {
        api.merchSquareLocations().then((d) => setLocations(d.locations || [])).catch(() => {})
      }
    } catch (e) {
      toast.error(e.message || 'Could not load Square status')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Surface the OAuth redirect result, then clean the URL.
  useEffect(() => {
    if (params.get('connected')) { toast.success('Square connected'); params.delete('connected'); setParams(params, { replace: true }) }
    else if (params.get('error')) { toast.error(`Square: ${params.get('error')}`); params.delete('error'); setParams(params, { replace: true }) }
  }, [])

  const connect = async () => {
    setBusy(true)
    try {
      const { url } = await api.merchSquareConnectUrl()
      window.location.href = url
    } catch (e) {
      toast.error(e.message || 'Could not start Square connect')
      setBusy(false)
    }
  }

  const pickLocation = async (loc) => {
    setBusy(true)
    try {
      const s = await api.merchSquareSetLocation(loc.id, loc.name)
      setStatus(s); setLocations(null)
      toast.success(`Syncing ${loc.name}`)
    } catch (e) { toast.error(e.message || 'Could not set location') } finally { setBusy(false) }
  }

  const saveSetting = async (patch) => {
    try { setStatus(await api.merchSquareSettings(patch)) }
    catch (e) { toast.error(e.message || 'Could not save') }
  }

  const syncNow = async () => {
    setBusy(true); setResult(null)
    try {
      const r = await api.merchSquareSync()
      setResult(r)
      toast.success('Synced from Square')
      load()
    } catch (e) { toast.error(e.message || 'Sync failed') } finally { setBusy(false) }
  }

  const disconnect = async () => {
    if (!window.confirm('Disconnect Square? Your synced products stay, but stock will no longer update from Square.')) return
    setBusy(true)
    try { await api.merchSquareDisconnect(); setStatus(await api.merchSquareStatus()); toast.success('Disconnected') }
    catch (e) { toast.error(e.message || 'Could not disconnect') } finally { setBusy(false) }
  }

  return (
    <BetterMerchLayout title="Square">
      {loading ? <PbSpinner message="Loading…" /> : !status ? null : (
        <div className="max-w-2xl space-y-5">
          <p className="text-[13px] text-pb-faint">
            Connect your club's Square account and BetterMerch mirrors your canteen and bar items, keeps their on-hand counts up to date, and pulls completed sales into your reports. Square stays the till; this is read-only.
          </p>

          {!status.configured ? (
            <div className="pb-card p-5 border-pb-amber/30">
              <div className="flex items-center gap-2 mb-1"><Icon name="info" size={16} className="text-pb-amber" /><b className="text-sm">Square isn't set up on the server yet</b></div>
              <p className="text-[12.5px] text-pb-faint mb-3">This is a one-off, server-wide setup an administrator does once. After it's done, every club connects its own Square account from this page.</p>
              <ol className="space-y-2.5 text-[12.5px] text-pb-faint list-decimal list-inside">
                <li>Go to <span className="text-pb-text">developer.squareup.com/apps</span> and sign in with your Square account.</li>
                <li>Click <b className="text-pb-text">+ Create App</b> (or open an existing one).</li>
                <li>Open the <b className="text-pb-text">Credentials</b> tab and copy the <b className="text-pb-text">Production Application ID</b> and <b className="text-pb-text">Application Secret</b>.</li>
                <li>
                  Open the <b className="text-pb-text">OAuth</b> tab and add this as an Authorized Redirect URL:
                  <div className="mt-1"><code className="text-pb-text bg-pb-hairline/40 px-2 py-1 rounded text-[11.5px] break-all">https://betterat.cricket/api/public/square/callback</code></div>
                </li>
                <li>
                  Add these to the server's <code className="text-pb-text">.env</code> and redeploy the backend:
                  <div className="mt-1 space-y-0.5">
                    <div><code className="text-pb-text bg-pb-hairline/40 px-2 py-1 rounded text-[11.5px]">SQUARE_APP_ID=&hellip;</code></div>
                    <div><code className="text-pb-text bg-pb-hairline/40 px-2 py-1 rounded text-[11.5px]">SQUARE_APP_SECRET=&hellip;</code></div>
                    <div><code className="text-pb-text bg-pb-hairline/40 px-2 py-1 rounded text-[11.5px]">SQUARE_ENVIRONMENT=production</code></div>
                  </div>
                </li>
              </ol>
              <p className="text-[11.5px] text-pb-faintest mt-3">Once that's live, this notice is replaced by a Connect Square button for each club to use.</p>
            </div>
          ) : !status.connected ? (
            <div className="pb-card p-6 text-center">
              <Icon name="share" size={28} className="text-pb-accent mx-auto mb-3" />
              <h3 className="font-display font-bold text-base mb-1">Connect Square</h3>
              <p className="text-[12.5px] text-pb-faint mb-4">You'll be sent to Square to approve read access to your items, inventory and sales.</p>
              <Btn variant="primary" onClick={connect} disabled={busy} icon="share">Connect Square</Btn>
            </div>
          ) : (
            <>
              <div className="pb-card p-5 space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <Pill tone="green">Connected</Pill>
                    {status.environment === 'sandbox' && <Pill tone="amber">sandbox</Pill>}
                    {status.merchant_id && <span className="font-mono text-[10.5px] text-pb-faintest">{status.merchant_id}</span>}
                  </div>
                  <button onClick={disconnect} disabled={busy} className="text-[12px] text-pb-faint hover:text-pb-red">Disconnect</button>
                </div>

                {status.needs_location ? (
                  <div className="border-t border-pb-hairline pt-3">
                    <div className="text-[12.5px] text-pb-faint mb-2">Pick the Square location to sync (your canteen or bar):</div>
                    {locations === null ? <PbSpinner message="Loading locations…" />
                      : locations.length === 0 ? <p className="text-[12.5px] text-pb-faint">No locations found on this Square account.</p>
                      : <div className="space-y-2">
                          {locations.map((l) => (
                            <button key={l.id} disabled={busy} onClick={() => pickLocation(l)}
                              className="block w-full text-left px-3 py-2 rounded-lg border border-pb-hairline2 hover:border-pb-accent/50 text-[13px]">
                              {l.name} {l.status && l.status !== 'ACTIVE' && <span className="text-pb-faint">({l.status.toLowerCase()})</span>}
                            </button>
                          ))}
                        </div>}
                  </div>
                ) : (
                  <div className="border-t border-pb-hairline pt-3 flex items-center justify-between gap-3">
                    <div className="text-[13px]">Location: <b>{status.location_name || status.location_id}</b></div>
                    <button onClick={() => { setLocations(null); setStatus({ ...status, needs_location: true }); api.merchSquareLocations().then((d) => setLocations(d.locations || [])).catch(() => setLocations([])) }}
                      className="text-[11.5px] text-pb-faint hover:text-pb-accent">change</button>
                  </div>
                )}
              </div>

              {!status.needs_location && (
                <>
                  <div className="pb-card p-5">
                    <Toggle label="Keep stock in sync" hint="Pull catalog + current inventory counts" checked={status.sync_enabled} onChange={(v) => saveSetting({ sync_enabled: v })} />
                    <Toggle label="Import sales" hint="Pull completed sales into Activity + Reports as revenue" checked={status.sync_sales} onChange={(v) => saveSetting({ sync_sales: v })} />
                  </div>

                  <div className="pb-card p-5">
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-[12.5px] text-pb-faint">
                        {status.last_sync_at
                          ? <>Last sync {new Date(status.last_sync_at).toLocaleString()} {status.last_sync_status === 'error' ? <Pill tone="red">failed</Pill> : <Pill tone="green">ok</Pill>}</>
                          : 'Not synced yet. Runs automatically each day, or sync now.'}
                      </div>
                      <Btn variant="primary" onClick={syncNow} disabled={busy} icon="bolt">Sync now</Btn>
                    </div>
                    {status.last_sync_error && <p className="text-[11.5px] text-pb-red mt-2">{status.last_sync_error}</p>}
                    {result && (
                      <div className="mt-3 text-[12.5px] text-pb-faint flex flex-wrap gap-x-4 gap-y-1">
                        <span>{result.products_added} products added</span>
                        <span>{result.variants_added} lines added</span>
                        <span>{result.inventory_updated} counts updated</span>
                        <span>{result.sales_imported} sales imported</span>
                      </div>
                    )}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      )}
    </BetterMerchLayout>
  )
}
