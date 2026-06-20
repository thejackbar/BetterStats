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

// ─── Player picker for our rows ────────────────────────────────────────────────
function PlayerSelect({ value, roster, cardName, onChange }) {
  return (
    <select
      className={`${SMALL_INPUT} ${value ? '' : 'border-amber-400/50'}`}
      value={value || ''}
      onChange={e => onChange(e.target.value)}
      title={cardName ? `Card: ${cardName}` : ''}
    >
      <option value="">— match player —</option>
      {roster.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
    </select>
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

  const [extract, setExtract] = useState(null)  // raw response
  const [roster, setRoster] = useState([])
  const [match, setMatch] = useState({})
  const [innings, setInnings] = useState([])
  const [fielding, setFielding] = useState([])
  const [warnings, setWarnings] = useState([])

  const [form, setForm] = useState({ season_id: '', grade_id: '', played_at: '', venue: '', result: '', winning_team: '', is_final: false, match_format: '', opp_name: '', opp_org_id: '' })
  const [confirm, setConfirm] = useState(false)
  const [createdId, setCreatedId] = useState(null)

  useEffect(() => {
    ;(async () => {
      try {
        const [s, g] = await Promise.all([api.adminListSeasons(), api.adminListGradesBySeason()])
        setSeasons(s || []); setGrades(g || [])
      } catch {}
    })()
  }, [])

  const seasonGrades = useMemo(
    () => (grades || []).filter(g => g.season_id === form.season_id),
    [grades, form.season_id]
  )

  function onFiles(list) {
    const arr = Array.from(list || [])
    setFiles(arr)
    setPreviews(arr.map(f => ({ name: f.name, url: URL.createObjectURL(f) })))
  }

  const runExtract = async () => {
    if (!files.length) { setErr('Add at least one scorecard photo.'); return }
    setErr(null); setBusy(true)
    try {
      const data = await api.adminExtractScorecard(files)
      setExtract(data)
      setRoster(data.roster || [])
      setMatch(data.match || {})
      setWarnings(data.warnings || [])

      const sugg = data.suggestions || {}
      const inns = (data.innings || []).map(inn => ({
        ...inn,
        batting: (inn.batting || []).map(b => ({ ...b, player_id: inn.is_our_team ? (sugg[b.name] || '') : undefined })),
        bowling: (inn.bowling || []).map(b => ({ ...b, player_id: !inn.is_our_team ? (sugg[b.name] || '') : undefined })),
      }))
      setInnings(inns)
      setFielding(buildFielding(data.innings || [], sugg, data.roster || []))

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

  // Build our fielding rows from opposition dismissals (catcher / stumper / run-out).
  function buildFielding(rawInnings, sugg, rost) {
    const byPid = {}
    for (const inn of rawInnings) {
      if (inn.is_our_team) continue   // their dismissals are caused by OUR fielders
      for (const b of (inn.batting || [])) {
        const fielder = b.fielder
        const how = (b.how_out || '').toLowerCase()
        if (!fielder) continue
        const pid = sugg[fielder]
        if (!pid) continue
        const row = byPid[pid] || (byPid[pid] = { player_id: pid, name: (rost.find(p => p.id === pid)?.name) || fielder, catches: 0, catches_wk: 0, run_outs: 0, stumpings: 0 })
        if (how.includes('stump')) row.stumpings += 1
        else if (how.includes('run')) row.run_outs += 1
        else row.catches += 1
      }
    }
    return Object.values(byPid)
  }

  // ─── immutable editors ───────────────────────────────────────────────────────
  const editInn = (idx, patch) => setInnings(prev => prev.map((x, i) => i === idx ? { ...x, ...patch } : x))
  const editRow = (innIdx, kind, rowIdx, patch) => setInnings(prev => prev.map((x, i) => {
    if (i !== innIdx) return x
    const rows = (x[kind] || []).map((r, j) => j === rowIdx ? { ...r, ...patch } : r)
    return { ...x, [kind]: rows }
  })
  )
  const editField = (idx, patch) => setFielding(prev => prev.map((x, i) => i === idx ? { ...x, ...patch } : x))

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
            batting_position: num(b.position), runs: num(b.runs) || 0, balls: num(b.balls),
            fours: num(b.fours) || 0, sixes: num(b.sixes) || 0,
            dismissal_type: b.dismissal_text || b.how_out || null,
            not_out: !!b.not_out, did_not_bat: !!b.did_not_bat,
          })
        }
      } else {
        for (const b of (inn.bowling || [])) {
          if (!b.player_id) continue
          bowlingRows.push({
            player_id: b.player_id, innings_number: inn.innings_number || 1,
            overs: num(b.overs), maidens: num(b.maidens) || 0, runs: num(b.runs) || 0,
            wickets: num(b.wickets) || 0, wides: num(b.wides) || 0, no_balls: num(b.no_balls) || 0,
          })
        }
      }
    }
    const fieldingRows = fielding
      .filter(f => f.player_id && (f.catches || f.catches_wk || f.run_outs || f.stumpings))
      .map(f => ({ player_id: f.player_id, catches: num(f.catches) || 0, catches_wk: num(f.catches_wk) || 0, run_outs: num(f.run_outs) || 0, stumpings: num(f.stumpings) || 0 }))

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
      const created = await api.adminCreateManualGame(buildPayload())
      setCreatedId(created?.id || null)
      setStep('done')
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
        </div>

        {err && <div className="mb-4 px-3 py-2 rounded bg-red-500/10 border border-red-400/30 text-red-300 text-sm">{err}</div>}

        {step === 'upload' && (
          <div className="bg-pb-surface border pb-hairline rounded-lg p-5 max-w-2xl">
            <label className={LABEL_CLS}>Scorecard photo(s)</label>
            <input type="file" accept="image/*" multiple onChange={e => onFiles(e.target.files)} className="block text-sm text-pb-text" />
            <p className="text-xs text-pb-faint mt-2">
              Add every page of the one match. A typical match is two photos, one innings each.
            </p>
            {previews.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-4">
                {previews.map((p, i) => (
                  <img key={i} src={p.url} alt={p.name} className="h-28 w-auto rounded border pb-hairline object-cover" />
                ))}
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

        {step === 'review' && (
          <div className="space-y-6">
            {warnings.length > 0 && (
              <div className="px-4 py-3 rounded bg-amber-500/10 border border-amber-400/30">
                <div className="text-amber-300 text-sm font-semibold mb-1">Worth a second look</div>
                <ul className="list-disc list-inside text-amber-200/90 text-xs space-y-0.5">
                  {warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
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

            {/* Innings */}
            {innings.map((inn, ii) => (
              <div key={ii} className="bg-pb-surface border pb-hairline rounded-lg p-5">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-semibold text-pb-text">
                    Innings {inn.innings_number}: {inn.batting_team || '—'} batting
                    {inn.is_our_team
                      ? <span className="ml-2 text-[10px] font-mono px-1.5 py-0.5 rounded bg-pb-accent/20 text-pb-accent">OUR INNINGS</span>
                      : <span className="ml-2 text-[10px] font-mono px-1.5 py-0.5 rounded bg-pb-surface2 text-pb-faint">OPPOSITION</span>}
                  </h2>
                  <div className="text-xs text-pb-faint">
                    {inn.total_runs != null ? `${inn.total_runs}/${inn.total_wickets ?? '?'}` : ''}
                  </div>
                </div>

                {/* Batting table */}
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead><tr className="border-b pb-hairline">
                      <th className={TH}>Batter</th>
                      {inn.is_our_team && <th className={TH}>Our player</th>}
                      <th className={TH}>Pos</th><th className={TH}>R</th><th className={TH}>B</th>
                      <th className={TH}>4s</th><th className={TH}>6s</th><th className={TH}>How out</th>
                    </tr></thead>
                    <tbody>
                      {(inn.batting || []).map((b, ri) => (
                        <tr key={ri} className="border-b pb-hairline/40">
                          <td className={TD}>
                            <input className={SMALL_INPUT} value={b.name || ''} onChange={e => editRow(ii, 'batting', ri, { name: e.target.value })} />
                          </td>
                          {inn.is_our_team && (
                            <td className={`${TD} min-w-[150px]`}>
                              <PlayerSelect value={b.player_id} roster={roster} cardName={b.name} onChange={v => editRow(ii, 'batting', ri, { player_id: v })} />
                            </td>
                          )}
                          <td className={TD}><input className={`${SMALL_INPUT} w-12`} value={b.position ?? ''} onChange={e => editRow(ii, 'batting', ri, { position: e.target.value })} /></td>
                          <td className={TD}><input className={`${SMALL_INPUT} w-14`} value={b.runs ?? ''} onChange={e => editRow(ii, 'batting', ri, { runs: e.target.value })} /></td>
                          <td className={TD}><input className={`${SMALL_INPUT} w-12`} value={b.balls ?? ''} onChange={e => editRow(ii, 'batting', ri, { balls: e.target.value })} /></td>
                          <td className={TD}><input className={`${SMALL_INPUT} w-12`} value={b.fours ?? ''} onChange={e => editRow(ii, 'batting', ri, { fours: e.target.value })} /></td>
                          <td className={TD}><input className={`${SMALL_INPUT} w-12`} value={b.sixes ?? ''} onChange={e => editRow(ii, 'batting', ri, { sixes: e.target.value })} /></td>
                          <td className={TD}><input className={`${SMALL_INPUT} min-w-[140px]`} value={b.dismissal_text || b.how_out || ''} onChange={e => editRow(ii, 'batting', ri, { dismissal_text: e.target.value })} /></td>
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
                        <th className={TH}>O</th><th className={TH}>M</th><th className={TH}>R</th>
                        <th className={TH}>W</th><th className={TH}>Wd</th><th className={TH}>Nb</th>
                      </tr></thead>
                      <tbody>
                        {(inn.bowling || []).map((b, ri) => (
                          <tr key={ri} className="border-b pb-hairline/40">
                            <td className={TD}><input className={SMALL_INPUT} value={b.name || ''} onChange={e => editRow(ii, 'bowling', ri, { name: e.target.value })} /></td>
                            {!inn.is_our_team && (
                              <td className={`${TD} min-w-[150px]`}>
                                <PlayerSelect value={b.player_id} roster={roster} cardName={b.name} onChange={v => editRow(ii, 'bowling', ri, { player_id: v })} />
                              </td>
                            )}
                            <td className={TD}><input className={`${SMALL_INPUT} w-14`} value={b.overs ?? ''} onChange={e => editRow(ii, 'bowling', ri, { overs: e.target.value })} /></td>
                            <td className={TD}><input className={`${SMALL_INPUT} w-12`} value={b.maidens ?? ''} onChange={e => editRow(ii, 'bowling', ri, { maidens: e.target.value })} /></td>
                            <td className={TD}><input className={`${SMALL_INPUT} w-12`} value={b.runs ?? ''} onChange={e => editRow(ii, 'bowling', ri, { runs: e.target.value })} /></td>
                            <td className={TD}><input className={`${SMALL_INPUT} w-12`} value={b.wickets ?? ''} onChange={e => editRow(ii, 'bowling', ri, { wickets: e.target.value })} /></td>
                            <td className={TD}><input className={`${SMALL_INPUT} w-12`} value={b.wides ?? ''} onChange={e => editRow(ii, 'bowling', ri, { wides: e.target.value })} /></td>
                            <td className={TD}><input className={`${SMALL_INPUT} w-12`} value={b.no_balls ?? ''} onChange={e => editRow(ii, 'bowling', ri, { no_balls: e.target.value })} /></td>
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
              <p className="text-xs text-pb-faint mb-3">Worked out from the opposition's dismissals. Adjust catches behind the stumps (wk) and run-outs as needed.</p>
              {fielding.length === 0
                ? <p className="text-xs text-pb-faint">No catches or stumpings matched to our players yet.</p>
                : (
                  <table className="w-full text-sm">
                    <thead><tr className="border-b pb-hairline">
                      <th className={TH}>Player</th><th className={TH}>Catches</th><th className={TH}>Ct (wk)</th><th className={TH}>Run outs</th><th className={TH}>Stumpings</th>
                    </tr></thead>
                    <tbody>
                      {fielding.map((f, i) => (
                        <tr key={i} className="border-b pb-hairline/40">
                          <td className={`${TD} min-w-[160px]`}>
                            <PlayerSelect value={f.player_id} roster={roster} cardName={f.name} onChange={v => editField(i, { player_id: v })} />
                          </td>
                          <td className={TD}><input className={`${SMALL_INPUT} w-14`} value={f.catches} onChange={e => editField(i, { catches: e.target.value })} /></td>
                          <td className={TD}><input className={`${SMALL_INPUT} w-14`} value={f.catches_wk} onChange={e => editField(i, { catches_wk: e.target.value })} /></td>
                          <td className={TD}><input className={`${SMALL_INPUT} w-14`} value={f.run_outs} onChange={e => editField(i, { run_outs: e.target.value })} /></td>
                          <td className={TD}><input className={`${SMALL_INPUT} w-14`} value={f.stumpings} onChange={e => editField(i, { stumpings: e.target.value })} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
            </div>

            <div className="flex items-center gap-3">
              <button className={BTN_SECONDARY} onClick={() => { setStep('upload'); setErr(null) }}>Back</button>
              <button className={BTN_PRIMARY} disabled={busy || !form.season_id} onClick={() => setConfirm(true)}>Import match</button>
              {unmatched > 0 && <span className="text-xs text-amber-300">{unmatched} of our rows aren't matched to a player and won't be imported.</span>}
              {!form.season_id && <span className="text-xs text-pb-faint">Choose a season to import.</span>}
            </div>
          </div>
        )}

        {step === 'done' && (
          <div className="bg-pb-surface border pb-hairline rounded-lg p-6 max-w-xl">
            <h2 className="text-lg font-semibold text-pb-text mb-2">Match imported</h2>
            <p className="text-sm text-pb-faint mb-4">It now counts in the stats like any other game, and the match page shows both teams. Every change is reversible from the Manual Entries audit tab.</p>
            <div className="flex gap-3">
              {createdId && <Link to={`/games/${createdId}`} className={BTN_PRIMARY}>View match</Link>}
              <button className={BTN_SECONDARY} onClick={() => {
                setStep('upload'); setFiles([]); setPreviews([]); setExtract(null); setInnings([]); setFielding([]); setWarnings([]); setCreatedId(null)
                setForm({ season_id: '', grade_id: '', played_at: '', venue: '', result: '', winning_team: '', is_final: false, match_format: '', opp_name: '', opp_org_id: '' })
              }}>Upload another</button>
            </div>
          </div>
        )}

        {confirm && (
          <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center px-4" onClick={() => setConfirm(false)}>
            <div className="bg-pb-surface border pb-hairline rounded-lg max-w-md w-full p-5" onClick={e => e.stopPropagation()}>
              <h3 className="text-lg font-semibold text-pb-text mb-2">Import this match?</h3>
              <div className="text-sm text-pb-faint mb-4 space-y-2">
                <p>It will be saved as a manual game and counted in the stats. Reversible from the Audit tab.</p>
                <p className="text-amber-300/90 text-xs">Check this match isn't already in the data from a sync (same date and opponent) before importing, so totals aren't double-counted.</p>
              </div>
              <div className="flex justify-end gap-2">
                <button className={BTN_SECONDARY} onClick={() => setConfirm(false)}>Cancel</button>
                <button className={BTN_PRIMARY} disabled={busy} onClick={doImport}>{busy ? 'Importing…' : 'Import'}</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </AdminLayout>
  )
}
