import { useState, useEffect, useCallback } from 'react'
import { api } from '../../../lib/api'
import BetterCommsLayout from '../../../components/admin/BetterCommsLayout'

// The whitelisted segment fields (mirrors services/comms_segments.py). Each rule
// is {field, op, value}; rules are ANDed. Stat fields read the club's current
// season, so a stat rule narrows to the playing squad automatically.
const FIELDS = {
  tag: { label: 'Has tag', input: 'text', ops: [['has', 'is']] },
  source: {
    label: 'Source', input: 'select', ops: [['eq', 'is']],
    options: [['player', 'A player'], ['member', 'A fee member'], ['import', 'Imported'], ['manual', 'Added manually']],
  },
  matches_this_season: { label: 'Matches this season', input: 'number', ops: [['gte', 'at least'], ['lte', 'at most']] },
  runs_this_season: { label: 'Runs this season', input: 'number', ops: [['gte', 'at least'], ['lte', 'at most']] },
  wickets_this_season: { label: 'Wickets this season', input: 'number', ops: [['gte', 'at least'], ['lte', 'at most']] },
  catches_this_season: { label: 'Catches this season', input: 'number', ops: [['gte', 'at least'], ['lte', 'at most']] },
}
const FIELD_KEYS = Object.keys(FIELDS)

function newRule() {
  return { field: 'tag', op: 'has', value: '' }
}

function RuleRow({ rule, onChange, onRemove }) {
  const f = FIELDS[rule.field] || FIELDS.tag
  return (
    <div className="flex flex-wrap items-center gap-2 py-1.5">
      <select value={rule.field}
        onChange={e => {
          const nf = FIELDS[e.target.value]
          onChange({ field: e.target.value, op: nf.ops[0][0], value: '' })
        }}
        className="px-2 py-1.5 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm">
        {FIELD_KEYS.map(k => <option key={k} value={k}>{FIELDS[k].label}</option>)}
      </select>
      <select value={rule.op} onChange={e => onChange({ ...rule, op: e.target.value })}
        className="px-2 py-1.5 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm">
        {f.ops.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
      {f.input === 'select' ? (
        <select value={rule.value} onChange={e => onChange({ ...rule, value: e.target.value })}
          className="px-2 py-1.5 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm">
          <option value="">choose…</option>
          {f.options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      ) : (
        <input value={rule.value} onChange={e => onChange({ ...rule, value: e.target.value })}
          type={f.input === 'number' ? 'number' : 'text'}
          placeholder={f.input === 'number' ? '0' : 'e.g. Committee'}
          className="px-2 py-1.5 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm w-32" />
      )}
      <button onClick={onRemove} className="text-pb-faint hover:text-pb-red text-sm px-1">✕</button>
    </div>
  )
}

function Editor({ initial, onSaved, onCancel, onDeleted }) {
  const [name, setName] = useState(initial?.name || '')
  const [rules, setRules] = useState(initial?.definition?.rules?.length ? initial.definition.rules : [newRule()])
  const [count, setCount] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const definition = { match: 'all', rules: rules.filter(r => String(r.value).trim() !== '') }

  // Live preview, debounced on the rules.
  useEffect(() => {
    let live = true
    const t = setTimeout(() => {
      api.commsPreviewSegment(definition).then(r => { if (live) setCount(r.count) }).catch(() => { if (live) setCount(null) })
    }, 350)
    return () => { live = false; clearTimeout(t) }
  }, [JSON.stringify(rules)]) // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => {
    if (!name.trim()) { setErr('Give the segment a name.'); return }
    setBusy(true); setErr('')
    try {
      const saved = initial?.id
        ? await api.commsUpdateSegment(initial.id, name.trim(), definition)
        : await api.commsCreateSegment(name.trim(), definition)
      onSaved(saved)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const remove = async () => {
    if (!initial?.id || !window.confirm('Delete this segment?')) return
    setBusy(true)
    try { await api.commsDeleteSegment(initial.id); onDeleted(initial.id) }
    catch (e) { setErr(e.message); setBusy(false) }
  }

  return (
    <div className="pb-card p-4">
      <input value={name} onChange={e => setName(e.target.value)} placeholder="Segment name (e.g. Active first XI)"
        className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm mb-3" />
      <div className="text-pb-faintest text-xs mb-1">Match contacts where ALL of these are true:</div>
      <div className="mb-2">
        {rules.map((r, i) => (
          <RuleRow key={i} rule={r}
            onChange={nr => setRules(rs => rs.map((x, j) => j === i ? nr : x))}
            onRemove={() => setRules(rs => rs.length > 1 ? rs.filter((_, j) => j !== i) : rs)} />
        ))}
      </div>
      <button onClick={() => setRules(rs => [...rs, newRule()])}
        className="text-xs text-pb-faint hover:text-pb-text mb-3">+ Add condition</button>

      <div className="flex items-center justify-between gap-3 pt-3 pb-hairline-t">
        <div className="text-sm text-pb-text">
          {count == null ? <span className="text-pb-faint">Counting…</span>
            : <><span className="font-medium" style={{ color: 'var(--pb-accent)' }}>{count}</span> matching contact{count === 1 ? '' : 's'}</>}
        </div>
        <div className="flex items-center gap-2">
          {initial?.id && <button onClick={remove} disabled={busy} className="text-sm text-pb-faint hover:text-pb-red px-2">Delete</button>}
          <button onClick={onCancel} className="text-sm text-pb-faint hover:text-pb-text px-2">Cancel</button>
          <button onClick={save} disabled={busy}
            className="px-3 py-1.5 rounded text-sm font-medium text-white disabled:opacity-60" style={{ background: 'var(--pb-accent)' }}>
            {busy ? 'Saving…' : 'Save segment'}
          </button>
        </div>
      </div>
      {err && <div className="text-pb-red text-xs mt-2">{err}</div>}
    </div>
  )
}

export default function CommsSegments() {
  const [segments, setSegments] = useState(null)
  const [editing, setEditing] = useState(null) // segment object, {} for new, or null
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api.commsListSegments().then(setSegments).catch(e => { setError(e.message); setSegments([]) })
  }, [])
  useEffect(() => { load() }, [load])

  const onSaved = () => { setEditing(null); load() }
  const onDeleted = () => { setEditing(null); load() }

  return (
    <BetterCommsLayout
      title="Segments"
      actions={!editing && (
        <button onClick={() => setEditing({})}
          className="px-3 py-1.5 rounded text-sm font-medium text-white" style={{ background: 'var(--pb-accent)' }}>
          + New segment
        </button>
      )}
    >
      {error && <div className="pb-card p-3 mb-4 text-pb-red text-sm">{error}</div>}

      <div className="text-pb-faintest text-sm mb-4 max-w-2xl">
        A segment is a saved filter that re-runs every time you send, so it always reflects who fits today.
        Mix contact tags with this season's cricket data, like "played at least 5 matches" or "took 10+ wickets".
      </div>

      {editing ? (
        <Editor initial={editing.id ? editing : null} onSaved={onSaved} onCancel={() => setEditing(null)} onDeleted={onDeleted} />
      ) : segments == null ? (
        <div className="text-pb-faint text-sm">Loading…</div>
      ) : segments.length === 0 ? (
        <div className="pb-card p-8 text-center">
          <div className="text-pb-text font-medium mb-1">No segments yet</div>
          <div className="text-pb-faint text-sm mb-4">Build a reusable audience from tags and cricket stats.</div>
          <button onClick={() => setEditing({})}
            className="px-4 py-2 rounded text-sm font-medium text-white" style={{ background: 'var(--pb-accent)' }}>
            + New segment
          </button>
        </div>
      ) : (
        <div className="pb-card overflow-hidden">
          {segments.map((s, i) => (
            <button key={s.id} onClick={() => setEditing(s)}
              className={`w-full text-left flex items-center justify-between gap-4 px-5 py-3.5 hover:bg-pb-surface2 transition-colors ${i > 0 ? 'pb-hairline-t' : ''}`}>
              <div className="min-w-0">
                <div className="text-pb-text text-sm truncate">{s.name}</div>
                <div className="text-pb-faintest text-xs mt-0.5">{(s.definition?.rules || []).length} condition{(s.definition?.rules || []).length === 1 ? '' : 's'}</div>
              </div>
              <span className="text-pb-faint text-xs shrink-0">Edit →</span>
            </button>
          ))}
        </div>
      )}
    </BetterCommsLayout>
  )
}
