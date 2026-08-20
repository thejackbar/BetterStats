import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import AdminLayout from '../../components/admin/AdminLayout'
import { PbSpinner } from '../../lib/presskit'
import { Btn, NumberInput, TextInput, Kpi } from '../../components/admin/crm/ui'

// Every number that decides a club's engagement score, and whether it appears
// on the sales pipeline at all. The catalogue (labels, help, defaults, ranges,
// grouping) is served by the backend rather than mirrored here — there are ~53
// entries carrying real explanatory copy, and a hand-kept mirror would drift.
// See backend services/engagement_params.py.
//
// Laid out floor-first on purpose: membership and the tier bands are what most
// visits are actually about, and the bulk of the weights are the least of the
// leverage. The stage-promotion rules are NOT restated here; they are already
// editable on Sales Automation, and two places to edit one thing is how the two
// start disagreeing.

const pct = (n, total) => (total ? Math.round((n / total) * 100) : 0)

function percentile(sorted, p) {
  if (!sorted.length) return 0
  const k = (sorted.length - 1) * (p / 100)
  const lo = Math.floor(k)
  const hi = Math.min(lo + 1, sorted.length - 1)
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (k - lo)
}

/** A 20-bin histogram of a score list, drawn as bars. The raw scores come over
 *  the wire so this is a client-side calculation rather than a second round
 *  trip for every way of slicing it. */
function Histogram({ scores, compare, label }) {
  const bins = useMemo(() => {
    const make = (list) => {
      const out = new Array(20).fill(0)
      for (const v of list || []) out[Math.min(19, Math.floor(v / 5))] += 1
      return out
    }
    return { now: make(scores), was: compare ? make(compare) : null }
  }, [scores, compare])
  const peak = Math.max(1, ...bins.now, ...(bins.was || [0]))
  return (
    <div>
      <div className="text-[11px] font-mono uppercase tracking-wide opacity-60 mb-2">{label}</div>
      {/* items-STRETCH plus h-full on each column, not items-end: a bar sized as
          a percentage resolves against its parent's height, and an items-end
          parent shrinks to its content, so every bar computes to zero. */}
      <div className="flex items-stretch gap-[2px] h-24">
        {bins.now.map((c, i) => (
          <div key={i} className="flex-1 h-full flex flex-col justify-end items-stretch relative"
               title={`${i * 5}-${i * 5 + 5}: ${c} club${c === 1 ? '' : 's'}`}>
            {bins.was && (
              <div className="absolute inset-x-0 bottom-0 border-t border-dashed opacity-50"
                   style={{ height: `${(bins.was[i] / peak) * 100}%`, borderColor: 'var(--pb-dim)' }} />
            )}
            <div style={{ height: `${(c / peak) * 100}%`, background: 'var(--pb-accent)', minHeight: c ? 2 : 0 }} />
          </div>
        ))}
      </div>
      <div className="flex justify-between text-[10px] font-mono opacity-50 mt-1">
        <span>0</span><span>25</span><span>50</span><span>75</span><span>100</span>
      </div>
    </div>
  )
}

function Stat({ label, before, after, suffix = '' }) {
  const moved = before !== undefined && before !== after
  return (
    <div className="pb-card p-3">
      <div className="text-[11px] font-mono uppercase tracking-wide opacity-60">{label}</div>
      <div className="text-lg font-semibold mt-1">
        {after}{suffix}
        {moved && (
          <span className="text-xs font-normal opacity-60 ml-2">
            was {before}{suffix}
          </span>
        )}
      </div>
    </div>
  )
}

function PreviewPanel({ preview, onClose }) {
  if (!preview) return null
  const { before, after } = preview
  const sortedAfter = [...(after.scores || [])].sort((a, b) => a - b)
  const sortedBefore = [...(before.scores || [])].sort((a, b) => a - b)
  const tiers = ['HOT', 'WARM', 'COLD', 'NOT_INTERESTED']
  return (
    <div className="pb-card p-4 mb-6" style={{ borderColor: 'var(--pb-accent)' }}>
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="font-semibold">If you save this</div>
          <div className="text-xs opacity-70">
            Scored every club under the proposed values without saving anything.
            Dashed outlines are where the distribution sits today.
          </div>
        </div>
        <Btn sm onClick={onClose}>Dismiss</Btn>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <Stat label={`Cards on the board (score ≥ ${after.add_min})`}
              before={before.on_board} after={after.on_board} />
        <Stat label={`Would raise an Opportunity (≥ ${after.opportunity_min})`}
              before={before.at_opportunity} after={after.at_opportunity} />
        <Stat label="Median score"
              before={Math.round(percentile(sortedBefore, 50))}
              after={Math.round(percentile(sortedAfter, 50))} />
        <Stat label="At the 100 ceiling"
              before={sortedBefore.filter(v => v >= 100).length}
              after={sortedAfter.filter(v => v >= 100).length} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-4">
        <Histogram scores={after.scores} compare={before.scores} label="All clubs" />
        <Histogram scores={after.scores_prospect} compare={before.scores_prospect}
                   label="Prospects only (the true lead-heat view)" />
      </div>

      <div className="flex flex-wrap gap-4 text-xs">
        {tiers.filter(t => (after.tiers?.[t] || before.tiers?.[t])).map(t => {
          const now = after.tiers?.[t] || 0
          const was = before.tiers?.[t] || 0
          return (
            <div key={t}>
              <span className="font-mono uppercase opacity-60">{t.replace('_', ' ')}</span>{' '}
              <span className="font-semibold">{now}</span>
              <span className="opacity-60"> ({pct(now, after.processed)}%)</span>
              {now !== was && <span className="opacity-60"> · was {was}</span>}
            </div>
          )
        })}
      </div>

      {after.on_board !== before.on_board && (
        <div className="mt-3 text-xs pb-card p-2" style={{ background: 'var(--pb-surface)' }}>
          {after.on_board > before.on_board
            ? `${after.on_board - before.on_board} club(s) would be ADDED to the pipeline as new Target cards.`
            : `${before.on_board - after.on_board} auto-added Target card(s) would be archived off the board. `
              + 'Hand-added cards, hand-moved cards and anything past Target are never touched, and lowering the '
              + 'threshold again brings the clubs back (as new cards).'}
        </div>
      )}
    </div>
  )
}

function ParamRow({ spec, value, isChanged, onChange }) {
  const isBool = spec.kind === 'bool'
  const defLabel = isBool ? (spec.default ? 'on' : 'off') : String(spec.default)
  return (
    <div className="py-3 border-b last:border-b-0" style={{ borderColor: 'var(--pb-border)' }}>
      <div className="flex items-start gap-4">
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium flex items-center gap-2 flex-wrap">
            <span>{spec.label}</span>
            {isChanged && (
              <span className="text-[10px] font-mono uppercase px-1.5 py-0.5 rounded"
                    style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}>
                changed
              </span>
            )}
          </div>
          {spec.help && <div className="text-xs opacity-70 mt-1">{spec.help}</div>}
        </div>
        <div className="shrink-0 flex items-center gap-2">
          {isBool ? (
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={!!value}
                     onChange={(e) => onChange(spec.key, e.target.checked)} />
              <span>{value ? 'On' : 'Off'}</span>
            </label>
          ) : (
            <NumberInput
              value={value ?? ''}
              step={spec.kind === 'multiplier' || spec.kind === 'points' ? '0.1' : '1'}
              min={spec.min} max={spec.max}
              onChange={(e) => onChange(spec.key,
                e.target.value === '' ? '' : Number(e.target.value))}
              style={{ width: 92 }}
            />
          )}
          <button type="button"
                  className="text-[11px] font-mono opacity-60 hover:opacity-100 disabled:opacity-25"
                  disabled={!isChanged}
                  title={`Back to the built-in default (${defLabel})`}
                  onClick={() => onChange(spec.key, null)}>
            reset
          </button>
        </div>
      </div>
    </div>
  )
}

function Group({ group, values, changedKeys, onChange, openByDefault }) {
  const [open, setOpen] = useState(!!openByDefault)
  const changedHere = group.params.filter(p => changedKeys.has(p.key)).length
  return (
    <div className="pb-card mb-3">
      <button type="button" onClick={() => setOpen(o => !o)}
              className="w-full text-left p-4 flex items-start justify-between gap-4">
        <div>
          <div className="font-semibold flex items-center gap-2">
            {group.label}
            {changedHere > 0 && (
              <span className="text-[10px] font-mono uppercase opacity-70">
                {changedHere} changed
              </span>
            )}
          </div>
          <div className="text-xs opacity-70 mt-0.5">{group.blurb}</div>
        </div>
        <span className="font-mono text-xs opacity-60 shrink-0">
          {open ? '−' : `+ ${group.params.length}`}
        </span>
      </button>
      {open && (
        <div className="px-4 pb-2">
          {group.params.map(spec => (
            <ParamRow key={spec.key} spec={spec} value={values[spec.key]}
                      isChanged={changedKeys.has(spec.key)} onChange={onChange} />
          ))}
        </div>
      )}
    </div>
  )
}

export default function SuperEngagementParams() {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [values, setValues] = useState({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [previewing, setPreviewing] = useState(false)
  const [preview, setPreview] = useState(null)
  const [note, setNote] = useState('')
  const [recalcRunning, setRecalcRunning] = useState(false)
  const pollRef = useRef(null)

  const load = useCallback(async () => {
    try {
      const d = await api.superEngagementParams()
      setData(d)
      setValues(d.values || {})
      setRecalcRunning(d.recalc?.status === 'running')
    } catch (e) {
      toast.error(e.message || 'Could not load the engagement parameters')
    } finally { setLoading(false) }
  }, [toast])

  useEffect(() => { load() }, [load])
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  // A save kicks the same full recompute the pipeline's Recalculate button
  // runs. It takes minutes, so it is polled rather than awaited.
  const pollRecalc = useCallback(() => {
    if (pollRef.current) return
    setRecalcRunning(true)
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.superCrmRecalcEngagementStatus()
        if (s.status === 'running') return
        clearInterval(pollRef.current); pollRef.current = null
        setRecalcRunning(false)
        if (s.error) toast.error(`Recalculation failed: ${s.error}`)
        else if (s.result) toast.success(
          `Rescored ${s.result.processed} club${s.result.processed === 1 ? '' : 's'} `
          + `under the new parameters.`)
        load()
      } catch { /* transient, keep polling */ }
    }, 4000)
  }, [toast, load])

  // Only the keys that differ from what the server currently has.
  const pending = useMemo(() => {
    if (!data) return {}
    const out = {}
    for (const [k, v] of Object.entries(values)) {
      if (v === '') continue
      if (v !== data.values[k]) out[k] = v
    }
    // A key reset back to its default needs sending explicitly as null so the
    // server drops the stored override rather than leaving it in place.
    for (const k of data.changed || []) {
      if (values[k] === data.defaults[k]) out[k] = null
    }
    return out
  }, [values, data])

  const dirty = Object.keys(pending).length > 0

  const onChange = (key, value) => {
    setValues(v => ({ ...v, [key]: value === null ? data.defaults[key] : value }))
    setPreview(null)
  }

  const runPreview = async () => {
    setPreviewing(true)
    try {
      setPreview(await api.superEngagementParamsPreview({ values: pending }))
    } catch (e) {
      toast.error(e.message || 'Could not build the preview')
    } finally { setPreviewing(false) }
  }

  const save = async (recalculate) => {
    setSaving(true)
    try {
      const r = await api.superEngagementParamsSave({
        values: pending, note: note.trim() || null, recalculate,
      })
      setNote('')
      setPreview(null)
      toast.success(recalculate
        ? 'Saved. Rescoring every club now.'
        : 'Saved. Scores update within the hour, or press Recalculate on the pipeline.')
      if (r.recalculating) pollRecalc()
      else load()
    } catch (e) {
      toast.error(e.message || 'Could not save')
    } finally { setSaving(false) }
  }

  const resetAll = () => {
    if (!window.confirm('Put every parameter back to its built-in default?')) return
    const next = { ...values }
    for (const k of data.changed || []) next[k] = data.defaults[k]
    setValues(next)
    setPreview(null)
  }

  if (loading) return <AdminLayout><PbSpinner message="Loading parameters…" /></AdminLayout>
  if (!data) return <AdminLayout><div className="p-6">Could not load the parameters.</div></AdminLayout>

  const changedKeys = new Set(data.changed || [])

  return (
    <AdminLayout>
      <div className="max-w-4xl mx-auto p-4 md:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3 mb-1">
          <h1 className="text-xl font-semibold">Engagement Score Parameters</h1>
          <Link to="/admin/super/crm" className="text-xs font-mono opacity-70 hover:opacity-100">
            ← Sales Pipeline
          </Link>
        </div>
        <p className="text-sm opacity-70 mb-5">
          What the CRM treats as a warm club, and which clubs reach the board at all.
          Stage-promotion rules live on{' '}
          <Link to="/admin/super/crm/automation" className="underline">Sales Automation</Link>,
          and the direct-enquiry window on General Settings.
        </p>

        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-5">
          <Kpi label="Deals on the board" value={data.deals_on_board} />
          <Kpi label="Parameters changed" value={changedKeys.size} accent={changedKeys.size > 0} />
          <Kpi label="Rescoring" value={recalcRunning ? 'Running…' : 'Idle'} />
        </div>

        <div className="pb-card p-3 mb-5 text-xs opacity-80">
          <div className="font-semibold mb-1 opacity-100">Worth knowing before you tune</div>
          <ul className="list-disc pl-4 space-y-1">
            <li>A score is capped at 100. Raising every weight piles clubs at the ceiling
                rather than spreading them out.</li>
            <li>A recent direct enquiry, and a self-serve club's setup depth, both
                override the ordinary calculation. Tuning the weights below does nothing
                for those clubs.</li>
            <li>A paying club scores on the Customer group alone. None of the prospect
                settings apply to it.</li>
            <li>Raising the membership floor archives auto-added Target cards. It never
                touches a hand-added card, a hand-moved one, or anything past Target.</li>
          </ul>
        </div>

        <PreviewPanel preview={preview} onClose={() => setPreview(null)} />

        {data.catalogue.map((g, i) => (
          <Group key={g.key} group={g} values={values} changedKeys={changedKeys}
                 onChange={onChange} openByDefault={i < 2} />
        ))}

        <div className="pb-card p-4 mt-5 sticky bottom-4"
             style={{ background: 'var(--pb-surface)' }}>
          <div className="flex flex-wrap items-center gap-3">
            <TextInput placeholder="What are you changing, and why? (optional)"
                       value={note} onChange={(e) => setNote(e.target.value)}
                       style={{ flex: '1 1 240px' }} />
            <Btn onClick={runPreview} disabled={!dirty || previewing}>
              {previewing ? 'Scoring every club…' : 'Preview'}
            </Btn>
            <Btn onClick={() => save(false)} disabled={!dirty || saving}>Save only</Btn>
            <Btn variant="primary" onClick={() => save(true)} disabled={!dirty || saving}>
              {saving ? 'Saving…' : 'Save and rescore'}
            </Btn>
          </div>
          <div className="text-xs opacity-70 mt-2">
            {dirty
              ? `${Object.keys(pending).length} change(s) not yet saved. Preview scores every `
                + 'club under them without saving anything.'
              : 'No unsaved changes.'}
            {changedKeys.size > 0 && (
              <> · <button type="button" className="underline" onClick={resetAll}>
                Reset all {changedKeys.size} to defaults
              </button></>
            )}
          </div>
        </div>

        {(data.revisions || []).length > 0 && (
          <div className="mt-6">
            <div className="text-[11px] font-mono uppercase tracking-wide opacity-60 mb-2">
              Change history
            </div>
            <div className="pb-card divide-y" style={{ borderColor: 'var(--pb-border)' }}>
              {data.revisions.map(r => (
                <div key={r.id} className="p-3 text-xs flex flex-wrap gap-x-3 gap-y-1">
                  <span className="font-mono opacity-60">
                    {new Date(r.created_at).toLocaleString()}
                  </span>
                  <span className="opacity-80">{r.changed_by || 'Unknown'}</span>
                  <span className="opacity-60">
                    {Object.keys(r.overrides_json || {}).length} parameter(s) off default
                  </span>
                  {r.note && <span className="opacity-80 italic">“{r.note}”</span>}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
