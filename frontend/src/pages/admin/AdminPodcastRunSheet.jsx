import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../lib/api'
import BetterSocialsLayout from '../../components/admin/BetterSocialsLayout'

// Podcast run sheet (BetterSocials). The hosts' Sunday night plan for a round
// review episode, laid out like their Word template: Episode details, then the
// seven segments, the Sunday night prep checklist and the close.
//
// Each competition takes ONE play.cricket.com.au match link from the round. The
// backend (services/podcast_round.py) reads the whole grade round from it and
// hands back results, the best batting and bowling, performers, milestones,
// catches and run outs (filmed ones flagged), the ladder and the next round.
// Those fill the suggestions beside each item; a click adds a suggestion to the
// notes, and the notes are what gets printed. Everything saves as you type.

const INPUT = 'w-full min-w-0 bg-pb-surface2 border pb-hairline rounded px-3 py-2 text-sm text-pb-text'
const LABEL = 'font-mono text-[10px] tracking-wide2 text-pb-faint block mb-1'

const DEFAULT_COMPS = [
  { key: 'north', name: 'North', link: '' },
  { key: 'south', name: 'South', link: '' },
  { key: 'east', name: 'East', link: '' },
]
const DEFAULT_HOSTS = [
  { name: 'Sam', prep: 'PlayHQ results, ladders, stats, milestones' },
  { name: 'Shay', prep: 'Club stories, community news, guest ideas, social events' },
]
const DEFAULT_DURATIONS = { opening: 3, grounds: 10, stats: 5, awards: 5, spotlight: 3, guest: 0, ahead: 3 }

// The template's segments. `mins` keys into durations.
const SEGMENTS = [
  { key: 'opening', title: '1. Opening', hint: '2 to 3 mins' },
  { key: 'grounds', title: '2. Around the Grounds', hint: '10 mins' },
  { key: 'stats', title: '3. Stats Corner', hint: '5 mins' },
  { key: 'awards', title: '4. Awards', hint: '5 mins' },
  { key: 'spotlight', title: '5. Club Spotlight', hint: '3 mins' },
  { key: 'guest', title: '6. Guest Segment', hint: 'Optional' },
  { key: 'ahead', title: '7. Looking Ahead', hint: '2 to 3 mins' },
]

function withDefaults(data) {
  const d = data && typeof data === 'object' ? data : {}
  return {
    ...d,
    competitions: Array.isArray(d.competitions) && d.competitions.length ? d.competitions : DEFAULT_COMPS,
    hosts: Array.isArray(d.hosts) && d.hosts.length ? d.hosts : DEFAULT_HOSTS,
    durations: { ...DEFAULT_DURATIONS, ...(d.durations || {}) },
    target_minutes: d.target_minutes ?? 30,
    notes: d.notes || {},
    checks: d.checks || {},
    guest_on: !!d.guest_on,
  }
}

// ── Suggestions built from the pulls ─────────────────────────────────────────

const pulled = (comps) => comps.filter(c => c.pull && c.pull.kind === 'round')

// "Swan Valley won by 19 runs": the result line with the name a host reads out,
// in place of Cricket Australia's full side name ("Swan Valley 1st XI").
function marginText(r) {
  const m = /\bwon\b(.*)$/i.exec(r.result || '')
  const winner = r.winner === 'home' ? r.home : r.winner === 'away' ? r.away : ''
  if (m && winner) return `${winner} won${m[1]}`
  return r.result || `${r.home} v ${r.away}`
}

function buildSuggestions(comps) {
  const ok = pulled(comps)
  const all = (k) => ok.flatMap(c => (c.pull[k] || []).map(x => ({ ...x, comp: c.name })))
  const results = all('results')
  const closest = results
    .filter(r => r.margin && r.margin.closeness !== null && r.margin.closeness !== undefined)
    .sort((a, b) => a.margin.closeness - b.margin.closeness)
    .slice(0, 3)
    .map(r => ({ text: `${r.comp}: ${r.home} ${r.home_score} v ${r.away} ${r.away_score}. ${marginText(r)}`, url: r.url }))
  const upsets = all('upsets').map(u => ({
    text: `${u.comp}: ${u.winner} (${ordinal(u.winner_rank)}) beat ${u.loser} (${ordinal(u.loser_rank)})${/\bby\b.*$/i.exec(u.result || '') ? ` ${/\bby\b.*$/i.exec(u.result)[0]}` : ''}`,
  }))
  const batting = all('batting').sort((a, b) => b.runs - a.runs || (a.balls || 999) - (b.balls || 999))
  const bowling = all('bowling').sort((a, b) => b.wickets - a.wickets || a.runs - b.runs)
  const performers = all('performers').sort((a, b) => b.points - a.points)
  const milestones = all('milestones')
  const biggestWins = results
    .filter(r => r.margin && r.margin.runs)
    .sort((a, b) => b.margin.runs - a.margin.runs)
    .slice(0, 2)
  const story = [
    ...milestones.filter(m => m.kind === 'hat_trick' || m.kind === 'hundred').slice(0, 3).map(m => ({ text: `${m.comp}: ${m.text}` })),
    ...performers.slice(0, 1).map(p => ({ text: `${p.comp}: ${p.name} (${p.team}) ${p.line} against ${p.opp}` })),
    ...biggestWins.map(r => ({ text: `${r.comp}: ${marginText(r)}`, url: r.url })),
  ]
  const clubs = [...new Set(results.flatMap(r => [r.home, r.away]).filter(Boolean))].sort()
  return {
    story: dedupe(story),
    closest,
    upsets,
    highScores: batting.slice(0, 5).map(b => ({ text: `${b.name} (${b.team}) ${b.line} v ${b.opp}, ${b.comp}` })),
    bestBowling: bowling.slice(0, 5).map(b => ({ text: `${b.name} (${b.team}) ${b.line} v ${b.opp}, ${b.comp}` })),
    catches: all('catches').slice(0, 8).map(c => ({
      text: `${c.fielder || 'Fielder'}${c.keeper ? ' (keeper)' : ''}${c.caught_and_bowled ? ' (caught and bowled)' : ''} caught ${c.batter} (${c.batter_runs}) for ${c.team} v ${c.opp}, ${c.comp}`,
      filmed: !!c.clip, url: matchUrl(ok, c.match_id),
    })),
    topCatchers: all('fielders').sort((a, b) => (b.catches + b.stumpings + b.run_outs) - (a.catches + a.stumpings + a.run_outs)).slice(0, 3)
      .map(f => ({ text: `${f.name} (${f.team}) ${f.catches} catches${f.stumpings ? `, ${f.stumpings} stumpings` : ''}${f.run_outs ? `, ${f.run_outs} run outs` : ''}, ${f.comp}` })),
    runOuts: all('run_outs').slice(0, 6).map(r => ({
      text: `${r.fielders.length ? r.fielders.join(' and ') : 'Fielder'} ran out ${r.batter} (${r.batter_runs}) for ${r.team} v ${r.opp}, ${r.comp}`,
      filmed: !!r.clip, url: matchUrl(ok, r.match_id),
    })),
    milestones: milestones.map(m => ({ text: `${m.comp}: ${m.text}` })),
    potr: performers.slice(0, 5).map(p => ({ text: `${p.name} (${p.team}) ${p.line} v ${p.opp}, ${p.comp}` })),
    team: results.filter(r => r.winner).sort((a, b) => (b.margin?.closeness ?? -1) - (a.margin?.closeness ?? -1)).slice(0, 3)
      .map(r => ({ text: `${r.comp}: ${marginText(r)} against ${r.winner === 'home' ? r.away : r.home}`, url: r.url })),
    clubs: clubs.map(c => ({ text: c })),
    matchOfRound: ok.map(c => {
      const n = c.pull.next_round || {}
      const f = (n.fixtures || [])[n.match_of_round]
      return f ? { text: `${c.name}: ${f.home} (${ordinal(f.home_rank)}) v ${f.away} (${ordinal(f.away_rank)}), ${f.label}${f.venue ? ` at ${f.venue}` : ''}`, url: f.url } : null
    }).filter(Boolean),
    ladderWatch: ok.map(c => {
      const top = (c.pull.ladder || []).slice(0, 4)
      return top.length ? { text: `${c.name} top four: ${top.map(t => `${t.rank}. ${t.team} (${t.points ?? 0})`).join(', ')}` } : null
    }).filter(Boolean),
  }
}

function matchUrl(comps, id) {
  for (const c of comps) {
    const r = (c.pull.results || []).find(x => x.match_id === id)
    if (r) return r.url
  }
  return null
}

function dedupe(list) {
  const seen = new Set()
  return list.filter(x => (seen.has(x.text) ? false : (seen.add(x.text), true)))
}

function ordinal(n) {
  if (typeof n !== 'number') return '?'
  const s = ['th', 'st', 'nd', 'rd']
  const v = n % 100
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`
}

// ── The run sheet as text (copy, print) ──────────────────────────────────────

function itemsFor(data) {
  const n = data.notes
  const hosts = data.hosts
  const comps = data.competitions
  const out = [
    ['1. Opening', data.durations.opening, [
      ['Welcome listeners', n.welcome], ['Biggest story of the round', n.story],
      ['Closest match', n.closest], ['Upset result', n.upset],
    ]],
    ['2. Around the Grounds', data.durations.grounds, comps.flatMap(c => [
      [`${c.name} Competition: results`, resultsText(c)],
      [`${c.name}: top batter`, n[`${c.key}_bat`]],
      [`${c.name}: top bowler`, n[`${c.key}_bowl`]],
      [`${c.name}: standout moment`, n[`${c.key}_moment`]],
    ])],
    ['3. Stats Corner', data.durations.stats, [
      ['Highest scores', n.high_scores], ['Best bowling figures', n.best_bowling],
      ['Best catch', n.best_catch], ['Best run out', n.best_run_out],
      ['Milestones and achievements', n.milestones],
    ]],
    ['4. Awards', data.durations.awards, [
      ['Player of the Round', n.potr], ['Team of the Round', n.team],
      ['Volunteer / Club Shoutout', n.volunteer], ['Funny Moment of the Week', n.funny],
    ]],
    ['5. Club Spotlight', data.durations.spotlight, [
      ['Featured club', n.featured_club], ["Women's cricket growth", n.womens],
      ['Club culture', n.culture], ['Upcoming events', n.events],
    ]],
  ]
  if (data.guest_on) {
    out.push(['6. Guest Segment', data.durations.guest, [
      ['Guest name', n.guest_name], ['Question 1', n.guest_q1], ['Question 2', n.guest_q2], ['Question 3', n.guest_q3],
    ]])
  }
  out.push(['7. Looking Ahead', data.durations.ahead, [
    ['Match of the Round', n.match_of_round], ['Ladder Watch', n.ladder_watch],
    ...hosts.map(h => [`${h.name}'s Prediction`, n[`pred_${h.name}`]]),
  ]])
  out.push(['Episode Close', null, [
    ['Social media plugs', n.plugs], ['Call for stories, photos and nominations', n.call_for],
  ]])
  return out
}

function resultsText(c) {
  if (!c.pull || c.pull.kind !== 'round') return ''
  return (c.pull.results || []).map(r => `${r.home} ${r.home_score} v ${r.away} ${r.away_score}. ${marginText(r)}`).join('\n')
}

function runSheetText(ep, data) {
  const lines = [`Episode ${ep.episode_no ?? ''}${ep.round_label ? `: ${ep.round_label}` : ''}`]
  if (ep.recording_date) lines.push(`Recording: ${ep.recording_date}`)
  lines.push(`Target duration: ${data.target_minutes} mins`, '')
  for (const [title, mins, items] of itemsFor(data)) {
    lines.push(`${title}${mins ? ` (${mins} mins)` : ''}`)
    for (const [label, body] of items) {
      lines.push(`  ${label}`)
      const t = (body || '').trim()
      if (t) t.split('\n').forEach(l => lines.push(`    ${l}`))
    }
    lines.push('')
  }
  return lines.join('\n')
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]))
}

function printRunSheet(ep, data) {
  const sections = itemsFor(data).map(([title, mins, items]) => `
    <h2>${escapeHtml(title)}${mins ? ` <span>(${mins} mins)</span>` : ''}</h2>
    ${items.map(([label, body]) => `<div class="item"><div class="label">${escapeHtml(label)}</div>${
      (body || '').trim() ? `<div class="body">${escapeHtml(body.trim()).replace(/\n/g, '<br>')}</div>` : '<div class="blank"></div>'
    }</div>`).join('')}`).join('')
  const w = window.open('', '_blank')
  if (!w) return
  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>Episode ${escapeHtml(ep.episode_no ?? '')} run sheet</title>
  <style>
    body{font-family:Georgia,serif;color:#111;max-width:760px;margin:24px auto;padding:0 16px;line-height:1.4}
    h1{font-size:22px;margin:0 0 4px;color:#1f3a5f} .meta{color:#444;font-size:13px;margin-bottom:12px}
    h2{font-size:17px;color:#1f3a5f;margin:18px 0 6px;border-bottom:1px solid #ccd} h2 span{font-weight:normal;color:#555;font-size:14px}
    .item{margin:6px 0 8px;break-inside:avoid} .label{font-weight:bold;font-size:14px} .body{font-size:14px;margin-left:12px}
    .blank{height:18px;border-bottom:1px dotted #bbb;margin-left:12px}
  </style></head><body>
  <h1>Episode ${escapeHtml(ep.episode_no ?? '')}${ep.round_label ? `: ${escapeHtml(ep.round_label)}` : ''}</h1>
  <div class="meta">${ep.recording_date ? `Recording ${escapeHtml(ep.recording_date)} · ` : ''}Target ${escapeHtml(data.target_minutes)} mins</div>
  ${sections}
  <script>window.onload=function(){window.print()}</script></body></html>`)
  w.document.close()
}

// ── Small pieces (module level: a component declared in render remounts) ──────

function Chips({ items, onPick, empty }) {
  if (!items || !items.length) {
    return empty ? <p className="text-xs text-pb-faint mt-1">{empty}</p> : null
  }
  return (
    <div className="flex flex-wrap gap-1.5 mt-1.5" data-testid="suggestions">
      {items.map((s, i) => (
        <span key={i} className="inline-flex items-center max-w-full min-w-0 rounded border pb-hairline bg-pb-surface2 text-xs">
          <button type="button" onClick={() => onPick(s.text)} className="px-2 py-1 text-left text-pb-text hover:bg-pb-surface min-w-0 break-words" title="Add to notes">
            + {s.text}
          </button>
          {s.filmed && <span className="px-1.5 font-mono text-[9px] text-pb-accent" title="Cricket Australia filmed this dismissal">FILMED</span>}
          {s.url && <a href={s.url} target="_blank" rel="noreferrer" className="px-1.5 py-1 text-pb-faint hover:text-pb-text border-l pb-hairline shrink-0">match ↗</a>}
        </span>
      ))}
    </div>
  )
}

function Item({ label, value, onChange, suggestions, empty, rows = 2, placeholder, testid }) {
  const pick = (text) => onChange(value && value.trim() ? `${value.trim()}\n${text}` : text)
  return (
    <div className="py-2.5 border-b pb-hairline last:border-b-0" data-testid={testid}>
      <div className="text-sm font-medium text-pb-text">{label}</div>
      <Chips items={suggestions} onPick={pick} empty={empty} />
      <textarea
        className={`${INPUT} mt-1.5`}
        rows={rows}
        value={value || ''}
        placeholder={placeholder || 'Notes'}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}

function Segment({ title, hint, mins, onMins, children, right }) {
  return (
    <section className="mb-4 rounded border pb-hairline bg-pb-surface">
      <header className="flex flex-wrap items-center gap-2 px-4 py-3 border-b pb-hairline">
        <h2 className="text-base font-semibold text-pb-text">{title}</h2>
        {hint && <span className="font-mono text-[10px] text-pb-faint">{hint}</span>}
        <span className="ml-auto flex items-center gap-2">
          {right}
          {onMins && (
            <label className="flex items-center gap-1 font-mono text-[10px] text-pb-faint">
              <input type="number" min="0" max="60" value={mins ?? 0} onChange={(e) => onMins(Number(e.target.value) || 0)}
                className="w-12 bg-pb-surface2 border pb-hairline rounded px-1 py-0.5 text-xs text-pb-text text-center" />
              MINS
            </label>
          )}
        </span>
      </header>
      <div className="px-4 py-1">{children}</div>
    </section>
  )
}

function CompResults({ comp }) {
  const p = comp.pull
  if (!p) return <p className="text-xs text-pb-faint py-2">Paste a match link for {comp.name} above and press Pull.</p>
  if (p.kind !== 'round') return <p className="text-xs text-red-500 py-2">{p.message || 'Nothing to show for that link.'}</p>
  return (
    <div className="py-2">
      <div className="font-mono text-[10px] text-pb-faint mb-1">{p.grade} · {p.round} · {p.label}</div>
      <ul className="space-y-1">
        {p.results.map(r => (
          <li key={r.match_id} className="text-sm text-pb-text">
            <span className={r.winner === 'home' ? 'font-semibold' : ''}>{r.home} {r.home_score}</span>
            {' v '}
            <span className={r.winner === 'away' ? 'font-semibold' : ''}>{r.away} {r.away_score}</span>
            <span className="text-pb-dim">. {marginText(r)}</span>{' '}
            <a href={r.url} target="_blank" rel="noreferrer" className="text-xs text-pb-faint hover:text-pb-text">card ↗</a>
          </li>
        ))}
      </ul>
      {(p.not_played || []).length > 0 && (
        <p className="text-xs text-pb-dim mt-1">No result: {p.not_played.map(m => `${m.home} v ${m.away}${m.status ? ` (${m.status})` : ''}`).join('; ')}</p>
      )}
      {(p.skipped || []).length > 0 && (
        <p className="text-xs text-amber-600 mt-1">Cricket Australia sent no scorecard for {p.skipped.join(', ')}. Check those on the website.</p>
      )}
    </div>
  )
}

function Ladder({ comp }) {
  const rows = comp.pull?.ladder || []
  if (!rows.length) return null
  return (
    <div className="min-w-0">
      <div className="font-mono text-[10px] text-pb-faint mb-1">{comp.name.toUpperCase()} LADDER</div>
      <table className="w-full text-xs text-pb-text">
        <tbody>
          {rows.map(r => (
            <tr key={r.team_id || r.team} className="border-b pb-hairline last:border-b-0">
              <td className="py-0.5 pr-1 font-mono text-pb-faint w-5">{r.rank}</td>
              <td className="py-0.5 pr-1 truncate max-w-0 w-full">{r.team}</td>
              <td className="py-0.5 pr-1 font-mono text-pb-dim whitespace-nowrap">{r.won ?? 0}-{r.lost ?? 0}</td>
              <td className="py-0.5 font-mono text-right">{r.points ?? 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function NextRound({ comp }) {
  const n = comp.pull?.next_round
  if (!n || !(n.fixtures || []).length) return null
  return (
    <div className="min-w-0">
      <div className="font-mono text-[10px] text-pb-faint mb-1">{comp.name.toUpperCase()} · {n.round || 'NEXT ROUND'}</div>
      <ul className="text-xs text-pb-text space-y-0.5">
        {n.fixtures.map((f, i) => (
          <li key={f.match_id} className={i === n.match_of_round ? 'font-semibold' : ''}>
            {f.home} ({ordinal(f.home_rank)}) v {f.away} ({ordinal(f.away_rank)})
            {i === n.match_of_round && <span className="ml-1 font-mono text-[9px] text-pb-accent">PICK</span>}
          </li>
        ))}
      </ul>
    </div>
  )
}

// ── The page ─────────────────────────────────────────────────────────────────

export default function AdminPodcastRunSheet() {
  const [episodes, setEpisodes] = useState(null)
  const [ep, setEp] = useState(null) // { id, episode_no, recording_date, round_label, data }
  const [error, setError] = useState('')
  const [saveState, setSaveState] = useState('')
  const [pulling, setPulling] = useState({})
  const [copied, setCopied] = useState(false)
  const saveTimer = useRef(null)
  const pending = useRef(null)

  const loadList = useCallback(() => api.podcastEpisodes()
    .then(d => { setEpisodes(d.episodes || []); return d.episodes || [] })
    .catch(e => { setError(e.message); setEpisodes([]); return [] }), [])

  const open = useCallback(async (id) => {
    setError('')
    try {
      const d = await api.podcastEpisode(id)
      setEp({ ...d, data: withDefaults(d.data) })
    } catch (e) { setError(e.message) }
  }, [])

  useEffect(() => {
    loadList().then(list => { if (list.length) open(list[0].id) })
  }, [loadList, open])

  // Save shortly after the last change; a pending save is sent before switching away.
  const flush = useCallback(async () => {
    if (saveTimer.current) { clearTimeout(saveTimer.current); saveTimer.current = null }
    const job = pending.current
    if (!job) return
    pending.current = null
    setSaveState('Saving…')
    try {
      await api.podcastSaveEpisode(job.id, job.fields)
      setSaveState('Saved')
      setEpisodes(list => (list || []).map(e => (e.id === job.id
        ? { ...e, episode_no: job.fields.episode_no, round_label: job.fields.round_label, recording_date: job.fields.recording_date }
        : e)))
    } catch (e) {
      setSaveState('Not saved')
      setError(e.message || 'Could not save')
    }
  }, [])

  const update = useCallback((fn) => {
    setEp(prev => {
      if (!prev) return prev
      const next = fn(prev)
      pending.current = {
        id: next.id,
        fields: { episode_no: next.episode_no, recording_date: next.recording_date || null, round_label: next.round_label || '', data: next.data },
      }
      if (saveTimer.current) clearTimeout(saveTimer.current)
      saveTimer.current = setTimeout(flush, 900)
      setSaveState('Unsaved changes')
      return next
    })
  }, [flush])

  useEffect(() => () => { flush() }, [flush])

  const setNote = (key) => (value) => update(p => ({ ...p, data: { ...p.data, notes: { ...p.data.notes, [key]: value } } }))
  const setData = (patch) => update(p => ({ ...p, data: { ...p.data, ...patch } }))
  const setComp = (i, patch) => update(p => ({
    ...p, data: { ...p.data, competitions: p.data.competitions.map((c, j) => (j === i ? { ...c, ...patch } : c)) },
  }))

  const newEpisode = async () => {
    await flush()
    setError('')
    try {
      const d = await api.podcastCreateEpisode()
      await loadList()
      setEp({ ...d, data: withDefaults(d.data) })
    } catch (e) { setError(e.message) }
  }

  const switchTo = async (id) => { await flush(); open(id) }

  const archive = async () => {
    if (!ep || !window.confirm(`Archive episode ${ep.episode_no ?? ''}? It leaves this list.`)) return
    await flush()
    try {
      await api.podcastArchiveEpisode(ep.id)
      const list = await loadList()
      if (list.length) open(list[0].id)
      else setEp(null)
    } catch (e) { setError(e.message) }
  }

  const pull = async (i) => {
    const comp = ep.data.competitions[i]
    if (!(comp.link || '').trim()) { setComp(i, { pull: { kind: 'invalid', message: 'Paste a match link first.' } }); return }
    setPulling(s => ({ ...s, [i]: true }))
    try {
      const d = await api.podcastPull(comp.link.trim())
      update(p => {
        const comps = p.data.competitions.map((c, j) => (j === i ? { ...c, pull: d, pulled_at: new Date().toISOString() } : c))
        // The first pull names the round, unless someone already typed one.
        const roundLabel = p.round_label || (d.kind === 'round' ? titleRound(d.round) : '')
        return { ...p, round_label: roundLabel, data: { ...p.data, competitions: comps } }
      })
    } catch (e) {
      setComp(i, { pull: { kind: 'error', message: e.message || 'Could not read that round' } })
    } finally {
      setPulling(s => ({ ...s, [i]: false }))
    }
  }

  const pullAll = async () => {
    for (let i = 0; i < ep.data.competitions.length; i++) {
      if ((ep.data.competitions[i].link || '').trim()) await pull(i)
    }
  }

  const addComp = () => update(p => ({
    ...p, data: { ...p.data, competitions: [...p.data.competitions, { key: `c${Date.now()}`, name: 'New', link: '' }] },
  }))
  const removeComp = (i) => {
    if (!window.confirm(`Remove ${ep.data.competitions[i].name} from this episode?`)) return
    update(p => ({ ...p, data: { ...p.data, competitions: p.data.competitions.filter((_, j) => j !== i) } }))
  }

  const data = ep?.data
  const sugg = useMemo(() => (data ? buildSuggestions(data.competitions) : null), [data])
  const totalMins = data ? Object.entries(data.durations).reduce((s, [k, v]) => s + (k === 'guest' && !data.guest_on ? 0 : (Number(v) || 0)), 0) : 0

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(runSheetText(ep, data))
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { setError('Your browser blocked copying. Use Print instead.') }
  }

  const actions = (
    <div className="flex items-center gap-2">
      {saveState && <span className="font-mono text-[10px] text-pb-faint" data-testid="save-state">{saveState.toUpperCase()}</span>}
      <button type="button" className="btn-primary btn-sm" onClick={newEpisode}>New episode</button>
    </div>
  )

  return (
    <BetterSocialsLayout title="Podcast Run Sheet" actions={actions}>
      <div className="max-w-4xl mx-auto">
        {error && <div className="mb-3 p-3 rounded border border-red-400 text-sm text-red-600" role="alert">{error}</div>}

        {episodes !== null && !ep && (
          <div className="p-6 rounded border pb-hairline bg-pb-surface text-center">
            <p className="text-sm text-pb-text mb-1">No episodes yet.</p>
            <p className="text-xs text-pb-dim mb-3">Start one, paste a match link for each competition, and the round's results, stats and ladder fill in.</p>
            <button type="button" className="btn-primary btn-sm" onClick={newEpisode}>Start episode 1</button>
          </div>
        )}

        {ep && data && (
          <>
            {/* Episode details */}
            <section className="mb-4 rounded border pb-hairline bg-pb-surface p-4">
              <div className="flex flex-wrap items-center gap-2 mb-3">
                <h2 className="text-base font-semibold text-pb-text">Episode Details</h2>
                <span className="ml-auto flex flex-wrap items-center gap-2">
                  {(episodes || []).length > 1 && (
                    <select className="bg-pb-surface2 border pb-hairline rounded px-2 py-1 text-sm text-pb-text" value={ep.id}
                      onChange={(e) => switchTo(e.target.value)} aria-label="Open another episode">
                      {episodes.map(e => <option key={e.id} value={e.id}>Episode {e.episode_no ?? '?'}{e.round_label ? `: ${e.round_label}` : ''}</option>)}
                    </select>
                  )}
                  <button type="button" className="btn-secondary btn-sm" onClick={copy}>{copied ? 'Copied' : 'Copy as text'}</button>
                  <button type="button" className="btn-secondary btn-sm" onClick={async () => { await flush(); printRunSheet(ep, data) }}>Print</button>
                  <button type="button" className="btn-quiet btn-sm" onClick={archive}>Archive</button>
                </span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <label className="min-w-0"><span className={LABEL}>EPISODE #</span>
                  <input className={INPUT} type="number" min="1" value={ep.episode_no ?? ''} data-testid="episode-no"
                    onChange={(e) => update(p => ({ ...p, episode_no: e.target.value === '' ? null : Number(e.target.value) }))} />
                </label>
                <label className="min-w-0"><span className={LABEL}>RECORDING DATE</span>
                  <input className={INPUT} type="date" value={ep.recording_date || ''}
                    onChange={(e) => update(p => ({ ...p, recording_date: e.target.value || null }))} />
                </label>
                <label className="min-w-0"><span className={LABEL}>ROUND</span>
                  <input className={INPUT} value={ep.round_label || ''} placeholder="Round 5"
                    onChange={(e) => update(p => ({ ...p, round_label: e.target.value }))} />
                </label>
                <label className="min-w-0"><span className={LABEL}>TARGET (MINS)</span>
                  <input className={INPUT} type="number" min="1" value={data.target_minutes}
                    onChange={(e) => setData({ target_minutes: Number(e.target.value) || 0 })} />
                </label>
              </div>
              <p className={`mt-2 font-mono text-[10px] ${totalMins > data.target_minutes ? 'text-amber-600' : 'text-pb-faint'}`} data-testid="running-time">
                SEGMENTS ADD UP TO {totalMins} MINS OF {data.target_minutes}
              </p>
            </section>

            {/* Competition links */}
            <section className="mb-4 rounded border pb-hairline bg-pb-surface p-4">
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <h2 className="text-base font-semibold text-pb-text">Competitions</h2>
                <span className="ml-auto flex gap-2">
                  <button type="button" className="btn-quiet btn-sm" onClick={addComp}>Add competition</button>
                  <button type="button" className="btn-primary btn-sm" onClick={pullAll} disabled={Object.values(pulling).some(Boolean)}>Pull all</button>
                </span>
              </div>
              <p className="text-xs text-pb-dim mb-3">
                Paste any one match link from the round for each competition (open the match on play.cricket.com.au and copy the address).
                The whole round in that grade is read from it.
              </p>
              <div className="space-y-2">
                {data.competitions.map((c, i) => (
                  <div key={c.key || i} data-testid={`comp-${i}`}>
                  <div className="flex flex-wrap sm:flex-nowrap items-center gap-2">
                    <input className={`${INPUT} sm:w-28 w-24 shrink-0`} value={c.name} aria-label="Competition name"
                      onChange={(e) => setComp(i, { name: e.target.value })} />
                    <input className={`${INPUT} font-mono flex-1 basis-40 min-w-0`} value={c.link || ''} aria-label={`${c.name} match link`}
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
                          ? <span className="text-pb-dim">{c.pull.grade} · {c.pull.round} · {c.pull.results.length} results{c.pulled_at ? ` · pulled ${new Date(c.pulled_at).toLocaleString('en-AU', { weekday: 'short', hour: 'numeric', minute: '2-digit' })}` : ''}</span>
                          : <span className="text-red-500">{c.pull.message}</span>}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>

            <Segment {...SEGMENTS[0]} mins={data.durations.opening} onMins={(v) => setData({ durations: { ...data.durations, opening: v } })}>
              <Item label="Welcome listeners" value={data.notes.welcome} onChange={setNote('welcome')} />
              <Item label="Biggest story of the round" value={data.notes.story} onChange={setNote('story')} suggestions={sugg.story} testid="item-story" />
              <Item label="Closest match" value={data.notes.closest} onChange={setNote('closest')} suggestions={sugg.closest} testid="item-closest"
                empty={pulled(data.competitions).length ? 'No margins in the pulled results.' : null} />
              <Item label="Upset result" value={data.notes.upset} onChange={setNote('upset')} suggestions={sugg.upsets} testid="item-upset"
                empty={pulled(data.competitions).length ? `No winner sat 3 or more places below the side it beat, on the ladder as it stands now.` : null} />
            </Segment>

            <Segment {...SEGMENTS[1]} mins={data.durations.grounds} onMins={(v) => setData({ durations: { ...data.durations, grounds: v } })}>
              {data.competitions.map(c => {
                const p = c.pull?.kind === 'round' ? c.pull : null
                return (
                  <div key={c.key} className="py-2 border-b pb-hairline last:border-b-0" data-testid={`grounds-${c.key}`}>
                    <div className="text-sm font-semibold text-pb-text">{c.name} Competition</div>
                    <CompResults comp={c} />
                    {p && (
                      <>
                        <Item label="Top batter" value={data.notes[`${c.key}_bat`]} onChange={setNote(`${c.key}_bat`)} rows={1}
                          suggestions={p.batting.slice(0, 3).map(b => ({ text: `${b.name} (${b.team}) ${b.line} v ${b.opp}` }))} />
                        <Item label="Top bowler" value={data.notes[`${c.key}_bowl`]} onChange={setNote(`${c.key}_bowl`)} rows={1}
                          suggestions={p.bowling.slice(0, 3).map(b => ({ text: `${b.name} (${b.team}) ${b.line} v ${b.opp}` }))} />
                        <Item label="Standout moment" value={data.notes[`${c.key}_moment`]} onChange={setNote(`${c.key}_moment`)}
                          suggestions={[
                            ...p.milestones.slice(0, 4).map(m => ({ text: m.text })),
                            ...p.run_outs.filter(r => r.clip).slice(0, 2).map(r => ({ text: `${r.fielders.join(' and ') || 'Fielder'} ran out ${r.batter} (${r.batter_runs})`, filmed: true, url: matchUrl([c], r.match_id) })),
                          ]} />
                      </>
                    )}
                  </div>
                )
              })}
            </Segment>

            <Segment {...SEGMENTS[2]} mins={data.durations.stats} onMins={(v) => setData({ durations: { ...data.durations, stats: v } })}>
              <Item label="Highest scores" value={data.notes.high_scores} onChange={setNote('high_scores')} suggestions={sugg.highScores} rows={3} testid="item-high-scores" />
              <Item label="Best bowling figures" value={data.notes.best_bowling} onChange={setNote('best_bowling')} suggestions={sugg.bestBowling} rows={3} />
              <Item label="Best catch" value={data.notes.best_catch} onChange={setNote('best_catch')} suggestions={[...sugg.topCatchers, ...sugg.catches]}
                empty={pulled(data.competitions).length ? 'No catches in the pulled cards.' : null} />
              <Item label="Best run out" value={data.notes.best_run_out} onChange={setNote('best_run_out')} suggestions={sugg.runOuts}
                empty={pulled(data.competitions).length ? 'No run outs in the pulled cards.' : null} />
              <Item label="Milestones and achievements" value={data.notes.milestones} onChange={setNote('milestones')} suggestions={sugg.milestones} rows={3}
                empty={pulled(data.competitions).length ? 'No fifties, hundreds, five-fors or hat-tricks this round.' : null} />
              {pulled(data.competitions).length > 0 && (
                <p className="text-[11px] text-pb-faint py-2">FILMED marks a dismissal Cricket Australia has a video clip of; open the match to watch it. Milestones here are this round's scores and hauls, not career totals.</p>
              )}
            </Segment>

            <Segment {...SEGMENTS[3]} mins={data.durations.awards} onMins={(v) => setData({ durations: { ...data.durations, awards: v } })}>
              <Item label="Player of the Round" value={data.notes.potr} onChange={setNote('potr')} suggestions={sugg.potr} testid="item-potr" />
              <Item label="Team of the Round" value={data.notes.team} onChange={setNote('team')} suggestions={sugg.team} />
              <Item label="Volunteer / Club Shoutout" value={data.notes.volunteer} onChange={setNote('volunteer')} />
              <Item label="Funny Moment of the Week" value={data.notes.funny} onChange={setNote('funny')} />
              {sugg.potr.length > 0 && <p className="text-[11px] text-pb-faint py-2">Player of the Round suggestions use the same points as Player of the Match: a run is 1, a wicket 20, a catch, stumping or run out 8.</p>}
            </Segment>

            <Segment {...SEGMENTS[4]} mins={data.durations.spotlight} onMins={(v) => setData({ durations: { ...data.durations, spotlight: v } })}>
              <Item label="Featured club" value={data.notes.featured_club} onChange={setNote('featured_club')} suggestions={sugg.clubs} rows={1} />
              <Item label="Women's cricket growth" value={data.notes.womens} onChange={setNote('womens')} />
              <Item label="Club culture" value={data.notes.culture} onChange={setNote('culture')} />
              <Item label="Upcoming events" value={data.notes.events} onChange={setNote('events')} />
            </Segment>

            <Segment {...SEGMENTS[5]} mins={data.durations.guest} onMins={data.guest_on ? (v) => setData({ durations: { ...data.durations, guest: v } }) : null}
              right={(
                <label className="flex items-center gap-1.5 text-xs text-pb-dim">
                  <input type="checkbox" checked={data.guest_on} onChange={(e) => setData({ guest_on: e.target.checked })} /> Guest this week
                </label>
              )}>
              {data.guest_on ? (
                <>
                  <Item label="Guest name" value={data.notes.guest_name} onChange={setNote('guest_name')} rows={1} />
                  <Item label="Question 1" value={data.notes.guest_q1} onChange={setNote('guest_q1')} rows={1} />
                  <Item label="Question 2" value={data.notes.guest_q2} onChange={setNote('guest_q2')} rows={1} />
                  <Item label="Question 3" value={data.notes.guest_q3} onChange={setNote('guest_q3')} rows={1} />
                </>
              ) : <p className="text-xs text-pb-faint py-2">No guest this week. Tick the box to plan one.</p>}
            </Segment>

            <Segment {...SEGMENTS[6]} mins={data.durations.ahead} onMins={(v) => setData({ durations: { ...data.durations, ahead: v } })}>
              <Item label="Match of the Round" value={data.notes.match_of_round} onChange={setNote('match_of_round')} suggestions={sugg.matchOfRound} testid="item-mor" />
              <Item label="Ladder Watch" value={data.notes.ladder_watch} onChange={setNote('ladder_watch')} suggestions={sugg.ladderWatch} rows={3} />
              {pulled(data.competitions).length > 0 && (
                <div className="grid sm:grid-cols-3 gap-4 py-3 border-b pb-hairline">
                  {pulled(data.competitions).map(c => (
                    <div key={c.key} className="min-w-0 space-y-3">
                      <Ladder comp={c} />
                      <NextRound comp={c} />
                    </div>
                  ))}
                </div>
              )}
              {data.hosts.map(h => (
                <Item key={h.name} label={`${h.name}'s Prediction`} value={data.notes[`pred_${h.name}`]} onChange={setNote(`pred_${h.name}`)} />
              ))}
              {pulled(data.competitions).length > 0 && (
                <p className="text-[11px] text-pb-faint py-2">Match of the Round picks the two highest placed sides meeting next round. Ladders are as Cricket Australia shows them now.</p>
              )}
            </Segment>

            <section className="mb-4 rounded border pb-hairline bg-pb-surface">
              <header className="px-4 py-3 border-b pb-hairline"><h2 className="text-base font-semibold text-pb-text">Sunday Night Preparation</h2></header>
              <div className="px-4 py-3 grid sm:grid-cols-2 gap-4">
                {data.hosts.map((h, hi) => (
                  <div key={hi} className="min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <input className={`${INPUT} w-28`} value={h.name} aria-label="Host name"
                        onChange={(e) => setData({ hosts: data.hosts.map((x, j) => (j === hi ? { ...x, name: e.target.value } : x)) })} />
                    </div>
                    <ul className="space-y-1">
                      {(h.prep || '').split(',').map(s => s.trim()).filter(Boolean).map(task => {
                        const k = `${h.name}:${task}`
                        return (
                          <li key={task}>
                            <label className="flex items-center gap-2 text-sm text-pb-text">
                              <input type="checkbox" checked={!!data.checks[k]} onChange={(e) => setData({ checks: { ...data.checks, [k]: e.target.checked } })} />
                              {task}
                            </label>
                          </li>
                        )
                      })}
                    </ul>
                    <input className={`${INPUT} mt-2 text-xs`} value={h.prep || ''} aria-label={`${h.name}'s jobs`}
                      title="Jobs, separated by commas"
                      onChange={(e) => setData({ hosts: data.hosts.map((x, j) => (j === hi ? { ...x, prep: e.target.value } : x)) })} />
                  </div>
                ))}
              </div>
            </section>

            <Segment title="Episode Close">
              <Item label="Social media plugs" value={data.notes.plugs} onChange={setNote('plugs')} />
              <Item label="Call for stories, photos and nominations" value={data.notes.call_for} onChange={setNote('call_for')} />
            </Segment>
          </>
        )}
      </div>
    </BetterSocialsLayout>
  )
}

function titleRound(r) {
  const s = String(r || '').trim()
  return s ? s.charAt(0).toUpperCase() + s.slice(1).toLowerCase() : ''
}
