import { useParams } from 'react-router-dom'
import { useState, useEffect, useRef } from 'react'
import { api } from '../lib/api'
import { getSubcategoriesFromDefs, getAchievementsFromDefs, resolveAwardLabel } from '../lib/achievementOptions'
import { PbSpinner } from '../lib/presskit'
import { CATEGORY_ICON_SRC, ThiingIcon, thiings } from '../assets/thiings'
import Dropdown from '../components/Dropdown'
import { formatSeason } from '../lib/cricketFormat'

// Build the deduped, canonical "YYYY/YY" season options for the add/edit
// dropdowns. Dedupes across the inconsistent source names (so "Summer 1996/97"
// and "1996/97" collapse to one entry) and keeps any already-selected value
// selectable even if it isn't in the org's current season list.
function seasonOptionList(seasons, ...current) {
  const seen = new Set()
  const opts = []
  for (const s of seasons || []) {
    const label = formatSeason(s)
    if (label && !seen.has(label)) { seen.add(label); opts.push(label) }
  }
  for (const v of current) {
    const label = v ? formatSeason(v) : ''
    if (label && !seen.has(label)) { seen.add(label); opts.push(label) }
  }
  opts.sort((a, b) => b.localeCompare(a))
  return opts
}

const CATEGORIES = ['Club Award', 'Association Award', 'Office Bearer', 'Premiership', 'Hall of Fame', 'Life Membership', 'Milestone']

const BASE = import.meta.env.VITE_API_URL || '/api'

const INPUT_CLS = 'w-full bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent placeholder-pb-faintest'

function PlayerAutocomplete({ players, value, onChange }) {
  const [query, setQuery] = useState(value || '')
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => { setQuery(value || '') }, [value])

  const filtered = query.trim().length >= 1
    ? players.filter(p => (p.display_name || p.name).toLowerCase().includes(query.trim().toLowerCase())).slice(0, 10)
    : []

  return (
    <div ref={ref} className="relative">
      <input
        type="text"
        value={query}
        onChange={e => { setQuery(e.target.value); onChange({ name: e.target.value, id: null }); setOpen(true) }}
        onFocus={() => setOpen(true)}
        placeholder="Full name"
        className={INPUT_CLS}
      />
      <Dropdown
        anchorRef={ref}
        open={open && filtered.length > 0}
        onClose={() => setOpen(false)}
        maxHeight={208}
        className="bg-pb-surface border pb-hairline rounded shadow-xl pb-scroll"
      >
        {filtered.map(p => (
          <button
            key={p.id}
            onMouseDown={() => { const dn = p.display_name || p.name; setQuery(dn); onChange({ name: dn, id: p.id }); setOpen(false) }}
            className="w-full text-left px-3 py-2 text-sm text-pb-dim hover:bg-pb-surface2 hover:text-pb-text"
          >
            {p.display_name || p.name}
          </button>
        ))}
      </Dropdown>
    </div>
  )
}

function ImportPanel({ orgId, onImported }) {
  const fileRef = useRef(null)
  const [importing, setImporting] = useState(false)
  const [forcing, setForcing] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [checkedDupes, setCheckedDupes] = useState({})
  const [pdfParsing, setPdfParsing] = useState(false)
  const [pdfResult, setPdfResult] = useState(null)
  const [colMap, setColMap] = useState({})
  const [pdfImporting, setPdfImporting] = useState(false)
  const [pdfDone, setPdfDone] = useState(null)
  const [linkChoices, setLinkChoices] = useState({})   // name → chosen player_id
  const [linking, setLinking] = useState(false)
  const [history, setHistory] = useState([])
  const [undoing, setUndoing] = useState(null)

  const loadHistory = () => {
    api.listAchievementImports(orgId).then(d => setHistory(d || [])).catch(() => {})
  }
  useEffect(() => { loadHistory() }, [orgId])

  const handleDownloadTemplate = async () => {
    const token = localStorage.getItem('bs_token')
    const headers = token ? { Authorization: `Bearer ${token}` } : {}
    const res = await fetch(`${BASE}/achievements/template`, { headers })
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'achievements_template.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleImport = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = '' // allow re-picking the same file after error
    if (!file) return
    const ext = '.' + (file.name || '').split('.').pop().toLowerCase()
    if (!['.csv', '.xlsx', '.xls'].includes(ext)) {
      setError(`Unsupported file type: ${ext || 'unknown'}. Use .csv, .xlsx or .xls.`)
      return
    }
    const MAX = 5 * 1024 * 1024
    if (file.size > MAX) {
      setError(`File is ${(file.size / 1024 / 1024).toFixed(1)} MB — must be 5 MB or smaller.`)
      return
    }
    if (file.size === 0) {
      setError('File is empty.')
      return
    }
    setImporting(true)
    setResult(null)
    setError(null)
    setCheckedDupes({})
    setLinkChoices({})
    try {
      const res = await api.importAchievements(orgId, file)
      setResult(res)
      // Pre-select the strongest candidate for each suggested name.
      const choices = {}
      for (const s of res.suggested_matches || []) {
        if (s.candidates?.length) choices[s.name] = s.candidates[0].player_id
      }
      setLinkChoices(choices)
      onImported()
      loadHistory()
    } catch (err) {
      setError(err.message || 'Import failed')
    } finally {
      setImporting(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const handleApplyLinks = async () => {
    const suggestions = result?.suggested_matches || []
    const links = suggestions
      .map(s => ({ player_name: s.name, player_id: linkChoices[s.name] }))
      .filter(l => l.player_id)
    if (!links.length) return
    setLinking(true)
    try {
      await api.linkAchievementPlayers(orgId, links, result.batch_id)
      const linkedNames = new Set(links.map(l => l.player_name))
      setResult(prev => ({
        ...prev,
        suggested_matches: (prev.suggested_matches || []).filter(s => !linkedNames.has(s.name)),
      }))
      onImported()
    } catch (err) {
      setError(err.message || 'Could not link players')
    } finally {
      setLinking(false)
    }
  }

  const handleUndo = async (batch) => {
    if (!window.confirm(`Undo this import? ${batch.remaining} achievement${batch.remaining !== 1 ? 's' : ''} will be removed.`)) return
    setUndoing(batch.id)
    try {
      await api.undoAchievementImport(orgId, batch.id)
      if (result?.batch_id === batch.id) setResult(null)
      onImported()
      loadHistory()
    } catch (err) {
      setError(err.message || 'Undo failed')
    } finally {
      setUndoing(null)
    }
  }

  // ── Honour-board PDF (no API tokens — parsed from the PDF text layer) ──
  const guessCategory = (label) => {
    const l = (label || '').toLowerCase()
    if (/life member/.test(l)) return 'Life Membership'
    if (/hall of fame/.test(l)) return 'Hall of Fame'
    if (/premiership|premiers/.test(l)) return 'Premiership'
    if (/president|treasurer|secretary|captain|coach|chair|vice|committee|delegate|registrar|officer|manager|selector/.test(l)) return 'Office Bearer'
    return 'Club Award'
  }
  const tcLabel = (s) => (s || '').replace(/[A-Za-z]+/g, w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
  const fmtName = (raw) => {
    let s = (raw || '').replace(/\s+/g, ' ').trim().replace(/\s+\./g, '.')
    const tc = (x) => x.replace(/[A-Za-z]+/g, w => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    const m = s.match(/^([A-Za-z])\.\s*(.+)$/)
    return m ? `${m[1].toUpperCase()}. ${tc(m[2])}` : tc(s)
  }

  const handleParsePdf = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    const name = (file.name || '').toLowerCase()
    if (!/\.(pdf|png|jpe?g|webp|tiff?|bmp)$/.test(name)) {
      setError('Upload a PDF or a photo of the board.')
      return
    }
    setPdfParsing(true); setError(null); setPdfResult(null); setPdfDone(null)
    try {
      const res = await api.parseAchievementsPdf(orgId, file)
      if (!res.available) {
        setPdfResult(res)
      } else {
        const map = {}
        for (const label of res.columns) {
          map[label] = { include: true, category: guessCategory(label), achievement: tcLabel(label), subcategory: '' }
        }
        setColMap(map)
        setPdfResult(res)
      }
    } catch (err) {
      setError(err.message || 'Could not read the PDF')
    } finally {
      setPdfParsing(false)
    }
  }

  const setCol = (label, patch) => setColMap(prev => ({ ...prev, [label]: { ...prev[label], ...patch } }))

  const handlePdfImport = async () => {
    if (!pdfResult?.available) return
    const rows = []
    for (const r of pdfResult.rows) {
      const m = colMap[r.label]
      if (!m || !m.include) continue
      rows.push({
        season: r.season || '',
        category: m.category,
        subcategory: m.subcategory || '',
        achievement: (m.achievement || tcLabel(r.label)).trim(),
        player_name: fmtName(r.player_name),
      })
    }
    if (!rows.length) { setError('Tick at least one column to import.'); return }
    setPdfImporting(true); setError(null)
    try {
      const res = await api.forceImportAchievements(orgId, rows, { filename: 'Honour board' })
      setPdfDone({ created: res.created ?? rows.length })
      setPdfResult(null); setColMap({})
      onImported()
      loadHistory()
    } catch (err) {
      setError(err.message || 'Import failed')
    } finally {
      setPdfImporting(false)
    }
  }

  const toggleDupe = (idx) => setCheckedDupes(prev => ({ ...prev, [idx]: !prev[idx] }))
  const toggleAll = () => {
    const dupes = result?.skipped_duplicates || []
    const allChecked = dupes.every((_, i) => checkedDupes[i])
    setCheckedDupes(allChecked ? {} : Object.fromEntries(dupes.map((_, i) => [i, true])))
  }

  const handleForceImport = async () => {
    const dupes = result?.skipped_duplicates || []
    const rows = dupes.filter((_, i) => checkedDupes[i])
    if (!rows.length) return
    setForcing(true)
    try {
      await api.forceImportAchievements(orgId, rows, { batchId: result?.batch_id })
      setResult(prev => ({
        ...prev,
        created: (prev.created || 0) + rows.length,
        skipped_duplicates: dupes.filter((_, i) => !checkedDupes[i]),
      }))
      setCheckedDupes({})
      onImported()
      loadHistory()
    } catch (err) {
      setError(err.message || 'Force import failed')
    } finally {
      setForcing(false)
    }
  }

  const dupes = result?.skipped_duplicates || []
  const checkedCount = Object.values(checkedDupes).filter(Boolean).length

  return (
    <div className="pb-card p-5 mb-6">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3 uppercase">Bulk Import</p>
      <p className="text-pb-dim text-sm mb-4 leading-relaxed">
        Download the CSV template, fill in achievements using the column format, then upload. Player names are matched automatically.
      </p>
      <div className="flex flex-wrap gap-3 items-center">
        <button
          onClick={handleDownloadTemplate}
          className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-dim hover:text-pb-text transition-colors flex items-center gap-2"
        >
          ⬇ Download Template (.csv)
        </button>
        <label className={`px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition cursor-pointer flex items-center gap-2 text-pb-bg ${importing ? 'opacity-50 pointer-events-none' : ''}`}
          style={{ background: 'var(--pb-accent)' }}>
          ⬆ {importing ? 'Importing…' : 'Upload File (.xlsx / .csv)'}
          <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" className="hidden" onChange={handleImport} />
        </label>
        <label className={`px-4 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-dim hover:text-pb-text transition-colors cursor-pointer flex items-center gap-2 ${pdfParsing ? 'opacity-50 pointer-events-none' : ''}`}>
          📄 {pdfParsing ? 'Reading…' : 'Read honour board (PDF or photo)'}
          <input type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.tif,.tiff,.bmp" className="hidden" onChange={handleParsePdf} />
        </label>
      </div>
      <p className="text-pb-faintest text-xs mt-2 leading-relaxed">
        Best on a board that's a table with the season down the rows and an award per column.
        A PDF exported from Word/Excel/Sheets reads exactly. A scan or a straight-on photo is
        read by OCR, which is rougher, so check the names before importing. It all runs on the
        server with no AI cost.
      </p>

      {pdfDone && (
        <div className="mt-4 p-4 bg-pb-surface2 rounded border pb-hairline text-sm">
          <p className="font-mono text-[11px]" style={{ color: 'var(--pb-accent)' }}>✓ Imported {pdfDone.created} achievements from the honour board</p>
        </div>
      )}

      {pdfResult && !pdfResult.available && (
        <div className="mt-4 p-4 bg-pb-surface2 rounded border pb-hairline text-sm">
          <p className="font-mono text-[10px] text-pb-amber">{pdfResult.message}</p>
        </div>
      )}

      {pdfResult && pdfResult.available && (
        <div className="mt-4 p-4 bg-pb-surface2 rounded border pb-hairline">
          <p className="font-mono text-[10px] tracking-wide text-pb-faint mb-1 uppercase">Review honour-board columns</p>
          <p className="text-pb-faintest text-xs mb-3 leading-relaxed">
            Read {pdfResult.row_count} entries across {pdfResult.columns.length} columns. Set the
            category for each column, untick any you don't want, then import. Names are matched to
            players automatically; unmatched ones still save and can be linked later.
          </p>
          {pdfResult.warnings?.length > 0 && (
            <p className="font-mono text-[10px] text-pb-amber mb-3">⚠ {pdfResult.warnings.join(' ')}</p>
          )}
          <div className="space-y-1 max-h-96 overflow-y-auto pb-scroll">
            {pdfResult.columns.map(label => {
              const m = colMap[label] || {}
              const rows = pdfResult.rows.filter(r => r.label === label)
              const sample = rows.slice(0, 3).map(r => fmtName(r.player_name)).join(', ')
              return (
                <div key={label} className="pb-hairline-t pt-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <label className="flex items-center gap-2 w-48 flex-shrink-0 cursor-pointer">
                      <input type="checkbox" checked={!!m.include} onChange={e => setCol(label, { include: e.target.checked })} className="accent-[var(--pb-accent)]" />
                      <span className="text-pb-text text-sm truncate" title={label}>{tcLabel(label)}</span>
                    </label>
                    <span className="font-mono text-[10px] text-pb-faint w-12 flex-shrink-0">{rows.length}</span>
                    <select className={`${INPUT_CLS} w-40`} value={m.category || ''} onChange={e => setCol(label, { category: e.target.value })} disabled={!m.include}>
                      {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                    <input className={`${INPUT_CLS} flex-1 min-w-[8rem]`} value={m.achievement || ''} onChange={e => setCol(label, { achievement: e.target.value })} placeholder="Achievement" disabled={!m.include} />
                    <input className={`${INPUT_CLS} w-40`} value={m.subcategory || ''} onChange={e => setCol(label, { subcategory: e.target.value })} placeholder="Subcategory (optional)" disabled={!m.include} />
                  </div>
                  {m.include && sample && (
                    <p className="font-mono text-[10px] text-pb-faintest mt-1 ml-[3.5rem] truncate">e.g. {sample}{rows.length > 3 ? '…' : ''}</p>
                  )}
                </div>
              )
            })}
          </div>
          <div className="flex gap-2 mt-4">
            <button
              onClick={handlePdfImport}
              disabled={pdfImporting}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              {pdfImporting ? 'Importing…' : `Import ${pdfResult.rows.filter(r => colMap[r.label]?.include).length} achievements`}
            </button>
            <button
              onClick={() => { setPdfResult(null); setColMap({}) }}
              className="px-4 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {result && (
        <div className="mt-4 p-4 bg-pb-surface2 rounded border pb-hairline text-sm space-y-1">
          <p className="font-mono text-[11px]" style={{ color: 'var(--pb-accent)' }}>✓ Import complete — {result.created} achievements added</p>
          {result.skipped > 0 && <p className="text-pb-faint font-mono text-[10px]">Skipped: {result.skipped} rows (empty or invalid)</p>}
          {result.errors?.length > 0 && (
            <div className="text-pb-red font-mono text-[10px]">{result.errors.map((e, i) => <p key={i}>{e}</p>)}</div>
          )}
          {result.auto_matched?.length > 0 && (
            <div>
              <p className="font-mono text-[10px] mt-2" style={{ color: 'var(--pb-accent)' }}>
                ✓ Auto-linked {result.auto_matched.length} near-match name{result.auto_matched.length !== 1 ? 's' : ''} (e.g. initials → full name)
              </p>
              <div className="mt-1 flex flex-wrap gap-1">
                {result.auto_matched.map(m => (
                  <span key={m.name} className="font-mono text-[10px] bg-pb-surface border pb-hairline text-pb-dim px-2 py-0.5 rounded">
                    {m.name} <span className="text-pb-faint">→</span> {m.matched_name}
                  </span>
                ))}
              </div>
            </div>
          )}

          {result.suggested_matches?.length > 0 && (
            <div className="mt-3 pt-3 border-t pb-hairline">
              <p className="font-mono text-[10px] text-pb-amber mb-2">
                ? {result.suggested_matches.length} name{result.suggested_matches.length !== 1 ? 's need' : ' needs'} confirming. Pick the player, then link.
              </p>
              <div className="space-y-1.5 max-h-56 overflow-y-auto pb-scroll">
                {result.suggested_matches.map(s => (
                  <div key={s.name} className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-[10px] text-pb-text w-40 flex-shrink-0 truncate" title={s.name}>{s.name}</span>
                    <span className="text-pb-faint">→</span>
                    <select
                      className={`${INPUT_CLS} flex-1 min-w-[10rem] py-1`}
                      value={linkChoices[s.name] || ''}
                      onChange={e => setLinkChoices(prev => ({ ...prev, [s.name]: e.target.value }))}
                    >
                      <option value="">Don't link</option>
                      {s.candidates.map(c => (
                        <option key={c.player_id} value={c.player_id}>
                          {c.name}{c.confidence ? ` (${Math.round(c.confidence * 100)}%)` : ''}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
              <button
                onClick={handleApplyLinks}
                disabled={linking || !Object.values(linkChoices).some(Boolean)}
                className="mt-3 px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-pb-bg"
                style={{ background: 'var(--pb-accent)' }}
              >
                {linking ? 'Linking…' : 'Link selected players'}
              </button>
            </div>
          )}

          {result.unmatched_players?.length > 0 && (
            <div>
              <p className="text-pb-amber font-mono text-[10px] mt-2">⚠ Player names not matched ({result.unmatched_players.length}) — still saved, can be linked manually</p>
              <div className="mt-1 flex flex-wrap gap-1">
                {result.unmatched_players.map(n => (
                  <span key={n} className="font-mono text-[10px] bg-pb-surface border pb-hairline text-pb-amber px-2 py-0.5 rounded">{n}</span>
                ))}
              </div>
            </div>
          )}

          {dupes.length > 0 && (
            <div className="mt-3 pt-3 border-t pb-hairline">
              <div className="flex items-center justify-between mb-2">
                <p className="font-mono text-[10px] text-pb-amber">
                  ⚠ {dupes.length} duplicate{dupes.length !== 1 ? 's' : ''} skipped — already exist in the database
                </p>
                <button
                  onClick={toggleAll}
                  className="font-mono text-[10px] text-pb-faint hover:text-pb-text underline"
                >
                  {dupes.every((_, i) => checkedDupes[i]) ? 'Deselect all' : 'Select all'}
                </button>
              </div>
              <div className="space-y-1 max-h-48 overflow-y-auto pb-scroll">
                {dupes.map((d, i) => (
                  <label key={i} className="flex items-start gap-2 cursor-pointer group py-0.5">
                    <input
                      type="checkbox"
                      checked={!!checkedDupes[i]}
                      onChange={() => toggleDupe(i)}
                      className="mt-0.5 accent-[var(--pb-accent)] flex-shrink-0"
                    />
                    <span className="font-mono text-[10px] text-pb-dim group-hover:text-pb-text leading-relaxed">
                      <span className="text-pb-text">{d.player_name}</span>
                      {d.season && <span className="text-pb-faint"> · {d.season.replace(/_/g, '/')}</span>}
                      {' · '}{d.category}
                      {d.subcategory && <span className="text-pb-faint"> / {d.subcategory}</span>}
                      {' · '}{d.achievement}
                      {d.detail && <span className="text-pb-faint italic"> ({d.detail})</span>}
                    </span>
                  </label>
                ))}
              </div>
              {checkedCount > 0 && (
                <button
                  onClick={handleForceImport}
                  disabled={forcing}
                  className="mt-3 px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-pb-bg"
                  style={{ background: 'var(--pb-accent)' }}
                >
                  {forcing ? 'Importing…' : `Force import ${checkedCount} selected`}
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {history.length > 0 && (
        <div className="mt-5 pt-4 border-t pb-hairline">
          <p className="font-mono text-[10px] tracking-wide text-pb-faint mb-2 uppercase">Recent imports</p>
          <div className="space-y-1">
            {history.slice(0, 8).map(b => (
              <div key={b.id} className="flex flex-wrap items-center gap-2 py-1">
                <span className="font-mono text-[10px] text-pb-text truncate max-w-[14rem]" title={b.filename}>{b.filename || 'Import'}</span>
                <span className="font-mono text-[10px] text-pb-faint">
                  {b.status === 'undone'
                    ? `undone · ${b.created_count} removed`
                    : `${b.remaining} achievement${b.remaining !== 1 ? 's' : ''}`}
                </span>
                {b.created_at && (
                  <span className="font-mono text-[10px] text-pb-faintest">
                    {new Date(b.created_at).toLocaleDateString()}
                  </span>
                )}
                <span className="flex-1" />
                {b.status === 'undone' ? (
                  <span className="font-mono text-[10px] text-pb-faintest">undone</span>
                ) : (
                  <button
                    onClick={() => handleUndo(b)}
                    disabled={undoing === b.id || b.remaining === 0}
                    className="font-mono text-[10px] text-pb-red hover:underline disabled:opacity-40 disabled:no-underline"
                  >
                    {undoing === b.id ? 'Undoing…' : 'Undo'}
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {error && <p className="mt-3 font-mono text-[11px] text-pb-red">{error}</p>}
    </div>
  )
}

function AchievementFields({ form, setForm, seasons, awardDefs }) {
  const [customSubcat, setCustomSubcat] = useState(false)
  const [customAchievement, setCustomAchievement] = useState(false)

  const subcatOptions = getSubcategoriesFromDefs(awardDefs, form.category)
  const achievementOptions = getAchievementsFromDefs(awardDefs, form.category, form.subcategory)
  const seasonOpts = seasonOptionList(seasons, form.season, form.season_end)

  const setCategory = (cat) => {
    setForm(f => ({ ...f, category: cat, subcategory: '', achievement: '' }))
    setCustomSubcat(false)
    setCustomAchievement(false)
  }

  const setSubcat = (val) => {
    if (val === '__other__') { setCustomSubcat(true); setForm(f => ({ ...f, subcategory: '', achievement: '' })) }
    else { setCustomSubcat(false); setForm(f => ({ ...f, subcategory: val, achievement: '' })); setCustomAchievement(false) }
  }

  const setAchievement = (val) => {
    if (val === '__other__') { setCustomAchievement(true); setForm(f => ({ ...f, achievement: '' })) }
    else { setCustomAchievement(false); setForm(f => ({ ...f, achievement: val })) }
  }

  return (
    <>
      <div>
        <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Season {form.category === 'Office Bearer' ? 'Start' : ''}</label>
        <select className={INPUT_CLS} value={formatSeason(form.season)} onChange={e => setForm(f => ({ ...f, season: e.target.value }))}>
          <option value="">— All Time —</option>
          {seasonOpts.map(label => <option key={label} value={label}>{label}</option>)}
        </select>
      </div>
      {form.category === 'Office Bearer' && (
        <div>
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Season End</label>
          <select className={INPUT_CLS} value={formatSeason(form.season_end || '')} onChange={e => setForm(f => ({ ...f, season_end: e.target.value }))}>
            <option value="">— Present —</option>
            {seasonOpts.map(label => <option key={label} value={label}>{label}</option>)}
          </select>
        </div>
      )}
      <div>
        <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Category *</label>
        <select className={INPUT_CLS} value={form.category} onChange={e => setCategory(e.target.value)}>
          {CATEGORIES.map(c => <option key={c}>{c}</option>)}
        </select>
      </div>
      <div>
        <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Subcategory / Grade</label>
        {!customSubcat && subcatOptions.length > 0 ? (
          <select className={INPUT_CLS} value={form.subcategory} onChange={e => setSubcat(e.target.value)}>
            <option value="">— Select —</option>
            {subcatOptions.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
            <option value="__other__">Other…</option>
          </select>
        ) : (
          <div className="flex gap-1">
            <input className={INPUT_CLS} placeholder="e.g. 1st XI, WASTCA" value={form.subcategory}
              onChange={e => setForm(f => ({ ...f, subcategory: e.target.value, achievement: '' }))} />
            {customSubcat && <button onClick={() => { setCustomSubcat(false); setForm(f => ({ ...f, subcategory: '' })) }} className="text-pb-faint hover:text-pb-text px-1 text-lg">×</button>}
          </div>
        )}
      </div>
      <div>
        <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Achievement *</label>
        {!customAchievement && achievementOptions.length > 0 ? (
          <select className={INPUT_CLS} value={form.achievement} onChange={e => setAchievement(e.target.value)}>
            <option value="">— Select —</option>
            {achievementOptions.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
            <option value="__other__">Other…</option>
          </select>
        ) : (
          <div className="flex gap-1">
            <input className={INPUT_CLS} placeholder="e.g. Best & Fairest, President" value={form.achievement}
              onChange={e => setForm(f => ({ ...f, achievement: e.target.value }))} />
            {customAchievement && <button onClick={() => { setCustomAchievement(false); setForm(f => ({ ...f, achievement: '' })) }} className="text-pb-faint hover:text-pb-text px-1 text-lg">×</button>}
          </div>
        )}
      </div>
      <div>
        <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Detail</label>
        <input className={INPUT_CLS} placeholder="e.g. 436 runs at 39.64, captain"
          value={form.detail} onChange={e => setForm(f => ({ ...f, detail: e.target.value }))} />
      </div>
    </>
  )
}

function AchievementForm({ orgId, initial, players, seasons, awardDefs, onSave, onCancel }) {
  const [form, setForm] = useState(initial || { season: '', season_end: '', category: 'Club Award', subcategory: '', achievement: '', player_name: '', player_id: null, detail: '' })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const handleSave = async () => {
    if (!form.achievement.trim() || !form.player_name.trim()) { setError('Player Name and Achievement are required'); return }
    setSaving(true); setError(null)
    try {
      // Persist the canonical "YYYY/YY" label so editing an old award (e.g.
      // "Summer 1996/97") converges it onto the standard season — no duplicates.
      const normed = {
        ...form,
        season: form.season ? (formatSeason(form.season) || form.season) : form.season,
        season_end: form.season_end ? (formatSeason(form.season_end) || form.season_end) : form.season_end,
      }
      if (initial?.id) {
        await api.updateAchievement(initial.id, normed)
      } else {
        const payload = { ...normed, org_id: orgId }
        if (!payload.player_id) delete payload.player_id
        await api.createAchievement(payload)
      }
      onSave()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="bg-pb-surface2/60 border pb-hairline rounded p-5 mb-4">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-3">{initial?.id ? 'EDIT ACHIEVEMENT' : 'ADD ACHIEVEMENT'}</p>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
        <div>
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Player Name *</label>
          <PlayerAutocomplete
            players={players}
            value={form.player_name}
            onChange={({ name, id }) => setForm(f => ({ ...f, player_name: name, player_id: id }))}
          />
        </div>
        <AchievementFields form={form} setForm={setForm} seasons={seasons} awardDefs={awardDefs} />
      </div>
      {error && <p className="font-mono text-[10px] text-pb-red mb-2">{error}</p>}
      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-pb-bg"
          style={{ background: 'var(--pb-accent)' }}
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button
          onClick={onCancel}
          className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

function BulkAddPanel({ orgId, players, seasons, awardDefs, onSave, onCancel }) {
  const [form, setForm] = useState({ season: '', season_end: '', category: 'Club Award', subcategory: '', achievement: '', detail: '' })
  const [selectedPlayers, setSelectedPlayers] = useState([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  const filtered = query.trim().length >= 1
    ? players.filter(p => (p.display_name || p.name).toLowerCase().includes(query.trim().toLowerCase()) && !selectedPlayers.find(s => s.id === p.id)).slice(0, 10)
    : []

  const addPlayer = (p) => { setSelectedPlayers(prev => [...prev, p]); setQuery(''); setOpen(false) }
  const removePlayer = (id) => setSelectedPlayers(prev => prev.filter(p => p.id !== id))

  const handleSave = async () => {
    if (!form.achievement.trim()) { setError('Achievement is required'); return }
    if (selectedPlayers.length === 0) { setError('Select at least one player'); return }
    setSaving(true); setError(null)
    try {
      const season = form.season ? (formatSeason(form.season) || form.season) : form.season
      const season_end = form.season_end ? (formatSeason(form.season_end) || form.season_end) : form.season_end
      for (const p of selectedPlayers) {
        await api.createAchievement({ ...form, season, season_end, org_id: orgId, player_id: p.id, player_name: p.display_name || p.name })
      }
      onSave()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="pb-card p-5 mb-4" style={{ borderColor: 'var(--pb-accent)', borderWidth: '1px' }}>
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1">BULK ADD — MULTIPLE PLAYERS, ONE ACHIEVEMENT</p>
      <p className="font-mono text-[10px] text-pb-faintest mb-4">Select an achievement, then add all players who received it. One record is created per player.</p>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-4">
        <AchievementFields form={form} setForm={setForm} seasons={seasons} awardDefs={awardDefs} />
      </div>

      <div className="mb-4">
        <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1.5 block">Players *</label>
        <div ref={ref} className="relative">
          <input
            type="text"
            value={query}
            onChange={e => { setQuery(e.target.value); setOpen(true) }}
            onFocus={() => setOpen(true)}
            placeholder="Search and add players…"
            className={INPUT_CLS}
          />
          <Dropdown
            anchorRef={ref}
            open={open && filtered.length > 0}
            onClose={() => setOpen(false)}
            maxHeight={208}
            className="bg-pb-surface border pb-hairline rounded shadow-xl pb-scroll"
          >
            {filtered.map(p => (
              <button key={p.id} onMouseDown={() => addPlayer(p)}
                className="w-full text-left px-3 py-2 text-sm text-pb-dim hover:bg-pb-surface2 hover:text-pb-text">
                {p.display_name || p.name}
              </button>
            ))}
          </Dropdown>
        </div>
        {selectedPlayers.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-2">
            {selectedPlayers.map(p => (
              <span key={p.id} className="flex items-center gap-1 bg-pb-surface2 border pb-hairline text-pb-text text-xs px-2.5 py-1 rounded-full">
                {p.display_name || p.name}
                <button onClick={() => removePlayer(p.id)} className="text-pb-faint hover:text-pb-text ml-0.5">×</button>
              </span>
            ))}
          </div>
        )}
      </div>

      {error && <p className="font-mono text-[10px] text-pb-red mb-2">{error}</p>}
      <div className="flex gap-2 items-center">
        <button
          onClick={handleSave}
          disabled={saving || selectedPlayers.length === 0}
          className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold transition disabled:opacity-50 text-pb-bg"
          style={{ background: 'var(--pb-accent)' }}
        >
          {saving ? 'Saving…' : `Save ${selectedPlayers.length > 0 ? `${selectedPlayers.length} achievement${selectedPlayers.length !== 1 ? 's' : ''}` : 'achievements'}`}
        </button>
        <button
          onClick={onCancel}
          className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

export default function AchievementsAdmin({ embeddedOrgId }) {
  const params = useParams()
  const orgId = embeddedOrgId || params.orgId
  const [achievements, setAchievements] = useState(null)
  const [players, setPlayers] = useState([])
  const [seasons, setSeasons] = useState(null)
  const [awardDefs, setAwardDefs] = useState([])
  const [loading, setLoading] = useState(true)
  const [filterSeason, setFilterSeason] = useState('')
  const [filterCategory, setFilterCategory] = useState('')
  const [filterSearch, setFilterSearch] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [showBulk, setShowBulk] = useState(false)
  const [editItem, setEditItem] = useState(null)

  const load = () => {
    setLoading(true)
    api.listAchievements(orgId).then(data => {
      setAchievements(data)
      setLoading(false)
    }).catch(() => { setAchievements([]); setLoading(false) })
  }

  useEffect(() => {
    load()
    api.listPlayers(orgId).then(data => setPlayers(data || [])).catch(() => {})
    api.getOrgSeasons(orgId).then(data => setSeasons(data || [])).catch(() => {})
    api.listAwardDefinitions(orgId).then(data => setAwardDefs(data || [])).catch(() => {})
  }, [orgId])

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this achievement?')) return
    await api.deleteAchievement(id, orgId)
    setAchievements(prev => prev.filter(a => a.id !== id))
  }

  const handleSaved = () => { setShowAdd(false); setShowBulk(false); setEditItem(null); load() }

  if ((loading && !achievements) || seasons === null) return <PbSpinner message="Loading achievements…" />

  const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
  // Canonical "YYYY/YY" key for grouping, filtering and display. Collapses the
  // inconsistent stored values ("Summer 1996/97", "1996/97", "2016", "2025_26")
  // onto one season so they no longer show as duplicate groups. Orphaned UUIDs
  // (org recreated) keep their own bucket, rendered as "Unknown Season".
  const seasonKey = (s) => {
    if (!s) return ''
    if (UUID_RE.test(s)) return s
    return formatSeason(s)
  }
  const seasonDisplay = (s) => {
    if (!s || s === 'All Time') return 'All Time'
    if (UUID_RE.test(s)) return 'Unknown Season'
    return formatSeason(s)
  }

  const allSeasons = [...new Set((achievements || []).map(a => seasonKey(a.season)).filter(Boolean))].sort((a, b) => b.localeCompare(a))

  const filtered = (achievements || []).filter(a => {
    if (filterSeason && seasonKey(a.season) !== filterSeason) return false
    if (filterCategory && a.category !== filterCategory) return false
    if (filterSearch) {
      const q = filterSearch.toLowerCase()
      return a.player_name.toLowerCase().includes(q) || a.achievement.toLowerCase().includes(q) || (a.subcategory || '').toLowerCase().includes(q)
    }
    return true
  })

  const grouped = {}
  for (const a of filtered) {
    const s = seasonKey(a.season) || 'All Time'
    if (!grouped[s]) grouped[s] = {}
    if (!grouped[s][a.category]) grouped[s][a.category] = []
    grouped[s][a.category].push(a)
  }
  const groupedSeasons = Object.keys(grouped).sort((a, b) => {
    if (a === 'All Time') return 1
    if (b === 'All Time') return -1
    return b.localeCompare(a)
  })

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="mb-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="font-display font-bold text-3xl text-pb-text tracking-tight">Achievements & Honours</h1>
            <p className="text-pb-faint text-sm mt-1">Manage club awards, office bearers, premierships, and milestones</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => { setShowBulk(true); setShowAdd(false); setEditItem(null) }}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-dim hover:text-pb-text transition-colors"
            >
              Bulk Add
            </button>
            <button
              onClick={() => { setShowAdd(true); setShowBulk(false); setEditItem(null) }}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold transition text-pb-bg"
              style={{ background: 'var(--pb-accent)' }}
            >
              + Add Achievement
            </button>
          </div>
        </div>
      </div>

      <ImportPanel orgId={orgId} onImported={load} />

      {showBulk && (
        <BulkAddPanel orgId={orgId} players={players} seasons={seasons} awardDefs={awardDefs} onSave={handleSaved} onCancel={() => setShowBulk(false)} />
      )}

      {showAdd && !editItem && (
        <AchievementForm orgId={orgId} players={players} seasons={seasons} awardDefs={awardDefs} onSave={handleSaved} onCancel={() => setShowAdd(false)} />
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-5">
        <input
          className="bg-pb-surface border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent placeholder-pb-faintest w-48"
          placeholder="Search player or award…"
          value={filterSearch}
          onChange={e => setFilterSearch(e.target.value)}
        />
        <select
          className="bg-pb-surface border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent"
          value={filterSeason}
          onChange={e => setFilterSeason(e.target.value)}
        >
          <option value="">All Seasons</option>
          {allSeasons.map(s => <option key={s} value={s}>{seasonDisplay(s)}</option>)}
        </select>
        <select
          className="bg-pb-surface border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent"
          value={filterCategory}
          onChange={e => setFilterCategory(e.target.value)}
        >
          <option value="">All Categories</option>
          {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <span className="font-mono text-[11px] text-pb-faint self-center">{filtered.length} records</span>
      </div>

      {filtered.length === 0 && (
        <div className="pb-card p-10 text-center text-pb-faint font-mono text-[11px]">
          No achievements found. Use the import above or add one manually.
        </div>
      )}

      {groupedSeasons.map(season => (
        <div key={season} className="mb-6">
          <div className="flex items-center gap-3 mb-3">
            <span className="text-pb-text font-semibold text-sm">{seasonDisplay(season)}</span>
            <span className="h-px flex-1 bg-pb-hairline" />
            <span className="font-mono text-[10px] text-pb-faintest">
              {Object.values(grouped[season]).reduce((sum, arr) => sum + arr.length, 0)} achievements
            </span>
          </div>

          {Object.entries(grouped[season]).map(([cat, items]) => (
            <div key={cat} className="pb-card mb-3 overflow-hidden">
              <div className="px-4 py-2.5 bg-pb-surface2/40 pb-hairline-b flex items-center gap-2">
                <ThiingIcon src={CATEGORY_ICON_SRC[cat] || thiings.goldMedal} alt="" className="w-5 h-5" />
                <span className="font-mono text-[10px] tracking-wide3 text-pb-faint">{cat.toUpperCase()}</span>
              </div>

              <div>
                {items.map((a, i) => (
                  <div key={a.id} className={i ? 'pb-hairline-t' : ''}>
                    <div className="px-4 py-2.5 flex items-center gap-2 group hover:bg-pb-surface2 transition-colors">
                      <div className="flex-1 min-w-0 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                        <span className="text-pb-text text-sm font-medium truncate">{a.player_name}</span>
                        <span className="text-pb-dim text-sm truncate">{resolveAwardLabel(awardDefs, a.category, a.subcategory, a.achievement)}</span>
                        {a.subcategory && <span className="font-mono text-[10px] text-pb-faint">{a.subcategory}</span>}
                        {a.season_end && (
                          <span className="font-mono text-[10px] text-pb-faint">
                            {seasonDisplay(a.season)} — {seasonDisplay(a.season_end)}
                          </span>
                        )}
                        {a.detail && <span className="font-mono text-[10px] text-pb-faint italic">{a.detail}</span>}
                      </div>
                      <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                        <button
                          onClick={() => { setEditItem(a); setShowAdd(false); setShowBulk(false) }}
                          className="font-mono text-[10px] text-pb-faint hover:text-pb-text px-2 py-0.5 rounded hover:bg-pb-surface2"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleDelete(a.id)}
                          className="font-mono text-[10px] text-pb-red/70 hover:text-pb-red px-2 py-0.5 rounded hover:bg-pb-surface2"
                        >
                          ✕
                        </button>
                      </div>
                    </div>
                    {editItem?.id === a.id && (
                      <div className="px-4 py-3 pb-hairline-t bg-pb-surface2/20">
                        <AchievementForm
                          orgId={orgId}
                          initial={editItem}
                          players={players}
                          seasons={seasons}
                          awardDefs={awardDefs}
                          onSave={handleSaved}
                          onCancel={() => setEditItem(null)}
                        />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}
