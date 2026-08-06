import { useState, useEffect, useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import BetterFeesLayout from '../../components/admin/BetterFeesLayout'
import { Button, Field, Select, Empty, INPUT_CLS } from '../../components/admin/ui'
import { PbSpinner } from '../../lib/presskit'

import { formatSeason } from '../../lib/cricketFormat'

const money = n => `$${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`
const PAY_METHODS = ['EFT', 'Cash', 'PlayHQ', 'Comp', 'Other']

function sortSeasons(seasons) {
  return seasons.filter(s => !s.alias_of).sort((a, b) => (b.year || 0) - (a.year || 0) || (b.name > a.name ? 1 : -1))
}

function ConfidenceDot({ score }) {
  if (score == null) return <span className="font-mono text-[9px] text-pb-faintest">—</span>
  const tone = score >= 0.85 ? 'text-green-300' : score >= 0.6 ? 'text-pb-amber' : 'text-pb-red/60'
  return <span className={`font-mono text-[10px] ${tone}`}>{Math.round(score * 100)}%</span>
}

export default function AdminFeePaymentImport() {
  const toast = useToast()
  const navigate = useNavigate()
  const [seasons, setSeasons] = useState([])
  const [seasonId, setSeasonId] = useState('')
  const [members, setMembers] = useState([])
  const [file, setFile] = useState(null)
  const [previewing, setPreviewing] = useState(false)
  const [preview, setPreview] = useState(null)
  // rows is the editable working copy — rendered in the table.
  const [rows, setRows] = useState([])
  const [committing, setCommitting] = useState(false)

  useEffect(() => {
    api.adminListSeasons()
      .then(s => { const sorted = sortSeasons(s); setSeasons(sorted); if (sorted[0]) setSeasonId(sorted[0].id) })
      .catch(e => toast.error(e.message))
  }, [])

  // Members list — drives the per-row override dropdown.
  useEffect(() => {
    if (!seasonId) return
    api.feeListMembers(seasonId).then(d =>
      setMembers((d.members || []).map(m => ({
        member_id: m.member_id, member_season_id: m.member_season_id, full_name: m.full_name,
      })))
    ).catch(() => setMembers([]))
  }, [seasonId])

  async function runPreview() {
    if (!file || !seasonId) return
    setPreviewing(true); setPreview(null); setRows([])
    try {
      const p = await api.feeImportPreview(seasonId, file)
      setPreview(p)
      setRows(p.rows.map(r => ({
        ...r,
        selected: !!r.suggested && r.suggested.confidence >= 0.85,
        chosen_member_season_id: r.suggested?.member_season_id || '',
        kind: r.kind, method: r.method,
        bank_ref: r.description.slice(0, 120),
        notes: '',
      })))
      toast.success(`Parsed ${p.rows.length} credit rows`)
    } catch (e) { toast.error(e.message) } finally { setPreviewing(false) }
  }

  const ready = useMemo(() => rows.filter(r => r.selected && r.chosen_member_season_id), [rows])

  async function commit() {
    if (ready.length === 0) return
    setCommitting(true)
    try {
      const items = ready.map(r => ({
        member_season_id: r.chosen_member_season_id,
        amount: r.amount,
        paid_at: r.paid_at,
        kind: r.kind,
        method: r.method,
        bank_ref: r.bank_ref || null,
        notes: r.notes || null,
      }))
      const res = await api.feeImportCommit(items)
      toast.success(`Imported ${res.created} payment${res.created === 1 ? '' : 's'}`)
      navigate(`/admin/fees/payments`)
    } catch (e) { toast.error(e.message) } finally { setCommitting(false) }
  }

  function patchRow(idx, patch) {
    setRows(rs => rs.map((r, i) => i === idx ? { ...r, ...patch } : r))
  }

  const cell = `${INPUT_CLS} !px-2 !py-1.5 !text-[12px]`

  return (
    <BetterFeesLayout
      title="Import bank statement"
      caption="Match a bank CSV's credits to members"
      actions={<Button as={Link} to="/admin/fees/payments">← Payments</Button>}
    >
      <div className="max-w-6xl">
        <p className="text-pb-dim text-[13px] mb-5 leading-relaxed">
          Upload a CSV from your bank. Credit rows are matched to members by description; you confirm each match or
          override it, then commit them all at once. Debit rows and zero-value rows are ignored.
        </p>

        <div className="pb-card p-5 mb-6">
          <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto_auto] gap-3 items-end">
            <Field label="Season">
              <Select value={seasonId} onChange={e => setSeasonId(e.target.value)}>
                {seasons.map(s => <option key={s.id} value={s.id}>{formatSeason(s)}</option>)}
              </Select>
            </Field>
            <Field label="Bank CSV">
              <input type="file" accept=".csv,text/csv"
                onChange={e => setFile(e.target.files?.[0] || null)}
                className="block text-pb-dim text-[13px] file:bg-pb-surface2 file:border file:border-pb-hairline2 file:rounded-lg file:px-3 file:py-1.5 file:mr-3 file:text-[12.5px] file:text-pb-text file:cursor-pointer" />
            </Field>
            <Button variant="primary" onClick={runPreview} disabled={!file || !seasonId || previewing}>
              {previewing ? 'Parsing…' : 'Parse CSV'}
            </Button>
          </div>
        </div>

        {previewing && <PbSpinner message="Parsing CSV…" />}

        {preview && rows.length === 0 && (
          <div className="pb-card"><Empty>No credit rows found in this CSV.</Empty></div>
        )}

        {rows.length > 0 && (
          <>
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <span className="text-[12.5px] text-pb-dim mr-1">
                {ready.length} of {rows.length} rows ready to import
              </span>
              <Button size="sm" onClick={() => setRows(rs => rs.map(r => ({ ...r, selected: !!r.chosen_member_season_id })))}>
                Select all matched
              </Button>
              <Button size="sm" variant="quiet" onClick={() => setRows(rs => rs.map(r => ({ ...r, selected: false })))}>
                Clear
              </Button>
              <Button variant="primary" className="ml-auto" onClick={commit} disabled={ready.length === 0 || committing}>
                {committing ? 'Importing…' : `Import ${ready.length}`}
              </Button>
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
                    <th className="py-2.5 pr-2 w-20">METHOD</th>
                    <th className="py-2.5 pr-4"></th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, idx) => (
                    <tr key={idx} className={`pb-hairline-t align-middle ${r.selected ? 'bg-pb-surface2/40' : ''}`}>
                      <td className="py-2 pl-4 pr-2">
                        <input type="checkbox" checked={r.selected}
                          onChange={e => patchRow(idx, { selected: e.target.checked })}
                          className="cursor-pointer" />
                      </td>
                      <td className="py-2 pr-2 font-mono text-[11px] text-pb-dim">{r.paid_at || r.paid_at_raw}</td>
                      <td className="py-2 pr-2 font-mono text-[11px] text-pb-text text-right">{money(r.amount)}</td>
                      <td className="py-2 pr-2 text-pb-dim truncate max-w-[280px]">{r.description}</td>
                      <td className="py-2 pr-2">
                        <select className={cell}
                          value={r.chosen_member_season_id}
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
                      <td className="py-2 pr-2 text-center">
                        <ConfidenceDot score={r.suggested?.confidence} />
                      </td>
                      <td className="py-2 pr-2">
                        <select className={cell} value={r.kind} onChange={e => patchRow(idx, { kind: e.target.value })}>
                          <option value="membership">Membership</option>
                          <option value="match_day">Match day</option>
                        </select>
                      </td>
                      <td className="py-2 pr-2">
                        <select className={cell} value={r.method} onChange={e => patchRow(idx, { method: e.target.value })}>
                          {PAY_METHODS.map(m => <option key={m} value={m}>{m}</option>)}
                        </select>
                      </td>
                      <td className="py-2 pr-4"></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="font-mono text-[10px] text-pb-faintest mt-3">
              Confidence ≥ 85% rows are auto-selected; review the rest. The cleaned description is saved as <span className="text-pb-faint">bank_ref</span> on each payment.
            </p>
          </>
        )}
      </div>
    </BetterFeesLayout>
  )
}
