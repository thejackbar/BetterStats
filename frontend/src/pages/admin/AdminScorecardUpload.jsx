import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import AdminLayout from '../../components/admin/AdminLayout'
import { formatSeason } from '../../lib/cricketFormat'

const INPUT_CLS = 'w-full bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent'
const SMALL_INPUT = 'w-full bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-2 py-1 focus:outline-none focus:border-pb-accent'
const LABEL_CLS = 'font-mono text-[10px] text-pb-faint block mb-1'
const BTN_PRIMARY = 'inline-flex items-center px-4 py-2 bg-pb-accent text-white text-sm font-semibold rounded hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed'
const BTN_SECONDARY = 'inline-flex items-center px-3 py-1.5 border pb-hairline text-pb-text text-xs rounded hover:bg-pb-surface2'
const TH = 'text-left font-mono text-[10px] text-pb-faint font-normal px-2 py-1'
const TD = 'px-2 py-1 align-top'

// Derive the AU season start year from a match date: a Sep–Dec game belongs to that
// year's summer, a Jan–Aug game to the previous year's (so 2020-03-14 → 2019/20 → 2019).
function seasonStartYear(iso) {
  const d = iso && /^\d{4}-\d{2}-\d{2}/.test(iso) ? new Date(iso) : null
  if (!d || isNaN(d)) return null
  const m = d.getMonth() + 1
  return m >= 9 ? d.getFullYear() : d.getFullYear() - 1
}

function num(v) {
  if (v === '' || v === null || v === undefined) return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

// ─── Dismissals ────────────────────────────────────────────────────────────────
// Known modes for the dropdown. `fielder`/`bowler` say which of the two columns
// apply: a bowled has a bowler but no fielder, a run out a fielder but no bowler,
// a not out neither. '' is the "unknown / incomplete card" option, where everything
// stays blank. Values match the backend dismissal parser's method strings.
const DISMISSAL_MODES = [
  { value: '', label: '— unknown —', fielder: false, bowler: false },
  { value: 'caught', label: 'Caught (c)', fielder: true, bowler: true },
  { value: 'caught & bowled', label: 'Caught & bowled (c & b)', fielder: false, bowler: true },
  { value: 'bowled', label: 'Bowled (b)', fielder: false, bowler: true },
  { value: 'lbw', label: 'LBW', fielder: false, bowler: true },
  { value: 'stumped', label: 'Stumped (st)', fielder: true, bowler: true },
  { value: 'run out', label: 'Run out', fielder: true, bowler: false },
  { value: 'hit wicket', label: 'Hit wicket', fielder: false, bowler: true },
  { value: 'not out', label: 'Not out', fielder: false, bowler: false },
  { value: 'retired', label: 'Retired', fielder: false, bowler: false },
  { value: 'did not bat', label: 'Did not bat', fielder: false, bowler: false },
  { value: 'absent', label: 'Absent', fielder: false, bowler: false },
]
const MODE_BY_VALUE = Object.fromEntries(DISMISSAL_MODES.map(m => [m.value, m]))
const modeHasFielder = v => !!MODE_BY_VALUE[(v || '').toLowerCase()]?.fielder
const modeHasBowler = v => !!MODE_BY_VALUE[(v || '').toLowerCase()]?.bowler

// Read a dismissal string into {mode, fielder, bowler}. Mirrors the backend
// _parse_dismissal so the on-card text and the split columns always agree.
function parseDismissalText(text) {
  const s = (text || '').replace(/\s+/g, ' ').trim()
  const sl = s.toLowerCase()
  if (!sl) return { mode: '', fielder: '', bowler: '' }
  if (sl.includes('not out')) return { mode: 'not out', fielder: '', bowler: '' }
  if (sl === 'dnb' || sl === 'did not bat') return { mode: 'did not bat', fielder: '', bowler: '' }
  if (sl.startsWith('absent')) return { mode: 'absent', fielder: '', bowler: '' }
  if (sl.startsWith('retired')) return { mode: 'retired', fielder: '', bowler: '' }
  let m
  if ((m = s.match(/^c(?:aught)?\s*(?:&|and|\+)\s*b(?:owled)?\.?\s+(.+)$/i))) return { mode: 'caught & bowled', fielder: m[1].trim(), bowler: m[1].trim() }
  if ((m = s.match(/^st(?:umped)?\.?\s+(.+?)\s+b(?:owled)?\.?\s+(.+)$/i))) return { mode: 'stumped', fielder: m[1].trim(), bowler: m[2].trim() }
  if ((m = s.match(/^c(?:aught)?\.?\s+(.+?)\s+b(?:owled)?\.?\s+(.+)$/i))) return { mode: 'caught', fielder: m[1].trim(), bowler: m[2].trim() }
  if ((m = s.match(/^hit\s*wicket(?:\s+b(?:owled)?\.?\s+(.+))?$/i))) return { mode: 'hit wicket', fielder: '', bowler: (m[1] || '').trim() }
  if ((m = s.match(/^lbw(?:\s+b(?:owled)?\.?\s+(.+))?$/i))) return { mode: 'lbw', fielder: '', bowler: (m[1] || '').trim() }
  if ((m = s.match(/^(?:run\s*out|ro)\b\s*\(?\s*([^)]*)\)?$/i))) return { mode: 'run out', fielder: (m[1] || '').trim(), bowler: '' }
  if ((m = s.match(/^b(?:owled)?\.?\s+(.+)$/i))) return { mode: 'bowled', fielder: '', bowler: m[1].trim() }
  return { mode: '', fielder: '', bowler: '' }
}

// Fall back to the model's structured how_out when there's no dismissal text.
function modeFromHowOut(how) {
  const h = (how || '').toLowerCase().trim()
  if (!h) return ''
  if (h.includes('not out')) return 'not out'
  if (h.includes('did not bat') || h === 'dnb') return 'did not bat'
  if (h.includes('absent')) return 'absent'
  if (h.includes('retired')) return 'retired'
  if (h.includes('hit wicket')) return 'hit wicket'
  if (h.includes('&') || h.includes('and bowled')) return 'caught & bowled'
  if (h.includes('stump') || h === 'st') return 'stumped'
  if (h.includes('run')) return 'run out'
  if (h.includes('lbw')) return 'lbw'
  if (h.includes('caught') || h === 'c') return 'caught'
  if (h.includes('bowled') || h === 'b') return 'bowled'
  return ''
}

// Build the canonical dismissal string from the split parts, e.g.
// ('caught','Smith','Jones') → 'c Smith b Jones'. Empty mode → '' (incomplete card).
function composeDismissal(mode, fielder, bowler) {
  const m = (mode || '').toLowerCase().trim()
  const f = (fielder || '').trim()
  const b = (bowler || '').trim()
  if (!m) return ''
  if (m === 'not out') return 'not out'
  if (m === 'did not bat') return 'did not bat'
  if (m === 'absent') return 'absent'
  if (m === 'retired') return 'retired not out'
  if (m === 'run out') return f ? `run out (${f})` : 'run out'
  if (m === 'caught & bowled') return b ? `c & b ${b}` : 'c & b'
  if (m === 'stumped') return b ? `st ${f} b ${b}`.replace(/\s+/g, ' ').trim() : (f ? `st ${f}` : 'stumped')
  if (m === 'lbw') return b ? `lbw b ${b}` : 'lbw'
  if (m === 'hit wicket') return b ? `hit wicket b ${b}` : 'hit wicket'
  if (m === 'caught') return (f && b) ? `c ${f} b ${b}` : (b ? `c b ${b}` : (f ? `c ${f}` : 'caught'))
  if (m === 'bowled') return b ? `b ${b}` : 'bowled'
  return mode
}

function ModeSelect({ value, onChange }) {
  return (
    <select className={`${SMALL_INPUT} min-w-[120px]`} value={value || ''} onChange={e => onChange(e.target.value)}>
      {DISMISSAL_MODES.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
    </select>
  )
}

// ─── Opposition club search (CA / Grassroots, same lookup onboarding uses) ──────
function OppClubSearch({ value, onPick }) {
  const [q, setQ] = useState(value || '')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const ref = useRef(null)

  useEffect(() => { setQ(value || '') }, [value])

  useEffect(() => {
    if (!open) return
    const term = q.trim()
    if (term.length < 2) { setResults([]); return }
    const t = setTimeout(async () => {
      setLoading(true)
      try { setResults(await api.searchOrgs(term) || []) } catch { setResults([]) } finally { setLoading(false) }
    }, 300)
    return () => clearTimeout(t)
  }, [q, open])

  return (
    <div ref={ref} className="relative">
      <input
        className={INPUT_CLS}
        value={q}
        placeholder="Search Cricket Australia clubs…"
        onChange={e => { setQ(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 200)}
      />
      {open && (results.length > 0 || loading) && (
        <div className="absolute z-20 mt-1 w-full bg-pb-surface border pb-hairline rounded shadow-lg max-h-56 overflow-auto">
          {loading && <div className="px-3 py-2 text-xs text-pb-faint">Searching…</div>}
          {results.map(org => (
            <button
              key={org.id}
              className="block w-full text-left px-3 py-2 text-sm text-pb-text hover:bg-pb-surface2"
              onMouseDown={() => { onPick(org); setOpen(false) }}
            >
              {org.name || org.shortName}
              {org.shortName && org.name !== org.shortName ? <span className="text-pb-faint text-xs"> · {org.shortName}</span> : null}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Player picker for our rows (searchable, like the app's player search) ──────
// `candidates` are the backend's close matches for this card name (same fuzzy
// engine as historical imports and Merge Players) — shown first with their
// confidence, so a near-miss spelling is one click instead of a search.
function PlayerSelect({ value, roster, cardName, onChange, candidates = [] }) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const selected = roster.find(p => p.id === value)
  const t = q.trim().toLowerCase()
  const matches = (t ? roster.filter(p => (p.name || '').toLowerCase().includes(t)) : roster).slice(0, 40)
  const cands = t ? [] : candidates.filter(c => roster.some(p => p.id === c.player_id))
  return (
    <div ref={ref} className="relative">
      <input
        className={`${SMALL_INPUT} ${value ? '' : 'border-amber-400/50'}`}
        value={open ? q : (selected ? selected.name : '')}
        placeholder={cardName ? `match: ${cardName}` : 'search player…'}
        onChange={e => { setQ(e.target.value); setOpen(true) }}
        onFocus={() => { setQ(''); setOpen(true) }}
        onBlur={() => setTimeout(() => setOpen(false), 180)}
        title={cardName ? `Card: ${cardName}` : ''}
      />
      {open && (
        <div className="absolute z-30 mt-1 w-full min-w-[190px] bg-pb-surface border pb-hairline rounded shadow-lg max-h-56 overflow-auto">
          {value && (
            <button type="button" className="block w-full text-left px-3 py-1.5 text-xs text-pb-faint hover:bg-pb-surface2"
              onMouseDown={() => { onChange(''); setOpen(false) }}>— clear —</button>
          )}
          {cands.length > 0 && (
            <>
              <div className="px-3 pt-1.5 pb-0.5 font-mono text-[9px] text-pb-faint">CLOSE MATCHES</div>
              {cands.map(c => (
                <button type="button" key={`cand-${c.player_id}`}
                  className="block w-full text-left px-3 py-1.5 text-sm text-pb-text hover:bg-pb-surface2"
                  onMouseDown={() => { onChange(c.player_id); setOpen(false) }}>
                  {c.name}
                  {c.confidence != null && <span className="text-pb-faint text-xs"> · {Math.round(c.confidence * 100)}%</span>}
                </button>
              ))}
              <div className="border-t pb-hairline" />
            </>
          )}
          {matches.length === 0
            ? <div className="px-3 py-2 text-xs text-pb-faint">No match</div>
            : matches.map(p => (
              <button type="button" key={p.id}
                className="block w-full text-left px-3 py-1.5 text-sm text-pb-text hover:bg-pb-surface2"
                onMouseDown={() => { onChange(p.id); setOpen(false) }}>{p.name}</button>
            ))}
        </div>
      )}
    </div>
  )
}

// ─── Uploaded scorecards log ────────────────────────────────────────────────
// Every import (this page or the Manual Games tab) lands in the same manual_games
// table; this list is filtered to just the ones read off a photo (is_photo_upload),
// which is what "uploaded scorecards" means on this specific page. A hand-typed
// manual game still shows on /admin/manual-entries#game, not duplicated here.
function UploadsLog({ uploads, loading, err, onEdit, onDelete }) {
  if (loading) return <p className="text-sm text-pb-faint">Loading…</p>
  if (err) return <p className="text-sm text-red-400">{err}</p>
  if (uploads.length === 0) return <p className="text-sm text-pb-faint">No scorecards uploaded yet.</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-pb-faint font-mono text-[10px] border-b pb-hairline">
            <th className="text-left py-2 pr-3">Date</th>
            <th className="text-left py-2 pr-3">Opposition</th>
            <th className="text-left py-2 pr-3">Season</th>
            <th className="text-left py-2 pr-3">Uploaded</th>
            <th className="text-right py-2 pr-3">Players</th>
            <th className="py-2"></th>
          </tr>
        </thead>
        <tbody>
          {uploads.map(r => (
            <tr key={r.id} className="border-b pb-hairline">
              <td className="py-2 pr-3 text-pb-text">{r.played_at ? r.played_at.split('T')[0] : '—'}</td>
              <td className="py-2 pr-3 text-pb-faint">{r.opposition || '—'}</td>
              <td className="py-2 pr-3 text-pb-faint">{formatSeason(r.season_name)}</td>
              <td className="py-2 pr-3 text-pb-faintest text-xs">
                {r.created_at ? new Date(r.created_at).toLocaleDateString() : '—'}
                {r.created_by_name ? <span> · {r.created_by_name}</span> : ''}
              </td>
              <td className="py-2 pr-3 text-right text-pb-text">{r.batting_count}</td>
              <td className="py-2 text-right whitespace-nowrap">
                <Link to={`/games/${r.id}`} target="_blank" className={BTN_SECONDARY + ' mr-2'}>View</Link>
                <button className={BTN_SECONDARY + ' mr-2'} onClick={() => onEdit(r)}>Edit</button>
                <button className="inline-flex items-center px-3 py-1.5 border border-red-400/40 text-red-300 text-xs rounded hover:bg-red-500/10" onClick={() => onDelete(r)}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-[11px] text-pb-faintest mt-3">
        Every change here is logged and can be undone from{' '}
        <Link to="/admin/manual-entries#audit" className="underline">Manual Entries → Audit &amp; Undo</Link>.
      </p>
    </div>
  )
}

function DeleteConfirmModal({ row, onConfirm, onCancel, busy }) {
  if (!row) return null
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center px-4" onClick={onCancel}>
      <div className="bg-pb-surface border pb-hairline rounded-lg max-w-md w-full p-5" onClick={e => e.stopPropagation()}>
        <h3 className="text-lg font-semibold text-pb-text mb-2">Delete this scorecard?</h3>
        <p className="text-sm text-pb-faint mb-4">
          Remove the uploaded game from {row.played_at ? row.played_at.split('T')[0] : 'date unknown'}
          {row.opposition ? ` vs ${row.opposition}` : ''}. This is logged and can be undone from the Manual Entries audit tab.
        </p>
        <div className="flex justify-end gap-2">
          <button className={BTN_SECONDARY} onClick={onCancel}>Cancel</button>
          <button
            className="inline-flex items-center px-3 py-1.5 border border-red-400/40 text-red-300 text-xs rounded hover:bg-red-500/10"
            disabled={busy}
            onClick={onConfirm}
          >{busy ? 'Deleting…' : 'Delete'}</button>
        </div>
      </div>
    </div>
  )
}

export default function AdminScorecardUpload() {
  const [step, setStep] = useState('upload')   // upload | review | done
  const [files, setFiles] = useState([])
  const [previews, setPreviews] = useState([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const [seasons, setSeasons] = useState([])
  const [grades, setGrades] = useState([])
  const [allPlayers, setAllPlayers] = useState([])  // {id, name} — roster source when re-editing (no fresh OCR read)

  const [extract, setExtract] = useState(null)  // raw response
  const [roster, setRoster] = useState([])
  const [match, setMatch] = useState({})
  const [innings, setInnings] = useState([])
  // Catches behind the stumps, per player id. The one fielding figure that can't be
  // read off a dismissal ('c wk' isn't always marked); everything else is derived.
  const [wkByPid, setWkByPid] = useState({})
  // Fielding read straight off the card (an OWN CATCHES column on a match-summary
  // form) rather than derived from dismissals. Editable rows the admin matches to
  // the roster — merged with the dismissal-derived rows at import (max per stat, so
  // the two sources never double-count the same catch).
  const [fieldingExtra, setFieldingExtra] = useState([])
  // Which optional stat columns this card actually tracks. Unticked → the column
  // is hidden on review and imports as null ("not recorded"), never a fake 0 —
  // a summary form has no 4s/6s or maidens at all. Defaults come from whether
  // the reader found any value for the field.
  const ALL_TRACKED = { balls: true, boundaries: true, maidens: true, bowler_extras: true }
  const [tracked, setTracked] = useState(ALL_TRACKED)
  const [warnings, setWarnings] = useState([])

  const [form, setForm] = useState({ season_id: '', grade_id: '', played_at: '', venue: '', result: '', winning_team: '', is_final: false, match_format: '', opp_name: '', opp_org_id: '' })
  const [confirm, setConfirm] = useState(false)
  const [createdId, setCreatedId] = useState(null)
  const [dupes, setDupes] = useState([])

  // editingId is set when we've jumped back into an already-saved upload from the
  // log below, rather than reading a fresh photo — doImport then PATCHes it in place.
  const [editingId, setEditingId] = useState(null)

  const [uploads, setUploads] = useState([])
  const [uploadsLoading, setUploadsLoading] = useState(true)
  const [uploadsErr, setUploadsErr] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [deleteBusy, setDeleteBusy] = useState(false)

  const loadUploads = useCallback(async () => {
    setUploadsLoading(true); setUploadsErr(null)
    try {
      const rows = await api.adminListManualGames()
      setUploads((rows || []).filter(r => r.is_photo_upload))
    } catch (e) { setUploadsErr(e.message) } finally { setUploadsLoading(false) }
  }, [])

  // Warn if this club already has a game on that date — an uploaded game counts on
  // top of what's already there, so importing one that's already synced (or uploaded)
  // double-counts it. Excludes the game itself when re-editing an existing upload.
  useEffect(() => {
    if (step !== 'review' || !form.played_at) { setDupes([]); return }
    let cancelled = false
    const t = setTimeout(async () => {
      try {
        const res = await api.adminCheckScorecardDuplicate(form.played_at, form.opp_name || '', editingId || '')
        if (!cancelled) setDupes(res.matches || [])
      } catch { if (!cancelled) setDupes([]) }
    }, 400)
    return () => { cancelled = true; clearTimeout(t) }
  }, [step, form.played_at, form.opp_name, editingId])

  useEffect(() => {
    ;(async () => {
      try {
        const [s, g, p] = await Promise.all([api.adminListSeasons(), api.adminListGradesBySeason(), api.adminListPlayers()])
        setSeasons(s || []); setGrades(g || [])
        setAllPlayers((p || []).filter(x => x.is_player !== false).map(x => ({ id: x.id, name: x.display_name })))
      } catch {}
    })()
    loadUploads()
  }, [loadUploads])

  // Jump back into a previously uploaded scorecard for editing. The reviewed
  // match+innings shape is preserved verbatim in extracted_payload from the original
  // read, so this re-opens the exact same review screen instead of re-reading the photo.
  const handleEditUpload = async (row) => {
    setErr(null)
    try {
      const full = await api.adminGetManualGame(row.id)
      const payload = full.extracted_payload || {}
      setExtract({ suggestions: {}, read_notes: null })
      setRoster(allPlayers)
      setMatch(payload.match || {})
      setInnings(payload.innings || [])
      setWkByPid(Object.fromEntries((full.fielding_stats || []).map(f => [f.player_id, f.catches_wk || 0])))
      // Re-seed the card-read fielding from what was saved, so a re-save can't drop
      // fielding that originally came off an own-catches column (the dismissal-derived
      // rows alone wouldn't cover it, and import merges by max per stat).
      setFieldingExtra((full.fielding_stats || []).map(f => ({
        name: (allPlayers.find(p => p.id === f.player_id)?.name) || '',
        player_id: f.player_id,
        catches: f.catches || 0, catches_wk: f.catches_wk || 0,
        stumpings: f.stumpings || 0, run_outs: f.run_outs || 0,
      })))
      // Recover the tracked-columns choice from what the last save stored:
      // null = wasn't tracked. No rows at all → leave everything on.
      const bat = full.batting_innings || [], bowl = full.bowling_spells || []
      setTracked({
        balls: bat.length ? bat.some(r => r.balls != null) : true,
        boundaries: bat.length ? bat.some(r => r.fours != null || r.sixes != null) : true,
        maidens: bowl.length ? bowl.some(r => r.maidens != null) : true,
        bowler_extras: bowl.length ? bowl.some(r => r.wides != null || r.no_balls != null) : true,
      })
      setWarnings([])
      setForm({
        season_id: full.season_id || '',
        grade_id: full.grade_id || '',
        played_at: full.played_at ? full.played_at.split('T')[0] : '',
        venue: full.venue || '',
        result: full.result || '',
        winning_team: full.winning_team || '',
        is_final: !!full.is_final,
        match_format: full.match_format || '',
        opp_name: full.opposition || '',
        opp_org_id: full.opp_org_id || '',
      })
      setEditingId(row.id)
      setCreatedId(row.id)
      setStep('review')
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (e) { setErr(e.message || 'Could not load this scorecard.') }
  }

  const handleDeleteUpload = async () => {
    if (!deleteTarget) return
    setDeleteBusy(true)
    try {
      await api.adminDeleteManualGame(deleteTarget.id)
      setDeleteTarget(null)
      await loadUploads()
    } catch (e) { setErr(e.message || 'Delete failed.') } finally { setDeleteBusy(false) }
  }

  const seasonGrades = useMemo(
    () => (grades || []).filter(g => g.season_id === form.season_id),
    [grades, form.season_id]
  )

  function onFiles(list) {
    const arr = Array.from(list || [])
    setFiles(arr)
    setPreviews(arr.map(f => ({
      name: f.name,
      url: URL.createObjectURL(f),
      isPdf: f.type === 'application/pdf' || /\.pdf$/i.test(f.name || ''),
    })))
  }

  const runExtract = async () => {
    if (!files.length) { setErr('Add at least one scorecard photo.'); return }
    setErr(null); setBusy(true)
    setEditingId(null); setCreatedId(null)  // a fresh read always creates a new game, never patches a prior edit target
    try {
      const data = await api.adminExtractScorecard(files)
      setExtract(data)
      setRoster(data.roster || [])
      setMatch(data.match || {})
      setWarnings(data.warnings || [])

      const sugg = data.suggestions || {}
      const inns = (data.innings || []).map(inn => ({
        ...inn,
        batting: (inn.batting || []).map(b => prepBattingRow(b, inn.is_our_team, sugg)),
        bowling: (inn.bowling || []).map(b => ({ ...b, player_id: !inn.is_our_team ? (sugg[b.name] || '') : undefined })),
      }))
      setInnings(inns)
      setWkByPid({})
      // Fielding the card lists separately from dismissals (an own-catches column):
      // ours is whatever's attached to an innings where we FIELDED (not batting).
      setFieldingExtra((data.innings || [])
        .filter(inn => !inn.is_our_team)
        .flatMap(inn => inn.fielding || [])
        .map(f => ({
          name: f.name || '',
          player_id: sugg[f.name] || '',
          catches: f.catches ?? '', catches_wk: f.catches_wk ?? '',
          stumpings: f.stumpings ?? '', run_outs: f.run_outs ?? '',
        })))
      // Default the tracked-columns toggles to what the reader actually found —
      // a card with no 4s/6s or maidens anywhere starts with those unticked.
      const anyBat = f => (data.innings || []).some(inn => (inn.batting || []).some(b => b[f] != null))
      const anyBowl = f => (data.innings || []).some(inn => (inn.bowling || []).some(b => b[f] != null))
      setTracked({
        balls: anyBat('balls'),
        boundaries: anyBat('fours') || anyBat('sixes'),
        maidens: anyBowl('maidens'),
        bowler_extras: anyBowl('wides') || anyBowl('no_balls'),
      })

      // Best-effort defaults: date, opponent name, season.
      const oppName = data.match?.our_team
        ? ([data.match?.home_team, data.match?.away_team].find(t => t && t !== data.match.our_team) || '')
        : (data.match?.away_team || '')
      const yr = seasonStartYear(data.match?.date)
      const seasonHit = yr != null ? (seasons.find(s => s.year === yr) || null) : null
      setForm(f => ({
        ...f,
        played_at: data.match?.date || '',
        venue: data.match?.venue || '',
        winning_team: data.match?.winning_team || '',
        result: data.match?.result || '',
        opp_name: oppName,
        season_id: seasonHit ? seasonHit.id : f.season_id,
      }))
      setStep('review')
    } catch (e) {
      setErr(e.message || 'Could not read the scorecard.')
    } finally { setBusy(false) }
  }

  const rosterName = useCallback(id => (roster.find(p => p.id === id)?.name) || '', [roster])
  // Close-match candidates for a card name (the historical-import fuzzy engine,
  // returned by the extract endpoint) — shown at the top of each player picker.
  const candsFor = useCallback(name => (extract?.match_info?.[name]?.candidates) || [], [extract])

  // Normalise one extracted batting row into the split-dismissal shape: a canonical
  // `how_out` mode + fielder/bowler. For an opposition innings the fielder/bowler are
  // OUR players, so pre-match them to the roster (fielder_id/bowler_id); for our innings
  // they're the opposition's, kept as free text.
  function prepBattingRow(b, isOur, sugg) {
    const parsed = parseDismissalText(b.dismissal_text)
    let how_out = parsed.mode || modeFromHowOut(b.how_out)
    if (b.not_out) how_out = 'not out'
    if (b.did_not_bat) how_out = 'did not bat'
    const fielder = parsed.fielder || b.fielder || ''
    const bowler = parsed.bowler || b.bowler || ''
    const row = {
      ...b,
      player_id: isOur ? (sugg[b.name] || '') : undefined,
      how_out, fielder, bowler,
      dismissal_text: b.dismissal_text || composeDismissal(how_out, fielder, bowler),
    }
    if (!isOur) {
      row.fielder_id = sugg[fielder] || sugg[b.fielder] || ''
      row.bowler_id = sugg[bowler] || sugg[b.bowler] || ''
    }
    return row
  }

  // ─── immutable editors ───────────────────────────────────────────────────────
  const editInn = (idx, patch) => setInnings(prev => prev.map((x, i) => i === idx ? { ...x, ...patch } : x))
  const editFieldingExtra = (idx, patch) => setFieldingExtra(prev => prev.map((x, i) => i === idx ? { ...x, ...patch } : x))
  const editRow = (innIdx, kind, rowIdx, patch) => setInnings(prev => prev.map((x, i) => {
    if (i !== innIdx) return x
    const rows = (x[kind] || []).map((r, j) => j === rowIdx ? { ...r, ...patch } : r)
    return { ...x, [kind]: rows }
  })
  )

  // Mark an innings as ours / the opposition's and re-flow the player matching:
  // batters match the roster when it's our innings, bowlers when it's the opposition's,
  // and a dismissal's fielder/bowler become our roster picks for an opposition innings.
  const setInningsTeam = (idx, isOur) => setInnings(prev => prev.map((x, i) => {
    if (i !== idx) return x
    const sugg = extract?.suggestions || {}
    const batting = (x.batting || []).map(b => {
      const row = { ...b }
      if (isOur) {
        row.player_id = b.player_id || sugg[b.name] || ''
        delete row.fielder_id
        delete row.bowler_id
      } else {
        row.player_id = undefined
        row.fielder_id = b.fielder_id || sugg[b.fielder] || ''
        row.bowler_id = b.bowler_id || sugg[b.bowler] || ''
      }
      return row
    })
    const bowling = (x.bowling || []).map(b => ({ ...b, player_id: !isOur ? (b.player_id || sugg[b.name] || '') : undefined }))
    return { ...x, is_our_team: isOur, batting, bowling }
  }))

  // Edit a dismissal's mode / fielder / bowler and keep the canonical text in sync.
  // Changing the mode clears the columns it doesn't use and updates the not-out flags.
  const editDismissal = (innIdx, rowIdx, patch) => setInnings(prev => prev.map((x, i) => {
    if (i !== innIdx) return x
    const isOur = x.is_our_team
    const rows = (x.batting || []).map((r, j) => {
      if (j !== rowIdx) return r
      const row = { ...r, ...patch }
      if ('how_out' in patch) {
        if (!modeHasFielder(row.how_out)) { row.fielder = ''; row.fielder_id = '' }
        if (!modeHasBowler(row.how_out)) { row.bowler = ''; row.bowler_id = '' }
        row.not_out = row.how_out === 'not out'
        row.did_not_bat = row.how_out === 'did not bat'
      }
      const fName = isOur ? row.fielder : (rosterName(row.fielder_id) || row.fielder || '')
      const bName = isOur ? row.bowler : (rosterName(row.bowler_id) || row.bowler || '')
      row.dismissal_text = composeDismissal(row.how_out, fName, bName)
      return row
    })
    return { ...x, batting: rows }
  }))

  // Our fielding, derived from the opposition's dismissals: a catch/stumping/run-out
  // credits the fielder picked on that wicket (a c & b credits the bowler). Catches
  // behind the stumps come from wkByPid since the card doesn't always mark them.
  const fieldingDerived = useMemo(() => {
    const byPid = {}
    for (const inn of innings) {
      if (inn.is_our_team) continue
      for (const b of (inn.batting || [])) {
        const m = (b.how_out || '').toLowerCase()
        let pid = b.fielder_id || ''
        if (m === 'caught & bowled') pid = b.bowler_id || ''
        if (!pid) continue
        if (!['caught', 'caught & bowled', 'stumped', 'run out'].includes(m)) continue
        const row = byPid[pid] || (byPid[pid] = { player_id: pid, name: rosterName(pid), catches: 0, run_outs: 0, stumpings: 0 })
        if (m === 'stumped') row.stumpings += 1
        else if (m === 'run out') row.run_outs += 1
        else row.catches += 1
      }
    }
    return Object.values(byPid)
  }, [innings, rosterName])

  const unmatched = useMemo(() => {
    let n = 0
    for (const inn of innings) {
      const rows = inn.is_our_team ? inn.batting : inn.bowling
      for (const r of (rows || [])) if (!r.player_id) n++
    }
    return n
  }, [innings])

  function buildPayload() {
    const battingRows = []
    const bowlingRows = []
    for (const inn of innings) {
      if (inn.is_our_team) {
        for (const b of (inn.batting || [])) {
          if (!b.player_id) continue
          battingRows.push({
            player_id: b.player_id, innings_number: inn.innings_number || 1,
            batting_position: num(b.position), runs: num(b.runs) || 0,
            balls: tracked.balls ? num(b.balls) : null,
            fours: tracked.boundaries ? (num(b.fours) || 0) : null,
            sixes: tracked.boundaries ? (num(b.sixes) || 0) : null,
            dismissal_type: (b.dismissal_text || composeDismissal(b.how_out, b.fielder, b.bowler)) || null,
            not_out: !!b.not_out, did_not_bat: !!b.did_not_bat,
          })
        }
      } else {
        for (const b of (inn.bowling || [])) {
          if (!b.player_id) continue
          bowlingRows.push({
            player_id: b.player_id, innings_number: inn.innings_number || 1,
            overs: num(b.overs),
            maidens: tracked.maidens ? (num(b.maidens) || 0) : null,
            runs: num(b.runs) || 0, wickets: num(b.wickets) || 0,
            wides: tracked.bowler_extras ? (num(b.wides) || 0) : null,
            no_balls: tracked.bowler_extras ? (num(b.no_balls) || 0) : null,
          })
        }
      }
    }
    // Merge dismissal-derived fielding with rows read off the card's own-catches
    // column: max per stat, so a catch visible both as a dismissal and in the column
    // counts once. wk catches come from the review input, else the card's W/K marker.
    const byPid = {}
    for (const f of fieldingDerived) {
      byPid[f.player_id] = { player_id: f.player_id, catches: f.catches, catches_wk: 0, run_outs: f.run_outs, stumpings: f.stumpings }
    }
    for (const f of fieldingExtra) {
      if (!f.player_id) continue
      const row = byPid[f.player_id] || (byPid[f.player_id] = { player_id: f.player_id, catches: 0, catches_wk: 0, run_outs: 0, stumpings: 0 })
      row.catches = Math.max(row.catches, num(f.catches) || 0)
      row.catches_wk = Math.max(row.catches_wk, num(f.catches_wk) || 0)
      row.run_outs = Math.max(row.run_outs, num(f.run_outs) || 0)
      row.stumpings = Math.max(row.stumpings, num(f.stumpings) || 0)
    }
    const fieldingRows = Object.values(byPid)
      .map(f => {
        const wk = Math.min(Math.max(num(wkByPid[f.player_id]) || 0, f.catches_wk), f.catches)
        return { player_id: f.player_id, catches: f.catches, catches_wk: wk, run_outs: f.run_outs, stumpings: f.stumpings }
      })
      .filter(f => f.player_id && (f.catches || f.catches_wk || f.run_outs || f.stumpings))

    return {
      season_id: form.season_id,
      grade_id: form.grade_id || null,
      played_at: form.played_at || null,
      home_team: match.home_team || null,
      away_team: match.away_team || null,
      opposition: form.opp_name || null,
      opp_org_id: form.opp_org_id || null,
      venue: form.venue || null,
      result: form.result || null,
      winning_team: form.winning_team || null,
      is_final: !!form.is_final,
      match_format: form.match_format || null,
      notes: 'Imported from scorecard photo' + (extract?.read_notes ? ` — ${extract.read_notes}` : ''),
      extracted_payload: { match, innings, source: 'ai_scorecard_upload' },
      batting_innings: battingRows,
      bowling_spells: bowlingRows,
      fielding_stats: fieldingRows,
    }
  }

  const doImport = async () => {
    setErr(null); setBusy(true)
    try {
      if (editingId) {
        await api.adminPatchManualGame(editingId, buildPayload())
        setCreatedId(editingId)
      } else {
        const created = await api.adminCreateManualGame(buildPayload())
        setCreatedId(created?.id || null)
      }
      setStep('done')
      loadUploads()
    } catch (e) {
      setErr(e.message || 'Import failed.')
    } finally { setBusy(false); setConfirm(false) }
  }

  return (
    <AdminLayout>
      <div className="p-4 md:p-6 max-w-6xl">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-pb-text mb-1">Upload Historical Scorecard</h1>
          <p className="text-sm text-pb-faint max-w-2xl">
            Photograph an old paper scorecard and the reader pulls it into a structured
            card. Check what it read, match our players, pick the season and opponent,
            then import it as a manual game. Both teams show on the match page.
          </p>
          <p className="text-xs text-pb-faint max-w-2xl mt-2">
            Handwritten scorebook, or a stack of them? The photo reader is built for
            typed/printed cards — for handwritten pages, or digitising a whole season at
            once, use{' '}
            <Link to="/admin/manual-entries" className="text-pb-accent underline hover:opacity-80">
              Manual Games
            </Link>{' '}
            to type a match in directly, or its CSV template to bulk-upload many matches
            from a spreadsheet in one go.
          </p>
        </div>

        {err && <div className="mb-4 px-3 py-2 rounded bg-red-500/10 border border-red-400/30 text-red-300 text-sm">{err}</div>}

        {step === 'upload' && (
          <div className="bg-pb-surface border pb-hairline rounded-lg p-5 max-w-2xl">
            <label className={LABEL_CLS}>Scorecard photo(s) or PDF scan</label>
            <input type="file" accept="image/*,application/pdf,.pdf" multiple onChange={e => onFiles(e.target.files)} className="block text-sm text-pb-text" />
            <p className="text-xs text-pb-faint mt-2">
              Add every page of the one match. A typical match is two photos, one innings
              each. A PDF with all the pages of one match works too.
            </p>
            {previews.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-4">
                {previews.map((p, i) => p.isPdf
                  ? (
                    <div key={i} className="h-28 px-4 flex flex-col items-center justify-center rounded border pb-hairline bg-pb-surface2 text-center">
                      <span className="text-2xl">📄</span>
                      <span className="text-[10px] text-pb-faint mt-1 max-w-[120px] truncate" title={p.name}>{p.name}</span>
                    </div>
                  )
                  : <img key={i} src={p.url} alt={p.name} className="h-28 w-auto rounded border pb-hairline object-cover" />)}
              </div>
            )}
            <div className="mt-5">
              <button className={BTN_PRIMARY} disabled={busy || !files.length} onClick={runExtract}>
                {busy ? 'Reading scorecard…' : 'Read scorecard'}
              </button>
              {busy && <span className="ml-3 text-xs text-pb-faint">This can take up to a minute for a full card.</span>}
            </div>
          </div>
        )}

        {step === 'upload' && (
          <div className="bg-pb-surface border pb-hairline rounded-lg p-4 mt-6">
            <h3 className="text-base font-semibold text-pb-text mb-3">Uploaded scorecards</h3>
            <UploadsLog
              uploads={uploads}
              loading={uploadsLoading}
              err={uploadsErr}
              onEdit={handleEditUpload}
              onDelete={setDeleteTarget}
            />
          </div>
        )}

        {step === 'review' && (
          <div className="space-y-6">
            {dupes.length > 0 && (
              <div className="px-4 py-3 rounded bg-red-500/10 border border-red-400/40">
                <div className="text-red-300 text-sm font-semibold mb-1">Possible duplicate — this could double-count</div>
                <p className="text-red-200/90 text-xs mb-2">
                  Your club already has {dupes.length === 1 ? 'a game' : `${dupes.length} games`} on {form.played_at}. An uploaded game counts in the stats on top of what's already there, so importing a match that's already in your data double-counts it on profiles and lists.
                </p>
                <ul className="list-disc list-inside text-red-200/90 text-xs space-y-0.5">
                  {dupes.map(d => (
                    <li key={d.id}>
                      {d.grade ? `${d.grade}: ` : ''}vs {d.opponent || 'unknown'} ({d.source === 'manual' ? 'manual upload' : 'synced'}){d.likely ? ' — same opponent' : ''}{' '}
                      <Link to={`/games/${d.id}`} target="_blank" className="underline">view</Link>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {warnings.length > 0 && (
              <div className="px-4 py-3 rounded bg-amber-500/10 border border-amber-400/30">
                <div className="text-amber-300 text-sm font-semibold mb-1">Worth a second look</div>
                <ul className="list-disc list-inside text-amber-200/90 text-xs space-y-0.5">
                  {warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              </div>
            )}
            {match.balls_per_over === 8 && (
              <div className="px-4 py-3 rounded bg-pb-surface2 border pb-hairline text-xs text-pb-faint">
                <span className="font-semibold text-pb-text">8-ball overs: </span>
                this card is from the 8-ball-over era (pre-1980 Australia). Overs are kept
                as written on the card.
              </div>
            )}
            {extract?.read_notes && (
              <div className="px-4 py-3 rounded bg-pb-surface2 border pb-hairline text-xs text-pb-faint">
                <span className="font-semibold text-pb-text">Reader notes: </span>{extract.read_notes}
              </div>
            )}

            {/* Match details */}
            <div className="bg-pb-surface border pb-hairline rounded-lg p-5">
              <h2 className="text-sm font-semibold text-pb-text mb-3">Match details</h2>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <div>
                  <label className={LABEL_CLS}>Season *</label>
                  <select className={INPUT_CLS} value={form.season_id} onChange={e => setForm(f => ({ ...f, season_id: e.target.value, grade_id: '' }))}>
                    <option value="">— choose —</option>
                    {seasons.map(s => <option key={s.id} value={s.id}>{formatSeason(s.name, s.year)}</option>)}
                  </select>
                </div>
                <div>
                  <label className={LABEL_CLS}>Grade</label>
                  <select className={INPUT_CLS} value={form.grade_id} onChange={e => setForm(f => ({ ...f, grade_id: e.target.value }))} disabled={!form.season_id}>
                    <option value="">— none —</option>
                    {seasonGrades.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className={LABEL_CLS}>Date</label>
                  <input type="date" className={INPUT_CLS} value={form.played_at} onChange={e => setForm(f => ({ ...f, played_at: e.target.value }))} />
                </div>
                <div className="col-span-2">
                  <label className={LABEL_CLS}>Opposition club (Cricket Australia search)</label>
                  <OppClubSearch
                    value={form.opp_name}
                    onPick={org => setForm(f => ({ ...f, opp_name: org.name || org.shortName, opp_org_id: org.id }))}
                  />
                  {form.opp_org_id
                    ? <p className="text-[11px] text-green-400/80 mt-1">Linked to CA club · head-to-head will match</p>
                    : <p className="text-[11px] text-pb-faint mt-1">Pick the club so this links to opponent history. You can also just type a name.</p>}
                </div>
                <div>
                  <label className={LABEL_CLS}>Venue</label>
                  <input className={INPUT_CLS} value={form.venue} onChange={e => setForm(f => ({ ...f, venue: e.target.value }))} />
                </div>
                <div>
                  <label className={LABEL_CLS}>Result</label>
                  <input className={INPUT_CLS} value={form.result} onChange={e => setForm(f => ({ ...f, result: e.target.value }))} />
                  {match.result_inferred && (
                    <p className="text-[11px] text-amber-300/90 mt-1">
                      Not written on the card — the reader worked this out from the scores. Check it.
                    </p>
                  )}
                </div>
                <div>
                  <label className={LABEL_CLS}>Winning team</label>
                  <input className={INPUT_CLS} value={form.winning_team} onChange={e => setForm(f => ({ ...f, winning_team: e.target.value }))} />
                </div>
                <div>
                  <label className={LABEL_CLS}>Format</label>
                  <input className={INPUT_CLS} placeholder="e.g. 40-over" value={form.match_format} onChange={e => setForm(f => ({ ...f, match_format: e.target.value }))} />
                </div>
                <label className="flex items-center gap-2 text-sm text-pb-text mt-5">
                  <input type="checkbox" checked={form.is_final} onChange={e => setForm(f => ({ ...f, is_final: e.target.checked }))} />
                  Final
                </label>
              </div>
            </div>

            {/* Which optional columns this card records */}
            <div className="bg-pb-surface border pb-hairline rounded-lg p-4">
              <h2 className="text-sm font-semibold text-pb-text mb-1">This card tracks</h2>
              <p className="text-xs text-pb-faint mb-2">
                Untick anything this card doesn't record. Unticked fields are hidden below
                and import as "not recorded" rather than a zero, so they never drag a
                player's boundary or discipline stats.
              </p>
              <div className="flex flex-wrap gap-x-5 gap-y-2">
                {[['balls', 'Balls faced'], ['boundaries', '4s & 6s'], ['maidens', 'Maidens'], ['bowler_extras', 'Bowler wides & no-balls']].map(([k, label]) => (
                  <label key={k} className="flex items-center gap-2 text-sm text-pb-text">
                    <input type="checkbox" checked={!!tracked[k]} onChange={e => setTracked(t => ({ ...t, [k]: e.target.checked }))} />
                    {label}
                  </label>
                ))}
              </div>
            </div>

            {/* Innings */}
            {innings.map((inn, ii) => (
              <div key={ii} className="bg-pb-surface border pb-hairline rounded-lg p-5">
                <div className="flex items-center justify-between mb-1 gap-3 flex-wrap">
                  <h2 className="text-sm font-semibold text-pb-text">
                    Innings {inn.innings_number}: {inn.batting_team || 'Unknown'} batting
                  </h2>
                  <div className="flex items-center gap-3">
                    <span className="inline-flex rounded overflow-hidden border pb-hairline text-[10px] font-mono">
                      <button type="button"
                        className={`px-2 py-1 ${inn.is_our_team ? 'bg-pb-accent text-white' : 'bg-pb-surface2 text-pb-faint hover:text-pb-text'}`}
                        onClick={() => setInningsTeam(ii, true)}>OUR TEAM</button>
                      <button type="button"
                        className={`px-2 py-1 ${!inn.is_our_team ? 'bg-pb-accent text-white' : 'bg-pb-surface2 text-pb-faint hover:text-pb-text'}`}
                        onClick={() => setInningsTeam(ii, false)}>OPPOSITION</button>
                    </span>
                    <div className="text-xs text-pb-faint">
                      {inn.total_runs != null ? `${inn.total_runs}/${inn.total_wickets ?? '?'}` : ''}
                    </div>
                  </div>
                </div>
                <p className="text-[11px] text-pb-faint mb-3">
                  {inn.is_our_team
                    ? 'Our club batted. Match each batter to a player below.'
                    : 'The opposition batted. Match the bowler and fielder who took each wicket to our players.'}
                </p>

                {/* Batting table */}
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead><tr className="border-b pb-hairline">
                      <th className={TH}>Batter</th>
                      {inn.is_our_team && <th className={TH}>Our player</th>}
                      <th className={TH}>Pos</th><th className={TH}>R</th>
                      {tracked.balls && <th className={TH}>B</th>}
                      {tracked.boundaries && <th className={TH}>4s</th>}
                      {tracked.boundaries && <th className={TH}>6s</th>}
                      <th className={TH}>How out</th><th className={TH}>Fielder</th><th className={TH}>Bowler</th>
                    </tr></thead>
                    <tbody>
                      {(inn.batting || []).map((b, ri) => (
                        <tr key={ri} className="border-b pb-hairline/40">
                          <td className={TD}>
                            <input className={SMALL_INPUT} value={b.name || ''} onChange={e => editRow(ii, 'batting', ri, { name: e.target.value })} />
                          </td>
                          {inn.is_our_team && (
                            <td className={`${TD} min-w-[150px]`}>
                              <PlayerSelect value={b.player_id} roster={roster} cardName={b.name} candidates={candsFor(b.name)} onChange={v => editRow(ii, 'batting', ri, { player_id: v })} />
                            </td>
                          )}
                          <td className={TD}><input className={`${SMALL_INPUT} w-12`} value={b.position ?? ''} onChange={e => editRow(ii, 'batting', ri, { position: e.target.value })} /></td>
                          <td className={TD}><input className={`${SMALL_INPUT} w-14`} value={b.runs ?? ''} onChange={e => editRow(ii, 'batting', ri, { runs: e.target.value })} /></td>
                          {tracked.balls && <td className={TD}><input className={`${SMALL_INPUT} w-12`} value={b.balls ?? ''} onChange={e => editRow(ii, 'batting', ri, { balls: e.target.value })} /></td>}
                          {tracked.boundaries && <td className={TD}><input className={`${SMALL_INPUT} w-12`} value={b.fours ?? ''} onChange={e => editRow(ii, 'batting', ri, { fours: e.target.value })} /></td>}
                          {tracked.boundaries && <td className={TD}><input className={`${SMALL_INPUT} w-12`} value={b.sixes ?? ''} onChange={e => editRow(ii, 'batting', ri, { sixes: e.target.value })} /></td>}
                          <td className={TD}><ModeSelect value={b.how_out || ''} onChange={v => editDismissal(ii, ri, { how_out: v })} /></td>
                          <td className={`${TD} min-w-[140px]`}>
                            {!modeHasFielder(b.how_out)
                              ? <span className="text-pb-faint/40 text-xs">—</span>
                              : inn.is_our_team
                                ? <input className={SMALL_INPUT} placeholder="fielder (opp)" value={b.fielder || ''} onChange={e => editDismissal(ii, ri, { fielder: e.target.value })} />
                                : <PlayerSelect value={b.fielder_id || ''} roster={roster} cardName={b.fielder} candidates={candsFor(b.fielder)} onChange={v => editDismissal(ii, ri, { fielder_id: v, fielder: rosterName(v) })} />}
                          </td>
                          <td className={`${TD} min-w-[140px]`}>
                            {!modeHasBowler(b.how_out)
                              ? <span className="text-pb-faint/40 text-xs">—</span>
                              : inn.is_our_team
                                ? <input className={SMALL_INPUT} placeholder="bowler (opp)" value={b.bowler || ''} onChange={e => editDismissal(ii, ri, { bowler: e.target.value })} />
                                : <PlayerSelect value={b.bowler_id || ''} roster={roster} cardName={b.bowler} candidates={candsFor(b.bowler)} onChange={v => editDismissal(ii, ri, { bowler_id: v, bowler: rosterName(v) })} />}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Bowling table */}
                {(inn.bowling || []).length > 0 && (
                  <div className="overflow-x-auto mt-4">
                    <div className="text-[10px] font-mono text-pb-faint mb-1">
                      {inn.is_our_team ? 'OPPOSITION BOWLING' : 'OUR BOWLING'}
                    </div>
                    <table className="w-full text-sm">
                      <thead><tr className="border-b pb-hairline">
                        <th className={TH}>Bowler</th>
                        {!inn.is_our_team && <th className={TH}>Our player</th>}
                        <th className={TH}>O</th>
                        {tracked.maidens && <th className={TH}>M</th>}
                        <th className={TH}>R</th><th className={TH}>W</th>
                        {tracked.bowler_extras && <th className={TH}>Wd</th>}
                        {tracked.bowler_extras && <th className={TH}>Nb</th>}
                      </tr></thead>
                      <tbody>
                        {(inn.bowling || []).map((b, ri) => (
                          <tr key={ri} className="border-b pb-hairline/40">
                            <td className={TD}><input className={SMALL_INPUT} value={b.name || ''} onChange={e => editRow(ii, 'bowling', ri, { name: e.target.value })} /></td>
                            {!inn.is_our_team && (
                              <td className={`${TD} min-w-[150px]`}>
                                <PlayerSelect value={b.player_id} roster={roster} cardName={b.name} candidates={candsFor(b.name)} onChange={v => editRow(ii, 'bowling', ri, { player_id: v })} />
                              </td>
                            )}
                            <td className={TD}><input className={`${SMALL_INPUT} w-14`} value={b.overs ?? ''} onChange={e => editRow(ii, 'bowling', ri, { overs: e.target.value })} /></td>
                            {tracked.maidens && <td className={TD}><input className={`${SMALL_INPUT} w-12`} value={b.maidens ?? ''} onChange={e => editRow(ii, 'bowling', ri, { maidens: e.target.value })} /></td>}
                            <td className={TD}><input className={`${SMALL_INPUT} w-12`} value={b.runs ?? ''} onChange={e => editRow(ii, 'bowling', ri, { runs: e.target.value })} /></td>
                            <td className={TD}><input className={`${SMALL_INPUT} w-12`} value={b.wickets ?? ''} onChange={e => editRow(ii, 'bowling', ri, { wickets: e.target.value })} /></td>
                            {tracked.bowler_extras && <td className={TD}><input className={`${SMALL_INPUT} w-12`} value={b.wides ?? ''} onChange={e => editRow(ii, 'bowling', ri, { wides: e.target.value })} /></td>}
                            {tracked.bowler_extras && <td className={TD}><input className={`${SMALL_INPUT} w-12`} value={b.no_balls ?? ''} onChange={e => editRow(ii, 'bowling', ri, { no_balls: e.target.value })} /></td>}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Fall of wickets / partnerships */}
                {(inn.fall_of_wickets || []).length > 0 && (
                  <div className="overflow-x-auto mt-4">
                    <div className="text-[10px] font-mono text-pb-faint mb-1">FALL OF WICKETS · STAND = partnership runs</div>
                    <table className="text-sm">
                      <thead><tr className="border-b pb-hairline">
                        <th className={TH}>Wkt</th><th className={TH}>Score</th><th className={TH}>Batter out</th><th className={TH}>Stand</th>
                      </tr></thead>
                      <tbody>
                        {(inn.fall_of_wickets || []).map((f, ri) => (
                          <tr key={ri} className="border-b pb-hairline/40">
                            <td className={TD}><input className={`${SMALL_INPUT} w-12`} value={f.wicket ?? ''} onChange={e => editRow(ii, 'fall_of_wickets', ri, { wicket: num(e.target.value) })} /></td>
                            <td className={TD}><input className={`${SMALL_INPUT} w-16`} value={f.score ?? ''} onChange={e => editRow(ii, 'fall_of_wickets', ri, { score: num(e.target.value) })} /></td>
                            <td className={TD}><input className={`${SMALL_INPUT} min-w-[140px]`} value={f.batter_out || ''} onChange={e => editRow(ii, 'fall_of_wickets', ri, { batter_out: e.target.value })} /></td>
                            <td className={TD}><input className={`${SMALL_INPUT} w-16`} value={f.stand ?? ''} onChange={e => editRow(ii, 'fall_of_wickets', ri, { stand: num(e.target.value) })} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ))}

            {/* Our fielding */}
            <div className="bg-pb-surface border pb-hairline rounded-lg p-5">
              <h2 className="text-sm font-semibold text-pb-text mb-1">Our fielding</h2>
              <p className="text-xs text-pb-faint mb-3">Worked out from the fielder you matched on each opposition wicket above. Set how many of a player's catches were taken behind the stumps (wk), since the card doesn't always mark those.</p>
              {fieldingDerived.length === 0
                ? <p className="text-xs text-pb-faint">No catches, run-outs or stumpings matched to our players yet. Match the fielder on each opposition wicket above.</p>
                : (
                  <table className="w-full text-sm">
                    <thead><tr className="border-b pb-hairline">
                      <th className={TH}>Player</th><th className={TH}>Catches</th><th className={TH}>of which (wk)</th><th className={TH}>Run outs</th><th className={TH}>Stumpings</th>
                    </tr></thead>
                    <tbody>
                      {fieldingDerived.map((f) => (
                        <tr key={f.player_id} className="border-b pb-hairline/40">
                          <td className={`${TD} min-w-[160px] text-pb-text`}>{f.name || '(unknown)'}</td>
                          <td className={TD}>{f.catches}</td>
                          <td className={TD}>
                            <input className={`${SMALL_INPUT} w-14`} value={wkByPid[f.player_id] ?? ''} placeholder="0"
                              onChange={e => setWkByPid(prev => ({ ...prev, [f.player_id]: e.target.value }))} />
                          </td>
                          <td className={TD}>{f.run_outs}</td>
                          <td className={TD}>{f.stumpings}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}

              {fieldingExtra.length > 0 && (
                <div className="mt-5">
                  <div className="text-[10px] font-mono text-pb-faint mb-1">FROM THE CARD'S OWN-CATCHES COLUMN</div>
                  <p className="text-xs text-pb-faint mb-2">
                    This card credits fielders separately from the dismissals (a summary form's catches column).
                    Match each name to a player; a player in both lists counts once, whichever reading is higher.
                  </p>
                  <table className="w-full text-sm">
                    <thead><tr className="border-b pb-hairline">
                      <th className={TH}>Name on card</th><th className={TH}>Our player</th>
                      <th className={TH}>Catches</th><th className={TH}>of which (wk)</th>
                      <th className={TH}>Run outs</th><th className={TH}>Stumpings</th>
                    </tr></thead>
                    <tbody>
                      {fieldingExtra.map((f, fi) => (
                        <tr key={fi} className="border-b pb-hairline/40">
                          <td className={TD}>
                            <input className={SMALL_INPUT} value={f.name || ''} onChange={e => editFieldingExtra(fi, { name: e.target.value })} />
                          </td>
                          <td className={`${TD} min-w-[150px]`}>
                            <PlayerSelect value={f.player_id} roster={roster} cardName={f.name} candidates={candsFor(f.name)} onChange={v => editFieldingExtra(fi, { player_id: v })} />
                          </td>
                          <td className={TD}><input className={`${SMALL_INPUT} w-14`} value={f.catches ?? ''} onChange={e => editFieldingExtra(fi, { catches: e.target.value })} /></td>
                          <td className={TD}><input className={`${SMALL_INPUT} w-14`} value={f.catches_wk ?? ''} onChange={e => editFieldingExtra(fi, { catches_wk: e.target.value })} /></td>
                          <td className={TD}><input className={`${SMALL_INPUT} w-14`} value={f.run_outs ?? ''} onChange={e => editFieldingExtra(fi, { run_outs: e.target.value })} /></td>
                          <td className={TD}><input className={`${SMALL_INPUT} w-14`} value={f.stumpings ?? ''} onChange={e => editFieldingExtra(fi, { stumpings: e.target.value })} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="flex items-center gap-3">
              <button className={BTN_SECONDARY} onClick={() => { setStep('upload'); setErr(null); setEditingId(null) }}>Back</button>
              <button className={BTN_PRIMARY} disabled={busy || !form.season_id} onClick={() => setConfirm(true)}>{editingId ? 'Save changes' : 'Import match'}</button>
              {unmatched > 0 && <span className="text-xs text-amber-300">{unmatched} of our rows aren't matched to a player and won't be imported.</span>}
              {!form.season_id && <span className="text-xs text-pb-faint">Choose a season to import.</span>}
            </div>
          </div>
        )}

        {step === 'done' && (
          <div className="bg-pb-surface border pb-hairline rounded-lg p-6 max-w-xl">
            <h2 className="text-lg font-semibold text-pb-text mb-2">{editingId ? 'Scorecard updated' : 'Match imported'}</h2>
            <p className="text-sm text-pb-faint mb-4">It now counts in the stats like any other game, and the match page shows both teams. Every change is reversible from the Manual Entries audit tab.</p>
            <div className="flex gap-3">
              {createdId && <Link to={`/games/${createdId}`} className={BTN_PRIMARY}>View match</Link>}
              <button className={BTN_SECONDARY} onClick={() => {
                setStep('upload'); setFiles([]); setPreviews([]); setExtract(null); setInnings([]); setWkByPid({}); setFieldingExtra([]); setTracked(ALL_TRACKED); setWarnings([]); setCreatedId(null); setEditingId(null)
                setForm({ season_id: '', grade_id: '', played_at: '', venue: '', result: '', winning_team: '', is_final: false, match_format: '', opp_name: '', opp_org_id: '' })
              }}>{editingId ? 'Back to list' : 'Upload another'}</button>
            </div>
          </div>
        )}

        {confirm && (
          <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center px-4" onClick={() => setConfirm(false)}>
            <div className="bg-pb-surface border pb-hairline rounded-lg max-w-md w-full p-5" onClick={e => e.stopPropagation()}>
              <h3 className="text-lg font-semibold text-pb-text mb-2">{editingId ? 'Save changes to this scorecard?' : 'Import this match?'}</h3>
              <div className="text-sm text-pb-faint mb-4 space-y-2">
                <p>{editingId ? 'This updates the saved game and its stats in place.' : 'It will be saved as a manual game and counted in the stats.'} Reversible from the Audit tab.</p>
                {dupes.length > 0
                  ? <p className="text-red-300 text-xs">Heads up: your club already has {dupes.length === 1 ? 'a game' : `${dupes.length} games`} on {form.played_at}. If this is the same match, importing will double-count it. Only proceed if it's a different game.</p>
                  : <p className="text-amber-300/90 text-xs">No existing game found on this date, so it won't double up.</p>}
              </div>
              <div className="flex justify-end gap-2">
                <button className={BTN_SECONDARY} onClick={() => setConfirm(false)}>Cancel</button>
                <button className={BTN_PRIMARY} disabled={busy} onClick={doImport}>{busy ? 'Saving…' : (editingId ? 'Save changes' : 'Import')}</button>
              </div>
            </div>
          </div>
        )}

        <DeleteConfirmModal
          row={deleteTarget}
          busy={deleteBusy}
          onConfirm={handleDeleteUpload}
          onCancel={() => setDeleteTarget(null)}
        />
      </div>
    </AdminLayout>
  )
}
