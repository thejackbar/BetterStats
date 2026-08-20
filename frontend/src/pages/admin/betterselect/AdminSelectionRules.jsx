// BetterSelect → Setup → Selection rules.
//
// Where a club writes down what its competition requires, once, so a selector
// isn't holding the association handbook in their head on a Friday night: who
// is old enough for each division, how many overseas players may be named, how
// many overs a fourteen year old may bowl, what qualifies someone for a final.
//
// Nothing here has a built-in number. The date age is measured on is a setting
// (1 September, 1 January, the day of the match), grades are picked by NAME so
// a rule survives the season rollover, and each rule is the club's own call
// between a warning and a bar. See services/selection_rules.py.
//
// The BetterSelect settings that used to sit on the Club Settings page — the
// age display, the dormant-player window, the default side size — live at the
// bottom of this screen now, because they are the same person's job.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { PbSpinner } from '../../../lib/presskit'
import { Btn, Chip, Empty, Icon, Search, Segmented, Tag } from './ui'

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
  'August', 'September', 'October', 'November', 'December']

const SEVERITY_OPTS = [
  { value: 'warn', label: 'Warning' },
  { value: 'block', label: 'Blocking' },
]

const FIELD = 'w-full bg-pb-surface2 border border-pb-hairline rounded-lg px-3 py-2 text-pb-text text-[13.5px] focus:outline-none focus:border-pb-accent'
const LABEL = 'font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest block mb-1.5'
const HINT = 'text-[11.5px] leading-snug text-pb-faintest mt-1.5'

/* Sensible starting numbers per rule type — the SHAPE a club edits, never a
 * rule we invented for them. Nothing is saved until they press Add. */
const BLANK = {
  age: { min_age: 15, under_age: null },
  overseas: { max_in_xi: 1, max_in_round: null },
  bowling_workload: {
    applies_to: 'pace',
    max_share_of_overs: null,
    ladder: [{ under_age: 13, max_overs: 8, max_spell: 4, rest_minutes: 30 }],
  },
  finals_qualification: { min_games: 4, counts: 'club' },
  grade_cap: { max_games_above: 2, above: 'any' },
  fees: {},
  training: { min_sessions: 1, window_days: 21 },
  registration: {},
  rest: { max_games_in_window: 1, window_days: 2 },
  custom: { note: '', require_tick: false },
}

const num = (v) => (v === '' || v == null ? null : Number(v))

function Card({ children, className = '' }) {
  return <section className={`pb-card rounded-xl p-4 sm:p-5 ${className}`}>{children}</section>
}
function SectionHead({ title, sub, right }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
      <div className="min-w-0">
        <h2 className="font-display font-bold text-[15px] tracking-tight">{title}</h2>
        {sub && <p className="text-[12.5px] text-pb-dim mt-0.5 max-w-[62ch]">{sub}</p>}
      </div>
      {right}
    </div>
  )
}

/* ── How age is measured ──────────────────────────────────────────────────
 * The setting that stops this being one association's rulebook. */
function AgeBasisCard({ settings, onSave, canEdit }) {
  const [basis, setBasis] = useState(settings.age_basis || { basis: 'cutoff', month: 9, day: 1, year: 'season_start' })
  const [startMonth, setStartMonth] = useState(settings.season_start_month || 7)
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    setBasis(settings.age_basis || { basis: 'cutoff', month: 9, day: 1, year: 'season_start' })
    setStartMonth(settings.season_start_month || 7)
  }, [settings])

  const isCutoff = basis.basis !== 'match_date'
  const save = async () => {
    setSaving(true)
    try { await onSave({ age_basis: basis, season_start_month: Number(startMonth) }) }
    finally { setSaving(false) }
  }
  const example = isCutoff
    ? `A player's age is taken as at ${basis.day} ${MONTHS[(basis.month || 1) - 1]} of the year the season ${basis.year === 'season_end' ? 'ends' : 'started'}, so it doesn't change mid-season.`
    : "A player's age is taken on the day of each match, so a birthday mid-season changes what they're eligible for."

  return (
    <Card>
      <SectionHead title="How your association measures age"
        sub="Competitions don't agree on this, so it's yours to set. Everything the age rules below decide is worked out on this date." />
      <div className="flex flex-col gap-3">
        <Segmented value={isCutoff ? 'cutoff' : 'match_date'}
          onChange={(v) => setBasis(v === 'cutoff'
            ? { basis: 'cutoff', month: 9, day: 1, year: 'season_start' }
            : { basis: 'match_date' })}
          options={[{ value: 'cutoff', label: 'As at a set date' }, { value: 'match_date', label: 'On the day of the match' }]} />
        {isCutoff && (
          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <label className={LABEL}>Day</label>
              <input type="number" min="1" max="31" className={FIELD} value={basis.day ?? 1}
                onChange={(e) => setBasis((b) => ({ ...b, day: num(e.target.value) }))} />
            </div>
            <div>
              <label className={LABEL}>Month</label>
              <select className={FIELD} value={basis.month ?? 9}
                onChange={(e) => setBasis((b) => ({ ...b, month: Number(e.target.value) }))}>
                {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
              </select>
            </div>
            <div>
              <label className={LABEL}>Of which year</label>
              <select className={FIELD} value={basis.year || 'season_start'}
                onChange={(e) => setBasis((b) => ({ ...b, year: e.target.value }))}>
                <option value="season_start">The year the season started</option>
                <option value="season_end">The year the season ends</option>
              </select>
            </div>
          </div>
        )}
        <p className={HINT}>{example}</p>
        <div className="pt-3 pb-hairline-t">
          <label className={LABEL}>Your season starts in</label>
          <select className={`${FIELD} sm:w-[260px]`} value={startMonth}
            onChange={(e) => setStartMonth(Number(e.target.value))}>
            {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </select>
          <p className={HINT}>
            Only used for a fixture with no season attached to read. July for an Australian summer;
            April for a club playing through an English summer.
          </p>
        </div>
        {canEdit && (
          <div><Btn variant="primary" sm onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save'}</Btn></div>
        )}
      </div>
    </Card>
  )
}

/* ── Who a rule covers ────────────────────────────────────────────────────
 * Grades are ticked by NAME, which is what makes a rule standing: next
 * season's "1st Grade" is a different row, and a rule keyed on the row would
 * quietly stop applying the day it appeared. */
function ScopePicker({ scope, setScope, options }) {
  const [q, setQ] = useState('')
  const grades = (options.grades || []).filter((g) => !q || g.name.toLowerCase().includes(q.toLowerCase()))
  const toggle = (key, value) => setScope((s) => {
    const cur = s[key] || []
    return { ...s, [key]: cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value] }
  })
  const none = !(scope.grade_names?.length || scope.categories?.length || scope.formats?.length || scope.team_ids?.length)
  return (
    <div className="flex flex-col gap-3">
      <div>
        <label className={LABEL}>Grades</label>
        {(options.grades || []).length > 8 && (
          <div className="mb-2"><Search value={q} onChange={setQ} placeholder="Find a grade…" /></div>
        )}
        <div className="flex flex-wrap gap-1.5 max-h-[176px] overflow-auto pb-scroll">
          {grades.map((g) => (
            <Chip key={g.name} label={g.name} active={(scope.grade_names || []).includes(g.name)}
              onClick={() => toggle('grade_names', g.name)} />
          ))}
          {!grades.length && <span className="text-[12px] text-pb-faintest">No grades yet — this rule will cover every fixture.</span>}
        </div>
        <p className={HINT}>
          {none
            ? 'Nothing ticked, so this rule covers every fixture.'
            : 'Ticked by name, so the rule keeps working when next season’s grades arrive.'}
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className={LABEL}>…or a whole grade type</label>
          <div className="flex flex-wrap gap-1.5">
            {(options.categories || []).map((c) => (
              <Chip key={c.value} label={c.label} active={(scope.categories || []).includes(c.value)}
                onClick={() => toggle('categories', c.value)} />
            ))}
          </div>
        </div>
        <div>
          <label className={LABEL}>…or a match format</label>
          <div className="flex flex-wrap gap-1.5">
            {(options.formats || []).map((f) => (
              <Chip key={f.value} label={f.label} active={(scope.formats || []).includes(f.value)}
                onClick={() => toggle('formats', f.value)} />
            ))}
          </div>
        </div>
      </div>
      <div>
        <label className={LABEL}>Finals</label>
        <Segmented sm value={scope.finals || 'any'} onChange={(v) => setScope((s) => ({ ...s, finals: v }))}
          options={[{ value: 'any', label: 'Every match' }, { value: 'only', label: 'Finals only' },
                    { value: 'exclude', label: 'Not in finals' }]} />
        <p className={HINT}>A fixture counts as a final when its round says so — override it on the fixture itself if your association names them differently.</p>
      </div>
    </div>
  )
}

/* ── The numbers, per rule type ───────────────────────────────────────────── */
function ConfigFields({ kind, config, setConfig, ageBasisLabel }) {
  const set = (patch) => setConfig((c) => ({ ...c, ...patch }))
  if (kind === 'age') {
    return (
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className={LABEL}>Minimum age</label>
          <input type="number" min="5" max="99" className={FIELD} value={config.min_age ?? ''}
            placeholder="No minimum" onChange={(e) => set({ min_age: num(e.target.value) })} />
        </div>
        <div>
          <label className={LABEL}>Must be under</label>
          <input type="number" min="5" max="99" className={FIELD} value={config.under_age ?? ''}
            placeholder="No maximum" onChange={(e) => set({ under_age: num(e.target.value) })} />
        </div>
        <p className={`${HINT} sm:col-span-2`}>Measured {ageBasisLabel}. A player with no date of birth on their profile is never flagged.</p>
      </div>
    )
  }
  if (kind === 'overseas') {
    return (
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className={LABEL}>Allowed in one side</label>
          <input type="number" min="0" max="20" className={FIELD} value={config.max_in_xi ?? 1}
            onChange={(e) => set({ max_in_xi: num(e.target.value) })} />
        </div>
        <div>
          <label className={LABEL}>Across the club on a match day</label>
          <input type="number" min="0" max="40" className={FIELD} value={config.max_in_round ?? ''}
            placeholder="No limit" onChange={(e) => set({ max_in_round: num(e.target.value) })} />
        </div>
        <p className={`${HINT} sm:col-span-2`}>Counted from the overseas tick on each player's profile, live as you build the side.</p>
      </div>
    )
  }
  if (kind === 'bowling_workload') {
    const ladder = config.ladder || []
    const setRung = (i, patch) => set({ ladder: ladder.map((r, n) => (n === i ? { ...r, ...patch } : r)) })
    return (
      <div className="flex flex-col gap-3">
        <div>
          <label className={LABEL}>Applies to</label>
          <Segmented sm value={config.applies_to || 'pace'} onChange={(v) => set({ applies_to: v })}
            options={[{ value: 'pace', label: 'Pace and medium pace' }, { value: 'all', label: 'Every bowler' }]} />
        </div>
        <div>
          <label className={LABEL}>Age bands</label>
          <div className="flex flex-col gap-2">
            {ladder.map((r, i) => (
              <div key={i} className="grid gap-2 sm:grid-cols-[1fr_1fr_1fr_1fr_auto] items-end">
                <div>
                  <span className="text-[10.5px] text-pb-faintest">Under</span>
                  <input type="number" min="5" max="99" className={FIELD} value={r.under_age ?? ''}
                    onChange={(e) => setRung(i, { under_age: num(e.target.value) })} />
                </div>
                <div>
                  <span className="text-[10.5px] text-pb-faintest">Overs a day</span>
                  <input type="number" min="1" max="90" className={FIELD} value={r.max_overs ?? ''}
                    onChange={(e) => setRung(i, { max_overs: num(e.target.value) })} />
                </div>
                <div>
                  <span className="text-[10.5px] text-pb-faintest">Per spell</span>
                  <input type="number" min="1" max="40" className={FIELD} value={r.max_spell ?? ''}
                    onChange={(e) => setRung(i, { max_spell: num(e.target.value) })} />
                </div>
                <div>
                  <span className="text-[10.5px] text-pb-faintest">Rest (min)</span>
                  <input type="number" min="0" max="240" className={FIELD} value={r.rest_minutes ?? ''}
                    onChange={(e) => setRung(i, { rest_minutes: num(e.target.value) })} />
                </div>
                <Btn variant="ghost" sm icon="trash" title="Remove this band"
                  onClick={() => set({ ladder: ladder.filter((_, n) => n !== i) })} />
              </div>
            ))}
          </div>
          <div className="mt-2">
            <Btn variant="ghost" sm icon="plus"
              onClick={() => set({ ladder: [...ladder, { under_age: (ladder.at(-1)?.under_age || 11) + 2, max_overs: null, max_spell: null, rest_minutes: 30 }] })}>
              Add a band
            </Btn>
          </div>
        </div>
        <div>
          <label className={LABEL}>Share of the innings (optional)</label>
          <input type="number" min="1" max="100" className={`${FIELD} sm:w-[200px]`}
            value={config.max_share_of_overs != null ? Math.round(config.max_share_of_overs * 100) : ''}
            placeholder="e.g. 20" onChange={(e) => set({ max_share_of_overs: e.target.value ? Number(e.target.value) / 100 : null })} />
          <p className={HINT}>A percentage, if your association also caps a junior at a share of the scheduled overs.</p>
        </div>
        <p className={HINT}>Shown beside the player as a note. It never stops anyone being picked — the limit is on what you ask of them once they're out there.</p>
      </div>
    )
  }
  if (kind === 'finals_qualification') {
    return (
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className={LABEL}>Games needed</label>
          <input type="number" min="1" max="60" className={FIELD} value={config.min_games ?? 4}
            onChange={(e) => set({ min_games: num(e.target.value) })} />
        </div>
        <div>
          <label className={LABEL}>Counting games</label>
          <select className={FIELD} value={config.counts || 'club'} onChange={(e) => set({ counts: e.target.value })}>
            <option value="club">Anywhere for the club</option>
            <option value="this_or_higher">In this grade or higher</option>
            <option value="same_grade">In this grade only</option>
          </select>
        </div>
        <p className={`${HINT} sm:col-span-2`}>Counted from matches played and from sides you've named, so the last round still counts before it syncs.</p>
      </div>
    )
  }
  if (kind === 'grade_cap') {
    return (
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className={LABEL}>Games in a higher grade</label>
          <input type="number" min="1" max="60" className={FIELD} value={config.max_games_above ?? 2}
            onChange={(e) => set({ max_games_above: num(e.target.value) })} />
        </div>
        <div>
          <label className={LABEL}>Counting</label>
          <select className={FIELD} value={config.above || 'any'} onChange={(e) => set({ above: e.target.value })}>
            <option value="any">Any higher grade</option>
            <option value="immediate">The grade immediately above</option>
          </select>
        </div>
        <p className={`${HINT} sm:col-span-2`}>Reads your squads' order of seniority (Squads → sequence). A club that hasn't ordered its squads gets no answer, and the rule stays quiet.</p>
      </div>
    )
  }
  if (kind === 'training') {
    return (
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className={LABEL}>Sessions needed</label>
          <input type="number" min="1" max="30" className={FIELD} value={config.min_sessions ?? 1}
            onChange={(e) => set({ min_sessions: num(e.target.value) })} />
        </div>
        <div>
          <label className={LABEL}>In the last (days)</label>
          <input type="number" min="1" max="365" className={FIELD} value={config.window_days ?? 21}
            onChange={(e) => set({ window_days: num(e.target.value) })} />
        </div>
        <p className={`${HINT} sm:col-span-2`}>Read from Nets. If you ran no sessions in that window the rule says nothing about anyone.</p>
      </div>
    )
  }
  if (kind === 'rest') {
    return (
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className={LABEL}>Matches allowed</label>
          <input type="number" min="1" max="20" className={FIELD} value={config.max_games_in_window ?? 1}
            onChange={(e) => set({ max_games_in_window: num(e.target.value) })} />
        </div>
        <div>
          <label className={LABEL}>In any (days)</label>
          <input type="number" min="1" max="60" className={FIELD} value={config.window_days ?? 2}
            onChange={(e) => set({ window_days: num(e.target.value) })} />
        </div>
        <p className={`${HINT} sm:col-span-2`}>Counted from the sides you've named either side of this fixture.</p>
      </div>
    )
  }
  if (kind === 'custom') {
    return (
      <div className="flex flex-col gap-3">
        <div>
          <label className={LABEL}>The rule</label>
          <textarea className={`${FIELD} min-h-[72px]`} value={config.note || ''} maxLength={600}
            placeholder="e.g. Must have signed the code of conduct"
            onChange={(e) => set({ note: e.target.value })} />
        </div>
        <label className="flex items-start gap-2.5 cursor-pointer">
          <input type="checkbox" className="accent-pb-accent mt-0.5 shrink-0" checked={!!config.require_tick}
            onChange={(e) => set({ require_tick: e.target.checked })} />
          <span className="leading-tight">
            <span className="text-pb-text text-[13.5px]">Tick each player off by hand</span>
            <span className={`${HINT} block mt-0.5`}>Anyone not ticked is flagged. Leave it off and the rule is just a reminder on this screen.</span>
          </span>
        </label>
      </div>
    )
  }
  return <p className={HINT}>Nothing to set — this one reads what the club already holds.</p>
}

/* ── Add / edit one rule ─────────────────────────────────────────────────── */
function RuleEditor({ rule, kinds, options, ageBasisLabel, onCancel, onSave }) {
  const kind = rule.kind
  const meta = kinds.find((k) => k.kind === kind) || {}
  const [name, setName] = useState(rule.name || '')
  const [config, setConfig] = useState(rule.config || BLANK[kind] || {})
  const [scope, setScope] = useState(rule.scope || { finals: kind === 'finals_qualification' ? 'only' : 'any' })
  const [severity, setSeverity] = useState(rule.severity || 'warn')
  const [saving, setSaving] = useState(false)

  const submit = async () => {
    setSaving(true)
    try { await onSave({ kind, name: name.trim() || null, config, scope, severity }) }
    finally { setSaving(false) }
  }
  return (
    <Card className="border-pb-accent/40">
      <SectionHead title={rule.id ? `Edit — ${meta.label || kind}` : `New rule — ${meta.label || kind}`}
        sub={meta.blurb} />
      <div className="flex flex-col gap-4">
        <div>
          <label className={LABEL}>Call it</label>
          <input className={`${FIELD} sm:w-[360px]`} value={name} maxLength={80}
            placeholder={meta.label || ''} onChange={(e) => setName(e.target.value)} />
          <p className={HINT}>Your association's own wording reads better on the board than ours. Optional.</p>
        </div>
        <div className="pt-4 pb-hairline-t">
          <ConfigFields kind={kind} config={config} setConfig={setConfig} ageBasisLabel={ageBasisLabel} />
        </div>
        <div className="pt-4 pb-hairline-t">
          <label className={LABEL}>Which fixtures</label>
          <ScopePicker scope={scope} setScope={setScope} options={options} />
        </div>
        {!meta.info_only && (
          <div className="pt-4 pb-hairline-t">
            <label className={LABEL}>When a side breaks it</label>
            <Segmented sm value={severity} onChange={setSeverity} options={SEVERITY_OPTS} />
            <p className={HINT}>
              {severity === 'block'
                ? 'The side can’t be saved until it’s fixed. Grant a player an exception if your association has cleared them.'
                : 'The board says so and asks before saving. The selector still decides.'}
            </p>
          </div>
        )}
        {meta.needs && <p className={HINT}>Needs: {meta.needs}</p>}
        <div className="flex items-center gap-2 pt-1">
          <Btn variant="primary" sm onClick={submit} disabled={saving}>{saving ? 'Saving…' : rule.id ? 'Save changes' : 'Add rule'}</Btn>
          <Btn variant="ghost" sm onClick={onCancel}>Cancel</Btn>
        </div>
      </div>
    </Card>
  )
}

/* ── Per-player exceptions ───────────────────────────────────────────────── */
function ExceptionsPanel({ rule, onClose, toast }) {
  const [data, setData] = useState(null)
  const [q, setQ] = useState('')
  const load = useCallback(() => { api.bsRulePlayers(rule.id).then(setData).catch((e) => toast.error(e.message)) }, [rule.id, toast])
  useEffect(() => { load() }, [load])

  const set = async (playerId, state) => {
    let note = null
    if (state) {
      note = window.prompt(state === 'cleared'
        ? 'Why are they cleared? (a permit number, a date — optional)'
        : 'Why are they ineligible? (optional)') ?? null
    }
    try {
      await api.bsSetRulePlayer(rule.id, playerId, state, note)
      load()
    } catch (e) { toast.error(e.message) }
  }
  const players = (data?.players || []).filter((p) => !q || p.name.toLowerCase().includes(q.toLowerCase()))
  return (
    <Card className="border-pb-accent/40">
      <SectionHead title={`Exceptions — ${rule.name}`}
        sub="An association permit, a clearance, or someone ruled out for this one rule. Everything else about them is untouched."
        right={<Btn variant="ghost" sm icon="close" onClick={onClose}>Close</Btn>} />
      <div className="mb-3"><Search value={q} onChange={setQ} placeholder="Find a player…" /></div>
      {!data ? <PbSpinner message="Loading players…" /> : (
        <div className="flex flex-col gap-1 max-h-[420px] overflow-auto pb-scroll">
          {players.map((p) => (
            <div key={p.id} className="flex items-center gap-3 py-1.5 px-2 rounded-lg hover:bg-pb-surface2">
              <span className="flex-1 min-w-0 text-[13.5px] truncate">
                {p.name}
                {p.note && <span className="text-[11.5px] text-pb-faintest"> · {p.note}</span>}
              </span>
              <Segmented sm value={p.state || ''} onChange={(v) => set(p.id, v || null)}
                options={[{ value: '', label: 'Normal' }, { value: 'cleared', label: 'Cleared' },
                          { value: 'blocked', label: 'Ineligible' }]} />
            </div>
          ))}
          {!players.length && <Empty>No players match.</Empty>}
        </div>
      )}
    </Card>
  )
}

/* ── One rule in the list ────────────────────────────────────────────────── */
function RuleRow({ rule, canEdit, onEdit, onExceptions, onToggle, onSeverity, onDelete }) {
  return (
    <div className={`rounded-xl border px-4 py-3 flex flex-col gap-2 ${rule.enabled ? 'border-pb-hairline bg-pb-surface2/40' : 'border-pb-hairline opacity-60'}`}>
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-display font-semibold text-[14.5px]">{rule.name}</span>
            <Tag tone="faint">{rule.label}</Tag>
            {rule.severity === 'block' && <Tag tone="red" title="A side breaking this can't be saved">BLOCKS</Tag>}
            {rule.severity === 'info' && <Tag tone="faint" title="Shown as a note, never a breach">NOTE</Tag>}
            {rule.exception_count > 0 && (
              <Tag tone="amber" title="Players with an exception to this rule">{rule.exception_count} exc</Tag>
            )}
          </div>
          <div className="text-[12.5px] text-pb-dim mt-1">{rule.summary}</div>
          <div className="text-[11.5px] text-pb-faintest mt-0.5">{rule.scope_summary}</div>
        </div>
        {/* No shrink-0 on the action cluster: it has to be allowed to shrink so
            it wraps onto its own line on a phone rather than pushing the page
            sideways. The buttons inside wrap on their own. */}
        {canEdit && (
          <div className="flex flex-wrap items-center gap-1.5">
            {rule.severity !== 'info' && (
              <Segmented sm value={rule.severity} onChange={(v) => onSeverity(rule, v)} options={SEVERITY_OPTS} />
            )}
            <Btn variant="ghost" sm onClick={() => onToggle(rule)}>{rule.enabled ? 'Turn off' : 'Turn on'}</Btn>
            <Btn variant="ghost" sm icon="settings" onClick={() => onEdit(rule)}>Edit</Btn>
            <Btn variant="ghost" sm onClick={() => onExceptions(rule)}>Exceptions</Btn>
            <Btn variant="danger" sm icon="trash" title="Delete this rule" onClick={() => onDelete(rule)} />
          </div>
        )}
      </div>
    </div>
  )
}

/* ── What the board shows (the settings that moved here) ─────────────────── */
function BoardSettingsCard({ settings, onSave, canEdit }) {
  const [form, setForm] = useState(settings)
  const [saving, setSaving] = useState(false)
  useEffect(() => setForm(settings), [settings])
  const save = async () => {
    setSaving(true)
    try {
      await onSave({
        select_show_age: !!form.select_show_age,
        select_show_age_under: form.select_show_age_under ?? null,
        dormancy_months: Number(form.dormancy_months),
        default_team_size: Number(form.default_team_size),
      })
    } finally { setSaving(false) }
  }
  return (
    <Card>
      <SectionHead title="What the board shows"
        sub="The rest of BetterSelect's own settings. They used to live under Club Settings, which is a long way from the person who needs them." />
      <div className="flex flex-col gap-4">
        <div>
          <label className="flex items-start gap-2.5 cursor-pointer">
            <input type="checkbox" className="accent-pb-accent mt-0.5 shrink-0" checked={!!form.select_show_age}
              onChange={(e) => setForm((f) => ({ ...f, select_show_age: e.target.checked }))} />
            <span className="leading-tight">
              <span className="text-pb-text text-[13.5px]">Show a player's age beside their name</span>
              <span className={`${HINT} block mt-0.5`}>
                Worked out from the date of birth on their profile, which you fill in yourself. Never shown
                on your public website. With an age rule running, the age shown is the one your competition
                counts.
              </span>
            </span>
          </label>
          {form.select_show_age && (
            <div className="mt-3 pl-7">
              <label className={LABEL}>Show it for</label>
              <select className={`${FIELD} sm:w-[280px]`} value={form.select_show_age_under ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, select_show_age_under: e.target.value ? Number(e.target.value) : null }))}>
                <option value="">Every player</option>
                {[13, 14, 15, 16, 17, 18, 19, 21].map((n) => <option key={n} value={n}>Players under {n} only</option>)}
              </select>
              <p className={HINT}>Anyone at or over that age shows no age at all — their birthday never leaves their profile.</p>
            </div>
          )}
        </div>
        <div className="grid gap-3 sm:grid-cols-2 pt-4 pb-hairline-t">
          <div>
            <label className={LABEL}>Dormant player window</label>
            <select className={FIELD} value={form.dormancy_months ?? 24}
              onChange={(e) => setForm((f) => ({ ...f, dormancy_months: Number(e.target.value) }))}>
              {[[6, '6 months'], [12, '1 year'], [18, '18 months'], [24, '2 years'], [36, '3 years'], [60, '5 years']]
                .map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <p className={HINT}>Nobody who hasn't played inside this window is offered by default.</p>
          </div>
          <div>
            <label className={LABEL}>Default side size</label>
            <select className={FIELD} value={form.default_team_size ?? 11}
              onChange={(e) => setForm((f) => ({ ...f, default_team_size: Number(e.target.value) }))}>
              {[[11, '11'], [12, '12'], [13, '13'], [0, 'No limit']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <p className={HINT}>What a new team sheet opens on.</p>
          </div>
        </div>
        {canEdit && (
          <div><Btn variant="primary" sm onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save'}</Btn></div>
        )}
      </div>
    </Card>
  )
}

/* ── The screen ──────────────────────────────────────────────────────────── */
export default function AdminSelectionRules() {
  const { hasCapability } = useAuth()
  const toast = useToast()
  const canEdit = hasCapability(CAP.MANAGE_SELECTIONS)
  const [data, setData] = useState(null)
  const [editing, setEditing] = useState(null)      // {kind, ...rule} or null
  const [exceptions, setExceptions] = useState(null)
  const [adding, setAdding] = useState(false)

  const load = useCallback(() => {
    api.bsRules().then(setData).catch((e) => { toast.error(e.message); setData({ rules: [], kinds: [], options: {} }) })
  }, [toast])
  useEffect(() => { load() }, [load])

  const saveSettings = async (patch) => {
    try {
      const s = await api.bsRuleSettings(patch)
      setData((d) => ({ ...d, settings: s }))
      toast.success('Saved')
    } catch (e) { toast.error(e.message) }
  }
  const saveRule = async (body) => {
    try {
      if (editing?.id) await api.bsUpdateRule(editing.id, body)
      else await api.bsCreateRule(body)
      setEditing(null); setAdding(false); load()
      toast.success(editing?.id ? 'Rule updated' : 'Rule added')
    } catch (e) { toast.error(e.message) }
  }
  const patchRule = async (rule, patch) => {
    try { await api.bsUpdateRule(rule.id, patch); load() }
    catch (e) { toast.error(e.message) }
  }
  const deleteRule = async (rule) => {
    if (!window.confirm(`Delete "${rule.name}"?\n\nAny exceptions you granted for it go too. Turning it off instead keeps everything.`)) return
    try { await api.bsDeleteRule(rule.id); load(); toast.success('Rule deleted') }
    catch (e) { toast.error(e.message) }
  }
  const seed = async () => {
    try {
      const r = await api.bsSeedStarterRules()
      load()
      toast.success(r.added ? 'Added the junior bowling limits — edit them to match your association' : 'You already have a bowling rule')
    } catch (e) { toast.error(e.message) }
  }

  const rules = data?.rules || []
  const kinds = data?.kinds || []
  const options = data?.options || {}
  const ageBasisLabel = data?.settings?.age_basis_label || 'as at 1 September'
  const grouped = useMemo(() => rules.filter((r) => r.enabled).length, [rules])

  if (data === null) {
    return <BetterSelectLayout title="Selection rules"><PbSpinner message="Loading rules…" /></BetterSelectLayout>
  }

  return (
    <BetterSelectLayout title="Selection rules"
      caption={`${rules.length} rule${rules.length === 1 ? '' : 's'} · ${grouped} on`}>
      <div className="flex flex-col gap-4 max-w-[980px]">
        <Card>
          <SectionHead title="Your association's rules, written down once"
            sub="Age limits, overseas players, bowling workloads, what qualifies someone for a final. BetterSelect checks each side against them as you pick it, and shows nothing at all for the rules you haven't set." />
          <p className="text-[12.5px] text-pb-dim">
            Every number here is yours. Nothing is assumed about your competition, and a rule you turn
            off takes its badge, its filter and its warning off the board with it.
          </p>
        </Card>

        <AgeBasisCard settings={data.settings || {}} onSave={saveSettings} canEdit={canEdit} />

        <Card>
          <SectionHead title="Rules" sub={rules.length ? null : 'Nothing set yet — add the ones your competition actually has.'}
            right={canEdit && !adding && !editing ? (
              <div className="flex items-center gap-2">
                {!rules.length && <Btn variant="ghost" sm icon="bolt" onClick={seed}>Add junior bowling limits</Btn>}
                <Btn variant="primary" sm icon="plus" onClick={() => setAdding(true)}>Add a rule</Btn>
              </div>
            ) : null} />

          {adding && (
            <div className="mb-4 grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))' }}>
              {kinds.map((k) => (
                <button key={k.kind} type="button"
                  onClick={() => { setEditing({ kind: k.kind }); setAdding(false) }}
                  className="text-left rounded-xl border border-pb-hairline2 hover:border-pb-accent/50 bg-pb-surface2/40 px-3.5 py-3 transition">
                  <div className="font-display font-semibold text-[13.5px]">{k.label}</div>
                  <div className="text-[11.5px] text-pb-dim mt-0.5 leading-snug">{k.blurb}</div>
                </button>
              ))}
              <div className="col-span-full"><Btn variant="ghost" sm onClick={() => setAdding(false)}>Cancel</Btn></div>
            </div>
          )}

          {editing && (
            <div className="mb-4">
              <RuleEditor rule={editing} kinds={kinds} options={options} ageBasisLabel={ageBasisLabel}
                onCancel={() => setEditing(null)} onSave={saveRule} />
            </div>
          )}

          {exceptions && (
            <div className="mb-4">
              <ExceptionsPanel rule={exceptions} toast={toast} onClose={() => { setExceptions(null); load() }} />
            </div>
          )}

          <div className="flex flex-col gap-2">
            {rules.map((r) => (
              <RuleRow key={r.id} rule={r} canEdit={canEdit}
                onEdit={(rule) => { setEditing(rule); setAdding(false) }}
                onExceptions={setExceptions}
                onToggle={(rule) => patchRule(rule, { enabled: !rule.enabled })}
                onSeverity={(rule, v) => patchRule(rule, { severity: v })}
                onDelete={deleteRule} />
            ))}
            {!rules.length && !adding && !editing && (
              <Empty>No rules yet. Everything on the selection board reads exactly as it does now until you add one.</Empty>
            )}
          </div>
        </Card>

        <BoardSettingsCard settings={data.settings || {}} onSave={saveSettings} canEdit={canEdit} />

        <p className="text-[11.5px] text-pb-faintest">
          A player's date of birth and overseas status live on their profile —{' '}
          <Link to="/admin/betterselect/players" className="text-pb-accent hover:underline">BetterSelect → Players</Link>.
        </p>
      </div>
    </BetterSelectLayout>
  )
}
