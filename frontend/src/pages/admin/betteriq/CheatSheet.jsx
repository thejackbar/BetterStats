import { useState, useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import './iq-theme.css'
import { Icon, CountUp, ResultPills, SplitBar, Tag, Btn, Search, Empty, PageIntro, a2, surname, LoadingBar, runsPhrase, wktsPhrase } from './ui'
import { api } from '../../../lib/api'

/* BetterIQ — Captain's Cheat Sheet (analytics brief §16.6).
 *
 * A self-contained, print-ready, LANDSCAPE one-pager a captain takes to the
 * toss. Rendered in a FIXED LIGHT palette (independent of the app theme) so
 * Print / Save-PDF is always clean on paper — the outer `.iq-root` is forced to
 * `data-theme="light"`, so every pb-* token resolves to the light palette.
 *
 * Print isolation lives in iq-theme.css (@media print): everything except
 * `.iq-print-area` is hidden, the `.iq-cs-overlay` flattens to white, and the
 * page is set to landscape. The Print button (`.iq-no-print`) calls
 * window.print().
 *
 * Standalone route (`/admin/betteriq/opposition/cheatsheet`) — NOT wrapped in
 * IQLayout. Reads the instant opposition report + polls the live dossier we
 * already build, keyed off the opponent / fixture / team URL params. */

const POLL_MS = 2500
const MAX_POLLS = 12

/* — small print-friendly atoms (token-classed so light/dark both resolve) — */

function Eyebrow({ children, className = 'text-pb-faint', style }) {
  return (
    <div className={`iq-mono uppercase font-semibold whitespace-nowrap ${className}`}
      style={{ fontSize: 8.5, letterSpacing: '0.16em', ...style }}>{children}</div>
  )
}

function StatCell({ label, value, color, count = false, decimals = 0, suffix = '' }) {
  return (
    <div>
      <Eyebrow>{label}</Eyebrow>
      <div className="iq-display iq-num leading-none" style={{ fontWeight: 800, fontSize: 20, marginTop: 2, whiteSpace: 'nowrap', color: color || 'var(--pb-text)' }}>
        {count && typeof value === 'number'
          ? <CountUp value={value} decimals={decimals} suffix={suffix} />
          : value}
      </div>
    </div>
  )
}

function Column({ title, accent, children }) {
  return (
    <div className="min-w-0" style={{ flex: 1 }}>
      <div className="iq-display font-bold" style={{ fontSize: 12.5, color: accent, paddingBottom: 6, marginBottom: 8, borderBottom: `2px solid ${accent}` }}>
        {title}
      </div>
      <div className="flex flex-col" style={{ gap: 9 }}>{children}</div>
    </div>
  )
}

function PlayerRow({ name, line, note }) {
  return (
    <div className="min-w-0">
      <div className="flex items-baseline justify-between" style={{ gap: 10 }}>
        {/* Name truncates rather than forcing the row wider than its column —
            nowrap with no overflow handling let a long name blow out a
            squashed mobile column; the stat line is always short, so it
            keeps nowrap and never shrinks. */}
        <span className="iq-display font-bold text-pb-text truncate" style={{ fontSize: 13 }}>{name}</span>
        <span className="iq-mono text-pb-dim shrink-0" style={{ fontSize: 10.5, whiteSpace: 'nowrap' }}>{line}</span>
      </div>
      {note && <div className="text-pb-dim" style={{ fontSize: 10.5, lineHeight: 1.35, marginTop: 2 }}>{note}</div>}
    </div>
  )
}

/* Picker — shown when the sheet is opened cold from the nav (no opponent or
   fixture in the URL yet), rather than the button-driven deep links from
   Match preview / Opposition scout. Deliberately lightweight (this page has
   no IQLayout chrome to lean on): upcoming fixtures first, a club search as
   the fallback, same data source (`list_opponents`) the other pickers use. */
function CheatSheetPicker({ onPick }) {
  const [opp, setOpp] = useState(null)
  const [q, setQ] = useState('')
  useEffect(() => { api.iqListOpponents().then(setOpp).catch(() => setOpp({ opponents: [], upcoming: [] })) }, [])
  const upcoming = opp?.upcoming || []
  const oppList = opp?.opponents || []
  const ql = q.trim().toLowerCase()
  const matches = (ql ? oppList.filter(o => (o.name || '').toLowerCase().includes(ql)) : oppList).slice(0, 20)

  return (
    <div className="iq-print-area iq-rise" style={{ maxWidth: 720, margin: '0 auto', background: 'var(--pb-surface)', color: 'var(--pb-text)', borderRadius: 14, padding: '26px', boxShadow: '0 30px 80px -30px rgba(0,0,0,0.7)' }}>
      <Eyebrow className="text-pb-accent">Captain&rsquo;s cheat sheet</Eyebrow>
      <div className="iq-display font-bold mt-1" style={{ fontSize: 'clamp(20px, 5vw, 26px)' }}>Pick a match</div>
      <PageIntro>One printable page for the toss. Choose an upcoming fixture, or search an opponent you've scouted before.</PageIntro>

      {opp === null ? <LoadingBar label="Loading fixtures…" expectedMs={3500} /> : (
        <div className="space-y-6">
          {upcoming.length > 0 && (
            <div>
              <div className="iq-eyebrow mb-2.5">Upcoming fixtures</div>
              <div className="grid gap-2.5 sm:grid-cols-2">
                {upcoming.map(f => (
                  <button key={f.fixture_id} onClick={() => onPick({ fixtureId: f.fixture_id, opponent: f.opp_key })}
                    className="text-left transition hover:brightness-95" style={{ background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline)', borderRadius: 10, padding: '10px 12px' }}>
                    <div className="font-semibold truncate">vs {f.opponent_name}</div>
                    <div className="text-pb-faint text-[12px] mt-0.5 flex flex-wrap gap-x-2">
                      {f.played_on && <span>{f.played_on}</span>}
                      {f.grade_name && <span className="iq-mono truncate">{f.grade_name}</span>}
                      {!f.opp_key && <span className="text-pb-faintest">no history yet</span>}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
          <div>
            <div className="iq-eyebrow mb-2.5">{upcoming.length > 0 ? 'Or search an opponent' : 'Search an opponent'}</div>
            <Search value={q} onChange={setQ} placeholder="Search an opponent club…" className="w-full" />
            {q && (
              <div className="mt-2 max-h-72 overflow-auto iq-scroll" style={{ border: '1px solid var(--pb-hairline)', borderRadius: 10, padding: 6 }}>
                {matches.length === 0 ? <div className="px-2.5 py-2 text-pb-faint text-sm">No match.</div>
                  : matches.map(o => (
                    <button key={o.opp_key} onClick={() => onPick({ opponent: o.opp_key })}
                      className="w-full flex items-center justify-between gap-3 px-3 py-2 rounded-lg text-left transition hover:bg-pb-surface2">
                      <span className="font-medium truncate">{o.name}</span>
                      <span className="iq-mono text-pb-faint text-[11px]">{o.meetings ?? 0} mtgs</span>
                    </button>
                  ))}
              </div>
            )}
          </div>
          {upcoming.length === 0 && !q && <Empty>Search a club above to build a cheat sheet for them.</Empty>}
        </div>
      )}
    </div>
  )
}

export default function CheatSheet() {
  const navigate = useNavigate()
  const [params, setSearchParams] = useSearchParams()
  const opponent = params.get('opponent') || undefined
  const fixtureId = params.get('fixture') || undefined
  const team = params.get('team') || undefined
  const grade = params.get('grade') || undefined
  const hasSelection = !!(opponent || fixtureId)

  const [report, setReport] = useState(null)
  const [dossier, setDossier] = useState(null)
  const [club, setClub] = useState(null)
  const pollRef = useRef(null)

  // The club's own name. This sheet used to hardcode one club's name on every
  // club's printout.
  useEffect(() => { api.adminGetSettings().then(setClub).catch(() => setClub(null)) }, [])

  useEffect(() => {
    if (!hasSelection) return
    api.iqOppositionReport({ opponent, fixtureId, grade }).then(setReport).catch(() => setReport({ error: true }))
    let tries = 0
    const poll = () => {
      api.iqOppositionDossier({ opponent, fixtureId, team, grade }).then(d => {
        setDossier(d)
        if (d?.status === 'building' && tries++ < MAX_POLLS) pollRef.current = setTimeout(poll, POLL_MS)
      }).catch(() => setDossier({ status: 'error' }))
    }
    poll()
    return () => { if (pollRef.current) clearTimeout(pollRef.current) }
  }, [hasSelection, opponent, fixtureId, team, grade])

  const clubName = club?.short_name || club?.name || 'Us'
  const oppName = dossier?.opponent?.name || report?.opponent?.name || 'Opponent'
  const building = dossier?.status === 'building' || (!dossier && !report)
  const ready = dossier && !['building', 'error', 'unavailable'].includes(dossier.status)

  const h = report?.head_to_head
  const lm = report?.last_meeting
  const gp = ready ? dossier.game_plan : null
  const dangerBat = (ready && dossier.danger_batters) || []
  const dangerBowl = (ready && dossier.danger_bowlers) || []
  const ourBat = report?.our_performers?.batting || []
  const ourBowl = report?.our_performers?.bowling || []
  const dominance = report?.matchups?.bowler_dominance || []

  // "Save bowler X for batter Y" — strongest stored match-up for a danger batter.
  // Full-name match first; a bare-surname fallback only when it's unambiguous on
  // BOTH sides (one dominance row with that surname, and no other danger batter
  // sharing it) — two players sharing a surname used to print a confidently
  // wrong instruction on the sheet the captain carries to the toss.
  const norm = (n) => String(n || '').toLowerCase().replace(/[^a-z ]/g, '').split(/\s+/).filter(Boolean).sort().join(' ')
  const dismissPlan = (name) => {
    let rows = dominance.filter(m => norm(m.batter) === norm(name))
    if (!rows.length) {
      const last = surname(name).split(' ').pop().toLowerCase()
      const surnameRows = dominance.filter(m => surname(m.batter).split(' ').pop().toLowerCase() === last)
      const sharedSurname = dangerBat.filter(b => surname(b.name).split(' ').pop().toLowerCase() === last).length > 1
      if (surnameRows.length === 1 && !sharedSurname) rows = surnameRows
    }
    if (!rows.length) return null
    const best = [...rows].sort((a, b) => b.dismissals - a.dismissals)[0]
    return `${surname(best.bowler)} has him ${best.dismissals}×. Save him for this match-up`
  }

  const wins = h?.wins ?? 0
  const losses = h?.losses ?? 0
  const draws = (h?.draws ?? 0) + (h?.ties ?? 0)
  const h2hLine = h ? `${wins}–${losses}–${draws}` : '—'
  const lmResult = lm?.result ? lm.result.toUpperCase() : null
  const lmColor = lmResult === 'WIN' ? 'var(--pb-brand)' : lmResult === 'LOSS' ? 'var(--pb-red)' : 'var(--pb-amber)'

  const pick = (sel) => {
    const sp = {}
    if (sel.fixtureId) sp.fixture = sel.fixtureId
    else if (sel.opponent) sp.opponent = sel.opponent
    setSearchParams(sp, { replace: true })
  }

  return (
    <div className="iq-root iq-cs-overlay" data-theme="light" data-card="hairline"
      style={{ position: 'fixed', inset: 0, zIndex: 80, background: 'rgba(4,5,10,0.72)', backdropFilter: 'blur(6px)', overflow: 'auto', padding: '28px 18px' }}>

      {/* toolbar — screen only */}
      <div className="iq-no-print flex flex-wrap items-center justify-between" style={{ maxWidth: 1040, margin: '0 auto 14px', gap: 12 }}>
        <div className="text-white">
          <div className="iq-display font-bold" style={{ fontSize: 16 }}>Match cheat sheet</div>
          <div style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.6)' }}>One page for the toss. Prints clean on paper.</div>
        </div>
        <div className="flex flex-wrap" style={{ gap: 10 }}>
          {hasSelection && (
            <Btn variant="ghost" icon="back" onClick={() => setSearchParams({}, { replace: true })}>All fixtures</Btn>
          )}
          <Btn variant="ghost" onClick={() => navigate('/admin/betteriq')}>Close</Btn>
          {hasSelection && <Btn variant="primary" icon="print" onClick={() => window.print()}>Print / Save PDF</Btn>}
        </div>
      </div>

      {!hasSelection && <CheatSheetPicker onPick={pick} />}

      {/* the printable sheet */}
      {hasSelection && (
      <div className="iq-print-area iq-rise"
        style={{ maxWidth: 1040, margin: '0 auto', background: 'var(--pb-surface)', color: 'var(--pb-text)', borderRadius: 14, overflow: 'hidden', boxShadow: '0 30px 80px -30px rgba(0,0,0,0.7)' }}>
        <div style={{ padding: '22px 26px' }}>

          {/* header — stacks on a narrow screen; print is always landscape so
              @media print pins it back to a row (iq-theme.css). */}
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between border-b border-pb-hairline iq-cs-header" style={{ gap: 12, paddingBottom: 14 }}>
            <div className="min-w-0">
              <Eyebrow className="text-pb-accent">Captain&rsquo;s cheat sheet</Eyebrow>
              <div className="iq-display" style={{ fontWeight: 800, fontSize: 'clamp(20px, 6vw, 28px)', letterSpacing: '-0.01em', marginTop: 4, lineHeight: 1.15 }}>
                {clubName} <span className="text-pb-faint" style={{ fontWeight: 600 }}>vs</span> {oppName}
              </div>
            </div>
            <div className="sm:text-right shrink-0">
              {team && <div className="text-pb-dim" style={{ fontSize: 12 }}>{dossier?.selected_team_name || team}</div>}
              {lm?.grade && <div className="iq-mono text-pb-faint" style={{ fontSize: 11, marginTop: 3 }}>{lm.grade}</div>}
              <div className="iq-display font-bold" style={{ fontSize: 13, marginTop: 6 }}>Better<span className="text-pb-accent">IQ</span></div>
              <div className="text-pb-faint" style={{ fontSize: 10.5, marginTop: 1 }}>{new Date().toLocaleDateString()}</div>
            </div>
          </div>

          {/* H2H strip */}
          <div className="flex flex-wrap items-end border-b border-pb-hairline" style={{ gap: 26, padding: '14px 0' }}>
            <StatCell label="Head to head" value={h2hLine} />
            <StatCell label="Win rate" value={h?.win_pct != null ? h.win_pct : '—'} color="var(--pb-accent)" count decimals={0} suffix="%" />
            {h && (wins + losses + draws) > 0 && (
              <div style={{ minWidth: 150, flex: 1, maxWidth: 230 }}>
                <Eyebrow>Balance</Eyebrow>
                <div style={{ marginTop: 7 }}>
                  <SplitBar h={10} segments={[
                    { label: 'W', value: wins, color: 'var(--pb-brand)' },
                    { label: 'L', value: losses, color: 'var(--pb-red)' },
                    { label: 'D', value: draws, color: 'var(--pb-amber)' },
                  ]} />
                </div>
              </div>
            )}
            <div>
              <Eyebrow>Recent (newest &rarr;)</Eyebrow>
              <div style={{ marginTop: 4 }}>
                {h?.recent_form?.length
                  ? <ResultPills form={h.recent_form} size={20} />
                  : <span className="text-pb-faintest" style={{ fontSize: 12 }}>—</span>}
              </div>
            </div>
            {lmResult && <StatCell label="Last meeting" value={lmResult} color={lmColor} />}
            {lm && (lm.our_runs != null || lm.opp_runs != null) && (
              <div>
                <Eyebrow>Last scoreline</Eyebrow>
                <div className="iq-mono font-semibold" style={{ fontSize: 13, marginTop: 5 }}>
                  {lm.our_runs ?? '—'} v {lm.opp_runs ?? '—'}
                </div>
              </div>
            )}
          </div>

          {/* the plan */}
          {gp ? (
            <div className="flex flex-wrap items-center" style={{ background: 'color-mix(in srgb, var(--pb-accent) 9%, var(--pb-surface))', border: '1px solid color-mix(in srgb, var(--pb-accent) 28%, transparent)', borderRadius: 10, padding: '13px 16px', margin: '14px 0', gap: 18 }}>
              <div style={{ flex: 2, minWidth: 260 }}>
                <Eyebrow className="text-pb-accent">The plan</Eyebrow>
                <div className="iq-display font-bold" style={{ fontSize: 16, lineHeight: 1.2, marginTop: 3 }}>
                  {gp.one_liner || 'Stick to the basics and take your chances.'}
                </div>
              </div>
              <div className="flex" style={{ gap: 18, flex: 1, minWidth: 240 }}>
                <div>
                  <Eyebrow className="text-pb-red">Remove early</Eyebrow>
                  <div className="iq-display font-bold" style={{ fontSize: 13, marginTop: 3 }}>{gp.remove_early?.name ? surname(gp.remove_early.name) : '—'}</div>
                  {gp.remove_early?.why && <div className="text-pb-faint" style={{ fontSize: 10, lineHeight: 1.3, marginTop: 1 }}>{gp.remove_early.why}</div>}
                </div>
                <div>
                  <Eyebrow className="text-pb-amber">See off</Eyebrow>
                  <div className="iq-display font-bold" style={{ fontSize: 13, marginTop: 3 }}>{gp.see_off?.name ? surname(gp.see_off.name) : '—'}</div>
                  {gp.see_off?.why && <div className="text-pb-faint" style={{ fontSize: 10, lineHeight: 1.3, marginTop: 1 }}>{gp.see_off.why}</div>}
                </div>
                <div>
                  <Eyebrow className="text-pb-brand">Target</Eyebrow>
                  <div className="iq-display font-bold" style={{ fontSize: 13, marginTop: 3 }}>{gp.target_bowler?.name ? surname(gp.target_bowler.name) : '—'}</div>
                  {gp.target_bowler?.economy != null && <div className="iq-mono text-pb-faint" style={{ fontSize: 10, marginTop: 1 }}>econ {a2(gp.target_bowler.economy)}</div>}
                </div>
              </div>
            </div>
          ) : (
            <div className="flex items-center" style={{ margin: '14px 0', gap: 8, background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline)', borderRadius: 10, padding: '12px 16px' }}>
              <Icon name={building ? 'refresh' : 'info'} size={15} className={`text-pb-accent ${building ? 'iq-spin' : ''}`} />
              <span className="text-pb-dim" style={{ fontSize: 12.5 }}>
                {building
                  ? 'Building their live dossier… the game plan and danger players will fill in shortly.'
                  : 'Live dossier unavailable. The head-to-head below is from data we already hold.'}
              </span>
            </div>
          )}

          {/* three columns. Squashed to ~1/3 of a 390px screen with nowrap text
              inside, this used to force a horizontal scroll on the ONE surface
              in the module a captain actually opens on a phone. Stacks full-width
              below sm; iq-theme.css pins it back to a fixed 3-col row for print,
              which is always landscape and has the room. */}
          <div className="flex flex-col sm:flex-row iq-cs-columns" style={{ gap: 16 }}>
            <Column title="Get these out" accent="var(--pb-red)">
              {dangerBat.length
                ? dangerBat.slice(0, 3).map((b, i) => (
                  <PlayerRow key={b.player_id || i} name={surname(b.name)}
                    line={runsPhrase(b.runs ?? 0, b.average)}
                    note={dismissPlan(b.name) || b.plan || b.key_note} />
                ))
                : building ? <LoadingBar label="Loading…" expectedMs={35000} labelClassName="text-pb-faint text-[11.5px]" />
                  : <Empty className="text-pb-faint text-[11.5px]">No standout batters identified.</Empty>}
            </Column>

            <div className="iq-cs-divider" />

            <Column title="New-ball threat" accent="var(--pb-accent)">
              {dangerBowl.length
                ? dangerBowl.slice(0, 3).map((b, i) => (
                  <PlayerRow key={b.player_id || i} name={surname(b.name)}
                    line={wktsPhrase(b.wickets ?? 0, b.average)}
                    note={b.plan || b.key_note} />
                ))
                : building ? <LoadingBar label="Loading…" expectedMs={35000} labelClassName="text-pb-faint text-[11.5px]" />
                  : <Empty className="text-pb-faint text-[11.5px]">No standout bowlers identified.</Empty>}
            </Column>

            <div className="iq-cs-divider" />

            <Column title="Our edge" accent="var(--pb-brand)">
              {(ourBat.length || ourBowl.length)
                ? <>
                  {ourBat.slice(0, 2).map((p, i) => (
                    <PlayerRow key={p.player_id || `b${i}`} name={surname(p.name)}
                      line={runsPhrase(p.runs ?? 0, p.average)} note="Scores heavily against them" />
                  ))}
                  {ourBowl.slice(0, 2).map((p, i) => (
                    <PlayerRow key={p.player_id || `w${i}`} name={surname(p.name)}
                      line={wktsPhrase(p.wickets ?? 0, p.average)} note="Has their number, bowl him long" />
                  ))}
                </>
                : <Empty className="text-pb-faint text-[11.5px]">No prior record against them.</Empty>}
            </Column>
          </div>

          {/* footer — win/lose + toss */}
          <div className="flex flex-wrap border-t border-pb-hairline" style={{ gap: 22, marginTop: 16, paddingTop: 13 }}>
            {ready && dossier.how_they_lose?.[0] && (
              <div style={{ flex: 1, minWidth: 220 }}>
                <Eyebrow className="text-pb-brand">They lose when</Eyebrow>
                <div className="text-pb-dim" style={{ fontSize: 11.5, lineHeight: 1.4, marginTop: 4 }}>{dossier.how_they_lose[0]}</div>
              </div>
            )}
            {ready && dossier.how_they_win?.[0] && (
              <div style={{ flex: 1, minWidth: 220 }}>
                <Eyebrow className="text-pb-red">They win when</Eyebrow>
                <div className="text-pb-dim" style={{ fontSize: 11.5, lineHeight: 1.4, marginTop: 4 }}>{dossier.how_they_win[0]}</div>
              </div>
            )}
            {gp?.key_warning && (
              <div style={{ minWidth: 200, flex: 1 }}>
                <Eyebrow className="text-pb-amber">At the toss</Eyebrow>
                <div className="flex items-start" style={{ gap: 5, marginTop: 4 }}>
                  <Tag tone="amber">Watch</Tag>
                  <span className="text-pb-dim" style={{ fontSize: 11.5, lineHeight: 1.4 }}>{gp.key_warning}</span>
                </div>
              </div>
            )}
            {ready && (dossier.coverage?.notes?.length > 0) && !gp?.key_warning && !dossier.how_they_win?.[0] && !dossier.how_they_lose?.[0] && (
              <div style={{ flex: 1, minWidth: 220 }}>
                <Eyebrow>Coverage</Eyebrow>
                <div className="text-pb-faint" style={{ fontSize: 11, lineHeight: 1.4, marginTop: 4 }}>{dossier.coverage.notes[0]}</div>
              </div>
            )}
          </div>

          <div className="iq-mono text-pb-faint text-center" style={{ fontSize: 8.5, marginTop: 14 }}>
            Generated by BetterIQ from scorecard data · {new Date().toLocaleDateString()}
            {dossier?.grade_filter?.length ? ` · scoped to ${dossier.grade_filter.join(', ')}` : ''}
            {dossier?.scouted?.season_name ? ` · ${dossier.scouted.season_name}` : ''}
            {dossier?.built_at ? ` · dossier built ${new Date(dossier.built_at).toLocaleDateString()}` : ''}
            {' '}· a starting plan, not gospel
          </div>
        </div>
      </div>
      )}
    </div>
  )
}
