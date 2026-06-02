import { useState, useEffect } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import IQLayout from '../../../components/admin/IQLayout'
import { api } from '../../../lib/api'
import { Btn, Empty, Search } from '../betterselect/ui'

const num = (v, dash = '—') => (v === null || v === undefined ? dash : v)
const fmt2 = (v) => (v === null || v === undefined || Number.isNaN(Number(v))) ? '—' : Number(v).toFixed(2)
const ord = (n) => (n == null ? '—' : ({ 1: '1st', 2: '2nd', 3: '3rd' }[n] || `${n}th`))

function Card({ title, right, children, accent = false }) {
  return (
    <div className="pb-card p-4 md:p-5" style={accent ? { borderColor: 'color-mix(in srgb, var(--pb-accent) 30%, transparent)' } : undefined}>
      {(title || right) && (
        <div className="flex items-center justify-between gap-3 mb-3">
          <h3 className="font-display font-bold">{title}</h3>
          {right}
        </div>
      )}
      {children}
    </div>
  )
}

// Compose a short pre-game lean from the pieces we already hold.
function synthesise({ report, ladder, team }) {
  const bits = []
  const inn = team?.innings
  if (inn?.bat_first?.win_pct != null && inn?.chasing?.win_pct != null) {
    const bf = inn.bat_first.win_pct, ch = inn.chasing.win_pct
    if (Math.abs(bf - ch) >= 8) bits.push(bf > ch ? `Lean to batting first — we win ${bf}% setting vs ${ch}% chasing.` : `We chase well — ${ch}% vs ${bf}% batting first.`)
  }
  if (inn?.par?.par_score != null) bits.push(`A winning first-innings total is usually around ${inn.par.par_score}.`)
  const db = report?.their_danger_batters?.[0]
  if (db?.name) bits.push(`Watch ${db.name}${db.runs ? ` (${db.runs} runs${db.average ? ` @ ${fmt2(db.average)}` : ''})` : ''} — their main threat.`)
  const dom = report?.matchups?.bowler_dominance?.[0]
  if (dom?.bowler && dom?.batter) bits.push(`Save ${dom.bowler} for ${dom.batter} — he's dismissed him ${dom.dismissals}×.`)
  const ob = report?.our_performers?.batting?.[0]
  if (ob?.name) bits.push(`${ob.name} is our man with the bat against them (${ob.runs} @ ${fmt2(ob.average)}).`)
  if (ladder?.available && ladder.our_row?.rank && ladder.opponent_row?.rank) {
    bits.push(`Ladder: you're ${ord(ladder.our_row.rank)}, they're ${ord(ladder.opponent_row.rank)}.`)
  }
  return bits
}

function LadderRow({ label, row, tone }) {
  if (!row) return null
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <div className="flex items-center gap-2 min-w-0">
        <span className="font-display font-bold text-lg pb-num w-8 text-center" style={tone ? { color: tone } : undefined}>{ord(row.rank)}</span>
        <span className="truncate">{row.team_name} <span className="text-pb-faintest text-[11px]">· {label}</span></span>
      </div>
      <span className="text-pb-faint text-[12px] pb-num whitespace-nowrap">{num(row.played, 0)}P · {num(row.won, 0)}W–{num(row.lost, 0)}L{row.points != null ? ` · ${row.points}pts` : ''}</span>
    </div>
  )
}

export default function MatchPreview() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [opp, setOpp] = useState(null)              // {opponents, upcoming}
  const [team, setTeam] = useState(null)            // team overview (par/record)
  const [sel, setSel] = useState(null)              // {fixtureId, opponent, meta}
  const [report, setReport] = useState(null)
  const [ladder, setLadder] = useState(null)
  const [q, setQ] = useState('')

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

  const upcoming = opp?.upcoming || []
  const oppList = opp?.opponents || []
  const t = q.trim().toLowerCase()
  const oppMatches = (t ? oppList.filter(o => (o.name || '').toLowerCase().includes(t)) : oppList).slice(0, 20)

  // ── Detail ──
  if (sel) {
    const m = sel.meta
    const oppName = m.opponent_name || report?.opponent?.name || 'Opponent'
    const h2h = report?.head_to_head
    const lm = report?.last_meeting
    const lines = synthesise({ report, ladder, team })
    return (
      <IQLayout title="Match preview" actions={<Btn variant="ghost" sm icon="back" onClick={clear}>All fixtures</Btn>}>
        <div className="flex flex-wrap items-center gap-2 mb-1">
          <h2 className="font-display font-bold text-2xl">vs {oppName}</h2>
          {m.home_away && <span className="text-[11px] font-mono uppercase px-1.5 py-0.5 rounded" style={{ background: 'var(--pb-surface2)' }}>{m.home_away}</span>}
        </div>
        <div className="text-pb-faint text-sm mb-4 flex flex-wrap gap-x-4 gap-y-1">
          {m.played_on && <span>{m.played_on}</span>}
          {m.grade_name && <span>{m.grade_name}</span>}
          {m.team_name && <span>{m.team_name}</span>}
          {m.venue && <span>{m.venue}</span>}
        </div>

        {lines.length > 0 && (
          <Card title="The lean" accent>
            <ul className="space-y-1.5 text-sm">
              {lines.map((s, i) => <li key={i} className="flex gap-2"><span style={{ color: 'var(--pb-accent)' }}>›</span><span>{s}</span></li>)}
            </ul>
          </Card>
        )}

        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <Card title="Ladder" right={ladder?.grade_name ? <span className="text-pb-faint text-xs truncate max-w-[160px]">{ladder.grade_name}</span> : null}>
            {ladder === null ? <div className="animate-pulse text-pb-faint text-sm">Loading standings…</div>
              : ladder.available && (ladder.our_row || ladder.opponent_row) ? (
                <div className="divide-y pb-hairline">
                  <LadderRow label="us" row={ladder.our_row} tone="var(--pb-accent)" />
                  <LadderRow label={oppName} row={ladder.opponent_row} tone="var(--pb-red)" />
                </div>
              ) : <Empty>{ladder?.note || 'No ladder for this fixture.'}</Empty>}
          </Card>

          <Card title="Head-to-head" right={h2h?.win_pct != null ? <span className="text-pb-faint text-xs">{h2h.win_pct}% win</span> : null}>
            {report === null ? <div className="animate-pulse text-pb-faint text-sm">Loading…</div>
              : h2h && h2h.meetings > 0 ? (
                <>
                  <div className="flex flex-wrap items-center gap-x-6 gap-y-1">
                    <div><span className="font-display font-bold text-2xl pb-num">{h2h.wins}–{h2h.losses}{h2h.draws ? `–${h2h.draws}` : ''}</span><span className="text-pb-faint text-sm ml-2">from {h2h.meetings}</span></div>
                    <div className="text-sm text-pb-faint">Home {h2h.home?.wins}/{h2h.home?.played} · Away {h2h.away?.wins}/{h2h.away?.played}</div>
                  </div>
                  {h2h.recent_form?.length > 0 && (
                    <div className="flex gap-1 mt-2">
                      {h2h.recent_form.slice(0, 8).map((r, i) => (
                        <span key={i} className="w-5 h-5 rounded text-[10px] font-bold flex items-center justify-center" style={{ background: r === 'W' ? 'color-mix(in srgb, var(--pb-brand) 22%, transparent)' : r === 'L' ? 'color-mix(in srgb, var(--pb-red) 22%, transparent)' : 'var(--pb-surface2)', color: r === 'W' ? 'var(--pb-brand)' : r === 'L' ? 'var(--pb-red)' : 'var(--pb-faint)' }}>{r}</span>
                      ))}
                    </div>
                  )}
                </>
              ) : <Empty>No history vs {oppName} yet.</Empty>}
          </Card>
        </div>

        {lm && (
          <div className="mt-4"><Card title="Last meeting" right={lm.played_at ? <span className="text-pb-faint text-xs">{lm.played_at}</span> : null}>
            <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
              <span className="font-display font-bold text-lg" style={{ color: lm.result === 'WIN' ? 'var(--pb-brand)' : lm.result === 'LOSS' ? 'var(--pb-red)' : 'var(--pb-faint)' }}>{lm.result === 'WIN' ? 'Won' : lm.result === 'LOSS' ? 'Lost' : (lm.result || '—')}</span>
              {(lm.our_runs != null || lm.opp_runs != null) && <span className="pb-num text-pb-faint">{num(lm.our_runs)} vs {num(lm.opp_runs)}</span>}
              {lm.venue && <span className="text-pb-faintest text-[12px]">{lm.venue}</span>}
            </div>
            {(lm.our_top_bat || lm.our_top_bowl) && (
              <div className="text-[13px] text-pb-faint mt-1">{lm.our_top_bat ? `Top bat: ${lm.our_top_bat}. ` : ''}{lm.our_top_bowl ? `Top bowler: ${lm.our_top_bowl}.` : ''}</div>
            )}
          </Card></div>
        )}

        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <Card title="Their danger players">
            {report?.their_danger_batters?.length > 0 ? (
              <div className="space-y-1">
                {report.their_danger_batters.slice(0, 5).map((b, i) => (
                  <div key={i} className="flex items-center justify-between gap-3 text-sm py-0.5">
                    <span className="truncate">{b.name}</span>
                    <span className="pb-num text-pb-faint whitespace-nowrap">{num(b.runs)} runs{b.average != null ? ` @ ${fmt2(b.average)}` : ''}</span>
                  </div>
                ))}
              </div>
            ) : <Empty>No standout batters flagged.</Empty>}
          </Card>
          <Card title="Our edge">
            {report?.our_performers?.batting?.[0] || report?.matchups?.bowler_dominance?.length > 0 ? (
              <div className="space-y-2 text-sm">
                {report?.our_performers?.batting?.[0] && <div className="flex justify-between gap-2"><span className="text-pb-faint">Best with the bat</span><span className="pb-num text-right">{report.our_performers.batting[0].name} · {report.our_performers.batting[0].runs} @ {fmt2(report.our_performers.batting[0].average)}</span></div>}
                {report?.our_performers?.bowling?.[0] && <div className="flex justify-between gap-2"><span className="text-pb-faint">Best with the ball</span><span className="pb-num text-right">{report.our_performers.bowling[0].name}</span></div>}
                {report?.matchups?.bowler_dominance?.slice(0, 3).map((d, i) => (
                  <div key={i} className="flex justify-between gap-2 text-[13px]"><span className="text-pb-faint truncate">{d.bowler} vs {d.batter}</span><span className="pb-num whitespace-nowrap">{d.dismissals}× out</span></div>
                ))}
              </div>
            ) : <Empty>No standout edge in the record.</Empty>}
          </Card>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <Link to={`/admin/betteriq/opposition?${sel.fixtureId ? `fixture=${encodeURIComponent(sel.fixtureId)}` : sel.opponent ? `opponent=${encodeURIComponent(sel.opponent)}` : ''}`} className="px-3 h-[36px] inline-flex items-center rounded-lg text-sm font-medium" style={{ background: 'var(--pb-surface2)' }}>Full opposition scout →</Link>
          {sel.opponent && <Link to={`/admin/betteriq/opposition/cheatsheet?opponent=${encodeURIComponent(sel.opponent)}${sel.fixtureId ? `&fixture=${encodeURIComponent(sel.fixtureId)}` : ''}`} className="px-3 h-[36px] inline-flex items-center rounded-lg text-sm font-medium" style={{ background: 'var(--pb-surface2)' }}>Captain's cheat sheet →</Link>}
        </div>

        {report?.coverage?.note && <div className="text-pb-faintest text-[11px] mt-4">{report.coverage.note}</div>}
      </IQLayout>
    )
  }

  // ── Picker ──
  return (
    <IQLayout title="Match preview">
      <p className="text-pb-faint text-sm mb-4 max-w-2xl">A pre-game one-pager for your next match — the lean, the ladder, your head-to-head, their danger players and where your edge is. Pick an upcoming fixture, or search an opponent.</p>

      {upcoming.length > 0 && (
        <div className="mb-5">
          <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-2">Upcoming fixtures</div>
          <div className="grid gap-2 sm:grid-cols-2">
            {upcoming.map(f => (
              <button key={f.fixture_id} onClick={() => load(f)} className="pb-card px-4 py-3 text-left hover:border-pb-accent/50 transition-colors">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium truncate">vs {f.opponent_name}</span>
                  {f.home_away && <span className="text-pb-faintest text-[10px] font-mono uppercase shrink-0">{f.home_away}</span>}
                </div>
                <div className="text-pb-faint text-[12px] mt-0.5 flex flex-wrap gap-x-3">
                  {f.played_on && <span>{f.played_on}</span>}
                  {f.grade_name && <span className="truncate">{f.grade_name}</span>}
                  {!f.opp_key && <span className="text-pb-faintest">no history yet</span>}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="max-w-xl">
        <div className="text-pb-faint text-[11px] uppercase tracking-wide2 mb-2">{upcoming.length > 0 ? 'Or scout any opponent' : 'Scout an opponent'}</div>
        <Search value={q} onChange={setQ} placeholder="Search an opponent club…" className="w-full" />
        {q && (
          <div className="pb-card mt-1 p-1 max-h-80 overflow-auto">
            {oppMatches.length === 0 ? <div className="px-2.5 py-2 text-pb-faint text-sm">No match.</div>
              : oppMatches.map(o => (
                <button key={o.opp_key} onClick={() => load({ opp_key: o.opp_key, opponent_name: o.name })}
                  className="w-full flex items-center justify-between gap-3 px-2.5 py-1.5 rounded-lg hover:bg-pb-surface2 text-left">
                  <span className="font-medium truncate">{o.name}</span>
                  <span className="text-pb-faintest text-[11px] pb-num">{o.meetings} mtgs</span>
                </button>
              ))}
          </div>
        )}
      </div>

      {upcoming.length === 0 && !q && <div className="pb-card p-5 mt-3"><Empty>No upcoming fixtures with an opponent — search a club above to preview them.</Empty></div>}
    </IQLayout>
  )
}
