import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import BetterStatsLayout from '../../components/admin/BetterStatsLayout'
import { useClub } from '../../hooks/useClub'
import { normalizeGender } from '../../lib/playerAttributes'
import MilestoneSplitNote from '../../components/MilestoneSplitNote'
import { useAuth } from '../../contexts/AuthContext'
import { CAP } from '../../lib/capabilities'

const CAT_LABELS = {
  batting: 'BATTING',
  bowling: 'BOWLING',
  fielding: 'FIELDING',
  matches: 'MATCHES',
}

const CAT_COLORS = {
  batting: 'text-blue-400 bg-blue-400/10 border-blue-400/20',
  bowling: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20',
  fielding: 'text-amber-400 bg-amber-400/10 border-amber-400/20',
  matches: 'text-purple-400 bg-purple-400/10 border-purple-400/20',
}

function milestoneLabel(item, isUpcoming) {
  const { type, milestone_value, target, current, detail } = item
  const value = isUpcoming ? target : milestone_value
  if (type === 'grade_matches') return `${value} games — ${detail || ''}`
  if (type === 'runs') return `${value.toLocaleString()} runs`
  if (type === 'wickets') return `${value} wickets`
  if (type === 'catches') return `${value} catches`
  if (type === 'matches') return `${value} club games`
  return `${value}`
}

function fmtDate(iso) {
  if (!iso) return null
  return new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

function CatBadge({ cat }) {
  return (
    <span className={`inline-block font-mono text-[9px] tracking-wide3 px-1.5 py-0.5 rounded border ${CAT_COLORS[cat] || 'text-pb-faint bg-pb-surface2 border-pb-hairline'}`}>
      {CAT_LABELS[cat] || cat.toUpperCase()}
    </span>
  )
}

const STATS = [
  { stat: 'runs', label: 'Runs' },
  { stat: 'wickets', label: 'Wickets' },
  { stat: 'matches', label: 'Matches' },
  { stat: 'catches', label: 'Catches' },
]

// What a step looks like in play, for the line under each picker. The default
// runs and wickets steps carry an extra first rung (500 runs, 50 wickets);
// every other step is a plain multiple of itself.
function ladderText(stat, step) {
  const extra = (stat === 'runs' && step === 1000) ? 500 : (stat === 'wickets' && step === 100) ? 50 : null
  const rungs = extra ? [extra, step, step * 2, step * 3] : [step, step * 2, step * 3, step * 4]
  return `${rungs.map(n => n.toLocaleString()).join(', ')}…`
}

// The same rule the server enforces (services/milestone_rules.step_problem),
// so a typed step is turned back before it is sent. The server still decides.
function stepProblem(stat, raw, limits) {
  const n = Number(raw)
  const { min, max, multiple } = limits
  const name = stat.charAt(0).toUpperCase() + stat.slice(1)
  if (String(raw).trim() === '' || !Number.isInteger(n)) return `${name} must be a whole number`
  if (n < min || n > max) return `${name} must be between ${min.toLocaleString()} and ${max.toLocaleString()}`
  if (n % multiple) return `${name} must be a multiple of ${multiple}`
  return null
}

// A typed step and its Set button. Enter sets it too.
function CustomStepInput({ stat, scope, initial, limits, onSet, disabled }) {
  const [draft, setDraft] = useState(initial == null ? '' : String(initial))
  const [problem, setProblem] = useState(null)
  useEffect(() => { setDraft(initial == null ? '' : String(initial)) }, [initial])
  const submit = () => {
    const err = stepProblem(stat, draft, limits)
    setProblem(err)
    if (!err) onSet(Number(draft))
  }
  return (
    <div className="mt-2">
      <div className="flex items-center gap-2">
        <input
          type="number"
          inputMode="numeric"
          value={draft}
          min={limits.min}
          max={limits.max}
          step={limits.multiple}
          disabled={disabled}
          aria-label={`${scope ? `${scope} ` : ''}custom ${stat} step`}
          onChange={e => { setDraft(e.target.value); setProblem(null) }}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); submit() } }}
          className="w-24 px-2 py-1.5 text-sm bg-pb-surface2 border pb-hairline rounded text-pb-text focus:outline-none focus:border-pb-accent/50 disabled:opacity-50"
        />
        <button
          type="button"
          disabled={disabled || String(draft) === String(initial ?? '')}
          onClick={submit}
          className="px-3 py-1.5 font-mono text-[10px] tracking-wide2 border pb-hairline rounded text-pb-faint hover:text-pb-text transition-colors disabled:opacity-40"
        >
          SET
        </button>
      </div>
      <p className={`text-xs mt-1 ${problem ? 'text-red-400' : 'text-pb-faintest'}`}>
        {problem || `${limits.min.toLocaleString()} to ${limits.max.toLocaleString()}, in multiples of ${limits.multiple}`}
      </p>
    </div>
  )
}

// The club's own increment for one stat: the presets, or a step typed in.
function StepPicker({ label, stat, value, options, limits, onChange, disabled }) {
  const isPreset = options.includes(value)
  const [custom, setCustom] = useState(false)
  const showCustom = custom || !isPreset
  // A typed step that lands on a preset is that preset from then on.
  useEffect(() => { if (isPreset) setCustom(false) }, [value, isPreset])
  return (
    <div>
      <p className="font-mono text-[9px] tracking-wide2 text-pb-faintest uppercase mb-1.5">{label}</p>
      <div className="flex border pb-hairline rounded overflow-hidden w-fit max-w-full flex-wrap">
        {options.map(opt => {
          const on = !showCustom && value === opt
          return (
            <button
              key={opt}
              type="button"
              disabled={disabled}
              onClick={() => { setCustom(false); if (value !== opt) onChange(opt) }}
              aria-pressed={on}
              className={`px-3 py-1.5 font-mono text-[10px] tracking-wide2 transition-colors disabled:opacity-50 ${
                on ? 'bg-pb-surface2' : 'text-pb-faint hover:text-pb-text'
              }`}
              style={on ? { color: 'var(--pb-accent)' } : {}}
            >
              {opt.toLocaleString()}
            </button>
          )
        })}
        <button
          type="button"
          disabled={disabled}
          onClick={() => setCustom(true)}
          aria-pressed={showCustom}
          className={`px-3 py-1.5 font-mono text-[10px] tracking-wide2 transition-colors disabled:opacity-50 ${
            showCustom ? 'bg-pb-surface2' : 'text-pb-faint hover:text-pb-text'
          }`}
          style={showCustom ? { color: 'var(--pb-accent)' } : {}}
        >
          CUSTOM
        </button>
      </div>
      {showCustom && (
        <CustomStepInput
          stat={stat}
          initial={isPreset ? null : value}
          limits={limits}
          onSet={onChange}
          disabled={disabled}
        />
      )}
      <p className="text-pb-faintest text-xs mt-1.5">{ladderText(stat, value)}</p>
    </div>
  )
}

// One grade's increment for one stat. A null value follows the club's setting.
function GradeStepSelect({ stat, label, grade, value, clubValue, options, limits, onChange, disabled }) {
  const isPreset = value != null && options.includes(value)
  const [custom, setCustom] = useState(false)
  const showCustom = custom || (value != null && !isPreset)
  useEffect(() => { if (isPreset) setCustom(false) }, [value, isPreset])
  const selectValue = showCustom ? 'custom' : value == null ? '' : String(value)
  const pick = e => {
    const v = e.target.value
    if (v === 'custom') { setCustom(true); return }
    setCustom(false)
    onChange(v === '' ? null : Number(v))
  }
  return (
    <div className="min-w-0">
      <label className="block font-mono text-[9px] tracking-wide2 text-pb-faintest uppercase mb-1">
        {label}
        <select
          value={selectValue}
          onChange={pick}
          disabled={disabled}
          aria-label={`${grade} ${stat} increment`}
          className="mt-1 block w-full min-w-0 px-2 py-1.5 text-sm normal-case tracking-normal font-sans bg-pb-surface2 border pb-hairline rounded text-pb-text focus:outline-none focus:border-pb-accent/50 disabled:opacity-50"
        >
          <option value="">Club ({clubValue.toLocaleString()})</option>
          {options.map(opt => <option key={opt} value={opt}>Every {opt.toLocaleString()}</option>)}
          <option value="custom">Custom…</option>
        </select>
      </label>
      {showCustom && (
        <CustomStepInput
          stat={stat}
          scope={grade}
          initial={value != null && !isPreset ? value : null}
          limits={limits}
          onSet={onChange}
          disabled={disabled}
        />
      )}
    </div>
  )
}

function GradeSchemeCard({ data, canEdit, saving, onChange, error }) {
  const [showOlder, setShowOlder] = useState(false)
  const grades = data.grade_schemes || []
  const hasSteps = g => STATS.some(({ stat }) => g.steps?.[stat] != null)
  const shown = grades.filter(g => g.active || hasSteps(g) || showOlder)
  const hiddenCount = grades.length - grades.filter(g => g.active || hasSteps(g)).length
  if (grades.length === 0) return null
  return (
    <div className="pb-card px-4 py-4 mb-6">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">Milestones by grade</p>
      <p className="text-pb-faint text-sm mb-1">
        Give a grade its own increments, for example every 25 games in A Grade while the rest of the club stays on 50.
        These apply to milestones inside that grade (such as 1,000 runs in A Grade) on the Records page and in grade milestone emails.
        Career milestones keep the club setting above.
      </p>
      <p className="text-pb-faintest text-xs mb-4">Leave a box on Club to follow the club setting above.</p>
      <div className="space-y-4">
        {shown.map(g => (
          <div key={g.key} className="border-t pb-hairline pt-3 first:border-t-0 first:pt-0">
            <p className="text-pb-text text-sm font-medium mb-2 truncate" title={g.name}>{g.name}</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {STATS.map(({ stat, label }) => (
                <GradeStepSelect
                  key={stat}
                  stat={stat}
                  label={label}
                  grade={g.name}
                  value={g.steps?.[stat] ?? null}
                  clubValue={data.scheme[`${stat}_step`]}
                  options={data.scheme_options[`${stat}_steps`]}
                  limits={data.step_limits[stat]}
                  onChange={v => onChange(g, stat, v)}
                  disabled={!canEdit || saving}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
      {hiddenCount > 0 && (
        <button
          type="button"
          onClick={() => setShowOlder(v => !v)}
          className="mt-4 font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors"
        >
          {showOlder ? 'HIDE OLDER GRADES' : `SHOW ${hiddenCount} OLDER GRADE${hiddenCount === 1 ? '' : 'S'}`}
        </button>
      )}
      {!canEdit && (
        <p className="text-pb-faintest text-xs mt-3">You need the Milestones permission to change these.</p>
      )}
      {error && <p className="text-red-400 text-sm mt-3">{error}</p>}
    </div>
  )
}

function ProgressBar({ current, target }) {
  const pct = Math.min(100, Math.round((current / target) * 100))
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-1.5 bg-pb-surface2 rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: 'var(--pb-accent)' }} />
      </div>
      <span className="font-mono text-[10px] text-pb-faint">{pct}%</span>
    </div>
  )
}

export default function AdminMilestones() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [status, setStatus] = useState('upcoming')
  const [category, setCategory] = useState('all')
  const [gender, setGender] = useState('all')
  const [search, setSearch] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const { club } = useClub()
  const slug = club?.slug
  const { hasCapability } = useAuth()
  const canPickSteps = hasCapability(CAP.MANAGE_MILESTONES)
  const [savingStep, setSavingStep] = useState(false)
  const [stepError, setStepError] = useState(null)
  const [gradeError, setGradeError] = useState(null)
  const [settingsOpen, setSettingsOpen] = useState(false)

  useEffect(() => {
    setLoading(true)
    api.adminGetMilestones()
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [])

  const loadReport = () => api.adminGetMilestones().then(d => { setData(d); return d })

  // Saving fills in the rungs the new step adds on the server, in the
  // background, so the list is read again straight away and once more shortly
  // after. A club on a large history may see the first read without the new
  // rungs; the second picks them up.
  const changeStep = async (key, value) => {
    setSavingStep(true)
    setStepError(null)
    try {
      await api.adminSetMilestoneScheme({ [key]: value })
      await loadReport()
      setTimeout(() => { loadReport().catch(() => {}) }, 4000)
    } catch (e) {
      setStepError(e.message)
    } finally {
      setSavingStep(false)
    }
  }

  // A grade's increments are read when a screen asks, nothing is rebuilt, so
  // one reload of the report is enough.
  const changeGradeStep = async (grade, stat, value) => {
    setSavingStep(true)
    setGradeError(null)
    try {
      await api.adminSetMilestoneGradeScheme({ grade: grade.name, [`${stat}_step`]: value })
      await loadReport()
    } catch (e) {
      setGradeError(e.message)
    } finally {
      setSavingStep(false)
    }
  }

  const { upcomingFiltered, achievedFiltered } = useMemo(() => {
    if (!data) return { upcomingFiltered: [], achievedFiltered: [] }
    const q = search.trim().toLowerCase()
    const catMatch = item => category === 'all' || item.category === category
    const nameMatch = item => !q || item.player_name.toLowerCase().includes(q)
    const genderMatch = item => gender === 'all' || normalizeGender(item.gender) === gender
    // Date filter only applies to achieved milestones (by the date achieved).
    // Items with no achieved_at fall out once a range is set.
    const dateMatch = item => {
      if (!dateFrom && !dateTo) return true
      if (!item.achieved_at) return false
      const d = item.achieved_at.slice(0, 10)
      if (dateFrom && d < dateFrom) return false
      if (dateTo && d > dateTo) return false
      return true
    }
    return {
      upcomingFiltered: data.upcoming.filter(i => catMatch(i) && nameMatch(i) && genderMatch(i)),
      achievedFiltered: data.achieved.filter(i => catMatch(i) && nameMatch(i) && genderMatch(i) && dateMatch(i)),
    }
  }, [data, category, search, gender, dateFrom, dateTo])

  const showUpcoming = status === 'upcoming' || status === 'all'
  const showAchieved = status === 'achieved' || status === 'all'

  return (
    <BetterStatsLayout>
      <div className="max-w-5xl">
        <div className="mb-6">
          <h1 className="font-display font-bold text-2xl text-pb-text mb-1">Milestones</h1>
          <p className="text-pb-faint text-sm">Upcoming and achieved milestones across all club members.</p>
        </div>

        {/* Filter bar */}
        <div className="flex flex-wrap items-center gap-3 mb-6">
          {/* Status tabs */}
          <div className="flex border pb-hairline rounded overflow-hidden">
            {[['upcoming', 'Upcoming'], ['achieved', 'Achieved'], ['all', 'All']].map(([val, label]) => (
              <button
                key={val}
                onClick={() => setStatus(val)}
                className={`px-3 py-1.5 font-mono text-[10px] tracking-wide2 transition-colors ${
                  status === val
                    ? 'bg-pb-surface2 text-pb-text'
                    : 'text-pb-faint hover:text-pb-text'
                }`}
                style={status === val ? { color: 'var(--pb-accent)' } : {}}
              >
                {label.toUpperCase()}
              </button>
            ))}
          </div>

          {/* Category filter */}
          <div className="flex border pb-hairline rounded overflow-hidden">
            {[['all', 'All'], ['batting', 'Batting'], ['bowling', 'Bowling'], ['fielding', 'Fielding'], ['matches', 'Matches']].map(([val, label]) => (
              <button
                key={val}
                onClick={() => setCategory(val)}
                className={`px-3 py-1.5 font-mono text-[10px] tracking-wide2 transition-colors ${
                  category === val
                    ? 'bg-pb-surface2 text-pb-text'
                    : 'text-pb-faint hover:text-pb-text'
                }`}
                style={category === val ? { color: 'var(--pb-accent)' } : {}}
              >
                {label.toUpperCase()}
              </button>
            ))}
          </div>

          {/* Gender filter */}
          <div className="flex border pb-hairline rounded overflow-hidden">
            {[['all', 'All'], ['male', 'Men'], ['female', 'Women']].map(([val, label]) => (
              <button
                key={val}
                onClick={() => setGender(val)}
                className={`px-3 py-1.5 font-mono text-[10px] tracking-wide2 transition-colors ${
                  gender === val
                    ? 'bg-pb-surface2 text-pb-text'
                    : 'text-pb-faint hover:text-pb-text'
                }`}
                style={gender === val ? { color: 'var(--pb-accent)' } : {}}
              >
                {label.toUpperCase()}
              </button>
            ))}
          </div>

          {/* Player search */}
          <input
            type="text"
            placeholder="Search player..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="px-3 py-1.5 text-sm bg-pb-surface2 border pb-hairline rounded text-pb-text placeholder-pb-faintest focus:outline-none focus:border-pb-accent/50 min-w-[160px]"
          />

          {/* Achieved-date filter (only meaningful when achieved rows show) */}
          {showAchieved && (
            <div className="flex items-center gap-2">
              <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest uppercase">Achieved</span>
              <input
                type="date"
                value={dateFrom}
                onChange={e => setDateFrom(e.target.value)}
                aria-label="Achieved from date"
                className="px-2 py-1.5 text-sm bg-pb-surface2 border pb-hairline rounded text-pb-text focus:outline-none focus:border-pb-accent/50"
              />
              <span className="text-pb-faintest text-xs">to</span>
              <input
                type="date"
                value={dateTo}
                onChange={e => setDateTo(e.target.value)}
                aria-label="Achieved to date"
                className="px-2 py-1.5 text-sm bg-pb-surface2 border pb-hairline rounded text-pb-text focus:outline-none focus:border-pb-accent/50"
              />
              {(dateFrom || dateTo) && (
                <button
                  onClick={() => { setDateFrom(''); setDateTo('') }}
                  className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors"
                >
                  CLEAR
                </button>
              )}
            </div>
          )}

          {data && (
            <span className="text-pb-faintest font-mono text-[10px] ml-auto">
              {showUpcoming && `${upcomingFiltered.length} upcoming`}
              {showUpcoming && showAchieved && ' · '}
              {showAchieved && `${achievedFiltered.length} achieved`}
            </span>
          )}
        </div>

        {loading && (
          <div className="text-pb-faint text-sm">Loading milestones…</div>
        )}
        {error && (
          <div className="text-red-400 text-sm">{error}</div>
        )}

        {data && (
          <div className="space-y-8">
            {/* ---- Upcoming ---- */}
            {showUpcoming && (
              <section>
                <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">
                  Milestones In Reach
                  {upcomingFiltered.length > 0 && (
                    <span className="ml-2 text-pb-faintest">({upcomingFiltered.length})</span>
                  )}
                </p>
                {upcomingFiltered.length === 0 ? (
                  <div className="pb-card px-5 py-4 text-pb-faint text-sm">No upcoming milestones match the current filters.</div>
                ) : (
                  <div className="pb-card overflow-hidden">
                    <table className="w-full">
                      <thead>
                        <tr className="pb-hairline-b">
                          <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">Player</th>
                          <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase hidden sm:table-cell">Category</th>
                          <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">Milestone</th>
                          <th className="text-right px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">Progress</th>
                          <th className="text-right px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">To Go</th>
                        </tr>
                      </thead>
                      <tbody>
                        {upcomingFiltered.map((item, i) => (
                          <tr key={`${item.player_id}-${item.type}-${item.detail}-${item.target}-${item.counts || ''}`}
                            className={`${i > 0 ? 'pb-hairline-t' : ''} hover:bg-pb-surface2 transition-colors`}>
                            <td className="px-4 py-3">
                              {slug ? (
                                <Link
                                  to={`/players/${item.player_id}`}
                                  className="text-pb-text text-sm hover:underline"
                                  style={{ color: 'var(--pb-accent)' }}
                                >
                                  {item.player_name}
                                </Link>
                              ) : (
                                <span className="text-pb-text text-sm">{item.player_name}</span>
                              )}
                            </td>
                            <td className="px-4 py-3 hidden sm:table-cell">
                              <CatBadge cat={item.category} />
                            </td>
                            <td className="px-4 py-3">
                              <span className="text-pb-text text-sm">{milestoneLabel(item, true)}</span>
                              {item.detail && (
                                <span className="block text-pb-faintest font-mono text-[10px] mt-0.5">{item.detail}</span>
                              )}
                              <MilestoneSplitNote m={item} className="mt-0.5" />
                            </td>
                            <td className="px-4 py-3 text-right">
                              <div className="flex justify-end">
                                <ProgressBar current={item.current} target={item.target} />
                              </div>
                              <div className="text-pb-faintest font-mono text-[10px] mt-0.5 text-right">
                                {item.current.toLocaleString()} / {item.target.toLocaleString()}
                              </div>
                            </td>
                            <td className="px-4 py-3 text-right">
                              <span className="font-mono text-sm font-bold" style={{ color: 'var(--pb-accent)' }}>
                                {item.needed}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            )}

            {/* ---- Achieved ---- */}
            {showAchieved && (
              <section>
                <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-3">
                  Achieved
                  {achievedFiltered.length > 0 && (
                    <span className="ml-2 text-pb-faintest">({achievedFiltered.length})</span>
                  )}
                </p>
                {achievedFiltered.length === 0 ? (
                  <div className="pb-card px-5 py-4 text-pb-faint text-sm">No achieved milestones match the current filters.</div>
                ) : (
                  <div className="pb-card overflow-hidden">
                    <table className="w-full">
                      <thead>
                        <tr className="pb-hairline-b">
                          <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">Player</th>
                          <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase hidden sm:table-cell">Category</th>
                          <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">Milestone</th>
                          <th className="text-left px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase hidden md:table-cell">Grade</th>
                          <th className="text-right px-4 py-2.5 font-mono text-[9px] tracking-wide3 text-pb-faintest uppercase">Date</th>
                        </tr>
                      </thead>
                      <tbody>
                        {achievedFiltered.map((item, i) => (
                          <tr key={`${item.player_id}-${item.type}-${item.milestone_value}-${item.detail}-${i}`}
                            className={`${i > 0 ? 'pb-hairline-t' : ''} hover:bg-pb-surface2 transition-colors`}>
                            <td className="px-4 py-3">
                              {slug ? (
                                <Link
                                  to={`/players/${item.player_id}`}
                                  className="text-sm hover:underline"
                                  style={{ color: 'var(--pb-accent)' }}
                                >
                                  {item.player_name}
                                </Link>
                              ) : (
                                <span className="text-pb-text text-sm">{item.player_name}</span>
                              )}
                            </td>
                            <td className="px-4 py-3 hidden sm:table-cell">
                              <CatBadge cat={item.category} />
                            </td>
                            <td className="px-4 py-3">
                              <span className="text-pb-text text-sm">{milestoneLabel(item, false)}</span>
                            </td>
                            <td className="px-4 py-3 hidden md:table-cell">
                              <span className="text-pb-faint text-sm">{item.detail || '—'}</span>
                            </td>
                            <td className="px-4 py-3 text-right font-mono text-[11px] text-pb-faint whitespace-nowrap">
                              {fmtDate(item.achieved_at) || '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            )}
          </div>
        )}

        {/* The increments live at the foot and start closed: the list of runs,
            wickets and matches pickers (plus a card per grade) was longer than
            the milestones it configures. */}
        {data?.scheme && (
          <section className="mt-10" data-testid="milestone-settings">
            <button
              type="button"
              onClick={() => setSettingsOpen(v => !v)}
              aria-expanded={settingsOpen}
              aria-controls="milestone-settings-body"
              className="w-full flex items-center justify-between gap-3 pb-card px-4 py-3 text-left hover:bg-pb-surface2 transition-colors"
            >
              <span>
                <span className="block font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">Milestone settings</span>
                <span className="block text-pb-faintest text-xs mt-0.5">How often runs, wickets, matches and catches are marked, club wide and by grade.</span>
              </span>
              <span className="font-mono text-[10px] tracking-wide2 text-pb-faint shrink-0">{settingsOpen ? 'HIDE' : 'SHOW'}</span>
            </button>
            {settingsOpen && (
              <div id="milestone-settings-body" className="mt-4 space-y-6">
            {/* Which milestones the club tracks. Applies to the Milestones page the
                public sees, the dashboard, player profiles and the milestone emails. */}
            {data?.scheme && (
              <div className="pb-card px-4 py-4">
                <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">Milestones tracked</p>
                <p className="text-pb-faint text-sm mb-3">
                  Choose how often a milestone is marked across a player's whole career at the club.
                  Pick a preset or type your own.
                </p>
                <div className="flex flex-wrap gap-x-8 gap-y-4">
                  {STATS.map(({ stat, label }) => (
                    <StepPicker
                      key={stat}
                      label={`${label}, every`}
                      stat={stat}
                      value={data.scheme[`${stat}_step`]}
                      options={data.scheme_options[`${stat}_steps`]}
                      limits={data.step_limits[stat]}
                      onChange={v => changeStep(`${stat}_step`, v)}
                      disabled={!canPickSteps || savingStep}
                    />
                  ))}
                </div>
                {!canPickSteps && (
                  <p className="text-pb-faintest text-xs mt-3">You need the Milestones permission to change these.</p>
                )}
                {stepError && <p className="text-red-400 text-sm mt-3">{stepError}</p>}
              </div>
            )}

            {data?.scheme && data.grade_schemes && (
              <GradeSchemeCard
                data={data}
                canEdit={canPickSteps}
                saving={savingStep}
                onChange={changeGradeStep}
                error={gradeError}
              />
            )}

              </div>
            )}
          </section>
        )}
      </div>
    </BetterStatsLayout>
  )
}
