import { useState, useEffect, useCallback } from 'react'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import AdminLayout from '../../components/admin/AdminLayout'
import { PbSpinner } from '../../lib/presskit'

const PAYMENT_TYPES = [
  { value: 'standard', label: 'Standard' },
  { value: 'upfront', label: 'Upfront' },
  { value: 'complimentary', label: 'Complimentary' },
  { value: 'left_club', label: 'Left Club' },
]

const FORMAT_OPTIONS = [
  { value: '', label: 'Auto (from match format)' },
  { value: 'two_day', label: 'Two Day (2 days)' },
  { value: 'one_day', label: 'One Day' },
  { value: 't20', label: 'T20' },
  { value: 'women', label: "Women's" },
  { value: 'exclude', label: 'Exclude from fees' },
]

function sortSeasons(seasons) {
  return seasons.filter(s => !s.alias_of).sort((a, b) => (b.year || 0) - (a.year || 0) || (b.name > a.name ? 1 : -1))
}

// ── Rate card ────────────────────────────────────────────────────────────────
function ScheduleRow({ row, onSaved, onDeleted }) {
  const toast = useToast()
  const [draft, setDraft] = useState(row)
  const [busy, setBusy] = useState(false)
  useEffect(() => setDraft(row), [row.id])

  const dirty = draft.name !== row.name || draft.payment_type !== row.payment_type ||
    Number(draft.membership_amount) !== Number(row.membership_amount) ||
    Number(draft.match_day_rate) !== Number(row.match_day_rate)

  async function save() {
    setBusy(true)
    try {
      await api.feeUpdateSchedule(row.id, {
        name: draft.name,
        payment_type: draft.payment_type,
        membership_amount: Number(draft.membership_amount) || 0,
        match_day_rate: Number(draft.match_day_rate) || 0,
      })
      toast.success('Tier saved')
      onSaved()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  async function del() {
    if (!confirm(`Delete tier "${row.name}"? Members on it become "needs tier".`)) return
    setBusy(true)
    try { await api.feeDeleteSchedule(row.id); toast.success('Tier deleted'); onDeleted() }
    catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  const cell = 'bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
  return (
    <tr className="pb-hairline-t align-middle hover:bg-pb-surface2/40">
      <td className="py-2 pl-5 pr-2">
        <input className={`${cell} w-full`} value={draft.name}
          onChange={e => setDraft(d => ({ ...d, name: e.target.value }))} />
      </td>
      <td className="py-2 px-2">
        <select className={`${cell} w-full`} value={draft.payment_type}
          onChange={e => setDraft(d => ({ ...d, payment_type: e.target.value }))}>
          {PAYMENT_TYPES.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
      </td>
      <td className="py-2 px-2 text-right">
        <input type="number" min="0" step="1" className={`${cell} w-24 text-right`} value={draft.membership_amount}
          onChange={e => setDraft(d => ({ ...d, membership_amount: e.target.value }))} />
      </td>
      <td className="py-2 px-2 text-right">
        <input type="number" min="0" step="1" className={`${cell} w-20 text-right`} value={draft.match_day_rate}
          onChange={e => setDraft(d => ({ ...d, match_day_rate: e.target.value }))} />
      </td>
      <td className="py-2 pr-5 pl-2 text-right whitespace-nowrap">
        <button onClick={save} disabled={!dirty || busy}
          className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-30"
          style={{ background: 'var(--pb-accent)' }}>SAVE</button>
        <button onClick={del} disabled={busy}
          className="ml-2 font-mono text-[10px] border pb-hairline rounded px-3 py-1.5 text-pb-red/60 hover:text-pb-red transition-colors disabled:opacity-50">DEL</button>
      </td>
    </tr>
  )
}

function AddTierRow({ seasonId, onAdded }) {
  const toast = useToast()
  const blank = { name: '', payment_type: 'standard', membership_amount: '', match_day_rate: '' }
  const [draft, setDraft] = useState(blank)
  const [busy, setBusy] = useState(false)
  const cell = 'bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
  async function add() {
    if (!draft.name.trim()) { toast.error('Name is required'); return }
    setBusy(true)
    try {
      await api.feeCreateSchedule({
        season_id: seasonId, name: draft.name.trim(), payment_type: draft.payment_type,
        membership_amount: Number(draft.membership_amount) || 0, match_day_rate: Number(draft.match_day_rate) || 0,
      })
      setDraft(blank); toast.success('Tier added'); onAdded()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  return (
    <tr className="pb-hairline-t bg-pb-surface2/20 align-middle">
      <td className="py-2 pl-5 pr-2">
        <input className={`${cell} w-full`} placeholder="New tier name…" value={draft.name}
          onChange={e => setDraft(d => ({ ...d, name: e.target.value }))}
          onKeyDown={e => e.key === 'Enter' && add()} />
      </td>
      <td className="py-2 px-2">
        <select className={`${cell} w-full`} value={draft.payment_type}
          onChange={e => setDraft(d => ({ ...d, payment_type: e.target.value }))}>
          {PAYMENT_TYPES.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
      </td>
      <td className="py-2 px-2 text-right">
        <input type="number" min="0" className={`${cell} w-24 text-right`} placeholder="0" value={draft.membership_amount}
          onChange={e => setDraft(d => ({ ...d, membership_amount: e.target.value }))} />
      </td>
      <td className="py-2 px-2 text-right">
        <input type="number" min="0" className={`${cell} w-20 text-right`} placeholder="0" value={draft.match_day_rate}
          onChange={e => setDraft(d => ({ ...d, match_day_rate: e.target.value }))} />
      </td>
      <td className="py-2 pr-5 pl-2 text-right">
        <button onClick={add} disabled={busy}
          className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold border pb-hairline text-pb-text hover:border-pb-accent disabled:opacity-50">ADD</button>
      </td>
    </tr>
  )
}

// ── Grade formats ────────────────────────────────────────────────────────────
function GradeFormatList({ seasonId }) {
  const toast = useToast()
  const [grades, setGrades] = useState(null)
  const load = useCallback(() => {
    api.feeListGrades(seasonId).then(setGrades).catch(() => setGrades([]))
  }, [seasonId])
  useEffect(() => { setGrades(null); load() }, [load])

  async function setFormat(g, value) {
    try {
      await api.feeSetGradeFormat(g.id, value || null)
      setGrades(gs => gs.map(x => x.id === g.id ? { ...x, fee_format: value || null } : x))
    } catch (e) { toast.error(e.message) }
  }

  if (grades === null) return <PbSpinner message="Loading grades…" />
  if (!grades.length) return <p className="font-mono text-[11px] text-pb-faint">No grades for this season.</p>

  return (
    <div className="pb-card overflow-hidden">
      <div className="grid grid-cols-[1fr_auto_220px] font-mono text-[10px] tracking-wide3 text-pb-faint px-5 py-2.5 bg-pb-surface2/40">
        <span>GRADE</span><span className="text-right pr-6">DETECTED</span><span>FEE FORMAT</span>
      </div>
      {grades.map((g, i) => (
        <div key={g.id} className={`grid grid-cols-[1fr_auto_220px] items-center px-5 py-2.5 ${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2/40`}>
          <span className="text-pb-text text-sm truncate pr-3">{g.name}</span>
          <span className="font-mono text-[10px] text-pb-faintest text-right pr-6 whitespace-nowrap">
            {g.formats.length ? g.formats.map(f => `${f.match_format}×${f.games}`).join(' · ') : `${g.games} games`}
          </span>
          <select
            value={g.fee_format || ''}
            onChange={e => setFormat(g, e.target.value)}
            className={`bg-pb-surface2 border rounded px-2.5 py-1.5 text-sm focus:outline-none ${g.fee_format ? 'text-pb-text border-pb-accent/50' : 'text-pb-dim pb-hairline'}`}
          >
            {FORMAT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
      ))}
    </div>
  )
}

export default function AdminFeeSchedule() {
  const toast = useToast()
  const [seasons, setSeasons] = useState([])
  const [seasonId, setSeasonId] = useState('')
  const [schedule, setSchedule] = useState(null)
  const [recomputing, setRecomputing] = useState(false)

  useEffect(() => {
    api.adminListSeasons()
      .then(s => { const sorted = sortSeasons(s); setSeasons(sorted); if (sorted[0]) setSeasonId(sorted[0].id) })
      .catch(e => toast.error(e.message))
  }, [])

  const load = useCallback(() => {
    if (!seasonId) return
    setSchedule(null)
    api.feeListSchedule(seasonId).then(setSchedule).catch(() => setSchedule([]))
  }, [seasonId])
  useEffect(() => { load() }, [load])

  async function seed() {
    try { const r = await api.feeSeedDefaults(seasonId); toast.success(`Seeded ${r.created} tiers`); load() }
    catch (e) { toast.error(e.message) }
  }
  async function copyFrom(fromId) {
    if (!fromId) return
    try { const r = await api.feeCopySchedule(seasonId, fromId); toast.success(`Copied ${r.created} tiers`); load() }
    catch (e) { toast.error(e.message) }
  }
  async function recompute() {
    setRecomputing(true)
    try {
      const r = await api.feeRecompute(seasonId)
      toast.success(`Match days rebuilt — ${r.entries_upserted} updated, ${r.members_created} new members`)
    } catch (e) { toast.error(e.message) } finally { setRecomputing(false) }
  }

  return (
    <AdminLayout>
      <div className="max-w-4xl">
        <h1 className="font-display font-bold text-2xl text-pb-text mb-1">Fee Schedule</h1>
        <p className="text-pb-faint text-sm mb-5 leading-relaxed">
          The membership rate card for a season. Each tier sets a one-off membership fee and a per-day match fee
          (set match fee to 0 for Upfront tiers who prepay). Match fee owed = days played × the tier's per-day rate.
        </p>

        <div className="flex flex-wrap items-center gap-3 mb-6">
          <select value={seasonId} onChange={e => setSeasonId(e.target.value)}
            className="bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-text text-sm focus:outline-none focus:border-pb-accent">
            {seasons.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <button onClick={recompute} disabled={recomputing || !seasonId}
            className="px-3 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text hover:border-pb-accent transition-colors disabled:opacity-50">
            {recomputing ? 'RECOMPUTING…' : 'RECOMPUTE MATCH DAYS'}
          </button>
        </div>

        {schedule === null ? (
          <PbSpinner message="Loading rate card…" />
        ) : (
          <>
            <div className="pb-card overflow-hidden mb-4">
              <table className="w-full">
                <thead>
                  <tr className="font-mono text-[10px] tracking-wide3 text-pb-faint text-left bg-pb-surface2/40">
                    <th className="font-medium py-2.5 pl-5">TIER</th>
                    <th className="font-medium py-2.5 px-2">PAYMENT TYPE</th>
                    <th className="font-medium py-2.5 px-2 text-right">MEMBERSHIP</th>
                    <th className="font-medium py-2.5 px-2 text-right">PER DAY</th>
                    <th className="py-2.5 pr-5"></th>
                  </tr>
                </thead>
                <tbody>
                  {schedule.map(r => (
                    <ScheduleRow key={r.id} row={r} onSaved={load} onDeleted={load} />
                  ))}
                  <AddTierRow seasonId={seasonId} onAdded={load} />
                </tbody>
              </table>
            </div>

            {schedule.length === 0 && (
              <div className="pb-card p-5 mb-8 flex flex-wrap items-center gap-3">
                <span className="text-pb-dim text-sm flex-1 min-w-[200px]">No tiers yet. Seed the default Applecross rate card, or copy from another season.</span>
                <button onClick={seed}
                  className="px-3 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg" style={{ background: 'var(--pb-accent)' }}>
                  SEED DEFAULTS
                </button>
                <select defaultValue="" onChange={e => copyFrom(e.target.value)}
                  className="bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-pb-dim text-sm focus:outline-none">
                  <option value="">Copy from season…</option>
                  {seasons.filter(s => s.id !== seasonId).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
            )}

            <div className="mt-10">
              <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2 uppercase">Grade Formats</p>
              <p className="text-pb-dim text-sm mb-4 leading-relaxed">
                How each grade counts towards match days. Leave on <span className="text-pb-text">Auto</span> to use PlayHQ's
                match format; tag women's (PSWL) grades as <span className="text-pb-text">Women's</span> since they arrive as plain
                One Day / T20, or set <span className="text-pb-text">Exclude</span> to drop a grade from fees. Recompute after changing these.
              </p>
              <GradeFormatList seasonId={seasonId} />
            </div>
          </>
        )}
      </div>
    </AdminLayout>
  )
}
