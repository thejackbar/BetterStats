import { useState, useEffect, useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import BetterFeesLayout from '../../components/admin/BetterFeesLayout'
import { PbSpinner } from '../../lib/presskit'
import { formatSeason } from '../../lib/cricketFormat'

const money = n => `$${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`

function sortSeasons(seasons) {
  return seasons.filter(s => !s.alias_of).sort((a, b) => (b.year || 0) - (a.year || 0) || (b.name > a.name ? 1 : -1))
}

function ConfidenceDot({ score }) {
  if (score == null) return <span className="font-mono text-[9px] text-pb-faintest">—</span>
  const tone = score >= 0.85 ? 'text-green-300' : score >= 0.6 ? 'text-pb-amber' : 'text-pb-red/60'
  return <span className={`font-mono text-[10px] ${tone}`}>{Math.round(score * 100)}%</span>
}

export default function AdminFeesXero() {
  const toast = useToast()
  const [params, setParams] = useSearchParams()
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [tenants, setTenants] = useState(null)
  const [accounts, setAccounts] = useState(null)

  const [seasons, setSeasons] = useState([])
  const [seasonId, setSeasonId] = useState('')
  const [members, setMembers] = useState([])
  const [previewing, setPreviewing] = useState(false)
  const [rows, setRows] = useState(null)
  const [committing, setCommitting] = useState(false)

  const loadStatus = useCallback(async () => {
    try {
      const s = await api.feeXeroStatus()
      setStatus(s)
      if (s.needs_tenant) api.feeXeroTenants().then(d => setTenants(d.tenants || [])).catch(() => {})
      if (s.tenant_name && s.needs_bank_account) api.feeXeroBankAccounts().then(d => setAccounts(d.accounts || [])).catch(() => {})
    } catch (e) { toast.error(e.message || 'Could not load Xero status') }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { loadStatus() }, [loadStatus])

  useEffect(() => {
    if (params.get('connected')) { toast.success('Xero connected'); params.delete('connected'); setParams(params, { replace: true }) }
    else if (params.get('error')) { toast.error(`Xero: ${params.get('error')}`); params.delete('error'); setParams(params, { replace: true }) }
  }, [])

  useEffect(() => {
    api.adminListSeasons()
      .then(s => { const sorted = sortSeasons(s); setSeasons(sorted); if (sorted[0]) setSeasonId(sorted[0].id) })
      .catch(e => toast.error(e.message))
  }, [])

  useEffect(() => {
    if (!seasonId) return
    api.feeListMembers(seasonId).then(d =>
      setMembers((d.members || []).map(m => ({ member_season_id: m.member_season_id, full_name: m.full_name })))
    ).catch(() => setMembers([]))
  }, [seasonId])

  const connect = async () => {
    setBusy(true)
    try {
      const { url } = await api.feeXeroConnectUrl()
      window.location.href = url
    } catch (e) { toast.error(e.message || 'Could not start Xero connect'); setBusy(false) }
  }

  const pickTenant = async (t) => {
    setBusy(true)
    try {
      const s = await api.feeXeroSetTenant(t.id, t.name)
      setStatus(s); setTenants(null)
      if (s.needs_bank_account) api.feeXeroBankAccounts().then(d => setAccounts(d.accounts || [])).catch(() => {})
    } catch (e) { toast.error(e.message || 'Could not set organisation') }
    finally { setBusy(false) }
  }

  const pickAccount = async (a) => {
    setBusy(true)
    try {
      const s = await api.feeXeroSetBankAccount(a.id, a.name)
      setStatus(s); setAccounts(null)
      toast.success(`Using ${a.name}`)
    } catch (e) { toast.error(e.message || 'Could not set bank account') }
    finally { setBusy(false) }
  }

  const toggleSync = async (v) => {
    setBusy(true)
    try { setStatus(await api.feeXeroSettings({ sync_enabled: v })) }
    catch (e) { toast.error(e.message || 'Could not save') }
    finally { setBusy(false) }
  }

  const disconnect = async () => {
    if (!window.confirm('Disconnect Xero? Payments already recorded stay as they are.')) return
    setBusy(true)
    try { await api.feeXeroDisconnect(); setStatus(await api.feeXeroStatus()); setRows(null); toast.success('Disconnected') }
    catch (e) { toast.error(e.message || 'Could not disconnect') }
    finally { setBusy(false) }
  }

  async function runPreview() {
    if (!seasonId) return
    setPreviewing(true); setRows(null)
    try {
      const p = await api.feeXeroPreview(seasonId)
      setRows(p.rows.map(r => ({
        ...r,
        selected: !!r.suggested && r.suggested.confidence >= 0.85,
        chosen_member_season_id: r.suggested?.member_season_id || '',
        kind: 'match_day',
      })))
      toast.success(`Found ${p.rows.length} Xero transaction${p.rows.length === 1 ? '' : 's'} to review`)
    } catch (e) { toast.error(e.message || 'Could not check Xero') }
    finally { setPreviewing(false) }
  }

  const ready = useMemo(() => (rows || []).filter(r => r.selected && r.chosen_member_season_id), [rows])

  function patchRow(idx, patch) {
    setRows(rs => rs.map((r, i) => i === idx ? { ...r, ...patch } : r))
  }

  async function commit() {
    if (ready.length === 0) return
    setCommitting(true)
    try {
      const items = ready.map(r => ({
        external_ref: r.external_ref, description: r.description, amount: r.amount,
        occurred_at: r.occurred_at, note: r.note, member_season_id: r.chosen_member_season_id, kind: r.kind,
      }))
      const res = await api.feeXeroCommit(items)
      toast.success(`Recorded ${res.created} payment${res.created === 1 ? '' : 's'}`)
      setRows(rs => rs.filter(r => !ready.includes(r)))
    } catch (e) { toast.error(e.message || 'Import failed') }
    finally { setCommitting(false) }
  }

  async function dismiss(row) {
    try {
      await api.feeXeroDismiss({
        external_ref: row.external_ref, description: row.description,
        amount: row.amount, occurred_at: row.occurred_at,
      })
      setRows(rs => rs.filter(r => r.external_ref !== row.external_ref))
    } catch (e) { toast.error(e.message || 'Could not dismiss') }
  }

  const inp = 'bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
  const cell = 'bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-pb-text text-[12px] focus:outline-none focus:border-pb-accent'

  return (
    <BetterFeesLayout title="Xero">
      {loading ? <PbSpinner message="Loading…" /> : !status ? null : (
        <div className="max-w-6xl space-y-5">
          <p className="text-[13px] text-pb-faint">
            Bank transactions already sitting in your club's Xero organisation can be pulled in and matched to a member here, 
            the same idea as the bank-statement CSV import, just live instead of an upload. Read-only: nothing here writes to Xero,
            and every match is confirmed by hand before it's recorded as a payment.
          </p>

          {!status.configured ? (
            <div className="pb-card p-5 border-pb-amber/30">
              <div className="flex items-center gap-2 mb-1"><b className="text-sm">Xero isn't set up on the server yet</b></div>
              <p className="text-[12.5px] text-pb-faint mb-3">This is a one-off, server-wide setup an administrator does once. After it's done, every club connects its own Xero organisation from this page.</p>
              <ol className="space-y-2.5 text-[12.5px] text-pb-faint list-decimal list-inside">
                <li>Go to <span className="text-pb-text">developer.xero.com/app/manage</span> and sign in with a Xero account.</li>
                <li>Click <b className="text-pb-text">New app</b> and choose <b className="text-pb-text">Web app</b> (not "Custom connection". That's pinned to one Xero organisation, and this needs to work for every club).</li>
                <li>
                  Set the redirect URI to:
                  <div className="mt-1"><code className="text-pb-text bg-pb-hairline/40 px-2 py-1 rounded text-[11.5px] break-all">https://betterat.cricket/api/public/xero/callback</code></div>
                </li>
                <li>Open <b className="text-pb-text">Configuration</b> and copy the <b className="text-pb-text">Client ID</b>; generate and copy the <b className="text-pb-text">Client Secret</b>.</li>
                <li>
                  Add these to the server's <code className="text-pb-text">.env</code> (and its compose service's environment list, if that's separately maintained) and redeploy the backend:
                  <div className="mt-1 space-y-0.5">
                    <div><code className="text-pb-text bg-pb-hairline/40 px-2 py-1 rounded text-[11.5px]">XERO_CLIENT_ID=&hellip;</code></div>
                    <div><code className="text-pb-text bg-pb-hairline/40 px-2 py-1 rounded text-[11.5px]">XERO_CLIENT_SECRET=&hellip;</code></div>
                  </div>
                </li>
              </ol>
              <p className="text-[11.5px] text-pb-faintest mt-3">Once that's live, this notice is replaced by a Connect Xero button for each club to use.</p>
            </div>
          ) : !status.connected ? (
            <div className="pb-card p-6 text-center">
              <h3 className="font-display font-bold text-base mb-1">Connect Xero</h3>
              <p className="text-[12.5px] text-pb-faint mb-4">You'll be sent to Xero to approve read-only access to your bank transactions.</p>
              <button onClick={connect} disabled={busy}
                className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50" style={{ background: 'var(--pb-accent)' }}>
                CONNECT XERO
              </button>
            </div>
          ) : (
            <>
              <div className="pb-card p-5 space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-[13px]">Connected{status.tenant_name ? <> — <b>{status.tenant_name}</b></> : ''}</div>
                  <button onClick={disconnect} disabled={busy} className="text-[12px] text-pb-faint hover:text-pb-red">Disconnect</button>
                </div>

                {status.needs_tenant ? (
                  <div className="border-t border-pb-hairline pt-3">
                    <div className="text-[12.5px] text-pb-faint mb-2">Pick the Xero organisation to use:</div>
                    {tenants === null ? <PbSpinner message="Loading organisations…" />
                      : tenants.length === 0 ? <p className="text-[12.5px] text-pb-faint">No organisations found on this Xero login.</p>
                      : <div className="space-y-2">
                          {tenants.map(t => (
                            <button key={t.id} disabled={busy} onClick={() => pickTenant(t)}
                              className="block w-full text-left px-3 py-2 rounded-lg border border-pb-hairline2 hover:border-pb-accent/50 text-[13px]">
                              {t.name}
                            </button>
                          ))}
                        </div>}
                  </div>
                ) : status.needs_bank_account ? (
                  <div className="border-t border-pb-hairline pt-3">
                    <div className="text-[12.5px] text-pb-faint mb-2">Pick the bank account to pull transactions from:</div>
                    {accounts === null ? <PbSpinner message="Loading bank accounts…" />
                      : accounts.length === 0 ? <p className="text-[12.5px] text-pb-faint">No bank accounts found in this organisation.</p>
                      : <div className="space-y-2">
                          {accounts.map(a => (
                            <button key={a.id} disabled={busy} onClick={() => pickAccount(a)}
                              className="block w-full text-left px-3 py-2 rounded-lg border border-pb-hairline2 hover:border-pb-accent/50 text-[13px]">
                              {a.name} {a.code && <span className="text-pb-faint">({a.code})</span>}
                            </button>
                          ))}
                        </div>}
                  </div>
                ) : (
                  <div className="border-t border-pb-hairline pt-3 flex items-center justify-between gap-3">
                    <div className="text-[13px]">Bank account: <b>{status.bank_account_name}</b></div>
                    <button onClick={() => { setAccounts(null); setStatus({ ...status, needs_bank_account: true }); api.feeXeroBankAccounts().then(d => setAccounts(d.accounts || [])).catch(() => setAccounts([])) }}
                      className="text-[11.5px] text-pb-faint hover:text-pb-accent">change</button>
                  </div>
                )}
              </div>

              {!status.needs_tenant && !status.needs_bank_account && (
                <>
                  <div className="pb-card p-5">
                    <label className="flex items-start gap-3 cursor-pointer py-1">
                      <input type="checkbox" checked={status.sync_enabled} disabled={busy}
                        onChange={e => toggleSync(e.target.checked)} className="mt-1" />
                      <span>
                        <span className="text-[13.5px] text-pb-text">Import bank transactions from Xero</span>
                        <span className="block text-[11.5px] text-pb-faint">Turns on the review queue below.</span>
                      </span>
                    </label>
                  </div>

                  {status.sync_enabled && (
                    <>
                      <div className="pb-card p-5">
                        <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-3 items-end">
                          <div>
                            <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">SEASON</label>
                            <select value={seasonId} onChange={e => setSeasonId(e.target.value)} className={`${inp} w-full`}>
                              {seasons.map(s => <option key={s.id} value={s.id}>{formatSeason(s)}</option>)}
                            </select>
                          </div>
                          <button onClick={runPreview} disabled={!seasonId || previewing}
                            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
                            {previewing ? 'CHECKING XERO…' : 'CHECK XERO'}
                          </button>
                        </div>
                        {status.last_sync_at && (
                          <p className="text-[11px] text-pb-faintest mt-2">
                            Last checked {new Date(status.last_sync_at).toLocaleString()}
                            {status.last_sync_status === 'error' && status.last_sync_error && <span className="text-pb-red">, {status.last_sync_error}</span>}
                          </p>
                        )}
                      </div>

                      {previewing && <PbSpinner message="Checking Xero…" />}

                      {rows && rows.length === 0 && (
                        <div className="pb-card p-6 text-center text-pb-dim text-sm">Nothing new to review. Every incoming transaction is already recorded or dismissed.</div>
                      )}

                      {rows && rows.length > 0 && (
                        <>
                          <div className="flex flex-wrap items-center gap-3 mb-1">
                            <span className="font-mono text-[10px] tracking-wide2 text-pb-faint">
                              {ready.length} of {rows.length} ready to record
                            </span>
                            <button onClick={() => setRows(rs => rs.map(r => ({ ...r, selected: !!r.chosen_member_season_id })))}
                              className="font-mono text-[10px] tracking-wide2 border pb-hairline rounded px-3 py-1.5 text-pb-faint hover:text-pb-text hover:border-pb-accent transition-colors">
                              SELECT ALL MATCHED
                            </button>
                            <button onClick={commit} disabled={ready.length === 0 || committing}
                              className="ml-auto px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50" style={{ background: 'var(--pb-accent)' }}>
                              {committing ? 'RECORDING…' : `RECORD ${ready.length}`}
                            </button>
                          </div>

                          <div className="pb-card overflow-x-auto">
                            <table className="w-full text-[12px] min-w-[1100px]">
                              <thead>
                                <tr className="font-mono text-[10px] tracking-wide3 text-pb-faint text-left bg-pb-surface2/40">
                                  <th className="py-2.5 pl-4 pr-2 w-8"></th>
                                  <th className="py-2.5 pr-2 w-24">DATE</th>
                                  <th className="py-2.5 pr-2 w-20 text-right">AMOUNT</th>
                                  <th className="py-2.5 pr-2">DESCRIPTION</th>
                                  <th className="py-2.5 pr-2 w-52">MEMBER</th>
                                  <th className="py-2.5 pr-2 w-16 text-center">CONF</th>
                                  <th className="py-2.5 pr-2 w-28">KIND</th>
                                  <th className="py-2.5 pr-4 w-16"></th>
                                </tr>
                              </thead>
                              <tbody>
                                {rows.map((r, idx) => (
                                  <tr key={r.external_ref} className={`pb-hairline-t align-middle ${r.selected ? 'bg-pb-surface2/40' : ''}`}>
                                    <td className="py-2 pl-4 pr-2">
                                      <input type="checkbox" checked={r.selected}
                                        onChange={e => patchRow(idx, { selected: e.target.checked })} className="cursor-pointer" />
                                    </td>
                                    <td className="py-2 pr-2 font-mono text-[11px] text-pb-dim whitespace-nowrap">{r.occurred_at || '—'}</td>
                                    <td className="py-2 pr-2 font-mono text-[11px] text-pb-text text-right">{money(r.amount)}</td>
                                    <td className="py-2 pr-2 text-pb-dim truncate max-w-[240px]">{r.description}</td>
                                    <td className="py-2 pr-2">
                                      <select className={`${cell} w-full`} value={r.chosen_member_season_id}
                                        onChange={e => patchRow(idx, { chosen_member_season_id: e.target.value, selected: !!e.target.value })}>
                                        <option value="">, No match (skip), </option>
                                        {r.candidates && r.candidates.length > 0 && (
                                          <optgroup label="Suggested">
                                            {r.candidates.map(c => (
                                              <option key={`s-${c.member_season_id}`} value={c.member_season_id}>
                                                {c.full_name} ({Math.round(c.confidence * 100)}%)
                                              </option>
                                            ))}
                                          </optgroup>
                                        )}
                                        <optgroup label="All members">
                                          {members.map(m => (
                                            <option key={m.member_season_id} value={m.member_season_id}>{m.full_name}</option>
                                          ))}
                                        </optgroup>
                                      </select>
                                    </td>
                                    <td className="py-2 pr-2 text-center"><ConfidenceDot score={r.suggested?.confidence} /></td>
                                    <td className="py-2 pr-2">
                                      <select className={`${cell} w-full`} value={r.kind} onChange={e => patchRow(idx, { kind: e.target.value })}>
                                        <option value="match_day">Match day</option>
                                        <option value="membership">Membership</option>
                                      </select>
                                    </td>
                                    <td className="py-2 pr-4 text-right">
                                      <button onClick={() => dismiss(r)} className="font-mono text-[9px] text-pb-faint hover:text-pb-red transition-colors">SKIP</button>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                          <p className="font-mono text-[10px] text-pb-faintest mt-3">
                            Confidence ≥ 85% rows are auto-selected; review the rest. SKIP dismisses a row for good (e.g. sponsorship income sitting in the same account), it won't come back next check.
                          </p>
                        </>
                      )}
                    </>
                  )}
                </>
              )}
            </>
          )}
        </div>
      )}
    </BetterFeesLayout>
  )
}
