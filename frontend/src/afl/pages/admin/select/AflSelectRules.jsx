import { useEffect, useState } from 'react'
import { aflApi } from '../../../aflApi'
import { useToast } from '../../../../contexts/ToastContext'
import LoadingSpinner from '../../../../components/LoadingSpinner'
import { Btn, Card, INPUT, PageHead } from './ui'

// Your league's rules, written down once, so a selector isn't holding the
// by-laws in their head on a Thursday night. Each rule covers every grade
// unless it names some. "Warn" asks before saving a side that breaks it;
// "Block" refuses to save it.

function ConfigFields({ kind, config, onChange }) {
  const c = config || {}
  const num = (key, label, min, max) => (
    <label className="flex flex-col text-xs text-pb-dim gap-1">
      {label}
      <input type="number" min={min} max={max} className={`${INPUT} w-24`} value={c[key] ?? ''}
        onChange={e => onChange({ ...c, [key]: e.target.value === '' ? null : Number(e.target.value) })} />
    </label>
  )
  if (kind === 'team_size') return <div className="flex flex-wrap gap-3">{num('field', 'On the ground', 9, 18)}{num('bench', 'Bench', 0, 15)}{num('emergencies', 'Emergencies', 0, 6)}</div>
  if (kind === 'age') return (
    <div className="flex flex-wrap items-end gap-3">
      {num('min_age', 'At least', 4, 99)}
      {num('under_age', 'Under', 5, 100)}
      <label className="flex flex-col text-xs text-pb-dim gap-1">Measured
        <select className={INPUT} value={c.basis || 'jan1'} onChange={e => onChange({ ...c, basis: e.target.value })}>
          <option value="jan1">As at 1 January of the season</option>
          <option value="match_date">On match day</option>
          <option value="fixed_date">On a set date</option>
        </select>
      </label>
      {c.basis === 'fixed_date' && (
        <label className="flex flex-col text-xs text-pb-dim gap-1">Date
          <input type="date" className={INPUT} value={c.date || ''} onChange={e => onChange({ ...c, date: e.target.value })} />
        </label>
      )}
    </div>
  )
  if (kind === 'finals_qualification') return (
    <div className="flex flex-wrap items-end gap-3">
      {num('min_games', 'Home-and-away games', 1, 40)}
      <label className="flex flex-col text-xs text-pb-dim gap-1">Counted
        <select className={INPUT} value={c.count || 'grade_or_higher'} onChange={e => onChange({ ...c, count: e.target.value })}>
          <option value="grade_or_higher">In this grade or higher</option>
          <option value="grade">In this grade only</option>
          <option value="club">Anywhere at the club</option>
        </select>
      </label>
    </div>
  )
  if (kind === 'higher_grade_limit') return (
    <div className="flex flex-wrap items-end gap-3">
      {num('max_games', 'Most games in a higher side', 0, 40)}
      <label className="flex items-center gap-1 text-xs text-pb-dim pb-1">
        <input type="checkbox" checked={c.finals_only !== false} onChange={e => onChange({ ...c, finals_only: e.target.checked })} />
        Finals only
      </label>
    </div>
  )
  if (kind === 'concussion') return num('days', 'Days stood down', 1, 120)
  if (kind === 'custom') return (
    <textarea className={`${INPUT} w-full`} rows={2} placeholder="What the rule says" value={c.text || ''}
      onChange={e => onChange({ ...c, text: e.target.value })} />
  )
  return null
}

function ScopeFields({ scope, meta, onChange }) {
  const s = scope || {}
  const toggle = (key, v) => {
    const cur = s[key] || []
    onChange({ ...s, [key]: cur.includes(v) ? cur.filter(x => x !== v) : [...cur, v] })
  }
  return (
    <details className="text-xs text-pb-dim mt-2">
      <summary className="cursor-pointer">Covers {[...(s.grade_names || []), ...(s.categories || []).map(c => meta.categories.find(x => x.key === c)?.label)].join(', ') || 'every grade'}</summary>
      <div className="mt-2 flex flex-wrap gap-2">
        {meta.categories.map(c => (
          <label key={c.key} className="flex items-center gap-1"><input type="checkbox" checked={(s.categories || []).includes(c.key)} onChange={() => toggle('categories', c.key)} />{c.label}</label>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        {meta.grades.map(g => (
          <label key={g} className="flex items-center gap-1"><input type="checkbox" checked={(s.grade_names || []).includes(g)} onChange={() => toggle('grade_names', g)} />{g}</label>
        ))}
      </div>
    </details>
  )
}

function Marks({ rule, players, onChange }) {
  const toast = useToast()
  const [f, setF] = useState({ player_id: '', mode: rule.kind === 'concussion' ? 'incident' : 'permit', incident_date: '', note: '' })
  const modes = rule.kind === 'concussion'
    ? [['incident', 'Concussed on'], ['permit', 'Cleared to play']]
    : [['permit', 'Cleared (a permit)'], ['block', 'Ruled out']]
  async function add(e) {
    e.preventDefault()
    try {
      await aflApi.selAddRulePlayer(rule.id, Object.fromEntries(Object.entries(f).filter(([, v]) => v !== '')))
      setF({ ...f, player_id: '', incident_date: '', note: '' })
      onChange()
    } catch (err) { toast.error(err.message) }
  }
  return (
    <div className="mt-3 pb-hairline-t pt-2">
      {rule.players.map(m => (
        <div key={m.id} className="flex items-center gap-2 text-xs py-0.5">
          <span className="flex-1">{m.name} · {modes.find(x => x[0] === m.mode)?.[1] || m.mode}{m.incident_date ? ` ${m.incident_date}` : ''}{m.note ? ` · ${m.note}` : ''}</span>
          <Btn small onClick={async () => { await aflApi.selDeleteRulePlayer(rule.id, m.id); onChange() }}>Remove</Btn>
        </div>
      ))}
      <form onSubmit={add} className="flex flex-wrap gap-2 mt-2" data-testid="mark-form">
        <select className={`${INPUT} !text-xs`} value={f.player_id} onChange={e => setF({ ...f, player_id: e.target.value })} aria-label="Player">
          <option value="">Player…</option>
          {players.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <select className={`${INPUT} !text-xs`} value={f.mode} onChange={e => setF({ ...f, mode: e.target.value })} aria-label="Entry">
          {modes.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        {f.mode === 'incident' && <input type="date" className={`${INPUT} !text-xs`} aria-label="Date" value={f.incident_date} onChange={e => setF({ ...f, incident_date: e.target.value })} />}
        <input className={`${INPUT} !text-xs flex-1 min-w-[8rem]`} placeholder="Note" value={f.note} onChange={e => setF({ ...f, note: e.target.value })} />
        <Btn small type="submit" disabled={!f.player_id || (f.mode === 'incident' && !f.incident_date)}>Add</Btn>
      </form>
    </div>
  )
}

function RuleCard({ rule, meta, players, onChange }) {
  const toast = useToast()
  const [draft, setDraft] = useState(null)
  const edit = draft || rule
  async function save() {
    try { await aflApi.selUpdateRule(rule.id, { name: draft.name, severity: draft.severity, scope: draft.scope, config: draft.config }); setDraft(null); onChange() }
    catch (e) { toast.error(e.message) }
  }
  return (
    <Card className="p-4" data-testid="rule-card">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-sm">{rule.name}</div>
          <div className="text-xs text-pb-dim">{rule.summary}</div>
        </div>
        {rule.kind !== 'team_size' && (
          <span className="font-mono text-[10px] uppercase px-1.5 py-0.5 rounded border pb-hairline"
            style={{ color: rule.severity === 'block' ? 'var(--pb-red,#e5484d)' : 'var(--pb-amber,#d29922)' }}>
            {rule.severity === 'block' ? 'Blocks' : 'Warns'}
          </span>
        )}
        <Btn small onClick={() => aflApi.selUpdateRule(rule.id, { enabled: !rule.enabled }).then(onChange)}>{rule.enabled ? 'Turn off' : 'Turn on'}</Btn>
        <Btn small onClick={() => setDraft(draft ? null : { ...rule })}>{draft ? 'Close' : 'Edit'}</Btn>
        <Btn small danger onClick={async () => { if (window.confirm(`Delete ${rule.name}?`)) { await aflApi.selDeleteRule(rule.id); onChange() } }}>Delete</Btn>
      </div>
      {draft && (
        <div className="mt-3 space-y-3">
          <input className={`${INPUT} w-full`} value={edit.name || ''} onChange={e => setDraft({ ...edit, name: e.target.value })} aria-label="Name" />
          <ConfigFields kind={rule.kind} config={edit.config} onChange={config => setDraft({ ...edit, config })} />
          {rule.kind !== 'team_size' && (
            <select className={INPUT} value={edit.severity} onChange={e => setDraft({ ...edit, severity: e.target.value })} aria-label="When broken">
              <option value="warn">Warn before saving</option>
              <option value="block">Refuse to save</option>
            </select>
          )}
          <ScopeFields scope={edit.scope} meta={meta} onChange={scope => setDraft({ ...edit, scope })} />
          <Btn primary small onClick={save}>Save rule</Btn>
        </div>
      )}
      {!draft && <div className="text-xs text-pb-faint mt-1">Covers {[...(rule.scope.grade_names || []), ...(rule.scope.categories || [])].join(', ') || 'every grade'}</div>}
      {['concussion', 'custom', 'age', 'finals_qualification', 'higher_grade_limit', 'fees', 'registration'].includes(rule.kind) && (
        <Marks rule={rule} players={players} onChange={onChange} />
      )}
    </Card>
  )
}

export default function AflSelectRules() {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [players, setPlayers] = useState([])
  const [kind, setKind] = useState('')
  const load = () => aflApi.selRules().then(setData)
  useEffect(() => {
    load().catch(e => toast.error(e.message))
    aflApi.selSquads().then(d => setPlayers(d.players.filter(p => p.status !== 'inactive'))).catch(() => {})
  }, [])

  async function add() {
    if (!kind) return
    try { await aflApi.selCreateRule({ kind, severity: 'warn' }); setKind(''); await load() } catch (e) { toast.error(e.message) }
  }

  if (!data) return <div className="pt-16 flex justify-center"><LoadingSpinner /></div>
  return (
    <div>
      <PageHead title="Selection rules"
        caption="Your league's rules, checked beside every name on the selection board. A rule covers every grade unless you name some."
        right={<>
          {data.rules.length === 0 && <Btn onClick={async () => { await aflApi.selStarterRules(); load() }}>Add the usual two</Btn>}
          <select className={INPUT} value={kind} onChange={e => setKind(e.target.value)} aria-label="New rule">
            <option value="">Add a rule…</option>
            {data.kinds.map(k => <option key={k.kind} value={k.kind}>{k.label}</option>)}
          </select>
          <Btn primary onClick={add} disabled={!kind}>Add</Btn>
        </>} />
      {data.rules.length === 0 && (
        <Card className="p-6 text-sm text-pb-dim mb-4">
          No rules yet. Without one, the board picks a senior side: 18 on the ground, up to 10 on the bench and 3 emergencies.
          "Add the usual two" puts that team size in, plus AFL's 21-day concussion stand-down.
        </Card>
      )}
      <div className="space-y-3">
        {data.rules.map(r => <RuleCard key={r.id} rule={r} meta={data} players={players} onChange={load} />)}
      </div>
      <Card className="p-4 mt-6">
        <h2 className="font-semibold text-sm mb-2">What each rule does</h2>
        {data.kinds.map(k => <div key={k.kind} className="text-xs text-pb-dim py-0.5"><strong className="text-pb-text">{k.label}.</strong> {k.help}</div>)}
      </Card>
    </div>
  )
}
