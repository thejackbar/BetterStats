import { useState, useEffect, useMemo, useCallback } from 'react'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'

const INPUT_CLS = 'w-full bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent'
const LABEL_CLS = 'font-mono text-[10px] text-pb-faint block mb-1'
const BTN_PRIMARY = 'inline-flex items-center px-4 py-2 bg-pb-accent text-white text-sm font-semibold rounded hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed'
const BTN_SECONDARY = 'inline-flex items-center px-3 py-1.5 border pb-hairline text-pb-text text-xs rounded hover:bg-pb-surface2'
const BTN_DANGER = 'inline-flex items-center px-3 py-1.5 border border-red-400/40 text-red-300 text-xs rounded hover:bg-red-500/10'

const TABS = [
  { key: 'season', label: 'Season Adjustments', hint: 'Add or correct a player\'s season totals' },
  { key: 'game', label: 'Manual Games', hint: 'Add full or partial historical scorecards' },
  { key: 'career', label: 'Career Adjustments', hint: 'Career-only totals when no season info is available' },
  { key: 'audit', label: 'Audit & Undo', hint: 'Reverse any previous change' },
]

function ConfirmModal({ open, title, body, confirmLabel = 'Save changes', danger = false, onConfirm, onCancel }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center px-4" onClick={onCancel}>
      <div className="bg-pb-surface border pb-hairline rounded-lg max-w-md w-full p-5" onClick={e => e.stopPropagation()}>
        <h3 className="text-lg font-semibold text-pb-text mb-2">{title}</h3>
        <div className="text-sm text-pb-faint mb-4 whitespace-pre-line">{body}</div>
        <div className="flex justify-end gap-2">
          <button className={BTN_SECONDARY} onClick={onCancel}>Cancel</button>
          <button
            className={danger ? BTN_DANGER : BTN_PRIMARY}
            onClick={onConfirm}
          >{confirmLabel}</button>
        </div>
      </div>
    </div>
  )
}

function PlayerPicker({ players, value, onChange, placeholder = 'Search player…' }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const selected = players.find(p => p.id === value)
  const displayValue = open ? query : (selected ? selected.display_name : '')

  const filtered = query.length >= 2
    ? players.filter(p => p.display_name.toLowerCase().includes(query.toLowerCase())).slice(0, 8)
    : []

  return (
    <div className="relative">
      <input
        type="text"
        value={displayValue}
        onChange={e => { setQuery(e.target.value); setOpen(true) }}
        onFocus={() => { setQuery(''); setOpen(true) }}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={placeholder}
        className={INPUT_CLS}
      />
      {open && filtered.length > 0 && (
        <div className="absolute z-20 w-full bg-pb-surface border pb-hairline rounded mt-1 shadow-lg max-h-64 overflow-y-auto">
          {filtered.map(p => (
            <button
              key={p.id}
              type="button"
              onMouseDown={() => { onChange(p.id); setOpen(false); setQuery('') }}
              className="w-full text-left px-3 py-2 text-sm text-pb-text hover:bg-pb-surface2"
            >{p.display_name}</button>
          ))}
        </div>
      )}
    </div>
  )
}

const EMPTY_AGG = {
  games_played: 0,
  batting_innings: 0, batting_runs: 0, batting_not_outs: 0, batting_balls: 0,
  batting_fours: 0, batting_sixes: 0, batting_fifties: 0, batting_hundreds: 0,
  batting_ducks: 0, batting_high_score: '', batting_high_score_not_out: false,
  bowling_innings: 0, bowling_overs: 0, bowling_balls: 0, bowling_maidens: 0,
  bowling_runs: 0, bowling_wickets: 0, bowling_five_wicket_innings: 0,
  bowling_best_wickets: '', bowling_best_figures: '',
  fielding_catches: 0, fielding_catches_wk: 0, fielding_run_outs: 0, fielding_stumpings: 0,
  notes: '',
}

const EMPTY_SEASON_FORM = {
  player_id: '', season_id: '', grade_id: '',
  ...EMPTY_AGG,
  bowling_wides: 0, bowling_no_balls: 0,
}
const EMPTY_CAREER_FORM = { player_id: '', ...EMPTY_AGG }

function NumberField({ label, value, onChange, step = 1, min = 0, allowDecimal = false }) {
  return (
    <div>
      <label className={LABEL_CLS}>{label}</label>
      <input
        type="number"
        step={allowDecimal ? '0.1' : step}
        min={min}
        value={value === '' || value === null || value === undefined ? '' : value}
        onChange={e => {
          const v = e.target.value
          if (v === '') return onChange('')
          onChange(allowDecimal ? parseFloat(v) : parseInt(v, 10))
        }}
        className={INPUT_CLS}
      />
    </div>
  )
}

function AggregateFieldGrid({ form, setForm, includeWidesNoBalls = false }) {
  const set = (k) => (v) => setForm({ ...form, [k]: v === '' ? '' : v })
  return (
    <>
      <div>
        <h4 className="text-sm font-semibold text-pb-text mt-3 mb-2">Match counts</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <NumberField label="Games played" value={form.games_played} onChange={set('games_played')} />
          <NumberField label="Batting innings" value={form.batting_innings} onChange={set('batting_innings')} />
          <NumberField label="Bowling innings" value={form.bowling_innings} onChange={set('bowling_innings')} />
        </div>
      </div>

      <div>
        <h4 className="text-sm font-semibold text-pb-text mt-3 mb-2">Batting</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <NumberField label="Runs" value={form.batting_runs} onChange={set('batting_runs')} />
          <NumberField label="Not outs" value={form.batting_not_outs} onChange={set('batting_not_outs')} />
          <NumberField label="Balls faced" value={form.batting_balls} onChange={set('batting_balls')} />
          <NumberField label="High score" value={form.batting_high_score} onChange={set('batting_high_score')} />
          <NumberField label="50s" value={form.batting_fifties} onChange={set('batting_fifties')} />
          <NumberField label="100s" value={form.batting_hundreds} onChange={set('batting_hundreds')} />
          <NumberField label="Ducks" value={form.batting_ducks} onChange={set('batting_ducks')} />
          <NumberField label="Fours" value={form.batting_fours} onChange={set('batting_fours')} />
          <NumberField label="Sixes" value={form.batting_sixes} onChange={set('batting_sixes')} />
          <label className="flex items-center gap-2 text-xs text-pb-text mt-5">
            <input
              type="checkbox"
              checked={!!form.batting_high_score_not_out}
              onChange={e => setForm({ ...form, batting_high_score_not_out: e.target.checked })}
            />
            HS was not out
          </label>
        </div>
      </div>

      <div>
        <h4 className="text-sm font-semibold text-pb-text mt-3 mb-2">Bowling</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <NumberField label="Overs" value={form.bowling_overs} onChange={set('bowling_overs')} allowDecimal />
          <NumberField label="Balls" value={form.bowling_balls} onChange={set('bowling_balls')} />
          <NumberField label="Maidens" value={form.bowling_maidens} onChange={set('bowling_maidens')} />
          <NumberField label="Runs conceded" value={form.bowling_runs} onChange={set('bowling_runs')} />
          <NumberField label="Wickets" value={form.bowling_wickets} onChange={set('bowling_wickets')} />
          <NumberField label="5-wicket innings" value={form.bowling_five_wicket_innings} onChange={set('bowling_five_wicket_innings')} />
          <NumberField label="Best — wickets" value={form.bowling_best_wickets} onChange={set('bowling_best_wickets')} />
          <div>
            <label className={LABEL_CLS}>Best figures (e.g. 4-13)</label>
            <input type="text" value={form.bowling_best_figures || ''} onChange={e => setForm({ ...form, bowling_best_figures: e.target.value })} className={INPUT_CLS} />
          </div>
          {includeWidesNoBalls && <>
            <NumberField label="Wides" value={form.bowling_wides} onChange={set('bowling_wides')} />
            <NumberField label="No-balls" value={form.bowling_no_balls} onChange={set('bowling_no_balls')} />
          </>}
        </div>
      </div>

      <div>
        <h4 className="text-sm font-semibold text-pb-text mt-3 mb-2">Fielding</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <NumberField label="Catches" value={form.fielding_catches} onChange={set('fielding_catches')} />
          <NumberField label="WK catches" value={form.fielding_catches_wk} onChange={set('fielding_catches_wk')} />
          <NumberField label="Run-outs" value={form.fielding_run_outs} onChange={set('fielding_run_outs')} />
          <NumberField label="Stumpings" value={form.fielding_stumpings} onChange={set('fielding_stumpings')} />
        </div>
      </div>

      <div className="mt-3">
        <label className={LABEL_CLS}>Notes (optional — visible only to club admins)</label>
        <textarea
          rows={2}
          value={form.notes || ''}
          onChange={e => setForm({ ...form, notes: e.target.value })}
          className={INPUT_CLS}
          placeholder="Source / reference / anything worth tracking"
        />
      </div>
    </>
  )
}

// ─── Season adjustments tab ─────────────────────────────────────────────────

function SeasonAdjustmentsTab({ players, seasons, refreshAll, onPending }) {
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState(EMPTY_SEASON_FORM)
  const [editingId, setEditingId] = useState(null)
  const [err, setErr] = useState(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.adminListSeasonAdjustments()
      setList(data || [])
    } catch (e) { setErr(e.message) } finally { setLoading(false) }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const resetForm = () => { setForm(EMPTY_SEASON_FORM); setEditingId(null); setErr(null) }

  const handleSubmit = () => {
    setErr(null)
    if (!form.player_id) return setErr('Choose a player')
    if (!form.season_id) return setErr('Choose a season')
    const payload = Object.fromEntries(Object.entries(form).map(([k, v]) => {
      if (v === '') return [k, k.includes('high_score') || k.includes('best_figures') ? null : 0]
      return [k, v]
    }))
    if (!payload.grade_id) payload.grade_id = null
    if (payload.batting_high_score === '' || payload.batting_high_score === null) payload.batting_high_score = null
    if (payload.bowling_best_wickets === '' || payload.bowling_best_wickets === null) payload.bowling_best_wickets = null
    if (payload.bowling_best_figures === '') payload.bowling_best_figures = null
    onPending({
      title: editingId ? 'Update season adjustment?' : 'Save season adjustment?',
      body: 'This adds to (or overrides) what BetterStats already has for this player in this season. Every change is logged and can be undone from the Audit tab.',
      confirmLabel: editingId ? 'Update' : 'Save',
      action: async () => {
        try {
          if (editingId) await api.adminPatchSeasonAdjustment(editingId, payload)
          else await api.adminCreateSeasonAdjustment(payload)
          await refresh(); refreshAll(); resetForm()
        } catch (e) { setErr(e.message) }
      },
    })
  }

  const handleEdit = (row) => {
    setEditingId(row.id)
    setForm({
      ...EMPTY_SEASON_FORM,
      ...row,
      grade_id: row.grade_id || '',
    })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleDelete = (row) => {
    onPending({
      title: 'Delete this adjustment?',
      body: `Remove the adjustment for ${row.player_name} in ${row.season_name}. This is logged and can be undone from the Audit tab.`,
      confirmLabel: 'Delete',
      danger: true,
      action: async () => {
        try {
          await api.adminDeleteSeasonAdjustment(row.id)
          await refresh(); refreshAll()
        } catch (e) { setErr(e.message) }
      },
    })
  }

  return (
    <div className="space-y-6">
      <div className="bg-pb-surface border pb-hairline rounded-lg p-4">
        <h3 className="text-base font-semibold text-pb-text mb-3">
          {editingId ? 'Edit season adjustment' : 'New season adjustment'}
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className={LABEL_CLS}>Player</label>
            <PlayerPicker players={players} value={form.player_id} onChange={(id) => setForm({ ...form, player_id: id })} />
          </div>
          <div>
            <label className={LABEL_CLS}>Season</label>
            <select className={INPUT_CLS} value={form.season_id} onChange={e => setForm({ ...form, season_id: e.target.value })}>
              <option value="">— Choose a season —</option>
              {seasons.map(s => (<option key={s.id} value={s.id}>{s.name}</option>))}
            </select>
          </div>
          <div>
            <label className={LABEL_CLS}>Grade (optional)</label>
            <input type="text" value={form.grade_id || ''} onChange={e => setForm({ ...form, grade_id: e.target.value })} placeholder="Grade ID — leave blank to apply across all grades" className={INPUT_CLS} />
          </div>
        </div>

        <AggregateFieldGrid form={form} setForm={setForm} includeWidesNoBalls />

        {err && <p className="text-sm text-red-400 mt-3">{err}</p>}

        <div className="flex justify-end gap-2 mt-4">
          {editingId && <button className={BTN_SECONDARY} onClick={resetForm}>Cancel edit</button>}
          <button className={BTN_PRIMARY} onClick={handleSubmit}>
            {editingId ? 'Update adjustment' : 'Save adjustment'}
          </button>
        </div>
      </div>

      <div className="bg-pb-surface border pb-hairline rounded-lg p-4">
        <h3 className="text-base font-semibold text-pb-text mb-3">Existing season adjustments</h3>
        {loading ? <p className="text-sm text-pb-faint">Loading…</p> : (
          list.length === 0 ? (
            <p className="text-sm text-pb-faint">No season adjustments yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-pb-faint font-mono text-[10px] border-b pb-hairline">
                    <th className="text-left py-2 pr-3">Player</th>
                    <th className="text-left py-2 pr-3">Season</th>
                    <th className="text-right py-2 pr-3">Games</th>
                    <th className="text-right py-2 pr-3">Runs</th>
                    <th className="text-right py-2 pr-3">Wkts</th>
                    <th className="text-right py-2 pr-3">Catches</th>
                    <th className="py-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {list.map(r => (
                    <tr key={r.id} className="border-b pb-hairline">
                      <td className="py-2 pr-3 text-pb-text">{r.player_name}</td>
                      <td className="py-2 pr-3 text-pb-faint">{r.season_name}</td>
                      <td className="py-2 pr-3 text-right text-pb-text">{r.games_played}</td>
                      <td className="py-2 pr-3 text-right text-pb-text">{r.batting_runs}</td>
                      <td className="py-2 pr-3 text-right text-pb-text">{r.bowling_wickets}</td>
                      <td className="py-2 pr-3 text-right text-pb-text">{r.fielding_catches}</td>
                      <td className="py-2 text-right">
                        <button className={BTN_SECONDARY + ' mr-2'} onClick={() => handleEdit(r)}>Edit</button>
                        <button className={BTN_DANGER} onClick={() => handleDelete(r)}>Delete</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
      </div>
    </div>
  )
}

// ─── Career adjustments tab ─────────────────────────────────────────────────

function CareerAdjustmentsTab({ players, refreshAll, onPending }) {
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState(EMPTY_CAREER_FORM)
  const [editingId, setEditingId] = useState(null)
  const [err, setErr] = useState(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try { setList(await api.adminListCareerAdjustments() || []) } catch (e) { setErr(e.message) } finally { setLoading(false) }
  }, [])
  useEffect(() => { refresh() }, [refresh])

  const resetForm = () => { setForm(EMPTY_CAREER_FORM); setEditingId(null); setErr(null) }

  const handleSubmit = () => {
    setErr(null)
    if (!form.player_id) return setErr('Choose a player')
    const payload = Object.fromEntries(Object.entries(form).map(([k, v]) => {
      if (v === '') return [k, null]
      return [k, v]
    }))
    onPending({
      title: editingId ? 'Update career adjustment?' : 'Save career adjustment?',
      body: 'Career adjustments apply ONLY to a player\'s career-total view (player profile lifetime totals). They don\'t affect any season leaderboard. Every change is logged and reversible from the Audit tab.',
      confirmLabel: editingId ? 'Update' : 'Save',
      action: async () => {
        try {
          if (editingId) await api.adminPatchCareerAdjustment(editingId, payload)
          else await api.adminCreateCareerAdjustment(payload)
          await refresh(); refreshAll(); resetForm()
        } catch (e) { setErr(e.message) }
      },
    })
  }

  const handleEdit = (row) => {
    setEditingId(row.id)
    setForm({ ...EMPTY_CAREER_FORM, ...row })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleDelete = (row) => {
    onPending({
      title: 'Delete this career adjustment?',
      body: `Remove the career-only delta for ${row.player_name}. This is logged and can be undone from the Audit tab.`,
      confirmLabel: 'Delete',
      danger: true,
      action: async () => {
        try { await api.adminDeleteCareerAdjustment(row.id); await refresh(); refreshAll() }
        catch (e) { setErr(e.message) }
      },
    })
  }

  return (
    <div className="space-y-6">
      <div className="bg-pb-surface border pb-hairline rounded-lg p-4">
        <h3 className="text-base font-semibold text-pb-text mb-3">
          {editingId ? 'Edit career adjustment' : 'New career adjustment'}
        </h3>
        <p className="text-xs text-pb-faint mb-3">
          Use this only when you have career totals (e.g. from a club history book) with no season-by-season detail. Career adjustments do NOT appear in season leaderboards.
        </p>
        <div className="max-w-xs">
          <label className={LABEL_CLS}>Player</label>
          <PlayerPicker players={players} value={form.player_id} onChange={(id) => setForm({ ...form, player_id: id })} />
        </div>

        <AggregateFieldGrid form={form} setForm={setForm} />

        {err && <p className="text-sm text-red-400 mt-3">{err}</p>}

        <div className="flex justify-end gap-2 mt-4">
          {editingId && <button className={BTN_SECONDARY} onClick={resetForm}>Cancel edit</button>}
          <button className={BTN_PRIMARY} onClick={handleSubmit}>
            {editingId ? 'Update adjustment' : 'Save adjustment'}
          </button>
        </div>
      </div>

      <div className="bg-pb-surface border pb-hairline rounded-lg p-4">
        <h3 className="text-base font-semibold text-pb-text mb-3">Existing career adjustments</h3>
        {loading ? <p className="text-sm text-pb-faint">Loading…</p> : (
          list.length === 0 ? (
            <p className="text-sm text-pb-faint">No career adjustments yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-pb-faint font-mono text-[10px] border-b pb-hairline">
                  <th className="text-left py-2 pr-3">Player</th>
                  <th className="text-right py-2 pr-3">Games</th>
                  <th className="text-right py-2 pr-3">Runs</th>
                  <th className="text-right py-2 pr-3">Wkts</th>
                  <th className="text-right py-2 pr-3">Catches</th>
                  <th className="py-2"></th>
                </tr>
              </thead>
              <tbody>
                {list.map(r => (
                  <tr key={r.id} className="border-b pb-hairline">
                    <td className="py-2 pr-3 text-pb-text">{r.player_name}</td>
                    <td className="py-2 pr-3 text-right text-pb-text">{r.games_played}</td>
                    <td className="py-2 pr-3 text-right text-pb-text">{r.batting_runs}</td>
                    <td className="py-2 pr-3 text-right text-pb-text">{r.bowling_wickets}</td>
                    <td className="py-2 pr-3 text-right text-pb-text">{r.fielding_catches}</td>
                    <td className="py-2 text-right">
                      <button className={BTN_SECONDARY + ' mr-2'} onClick={() => handleEdit(r)}>Edit</button>
                      <button className={BTN_DANGER} onClick={() => handleDelete(r)}>Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        )}
      </div>
    </div>
  )
}

// ─── Manual games tab ───────────────────────────────────────────────────────

function emptyBattingRow() {
  return { player_id: '', innings_number: 1, batting_position: '', runs: 0, balls: '', fours: 0, sixes: 0, dismissal_type: '', not_out: false, did_not_bat: false }
}
function emptyBowlingRow() {
  return { player_id: '', innings_number: 1, overs: 0, maidens: 0, runs: 0, wickets: 0, wides: 0, no_balls: 0 }
}
function emptyFieldingRow() {
  return { player_id: '', catches: 0, catches_wk: 0, run_outs: 0, stumpings: 0 }
}

const EMPTY_GAME_FORM = {
  season_id: '', grade_id: '', played_at: '', home_team: '', away_team: '', opposition: '',
  venue: '', result: '', winning_team: '', is_final: false, match_format: '', notes: '',
  batting_innings: [], bowling_spells: [], fielding_stats: [],
}

function ManualGamesTab({ players, seasons, refreshAll, onPending }) {
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState(EMPTY_GAME_FORM)
  const [editingId, setEditingId] = useState(null)
  const [err, setErr] = useState(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try { setList(await api.adminListManualGames() || []) } catch (e) { setErr(e.message) } finally { setLoading(false) }
  }, [])
  useEffect(() => { refresh() }, [refresh])

  const resetForm = () => { setForm(EMPTY_GAME_FORM); setEditingId(null); setErr(null) }

  const buildPayload = () => {
    const sanitize = (rows, mapFn) => rows
      .filter(r => r.player_id)
      .map(r => {
        const out = mapFn(r)
        Object.keys(out).forEach(k => { if (out[k] === '') out[k] = null })
        return out
      })
    return {
      season_id: form.season_id,
      grade_id: form.grade_id || null,
      played_at: form.played_at || null,
      home_team: form.home_team || null,
      away_team: form.away_team || null,
      opposition: form.opposition || null,
      venue: form.venue || null,
      result: form.result || null,
      winning_team: form.winning_team || null,
      is_final: !!form.is_final,
      match_format: form.match_format || null,
      notes: form.notes || null,
      batting_innings: sanitize(form.batting_innings, r => ({ ...r, runs: r.runs || 0, fours: r.fours || 0, sixes: r.sixes || 0 })),
      bowling_spells: sanitize(form.bowling_spells, r => ({ ...r, overs: r.overs || 0, runs: r.runs || 0, wickets: r.wickets || 0 })),
      fielding_stats: sanitize(form.fielding_stats, r => r),
    }
  }

  const handleSubmit = () => {
    setErr(null)
    if (!form.season_id) return setErr('Choose a season')
    const payload = buildPayload()
    if (payload.batting_innings.length === 0 && payload.bowling_spells.length === 0 && payload.fielding_stats.length === 0) {
      return setErr('Add at least one batting, bowling or fielding row.')
    }
    onPending({
      title: editingId ? 'Update manual game?' : 'Save manual game?',
      body: 'A manual game appears in stats aggregations like any other match. Every change is logged and reversible from the Audit tab.',
      confirmLabel: editingId ? 'Update' : 'Save',
      action: async () => {
        try {
          if (editingId) await api.adminPatchManualGame(editingId, payload)
          else await api.adminCreateManualGame(payload)
          await refresh(); refreshAll(); resetForm()
        } catch (e) { setErr(e.message) }
      },
    })
  }

  const handleEdit = async (row) => {
    try {
      const full = await api.adminGetManualGame(row.id)
      setEditingId(row.id)
      setForm({
        ...EMPTY_GAME_FORM,
        ...full,
        grade_id: full.grade_id || '',
        played_at: full.played_at ? full.played_at.split('T')[0] : '',
        batting_innings: (full.batting_innings || []).map(r => ({ ...r, batting_position: r.batting_position || '' })),
        bowling_spells: (full.bowling_spells || []),
        fielding_stats: (full.fielding_stats || []),
      })
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (e) { setErr(e.message) }
  }

  const handleDelete = (row) => {
    onPending({
      title: 'Delete this manual game?',
      body: `Remove the manual game from ${row.played_at || 'date unknown'}${row.opposition ? ` vs ${row.opposition}` : ''}. Reversible from the Audit tab.`,
      confirmLabel: 'Delete',
      danger: true,
      action: async () => {
        try { await api.adminDeleteManualGame(row.id); await refresh(); refreshAll() }
        catch (e) { setErr(e.message) }
      },
    })
  }

  const updateChild = (collection, idx, key, value) => {
    const arr = [...(form[collection] || [])]
    arr[idx] = { ...arr[idx], [key]: value }
    setForm({ ...form, [collection]: arr })
  }
  const addChild = (collection, blankFn) => setForm({ ...form, [collection]: [...(form[collection] || []), blankFn()] })
  const removeChild = (collection, idx) => {
    const arr = [...(form[collection] || [])]
    arr.splice(idx, 1)
    setForm({ ...form, [collection]: arr })
  }

  return (
    <div className="space-y-6">
      <div className="bg-pb-surface border pb-hairline rounded-lg p-4">
        <h3 className="text-base font-semibold text-pb-text mb-3">
          {editingId ? 'Edit manual game' : 'New manual game'}
        </h3>
        <p className="text-xs text-pb-faint mb-3">
          Date, opposition and venue can be left blank if unknown. At least one batting / bowling / fielding row is required.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className={LABEL_CLS}>Season *</label>
            <select className={INPUT_CLS} value={form.season_id} onChange={e => setForm({ ...form, season_id: e.target.value })}>
              <option value="">— Choose a season —</option>
              {seasons.map(s => (<option key={s.id} value={s.id}>{s.name}</option>))}
            </select>
          </div>
          <div>
            <label className={LABEL_CLS}>Date (optional)</label>
            <input type="date" value={form.played_at || ''} onChange={e => setForm({ ...form, played_at: e.target.value })} className={INPUT_CLS} />
          </div>
          <div>
            <label className={LABEL_CLS}>Opposition (optional)</label>
            <input type="text" value={form.opposition || ''} onChange={e => setForm({ ...form, opposition: e.target.value })} className={INPUT_CLS} />
          </div>
          <div>
            <label className={LABEL_CLS}>Home team</label>
            <input type="text" value={form.home_team || ''} onChange={e => setForm({ ...form, home_team: e.target.value })} className={INPUT_CLS} />
          </div>
          <div>
            <label className={LABEL_CLS}>Away team</label>
            <input type="text" value={form.away_team || ''} onChange={e => setForm({ ...form, away_team: e.target.value })} className={INPUT_CLS} />
          </div>
          <div>
            <label className={LABEL_CLS}>Venue</label>
            <input type="text" value={form.venue || ''} onChange={e => setForm({ ...form, venue: e.target.value })} className={INPUT_CLS} />
          </div>
          <div>
            <label className={LABEL_CLS}>Result</label>
            <input type="text" value={form.result || ''} onChange={e => setForm({ ...form, result: e.target.value })} className={INPUT_CLS} />
          </div>
          <div>
            <label className={LABEL_CLS}>Winning team</label>
            <input type="text" value={form.winning_team || ''} onChange={e => setForm({ ...form, winning_team: e.target.value })} className={INPUT_CLS} />
          </div>
          <div>
            <label className={LABEL_CLS}>Match format</label>
            <input type="text" value={form.match_format || ''} onChange={e => setForm({ ...form, match_format: e.target.value })} placeholder="T20 / 40-over / 2-day" className={INPUT_CLS} />
          </div>
          <label className="flex items-center gap-2 text-xs text-pb-text mt-5">
            <input type="checkbox" checked={!!form.is_final} onChange={e => setForm({ ...form, is_final: e.target.checked })} />
            Final
          </label>
        </div>

        <div className="mt-3">
          <label className={LABEL_CLS}>Notes (admin only)</label>
          <textarea rows={2} value={form.notes || ''} onChange={e => setForm({ ...form, notes: e.target.value })} className={INPUT_CLS} />
        </div>

        {/* Batting */}
        <div className="mt-5">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold text-pb-text">Batting</h4>
            <button className={BTN_SECONDARY} onClick={() => addChild('batting_innings', emptyBattingRow)}>+ Add batting row</button>
          </div>
          {(form.batting_innings || []).map((row, idx) => (
            <div key={idx} className="grid grid-cols-12 gap-2 items-end mb-2">
              <div className="col-span-4">
                <PlayerPicker players={players} value={row.player_id} onChange={v => updateChild('batting_innings', idx, 'player_id', v)} />
              </div>
              <div className="col-span-1"><NumberField label="Pos" value={row.batting_position} onChange={v => updateChild('batting_innings', idx, 'batting_position', v)} /></div>
              <div className="col-span-1"><NumberField label="Runs" value={row.runs} onChange={v => updateChild('batting_innings', idx, 'runs', v)} /></div>
              <div className="col-span-1"><NumberField label="Balls" value={row.balls} onChange={v => updateChild('batting_innings', idx, 'balls', v)} /></div>
              <div className="col-span-1"><NumberField label="4s" value={row.fours} onChange={v => updateChild('batting_innings', idx, 'fours', v)} /></div>
              <div className="col-span-1"><NumberField label="6s" value={row.sixes} onChange={v => updateChild('batting_innings', idx, 'sixes', v)} /></div>
              <div className="col-span-2">
                <label className={LABEL_CLS}>How out</label>
                <input type="text" value={row.dismissal_type || ''} onChange={e => updateChild('batting_innings', idx, 'dismissal_type', e.target.value)} placeholder="b Smith / c Jones b Smith / not out" className={INPUT_CLS} />
              </div>
              <div className="col-span-1 flex flex-col gap-1 pb-1">
                <label className="flex items-center gap-1 text-[10px] text-pb-text">
                  <input type="checkbox" checked={!!row.not_out} onChange={e => updateChild('batting_innings', idx, 'not_out', e.target.checked)} />NO
                </label>
                <label className="flex items-center gap-1 text-[10px] text-pb-text">
                  <input type="checkbox" checked={!!row.did_not_bat} onChange={e => updateChild('batting_innings', idx, 'did_not_bat', e.target.checked)} />DNB
                </label>
              </div>
              <div className="col-span-12 -mt-1">
                <button className="text-red-300 text-[11px] hover:underline" onClick={() => removeChild('batting_innings', idx)}>Remove row</button>
              </div>
            </div>
          ))}
        </div>

        {/* Bowling */}
        <div className="mt-5">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold text-pb-text">Bowling</h4>
            <button className={BTN_SECONDARY} onClick={() => addChild('bowling_spells', emptyBowlingRow)}>+ Add bowling row</button>
          </div>
          {(form.bowling_spells || []).map((row, idx) => (
            <div key={idx} className="grid grid-cols-12 gap-2 items-end mb-2">
              <div className="col-span-4">
                <PlayerPicker players={players} value={row.player_id} onChange={v => updateChild('bowling_spells', idx, 'player_id', v)} />
              </div>
              <div className="col-span-1"><NumberField label="Overs" value={row.overs} onChange={v => updateChild('bowling_spells', idx, 'overs', v)} allowDecimal /></div>
              <div className="col-span-1"><NumberField label="M" value={row.maidens} onChange={v => updateChild('bowling_spells', idx, 'maidens', v)} /></div>
              <div className="col-span-1"><NumberField label="Runs" value={row.runs} onChange={v => updateChild('bowling_spells', idx, 'runs', v)} /></div>
              <div className="col-span-1"><NumberField label="Wkts" value={row.wickets} onChange={v => updateChild('bowling_spells', idx, 'wickets', v)} /></div>
              <div className="col-span-1"><NumberField label="Wd" value={row.wides} onChange={v => updateChild('bowling_spells', idx, 'wides', v)} /></div>
              <div className="col-span-1"><NumberField label="Nb" value={row.no_balls} onChange={v => updateChild('bowling_spells', idx, 'no_balls', v)} /></div>
              <div className="col-span-2 pb-1">
                <button className="text-red-300 text-[11px] hover:underline" onClick={() => removeChild('bowling_spells', idx)}>Remove row</button>
              </div>
            </div>
          ))}
        </div>

        {/* Fielding */}
        <div className="mt-5">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-sm font-semibold text-pb-text">Fielding</h4>
            <button className={BTN_SECONDARY} onClick={() => addChild('fielding_stats', emptyFieldingRow)}>+ Add fielding row</button>
          </div>
          {(form.fielding_stats || []).map((row, idx) => (
            <div key={idx} className="grid grid-cols-12 gap-2 items-end mb-2">
              <div className="col-span-4">
                <PlayerPicker players={players} value={row.player_id} onChange={v => updateChild('fielding_stats', idx, 'player_id', v)} />
              </div>
              <div className="col-span-2"><NumberField label="Catches" value={row.catches} onChange={v => updateChild('fielding_stats', idx, 'catches', v)} /></div>
              <div className="col-span-2"><NumberField label="WK catches" value={row.catches_wk} onChange={v => updateChild('fielding_stats', idx, 'catches_wk', v)} /></div>
              <div className="col-span-1"><NumberField label="RO" value={row.run_outs} onChange={v => updateChild('fielding_stats', idx, 'run_outs', v)} /></div>
              <div className="col-span-1"><NumberField label="St" value={row.stumpings} onChange={v => updateChild('fielding_stats', idx, 'stumpings', v)} /></div>
              <div className="col-span-2 pb-1">
                <button className="text-red-300 text-[11px] hover:underline" onClick={() => removeChild('fielding_stats', idx)}>Remove row</button>
              </div>
            </div>
          ))}
        </div>

        {err && <p className="text-sm text-red-400 mt-3">{err}</p>}

        <div className="flex justify-end gap-2 mt-4">
          {editingId && <button className={BTN_SECONDARY} onClick={resetForm}>Cancel edit</button>}
          <button className={BTN_PRIMARY} onClick={handleSubmit}>
            {editingId ? 'Update manual game' : 'Save manual game'}
          </button>
        </div>
      </div>

      <div className="bg-pb-surface border pb-hairline rounded-lg p-4">
        <h3 className="text-base font-semibold text-pb-text mb-3">Existing manual games</h3>
        {loading ? <p className="text-sm text-pb-faint">Loading…</p> : (
          list.length === 0 ? (
            <p className="text-sm text-pb-faint">No manual games yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-pb-faint font-mono text-[10px] border-b pb-hairline">
                  <th className="text-left py-2 pr-3">Date</th>
                  <th className="text-left py-2 pr-3">Opposition</th>
                  <th className="text-left py-2 pr-3">Season</th>
                  <th className="text-right py-2 pr-3">Players</th>
                  <th className="py-2"></th>
                </tr>
              </thead>
              <tbody>
                {list.map(r => (
                  <tr key={r.id} className="border-b pb-hairline">
                    <td className="py-2 pr-3 text-pb-text">{r.played_at ? r.played_at.split('T')[0] : '—'}</td>
                    <td className="py-2 pr-3 text-pb-faint">{r.opposition || '—'}</td>
                    <td className="py-2 pr-3 text-pb-faint">{r.season_name}</td>
                    <td className="py-2 pr-3 text-right text-pb-text">{r.batting_count}</td>
                    <td className="py-2 text-right">
                      <button className={BTN_SECONDARY + ' mr-2'} onClick={() => handleEdit(r)}>Edit</button>
                      <button className={BTN_DANGER} onClick={() => handleDelete(r)}>Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        )}
      </div>
    </div>
  )
}

// ─── Audit tab ──────────────────────────────────────────────────────────────

function AuditTab({ refreshAll, onPending }) {
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try { setList(await api.adminListManualEntryAudit() || []) } catch (e) { setErr(e.message) } finally { setLoading(false) }
  }, [])
  useEffect(() => { refresh() }, [refresh])

  const handleUndo = (row) => {
    onPending({
      title: 'Undo this change?',
      body: `Reverse: ${row.summary}\n\nThis will reapply the prior state and mark the entry as undone.`,
      confirmLabel: 'Undo',
      danger: true,
      action: async () => {
        try { await api.adminUndoManualEntry(row.id); await refresh(); refreshAll() }
        catch (e) { setErr(e.message) }
      },
    })
  }

  return (
    <div className="bg-pb-surface border pb-hairline rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-base font-semibold text-pb-text">Manual entry audit log</h3>
        <button className={BTN_SECONDARY} onClick={refresh}>Refresh</button>
      </div>
      {err && <p className="text-sm text-red-400 mb-2">{err}</p>}
      {loading ? <p className="text-sm text-pb-faint">Loading…</p> : (
        list.length === 0 ? (
          <p className="text-sm text-pb-faint">No manual edits yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-pb-faint font-mono text-[10px] border-b pb-hairline">
                  <th className="text-left py-2 pr-3">When</th>
                  <th className="text-left py-2 pr-3">By</th>
                  <th className="text-left py-2 pr-3">Action</th>
                  <th className="text-left py-2 pr-3">Summary</th>
                  <th className="text-left py-2 pr-3">Status</th>
                  <th className="py-2"></th>
                </tr>
              </thead>
              <tbody>
                {list.map(r => (
                  <tr key={r.id} className="border-b pb-hairline">
                    <td className="py-2 pr-3 text-pb-faint font-mono text-[11px]">
                      {r.created_at ? new Date(r.created_at).toLocaleString() : '—'}
                    </td>
                    <td className="py-2 pr-3 text-pb-text text-xs">{r.user_name || '—'}</td>
                    <td className="py-2 pr-3 text-pb-faint text-xs uppercase font-mono">{r.action}</td>
                    <td className="py-2 pr-3 text-pb-text">{r.summary}</td>
                    <td className="py-2 pr-3">
                      {r.undone_at
                        ? <span className="text-[11px] text-pb-faint">undone</span>
                        : <span className="text-[11px] text-pb-text">live</span>}
                    </td>
                    <td className="py-2 text-right">
                      {!r.undone_at && (
                        <button className={BTN_DANGER} onClick={() => handleUndo(r)}>Undo</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  )
}

// ─── Main page ──────────────────────────────────────────────────────────────

export default function AdminManualEntries() {
  const [activeTab, setActiveTab] = useState(() => {
    return window.location.hash.replace('#', '') || 'season'
  })
  const [players, setPlayers] = useState([])
  const [seasons, setSeasons] = useState([])
  const [pending, setPending] = useState(null)
  const [tick, setTick] = useState(0)

  const refreshAll = useCallback(() => setTick(t => t + 1), [])

  useEffect(() => {
    ;(async () => {
      try {
        const [p, s] = await Promise.all([api.adminListPlayers(), api.adminListSeasons()])
        setPlayers((p || []).filter(x => x.is_player !== false))
        setSeasons(s || [])
      } catch {}
    })()
  }, [])

  useEffect(() => {
    window.location.hash = activeTab
  }, [activeTab])

  const onPending = (p) => setPending(p)
  const confirmPending = async () => {
    if (!pending) return
    const action = pending.action
    setPending(null)
    if (action) await action()
  }

  return (
    <AdminLayout>
      <div className="p-4 md:p-6 max-w-6xl">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-pb-text mb-1">Manual stat entries</h1>
          <p className="text-sm text-pb-faint max-w-2xl">
            Add historical games and stats that aren't in the upstream feed.
            Every change is logged and reversible — sync never touches this data.
          </p>
        </div>

        <div className="border-b pb-hairline mb-5 flex flex-wrap gap-x-6">
          {TABS.map(t => (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key)}
              className={`pb-3 -mb-px text-sm font-semibold border-b-2 transition-colors ${activeTab === t.key ? 'border-pb-accent text-pb-text' : 'border-transparent text-pb-faint hover:text-pb-text'}`}
            >{t.label}</button>
          ))}
        </div>

        <p className="text-xs text-pb-faintest mb-4">{TABS.find(t => t.key === activeTab)?.hint}</p>

        {activeTab === 'season' && (
          <SeasonAdjustmentsTab key={tick + ':season'} players={players} seasons={seasons} refreshAll={refreshAll} onPending={onPending} />
        )}
        {activeTab === 'career' && (
          <CareerAdjustmentsTab key={tick + ':career'} players={players} refreshAll={refreshAll} onPending={onPending} />
        )}
        {activeTab === 'game' && (
          <ManualGamesTab key={tick + ':game'} players={players} seasons={seasons} refreshAll={refreshAll} onPending={onPending} />
        )}
        {activeTab === 'audit' && (
          <AuditTab key={tick + ':audit'} refreshAll={refreshAll} onPending={onPending} />
        )}

        <ConfirmModal
          open={!!pending}
          title={pending?.title || 'Confirm'}
          body={pending?.body || ''}
          confirmLabel={pending?.confirmLabel || 'Confirm'}
          danger={pending?.danger}
          onConfirm={confirmPending}
          onCancel={() => setPending(null)}
        />
      </div>
    </AdminLayout>
  )
}
