import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../lib/api'
import BetterSocialsLayout from '../../components/admin/BetterSocialsLayout'
import { roundView, roundText, winText, ordinal, pulledComps } from '../../lib/performanceRound'

// Performance Tracker (Association Socials). One page per round across every
// competition the association follows. Each competition takes ONE
// play.cricket.com.au match link from the round; the backend
// (services/performance_round.py) reads the whole grade round from it. The page
// lays the round out to be read at a glance, and copies, downloads or prints as
// plain text for a podcast run sheet, a newsletter or a committee email. The
// Round Review posts in BetterPosts read the same saved round.

const INPUT = 'w-full min-w-0 bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text'
const LABEL = 'font-mono text-[10px] tracking-wide2 text-pb-faint block mb-1'
const DEFAULT_COMPS = [
  { key: 'north', name: 'North', link: '' },
  { key: 'south', name: 'South', link: '' },
  { key: 'east', name: 'East', link: '' },
]

function withDefaults(data) {
  const d = data && typeof data === 'object' ? data : {}
  return {
    ...d,
    competitions: Array.isArray(d.competitions) && d.competitions.length ? d.competitions : DEFAULT_COMPS,
    notes: typeof d.notes === 'string' ? d.notes : '',
  }
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]))
}

function fileName(round) {
  return `${(round.round_label || 'round').replace(/[^\w-]+/g, '-').toLowerCase()}-performance.txt`
}

// ── Pieces (module level: a component declared in render remounts) ───────────

function Card({ title, children, right, testid }) {
  return (
    <section className="mb-4 rounded border pb-hairline bg-pb-surface" data-testid={testid}>
      <header className="flex flex-wrap items-center gap-2 px-4 py-3 border-b pb-hairline">
        <h2 className="text-base font-semibold text-pb-text">{title}</h2>
        {right && <span className="ml-auto flex flex-wrap items-center gap-2">{right}</span>}
      </header>
      <div className="px-4 py-3">{children}</div>
    </section>
  )
}

function Crest({ src, size = 20 }) {
  if (!src) return null
  return <img src={src} alt="" className="inline-block object-contain shrink-0" style={{ width: size, height: size }} />
}

function Glance({ label, big, name, sub, comp, logo, url, testid }) {
  return (
    <div className="min-w-0 rounded border pb-hairline bg-pb-surface2 p-3 flex flex-col gap-1" data-testid={testid}>
      <div className="font-mono text-[10px] tracking-wide2 text-pb-faint">{label.toUpperCase()}{comp ? ` · ${comp.toUpperCase()}` : ''}</div>
      {big ? <div className="text-2xl font-semibold text-pb-accent leading-tight break-words">{big}</div> : null}
      {name ? <div className="flex items-center gap-1.5 text-sm font-medium text-pb-text min-w-0"><Crest src={logo} /><span className="min-w-0 break-words">{name}</span></div> : null}
      {sub ? <div className="text-xs text-pb-dim break-words">{sub}</div> : null}
      {url ? <a href={url} target="_blank" rel="noreferrer" className="text-[11px] text-pb-faint hover:text-pb-text self-start">scorecard ↗</a> : null}
    </div>
  )
}

function Table({ head, rows, testid }) {
  return (
    <div className="overflow-x-auto -mx-1" data-testid={testid}>
      <table className="w-full text-sm text-pb-text">
        <thead>
          <tr className="font-mono text-[10px] tracking-wide2 text-pb-faint text-left">
            {head.map((h, i) => <th key={i} className={`px-1 py-1 font-normal ${h.right ? 'text-right' : ''}`}>{h.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t pb-hairline align-top">
              {r.map((c, j) => <td key={j} className={`px-1 py-1.5 ${head[j]?.right ? 'text-right font-mono whitespace-nowrap' : ''} ${head[j]?.dim ? 'text-pb-dim' : ''}`}>{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function CompFilter({ comps, value, onChange }) {
  if (comps.length < 2) return null
  const opts = [{ key: '', name: 'All' }, ...comps.map(c => ({ key: c.key, name: c.name }))]
  return (
    <div className="flex flex-wrap gap-1" role="group" aria-label="Competition">
      {opts.map(o => (
        <button key={o.key || 'all'} type="button" onClick={() => onChange(o.key)} aria-pressed={value === o.key}
          className={`px-2 py-0.5 rounded border text-xs ${value === o.key ? 'border-pb-accent text-pb-accent' : 'pb-hairline text-pb-dim'}`}>
          {o.name}
        </button>
      ))}
    </div>
  )
}

function ResultsBlock({ comp }) {
  const p = comp.pull
  return (
    <div className="min-w-0" data-testid={`results-${comp.key}`}>
      <div className="flex flex-wrap items-baseline gap-2 mb-1">
        <h3 className="text-sm font-semibold text-pb-text">{comp.name}</h3>
        <span className="font-mono text-[10px] text-pb-faint">{p.grade} · {p.round} · {p.label}</span>
      </div>
      <ul className="divide-y pb-hairline">
        {p.results.map(r => (
          <li key={r.match_id} className="py-2">
            <div className="text-sm text-pb-text">
              <span className={r.winner === 'home' ? 'font-semibold' : ''}>{r.home} {r.home_score}</span>
              {' v '}
              <span className={r.winner === 'away' ? 'font-semibold' : ''}>{r.away} {r.away_score}</span>
            </div>
            <div className="text-xs text-pb-dim">
              {winText(r)}{' '}
              <a href={r.url} target="_blank" rel="noreferrer" className="text-pb-faint hover:text-pb-text">scorecard ↗</a>
            </div>
            {(r.top_bat?.length || r.top_bowl?.length) ? (
              <div className="text-xs text-pb-dim mt-0.5">
                {[...(r.top_bat || []).map(b => `${b.name} ${b.line}`), ...(r.top_bowl || []).map(b => `${b.name} ${b.line}`)].join(' · ')}
              </div>
            ) : null}
          </li>
        ))}
      </ul>
      {(p.not_played || []).length > 0 && (
        <p className="text-xs text-pb-dim mt-1">No result: {p.not_played.map(m => `${m.home} v ${m.away}${m.status ? ` (${m.status})` : ''}`).join('; ')}</p>
      )}
      {(p.skipped || []).length > 0 && (
        <p className="text-xs text-amber-600 mt-1">Cricket Australia sent no scorecard for {p.skipped.join(', ')}. Check those on play.cricket.com.au.</p>
      )}
    </div>
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
  const [filter, setFilter] = useState('')
  const saveTimer = useRef(null)
  const pending = useRef(null)

  const loadList = useCallback(() => api.performanceRounds()
    .then(d => { setRounds(d.rounds || []); return d.rounds || [] })
    .catch(e => { setError(e.message); setRounds([]); return [] }), [])

  const open = useCallback(async (id) => {
    setError('')
    try {
      const d = await api.performanceRound(id)
      setRound({ ...d, data: withDefaults(d.data) })
    } catch (e) { setError(e.message) }
  }, [])

  useEffect(() => { loadList().then(list => { if (list.length) open(list[0].id) }) }, [loadList, open])

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

  const setComp = (i, patch) => update(p => ({ ...p, data: { ...p.data, competitions: p.data.competitions.map((c, j) => (j === i ? { ...c, ...patch } : c)) } }))

  const newRound = async () => {
    await flush()
    setError('')
    try {
      const d = await api.performanceCreateRound()
      await loadList()
      setRound({ ...d, data: withDefaults(d.data) })
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

  const pull = async (i) => {
    const comp = round.data.competitions[i]
    if (!(comp.link || '').trim()) { setComp(i, { pull: { kind: 'invalid', message: 'Paste a match link first.' } }); return }
    setPulling(s => ({ ...s, [i]: true }))
    try {
      const d = await api.performancePull(comp.link.trim())
      update(p => {
        const comps = p.data.competitions.map((c, j) => (j === i ? { ...c, pull: d, pulled_at: new Date().toISOString() } : c))
        const label = p.round_label || (d.kind === 'round' ? d.round : '')
        const day = p.round_date || (d.kind === 'round' ? d.date || null : null)
        return { ...p, round_label: label, round_date: day, data: { ...p.data, competitions: comps } }
      })
    } catch (e) {
      setComp(i, { pull: { kind: 'error', message: e.message || 'Could not read that round' } })
    } finally {
      setPulling(s => ({ ...s, [i]: false }))
    }
  }
  const pullAll = async () => {
    for (let i = 0; i < round.data.competitions.length; i++) {
      if ((round.data.competitions[i].link || '').trim()) await pull(i)
    }
  }
  const addComp = () => update(p => ({ ...p, data: { ...p.data, competitions: [...p.data.competitions, { key: `c${Date.now()}`, name: 'New', link: '' }] } }))
  const removeComp = (i) => {
    if (!window.confirm(`Remove ${round.data.competitions[i].name} from this round?`)) return
    update(p => ({ ...p, data: { ...p.data, competitions: p.data.competitions.filter((_, j) => j !== i) } }))
  }

  const data = round?.data
  const v = useMemo(() => (data ? roundView(data) : null), [data])
  const comps = data ? pulledComps(data) : []
  const inFilter = (x) => !filter || x.compKey === filter

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(roundText(round))
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { setError('Your browser blocked copying. Use Download instead.') }
  }
  const download = () => {
    const blob = new Blob([roundText(round)], { type: 'text/plain;charset=utf-8' })
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
      </head><body><pre>${escapeHtml(roundText(round))}</pre><script>window.onload=function(){window.print()}</script></body></html>`)
    w.document.close()
  }
  const makePosts = async () => { await flush(); navigate(`/admin/social-post?type=review&round=${round.id}`) }

  const actions = (
    <div className="flex items-center gap-2">
      {saveState && <span className="font-mono text-[10px] text-pb-faint" data-testid="save-state">{saveState.toUpperCase()}</span>}
      <button type="button" className="btn-primary btn-sm" onClick={newRound}>New round</button>
    </div>
  )

  return (
    <BetterSocialsLayout title="Performance Tracker" actions={actions}>
      <div className="max-w-5xl mx-auto">
        {error && <div className="mb-3 p-3 rounded border border-red-400 text-sm text-red-600" role="alert">{error}</div>}

        {rounds !== null && !round && (
          <div className="p-6 rounded border pb-hairline bg-pb-surface text-center">
            <p className="text-sm text-pb-text mb-1">No rounds tracked yet.</p>
            <p className="text-xs text-pb-dim mb-3">Start one, paste a match link for each competition, and the round's results, performers, milestones, ladders and next round come through.</p>
            <button type="button" className="btn-primary btn-sm" onClick={newRound}>Track a round</button>
          </div>
        )}

        {round && data && (
          <>
            <section className="mb-4 rounded border pb-hairline bg-pb-surface p-4">
              <div className="flex flex-wrap items-center gap-2 mb-3">
                {(rounds || []).length > 1 ? (
                  <select className="bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-sm text-pb-text max-w-full" value={round.id}
                    onChange={async (e) => { await flush(); open(e.target.value) }} aria-label="Open another round">
                    {rounds.map(r => <option key={r.id} value={r.id}>{r.round_label || 'Untitled round'}{r.round_date ? ` · ${r.round_date}` : ''}</option>)}
                  </select>
                ) : <h2 className="text-base font-semibold text-pb-text">Round</h2>}
                <span className="ml-auto flex flex-wrap items-center gap-2">
                  <button type="button" className="btn-secondary btn-sm" onClick={copy}>{copied ? 'Copied' : 'Copy as text'}</button>
                  <button type="button" className="btn-secondary btn-sm" onClick={download}>Download</button>
                  <button type="button" className="btn-secondary btn-sm" onClick={print}>Print</button>
                  <button type="button" className="btn-secondary btn-sm" onClick={makePosts} disabled={!comps.length}>Make posts</button>
                  <button type="button" className="btn-quiet btn-sm" onClick={archive}>Archive</button>
                </span>
              </div>
              <div className="grid grid-cols-2 gap-3 mb-4">
                <label className="min-w-0"><span className={LABEL}>ROUND</span>
                  <input className={INPUT} value={round.round_label || ''} placeholder="Round 5" aria-label="Round"
                    onChange={(e) => update(p => ({ ...p, round_label: e.target.value }))} />
                </label>
                <label className="min-w-0"><span className={LABEL}>FIRST DAY</span>
                  <input className={INPUT} type="date" value={round.round_date || ''}
                    onChange={(e) => update(p => ({ ...p, round_date: e.target.value || null }))} />
                </label>
              </div>
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <h3 className="text-sm font-semibold text-pb-text">Competitions</h3>
                <span className="ml-auto flex gap-2">
                  <button type="button" className="btn-quiet btn-sm" onClick={addComp}>Add competition</button>
                  <button type="button" className="btn-primary btn-sm" onClick={pullAll} disabled={Object.values(pulling).some(Boolean)}>Pull all</button>
                </span>
              </div>
              <p className="text-xs text-pb-dim mb-3">Paste any one match link from the round for each competition (open the match on play.cricket.com.au and copy the address). The whole round in that grade is read from it.</p>
              <div className="space-y-2">
                {data.competitions.map((c, i) => (
                  <div key={c.key || i} data-testid={`comp-${i}`}>
                    <div className="flex flex-wrap sm:flex-nowrap items-center gap-2">
                      <input className={`${INPUT} sm:w-28`} value={c.name} aria-label="Competition name" onChange={(e) => setComp(i, { name: e.target.value })} />
                      <input className={`${INPUT} font-mono flex-1 basis-40`} value={c.link || ''} aria-label={`${c.name} match link`}
                        placeholder="https://play.cricket.com.au/match/…" onChange={(e) => setComp(i, { link: e.target.value })}
                        onKeyDown={(e) => { if (e.key === 'Enter') pull(i) }} />
                      <button type="button" className="btn-secondary btn-sm shrink-0" onClick={() => pull(i)} disabled={!!pulling[i]}>
                        {pulling[i] ? 'Pulling…' : c.pull?.kind === 'round' ? 'Pull again' : 'Pull'}
                      </button>
                      <button type="button" className="btn-quiet btn-sm shrink-0" onClick={() => removeComp(i)} aria-label={`Remove ${c.name}`}>✕</button>
                    </div>
                    {c.pull && (
                      <div className="text-xs mt-1">
                        {c.pull.kind === 'round'
                          ? <span className="text-pb-dim">{c.pull.grade} · {c.pull.round} · {c.pull.results.length} results{c.pulled_at ? ` · read ${new Date(c.pulled_at).toLocaleString('en-AU', { weekday: 'short', hour: 'numeric', minute: '2-digit' })}` : ''}</span>
                          : <span className="text-red-500">{c.pull.message}</span>}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>

            {comps.length === 0 ? (
              <p className="text-sm text-pb-dim text-center py-6">Pull a competition to see the round.</p>
            ) : (
              <>
                <Card title="At a glance" testid="glance">
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {v.potr && <Glance testid="glance-potr" label="Player of the round" big={v.potr.line} name={v.potr.name} logo={v.potr.logo} sub={`${v.potr.team} v ${v.potr.opp}`} comp={v.potr.comp} />}
                    {v.topScore && <Glance label="Highest score" big={v.topScore.line} name={v.topScore.name} logo={v.topScore.logo} sub={`${v.topScore.team} v ${v.topScore.opp}`} comp={v.topScore.comp} />}
                    {v.bestBowl && <Glance label="Best bowling" big={v.bestBowl.line} name={v.bestBowl.name} logo={v.bestBowl.logo} sub={`${v.bestBowl.team} v ${v.bestBowl.opp}`} comp={v.bestBowl.comp} />}
                    {v.biggest && <Glance label="Biggest win" big={winText(v.biggest).replace(/^.*?\bwon\s+/, '')} name={v.biggest.winner === 'home' ? v.biggest.home : v.biggest.away} logo={v.biggest.winner === 'home' ? v.biggest.homeLogo : v.biggest.awayLogo} sub={`against ${v.biggest.winner === 'home' ? v.biggest.away : v.biggest.home}`} comp={v.biggest.comp} url={v.biggest.url} />}
                    {v.closest && <Glance testid="glance-closest" label="Closest match" big={winText(v.closest).replace(/^.*?\bwon\s+/, '')} name={`${v.closest.home} ${v.closest.home_score} v ${v.closest.away} ${v.closest.away_score}`} sub={winText(v.closest)} comp={v.closest.comp} url={v.closest.url} />}
                    {v.upsets.length
                      ? v.upsets.slice(0, 2).map(u => <Glance key={u.match_id} label="Upset" big={`${ordinal(u.winner_rank)} beat ${ordinal(u.loser_rank)}`} name={`${u.winner} beat ${u.loser}`} comp={u.comp} sub="Ladder places as they stand now" />)
                      : <Glance testid="glance-upset" label="Upsets" name="None this round" sub="No winner sat 3 or more places below the side it beat, on the ladder as it stands now." />}
                  </div>
                </Card>

                <Card title="Results" testid="results">
                  <div className="grid md:grid-cols-2 gap-x-6 gap-y-4">
                    {comps.map(c => <ResultsBlock key={c.key} comp={c} />)}
                  </div>
                </Card>

                <Card title="Top performers" right={<CompFilter comps={comps} value={filter} onChange={setFilter} />} testid="performers">
                  <div className="grid lg:grid-cols-2 gap-x-6 gap-y-4">
                    <div className="min-w-0">
                      <h3 className="font-mono text-[10px] tracking-wide2 text-pb-faint mb-1">BATTING</h3>
                      <Table testid="table-batting" head={[{ label: 'PLAYER' }, { label: 'CLUB', dim: true }, { label: 'V', dim: true }, { label: 'RUNS', right: true }]}
                        rows={v.batting.filter(inFilter).slice(0, 10).map(b => [b.name, b.team, `${b.opp}${filter ? '' : ` · ${b.comp}`}`, b.line])} />
                    </div>
                    <div className="min-w-0">
                      <h3 className="font-mono text-[10px] tracking-wide2 text-pb-faint mb-1">BOWLING</h3>
                      <Table testid="table-bowling" head={[{ label: 'PLAYER' }, { label: 'CLUB', dim: true }, { label: 'V', dim: true }, { label: 'FIGURES', right: true }]}
                        rows={v.bowling.filter(inFilter).slice(0, 10).map(b => [b.name, b.team, `${b.opp}${filter ? '' : ` · ${b.comp}`}`, b.line])} />
                    </div>
                    <div className="min-w-0 lg:col-span-2">
                      <h3 className="font-mono text-[10px] tracking-wide2 text-pb-faint mb-1">BEST ALL-ROUND DAYS</h3>
                      <Table testid="table-performers" head={[{ label: 'PLAYER' }, { label: 'CLUB', dim: true }, { label: 'DID', dim: true }, { label: 'PTS', right: true }]}
                        rows={v.performers.filter(inFilter).slice(0, 8).map(p => [p.name, p.team, `${p.line} v ${p.opp}${filter ? '' : ` · ${p.comp}`}`, p.points])} />
                      <p className="text-[11px] text-pb-faint mt-1">Points are the same as Player of the Match: a run is 1, a wicket 20, a maiden 2, a catch, stumping or run out 8.</p>
                    </div>
                  </div>
                </Card>

                <Card title="Milestones and moments" testid="moments">
                  {v.milestones.filter(inFilter).length
                    ? <ul className="space-y-1 mb-3">{v.milestones.filter(inFilter).map((m, i) => <li key={i} className="text-sm text-pb-text">{m.text} <span className="text-pb-faint text-xs">{m.comp}</span></li>)}</ul>
                    : <p className="text-sm text-pb-dim mb-3">No fifties, hundreds, five-fors or hat-tricks this round.</p>}
                  <div className="grid md:grid-cols-2 gap-x-6 gap-y-3">
                    <div className="min-w-0">
                      <h3 className="font-mono text-[10px] tracking-wide2 text-pb-faint mb-1">IN THE FIELD</h3>
                      <ul className="space-y-0.5 text-sm text-pb-text">
                        {v.fielders.filter(inFilter).slice(0, 5).map((f, i) => (
                          <li key={i}>{f.name} <span className="text-pb-dim">({f.team})</span> {f.catches} ct{f.stumpings ? `, ${f.stumpings} st` : ''}{f.run_outs ? `, ${f.run_outs} ro` : ''}</li>
                        ))}
                      </ul>
                    </div>
                    <div className="min-w-0">
                      <h3 className="font-mono text-[10px] tracking-wide2 text-pb-faint mb-1">FILMED CATCHES AND RUN OUTS</h3>
                      <ul className="space-y-0.5 text-sm text-pb-text" data-testid="filmed">
                        {[...v.runOuts.filter(r => r.clip).map(r => ({ t: `${r.fielders.join(' and ') || 'Fielder'} ran out ${r.batter} (${r.batter_runs})`, r })),
                          ...v.catches.filter(c => c.clip).slice(0, 6).map(c => ({ t: `${c.fielder || 'Fielder'}${c.keeper ? ' (keeper)' : ''} caught ${c.batter} (${c.batter_runs})`, r: c }))]
                          .filter(x => inFilter(x.r)).map((x, i) => {
                            const url = v.results.find(r => r.match_id === x.r.match_id)?.url
                            return <li key={i}>{x.t} <span className="text-pb-dim">({x.r.team})</span>{url ? <> <a href={url} target="_blank" rel="noreferrer" className="text-xs text-pb-faint hover:text-pb-text">watch ↗</a></> : null}</li>
                          })}
                      </ul>
                      <p className="text-[11px] text-pb-faint mt-1">Cricket Australia films some games. Open the match to watch the clip.</p>
                    </div>
                  </div>
                </Card>

                <Card title="Ladders" testid="ladders">
                  <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {v.ladders.filter(l => l.rows.length).map(l => (
                      <div key={l.compKey} className="min-w-0">
                        <h3 className="font-mono text-[10px] tracking-wide2 text-pb-faint mb-1">{l.comp.toUpperCase()}</h3>
                        <Table head={[{ label: '#' }, { label: 'TEAM' }, { label: 'W-L', right: true }, { label: 'PTS', right: true }]}
                          rows={l.rows.map(r => [r.rank, r.team, `${r.won ?? 0}-${r.lost ?? 0}`, r.points ?? 0])} />
                      </div>
                    ))}
                  </div>
                  <p className="text-[11px] text-pb-faint mt-2">Ladders as Cricket Australia shows them now.</p>
                </Card>

                <Card title="Next round" testid="next">
                  <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {v.nextRound.filter(n => n.fixtures.length).map(n => (
                      <div key={n.compKey} className="min-w-0">
                        <h3 className="font-mono text-[10px] tracking-wide2 text-pb-faint mb-1">{n.comp.toUpperCase()} · {(n.round || 'NEXT ROUND').toUpperCase()}</h3>
                        <ul className="space-y-1 text-sm text-pb-text">
                          {n.fixtures.map(f => (
                            <li key={f.match_id} className={n.pick === f ? 'font-semibold' : ''}>
                              {f.home} ({ordinal(f.home_rank)}) v {f.away} ({ordinal(f.away_rank)})
                              {n.pick === f && <span className="ml-1 font-mono text-[9px] text-pb-accent">MATCH OF THE ROUND</span>}
                              <div className="text-xs text-pb-dim font-normal">{[f.label, f.time, f.venue].filter(Boolean).join(' · ')}</div>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                  <p className="text-[11px] text-pb-faint mt-2">Match of the round is the two highest placed sides meeting.</p>
                </Card>
              </>
            )}

            <Card title="Notes">
              <textarea className={INPUT} rows={4} value={data.notes} placeholder="Anything else from the round: club news, stories, shoutouts. It goes out with the copy and the download."
                onChange={(e) => update(p => ({ ...p, data: { ...p.data, notes: e.target.value } }))} aria-label="Notes" />
            </Card>
          </>
        )}
      </div>
    </BetterSocialsLayout>
  )
}
