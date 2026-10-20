// BetterSelect → Fines → Add fines: the after-game session.
//
// The rows start as the players picked in the squad's side for that week (from the
// selection lineups), so nobody has to be hunted down. Tick players and apply a fine
// to them together, or to everyone ("Fine all"), or take each to the squad's
// maximum for the session ("Max all"). A player can have several lines.
//
// The squad's maximum is held on the server too; this screen shows each player's
// running total against it and will not send a session that goes over.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { Btn } from './ui'
import { Card, inputCls, money, shortDate, todayISO, useLatest } from './finesUi'

let rowSeq = 0
const blankRow = (over = {}) => ({
  key: ++rowSeq, player_id: '', name: '', fixed: false, fine_type_id: '', reason: '', amount: '',
  quantity: '1', note: '', showNote: false, isMax: false, ...over,
})
const hasContent = (r) => !!(r.fine_type_id || r.reason.trim() || r.amount !== '')

// What one line comes to: the typed amount, else the fine's price, times how many.
export function lineTotal(r, types) {
  const t = types.find((x) => x.id === r.fine_type_id)
  const amt = r.amount !== '' ? Number(r.amount) : (t ? t.amount : 0)
  return (Number.isFinite(amt) ? amt : 0) * (Number(r.quantity) || 1)
}

// What each player's lines come to, optionally leaving the Max lines out.
export function totalsByPlayer(rows, types, { skipMax = false } = {}) {
  const out = {}
  for (const r of rows) {
    if (!r.player_id || !hasContent(r) || (skipMax && r.isMax)) continue
    out[r.player_id] = (out[r.player_id] || 0) + lineTotal(r, types)
  }
  return out
}

// Give each player in `pids` a line made by `make(pid)`: into their empty line if
// they have one, else a new line straight under their last. Never overwrites a
// line somebody has filled in.
export function giveLines(rows, pids, make, { replaceMax = false } = {}) {
  let next = [...rows]
  for (const pid of pids) {
    const patch = make(pid, next)
    if (!patch) continue
    const idxs = next.map((r, i) => (r.player_id === pid ? i : -1)).filter((i) => i >= 0)
    const maxIdx = replaceMax ? idxs.find((i) => next[i].isMax) : undefined
    const emptyIdx = maxIdx ?? idxs.find((i) => !hasContent(next[i]))
    if (emptyIdx !== undefined) {
      next[emptyIdx] = { ...next[emptyIdx], ...patch }
    } else {
      const at = idxs.length ? idxs[idxs.length - 1] + 1 : next.length
      const name = idxs.length ? next[idxs[0]].name : ''
      next.splice(at, 0, blankRow({ player_id: pid, name, fixed: true, ...patch }))
    }
  }
  return next
}

function FineRow({ row, types, people, checked, onCheck, onChange, onRemove, onAnother, total, max, existing }) {
  const type = types.find((t) => t.id === row.fine_type_id)
  const sum = (existing || 0) + (total || 0)
  const over = max != null && sum > max + 0.001
  return (
    <div className="py-2 border-t border-pb-hairline first:border-t-0" data-fine-row data-player={row.player_id || ''}>
      <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] sm:grid-cols-[auto_minmax(0,1.1fr)_minmax(0,1.4fr)_88px_56px_auto] gap-2 items-center">
        {row.fixed
          ? <input type="checkbox" checked={checked} onChange={onCheck} aria-label={`Tick ${row.name}`} className="shrink-0" />
          : <span className="w-[13px]" />}
        <div className="min-w-0">
          {row.fixed
            ? <div className="text-[14px] font-semibold truncate">{row.name}</div>
            : (
              <select value={row.player_id} onChange={(e) => {
                const p = people.find((x) => x.id === e.target.value)
                onChange({ player_id: e.target.value, name: p?.name || '' })
              }} aria-label="Player" className={`${inputCls} w-full`}>
                <option value="">Pick a player…</option>
                {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            )}
          {row.player_id && max != null && (
            <div className="text-[11px] mt-0.5" data-cap-line style={{ color: over ? 'var(--pb-red)' : 'var(--pb-faint)' }}>
              {money(sum)} of {money(max)} max{existing ? ` (${money(existing)} already)` : ''}
            </div>
          )}
        </div>
        <div className="flex items-center gap-1 justify-self-end sm:order-last">
          {row.fixed && <button type="button" onClick={onAnother} title="Another fine for this player" aria-label={`Another fine for ${row.name}`} className="text-pb-faint hover:text-pb-text text-base leading-none px-1.5">+</button>}
          <button type="button" onClick={onRemove} aria-label="Remove this line" className="text-pb-faint hover:text-pb-red text-lg leading-none px-1">×</button>
        </div>
        <div className="col-span-3 sm:col-span-1 flex flex-col gap-1.5 min-w-0">
          <select value={row.fine_type_id} onChange={(e) => onChange({ fine_type_id: e.target.value, amount: '', isMax: false })} aria-label="Fine" className={inputCls}>
            <option value="">Something else…</option>
            {types.map((t) => <option key={t.id} value={t.id}>{t.name} ({money(t.amount)})</option>)}
          </select>
          {!row.fine_type_id && (
            <input value={row.reason} onChange={(e) => onChange({ reason: e.target.value, isMax: false })} maxLength={120}
              placeholder="What was it for?" aria-label="Reason" className={inputCls} />
          )}
        </div>
        <input value={row.amount} onChange={(e) => onChange({ amount: e.target.value.replace(/[^0-9.]/g, ''), isMax: false })} inputMode="decimal"
          placeholder={type ? String(type.amount) : '$'} aria-label="Amount" className={`${inputCls} w-full col-span-2 sm:col-span-1`} />
        <input value={row.quantity} onChange={(e) => onChange({ quantity: e.target.value.replace(/\D/g, '').slice(0, 2) })} inputMode="numeric"
          aria-label="How many" title="How many" className={`${inputCls} w-full text-center`} />
      </div>
      {(row.showNote || row.note) ? (
        <input value={row.note} onChange={(e) => onChange({ note: e.target.value })} maxLength={300} placeholder="Note for the report (optional)"
          aria-label="Note" className={`${inputCls} w-full mt-1.5`} />
      ) : (
        <button type="button" onClick={() => onChange({ showNote: true })} className="text-[11.5px] text-pb-faint underline mt-1">Add a note</button>
      )}
    </div>
  )
}

export default function AddFinesSession({ teamId, data, onSaved }) {
  const toast = useToast()
  const toastRef = useLatest(toast)
  const max = data.settings.max_per_session ?? null
  const types = data.types
  const [date, setDate] = useState('')
  const [side, setSide] = useState(null)
  const [rows, setRows] = useState(() => [blankRow()])
  const [checked, setChecked] = useState(() => new Set())
  const [bulk, setBulk] = useState({ fine_type_id: '', reason: '', amount: '', quantity: '1' })
  const [saving, setSaving] = useState(false)
  const reqId = useRef(0)

  const people = useMemo(() => [
    ...data.players.map((p) => ({ id: p.player_id, name: p.name })),
    ...data.candidates,
  ], [data.players, data.candidates])

  // Add a fixed row for each of these players who has none yet.
  const addPlayers = useCallback((list) => {
    setRows((rs) => {
      const have = new Set(rs.filter((r) => r.player_id).map((r) => r.player_id))
      const fresh = list.filter((p) => !have.has(p.player_id)).map((p) => blankRow({ player_id: p.player_id, name: p.name, fixed: true }))
      // An untouched starter line makes way for the players.
      const base = rs.filter((r) => hasContent(r) || r.player_id)
      return [...base, ...fresh].length ? [...base, ...fresh] : [blankRow()]
    })
  }, [])

  const refresh = useCallback((d, { fill = true } = {}) => {
    const id = ++reqId.current
    return api.bsFinesSession(teamId, d || undefined).then((res) => {
      if (id !== reqId.current) return
      setSide(res)
      if (!d) setDate(res.date)
      if (fill) addPlayers(res.players)
    }).catch((e) => toastRef.current.error(e.message || 'Could not load the side'))
  }, [teamId, addPlayers, toastRef])

  useEffect(() => { refresh(undefined) }, [refresh])

  const changeDate = (d) => {
    setDate(d)
    if (d) refresh(d)
  }

  const existing = side?.existing || {}
  const totals = useMemo(() => totalsByPlayer(rows, types), [rows, types])
  const filled = rows.filter((r) => r.player_id && hasContent(r))
  const grand = Object.values(totals).reduce((a, b) => a + b, 0)
  const overNames = max == null ? [] : Object.entries(totals)
    .filter(([pid, t]) => (existing[pid] || 0) + t > max + 0.001)
    .map(([pid]) => rows.find((r) => r.player_id === pid)?.name || people.find((p) => p.id === pid)?.name || 'A player')

  const patchRow = (key, p) => setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...p } : r)))
  const removeRow = (key) => setRows((rs) => {
    const next = rs.filter((r) => r.key !== key)
    return next.length ? next : [blankRow()]
  })
  const anotherFor = (row) => setRows((rs) => {
    const i = rs.findIndex((r) => r.key === row.key)
    const at = rs.map((r, k) => (r.player_id === row.player_id ? k : -1)).filter((k) => k >= 0).pop() ?? i
    const copy = [...rs]
    copy.splice(at + 1, 0, blankRow({ player_id: row.player_id, name: row.name, fixed: true }))
    return copy
  })
  const toggle = (pid) => setChecked((s) => { const n = new Set(s); n.has(pid) ? n.delete(pid) : n.add(pid); return n })
  const playerIds = [...new Set(rows.filter((r) => r.player_id).map((r) => r.player_id))]
  const allChecked = playerIds.length > 0 && playerIds.every((p) => checked.has(p))

  // ── Bulk: the same fine to several players, or the maximum ──
  const bulkLine = () => {
    const t = types.find((x) => x.id === bulk.fine_type_id)
    if (!t && (!bulk.reason.trim() || !(Number(bulk.amount) > 0))) {
      toast.error('Pick a fine from the list, or type what it was for and an amount')
      return null
    }
    return t
      ? { fine_type_id: t.id, reason: '', amount: bulk.amount, quantity: bulk.quantity || '1', isMax: false }
      : { fine_type_id: '', reason: bulk.reason.trim(), amount: bulk.amount, quantity: bulk.quantity || '1', isMax: false }
  }
  const fineThem = (pids) => {
    if (pids.length === 0) { toast.error('Tick at least one player first'); return }
    const line = bulkLine()
    if (!line) return
    setRows(giveLines(rows, pids, () => line))
  }
  const maxThem = (pids) => {
    if (max == null) return
    if (pids.length === 0) { toast.error('Tick at least one player first'); return }
    let skipped = 0
    const others = totalsByPlayer(rows, types, { skipMax: true })
    setRows(giveLines(rows, pids, (pid) => {
      const room = Math.round((max - (existing[pid] || 0) - (others[pid] || 0)) * 100) / 100
      if (room <= 0) { skipped += 1; return null }
      return { fine_type_id: '', reason: 'Maximum fine', amount: room.toFixed(2), quantity: '1', isMax: true }
    }, { replaceMax: true }))
    if (skipped) toast.info(`${skipped} player${skipped === 1 ? ' is' : 's are'} already at the maximum`)
  }

  const save = async () => {
    const bad = filled.find((r) => !r.fine_type_id && (!r.reason.trim() || r.amount === ''))
    if (bad) { toast.error(`${bad.name || 'A line'}: say what it was for and an amount`); return }
    setSaving(true)
    try {
      const res = await api.bsFinesAddEntries(teamId, {
        fined_on: date,
        items: filled.map((r) => ({
          player_id: r.player_id,
          fine_type_id: r.fine_type_id || null,
          reason: r.fine_type_id ? null : r.reason,
          amount: r.amount === '' ? null : r.amount,
          quantity: Number(r.quantity) || 1,
          note: r.note.trim() || null,
        })),
      })
      toast.success(`${res.created} fine${res.created === 1 ? '' : 's'} added, ${money(res.total)} to collect`)
      setRows([blankRow()])
      setChecked(new Set())
      await refresh(date)
      onSaved()
    } catch (e) { toast.error(e.message || 'Could not save the fines') } finally { setSaving(false) }
  }

  const fixtureText = side && side.fixtures.length
    ? `Side picked for ${side.fixtures.map((f) => `${f.opponent || 'a game'} (${f.date ? shortDate(f.date) : '?'})`).join(' and ')}.`
    : side ? 'No side has been picked for that week. Add the squad, or choose players yourself.' : ''
  const ticked = [...checked].filter((p) => playerIds.includes(p))

  return (
    <Card title="Add fines" sub="The rows start as the players picked for that week. Tick players to fine them together, or use Fine all and Max all.">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-2">
        <div className="flex items-center gap-2.5">
          <label className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint" htmlFor="fines-date">Date</label>
          <input id="fines-date" type="date" value={date} max={todayISO()} onChange={(e) => changeDate(e.target.value)} className={inputCls} />
        </div>
        <span className="text-[12.5px] text-pb-dim" data-side-note>{fixtureText}</span>
        <div className="flex gap-1.5 ml-auto">
          <Btn sm onClick={() => side && addPlayers(side.players)} disabled={!side || side.players.length === 0}>Selected side</Btn>
          <Btn sm onClick={() => addPlayers(data.players.filter((p) => p.in_squad))}>Whole squad</Btn>
        </div>
      </div>

      {/* Bulk bar */}
      <div className="rounded-lg p-3 mb-2" style={{ background: 'var(--pb-surface2)' }} data-bulk-bar>
        <div className="flex flex-wrap items-center gap-2">
          <select value={bulk.fine_type_id} onChange={(e) => setBulk((b) => ({ ...b, fine_type_id: e.target.value, amount: '' }))} aria-label="Fine for the group" className={`${inputCls} min-w-[150px]`}>
            <option value="">Something else…</option>
            {types.map((t) => <option key={t.id} value={t.id}>{t.name} ({money(t.amount)})</option>)}
          </select>
          {!bulk.fine_type_id && (
            <>
              <input value={bulk.reason} onChange={(e) => setBulk((b) => ({ ...b, reason: e.target.value }))} maxLength={120} placeholder="What for?" aria-label="Group reason" className={`${inputCls} flex-1 min-w-[120px]`} />
              <input value={bulk.amount} onChange={(e) => setBulk((b) => ({ ...b, amount: e.target.value.replace(/[^0-9.]/g, '') }))} inputMode="decimal" placeholder="$" aria-label="Group amount" className={`${inputCls} w-20`} />
            </>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2 mt-2">
          <Btn sm variant="soft" onClick={() => fineThem(playerIds)} disabled={playerIds.length === 0} data-fine-all>Fine all</Btn>
          <Btn sm onClick={() => fineThem(ticked)} data-fine-ticked>Fine ticked ({ticked.length})</Btn>
          {max != null && (
            <>
              <Btn sm variant="soft" onClick={() => maxThem(playerIds)} disabled={playerIds.length === 0} data-max-all>Max all ({money(max)})</Btn>
              <Btn sm onClick={() => maxThem(ticked)} data-max-ticked>Max ticked ({ticked.length})</Btn>
            </>
          )}
          <label className="ml-auto text-[12px] text-pb-faint inline-flex items-center gap-1.5">
            <input type="checkbox" checked={allChecked} onChange={() => setChecked(allChecked ? new Set() : new Set(playerIds))} aria-label="Tick everyone" />
            Tick everyone
          </label>
        </div>
        {max == null && <div className="text-[11.5px] text-pb-faint mt-1.5">Set a maximum per session in Setup and Max all and Max ticked appear here.</div>}
      </div>

      <div>
        {rows.map((r) => (
          <FineRow key={r.key} row={r} types={types} people={people} max={max}
            existing={r.player_id ? existing[r.player_id] : 0}
            total={r.player_id ? totals[r.player_id] : 0}
            checked={checked.has(r.player_id)} onCheck={() => toggle(r.player_id)}
            onChange={(p) => patchRow(r.key, p)} onRemove={() => removeRow(r.key)} onAnother={() => anotherFor(r)} />
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3 mt-3">
        <Btn sm icon="plus" onClick={() => setRows((rs) => [...rs, blankRow()])}>Add a line</Btn>
        <span className="text-[13px] text-pb-dim ml-auto" data-session-total>{filled.length} line{filled.length === 1 ? '' : 's'}, <b className="text-pb-text">{money(grand)}</b></span>
        <Btn variant="primary" onClick={save} disabled={saving || filled.length === 0 || !date || overNames.length > 0}>{saving ? 'Saving…' : 'Save fines'}</Btn>
      </div>
      {overNames.length > 0 && (
        <p className="text-[12.5px] mt-2" data-over-max style={{ color: 'var(--pb-red)' }}>
          Over the {money(max)} maximum: {[...new Set(overNames)].join(', ')}. Lower their lines to save.
        </p>
      )}
    </Card>
  )
}
