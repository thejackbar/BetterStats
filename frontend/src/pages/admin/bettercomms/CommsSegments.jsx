import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from '../../../lib/api'
import BetterCommsLayout from '../../../components/admin/BetterCommsLayout'
import { ContactDetailModal } from './CommsContacts'
import { AudiencePanel } from './audience'

// Whitelisted segment fields (mirrors services/comms_segments.py). Each rule is
// {field, op, value}; rules are ANDed. Stat / role / availability fields read the
// linked player, so they narrow to the playing squad automatically. Fields whose
// `optionsKey` is set pull their dropdown values from /segments/options (the
// club's real roles / teams), so we never guess vocab.
const STAT_OPS = [['gte', 'at least'], ['lte', 'at most']]
const IS_OP = [['eq', 'is']]
const YESNO = [['yes', 'yes'], ['no', 'no']]
// The six modules a prospect can trial / request, by entitlement key.
const MODULE_OPTS = [
  ['core', 'BetterStats'], ['select', 'BetterSelect'], ['socials', 'BetterSocials'],
  ['admin', 'BetterAdmin'], ['iq', 'BetterIQ'], ['fantasy', 'BetterFantasyCricket'],
]

// The club / player field set — a normal club's members and their cricket data.
const CLUB_FIELD_DEFS = {
  tag: { label: 'Has tag', input: 'text', ops: [['has', 'is']] },
  source: {
    label: 'Source', input: 'select', ops: IS_OP,
    options: [['player', 'A player'], ['member', 'A fee member'], ['import', 'Imported'], ['manual', 'Added manually']],
  },
  role: { label: 'Player role', input: 'select', ops: IS_OP, optionsKey: 'roles' },
  gender: { label: 'Gender', input: 'select', ops: IS_OP, optionsKey: 'genders' },
  squad_team: { label: 'Squad / team', input: 'select', ops: IS_OP, optionsKey: 'teams' },
  availability: {
    label: 'Availability', input: 'select', ops: IS_OP,
    options: [['available', 'available for an upcoming game'], ['not_set', 'no availability set']],
  },
  matches_this_season: { label: 'Matches this season', input: 'number', ops: STAT_OPS },
  runs_this_season: { label: 'Runs this season', input: 'number', ops: STAT_OPS },
  wickets_this_season: { label: 'Wickets this season', input: 'number', ops: STAT_OPS },
  catches_this_season: { label: 'Catches this season', input: 'number', ops: STAT_OPS },
  fifties_this_season: { label: 'Fifties this season', input: 'number', ops: STAT_OPS },
  hundreds_this_season: { label: 'Hundreds this season', input: 'number', ops: STAT_OPS },
  five_wickets_this_season: { label: '5-wicket hauls this season', input: 'number', ops: STAT_OPS },
}

// The directory field set — a prospect club / its officer and what they've done.
// Only offered in the BetterCricket Clubs Directory comms context. Each reads data
// we already hold (exports, sent/open/click events, enquiries, club + customer
// status), so a segment can target who HAS or HASN'T done something today.
const DIRECTORY_FIELD_DEFS = {
  tag: { label: 'Has tag', input: 'text', ops: [['has', 'is']] },
  exported: { label: 'Exported from directory', input: 'select', ops: IS_OP, options: YESNO },
  emailed: { label: 'Emailed via BetterComms', input: 'select', ops: IS_OP, options: YESNO },
  opened: { label: 'Opened an email', input: 'select', ops: IS_OP, options: YESNO },
  clicked: { label: 'Clicked an email link', input: 'select', ops: IS_OP, options: YESNO },
  enquired: { label: 'Sent a Contact Us enquiry', input: 'select', ops: IS_OP, options: YESNO },
  visited_page: {
    label: 'Visited a page', input: 'multi', ops: [['eq', 'is any of']],
    options: [
      ['stats', 'BetterStats page'], ['select', 'BetterSelect page'], ['socials', 'BetterSocials page'],
      ['admin', 'BetterAdmin page'], ['betteriq', 'BetterIQ page'], ['fantasy', 'BetterFantasyCricket page'],
      ['pricing', 'Pricing page'], ['compare', 'Compare page'], ['about', 'About page'],
      ['faq', 'FAQ page'], ['contact', 'Contact Us page'], ['any', 'Any page'],
    ],
  },
  is_trialing: { label: 'Is trialing module', input: 'multi', ops: [['eq', 'is any of']], options: MODULE_OPTS },
  requested_trial: { label: 'Requested a trial', input: 'multi', ops: [['eq', 'is any of']], options: MODULE_OPTS },
  had_demo: {
    label: 'Had a demo', input: 'multi', ops: [['eq', 'is any of']],
    options: [['in_trial', 'In a trial'], ['trial_expired', 'Trial has expired'], ['customer', 'Is now a customer']],
  },
  customer_status: {
    label: 'Customer status', input: 'select', ops: IS_OP,
    options: [['none', 'not a customer'], ['trial', 'on a trial'], ['active', 'active customer'], ['lapsed', 'lapsed / paused']],
  },
  directory_status: {
    label: 'Directory status', input: 'select', ops: IS_OP,
    options: [['new', 'new'], ['enriched', 'enriched'], ['contacted', 'contacted'], ['onboarded', 'onboarded'], ['suppressed', 'suppressed']],
  },
  club_state: { label: 'Club state', input: 'select', ops: IS_OP, optionsKey: 'states' },
  association: { label: 'Association', input: 'select', ops: IS_OP, optionsKey: 'associations' },
}

function defsFor(opts) {
  return opts?.context === 'directory' ? DIRECTORY_FIELD_DEFS : CLUB_FIELD_DEFS
}

function newRule(defs) {
  const first = Object.keys(defs)[0]
  return { field: first, op: defs[first].ops[0][0], value: '' }
}

// Resolve a field's dropdown options from the fetched club/directory options.
function optionsFor(def, opts) {
  if (def.options) return def.options
  if (def.optionsKey === 'roles') return (opts.roles || []).map(r => [r, r])
  if (def.optionsKey === 'genders') return opts.genders || []
  if (def.optionsKey === 'teams') return (opts.teams || []).map(t => [t.id, t.name])
  if (def.optionsKey === 'states') return (opts.states || []).map(s => [s, s])
  if (def.optionsKey === 'associations') return (opts.associations || []).map(a => [a, a])
  return []
}

// Multi-select rule value: pick one or more [value, label] options. The rule
// value is stored as an array of the chosen value keys.
function MultiSelectValues({ options, selected, onChange }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    const k = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', h)
    document.addEventListener('keydown', k)
    return () => { document.removeEventListener('mousedown', h); document.removeEventListener('keydown', k) }
  }, [])
  const sel = Array.isArray(selected) ? selected : []
  const toggle = (v) => onChange(sel.includes(v) ? sel.filter(x => x !== v) : [...sel, v])
  const labels = options.filter(([v]) => sel.includes(v)).map(([, l]) => l)
  return (
    <div className="relative" ref={ref}>
      <button type="button" onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1.5 bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text text-sm max-w-[240px]">
        <span className="truncate">{labels.length ? labels.join(', ') : 'choose…'}</span>
        {sel.length > 0 && (
          <span role="button" title="Clear" className="text-pb-faint hover:text-pb-red"
            onClick={(e) => { e.stopPropagation(); onChange([]) }}>✕</span>
        )}
        <span className="text-pb-faint">▾</span>
      </button>
      {open && (
        <div className="absolute z-30 mt-1 w-60 max-h-72 overflow-auto rounded-lg border pb-hairline bg-pb-surface2 shadow-lg p-2">
          {options.map(([v, l]) => (
            <label key={v} className="flex items-center gap-2 px-1 py-0.5 text-sm text-pb-text hover:bg-pb-surface rounded cursor-pointer">
              <input type="checkbox" className="accent-pb-accent" checked={sel.includes(v)} onChange={() => toggle(v)} />
              <span className="truncate">{l}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  )
}

function RuleRow({ rule, defs, opts, onChange, onRemove }) {
  const def = defs[rule.field] || defs[Object.keys(defs)[0]]
  const keys = Object.keys(defs)
  return (
    <div className="flex flex-wrap items-center gap-2 py-1.5">
      <select value={rule.field}
        onChange={e => {
          const nd = defs[e.target.value]
          onChange({ field: e.target.value, op: nd.ops[0][0], value: '' })
        }}
        className="px-2 py-1.5 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm">
        {keys.map(k => <option key={k} value={k}>{defs[k].label}</option>)}
      </select>
      <select value={rule.op} onChange={e => onChange({ ...rule, op: e.target.value })}
        className="px-2 py-1.5 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm">
        {def.ops.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
      {def.input === 'multi' ? (
        <MultiSelectValues options={optionsFor(def, opts)}
          selected={Array.isArray(rule.value) ? rule.value : (rule.value ? [rule.value] : [])}
          onChange={(vals) => onChange({ ...rule, value: vals })} />
      ) : def.input === 'select' ? (
        <select value={rule.value} onChange={e => onChange({ ...rule, value: e.target.value })}
          className="px-2 py-1.5 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm max-w-[200px]">
          <option value="">choose…</option>
          {optionsFor(def, opts).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      ) : (
        <input value={rule.value} onChange={e => onChange({ ...rule, value: e.target.value })}
          type={def.input === 'number' ? 'number' : 'text'}
          placeholder={def.input === 'number' ? '0' : 'e.g. Committee'}
          className="px-2 py-1.5 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm w-32" />
      )}
      <button onClick={onRemove} className="text-pb-faint hover:text-pb-red text-sm px-1">✕</button>
    </div>
  )
}

function Editor({ initial, opts, onSaved, onCancel, onDeleted }) {
  const defs = defsFor(opts)
  const [name, setName] = useState(initial?.name || '')
  const [rules, setRules] = useState(initial?.definition?.rules?.length ? initial.definition.rules : [newRule(defs)])
  const [count, setCount] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [showAudience, setShowAudience] = useState(false)
  const [audience, setAudience] = useState(null)
  const [audienceLoading, setAudienceLoading] = useState(false)
  const [detailId, setDetailId] = useState(null)

  const definition = { match: 'all', rules: rules.filter(r => String(r.value).trim() !== '') }
  const defKey = JSON.stringify(rules)

  useEffect(() => {
    let live = true
    const t = setTimeout(() => {
      api.commsPreviewSegment(definition).then(r => { if (live) setCount(r.count) }).catch(() => { if (live) setCount(null) })
    }, 350)
    return () => { live = false; clearTimeout(t) }
  }, [defKey]) // eslint-disable-line react-hooks/exhaustive-deps

  // When the audience preview is open, resolve the full matching set (debounced).
  useEffect(() => {
    if (!showAudience) return
    let live = true
    setAudienceLoading(true)
    const t = setTimeout(() => {
      api.commsResolveSegment(definition)
        .then(r => { if (live) { setAudience(r); setAudienceLoading(false) } })
        .catch(() => { if (live) { setAudience({ count: 0, contacts: [] }); setAudienceLoading(false) } })
    }, 400)
    return () => { live = false; clearTimeout(t) }
  }, [defKey, showAudience]) // eslint-disable-line react-hooks/exhaustive-deps

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
          <RuleRow key={i} rule={r} defs={defs} opts={opts}
            onChange={nr => setRules(rs => rs.map((x, j) => j === i ? nr : x))}
            onRemove={() => setRules(rs => rs.length > 1 ? rs.filter((_, j) => j !== i) : rs)} />
        ))}
      </div>
      <button onClick={() => setRules(rs => [...rs, newRule(defs)])}
        className="text-xs text-pb-faint hover:text-pb-text mb-3">+ Add condition</button>

      <div className="flex items-center justify-between gap-3 pt-3 pb-hairline-t">
        <div className="text-sm text-pb-text flex items-center gap-3">
          <span>
            {count == null ? <span className="text-pb-faint">Counting…</span>
              : <><span className="font-medium" style={{ color: 'var(--pb-accent)' }}>{count}</span> matching contact{count === 1 ? '' : 's'}</>}
          </span>
          <button onClick={() => setShowAudience(s => !s)} className="text-xs text-pb-faint hover:text-pb-accent">
            {showAudience ? 'Hide audience' : 'Preview audience'}
          </button>
        </div>
        <div className="flex items-center gap-2">
          {initial?.id && (
            <a href={api.commsSegmentExportCsvUrl(initial.id)} className="text-sm text-pb-faint hover:text-pb-text px-2" title="Export this segment's current audience to CSV">Export CSV</a>
          )}
          {initial?.id && <button onClick={remove} disabled={busy} className="text-sm text-pb-faint hover:text-pb-red px-2">Delete</button>}
          <button onClick={onCancel} className="text-sm text-pb-faint hover:text-pb-text px-2">Cancel</button>
          <button onClick={save} disabled={busy}
            className="px-3 py-1.5 rounded text-sm font-medium text-white disabled:opacity-60" style={{ background: 'var(--pb-accent)' }}>
            {busy ? 'Saving…' : 'Save segment'}
          </button>
        </div>
      </div>
      {err && <div className="text-pb-red text-xs mt-2">{err}</div>}

      {showAudience && (
        <div className="mt-4 pt-4 pb-hairline-t">
          <div className="text-pb-text text-sm font-semibold uppercase tracking-wide2 mb-3">Audience preview</div>
          <AudiencePanel contacts={audience?.contacts || []} total={audience?.count}
            loading={audienceLoading} csvName={name || 'segment'} onRowClick={setDetailId} />
        </div>
      )}

      {detailId && <ContactDetailModal id={detailId} onClose={() => setDetailId(null)} onSaved={() => {}} />}
    </div>
  )
}

export default function CommsSegments() {
  const [segments, setSegments] = useState(null)
  const [opts, setOpts] = useState({ context: 'club', roles: [], genders: [], teams: [] })
  const [editing, setEditing] = useState(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api.commsListSegments().then(setSegments).catch(e => { setError(e.message); setSegments([]) })
  }, [])
  useEffect(() => {
    load()
    api.commsSegmentOptions().then(setOpts).catch(() => {})
  }, [load])

  const onSaved = () => { setEditing(null); load() }
  const onDeleted = () => { setEditing(null); load() }

  const isDirectory = opts.context === 'directory'

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
        {isDirectory
          ? ' Target prospect clubs by what they\'ve done, like "emailed but not opened", "sent a Contact Us enquiry", or "not a customer yet".'
          : ' Mix contact tags with this season\'s cricket data, like "played at least 5 matches", "in the women\'s squad", or "available for an upcoming game".'}
      </div>

      {editing ? (
        <Editor initial={editing.id ? editing : null} opts={opts} onSaved={onSaved} onCancel={() => setEditing(null)} onDeleted={onDeleted} />
      ) : segments == null ? (
        <div className="text-pb-faint text-sm">Loading…</div>
      ) : segments.length === 0 ? (
        <div className="pb-card p-8 text-center">
          <div className="text-pb-text font-medium mb-1">No segments yet</div>
          <div className="text-pb-faint text-sm mb-4">
            {isDirectory ? 'Build a reusable audience from directory activity and club status.' : 'Build a reusable audience from tags and cricket stats.'}
          </div>
          <button onClick={() => setEditing({})}
            className="px-4 py-2 rounded text-sm font-medium text-white" style={{ background: 'var(--pb-accent)' }}>
            + New segment
          </button>
        </div>
      ) : (
        <div className="pb-card overflow-hidden">
          {segments.map((s, i) => (
            <div key={s.id}
              className={`flex items-center justify-between gap-4 px-5 py-3.5 hover:bg-pb-surface2 transition-colors ${i > 0 ? 'pb-hairline-t' : ''}`}>
              <button onClick={() => setEditing(s)} className="min-w-0 text-left flex-1">
                <div className="text-pb-text text-sm truncate">{s.name}</div>
                <div className="text-pb-faintest text-xs mt-0.5">{(s.definition?.rules || []).length} condition{(s.definition?.rules || []).length === 1 ? '' : 's'}</div>
              </button>
              <div className="flex items-center gap-3 shrink-0">
                <a href={api.commsSegmentExportCsvUrl(s.id)} className="text-pb-faint text-xs hover:text-pb-text" title="Export this segment's current audience to CSV">Export CSV</a>
                <button onClick={() => setEditing(s)} className="text-pb-faint text-xs hover:text-pb-text">Edit →</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </BetterCommsLayout>
  )
}
