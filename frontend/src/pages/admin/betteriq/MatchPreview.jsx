/* BetterIQ — Match preview: a fast pre-game one-pager (instant data only).
   Restyled to the v2 high-fidelity design; wired to the real instant report,
   ladder and team-overview endpoints. Never calls the live dossier. */
import { useState, useEffect, useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import IQLayout from '../../../components/admin/IQLayout'
import { api } from '../../../lib/api'
import { useIQFilter, gradeBase } from './Context'
import {
  Icon, CountUp, ResultPills, SplitBar, Card, Tag, Btn, Search, Empty,
  Initials, PageIntro, Note, a2, LoadingBar, fmtCount, fmtPct, runsPhrase,
} from './ui'

const num = (v, dash = '—') => (v === null || v === undefined ? dash : v)
const ord = (n) => (n == null ? '—' : ({ 1: '1st', 2: '2nd', 3: '3rd' }[n] || `${n}th`))

// One-line standings read for under the ladder (mirrors the reference's context line).
function ladderContext(ladder, oppName) {
  const us = ladder?.our_row, them = ladder?.opponent_row
  if (!us?.rank || !them?.rank) return null
  const who = oppName || 'them'
  if (us.rank < them.rank) {
    const gap = (us.points != null && them.points != null) ? Math.abs(us.points - them.points) : null
    return `You sit ${ord(us.rank)}, ${gap != null ? `${gap} pts ` : ''}ahead of ${who} in ${ord(them.rank)}.`
  }
  if (us.rank > them.rank) {
    const gap = (us.points != null && them.points != null) ? Math.abs(them.points - us.points) : null
    return `${who} are above you — ${ord(them.rank)} to your ${ord(us.rank)}${gap != null ? `, a ${gap} pt swing` : ''}. A win closes the gap.`
  }
  return `Level with ${who} on the ladder — this one's for the table.`
}

/* Clean two-line perf cell: value + unit, then "avg X.XX". */
function PerfStat({ value, unit, avg }) {
  return (
    <div className="text-right shrink-0">
      <div className="iq-num font-semibold text-[15px] leading-none">
        {fmtCount(value)}<span className="text-pb-faint font-normal text-[11px] ml-1">{unit}</span>
      </div>
      <div className="iq-num text-pb-faint text-[11px] mt-1">avg {a2(avg)}</div>
    </div>
  )
}

// Compose a short pre-game lean from the pieces we already hold.
function synthesise({ report, ladder, team }) {
  const bits = []
  const inn = team?.innings
  if (inn?.bat_first?.win_pct != null && inn?.chasing?.win_pct != null) {
    const bf = inn.bat_first.win_pct, ch = inn.chasing.win_pct
    if (Math.abs(bf - ch) >= 8) bits.push(bf > ch ? `Lean to batting first — we win ${fmtPct(bf)} setting vs ${fmtPct(ch)} chasing.` : `We chase well — ${fmtPct(ch)} vs ${fmtPct(bf)} batting first.`)
  }
  if (inn?.par?.par_score != null) bits.push(`A winning first-innings total is usually around ${inn.par.par_score}.`)
  const db = report?.their_danger_batters?.[0]
  if (db?.name) bits.push(`Watch ${db.name}${db.runs ? ` (${runsPhrase(db.runs, db.average)})` : ''} — their main threat.`)
  const dom = report?.matchups?.bowler_dominance?.[0]
  if (dom?.bowler && dom?.batter) bits.push(`Save ${dom.bowler} for ${dom.batter} — he's dismissed him ${dom.dismissals}×.`)
  const ob = report?.our_performers?.batting?.[0]
  if (ob?.name) bits.push(`${ob.name} is our man with the bat against them (${runsPhrase(ob.runs, ob.average)}).`)
  if (ladder?.available && ladder.our_row?.rank && ladder.opponent_row?.rank) {
    bits.push(`Ladder: you're ${ord(ladder.our_row.rank)}, they're ${ord(ladder.opponent_row.rank)}.`)
  }
  return bits
}

// A plain-text pre-game brief for the group chat, built from the instant data
// we already hold (no extra fetch). Light emoji, plain cricket-club voice.
function buildTeamTalk({ report, ladder, team, oppName, meta }) {
  const L = []
  const ordL = (n) => (n == null ? null : ({ 1: '1st', 2: '2nd', 3: '3rd' }[n] || `${n}th`))
  const sub = [meta?.played_on, meta?.home_away, meta?.grade_name].filter(Boolean).join(' · ')
  L.push(`🏏 vs ${oppName}${sub ? `\n${sub}` : ''}`)

  const h2h = report?.head_to_head
  if (h2h?.meetings > 0) {
    L.push(`\n🤝 Record vs them: ${h2h.wins}-${h2h.losses} from ${h2h.meetings}${h2h.win_pct != null ? ` (${Math.round(h2h.win_pct)}% wins)` : ''}`)
  }
  const lm = report?.last_meeting
  if (lm && (lm.result || lm.our_runs != null)) {
    const r = lm.result === 'WIN' ? 'Won' : lm.result === 'LOSS' ? 'Lost' : (lm.result || 'Drew')
    L.push(`Last meeting: ${r}${(lm.our_runs != null || lm.opp_runs != null) ? ` ${lm.our_runs ?? '?'}-${lm.opp_runs ?? '?'}` : ''}${lm.played_at ? ` (${lm.played_at})` : ''}`)
  }
  if (ladder?.available && ladder.our_row?.rank && ladder.opponent_row?.rank) {
    L.push(`📊 Ladder: we're ${ordL(ladder.our_row.rank)}, they're ${ordL(ladder.opponent_row.rank)}.`)
  }

  const danger = (report?.their_danger_batters || []).slice(0, 3)
  if (danger.length) {
    L.push('\n⚠️ Watch out for:')
    danger.forEach(d => {
      const bits = []
      if (d.runs) bits.push(`${d.runs} runs${d.average != null ? ` @ ${d.average}` : ''} vs us`)
      if (d.times_out) bits.push(`out to us ${d.times_out}×`)
      L.push(`• ${d.name}${bits.length ? ` — ${bits.join(', ')}` : ''}`)
    })
  }
  const dom = (report?.matchups?.bowler_dominance || []).slice(0, 2).filter(m => m.bowler && m.batter)
  if (dom.length) {
    L.push('\n🎯 Match-ups in our favour:')
    dom.forEach(m => L.push(`• Save ${m.bowler} for ${m.batter} — ${m.dismissals}× dismissed`))
  }
  const eb = (report?.our_performers?.batting || []).slice(0, 2)
  const ew = (report?.our_performers?.bowling || []).slice(0, 1)
  if (eb.length || ew.length) {
    L.push('\n💪 Our edge against them:')
    eb.forEach(e => L.push(`• ${e.name} — ${e.runs} runs${e.average != null ? ` @ ${e.average}` : ''}`))
    ew.forEach(e => L.push(`• ${e.name} — ${e.wickets} wkts${e.average != null ? ` @ ${e.average}` : ''}`))
  }

  const inn = team?.innings
  const tail = []
  if (inn?.bat_first?.win_pct != null && inn?.chasing?.win_pct != null && Math.abs(inn.bat_first.win_pct - inn.chasing.win_pct) >= 8) {
    const bf = inn.bat_first.win_pct >= inn.chasing.win_pct
    tail.push(`🪙 Win the toss: ${bf ? 'bat first' : 'have a chase'} (we win ${Math.round(Math.max(inn.bat_first.win_pct, inn.chasing.win_pct))}% that way).`)
  }
  if (inn?.par?.par_score != null) tail.push(`📈 Par here is about ${inn.par.par_score} batting first.`)
  if (tail.length) L.push('\n' + tail.join('\n'))

  return L.join('\n').replace(/\n{3,}/g, '\n\n')
}

/* Ladder table — our row + the opponent row, styled like the reference. */
function LadderTable({ ladder, oppName }) {
  const rows = [
    ladder.our_row && { ...ladder.our_row, us: true },
    ladder.opponent_row && { ...ladder.opponent_row, us: false },
  ].filter(Boolean)
  if (!rows.length) return <Empty>{ladder?.note || 'No ladder for this fixture.'}</Empty>
  return (
    <div className="overflow-x-auto iq-scroll -mx-1">
      <table className="w-full text-[13.5px]">
        <thead>
          <tr className="iq-eyebrow text-left" style={{ fontSize: 9.5 }}>
            <th className="py-1.5 px-2 font-medium text-center">#</th>
            <th className="py-1.5 px-2 font-medium">Club</th>
            <th className="py-1.5 px-2 font-medium text-right">P</th>
            <th className="py-1.5 px-2 font-medium text-right">W</th>
            <th className="py-1.5 px-2 font-medium text-right">L</th>
            <th className="py-1.5 px-2 font-medium text-right">Pts</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} style={{ borderTop: '1px solid var(--pb-hairline)', background: r.us ? 'color-mix(in srgb, var(--pb-accent) 8%, transparent)' : 'transparent' }}>
              <td className="py-2.5 px-2 text-center iq-num font-semibold" style={{ color: r.us ? 'var(--pb-accent)' : 'var(--pb-faint)' }}>{ord(r.rank)}</td>
              <td className="py-2.5 px-2 font-semibold">
                <span className="truncate">{r.team_name || (r.us ? 'Us' : oppName)}</span>
                {r.us && <Tag tone="accent" className="ml-1.5">Us</Tag>}
              </td>
              <td className="py-2.5 px-2 text-right iq-num text-pb-faint">{fmtCount(r.played)}</td>
              <td className="py-2.5 px-2 text-right iq-num">{fmtCount(r.won)}</td>
              <td className="py-2.5 px-2 text-right iq-num">{fmtCount(r.lost)}</td>
              <td className="py-2.5 px-2 text-right iq-num font-bold">{fmtCount(r.points)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function MatchPreview() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { ctx } = useIQFilter()
  const gradeFilter = ctx?.team?.id || null         // global Grade filter (base name)
  const [opp, setOpp] = useState(null)              // {opponents, upcoming}
  const [team, setTeam] = useState(null)            // team overview (par/record)
  const [sel, setSel] = useState(null)              // {fixtureId, opponent, meta}
  const [report, setReport] = useState(null)
  const [ladder, setLadder] = useState(null)
  const [q, setQ] = useState('')
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    api.iqListOpponents().then(setOpp).catch(() => setOpp({ opponents: [], upcoming: [] }))
    api.iqTeamOverview().then(setTeam).catch(() => setTeam(null))
  }, [])

  // Restore from URL once the fixtures are loaded.
  useEffect(() => {
    if (!opp || sel) return
    const fid = searchParams.get('fixture'); const ok = searchParams.get('opponent')
    if (fid) { const f = (opp.upcoming || []).find(u => u.fixture_id === fid); if (f) load(f) }
    else if (ok) { const o = (opp.opponents || []).find(x => x.opp_key === ok); if (o) load({ opp_key: o.opp_key, opponent_name: o.name }) }
  }, [opp])  // eslint-disable-line react-hooks/exhaustive-deps

  const load = (f) => {
    const s = { fixtureId: f.fixture_id || null, opponent: f.opp_key || null, meta: f }
    setSel(s); setReport(null); setLadder(null); setQ('')
    setSearchParams(f.fixture_id ? { fixture: f.fixture_id } : (f.opp_key ? { opponent: f.opp_key } : {}), { replace: true })
    const params = { opponent: s.opponent, fixtureId: s.fixtureId }
    api.iqOppositionReport(params).then(setReport).catch(() => setReport({ error: true }))
    api.iqOpponentLadder(params).then(setLadder).catch(() => setLadder({ available: false }))
  }
  const clear = () => { setSel(null); setReport(null); setLadder(null); setSearchParams({}, {}) }

  // Follow the global Grade filter: narrow the upcoming-fixture list to that
  // grade (fixtures carry the raw, sponsor-decorated grade name, so normalise).
  const upcoming = useMemo(() => {
    const all = opp?.upcoming || []
    return gradeFilter ? all.filter(f => gradeBase(f.grade_name) === gradeFilter) : all
  }, [opp, gradeFilter])
  const oppList = opp?.opponents || []
  const t = q.trim().toLowerCase()
  const oppMatches = (t ? oppList.filter(o => (o.name || '').toLowerCase().includes(t)) : oppList).slice(0, 20)

  // Cross-screen navigation targets (carry the current fixture/opponent through).
  const qs = sel ? (sel.fixtureId ? `fixture=${encodeURIComponent(sel.fixtureId)}` : sel.opponent ? `opponent=${encodeURIComponent(sel.opponent)}` : '') : ''
  const goScout = () => navigate(`/admin/betteriq/opposition${qs ? `?${qs}` : ''}`)
  const goCheatSheet = () => {
    if (!sel?.opponent) return
    navigate(`/admin/betteriq/opposition/cheatsheet?opponent=${encodeURIComponent(sel.opponent)}${sel.fixtureId ? `&fixture=${encodeURIComponent(sel.fixtureId)}` : ''}`)
  }
  const goSelection = () => navigate(`/admin/betteriq/selection${qs ? `?${qs}` : ''}`)

  // ── Detail ──
  if (sel) {
    const m = sel.meta
    const oppName = m.opponent_name || report?.opponent?.name || 'Opponent'
    const h2h = report?.head_to_head
    const lm = report?.last_meeting
    const lines = synthesise({ report, ladder, team })
    const par = team?.innings?.par
    const danger = (report?.their_danger_batters || []).slice(0, 3)
    const edgeBat = (report?.our_performers?.batting || []).slice(0, 2)
    const edgeBowl = (report?.our_performers?.bowling || []).slice(0, 1)
    const lmTone = lm?.result === 'WIN' ? 'var(--pb-brand)' : lm?.result === 'LOSS' ? 'var(--pb-red)' : 'var(--pb-amber)'
    const lmLabel = lm?.result === 'WIN' ? 'Won' : lm?.result === 'LOSS' ? 'Lost' : (lm?.result || '—')
    const teamTalk = report && !report.error ? buildTeamTalk({ report, ladder, team, oppName, meta: m }) : ''
    const copyTeamTalk = () => {
      if (!teamTalk) return
      navigator.clipboard?.writeText(teamTalk).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000) }).catch(() => {})
    }

    return (
      <IQLayout title="Match preview" actions={<Btn variant="ghost" sm icon="back" onClick={clear}>All fixtures</Btn>}>
        <div className="iq-fade">
          <PageIntro>A 60-second read before the game — the essentials, fast. For the full dossier (danger men, match-ups, game plan) open the scout.</PageIntro>

          {/* Fixture bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
            <div className="flex items-center gap-4 flex-wrap">
              <span className="iq-headline" style={{ fontSize: 'clamp(24px,3vw,34px)' }}>vs {oppName}</span>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-pb-dim">
                {m.played_on && <span className="inline-flex items-center gap-1.5"><Icon name="fixtures" size={14} className="text-pb-faint" />{m.played_on}</span>}
                {(m.home_away || m.venue) && <span className="inline-flex items-center gap-1.5"><Icon name="target" size={14} className="text-pb-faint" />{[m.home_away, m.venue].filter(Boolean).join(' · ')}</span>}
                {(m.grade_name || m.team_name) && <span className="iq-mono text-pb-faint">{[m.team_name, m.grade_name].filter(Boolean).join(' · ')}</span>}
              </div>
            </div>
            <div className="flex items-center gap-2.5">
              <Btn variant="ghost" sm icon={copied ? 'check' : 'share'} onClick={copyTeamTalk} disabled={!teamTalk}>{copied ? 'Copied' : 'Copy team talk'}</Btn>
              <Btn variant="ghost" sm icon="print" onClick={goCheatSheet} disabled={!sel.opponent}>Cheat sheet</Btn>
              <Btn variant="primary" sm icon="search" onClick={goScout}>Full scout</Btn>
            </div>
          </div>

          <div className="space-y-5">
            {/* The lean */}
            {lines.length > 0 && (
              <Card accent eyebrow="The lean" title="What matters on the day" right={<Tag tone="accent">Synthesised</Tag>}>
                <ul className="space-y-3">
                  {lines.map((l, i) => (
                    <li key={i} className="flex gap-3 text-[14.5px] leading-snug">
                      <span className="iq-num shrink-0 font-bold" style={{ color: 'var(--pb-accent)', width: 18 }}>{i + 1}</span>
                      <span>{l}</span>
                    </li>
                  ))}
                </ul>
              </Card>
            )}

            {/* Team talk — copy/paste straight into the group chat */}
            {teamTalk && (
              <Card eyebrow="for the group chat" title="Team talk"
                right={<Btn variant="soft" sm icon={copied ? 'check' : 'share'} onClick={copyTeamTalk}>{copied ? 'Copied' : 'Copy'}</Btn>}>
                <pre className="whitespace-pre-wrap text-[13px] leading-relaxed" style={{ fontFamily: 'inherit', margin: 0 }}>{teamTalk}</pre>
                <Note>Built from the record and form we already hold — paste it into the team chat, or open the full scout for the detail.</Note>
              </Card>
            )}

            {/* Ladder + H2H */}
            <div className="grid gap-5 lg:grid-cols-2 items-start">
              <Card eyebrow="grade ladder" title="Where we sit" right={ladder?.grade_name ? <span className="text-pb-faint text-[11px] truncate max-w-[150px]">{ladder.grade_name}</span> : null}>
                {ladder === null ? <LoadingBar label="Loading standings…" expectedMs={6000} />
                  : ladder.available ? (
                    <>
                      <LadderTable ladder={ladder} oppName={oppName} />
                      {ladderContext(ladder, oppName) && (
                        <div className="text-pb-dim text-[12.5px] mt-3">{ladderContext(ladder, oppName)}</div>
                      )}
                    </>
                  ) : <Empty>{ladder?.note || 'No ladder for this fixture.'}</Empty>}
                {ladder?.available && (ladder.our_row || ladder.opponent_row) && (
                  <Note>Current standings for this grade — historical splits aren't kept.</Note>
                )}
              </Card>

              <Card eyebrow={h2h?.meetings ? `${h2h.meetings} meetings` : 'head-to-head'} title="Head-to-head" right={h2h?.win_pct != null ? <Tag tone="faint">{fmtPct(h2h.win_pct)} win</Tag> : null}>
                {report === null ? <LoadingBar label="Loading…" expectedMs={4500} />
                  : h2h && h2h.meetings > 0 ? (
                    <>
                      <div className="flex items-end gap-6">
                        <div>
                          <div className="iq-headline iq-num" style={{ fontSize: 40, color: 'var(--pb-brand)' }}><CountUp value={h2h.wins} /></div>
                          <div className="iq-eyebrow mt-1.5">Won</div>
                        </div>
                        <div>
                          <div className="iq-headline iq-num" style={{ fontSize: 40, color: 'var(--pb-red)' }}><CountUp value={h2h.losses} /></div>
                          <div className="iq-eyebrow mt-1.5">Lost</div>
                        </div>
                        {h2h.recent_form?.length > 0 && (
                          <div className="ml-auto flex flex-col items-end gap-1.5">
                            <div className="iq-eyebrow">Recent</div>
                            <ResultPills form={h2h.recent_form.slice(0, 6)} size={20} />
                          </div>
                        )}
                      </div>
                      <div className="mt-4">
                        <SplitBar h={10} segments={[
                          { label: 'W', value: h2h.wins, color: 'var(--pb-brand)' },
                          { label: 'L', value: h2h.losses, color: 'var(--pb-red)' },
                          { label: 'D', value: (h2h.draws || 0) + (h2h.ties || 0), color: 'var(--pb-amber)' },
                        ]} />
                      </div>
                      <div className="mt-4 text-[12.5px] text-pb-dim">
                        Home <span className="iq-num font-semibold text-pb-text">{num(h2h.home?.wins, 0)}/{num(h2h.home?.played, 0)}</span>
                        <span className="mx-2 text-pb-faintest">·</span>
                        Away <span className="iq-num font-semibold text-pb-text">{num(h2h.away?.wins, 0)}/{num(h2h.away?.played, 0)}</span>
                      </div>
                      {lm && (lm.result || lm.our_runs != null) && (
                        <div className="mt-4 pt-4 text-[13px]" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
                          <span className="text-pb-faint">Last meeting:</span>{' '}
                          <span className="font-semibold" style={{ color: lmTone }}>{lmLabel}</span>
                          {(lm.our_runs != null || lm.opp_runs != null) && <span className="iq-num text-pb-dim"> · {num(lm.our_runs)} vs {num(lm.opp_runs)}</span>}
                          {lm.played_at && <span className="iq-num text-pb-faint"> · {lm.played_at}</span>}
                        </div>
                      )}
                    </>
                  ) : <Empty>No history vs {oppName} yet.</Empty>}
              </Card>
            </div>

            {/* Danger + edge */}
            <div className="grid gap-5 lg:grid-cols-2 items-start">
              <Card eyebrow="watch them" title="Their danger players" right={<Btn variant="ghost" sm onClick={goScout}>Full scout</Btn>}>
                {report === null ? <LoadingBar label="Loading…" expectedMs={4500} />
                  : danger.length > 0 ? (
                    <div className="space-y-2.5">
                      {danger.map((d, i) => (
                        <div key={d.player_id || i} className="flex items-center justify-between gap-3 py-1">
                          <div className="flex items-center gap-3 min-w-0">
                            <Initials name={d.name} size={32} />
                            <div className="min-w-0">
                              <div className="font-semibold truncate">{d.name}</div>
                              {d.times_out ? <div className="iq-mono text-pb-faintest text-[10.5px]">out to us {d.times_out}×{d.top_score != null ? ` · best ${d.top_score}` : ''}</div> : null}
                            </div>
                          </div>
                          <PerfStat value={d.runs} unit="runs" avg={d.average} />
                        </div>
                      ))}
                    </div>
                  ) : <Empty>No standout batters flagged.</Empty>}
              </Card>

              <Card eyebrow="our edge" title="Players who own this match-up">
                {report === null ? <LoadingBar label="Loading…" expectedMs={4500} />
                  : (edgeBat.length > 0 || edgeBowl.length > 0) ? (
                    <div className="space-y-2.5">
                      {edgeBat.map((e, i) => (
                        <div key={e.player_id || `b${i}`} className="flex items-center justify-between gap-3 py-1">
                          <div className="flex items-center gap-3 min-w-0">
                            <Initials name={e.name} size={32} tone="accent" />
                            <span className="font-semibold truncate">{e.name}</span>
                          </div>
                          <PerfStat value={e.runs} unit="runs" avg={e.average} />
                        </div>
                      ))}
                      {edgeBowl.map((e, i) => (
                        <div key={e.player_id || `w${i}`} className="flex items-center justify-between gap-3 py-1">
                          <div className="flex items-center gap-3 min-w-0">
                            <Initials name={e.name} size={32} tone="accent" />
                            <span className="font-semibold truncate">{e.name}</span>
                          </div>
                          <PerfStat value={e.wickets} unit="wickets" avg={e.average} />
                        </div>
                      ))}
                    </div>
                  ) : <Empty>No standout edge in the record.</Empty>}
              </Card>
            </div>

            {/* Par callout */}
            {par?.par_score != null && (
              <Card eyebrow="set the target" title="Par at this level">
                <div className="flex items-center gap-5 flex-wrap">
                  <div className="iq-headline iq-num" style={{ fontSize: 'clamp(40px,5vw,60px)', color: 'var(--pb-accent)' }}><CountUp value={par.par_score} /></div>
                  <div className="text-pb-dim text-[13.5px] max-w-sm leading-relaxed">
                    Median winning first-innings score across our grounds — post that batting first and you're in the box seat.
                    {par.lowest_defended != null && <> The lowest total we've defended is <span className="iq-num font-semibold text-pb-text">{fmtCount(par.lowest_defended)}</span>.</>}
                  </div>
                </div>
              </Card>
            )}

            {/* Cross-links */}
            <div className="flex flex-wrap gap-2.5">
              <Btn variant="soft" icon="search" onClick={goScout}>Full opposition scout</Btn>
              <Btn variant="soft" icon="selection" onClick={goSelection}>Selection analysis</Btn>
              {sel.opponent && <Btn variant="soft" icon="print" onClick={goCheatSheet}>Captain's cheat sheet</Btn>}
            </div>

            {report?.coverage?.note && <Note>{report.coverage.note}</Note>}
          </div>
        </div>
      </IQLayout>
    )
  }

  // ── Picker ──
  return (
    <IQLayout title="Match preview">
      <div className="iq-fade">
        <PageIntro>A pre-game one-pager for your next match — the lean, the ladder, your head-to-head, their danger players and where your edge is. Pick an upcoming fixture, or search an opponent.</PageIntro>

        {opp === null ? (
          <Card><LoadingBar label="Loading fixtures…" expectedMs={4500} /></Card>
        ) : (
          <div className="space-y-6">
            {upcoming.length > 0 && (
              <div>
                <div className="iq-eyebrow mb-3">Upcoming fixtures{gradeFilter ? ` · ${gradeFilter}` : ''}</div>
                <div className="grid gap-3 sm:grid-cols-2">
                  {upcoming.map(f => (
                    <button key={f.fixture_id} onClick={() => load(f)} className="iq-card text-left transition hover:brightness-110">
                      <div className="p-4">
                        <div className="flex items-center justify-between gap-2">
                          <span className="iq-display font-semibold truncate">vs {f.opponent_name}</span>
                          {f.home_away && <Tag tone="faint">{f.home_away}</Tag>}
                        </div>
                        <div className="text-pb-faint text-[12px] mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5">
                          {f.played_on && <span className="inline-flex items-center gap-1"><Icon name="fixtures" size={12} />{f.played_on}</span>}
                          {f.grade_name && <span className="truncate iq-mono">{f.grade_name}</span>}
                          {!f.opp_key && <span className="text-pb-faintest">no history yet</span>}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="max-w-xl">
              <div className="iq-eyebrow mb-3">{upcoming.length > 0 ? 'Or scout any opponent' : 'Scout an opponent'}</div>
              <Search value={q} onChange={setQ} placeholder="Search an opponent club…" className="w-full" />
              {q && (
                <div className="iq-card mt-2 p-1.5 max-h-80 overflow-auto iq-scroll">
                  {oppMatches.length === 0 ? <div className="px-2.5 py-2 text-pb-faint text-sm">No match.</div>
                    : oppMatches.map(o => (
                      <button key={o.opp_key} onClick={() => load({ opp_key: o.opp_key, opponent_name: o.name })}
                        className="w-full flex items-center justify-between gap-3 px-3 py-2 rounded-lg text-left transition hover:bg-pb-surface2">
                        <span className="iq-display font-medium truncate">{o.name}</span>
                        <span className="iq-num text-pb-faint text-[11px]">{fmtCount(o.meetings)} mtgs</span>
                      </button>
                    ))}
                </div>
              )}
            </div>

            {upcoming.length === 0 && !q && (
              <Card><Empty>{gradeFilter
                ? `No upcoming fixtures in ${gradeFilter} — clear the grade filter, or search a club above.`
                : 'No upcoming fixtures with an opponent — search a club above to preview them.'}</Empty></Card>
            )}
          </div>
        )}
      </div>
    </IQLayout>
  )
}
