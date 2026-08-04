import { useState, useEffect } from 'react'
import { C, MONO } from '../ui'

// A reusable config-list manager: Starter Pack seeding, add / inline-edit /
// delete, and drag-to-reorder. Every setup list in BetterClubManager (roles,
// activities, qualifications, event types, facilities, assets, diary templates,
// roster areas…) drives one of these with its own field defs + endpoint hooks.
//
// Props:
//   load()                    → Promise<item[]>   (each item has .id + field keys)
//   fields: [{ key, label, type:'text'|'number'|'checkbox'|'select', options?, placeholder?, required?, span? }]
//     a 'select' field may set allowNew + onCreateNew(name)->id (+ newLabel/
//     newPlaceholder) to offer an inline "＋ New…" option that coins a value
//     (e.g. a new type) on submit and uses its id, without leaving the form.
//   onCreate(values) / onUpdate(id, values) / onDelete(id) / onReorder(orderedIds)  (async; omit to hide that action)
//   seed: { label, fn }       (Starter Pack button; shown when the list is empty)
//   primaryKey                (the field shown as the row title; defaults fields[0].key)
//   subtitle(item)            (optional meta line under the title)
//   describe                  (intro paragraph)
//   addLabel                  (defaults 'Add')
//   accentOf(item)            (optional dot colour per row)

export default function EntityManager({ load, fields, onCreate, onUpdate, onDelete, onReorder, onChanged, seed, primaryKey, subtitle, describe, addLabel = 'Add', accentOf, emptyText }) {
  const [items, setItems] = useState(null)
  const [err, setErr] = useState(null)
  const [adding, setAdding] = useState(false)
  const [editId, setEditId] = useState(null)
  const [form, setForm] = useState({})
  const [busy, setBusy] = useState(false)
  const [dragId, setDragId] = useState(null)
  const [overId, setOverId] = useState(null)
  const [newMode, setNewMode] = useState({})  // per-select-field: "＋ New…" chosen
  const [newText, setNewText] = useState({})  // per-select-field: the typed new name

  const pk = primaryKey || fields[0].key
  const notify = () => { try { onChanged && onChanged() } catch { /* parent refresh is best-effort */ } }
  const refresh = () => load().then(rows => setItems(Array.isArray(rows) ? rows : [])).catch(e => setErr(String(e?.message || e)))
  useEffect(() => { refresh() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const resetNew = () => { setNewMode({}); setNewText({}) }
  const blank = () => Object.fromEntries(fields.map(f => [f.key, f.type === 'checkbox' ? false : '']))
  const startAdd = () => { setForm(blank()); resetNew(); setAdding(true); setEditId(null) }
  const startEdit = (it) => { setForm(Object.fromEntries(fields.map(f => [f.key, it[f.key] ?? (f.type === 'checkbox' ? false : '')]))); resetNew(); setEditId(it.id); setAdding(false) }
  const cancel = () => { setAdding(false); setEditId(null); resetNew() }

  const clean = (v) => {
    const o = {}
    fields.forEach(f => {
      let x = v[f.key]
      if (f.type === 'number') x = (x === '' || x == null) ? null : Number(x)
      else if (f.type === 'checkbox') x = !!x
      else if (x === '') x = null
      o[f.key] = x
    })
    return o
  }
  const canSubmit = fields.filter(f => f.required).every(f =>
    (form[f.key] !== '' && form[f.key] != null) || (newMode[f.key] && (newText[f.key] || '').trim()))
  const submit = async () => {
    if (!canSubmit) return
    setBusy(true)
    try {
      const values = clean(form)
      // Coin any inline "＋ New…" values first, then use the created id.
      for (const f of fields) {
        if (f.type === 'select' && f.allowNew && newMode[f.key] && f.onCreateNew) {
          const name = (newText[f.key] || '').trim()
          if (name) { const made = await f.onCreateNew(name); values[f.key] = made?.id ?? made }
        }
      }
      if (editId) await onUpdate(editId, values); else await onCreate(values)
      await refresh(); notify(); cancel()
    } catch (e) { setErr(String(e?.message || e)) } finally { setBusy(false) }
  }
  const remove = async (it) => {
    if (!window.confirm('Remove "' + (it[pk] || 'this item') + '"? This can be re-added later.')) return
    setBusy(true); try { await onDelete(it.id); await refresh(); notify() } finally { setBusy(false) }
  }
  const doSeed = async () => {
    setBusy(true); setErr(null)
    try {
      await seed.fn()
      const rows = await load()
      const arr = Array.isArray(rows) ? rows : []
      setItems(arr)
      notify()
      if (arr.length === 0) setErr('Starter pack ran but nothing was added — these items may already exist (possibly archived). Add one manually below, or check with support.')
    } catch (e) {
      setErr('Could not add the starter pack: ' + String(e?.message || e))
    } finally { setBusy(false) }
  }

  const move = (fromId, toId) => {
    setDragId(null); setOverId(null)
    if (!fromId || fromId === toId || !onReorder) return
    const arr = [...items]
    const fi = arr.findIndex(x => x.id === fromId), ti = arr.findIndex(x => x.id === toId)
    if (fi < 0 || ti < 0) return
    const [m] = arr.splice(fi, 1); arr.splice(ti, 0, m)
    setItems(arr)
    onReorder(arr.map(x => x.id)).then(notify).catch(() => {})
  }

  const inp = { background: C.surface2, border: `1px solid ${C.hair2}`, borderRadius: 7, padding: '7px 10px', color: C.text, fontSize: 13, outline: 'none', width: '100%' }
  const btnP = { padding: '7px 13px', borderRadius: 7, fontSize: 12.5, fontWeight: 600, border: 'none', background: C.accent, color: '#fff', cursor: 'pointer' }
  const btnS = { padding: '7px 12px', borderRadius: 7, fontSize: 12.5, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer' }

  const setF = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const fieldInputs = () => (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10 }}>
      {fields.map(f => (
        <label key={f.key} style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, gridColumn: f.span === 2 ? '1 / -1' : undefined, display: f.type === 'checkbox' ? 'flex' : 'block', alignItems: 'center', gap: 8 }}>
          {f.type === 'checkbox'
            ? <><input type="checkbox" checked={!!form[f.key]} onChange={e => setF(f.key, e.target.checked)} /> <span style={{ color: C.dim, fontSize: 12.5, fontFamily: 'inherit' }}>{f.label}</span></>
            : f.type === 'select'
              ? <>{f.label}{f.required ? ' *' : ''}
                  <select value={newMode[f.key] ? '__new__' : (form[f.key] ?? '')}
                    onChange={e => { const v = e.target.value; if (v === '__new__') { setNewMode(m => ({ ...m, [f.key]: true })) } else { setNewMode(m => ({ ...m, [f.key]: false })); setF(f.key, v) } }}
                    style={{ ...inp, marginTop: 3 }}>
                    <option value="">{f.placeholder || '—'}</option>
                    {(f.options || []).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                    {f.allowNew && <option value="__new__">＋ {f.newLabel || 'New…'}</option>}
                  </select>
                  {f.allowNew && newMode[f.key] && <input value={newText[f.key] || ''} placeholder={f.newPlaceholder || 'New name'} onChange={e => setNewText(t => ({ ...t, [f.key]: e.target.value }))} style={{ ...inp, marginTop: 6 }} />}
                </>
              : <>{f.label}{f.required ? ' *' : ''}<input type={f.type === 'number' ? 'number' : 'text'} value={form[f.key] ?? ''} placeholder={f.placeholder || ''} onChange={e => setF(f.key, e.target.value)} style={{ ...inp, marginTop: 3 }} /></>}
        </label>
      ))}
    </div>
  )
  const formCard = (
    <div style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 9, padding: 14, marginBottom: 10 }}>
      {fieldInputs()}
      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <button onClick={submit} disabled={busy || !canSubmit} style={{ ...btnP, opacity: (busy || !canSubmit) ? 0.6 : 1 }}>{editId ? 'Save' : addLabel}</button>
        <button onClick={cancel} style={btnS}>Cancel</button>
      </div>
    </div>
  )

  if (items === null) return <div style={{ fontSize: 13, color: C.faint, padding: '4px 2px' }}>{err ? 'Could not load.' : 'Loading…'}</div>

  return (
    <div>
      {describe && <p style={{ fontSize: 13, color: C.dim, margin: '0 0 14px', lineHeight: 1.55, maxWidth: '46rem' }}>{describe}</p>}

      {err && (
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 12, padding: '9px 12px', borderRadius: 8, background: 'rgba(239,68,68,0.10)', border: '1px solid rgba(239,68,68,0.35)' }}>
          <span style={{ fontSize: 13, color: '#fca5a5', lineHeight: 1.5, flex: 1 }}>{err}</span>
          <button onClick={() => setErr(null)} style={{ background: 'transparent', border: 'none', color: '#fca5a5', cursor: 'pointer', fontSize: 15, lineHeight: 1, padding: 0 }}>×</button>
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        {onCreate && !adding && editId == null && <button onClick={startAdd} style={btnS}>+ {addLabel}</button>}
        {/* Always available: the starter pack tops up (idempotent) so a club can
            pick up newly-added starter items. Primary when the list is empty,
            secondary once it has items. */}
        {seed && <button onClick={doSeed} disabled={busy} style={{ ...(items.length === 0 ? btnP : btnS), opacity: busy ? 0.6 : 1 }}>{busy ? 'Adding…' : seed.label}</button>}
        {onReorder && items.length > 1 && <span style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.08em', color: C.faintest, alignSelf: 'center' }}>DRAG THE GRIP TO REORDER</span>}
      </div>

      {adding && formCard}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {items.map(it => {
          if (editId === it.id) return <div key={it.id}>{formCard}</div>
          const dragging = dragId === it.id
          const isOver = overId === it.id && dragId && dragId !== it.id
          return (
            <div key={it.id}
              onDragOver={e => { if (dragId && onReorder) { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; if (overId !== it.id) setOverId(it.id) } }}
              onDrop={e => { e.preventDefault(); move(dragId, it.id) }}
              style={{ display: 'flex', alignItems: 'center', gap: 10, background: C.surface, borderRadius: 8, padding: '10px 13px',
                border: `1px solid ${isOver ? C.accent : C.hair}`, boxShadow: isOver ? 'inset 0 2px 0 var(--pb-accent)' : undefined, opacity: dragging ? 0.5 : 1 }}>
              {onReorder && (
                <span draggable onDragStart={e => { e.dataTransfer.effectAllowed = 'move'; setDragId(it.id) }} onDragEnd={() => { setDragId(null); setOverId(null) }}
                  title="Drag to reorder" style={{ cursor: 'grab', color: C.faint, fontSize: 15, lineHeight: 1, flexShrink: 0, userSelect: 'none' }}>⠿</span>
              )}
              {accentOf && <span style={{ width: 9, height: 9, borderRadius: 3, background: accentOf(it) || C.accent, flexShrink: 0 }} />}
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontSize: 13.5, fontWeight: 600, color: C.text }}>{it[pk]}</div>
                {subtitle && subtitle(it) && <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 3 }}>{subtitle(it)}</div>}
              </div>
              {onUpdate && <button onClick={() => startEdit(it)} style={{ ...btnS, padding: '5px 10px', fontSize: 11.5 }}>Edit</button>}
              {onDelete && <button onClick={() => remove(it)} style={{ padding: '5px 10px', borderRadius: 6, fontSize: 11.5, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.faint, cursor: 'pointer' }}>Delete</button>}
            </div>
          )
        })}
        {items.length === 0 && !adding && <div style={{ fontSize: 13, color: C.faint }}>{emptyText || 'Nothing set up yet.'}</div>}
      </div>
    </div>
  )
}

// Reorder helper: persist a new order by PATCHing each item's sort_order to its
// index. Works for any entity whose update endpoint accepts sort_order and whose
// list is ordered by it (roles, activities, qualification types, event types…).
export function reorderBySortOrder(updateFn) {
  return (orderedIds) => Promise.all(orderedIds.map((id, i) => updateFn(id, { sort_order: i })))
}
