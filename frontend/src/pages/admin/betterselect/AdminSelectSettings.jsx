// BetterSelect → Setup → Settings.
//
// The small switches that change how BetterSelect looks and behaves, in one place
// instead of on the screens they affect. Today: what the club calls the two
// weeks of a two-day game, the colours that mark a player
// who is free for one weekend of a two-day game and away for the other ("half
// available"), how far back a player may have last played to be listed, starting
// filters for each team ("Team defaults"), whether junior grades are shown, and
// whether Maybe is offered.
// Selection rules (age limits, side size, emails) stay on their own screen.
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import usePersistedState from '../../../lib/usePersistedState'
import { setAllowMaybe, setHalfColours, setSelectConfig, setWeekNames, useHalfColours } from '../../../lib/useAvailabilityConfig'
import { DEFAULT_WEEK_NAMES } from '../../../lib/availability'
import { PbSpinner } from '../../../lib/presskit'
import { Btn, Dot, Segmented } from './ui'

const DEFAULTS = { w1: '#a855f7', w2: '#06b6d4' }

function Card({ children }) {
  return <section className="pb-card rounded-xl p-4 sm:p-5">{children}</section>
}
function Head({ title, sub }) {
  return (
    <div className="mb-3">
      <h2 className="font-display font-bold text-[15px] tracking-tight">{title}</h2>
      {sub && <p className="text-[12.5px] text-pb-dim mt-0.5 max-w-[66ch]">{sub}</p>}
    </div>
  )
}
function Row({ label, hint, children }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 py-2.5 border-t border-pb-hairline first:border-t-0">
      <div className="min-w-0 flex-1 basis-[260px]">
        <div className="text-[13.5px] font-semibold">{label}</div>
        {hint && <div className="text-[12px] text-pb-faint mt-0.5 max-w-[60ch]">{hint}</div>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  )
}

// One half-available colour: a picker, the hex, a live sample, and Reset.
function HalfColour({ weekKey, title, hint, value, onChange, disabled }) {
  const [text, setText] = useState(value)
  useEffect(() => setText(value), [value])
  const valid = /^#[0-9a-f]{6}$/i.test(text.trim())
  return (
    <Row label={title} hint={hint}>
      <div className="flex items-center gap-2.5" data-half-colour={weekKey}>
        <span className="inline-flex items-center gap-1.5 text-[12.5px] text-pb-dim min-w-[118px]">
          <span className="inline-block rounded-full" style={{ width: 11, height: 11, background: valid ? text : value }} data-half-sample={weekKey} />
          {title.replace('Available for ', '')}
        </span>
        <input type="color" value={value} disabled={disabled} aria-label={`${title} colour`}
          onChange={(e) => onChange(e.target.value)}
          className="h-8 w-10 rounded border border-pb-hairline bg-transparent cursor-pointer disabled:opacity-40" />
        <input type="text" value={text} disabled={disabled} spellCheck={false} maxLength={7} aria-label={`${title} hex`}
          onChange={(e) => { setText(e.target.value); if (/^#[0-9a-f]{6}$/i.test(e.target.value.trim())) onChange(e.target.value.trim().toLowerCase()) }}
          className={`w-[92px] bg-pb-surface2 border rounded-lg px-2 py-1.5 font-mono text-[12.5px] focus:outline-none focus:border-pb-accent ${valid ? 'border-pb-hairline' : 'border-pb-red'}`} />
        <Btn sm variant="ghost" onClick={() => onChange(DEFAULTS[weekKey])} disabled={disabled || value === DEFAULTS[weekKey]}>Reset</Btn>
      </div>
    </Row>
  )
}

// What the club calls one week of a two-day game. Saved when the box is left or
// Enter is pressed; blank goes back to the default (W1 / W2).
function WeekName({ weekKey, label, hint, value, onSave, disabled }) {
  const [text, setText] = useState(value)
  useEffect(() => setText(value), [value])
  const commit = () => {
    const next = text.replace(/\s+/g, ' ').trim().slice(0, 10) || DEFAULT_WEEK_NAMES[weekKey]
    setText(next)
    if (next !== value) onSave(next)
  }
  return (
    <Row label={label} hint={hint}>
      <div className="flex items-center gap-2.5" data-week-name={weekKey}>
        <input type="text" value={text} disabled={disabled} maxLength={10} aria-label={label}
          onChange={(e) => setText(e.target.value)} onBlur={commit}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); e.currentTarget.blur() } }}
          className="w-[110px] bg-pb-surface2 border border-pb-hairline rounded-lg px-2 py-1.5 font-mono text-[12.5px] focus:outline-none focus:border-pb-accent" />
        <Btn sm variant="ghost" onClick={() => onSave(DEFAULT_WEEK_NAMES[weekKey])} disabled={disabled || value === DEFAULT_WEEK_NAMES[weekKey]}>Reset</Btn>
      </div>
    </Row>
  )
}

const SELECTION_WINDOWS = [[0, 'Any time'], [-1, 'This season'], [1, '1 year'], [2, '2 years'], [3, '3 years'], [5, '5 years'], [10, '10 years']]
const AVAILABILITY_WINDOWS = SELECTION_WINDOWS.filter(([v]) => v !== -1)   // the matrix has no season to measure from
const SELECT = 'bg-pb-surface2 border border-pb-hairline rounded-lg px-2.5 py-1.5 text-[13px] text-pb-text focus:outline-none focus:border-pb-accent'
const newId = () => Math.random().toString(16).slice(2, 14)

// A rule has something to start on, and a team to start it for. Anything less is
// kept on screen while it is being written and saved once it is whole.
const ruleIsWhole = (r) => (r.team_ids || []).length > 0 && !!(r.gender || (r.squads || []).length || r.top_squads || r.played_years != null)

function CheckGrid({ options, selected, onToggle, disabled, label }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1.5" role="group" aria-label={label}>
      {options.map((o) => (
        <label key={o.value} className="inline-flex items-center gap-1.5 text-[12.5px] text-pb-dim cursor-pointer">
          <input type="checkbox" className="accent-pb-accent" checked={selected.includes(o.value)} disabled={disabled}
            onChange={() => onToggle(o.value)} />
          {o.label}
        </label>
      ))}
    </div>
  )
}

// One team rule: who it is for, and what that team starts on.
function TeamRule({ rule, teams, squads, onChange, onDelete, disabled }) {
  const set = (patch) => onChange({ ...rule, ...patch })
  const toggleIn = (key, v) => set({ [key]: (rule[key] || []).includes(v) ? rule[key].filter((x) => x !== v) : [...(rule[key] || []), v] })
  // The mode is remembered on screen (`_mode`, never sent): "Chosen" with nothing
  // ticked yet has no data to tell it apart from "All", and must not snap back.
  const squadMode = rule._mode || (rule.top_squads ? 'top' : (rule.squads || []).length ? 'chosen' : 'all')
  const setMode = (m) => set(m === 'all' ? { _mode: m, top_squads: null, squads: [] } : m === 'top' ? { _mode: m, top_squads: rule.top_squads || 3, squads: [] } : { _mode: m, top_squads: null, squads: rule.squads || [] })
  const whole = ruleIsWhole(rule)
  return (
    <div data-team-rule={rule.id} className="rounded-lg border border-pb-hairline p-3.5 flex flex-col gap-3">
      <div>
        <div className={LABEL}>For these teams</div>
        <CheckGrid label="Teams" options={teams} selected={rule.team_ids || []} onToggle={(v) => toggleIn('team_ids', v)} disabled={disabled} />
      </div>
      <div className="grid gap-x-6 gap-y-3 sm:grid-cols-3">
        <div>
          <div className={LABEL}>Gender</div>
          <Segmented sm value={rule.gender || ''} onChange={(v) => set({ gender: v })}
            options={[{ value: '', label: 'Any' }, { value: 'male', label: 'Men' }, { value: 'female', label: 'Women' }]} />
        </div>
        <div>
          <div className={LABEL}>Squads shown</div>
          <Segmented sm value={squadMode} onChange={setMode}
            options={[{ value: 'all', label: 'All' }, { value: 'top', label: 'Top' }, { value: 'chosen', label: 'Chosen' }]} />
          {squadMode === 'top' && (
            <div className="mt-2 flex items-center gap-2 text-[12.5px] text-pb-dim">
              Top <input type="number" min={1} max={30} value={rule.top_squads || ''} aria-label="Number of squads"
                onChange={(e) => set({ top_squads: Math.min(30, Math.max(1, Math.floor(Number(e.target.value)) || 1)) })}
                className={`${SELECT} w-[64px]`} /> squads, by XI number
            </div>
          )}
        </div>
        <div>
          <div className={LABEL}>Played within</div>
          <select value={rule.played_years == null ? 'club' : String(rule.played_years)} aria-label="Played within"
            onChange={(e) => set({ played_years: e.target.value === 'club' ? null : Number(e.target.value) })} className={SELECT}>
            <option value="club">Club setting</option>
            {SELECTION_WINDOWS.map(([v, l]) => <option key={v} value={v}>{l === 'Any time' ? 'Any time' : l}</option>)}
          </select>
        </div>
      </div>
      {squadMode === 'chosen' && (
        <div>
          <div className={LABEL}>Only these squads</div>
          {squads.length
            ? <CheckGrid label="Squads" options={squads.map((n) => ({ value: n, label: n }))} selected={rule.squads || []} onToggle={(v) => toggleIn('squads', v)} disabled={disabled} />
            : <div className="text-[12px] text-pb-faint">No squads set up yet. Add them on the Squads screen.</div>}
        </div>
      )}
      <div className="flex items-center justify-between gap-3">
        <div className="text-[12px]" style={{ color: whole ? 'var(--pb-faint)' : 'var(--pb-amber)' }} data-rule-state={whole ? 'saved' : 'incomplete'}>
          {whole ? 'Saved. Applies when you open one of these teams on the Selection board.' : 'Pick a team and at least one thing to start on. It is saved once both are set.'}
        </div>
        <Btn sm variant="ghost" onClick={onDelete} disabled={disabled}>Delete rule</Btn>
      </div>
    </div>
  )
}

const LABEL = 'font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest block mb-1.5'

export default function AdminSelectSettings() {
  const { hasCapability, canEditCap } = useAuth()
  const toast = useToast()
  // `toast` is a new object each render: never a hook dependency (a reload would wipe a rule being written).
  const toastRef = useRef(toast)
  toastRef.current = toast
  const canEdit = canEditCap(CAP.SELECT_RULES, CAP.MANAGE_SELECTIONS)
  const [loaded, setLoaded] = useState(false)
  const [maybe, setMaybe] = useState(true)
  const [colours, setColours] = useState(DEFAULTS)
  const [names, setNames] = useState(DEFAULT_WEEK_NAMES)
  const [windows, setWindows] = useState({ selection: 3, availability: 0 })
  const [rules, setRules] = useState([])
  const [teams, setTeams] = useState([])
  const [squadNames, setSquadNames] = useState([])
  const [showJuniors, setShowJuniors] = usePersistedState('select.juniors', false, (v) => typeof v === 'boolean')
  useHalfColours()

  useEffect(() => {
    let alive = true
    Promise.all([api.bsAvailabilityConfig(), api.bsRules()])
      .then(([cfg, rules]) => {
        if (!alive) return
        setMaybe(cfg?.allow_maybe !== false)
        setColours({ ...DEFAULTS, ...(rules?.settings?.half_colours || cfg?.half_colours || {}) })
        setNames({ ...DEFAULT_WEEK_NAMES, ...(rules?.settings?.week_names || cfg?.week_names || {}) })
        setWindows({ selection: 3, availability: 0, ...(cfg?.played_years || {}) })
        setRules(cfg?.team_defaults || [])
        setTeams((rules?.options?.teams || []).map((t) => ({ value: t.value, label: t.label })))
        setSquadNames((cfg?.squads || []).map((q) => q.name))
        setLoaded(true)
      })
      .catch((e) => { toastRef.current.error(e.message || 'Could not load settings'); setLoaded(true) })
    return () => { alive = false }
  }, [])

  const saveColour = async (key, hex) => {
    const before = colours
    const next = { ...colours, [key]: hex }
    setColours(next); setHalfColours(next)            // every open card follows at once
    try {
      const s = await api.bsRuleSettings({ [`half_colour_${key}`]: hex === DEFAULTS[key] ? null : hex })
      if (s?.half_colours) { setColours(s.half_colours); setHalfColours(s.half_colours) }
    } catch (e) {
      setColours(before); setHalfColours(before)
      toast.error(e.message || 'Could not save the colour')
    }
  }
  const saveName = async (key, value) => {
    const before = names
    const next = { ...names, [key]: value }
    setNames(next); setWeekNames(next)               // every open screen follows at once
    try {
      const s = await api.bsRuleSettings({ [`week_name_${key}`]: value === DEFAULT_WEEK_NAMES[key] ? null : value })
      if (s?.week_names) { setNames(s.week_names); setWeekNames(s.week_names) }
    } catch (e) {
      setNames(before); setWeekNames(before)
      toast.error(e.message || 'Could not save the name')
    }
  }
  const saveWindow = async (key, n) => {
    const before = windows
    const next = { ...windows, [key]: n }
    setWindows(next); setSelectConfig({ played_years: next })
    try {
      const s = await api.bsRuleSettings({ [`played_years_${key}`]: n })
      if (s?.played_years) { setWindows(s.played_years); setSelectConfig({ played_years: s.played_years }) }
    } catch (e) { setWindows(before); setSelectConfig({ played_years: before }); toast.error(e.message || 'Could not save') }
  }

  // Team rules are written as a list and saved whole, a moment after the last
  // edit. A rule that is still half written stays on screen and is left out of
  // what is sent (the server never stores one).
  const saveTimer = useRef(null)
  const persistRules = useCallback((list) => {
    clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(async () => {
      try {
        const s = await api.bsRuleSettings({ team_defaults: list.filter(ruleIsWhole) })
        setSelectConfig({ team_defaults: s?.team_defaults || [] })
      } catch (e) { toastRef.current.error(e.message || 'Could not save the team rules') }
    }, 350)
  }, [])
  useEffect(() => () => clearTimeout(saveTimer.current), [])
  const editRules = (next) => { setRules(next); persistRules(next) }

  const saveMaybe = async (on) => {
    setMaybe(on); setAllowMaybe(on)
    try { await api.bsSetSelfService({ allow_maybe: on }) }
    catch (e) { setMaybe(!on); setAllowMaybe(!on); toast.error(e.message || 'Could not save') }
  }

  if (!loaded) return <BetterSelectLayout title="Settings"><PbSpinner message="Loading settings…" /></BetterSelectLayout>

  return (
    <BetterSelectLayout title="Settings" caption="How BetterSelect looks and behaves">
      <div className="flex flex-col gap-4 max-w-[980px]" data-select-settings>
        <Card>
          <Head title="Two-day games"
            sub="A two-day game is answered one weekend at a time. Say what your club calls the two weeks (many use A and B). A player who is free for one weekend and away for the other is half available. Their dot and card edge use the colours below instead of the green of Available or the red of Unavailable, so you can see them at a glance." />
          <WeekName weekKey="w1" label="Name of the first week" hint={`Shown as "${names.w1} Only", "${names.w1} OUT". Up to 10 characters.`}
            value={names.w1} onSave={(v) => saveName('w1', v)} disabled={!canEdit} />
          <WeekName weekKey="w2" label="Name of the second week" hint={`Shown as "${names.w2} Only", "${names.w2} ?".`}
            value={names.w2} onSave={(v) => saveName('w2', v)} disabled={!canEdit} />
          <HalfColour weekKey="w1" title={`Available for ${names.w1} only`} hint="Free the first weekend of a two-day game, away the second."
            value={colours.w1} onChange={(v) => saveColour('w1', v)} disabled={!canEdit} />
          <HalfColour weekKey="w2" title={`Available for ${names.w2} only`} hint="Away the first weekend, free the second."
            value={colours.w2} onChange={(v) => saveColour('w2', v)} disabled={!canEdit} />
          <div className="flex items-center gap-4 pt-2.5 border-t border-pb-hairline text-[12px] text-pb-faint flex-wrap">
            <span>On a card:</span>
            <span className="inline-flex items-center gap-1.5"><Dot status="AVAILABLE" size={10} /> Available</span>
            <span className="inline-flex items-center gap-1.5"><Dot status="HALF_W1" size={10} /> {names.w1} Only</span>
            <span className="inline-flex items-center gap-1.5"><Dot status="HALF_W2" size={10} /> {names.w2} Only</span>
            <span className="inline-flex items-center gap-1.5"><Dot status="UNAVAILABLE" size={10} /> Unavailable</span>
          </div>
        </Card>

        <Card>
          <Head title="Players listed"
            sub="How far back a player's last game may be for the pool to list them. Typing a name in search always finds anyone, so nobody is out of reach." />
          <Row label="Selection board and Whiteboard" hint="Played within">
            <select value={windows.selection} disabled={!canEdit} aria-label="Selection board played within" data-window="selection"
              onChange={(e) => saveWindow('selection', Number(e.target.value))} className={SELECT}>
              {SELECTION_WINDOWS.map(([v, l]) => <option key={v} value={v}>{v === 0 ? 'Played any time' : v === -1 ? 'Played this season' : `Played within ${l}`}</option>)}
            </select>
          </Row>
          <Row label="Availability" hint="Played within">
            <select value={windows.availability} disabled={!canEdit} aria-label="Availability played within" data-window="availability"
              onChange={(e) => saveWindow('availability', Number(e.target.value))} className={SELECT}>
              {AVAILABILITY_WINDOWS.map(([v, l]) => <option key={v} value={v}>{v === 0 ? 'Played any time' : `Played within ${l}`}</option>)}
            </select>
          </Row>
        </Card>

        <Card>
          <Head title="Team defaults"
            sub="What each team's Selection board starts on, written as rules. For example, the women's team starts on Gender = Women, and the 1st XI only sees the top three squads. The board shows the rule at the top of the pool and one click turns it off for that match, so nobody is ever hidden for good." />
          <div className="flex flex-col gap-3" data-team-rules>
            {rules.length === 0 && <div className="text-[12.5px] text-pb-faint">No team rules yet. Every team starts on everyone.</div>}
            {rules.map((r) => (
              <TeamRule key={r.id} rule={r} teams={teams} squads={squadNames} disabled={!canEdit}
                onChange={(nr) => editRules(rules.map((x) => (x.id === r.id ? nr : x)))}
                onDelete={() => editRules(rules.filter((x) => x.id !== r.id))} />
            ))}
          </div>
          {canEdit && (
            <div className="mt-3">
              <Btn sm variant="soft" icon="plus" data-add-team-rule onClick={() => setRules((l) => [...l, { id: newId(), team_ids: [], gender: '', squads: [], top_squads: null, played_years: null }])}>Add a team rule</Btn>
            </div>
          )}
        </Card>

        <Card>
          <Head title="What the screens show" />
          <Row label="Junior grades" hint="Junior grades are set in Manage Grades. This is remembered on this device and applies to the Selection board, the Whiteboard, Availability and Fixtures.">
            <Segmented sm value={showJuniors ? 'show' : 'hide'} onChange={(v) => setShowJuniors(v === 'show')}
              options={[{ value: 'hide', label: 'Hide' }, { value: 'show', label: 'Show' }]} />
          </Row>
          <Row label="Maybe answer" hint="When off, selectors and players are offered only Available or Unavailable. Maybe answers already recorded stay.">
            <Segmented sm value={maybe ? 'on' : 'off'} onChange={(v) => canEdit && saveMaybe(v === 'on')}
              options={[{ value: 'on', label: 'On' }, { value: 'off', label: 'Off' }]} />
          </Row>
        </Card>

        <p className="text-[12.5px] text-pb-faint">
          Age limits, side size, fees and training notes, and the captain and player emails are on{' '}
          <Link to="/admin/betterselect/rules" className="text-pb-accent underline">Selection rules</Link>.
        </p>
      </div>
    </BetterSelectLayout>
  )
}
