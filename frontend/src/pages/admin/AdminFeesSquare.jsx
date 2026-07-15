import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
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

export default function AdminFeesSquare() {
  const toast = useToast()
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [savingSettings, setSavingSettings] = useState(false)
  const [keywordsDraft, setKeywordsDraft] = useState('')

  const [seasons, setSeasons] = useState([])
  const [seasonId, setSeasonId] = useState('')
  const [members, setMembers] = useState([])
  const [previewing, setPreviewing] = useState(false)
  const [rows, setRows] = useState(null)
  const [committing, setCommitting] = useState(false)

  const loadStatus = useCallback(async () => {
    try {
      const s = await api.feeSquareStatus()
      setStatus(s)
      setKeywordsDraft(s.fee_item_keywords || '')
    } catch (e) { toast.error(e.message || 'Could not load Square status') }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { loadStatus() }, [loadStatus])

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

  async function toggleSyncFees(v) {
    setSavingSettings(true)
    try { setStatus(await api.feeSquareSettings({ sync_fees: v })) }
    catch (e) { toast.error(e.message || 'Could not save') }
    finally { setSavingSettings(false) }
  }

  async function saveKeywords() {
    setSavingSettings(true)
    try { setStatus(await api.feeSquareSettings({ fee_item_keywords: keywordsDraft })); toast.success('Saved') }
    catch (e) { toast.error(e.message || 'Could not save') }
    finally { setSavingSettings(false) }
  }

  async function runPreview() {
    if (!seasonId) return
    setPreviewing(true); setRows(null)
    try {
      const p = await api.feeSquarePreview(seasonId)
      setRows(p.rows.map(r => ({
        ...r,
        selected: !!r.suggested && r.suggested.confidence >= 0.85,
        chosen_member_season_id: r.suggested?.member_season_id || '',
        kind: 'match_day',
      })))
      toast.success(`Found ${p.rows.length} Square sale${p.rows.length === 1 ? '' : 's'} to review`)
    } catch (e) { toast.error(e.message || 'Could not check Square') }
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
        external_ref: r.external_ref, item_name: r.item_name, amount: r.amount,
        occurred_at: r.occurred_at, note: r.note, member_season_id: r.chosen_member_season_id, kind: r.kind,
      }))
      const res = await api.feeSquareCommit(items)
      toast.success(`Recorded ${res.created} payment${res.created === 1 ? '' : 's'}`)
      setRows(rs => rs.filter(r => !ready.includes(r)))
    } catch (e) { toast.error(e.message || 'Import failed') }
    finally { setCommitting(false) }
  }

  async function dismiss(row) {
    try {
      await api.feeSquareDismiss({
        external_ref: row.external_ref, item_name: row.item_name, note: row.note,
        amount: row.amount, occurred_at: row.occurred_at,
      })
      setRows(rs => rs.filter(r => r.external_ref !== row.external_ref))
    } catch (e) { toast.error(e.message || 'Could not dismiss') }
  }

  const inp = 'bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
  const cell = 'bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-pb-text text-[12px] focus:outline-none focus:border-pb-accent'

  return (
    <BetterFeesLayout title="Square">
      {loading ? <PbSpinner message="Loading…" /> : !status ? null : (
        <div className="max-w-6xl space-y-5">
          <p className="text-[13px] text-pb-faint">
            Match fees or subs paid through Square (POS or a payment link) can be pulled in and matched to a member here.
            This reads the same Square connection as BetterMerch — nothing here writes back to Square, and every match is
            confirmed by hand before it's recorded as a payment.
          </p>

          {!status.configured ? (
            <div className="pb-card p-5 border-pb-amber/30 text-[12.5px] text-pb-faint">
              Square isn't set up on the server yet. See the setup guide on <Link to="/admin/merch/square" className="text-pb-accent hover:underline">BetterMerch's Square page</Link>.
            </div>
          ) : !status.connected ? (
            <div className="pb-card p-6 text-center text-[12.5px] text-pb-faint">
              <p className="mb-3">Your club hasn't connected Square yet. Square connects once per club and is then shared across BetterMerch and BetterFees.</p>
              <Link to="/admin/merch/square" className="inline-block px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg" style={{ background: 'var(--pb-accent)' }}>
                CONNECT VIA BETTERMERCH
              </Link>
            </div>
          ) : (
            <>
              <div className="pb-card p-5 space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-[13px]">Connected via BetterMerch's Square account{status.location_name ? <> — <b>{status.location_name}</b></> : ''}</div>
                </div>
                <label className="flex items-start gap-3 cursor-pointer py-1 border-t pb-hairline pt-3">
                  <input type="checkbox" checked={status.sync_fees} disabled={savingSettings}
                    onChange={e => toggleSyncFees(e.target.checked)} className="mt-1" />
                  <span>
                    <span className="text-[13.5px] text-pb-text">Import fee payments from Square</span>
                    <span className="block text-[11.5px] text-pb-faint">Turns on the review queue below. Off by default so it can't surface anything before you've set which item names count as a fee sale.</span>
                  </span>
                </label>
                {status.sync_fees && (
                  <div className="pt-1">
                    <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">SQUARE ITEM NAMES THAT COUNT AS A FEE SALE</label>
                    <div className="flex gap-2">
                      <input className={`${inp} flex-1`} placeholder="e.g. Match Fee, Membership"
                        value={keywordsDraft} onChange={e => setKeywordsDraft(e.target.value)} />
                      <button onClick={saveKeywords} disabled={savingSettings}
                        className="px-3 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text hover:border-pb-accent transition-colors whitespace-nowrap">
                        SAVE
                      </button>
                    </div>
                    <p className="text-[11px] text-pb-faintest mt-1">Comma-separated. A Square line item is pulled in when its name contains any of these (not case-sensitive).</p>
                  </div>
                )}
              </div>

              {status.sync_fees && (
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
                        {previewing ? 'CHECKING SQUARE…' : 'CHECK SQUARE'}
                      </button>
                    </div>
                    {status.last_sync_at && (
                      <p className="text-[11px] text-pb-faintest mt-2">
                        Last checked {new Date(status.last_sync_at).toLocaleString()}
                        {status.last_sync_status === 'error' && status.last_sync_error && <span className="text-pb-red"> — {status.last_sync_error}</span>}
                      </p>
                    )}
                  </div>

                  {previewing && <PbSpinner message="Checking Square…" />}

                  {rows && rows.length === 0 && (
                    <div className="pb-card p-6 text-center text-pb-dim text-sm">Nothing new to review — every matching Square sale is already recorded or dismissed.</div>
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
                              <th className="py-2.5 pr-2">ITEM / NOTE</th>
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
                                <td className="py-2 pr-2 text-pb-dim truncate max-w-[240px]">
                                  {r.item_name}{r.note && <span className="text-pb-faintest"> · {r.note}</span>}
                                </td>
                                <td className="py-2 pr-2">
                                  <select className={`${cell} w-full`} value={r.chosen_member_season_id}
                                    onChange={e => patchRow(idx, { chosen_member_season_id: e.target.value, selected: !!e.target.value })}>
                                    <option value="">— No match (skip) —</option>
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
                        Confidence ≥ 85% rows are auto-selected; review the rest. SKIP dismisses a row for good (e.g. a canteen sale that happened to match a keyword) — it won't come back next check.
                      </p>
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
