import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../lib/api'
import BetterSocialsLayout from '../../components/admin/BetterSocialsLayout'
import {
  roundView, roundText, winText, ordinal, pulledComps, LEADER_TABLES, seasonBoards, seasonBlocks, milestoneRows,
} from '../../lib/performanceRound'

// Performance Tracker (Association Socials). One page per round across every
// grade the association follows. A grade is added by pasting ONE
// play.cricket.com.au match link from the round; the backend
// (services/performance_round.py) reads the whole grade round from it, and the
// grade takes its name from Cricket Australia's (renameable).
//
// The page is built to be read: one grade filter at the top that every section
// follows, each section folds away (remembered in this browser), and each has a
// Make post button that opens the matching Round Review layout in BetterPosts
// on this round and these grades. Copy, Download and Print give the picked
// grades as plain text. Season figures come from services/performance_season.py.

const INPUT = 'w-full min-w-0 bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text'
const FOLD_KEY = 'bs_perf_folded'

function withDefaults(data) {
  const d = data && typeof data === 'object' ? data : {}
  return {
    ...d,
    competitions: Array.isArray(d.competitions) ? d.competitions : [],
    notes: typeof d.notes === 'string' ? d.notes : '',
  }
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]))
}

function fileName(round) {
  return `${(round.round_label || 'round').replace(/[^\w-]+/g, '-').toLowerCase()}-performance.txt`
}

function readFolded() {
  try { return JSON.parse(localStorage.getItem(FOLD_KEY) || '{}') || {} } catch { return {} }
}

// ── Pieces (module level: a component declared in render remounts) ───────────

function Crest({ src, size = 20 }) {
  if (!src) return <span className="inline-block shrink-0 rounded-full bg-pb-surface2" style={{ width: size, height: size }} aria-hidden="true" />
  return <img src={src} alt="" className="inline-block object-contain shrink-0" style={{ width: size, height: size }} />
}

function Tabs({ value, onChange, options, label }) {
  return (
    <div className="flex flex-wrap gap-1" role="tablist" aria-label={label}>
      {options.map(o => (
        <button key={o.key} type="button" role="tab" aria-selected={value === o.key} onClick={() => onChange(o.key)}
          className={`px-2.5 py-1 rounded-full border text-xs ${value === o.key ? 'border-pb-accent text-pb-accent bg-pb-surface2' : 'pb-hairline text-pb-dim hover:text-pb-text'}`}>
          {o.label}{typeof o.count === 'number' ? <span className="ml-1 font-mono text-[10px] opacity-70">{o.count}</span> : null}
        </button>
      ))}
    </div>
  )
}

function Toggles({ values, onToggle, options, label }) {
  return (
    <div className="flex flex-wrap gap-1" role="group" aria-label={label}>
      {options.map(o => {
        const on = values.includes(o.key)
        return (
          <button key={o.key} type="button" aria-pressed={on} onClick={() => onToggle(o.key)}
            className={`px-2.5 py-1 rounded-full border text-xs ${on ? 'border-pb-accent text-pb-accent bg-pb-surface2' : 'pb-hairline text-pb-faint line-through decoration-1'}`}>
            {o.label}{typeof o.count === 'number' ? <span className="ml-1 font-mono text-[10px] opacity-70">{o.count}</span> : null}
          </button>
        )
      })}
    </div>
  )
}

function Section({ id, title, summary, folded, onFold, posts, onPost, controls, children }) {
  const open = !folded
  return (
    <section className="mb-3 rounded border pb-hairline bg-pb-surface" data-testid={`section-${id}`}>
      <header className="flex flex-wrap items-center gap-2 px-4 py-2.5">
        <button type="button" onClick={onFold} aria-expanded={open} className="flex items-center gap-2 min-w-0 text-left flex-1 basis-full sm:basis-auto">
          <span className={`text-pb-faint text-xs transition-transform ${open ? 'rotate-90' : ''}`} aria-hidden="true">▶</span>
          <h2 className="text-base font-semibold text-pb-text whitespace-nowrap">{title}</h2>
          {summary ? <span className="text-xs text-pb-dim truncate min-w-0">{summary}</span> : null}
        </button>
        {posts && posts.length > 0 && (
          <span className="flex flex-wrap gap-1">
            {posts.map(p => (
              <button key={p.template} type="button" className="btn-secondary btn-sm" onClick={() => onPost(p.template)} data-testid={`post-${p.template}`}>
                {posts.length > 1 ? p.label : 'Make post'}
              </button>
            ))}
          </span>
        )}
      </header>
      {open && (
        <div className="px-4 pb-4 border-t pb-hairline">
          {controls ? <div className="flex flex-wrap items-center gap-2 py-3">{controls}</div> : <div className="h-3" />}
          {children}
        </div>
      )}
    </section>
  )
}

function Glance({ label, big, name, sub, comp, logo, url, testid }) {
  return (
    <div className="min-w-0 rounded border pb-hairline bg-pb-surface2 p-3 flex flex-col gap-1" data-testid={testid}>
      <div className="font-mono text-[10px] tracking-wide2 text-pb-faint">{label.toUpperCase()}{comp ? ` · ${comp.toUpperCase()}` : ''}</div>
      {big ? <div className="text-xl font-semibold text-pb-accent leading-tight break-words">{big}</div> : null}
      {name ? <div className="flex items-center gap-1.5 text-sm font-medium text-pb-text min-w-0">{logo !== undefined ? <Crest src={logo} /> : null}<span className="min-w-0 break-words">{name}</span></div> : null}
      {sub ? <div className="text-xs text-pb-dim break-words">{sub}</div> : null}
      {url ? <a href={url} target="_blank" rel="noreferrer" className="text-[11px] text-pb-faint hover:text-pb-text self-start">scorecard ↗</a> : null}
    </div>
  )
}

// A ranked list: rank, crest, name with a second line, the figure on the right.
function Ranked({ rows, testid, empty = 'Nothing yet.' }) {
  if (!rows.length) return <p className="text-sm text-pb-dim">{empty}</p>
  return (
    <ol className="divide-y pb-hairline" data-testid={testid}>
      {rows.map((r, i) => (
        <li key={r.key || i} className="flex items-center gap-3 py-2 min-w-0">
          <span className="font-mono text-[11px] text-pb-faint w-5 shrink-0 text-right">{i + 1}</span>
          <Crest src={r.logo} size={26} />
          <div className="min-w-0 flex-1">
            <div className="text-sm text-pb-text truncate">{r.name}</div>
            {r.sub ? <div className="text-xs text-pb-dim truncate">{r.sub}</div> : null}
          </div>
          <div className="font-mono text-sm text-pb-text shrink-0 text-right">{r.value}</div>
        </li>
      ))}
    </ol>
  )
}

const SCOPES = [{ key: 'match', label: 'In the match' }, { key: 'season', label: 'Season' }, { key: 'career', label: 'Career' }]
const STATS = [{ key: 'batting', label: 'Batting' }, { key: 'bowling', label: 'Bowling' }, { key: 'fielding', label: 'Fielding' }, { key: 'games', label: 'Games' }]

function MilestoneTable({ rows }) {
  return (
    <ul className="divide-y pb-hairline" data-testid="milestone-rows">
      {rows.map((m, i) => (
        <li key={i} className="flex items-center gap-3 py-2 min-w-0">
          <Crest src={m.logo} size={26} />
          <div className="min-w-0 flex-1">
            <div className="text-sm text-pb-text truncate">{m.name} <span className="text-pb-dim">{m.club}</span></div>
            <div className="text-xs text-pb-dim truncate">{m.detail}</div>
          </div>
          <div className="shrink-0 text-right">
            <div className="text-sm font-semibold text-pb-accent">{m.title}</div>
            <div className="font-mono text-[10px] text-pb-faint">{m.scope === 'match' ? 'THIS MATCH' : m.scope.toUpperCase()} · {m.comp.toUpperCase()}</div>
          </div>
        </li>
      ))}
    </ul>
  )
}

// ── The page ─────────────────────────────────────────────────────────────────

export default function AdminPerformanceTracker() {
  const navigate = useNavigate()
  const [rounds, setRounds] = useState(null)
  const [round, setRound] = useState(null) // { id, round_label, round_date, data }
  const [error, setError] = useState('')
  const [saveState, setSaveState] = useState('')
  const [pulling, setPulling] = useState({})
  const [copied, setCopied] = useState(false)
  const [library, setLibrary] = useState([])
  // Season leaderboards and milestones (GET .../season): null not read, 'loading', or the payload.
  const [season, setSeason] = useState(null)
  // The grades every section shows ([] is all of them), and each section's own tabs.
  const [picked, setPicked] = useState([])
  const [perfTab, setPerfTab] = useState('batting')
  const [boardTab, setBoardTab] = useState('runs')
  const [msScopes, setMsScopes] = useState(['match', 'season', 'career'])
  const [msStats, setMsStats] = useState(['batting', 'bowling', 'fielding', 'games'])
  const [ladderKey, setLadderKey] = useState('')
  const [folded, setFolded] = useState(readFolded)
  const [newLink, setNewLink] = useState('')
  const [gradesOpen, setGradesOpen] = useState(false)
  const saveTimer = useRef(null)
  const pending = useRef(null)

  const fold = (id) => setFolded(f => {
    const next = { ...f, [id]: !f[id] }
    try { localStorage.setItem(FOLD_KEY, JSON.stringify(next)) } catch { /* a viewer convenience only */ }
    return next
  })

  const loadList = useCallback(() => api.performanceRounds()
    .then(d => { setRounds(d.rounds || []); return d.rounds || [] })
    .catch(e => { setError(e.message); setRounds([]); return [] }), [])

  const open = useCallback(async (id) => {
    setError('')
    try {
      const d = await api.performanceRound(id)
      setRound({ ...d, data: withDefaults(d.data) })
      setPicked([])
    } catch (e) { setError(e.message) }
  }, [])

  useEffect(() => { loadList().then(list => { if (list.length) open(list[0].id) }) }, [loadList, open])
  useEffect(() => { api.getSocialCrests().then(d => setLibrary(d?.crests || [])).catch(() => {}) }, [])

  // The season reading follows the round's pulls: a new pull reads it again.
  const pullStamp = round ? (round.data?.competitions || []).map(c => c.pulled_at || '').join('|') : ''
  const roundId = round?.id
  useEffect(() => {
    if (!roundId || !pullStamp.replace(/\|/g, '')) { setSeason(null); return undefined }
    let dead = false
    let timer = null
    let tries = 0
    const read = async () => {
      try {
        await new Promise(r => setTimeout(r, 1200)) // let the autosave of a fresh pull land first
        const d = await api.performanceSeason(roundId)
        if (dead) return
        setSeason(d)
        // Career totals are read in the background the first time: look again while any are pending.
        if ((d.career?.pending || []).length && tries++ < 20) timer = setTimeout(read, 20000)
      } catch (e) {
        if (!dead) setSeason({ error: e.message || 'Could not read the season' })
      }
    }
    setSeason('loading')
    read()
    return () => { dead = true; if (timer) clearTimeout(timer) }
  }, [roundId, pullStamp])

  const flush = useCallback(async () => {
    if (saveTimer.current) { clearTimeout(saveTimer.current); saveTimer.current = null }
    const job = pending.current
    if (!job) return
    pending.current = null
    setSaveState('Saving…')
    try {
      await api.performanceSaveRound(job.id, job.fields)
      setSaveState('Saved')
      setRounds(list => (list || []).map(r => (r.id === job.id ? { ...r, round_label: job.fields.round_label, round_date: job.fields.round_date } : r)))
    } catch (e) {
      setSaveState('Not saved')
      setError(e.message || 'Could not save')
    }
  }, [])

  const update = useCallback((fn) => {
    setRound(prev => {
      if (!prev) return prev
      const next = fn(prev)
      pending.current = { id: next.id, fields: { round_label: next.round_label || '', round_date: next.round_date || null, data: next.data } }
      if (saveTimer.current) clearTimeout(saveTimer.current)
      saveTimer.current = setTimeout(flush, 900)
      setSaveState('Unsaved changes')
      return next
    })
  }, [flush])

  useEffect(() => () => { flush() }, [flush])

  const setComp = (key, patch) => update(p => ({ ...p, data: { ...p.data, competitions: p.data.competitions.map(c => (c.key === key ? { ...c, ...patch } : c)) } }))

  const newRound = async () => {
    await flush()
    setError('')
    try {
      const d = await api.performanceCreateRound()
      await loadList()
      setRound({ ...d, data: withDefaults(d.data) })
      setPicked([])
    } catch (e) { setError(e.message) }
  }

  const archive = async () => {
    if (!round || !window.confirm(`Archive ${round.round_label || 'this round'}? It leaves the list.`)) return
    await flush()
    try {
      await api.performanceArchiveRound(round.id)
      const list = await loadList()
      if (list.length) open(list[0].id)
      else setRound(null)
    } catch (e) { setError(e.message) }
  }

  // Read one grade's round from its link. A grade with no name of its own takes
  // Cricket Australia's ("PSWL South A").
  const pull = async (key, linkOverride) => {
    const comp = round.data.competitions.find(c => c.key === key)
    const link = (linkOverride ?? comp?.link ?? '').trim()
    if (!link) { setComp(key, { pull: { kind: 'invalid', message: 'Paste a match link first.' } }); return }
    setPulling(s => ({ ...s, [key]: true }))
    try {
      const d = await api.performancePull(link)
      update(p => {
        const comps = p.data.competitions.map(c => (c.key === key ? {
          ...c, link, pull: d, pulled_at: new Date().toISOString(),
          name: (c.name || '').trim() || (d.kind === 'round' ? d.grade : '') || c.name,
        } : c))
        const label = p.round_label || (d.kind === 'round' ? d.round : '')
        const day = p.round_date || (d.kind === 'round' ? d.date || null : null)
        return { ...p, round_label: label, round_date: day, data: { ...p.data, competitions: comps } }
      })
    } catch (e) {
      setComp(key, { pull: { kind: 'error', message: e.message || 'Could not read that round' } })
    } finally {
      setPulling(s => ({ ...s, [key]: false }))
    }
  }
  const pullAll = async () => {
    for (const c of round.data.competitions) if ((c.link || '').trim()) await pull(c.key)
  }
  const addGrade = async () => {
    const link = newLink.trim()
    if (!link) return
    const key = `g${Date.now().toString(36)}`
    update(p => ({ ...p, data: { ...p.data, competitions: [...p.data.competitions, { key, name: '', link }] } }))
    setNewLink('')
    // The state update above lands before the pull reads it.
    await new Promise(r => setTimeout(r, 0))
    await pull(key, link)
  }
  const removeGrade = (key) => {
    const c = round.data.competitions.find(x => x.key === key)
    if (!window.confirm(`Remove ${c?.name || 'this grade'} from this round?`)) return
    update(p => ({ ...p, data: { ...p.data, competitions: p.data.competitions.filter(x => x.key !== key) } }))
    setPicked(ks => ks.filter(k => k !== key))
  }

  const data = round?.data
  const comps = data ? pulledComps(data) : []
  const keys = picked.length ? picked : null
  const v = useMemo(() => (data ? roundView(data, library, keys) : null), [data, library, keys && keys.join('|')]) // eslint-disable-line react-hooks/exhaustive-deps
  const seasonReady = season && season.competitions ? season : null
  const boards = useMemo(() => (seasonReady ? seasonBoards(seasonReady, keys, library, data) : null), [seasonReady, library, data, keys && keys.join('|')]) // eslint-disable-line react-hooks/exhaustive-deps
  const milestones = useMemo(() => (data ? milestoneRows(data, seasonReady, keys, library) : []), [data, seasonReady, library, keys && keys.join('|')]) // eslint-disable-line react-hooks/exhaustive-deps
  const togglePick = (key) => setPicked(ks => {
    const next = ks.includes(key) ? ks.filter(k => k !== key) : [...ks, key]
    return next.length === comps.length ? [] : next
  })

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(roundText(round, seasonReady, keys))
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { setError('Your browser blocked copying. Use Download instead.') }
  }
  const download = () => {
    const blob = new Blob([roundText(round, seasonReady, keys)], { type: 'text/plain;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = fileName(round)
    a.click()
    setTimeout(() => URL.revokeObjectURL(a.href), 1000)
  }
  const print = () => {
    const w = window.open('', '_blank')
    if (!w) return
    w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(round.round_label || 'Round')} performance</title>
      <style>body{font-family:Georgia,serif;max-width:780px;margin:24px auto;padding:0 16px;color:#111}pre{white-space:pre-wrap;font:14px/1.45 Georgia,serif}</style>
      </head><body><pre>${escapeHtml(roundText(round, seasonReady, keys))}</pre><script>window.onload=function(){window.print()}</script></body></html>`)
    w.document.close()
  }
  // Open the section's post on this round and these grades.
  const makePost = async (template, extra = {}) => {
    await flush()
    const q = new URLSearchParams({ template, round: round.id })
    if (keys) q.set('grades', keys.join(','))
    for (const [k, val] of Object.entries(extra)) if (val) q.set(k, val)
    navigate(`/admin/social-post?${q.toString()}`)
  }

  const actions = (
    <div className="flex items-center gap-2">
      {saveState && <span className="font-mono text-[10px] text-pb-faint" data-testid="save-state">{saveState.toUpperCase()}</span>}
      <button type="button" className="btn-primary btn-sm" onClick={newRound}>New round</button>
    </div>
  )

  const glanceCount = v ? [v.potr, v.topScore, v.bestBowl, v.biggest, v.closest].filter(Boolean).length + v.upsets.length : 0
  const perfRows = !v ? [] : perfTab === 'batting'
    ? v.batting.slice(0, 10).map((b, i) => ({ key: i, name: b.name, logo: b.logo, sub: `${b.team} v ${b.opp}${keys && keys.length === 1 ? '' : ` · ${b.comp}`}`, value: b.line }))
    : perfTab === 'bowling'
      ? v.bowling.slice(0, 10).map((b, i) => ({ key: i, name: b.name, logo: b.logo, sub: `${b.team} v ${b.opp}${keys && keys.length === 1 ? '' : ` · ${b.comp}`}`, value: b.line }))
      : perfTab === 'allround'
        ? v.performers.slice(0, 10).map((p, i) => ({ key: i, name: p.name, logo: p.logo, sub: `${p.line} v ${p.opp}${keys && keys.length === 1 ? '' : ` · ${p.comp}`}`, value: `${p.points} pts` }))
        : v.fielders.slice(0, 10).map((f, i) => ({ key: i, name: f.name, logo: f.logo, sub: `${f.team}${keys && keys.length === 1 ? '' : ` · ${f.comp}`}`, value: [`${f.catches} ct`, f.stumpings ? `${f.stumpings} st` : '', f.run_outs ? `${f.run_outs} ro` : ''].filter(Boolean).join(', ') }))
  const filmed = !v ? [] : [
    ...v.runOuts.filter(r => r.clip).map(r => ({ t: `${r.fielders.join(' and ') || 'Fielder'} ran out ${r.batter} (${r.batter_runs})`, r })),
    ...v.catches.filter(c => c.clip).slice(0, 8).map(c => ({ t: `${c.fielder || 'Fielder'}${c.keeper ? ' (keeper)' : ''} caught ${c.batter} (${c.batter_runs})`, r: c })),
  ]
  const shownMilestones = milestones.filter(m => msScopes.includes(m.scope) && msStats.includes(m.stat))
  const count = (pred) => milestones.filter(pred).length
  const ladders = v ? v.ladders.filter(l => l.rows.length) : []
  const ladder = ladders.find(l => l.compKey === ladderKey) || ladders[0]
  const nextShown = v ? v.nextRound.filter(n => n.fixtures.length) : []

  return (
    <BetterSocialsLayout title="Performance Tracker" actions={actions}>
      <div className="max-w-5xl mx-auto">
        {error && <div className="mb-3 p-3 rounded border border-red-400 text-sm text-red-600" role="alert">{error}</div>}

        {rounds !== null && !round && (
          <div className="p-6 rounded border pb-hairline bg-pb-surface text-center">
            <p className="text-sm text-pb-text mb-1">No rounds tracked yet.</p>
            <p className="text-xs text-pb-dim mb-3">Start one, paste a match link for each grade you follow, and the round's results, performers, milestones, ladders and next round come through.</p>
            <button type="button" className="btn-primary btn-sm" onClick={newRound}>Track a round</button>
          </div>
        )}

        {round && data && (
          <>
            {/* Round header: which round, the export, and the grades in it */}
            <section className="mb-3 rounded border pb-hairline bg-pb-surface p-4">
              <div className="flex flex-wrap items-center gap-2">
                {(rounds || []).length > 1 ? (
                  <select className="bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-sm text-pb-text max-w-full" value={round.id}
                    onChange={async (e) => { await flush(); open(e.target.value) }} aria-label="Open another round">
                    {rounds.map(r => <option key={r.id} value={r.id}>{r.round_label || 'Untitled round'}{r.round_date ? ` · ${r.round_date}` : ''}</option>)}
                  </select>
                ) : null}
                <input className="bg-transparent text-lg font-semibold text-pb-text min-w-0 flex-1 basis-40 border-b border-transparent hover:border-pb-hairline focus:border-pb-accent outline-none"
                  value={round.round_label || ''} placeholder="Round" aria-label="Round"
                  onChange={(e) => update(p => ({ ...p, round_label: e.target.value }))} />
                <span className="flex flex-wrap items-center gap-2">
                  <button type="button" className="btn-secondary btn-sm" onClick={copy}>{copied ? 'Copied' : 'Copy as text'}</button>
                  <button type="button" className="btn-secondary btn-sm" onClick={download}>Download</button>
                  <button type="button" className="btn-secondary btn-sm" onClick={print}>Print</button>
                  <button type="button" className="btn-quiet btn-sm" onClick={archive}>Archive</button>
                </span>
              </div>

              {/* Add a grade: paste a link, it reads the round and names itself */}
              <div className="mt-3 flex flex-wrap sm:flex-nowrap gap-2" data-testid="add-grade">
                <input className={`${INPUT} font-mono flex-1 basis-56`} value={newLink} onChange={(e) => setNewLink(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') addGrade() }}
                  placeholder="Paste any match link from the round to add a grade" aria-label="Match link for a new grade" />
                <button type="button" className="btn-primary btn-sm shrink-0" onClick={addGrade} disabled={!newLink.trim()}>Add grade</button>
              </div>
              <p className="text-[11px] text-pb-faint mt-1">Open any match from the round on play.cricket.com.au and copy the address. The whole grade round is read from it and the grade takes its own name, which you can change.</p>

              {data.competitions.length > 0 && (
                <div className="mt-3">
                  <button type="button" className="text-xs text-pb-dim hover:text-pb-text flex items-center gap-1" onClick={() => setGradesOpen(o => !o)} aria-expanded={gradesOpen}>
                    <span className={`transition-transform ${gradesOpen ? 'rotate-90' : ''}`} aria-hidden="true">▶</span>
                    {data.competitions.length} {data.competitions.length === 1 ? 'grade' : 'grades'}: names, links and pulls
                  </button>
                  {gradesOpen && (
                    <div className="mt-2 space-y-2" data-testid="grades">
                      {data.competitions.map(c => (
                        <div key={c.key} data-testid={`grade-${c.key}`}>
                          <div className="flex flex-wrap sm:flex-nowrap items-center gap-2">
                            <input className={`${INPUT} sm:w-44`} value={c.name || ''} aria-label="Grade name" placeholder="Name"
                              onChange={(e) => setComp(c.key, { name: e.target.value })} />
                            <input className={`${INPUT} font-mono flex-1 basis-40`} value={c.link || ''} aria-label={`${c.name || 'Grade'} match link`}
                              placeholder="https://play.cricket.com.au/match/…" onChange={(e) => setComp(c.key, { link: e.target.value })}
                              onKeyDown={(e) => { if (e.key === 'Enter') pull(c.key) }} />
                            <button type="button" className="btn-secondary btn-sm shrink-0" onClick={() => pull(c.key)} disabled={!!pulling[c.key]}>
                              {pulling[c.key] ? 'Pulling…' : c.pull?.kind === 'round' ? 'Pull again' : 'Pull'}
                            </button>
                            <button type="button" className="btn-quiet btn-sm shrink-0" onClick={() => removeGrade(c.key)} aria-label={`Remove ${c.name || 'grade'}`}>✕</button>
                          </div>
                        </div>
                      ))}
                      <button type="button" className="btn-secondary btn-sm" onClick={pullAll} disabled={Object.values(pulling).some(Boolean)}>Pull every grade again</button>
                    </div>
                  )}
                </div>
              )}
              {/* Every grade's state on one line each, always visible */}
              <ul className="mt-2 space-y-0.5">
                {data.competitions.map(c => (
                  <li key={c.key} className="text-xs" data-testid={`grade-state-${c.key}`}>
                    <span className="text-pb-text font-medium">{c.name || 'New grade'}</span>{' '}
                    {pulling[c.key] ? <span className="text-pb-dim">reading the round…</span>
                      : c.pull?.kind === 'round' ? <span className="text-pb-dim">{c.pull.grade} · {c.pull.round} · {c.pull.results.length} results</span>
                        : c.pull ? <span className="text-red-500">{c.pull.message}</span> : <span className="text-pb-dim">not pulled yet</span>}
                  </li>
                ))}
              </ul>
            </section>

            {comps.length === 0 ? (
              <p className="text-sm text-pb-dim text-center py-6">Add a grade to see the round.</p>
            ) : (
              <>
                {/* The one grade filter every section follows */}
                {comps.length > 1 && (
                  <div className="sticky top-0 z-10 mb-3 py-2 px-3 rounded border pb-hairline bg-pb-bg/95 backdrop-blur flex flex-wrap items-center gap-2" data-testid="grade-filter">
                    <span className="font-mono text-[10px] tracking-wide2 text-pb-faint">SHOWING</span>
                    <button type="button" aria-pressed={!picked.length} onClick={() => setPicked([])}
                      className={`px-2.5 py-1 rounded-full border text-xs ${!picked.length ? 'border-pb-accent text-pb-accent bg-pb-surface2' : 'pb-hairline text-pb-dim'}`}>All grades</button>
                    {comps.map(c => {
                      const on = !picked.length || picked.includes(c.key)
                      return (
                        <button key={c.key} type="button" aria-pressed={!!picked.length && picked.includes(c.key)}
                          onClick={() => (picked.length ? togglePick(c.key) : setPicked([c.key]))}
                          className={`px-2.5 py-1 rounded-full border text-xs ${picked.includes(c.key) ? 'border-pb-accent text-pb-accent bg-pb-surface2' : on ? 'pb-hairline text-pb-text' : 'pb-hairline text-pb-faint'}`}>
                          {c.name}
                        </button>
                      )
                    })}
                  </div>
                )}

                <Section id="glance" title="At a glance" summary={`${glanceCount} highlights`} folded={folded.glance} onFold={() => fold('glance')}
                  posts={[{ template: 'RV1', label: 'Round wrap post' }, { template: 'RV3', label: 'Player of the round post' }]} onPost={makePost}>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="glance">
                    {v.potr && <Glance testid="glance-potr" label="Player of the round" big={v.potr.line} name={v.potr.name} logo={v.potr.logo} sub={`${v.potr.team} v ${v.potr.opp}`} comp={v.potr.comp} />}
                    {v.topScore && <Glance testid="glance-top" label="Highest score" big={v.topScore.line} name={v.topScore.name} logo={v.topScore.logo} sub={`${v.topScore.team} v ${v.topScore.opp}`} comp={v.topScore.comp} />}
                    {v.bestBowl && <Glance label="Best bowling" big={v.bestBowl.line} name={v.bestBowl.name} logo={v.bestBowl.logo} sub={`${v.bestBowl.team} v ${v.bestBowl.opp}`} comp={v.bestBowl.comp} />}
                    {v.biggest && <Glance label="Biggest win" big={winText(v.biggest).replace(/^.*?\bwon\s+/, '')} name={v.biggest.winner === 'home' ? v.biggest.home : v.biggest.away} logo={v.biggest.winner === 'home' ? v.biggest.homeLogo : v.biggest.awayLogo} sub={`against ${v.biggest.winner === 'home' ? v.biggest.away : v.biggest.home}`} comp={v.biggest.comp} url={v.biggest.url} />}
                    {v.closest && <Glance testid="glance-closest" label="Closest match" big={winText(v.closest).replace(/^.*?\bwon\s+/, '')} name={`${v.closest.home} v ${v.closest.away}`} sub={`${v.closest.home_score} v ${v.closest.away_score}`} comp={v.closest.comp} url={v.closest.url} />}
                    {v.upsets.length
                      ? v.upsets.slice(0, 2).map(u => <Glance key={u.match_id} label="Upset" big={`${ordinal(u.winner_rank)} beat ${ordinal(u.loser_rank)}`} name={`${u.winner} beat ${u.loser}`} comp={u.comp} sub="Ladder places as they stand now" />)
                      : <Glance testid="glance-upset" label="Upsets" name="None this round" sub="No winner sat 3 or more places below the side it beat, on the ladder as it stands now." />}
                  </div>
                </Section>

                <Section id="results" title="Results" summary={`${v.results.length} matches`} folded={folded.results} onFold={() => fold('results')}
                  posts={[{ template: 'RV5', label: 'Results post' }]} onPost={makePost}>
                  <div className="space-y-4" data-testid="results">
                    {v.comps.map(c => (
                      <div key={c.key} data-testid={`results-${c.key}`}>
                        {v.comps.length > 1 && <h3 className="font-mono text-[10px] tracking-wide2 text-pb-faint mb-1">{c.name.toUpperCase()} · {c.pull.round.toUpperCase()}</h3>}
                        <ul className="divide-y pb-hairline">
                          {v.results.filter(r => r.compKey === c.key).map(r => (
                            <li key={r.match_id} className="py-2">
                              <div className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-0.5 items-center text-sm">
                                <div className={`flex items-center gap-2 min-w-0 ${r.winner === 'home' ? 'font-semibold text-pb-text' : 'text-pb-dim'}`}><Crest src={r.homeLogo} /> <span className="truncate">{r.home}</span></div>
                                <div className={`font-mono text-right ${r.winner === 'home' ? 'text-pb-text' : 'text-pb-dim'}`}>{r.home_score}</div>
                                <div className={`flex items-center gap-2 min-w-0 ${r.winner === 'away' ? 'font-semibold text-pb-text' : 'text-pb-dim'}`}><Crest src={r.awayLogo} /> <span className="truncate">{r.away}</span></div>
                                <div className={`font-mono text-right ${r.winner === 'away' ? 'text-pb-text' : 'text-pb-dim'}`}>{r.away_score}</div>
                              </div>
                              <div className="text-xs text-pb-dim mt-1">
                                {winText(r)}
                                {(r.top_bat?.length || r.top_bowl?.length) ? ` · ${[...(r.top_bat || []).slice(0, 1).map(b => `${b.name} ${b.line}`), ...(r.top_bowl || []).slice(0, 1).map(b => `${b.name} ${b.line}`)].join(', ')}` : ''}
                                {' '}<a href={r.url} target="_blank" rel="noreferrer" className="text-pb-faint hover:text-pb-text">scorecard ↗</a>
                              </div>
                            </li>
                          ))}
                        </ul>
                        {(c.pull.not_played || []).length > 0 && <p className="text-xs text-pb-dim mt-1">No result: {c.pull.not_played.map(m => `${m.home} v ${m.away}${m.status ? ` (${m.status})` : ''}`).join('; ')}</p>}
                        {(c.pull.skipped || []).length > 0 && <p className="text-xs text-amber-600 mt-1">Cricket Australia sent no scorecard for {c.pull.skipped.join(', ')}. Check those on play.cricket.com.au.</p>}
                      </div>
                    ))}
                  </div>
                </Section>

                <Section id="performers" title="Top performers this round" summary={v.topScore ? `${v.topScore.name} ${v.topScore.line}` : ''} folded={folded.performers} onFold={() => fold('performers')}
                  posts={[{ template: 'RV2', label: 'Top performers post' }]} onPost={makePost}
                  controls={<Tabs label="Performers" value={perfTab} onChange={setPerfTab} options={[
                    { key: 'batting', label: 'Batting' }, { key: 'bowling', label: 'Bowling' }, { key: 'allround', label: 'All-round' }, { key: 'fielding', label: 'Fielding' }]} />}>
                  <Ranked rows={perfRows} testid={`performers-${perfTab}`} />
                  {perfTab === 'allround' && <p className="text-[11px] text-pb-faint mt-2">Points are the same as Player of the Match: a run is 1, a wicket 20, a maiden 2, a catch, stumping or run out 8.</p>}
                  {perfTab === 'fielding' && filmed.length > 0 && (
                    <div className="mt-3">
                      <h3 className="font-mono text-[10px] tracking-wide2 text-pb-faint mb-1">FILMED CATCHES AND RUN OUTS</h3>
                      <ul className="space-y-0.5 text-sm text-pb-text" data-testid="filmed">
                        {filmed.map((x, i) => {
                          const url = v.results.find(r => r.match_id === x.r.match_id)?.url
                          return <li key={i}>{x.t} <span className="text-pb-dim">({x.r.team})</span>{url ? <> <a href={url} target="_blank" rel="noreferrer" className="text-xs text-pb-faint hover:text-pb-text">watch ↗</a></> : null}</li>
                        })}
                      </ul>
                    </div>
                  )}
                </Section>

                <Section id="season" title="Season leaderboards" summary={boards?.runs?.[0] ? `${boards.runs[0].name} leads with ${boards.runs[0].value} runs` : ''}
                  folded={folded.season} onFold={() => fold('season')}
                  posts={[{ template: 'RV6', label: 'Leaderboard post' }]} onPost={(t) => makePost(t, { board: boardTab })}
                  controls={<Tabs label="Leaderboard" value={boardTab} onChange={setBoardTab} options={LEADER_TABLES.map(([label, key]) => ({ key, label }))} />}>
                  {season === 'loading' || season === null ? <p className="text-sm text-pb-dim">Reading the season from play.cricket.com.au…</p>
                    : season.error ? <p className="text-sm text-red-500">{season.error}</p>
                      : (
                        <>
                          <Ranked testid={`leaders-${boardTab}`} rows={(boards?.[boardTab] || []).map(r => ({ key: r.pid, name: r.name, logo: r.logo, sub: [r.club, r.sub, (seasonBlocks(seasonReady, keys).length > 1 ? r.comps.join(', ') : '')].filter(Boolean).join(' · '), value: r.value }))} empty="No season figures yet." />
                          <p className="text-[11px] text-pb-faint mt-2">Season to date as play.cricket.com.au shows it today{seasonBlocks(seasonReady, keys).length > 1 ? ', the shown grades added together (a player in two counts both)' : ''}.</p>
                        </>
                      )}
                </Section>

                <Section id="milestones" title="Milestones" summary={`${milestones.length} this round`} folded={folded.milestones} onFold={() => fold('milestones')}
                  posts={[{ template: 'RV7', label: 'Milestones post' }]} onPost={(t) => makePost(t, { scopes: msScopes.join(','), stats: msStats.join(',') })}
                  controls={(
                    <>
                      <Toggles label="Milestone kind" values={msScopes} onToggle={(k) => setMsScopes(s => (s.includes(k) ? s.filter(x => x !== k) : [...s, k]))}
                        options={SCOPES.map(o => ({ ...o, count: count(m => m.scope === o.key) }))} />
                      <span className="w-px h-5 bg-pb-hairline mx-1" aria-hidden="true" />
                      <Toggles label="Milestone stat" values={msStats} onToggle={(k) => setMsStats(s => (s.includes(k) ? s.filter(x => x !== k) : [...s, k]))}
                        options={STATS.map(o => ({ ...o, count: count(m => m.stat === o.key) }))} />
                    </>
                  )}>
                  {shownMilestones.length ? <MilestoneTable rows={shownMilestones} />
                    : <p className="text-sm text-pb-dim">{milestones.length ? 'None with these filters.' : 'No milestones this round.'}</p>}
                  {seasonReady && (() => {
                    const pendingClubs = seasonReady.career?.pending || []
                    const failed = seasonReady.career?.failed || []
                    const notLatest = seasonBlocks(seasonReady, keys).filter(b => !b.latest).map(b => b.name)
                    return (
                      <div className="mt-3 space-y-1">
                        {pendingClubs.length > 0 && <p className="text-[11px] text-pb-dim" data-testid="career-pending">Reading career records for {pendingClubs.join(', ')}. This takes a few minutes the first time and the page updates itself.</p>}
                        {failed.length > 0 && <p className="text-[11px] text-amber-600">Career records could not be read for {failed.join(', ')}. They are tried again next time.</p>}
                        {notLatest.length > 0 && <p className="text-[11px] text-amber-600">{notLatest.join(', ')}: games have been played since this round, so season and career milestones cannot be worked out for it.</p>}
                        <details className="text-[11px] text-pb-faint">
                          <summary className="cursor-pointer">What counts</summary>
                          <p className="mt-1">In the match: a fifty, a hundred, five wickets, a hat-trick, or four dismissals in the field. Season: 100, 200, 300 runs and on, 10, 15, 20 wickets and on, 10 catches and on. Career: every 50 games, 1,000 runs, 50 wickets and 50 catches at the player's club. Careers are each club's own record on play.cricket.com.au: complete where a competition has always been scored on it, short where a club's older seasons were not.</p>
                        </details>
                      </div>
                    )
                  })()}
                </Section>

                <Section id="ladders" title="Ladders" summary={ladder ? `${ladder.rows[0]?.team} top of ${ladder.comp}` : ''} folded={folded.ladders} onFold={() => fold('ladders')}
                  posts={[{ template: 'RV8', label: 'Ladder post' }]} onPost={(t) => makePost(t, { ladder: ladder?.compKey })}
                  controls={ladders.length > 1 ? <Tabs label="Ladder" value={ladder?.compKey} onChange={setLadderKey} options={ladders.map(l => ({ key: l.compKey, label: l.comp }))} /> : null}>
                  {ladder ? (
                    <>
                      <table className="w-full text-sm text-pb-text" data-testid="ladder">
                        <thead><tr className="font-mono text-[10px] tracking-wide2 text-pb-faint text-left"><th className="py-1 w-6">#</th><th className="py-1">TEAM</th><th className="py-1 text-right">P</th><th className="py-1 text-right">W-L</th><th className="py-1 text-right">PTS</th></tr></thead>
                        <tbody>
                          {ladder.rows.map(r => (
                            <tr key={r.team_id || r.team} className="border-t pb-hairline">
                              <td className="py-1.5 font-mono text-pb-faint">{r.rank}</td>
                              <td className="py-1.5"><span className="flex items-center gap-2 min-w-0"><Crest src={r.logo} /><span className="truncate">{r.team}</span></span></td>
                              <td className="py-1.5 text-right font-mono text-pb-dim">{r.played ?? ''}</td>
                              <td className="py-1.5 text-right font-mono text-pb-dim">{r.won ?? 0}-{r.lost ?? 0}</td>
                              <td className="py-1.5 text-right font-mono">{r.points ?? 0}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      <p className="text-[11px] text-pb-faint mt-2">As Cricket Australia shows it now.</p>
                    </>
                  ) : <p className="text-sm text-pb-dim">No ladder published.</p>}
                </Section>

                <Section id="next" title="Next round" summary={nextShown[0]?.pick ? `Match of the round: ${nextShown[0].pick.home} v ${nextShown[0].pick.away}` : ''}
                  folded={folded.next} onFold={() => fold('next')}
                  posts={[{ template: 'RV4', label: 'Match of the round post' }, { template: 'RV9', label: 'Fixtures post' }]} onPost={makePost}>
                  <div className="space-y-4" data-testid="next">
                    {nextShown.map(n => (
                      <div key={n.compKey}>
                        <h3 className="font-mono text-[10px] tracking-wide2 text-pb-faint mb-1">{n.comp.toUpperCase()} · {(n.round || 'NEXT ROUND').toUpperCase()}</h3>
                        <ul className="divide-y pb-hairline">
                          {n.fixtures.map(f => (
                            <li key={f.match_id} className="py-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-pb-text">
                              <span className="flex items-center gap-1.5 min-w-0"><Crest src={f.homeLogo} />{f.home} <span className="text-pb-faint text-xs">{ordinal(f.home_rank)}</span></span>
                              <span className="text-pb-faint">v</span>
                              <span className="flex items-center gap-1.5 min-w-0">{f.bye && f.away === 'Bye' ? <span className="text-pb-dim">Bye</span> : <><Crest src={f.awayLogo} />{f.away} <span className="text-pb-faint text-xs">{ordinal(f.away_rank)}</span></>}</span>
                              {n.pick === f && <span className="font-mono text-[9px] px-1.5 py-0.5 rounded border border-pb-accent text-pb-accent">MATCH OF THE ROUND</span>}
                              <span className="basis-full text-xs text-pb-dim">{[f.label, f.time, f.venue].filter(Boolean).join(' · ')}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                    {!nextShown.length && <p className="text-sm text-pb-dim">No fixtures published for the next round.</p>}
                  </div>
                  <p className="text-[11px] text-pb-faint mt-2">Match of the round is the two highest placed sides meeting.</p>
                </Section>
              </>
            )}

            <Section id="notes" title="Notes" summary={data.notes ? 'Saved with the round' : ''} folded={folded.notes} onFold={() => fold('notes')}>
              <textarea className={INPUT} rows={4} value={data.notes} placeholder="Anything else from the round: club news, stories, shoutouts. It goes out with Copy and Download."
                onChange={(e) => update(p => ({ ...p, data: { ...p.data, notes: e.target.value } }))} aria-label="Notes" />
            </Section>
          </>
        )}
      </div>
    </BetterSocialsLayout>
  )
}
