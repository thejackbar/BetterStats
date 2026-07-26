import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import AdminLayout from '../../components/admin/AdminLayout'
import { PbSpinner } from '../../lib/presskit'
import { Modal, Field, TextInput, NumberInput, Select, Btn, money, moneyToCents, centsToMoneyInput } from '../../components/admin/crm/ui'

// ── Period helpers (mirror backend services/crm_targets.py::period_bounds) ──

function currentFyYear(now = new Date()) {
  // AU convention: FY runs 1 Jul -> 30 Jun, named for the year it ENDS in.
  const m = now.getMonth() + 1
  return m >= 7 ? now.getFullYear() + 1 : now.getFullYear()
}
function monthKeysForFy(fyYear) {
  // Jul (fyYear-1) -> Jun (fyYear)
  const out = []
  for (let i = 0; i < 12; i++) {
    const m = ((6 + i) % 12) + 1 // 7,8,...,12,1,...,6
    const y = m >= 7 ? fyYear - 1 : fyYear
    out.push(`${y}-${String(m).padStart(2, '0')}`)
  }
  return out
}
function quarterKeysForFy(fyYear) {
  // Q1 (Jul-Sep) uses the CALENDAR year it falls in — same as period_bounds.
  const q1y = fyYear - 1
  return [`${q1y}-Q3`, `${q1y}-Q4`, `${fyYear}-Q1`, `${fyYear}-Q2`]
}
function monthLabel(key) {
  const [y, m] = key.split('-').map(Number)
  return new Date(y, m - 1, 1).toLocaleDateString('en-AU', { month: 'short', year: '2-digit' })
}

// A naive linear run-rate projection, mirroring services/crm_targets.py's
// own project_completion — "at the average daily rate achieved so far this
// period, when would we hit the target". Not a sophisticated forecast model.
function projectCompletion(targetValue, actualValue, periodStartIso, periodEndIso) {
  if (!targetValue || !actualValue || actualValue <= 0) return null
  const start = new Date(periodStartIso), end = new Date(periodEndIso), now = new Date()
  const elapsedDays = (Math.min(now, end) - start) / 86400000
  if (elapsedDays <= 0) return null
  const dailyRate = actualValue / elapsedDays
  if (dailyRate <= 0) return null
  const daysNeeded = targetValue / dailyRate
  return new Date(start.getTime() + daysNeeded * 86400000)
}

const PERIOD_TABS = [
  { key: 'month', label: 'Month' },
  { key: 'quarter', label: 'Quarter' },
  { key: 'fiscal_year', label: 'Financial Year' },
]

function ProgressBar({ actual, target, format }) {
  const pct = target ? Math.min(100, Math.round(100 * actual / target)) : null
  return (
    <div>
      <div className="flex items-center justify-between text-[11px] text-pb-faint mb-1">
        <span>{format(actual)}</span>
        {target != null && <span>of {format(target)} target</span>}
      </div>
      {target != null && (
        <div className="h-1.5 rounded-full bg-pb-surface2 overflow-hidden">
          <div className="h-full rounded-full" style={{
            width: `${pct}%`,
            background: pct >= 100 ? 'var(--pb-accent, #16c784)' : 'var(--pb-amber, #f5a623)',
          }} />
        </div>
      )}
    </div>
  )
}

function TargetFormModal({ open, onClose, periodType, periodKey, existing, onSaved }) {
  const toast = useToast()
  const [clubsWon, setClubsWon] = useState('')
  const [arr, setArr] = useState('')
  const [revenue, setRevenue] = useState('')
  const [trials, setTrials] = useState('')
  const [conversion, setConversion] = useState('')
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    setClubsWon(existing?.target_clubs_won ?? '')
    setArr(existing?.target_arr_cents != null ? centsToMoneyInput(existing.target_arr_cents) : '')
    setRevenue(existing?.target_revenue_cents != null ? centsToMoneyInput(existing.target_revenue_cents) : '')
    setTrials(existing?.target_trials ?? '')
    setConversion(existing?.target_conversion_rate ?? '')
    setNotes(existing?.notes || '')
  }, [open, existing])

  if (!open) return null

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      await api.superCrmUpsertTarget({
        period_type: periodType, period_key: periodKey,
        target_clubs_won: clubsWon === '' ? null : Number(clubsWon),
        target_arr_cents: arr === '' ? null : moneyToCents(arr),
        target_revenue_cents: revenue === '' ? null : moneyToCents(revenue),
        target_trials: trials === '' ? null : Number(trials),
        target_conversion_rate: conversion === '' ? null : Number(conversion),
        notes: notes || null,
      })
      onSaved()
      onClose()
    } catch (e2) { toast.error(e2.message || 'Could not save target') } finally { setSaving(false) }
  }

  return (
    <Modal open={open} onClose={onClose} title={`Target — ${periodKey}`}>
      <form onSubmit={submit} className="space-y-3">
        <Field label="Clubs won"><NumberInput min={0} value={clubsWon} onChange={e => setClubsWon(e.target.value)} /></Field>
        <Field label="New ARR ($)"><NumberInput min={0} value={arr} onChange={e => setArr(e.target.value)} /></Field>
        <Field label="Revenue ($)"><NumberInput min={0} value={revenue} onChange={e => setRevenue(e.target.value)} /></Field>
        <Field label="Trials started"><NumberInput min={0} value={trials} onChange={e => setTrials(e.target.value)} /></Field>
        <Field label="Trial conversion rate (%)"><NumberInput min={0} max={100} value={conversion} onChange={e => setConversion(e.target.value)} /></Field>
        <Field label="Notes"><TextInput value={notes} onChange={e => setNotes(e.target.value)} /></Field>
        <div className="flex justify-end pt-2"><Btn type="submit" variant="primary" disabled={saving}>Save target</Btn></div>
      </form>
    </Modal>
  )
}

export default function SuperCrmTargets() {
  const toast = useToast()
  const [periodType, setPeriodType] = useState('month')
  const now = new Date()
  const [periodKey, setPeriodKey] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`)
  const [fyYear, setFyYear] = useState(currentFyYear(now))
  const [targets, setTargets] = useState([])
  const [actuals, setActuals] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [yearSeries, setYearSeries] = useState(null)

  const loadTargets = useCallback(() => {
    api.superCrmListTargets().then(r => setTargets(r.targets || [])).catch(() => {})
  }, [])
  useEffect(() => { loadTargets() }, [loadTargets])

  const loadActuals = useCallback(() => {
    setLoading(true)
    api.superCrmTargetActuals(periodType, periodKey)
      .then(setActuals)
      .catch(e => toast.error(e.message || 'Could not load actuals'))
      .finally(() => setLoading(false))
  }, [periodType, periodKey, toast])
  useEffect(() => { loadActuals() }, [loadActuals])

  // Whole-financial-year monthly target-vs-actual series, for the line chart —
  // 12 parallel requests (admin-only, low-traffic page) rather than a new
  // dedicated backend endpoint.
  useEffect(() => {
    let alive = true
    const keys = monthKeysForFy(fyYear)
    Promise.all(keys.map(k => api.superCrmTargetActuals('month', k).catch(() => null)))
      .then(rows => {
        if (!alive) return
        const byKey = {}
        for (const t of targets) if (t.period_type === 'month') byKey[t.period_key] = t
        setYearSeries(keys.map((k, i) => ({
          key: k, label: monthLabel(k),
          actual: rows[i] ? Math.round((rows[i].new_arr_cents || 0) / 100) : 0,
          target: byKey[k]?.target_arr_cents != null ? Math.round(byKey[k].target_arr_cents / 100) : null,
        })))
      })
    return () => { alive = false }
  }, [fyYear, targets])

  const currentTarget = useMemo(
    () => targets.find(t => t.period_type === periodType && t.period_key === periodKey),
    [targets, periodType, periodKey])

  const deleteTarget = async (id) => {
    if (!window.confirm('Delete this target?')) return
    try { await api.superCrmDeleteTarget(id); loadTargets() }
    catch (e) { toast.error(e.message || 'Could not delete target') }
  }

  const arrProjection = actuals && currentTarget?.target_arr_cents
    ? projectCompletion(currentTarget.target_arr_cents, actuals.new_arr_cents, actuals.period_start, actuals.period_end)
    : null

  const periodOptions = periodType === 'month' ? monthKeysForFy(fyYear)
    : periodType === 'quarter' ? quarterKeysForFy(fyYear)
    : [`FY${fyYear - 1}`, `FY${fyYear}`, `FY${fyYear + 1}`]

  return (
    <AdminLayout>
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div>
          <Link to="/admin/super/crm" className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text">
            &larr; SALES PIPELINE
          </Link>
          <h1 className="font-display font-bold text-xl">BetterCRM — Sales Targets</h1>
        </div>
        <div className="flex items-center gap-2">
          <NumberInput value={fyYear} onChange={e => setFyYear(Number(e.target.value) || fyYear)} className="w-24" />
          <span className="text-[11px] text-pb-faint">FY (Jul-Jun)</span>
        </div>
      </div>

      <div className="flex items-center gap-2 mb-4">
        {PERIOD_TABS.map(p => (
          <button key={p.key} onClick={() => { setPeriodType(p.key); setPeriodKey(periodOptionsFor(p.key, fyYear)[0]) }}
            className={`px-2.5 py-1 rounded-full text-[11.5px] border transition ${
              periodType === p.key ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent' : 'border-pb-hairline2 text-pb-faint hover:text-pb-text'}`}>
            {p.label}
          </button>
        ))}
        <Select value={periodKey} onChange={e => setPeriodKey(e.target.value)} className="w-40">
          {periodOptions.map(k => <option key={k} value={k}>{k}</option>)}
        </Select>
        <Btn variant="ghost" sm onClick={() => setShowForm(true)}>
          {currentTarget ? 'Edit target' : '+ Set target'}
        </Btn>
      </div>

      {loading || !actuals ? <PbSpinner message="Loading targets…" /> : (
        <div className="space-y-5">
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
            <div className="pb-card px-3 py-2.5">
              <div className="font-mono text-[10px] tracking-wide text-pb-faint uppercase mb-1">Clubs won</div>
              <ProgressBar actual={actuals.clubs_won} target={currentTarget?.target_clubs_won} format={v => v} />
            </div>
            <div className="pb-card px-3 py-2.5">
              <div className="font-mono text-[10px] tracking-wide text-pb-faint uppercase mb-1">New ARR</div>
              <ProgressBar actual={actuals.new_arr_cents} target={currentTarget?.target_arr_cents} format={money} />
            </div>
            <div className="pb-card px-3 py-2.5">
              <div className="font-mono text-[10px] tracking-wide text-pb-faint uppercase mb-1">Cumulative ARR</div>
              <div className="font-display font-bold text-[15px]">{money(actuals.cumulative_arr_cents)}</div>
              <div className="text-[10.5px] text-pb-faintest">MRR {money(actuals.mrr_cents)}</div>
            </div>
            <div className="pb-card px-3 py-2.5">
              <div className="font-mono text-[10px] tracking-wide text-pb-faint uppercase mb-1">Current pipeline</div>
              <div className="font-display font-bold text-[15px]">{money(actuals.pipeline_value_cents)}</div>
              <div className="text-[10.5px] text-pb-faintest">Snapshot as of now, not historical</div>
            </div>
            <div className="pb-card px-3 py-2.5">
              <div className="font-mono text-[10px] tracking-wide text-pb-faint uppercase mb-1">Trials started</div>
              <ProgressBar actual={actuals.trials_started} target={currentTarget?.target_trials} format={v => v} />
              <div className="text-[10.5px] text-pb-faintest mt-1">Approximate — see note below</div>
            </div>
            <div className="pb-card px-3 py-2.5">
              <div className="font-mono text-[10px] tracking-wide text-pb-faint uppercase mb-1">Trial conversions</div>
              <div className="font-display font-bold text-[15px]">{actuals.trial_conversions}</div>
              {actuals.conversion_rate != null && (
                <ProgressBar actual={actuals.conversion_rate} target={currentTarget?.target_conversion_rate} format={v => `${v}%`} />
              )}
            </div>
          </div>

          {arrProjection && (
            <p className="text-[12px] text-pb-faint pb-card px-3 py-2 border-pb-accent/30">
              At the current run rate, the New ARR target for {periodKey} would be reached around{' '}
              <span className="text-pb-text font-medium">{arrProjection.toLocaleString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}</span>
              {' '}— a simple linear projection, not a sophisticated forecast.
            </p>
          )}

          <div className="pb-card px-4 py-3">
            <h3 className="font-display font-bold text-[13px] mb-2">Monthly target vs actual — New ARR (FY{fyYear})</h3>
            {yearSeries ? (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={yearSeries} margin={{ top: 4, right: 8, left: -10, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--pb-hairline, #1a2540)" />
                  <XAxis dataKey="label" tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: 'var(--pb-faint, #64748b)', fontSize: 10 }} axisLine={false} tickLine={false}
                    tickFormatter={v => `$${(v / 1000).toFixed(0)}k`} />
                  <Tooltip formatter={(v) => `$${Number(v).toLocaleString()}`}
                    contentStyle={{ background: 'var(--pb-surface, #0b1220)', border: '1px solid var(--pb-hairline, #1a2540)' }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Line type="monotone" dataKey="actual" name="Actual" stroke="var(--pb-accent, #16c784)" strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="target" name="Target" stroke="var(--pb-amber, #f5a623)" strokeWidth={2} strokeDasharray="5 4" dot={{ r: 3 }} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            ) : <PbSpinner message="Loading…" />}
          </div>

          <div className="pb-card overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="text-left text-pb-faint border-b border-pb-hairline">
                  <th className="px-3 py-2 font-normal">Period</th>
                  <th className="px-3 py-2 font-normal">Type</th>
                  <th className="px-3 py-2 font-normal text-right">Clubs won</th>
                  <th className="px-3 py-2 font-normal text-right">ARR target</th>
                  <th className="px-3 py-2 font-normal text-right">Trials</th>
                  <th className="px-3 py-2 font-normal text-right">Conversion %</th>
                  <th className="px-3 py-2 font-normal" />
                </tr>
              </thead>
              <tbody>
                {targets.length === 0 && (
                  <tr><td colSpan={7} className="px-3 py-6 text-center text-pb-faintest">No targets set yet.</td></tr>
                )}
                {targets.map(t => (
                  <tr key={t.id} className="border-b border-pb-hairline last:border-0">
                    <td className="px-3 py-2">{t.period_key}</td>
                    <td className="px-3 py-2 text-pb-faint">{t.period_type}</td>
                    <td className="px-3 py-2 text-right">{t.target_clubs_won ?? '—'}</td>
                    <td className="px-3 py-2 text-right">{t.target_arr_cents != null ? money(t.target_arr_cents) : '—'}</td>
                    <td className="px-3 py-2 text-right">{t.target_trials ?? '—'}</td>
                    <td className="px-3 py-2 text-right">{t.target_conversion_rate != null ? `${t.target_conversion_rate}%` : '—'}</td>
                    <td className="px-3 py-2 text-right">
                      <button onClick={() => deleteTarget(t.id)} className="text-pb-faint hover:text-pb-red text-[11px]">Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <TargetFormModal open={showForm} onClose={() => setShowForm(false)}
        periodType={periodType} periodKey={periodKey} existing={currentTarget}
        onSaved={() => { loadTargets(); loadActuals() }} />
    </AdminLayout>
  )
}

function periodOptionsFor(periodType, fyYear) {
  if (periodType === 'month') return monthKeysForFy(fyYear)
  if (periodType === 'quarter') return quarterKeysForFy(fyYear)
  return [`FY${fyYear - 1}`, `FY${fyYear}`, `FY${fyYear + 1}`]
}
