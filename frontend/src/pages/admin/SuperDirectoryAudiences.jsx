import { useState, useEffect, useCallback } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import { DIRECTORY_FIELD_DEFS, RuleRow, newRule } from './bettercomms/segmentFields'

// BetterCricket's own outreach audiences, against the Clubs Directory.
//
// This is the Super Admin half of BetterComms. It targets PROSPECT clubs by
// what they have done — exported, emailed, opened, enquired, trialing, customer
// status, engagement score — which is BetterCricket's sales telemetry and must
// never appear inside a club build. Same engine, two mounts: the club mount is
// BetterClubhouse's Audiences screen (CLUB_FIELD_DEFS only, no context switch),
// and this is the other one. See
// docs/design_handoff_betterclubhouse/PROJECT_RULES.md.
//
// It runs against the marketing organisation, so the switch into that org (what
// CommsContextBar used to do inside the club surface) belongs on the Clubs
// Directory beside it, not here.

const DEFS = DIRECTORY_FIELD_DEFS

function Editor({ initial, opts, onSaved, onCancel, onDeleted }) {
  const [name, setName] = useState(initial?.name || '')
  const [rules, setRules] = useState(initial?.definition?.rules?.length ? initial.definition.rules : [newRule(DEFS)])
  const [count, setCount] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const definition = { match: 'all', rules: rules.filter(r => String(r.value ?? '').trim() !== '') }
  const defKey = JSON.stringify(rules)

  useEffect(() => {
    let live = true
    const t = setTimeout(() => {
      api.commsPreviewSegment(definition).then(r => { if (live) setCount(r.count) }).catch(() => { if (live) setCount(null) })
    }, 350)
    return () => { live = false; clearTimeout(t) }
  }, [defKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => {
    if (!name.trim()) { setErr('Give the audience a name.'); return }
    setBusy(true); setErr('')
    try {
      const saved = initial?.id
        ? await api.commsUpdateSegment(initial.id, name.trim(), definition)
        : await api.commsCreateSegment(name.trim(), definition)
      onSaved(saved)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const remove = async () => {
    if (!initial?.id || !window.confirm('Delete this audience?')) return
    setBusy(true)
    try { await api.commsDeleteSegment(initial.id); onDeleted(initial.id) }
    catch (e) { setErr(e.message); setBusy(false) }
  }

  return (
    <div className="pb-card p-4">
      <input value={name} onChange={e => setName(e.target.value)} placeholder="Audience name (e.g. Emailed but never opened)"
        className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm mb-3" />
      <div className="text-pb-faintest text-xs mb-1">Match prospect clubs where ALL of these are true:</div>
      <div className="mb-2">
        {rules.map((r, i) => (
          <RuleRow key={i} rule={r} defs={DEFS} opts={opts}
            onChange={nr => setRules(rs => rs.map((x, j) => (j === i ? nr : x)))}
            onRemove={() => setRules(rs => (rs.length > 1 ? rs.filter((_, j) => j !== i) : rs))} />
        ))}
      </div>
      <button onClick={() => setRules(rs => [...rs, newRule(DEFS)])}
        className="text-xs text-pb-faint hover:text-pb-text mb-3">+ Add condition</button>

      <div className="flex items-center justify-between gap-3 pt-3 pb-hairline-t">
        <span className="text-sm text-pb-text">
          {count == null ? <span className="text-pb-faint">Counting…</span>
            : <><span className="font-medium" style={{ color: 'var(--pb-accent)' }}>{count}</span> matching contact{count === 1 ? '' : 's'}</>}
        </span>
        <div className="flex items-center gap-2">
          {initial?.id && (
            <a href={api.commsSegmentExportCsvUrl(initial.id)} className="text-sm text-pb-faint hover:text-pb-text px-2">Export CSV</a>
          )}
          {initial?.id && <button onClick={remove} disabled={busy} className="text-sm text-pb-faint hover:text-pb-red px-2">Delete</button>}
          <button onClick={onCancel} className="text-sm text-pb-faint hover:text-pb-text px-2">Cancel</button>
          <button onClick={save} disabled={busy}
            className="px-3 py-1.5 rounded text-sm font-medium disabled:opacity-60"
            style={{ background: 'var(--pb-accent)', color: '#0a0d14' }}>
            {busy ? 'Saving…' : 'Save audience'}
          </button>
        </div>
      </div>
      {err && <div className="text-pb-red text-xs mt-2">{err}</div>}
    </div>
  )
}

export default function SuperDirectoryAudiences() {
  const [segments, setSegments] = useState(null)
  const [opts, setOpts] = useState({ states: [], associations: [], countries: [] })
  const [editing, setEditing] = useState(null)
  const [error, setError] = useState('')
  const [ctx, setCtx] = useState(null)

  const load = useCallback(() => {
    api.commsListSegments().then(setSegments).catch(e => { setError(e.message); setSegments([]) })
  }, [])
  useEffect(() => {
    load()
    api.commsSegmentOptions().then(setOpts).catch(() => {})
    api.commsGetContext().then(setCtx).catch(() => {})
  }, [load])

  const onMarketing = !!ctx?.current?.is_marketing

  return (
    <AdminLayout>
      <div className="max-w-4xl">
        <div className="flex items-center justify-between gap-3 mb-1">
          <h1 className="font-display font-bold text-2xl text-pb-text">Directory audiences</h1>
          {!editing && (
            <button onClick={() => setEditing({})}
              className="px-3 py-1.5 rounded text-sm font-medium"
              style={{ background: 'var(--pb-accent)', color: '#0a0d14' }}>
              + New audience
            </button>
          )}
        </div>
        <p className="text-pb-faint text-sm mb-4 max-w-2xl">
          BetterCricket's own outreach audiences, built from what a prospect club has done — exported,
          emailed, opened, enquired, trialing, engagement score. Clubs never see these fields; their
          Audiences screen reads their own people and nothing else.
        </p>

        {!onMarketing && (
          <div className="pb-card p-3 mb-4 text-[13px] text-pb-dim">
            You are not acting as the marketing organisation, so these audiences resolve against whichever club
            you are currently in. Switch context from the{' '}
            <a href="/admin/super/marketing" className="underline" style={{ color: 'var(--pb-accent)' }}>Club Directory</a>.
          </div>
        )}

        {error && <div className="pb-card p-3 mb-4 text-pb-red text-sm">{error}</div>}

        {editing ? (
          <Editor initial={editing.id ? editing : null} opts={opts}
            onSaved={() => { setEditing(null); load() }}
            onCancel={() => setEditing(null)}
            onDeleted={() => { setEditing(null); load() }} />
        ) : segments == null ? (
          <div className="text-pb-faint text-sm">Loading…</div>
        ) : segments.length === 0 ? (
          <div className="pb-card p-8 text-center">
            <div className="text-pb-text font-medium mb-1">No directory audiences yet</div>
            <div className="text-pb-faint text-sm">Build a reusable audience from directory activity and club status.</div>
          </div>
        ) : (
          <div className="pb-card overflow-hidden">
            {segments.map((s, i) => (
              <div key={s.id}
                className={`flex items-center justify-between gap-4 px-5 py-3.5 hover:bg-pb-surface2 transition-colors ${i > 0 ? 'pb-hairline-t' : ''}`}>
                <button onClick={() => setEditing(s)} className="min-w-0 text-left flex-1">
                  <div className="text-pb-text text-sm truncate">{s.name}</div>
                  <div className="text-pb-faintest text-xs mt-0.5">
                    {(s.definition?.rules || []).length} condition{(s.definition?.rules || []).length === 1 ? '' : 's'}
                  </div>
                </button>
                <div className="flex items-center gap-3 shrink-0">
                  <a href={api.commsSegmentExportCsvUrl(s.id)} className="text-pb-faint text-xs hover:text-pb-text">Export CSV</a>
                  <button onClick={() => setEditing(s)} className="text-pb-faint text-xs hover:text-pb-text">Edit →</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
