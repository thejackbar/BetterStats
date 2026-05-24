import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import SeasonSelector from '../components/SeasonSelector'
import { useClubData } from '../hooks/useClubData'
import { Label, Card, PageHeader, PbSpinner, TabBar } from '../lib/presskit'
import { useNameFormat } from '../lib/nameFormat'

const ORDINALS = ['1st','2nd','3rd','4th','5th','6th','7th','8th','9th','10th']

function fmtDate(iso) {
  if (!iso) return null
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

function PlayerLink({ id, name, fmt = n => n }) {
  if (!id) return <span className="text-pb-text">{fmt(name)}</span>
  return <Link to={`/players/${id}`} className="text-pb-text hover:text-pb-accent transition-colors">{fmt(name)}</Link>
}

function RankNum({ rank }) {
  const color = rank === 1 ? 'var(--pb-amber)' : rank === 2 ? 'var(--pb-text)' : rank === 3 ? '#a07028' : 'var(--pb-faintest)'
  return (
    <span className="font-mono text-[12px] w-6 inline-block text-right mr-2" style={{ color }}>
      {rank}
    </span>
  )
}

function NewBadge() {
  return (
    <span className="ml-1.5 font-mono text-[9px] tracking-wide2 px-1 py-0.5 rounded"
          style={{ background: 'color-mix(in srgb, var(--pb-accent) 15%, transparent)', color: 'var(--pb-accent)' }}>
      NEW
    </span>
  )
}

function RecordSection({ title, filter, empty, children }) {
  return (
    <div className="pb-card overflow-hidden mb-4">
      <div className="px-5 py-3 pb-hairline-b bg-pb-surface2/40 flex items-center gap-3">
        <Label style={{ color: 'var(--pb-accent)' }}>{title}</Label>
        {filter && <span className="font-mono text-[10px] text-pb-faintest">{filter}</span>}
      </div>
      {empty
        ? <p className="text-pb-faintest text-sm px-5 py-4 italic">No data yet.</p>
        : <div className="overflow-x-auto pb-scroll">{children}</div>
      }
    </div>
  )
}

function RecordTable({ headers, rows }) {
  return (
    <table className="w-full text-[13px]">
      <thead>
        <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left">
          {headers.map((h, i) => (
            <th key={i} className={`py-2.5 px-3 font-medium ${i > 0 ? 'text-right' : ''}`}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
            {r.map((cell, j) => (
              <td key={j} className={`py-2.5 px-3 font-mono ${j > 0 ? 'text-right text-pb-dim' : ''}`}>
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function BattingTab({ data, latestSeason, fmt = n => n }) {
  if (!data) return <PbSpinner />
  const isNew = (seasonName) => latestSeason && seasonName && seasonName === latestSeason
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <RecordSection title="MOST CAREER RUNS" empty={!data.top_career_runs?.length}>
        <RecordTable
          headers={['Player', 'Runs', 'M', 'Inn', 'Avg', 'HS']}
          rows={(data.top_career_runs || []).map((r, i) => [
            <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} fmt={fmt} /></span>,
            <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.runs?.toLocaleString()}</span>,
            r.matches ?? '—', r.innings ?? '—', r.average != null ? Number(r.average).toFixed(2) : '—', r.high_score ?? '—',
          ])}
        />
      </RecordSection>
      <RecordSection title="HIGHEST INDIVIDUAL SCORES" empty={!data.top_high_scores?.length}>
        <RecordTable
          headers={['Player', 'Score', 'Season']}
          rows={(data.top_high_scores || []).map((r, i) => [
            <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} fmt={fmt} /></span>,
            <span className="font-bold" style={{ color: r.runs >= 100 ? 'var(--pb-chart-milestone, #f5b542)' : 'var(--pb-accent)' }}>{r.runs}{r.not_out ? '*' : ''}</span>,
            <span className="text-pb-faintest text-[11px]">{r.season_name}{isNew(r.season_name) && <NewBadge />}</span>,
          ])}
        />
      </RecordSection>
      <RecordSection title="BEST BATTING AVERAGE" filter="MIN. 10 DISMISSALS" empty={!data.top_batting_avg?.length}>
        <RecordTable
          headers={['Player', 'Avg', 'M', 'Runs', 'Inn']}
          rows={(data.top_batting_avg || []).map((r, i) => [
            <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} fmt={fmt} /></span>,
            <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.average != null ? Number(r.average).toFixed(2) : '—'}</span>,
            r.matches ?? '—', r.runs ?? '—', r.innings ?? '—',
          ])}
        />
      </RecordSection>
      <RecordSection title="MOST HUNDREDS" empty={!data.most_hundreds?.length}>
        <RecordTable
          headers={['Player', '100s', 'M', 'Runs']}
          rows={(data.most_hundreds || []).map((r, i) => [
            <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} fmt={fmt} /></span>,
            <span className="font-bold" style={{ color: 'var(--pb-chart-milestone, #f5b542)' }}>{r.hundreds}</span>,
            r.matches ?? '—', r.runs ?? '—',
          ])}
        />
      </RecordSection>
      <RecordSection title="MOST FIFTIES" empty={!data.most_fifties?.length}>
        <RecordTable
          headers={['Player', '50s', 'M', 'Runs']}
          rows={(data.most_fifties || []).map((r, i) => [
            <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} fmt={fmt} /></span>,
            <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.fifties}</span>,
            r.matches ?? '—', r.runs ?? '—',
          ])}
        />
      </RecordSection>
      {data.most_runs_season?.length > 0 && (
        <RecordSection title="MOST RUNS IN A SEASON">
          <RecordTable
            headers={['Player', 'Runs', 'Season']}
            rows={(data.most_runs_season || []).map((r, i) => [
              <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} fmt={fmt} /></span>,
              <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.runs?.toLocaleString()}</span>,
              <span className="text-pb-faintest text-[11px]">{r.season_name}{isNew(r.season_name) && <NewBadge />}</span>,
            ])}
          />
        </RecordSection>
      )}
      {data.most_sixes?.length > 0 && (
        <RecordSection title="MOST SIXES (CAREER)">
          <RecordTable
            headers={['Player', '6s', 'Runs']}
            rows={(data.most_sixes || []).map((r, i) => [
              <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} fmt={fmt} /></span>,
              <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.sixes ?? r.total_sixes}</span>,
              r.runs ?? '—',
            ])}
          />
        </RecordSection>
      )}
    </div>
  )
}

function BowlingTab({ data, latestSeason, fmt = n => n }) {
  if (!data) return <PbSpinner />
  const isNew = (seasonName) => latestSeason && seasonName && seasonName === latestSeason
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <RecordSection title="MOST CAREER WICKETS" empty={!data.top_career_wickets?.length}>
        <RecordTable
          headers={['Player', 'Wkts', 'M', 'Avg', 'Econ']}
          rows={(data.top_career_wickets || []).map((r, i) => [
            <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} fmt={fmt} /></span>,
            <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.wickets}</span>,
            r.matches ?? '—', r.average != null ? Number(r.average).toFixed(2) : '—', r.economy != null ? Number(r.economy).toFixed(2) : '—',
          ])}
        />
      </RecordSection>
      <RecordSection title="BEST INNINGS FIGURES" empty={!data.best_innings_figures?.length}>
        <RecordTable
          headers={['Player', 'Figures', 'Season']}
          rows={(data.best_innings_figures || []).map((r, i) => [
            <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} fmt={fmt} /></span>,
            <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.wickets}/{r.runs}</span>,
            <span className="text-pb-faintest text-[11px]">{r.season_name}{isNew(r.season_name) && <NewBadge />}</span>,
          ])}
        />
      </RecordSection>
      <RecordSection title="BEST BOWLING AVERAGE" filter="MIN. 20 WICKETS" empty={!data.top_bowling_avg?.length}>
        <RecordTable
          headers={['Player', 'Avg', 'Wkts', 'M']}
          rows={(data.top_bowling_avg || []).map((r, i) => [
            <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} fmt={fmt} /></span>,
            <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.average != null ? Number(r.average).toFixed(2) : '—'}</span>,
            r.wickets ?? '—', r.matches ?? '—',
          ])}
        />
      </RecordSection>
      <RecordSection title="BEST ECONOMY RATE" filter="MIN. 50 OVERS" empty={!data.top_economy?.length}>
        <RecordTable
          headers={['Player', 'Econ', 'Wkts', 'Ov']}
          rows={(data.top_economy || []).map((r, i) => [
            <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} fmt={fmt} /></span>,
            <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.economy != null ? Number(r.economy).toFixed(2) : '—'}</span>,
            r.wickets ?? '—', r.overs ?? '—',
          ])}
        />
      </RecordSection>
      {data.most_five_fors?.length > 0 && (
        <RecordSection title="MOST FIVE-WICKET HAULS">
          <RecordTable
            headers={['Player', '5W', 'Wkts']}
            rows={(data.most_five_fors || []).map((r, i) => [
              <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} fmt={fmt} /></span>,
              <span className="font-bold" style={{ color: 'var(--pb-chart-milestone, #f5b542)' }}>{r.five_fors}</span>,
              r.wickets ?? '—',
            ])}
          />
        </RecordSection>
      )}
      {data.most_wickets_season?.length > 0 && (
        <RecordSection title="MOST WICKETS IN A SEASON">
          <RecordTable
            headers={['Player', 'Wkts', 'Season']}
            rows={(data.most_wickets_season || []).map((r, i) => [
              <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} fmt={fmt} /></span>,
              <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.wickets}</span>,
              <span className="text-pb-faintest text-[11px]">{r.season_name}{isNew(r.season_name) && <NewBadge />}</span>,
            ])}
          />
        </RecordSection>
      )}
    </div>
  )
}

function gradeOrder(name) {
  const m = name.match(/^(\d+)/)
  return m ? parseInt(m[1]) : 999
}

function PartnershipTable({ rows, headers, fmt }) {
  return (
    <table className="w-full text-[13px]">
      <thead>
        <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left">
          {headers.map((h, i) => (
            <th key={i} className={`py-2.5 px-3 font-medium ${h.right ? 'text-right' : ''}`}>{h.label}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
            {r.map((cell, j) => (
              <td key={j} className={`py-2.5 px-3 font-mono ${headers[j].right ? 'text-right text-pb-faintest text-[11px]' : ''}`}>
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function PartnershipsTab({ data, fmt = n => n }) {
  if (!data) return <PbSpinner />

  const allTimeRecords = ORDINALS.map((ord, wi) => {
    const rec = (data[`wicket_${wi + 1}`] || [])[0]
    if (!rec) return null
    return { ...rec, wicket: wi + 1, ordinal: ord }
  }).filter(Boolean)

  const gradeEntries = Object.entries(data.by_grade || {})
    .sort(([a], [b]) => gradeOrder(a) - gradeOrder(b))

  const wicketBuckets = ORDINALS.map((ord, wi) => ({
    ordinal: ord,
    wicket: wi + 1,
    records: (data[`wicket_${wi + 1}`] || []).slice(0, 10),
  })).filter(b => b.records.length > 0)

  return (
    <div className="space-y-6">
      {/* Chart 1: All Time Records */}
      {allTimeRecords.length > 0 && (
        <div className="pb-card overflow-hidden">
          <div className="px-5 py-3 pb-hairline-b bg-pb-surface2/40">
            <Label style={{ color: 'var(--pb-accent)' }}>ALL TIME RECORDS</Label>
            <p className="font-mono text-[10px] text-pb-faintest mt-0.5">Best partnership ever recorded at each wicket position across all grades.</p>
          </div>
          <div className="overflow-x-auto pb-scroll">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left">
                  <th className="py-2.5 px-3 font-medium w-12">WKT</th>
                  <th className="py-2.5 px-3 font-medium">PARTNERSHIP</th>
                  <th className="py-2.5 px-3 font-medium text-right">RUNS</th>
                  <th className="py-2.5 px-3 font-medium text-right">GRADE / SEASON</th>
                </tr>
              </thead>
              <tbody>
                {allTimeRecords.map((r, i) => (
                  <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                    <td className="py-2.5 px-3 font-mono text-pb-faint">{r.ordinal}</td>
                    <td className="py-2.5 px-3">
                      <PlayerLink id={r.player1_id} name={r.player1_name} fmt={fmt} />
                      <span className="text-pb-faintest mx-1">&amp;</span>
                      <PlayerLink id={r.player2_id} name={r.player2_name} fmt={fmt} />
                    </td>
                    <td className="py-2.5 px-3 font-mono font-bold text-right" style={{ color: 'var(--pb-accent)' }}>{r.runs}</td>
                    <td className="py-2.5 px-3 font-mono text-pb-faintest text-[11px] text-right">{r.grade_name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Chart 2: Top 25 Partnerships */}
      {data.top_partnerships?.length > 0 && (
        <div className="pb-card overflow-hidden">
          <div className="px-5 py-3 pb-hairline-b bg-pb-surface2/40">
            <Label style={{ color: 'var(--pb-accent)' }}>TOP 25 PARTNERSHIPS</Label>
            <p className="font-mono text-[10px] text-pb-faintest mt-0.5">Highest individual partnerships across all grades and wickets.</p>
          </div>
          <div className="overflow-x-auto pb-scroll">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left">
                  <th className="py-2.5 px-3 font-medium w-10">#</th>
                  <th className="py-2.5 px-3 font-medium">PARTNERSHIP</th>
                  <th className="py-2.5 px-3 font-medium text-right">RUNS</th>
                  <th className="py-2.5 px-3 font-medium text-right">WKT</th>
                  <th className="py-2.5 px-3 font-medium text-right">GRADE</th>
                  <th className="py-2.5 px-3 font-medium text-right">SEASON</th>
                </tr>
              </thead>
              <tbody>
                {(data.top_partnerships || []).map((r, i) => (
                  <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                    <td className="py-2.5 px-3 font-mono text-pb-faint"><RankNum rank={i+1} /></td>
                    <td className="py-2.5 px-3">
                      <PlayerLink id={r.player1_id} name={r.player1_name} fmt={fmt} />
                      <span className="text-pb-faintest mx-1">&amp;</span>
                      <PlayerLink id={r.player2_id} name={r.player2_name} fmt={fmt} />
                    </td>
                    <td className="py-2.5 px-3 font-mono font-bold text-right" style={{ color: 'var(--pb-accent)' }}>{r.runs}</td>
                    <td className="py-2.5 px-3 font-mono text-pb-faintest text-[11px] text-right">{r.wicket_number ? ORDINALS[r.wicket_number - 1] : '—'}</td>
                    <td className="py-2.5 px-3 font-mono text-pb-faintest text-[11px] text-right">{r.grade_name || '—'}</td>
                    <td className="py-2.5 px-3 font-mono text-pb-faintest text-[11px] text-right">{r.season_name || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* By Grade: best partnership per wicket, two-column grid */}
      {gradeEntries.length > 0 && (
        <div className="pb-card overflow-hidden">
          <div className="px-5 py-3 pb-hairline-b bg-pb-surface2/40">
            <Label style={{ color: 'var(--pb-accent)' }}>WICKET RECORDS BY GRADE</Label>
            <p className="font-mono text-[10px] text-pb-faintest mt-0.5">Best partnership at each wicket, per grade.</p>
          </div>
          <div className="grid gap-0 md:grid-cols-2">
            {gradeEntries.map(([grade, records], gi) => (
              <div key={grade} className={`${gi % 2 === 0 ? 'md:border-r pb-hairline-r' : ''} ${gi >= 2 ? 'pb-hairline-t' : ''}`}>
                <div className="px-5 py-2.5 pb-hairline-b">
                  <span className="font-mono text-[11px] tracking-wide2 text-pb-dim font-semibold">{grade}</span>
                </div>
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="text-pb-faintest font-mono text-[10px] tracking-wide3">
                      <th className="py-2 px-3 text-left">WKT</th>
                      <th className="py-2 px-3 text-left">PARTNERSHIP</th>
                      <th className="py-2 px-3 text-right">RUNS</th>
                      <th className="py-2 px-3 text-right">SEASON</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...records].sort((a, b) => (a.wicket_number ?? 0) - (b.wicket_number ?? 0)).map((r, i) => (
                      <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                        <td className="py-2 px-3 font-mono text-pb-faint">{ORDINALS[(r.wicket_number || 1) - 1]}</td>
                        <td className="py-2 px-3">
                          <PlayerLink id={r.player1_id} name={r.player1_name} fmt={fmt} />
                          <span className="text-pb-faintest mx-1">&amp;</span>
                          <PlayerLink id={r.player2_id} name={r.player2_name} fmt={fmt} />
                        </td>
                        <td className="py-2 px-3 font-mono font-bold text-right" style={{ color: 'var(--pb-accent)' }}>{r.runs}</td>
                        <td className="py-2 px-3 font-mono text-pb-faintest text-[11px] text-right">{r.season_name || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Records by Wicket: top 10 per wicket */}
      {wicketBuckets.length > 0 && (
        <div className="space-y-4">
          <div className="px-1">
            <Label style={{ color: 'var(--pb-accent)' }}>RECORDS BY WICKET</Label>
            <p className="font-mono text-[10px] text-pb-faintest mt-1">Top 10 partnerships at each wicket position across all grades.</p>
          </div>
          {wicketBuckets.map(({ ordinal, wicket, records }) => (
            <div key={wicket} className="pb-card overflow-hidden">
              <div className="px-5 py-3 pb-hairline-b bg-pb-surface2/40">
                <Label style={{ color: 'var(--pb-accent)' }}>{ordinal} WICKET — TOP 10 PARTNERSHIPS</Label>
              </div>
              <div className="overflow-x-auto pb-scroll">
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left">
                      <th className="py-2.5 px-3 font-medium w-10">#</th>
                      <th className="py-2.5 px-3 font-medium">PARTNERSHIP</th>
                      <th className="py-2.5 px-3 font-medium text-right">RUNS</th>
                      <th className="py-2.5 px-3 font-medium text-right">GRADE</th>
                      <th className="py-2.5 px-3 font-medium text-right">SEASON</th>
                    </tr>
                  </thead>
                  <tbody>
                    {records.map((r, i) => (
                      <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                        <td className="py-2.5 px-3 font-mono text-pb-faint"><RankNum rank={i+1} /></td>
                        <td className="py-2.5 px-3">
                          <PlayerLink id={r.player1_id} name={r.player1_name} fmt={fmt} />
                          <span className="text-pb-faintest mx-1">&amp;</span>
                          <PlayerLink id={r.player2_id} name={r.player2_name} fmt={fmt} />
                        </td>
                        <td className="py-2.5 px-3 font-mono font-bold text-right" style={{ color: 'var(--pb-accent)' }}>{r.runs}</td>
                        <td className="py-2.5 px-3 font-mono text-pb-faintest text-[11px] text-right">{r.grade_name || '—'}</td>
                        <td className="py-2.5 px-3 font-mono text-pb-faintest text-[11px] text-right">{r.season_name || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}

      {!allTimeRecords.length && !data.top_partnerships?.length && !gradeEntries.length && (
        <p className="text-pb-faint text-sm py-4">No partnership records available.</p>
      )}
    </div>
  )
}

function TeamTab({ data, fmt = n => n }) {
  if (!data) return <PbSpinner />
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <RecordSection title="MOST MATCHES PLAYED" empty={!data.most_matches?.length}>
        <RecordTable
          headers={['Player', 'Matches', 'Seasons']}
          rows={(data.most_matches || []).map((r, i) => [
            <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} fmt={fmt} /></span>,
            <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.matches}</span>,
            r.seasons ?? '—',
          ])}
        />
      </RecordSection>
      <RecordSection title="MOST SEASONS PLAYED" empty={!data.most_seasons?.length}>
        <RecordTable
          headers={['Player', 'Seasons', 'Matches']}
          rows={(data.most_seasons || []).map((r, i) => [
            <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} fmt={fmt} /></span>,
            <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.seasons}</span>,
            r.matches ?? '—',
          ])}
        />
      </RecordSection>
    </div>
  )
}

function AllRoundersTab({ data, fmt = n => n }) {
  if (!data) return <PbSpinner />
  return (
    <div className="space-y-4">
      <div className="pb-card overflow-hidden">
        <div className="px-5 py-3 pb-hairline-b bg-pb-surface2/40">
          <Label style={{ color: 'var(--pb-accent)' }}>BEST ALL-ROUNDERS (CAREER)</Label>
          <p className="font-mono text-[10px] text-pb-faintest mt-0.5">
            Minimum 1,000 runs &amp; 100 wickets
          </p>
        </div>
        {!data.top_allrounders?.length ? (
          <p className="text-pb-faintest text-sm px-5 py-4 italic">No data yet.</p>
        ) : (
          <div className="overflow-x-auto pb-scroll">
            <table className="w-full min-w-[560px] text-[13px]">
              <thead>
                <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left">
                  <th className="py-2.5 px-3 font-medium w-10">#</th>
                  <th className="py-2.5 px-3 font-medium">PLAYER</th>
                  <th className="py-2.5 px-3 font-medium text-right">M</th>
                  <th className="py-2.5 px-3 font-medium text-right" style={{ color: 'var(--pb-accent)' }}>RUNS</th>
                  <th className="py-2.5 px-3 font-medium text-right">BAT AVG</th>
                  <th className="py-2.5 px-3 font-medium text-right" style={{ color: 'var(--pb-accent)' }}>WKTS</th>
                  <th className="py-2.5 px-3 font-medium text-right">BWL AVG</th>
                </tr>
              </thead>
              <tbody>
                {(data.top_allrounders || []).map((r, i) => (
                  <tr key={r.player_id} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                    <td className="py-2.5 px-3 font-mono text-pb-faint"><RankNum rank={i+1} /></td>
                    <td className="py-2.5 px-3"><PlayerLink id={r.player_id} name={r.name} fmt={fmt} /></td>
                    <td className="py-2.5 px-3 font-mono text-pb-dim text-right">{r.matches ?? '—'}</td>
                    <td className="py-2.5 px-3 font-mono font-bold text-right" style={{ color: 'var(--pb-accent)' }}>{r.runs ?? '—'}</td>
                    <td className="py-2.5 px-3 font-mono text-pb-dim text-right">{r.batting_average != null ? Number(r.batting_average).toFixed(2) : '—'}</td>
                    <td className="py-2.5 px-3 font-mono font-bold text-right" style={{ color: 'var(--pb-accent)' }}>{r.wickets ?? '—'}</td>
                    <td className="py-2.5 px-3 font-mono text-pb-dim text-right">{r.bowling_average != null ? Number(r.bowling_average).toFixed(2) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

const TABS = [
  { key: 'batting',      label: 'BATTING' },
  { key: 'bowling',      label: 'BOWLING' },
  { key: 'partnerships', label: 'PARTNERSHIPS' },
  { key: 'allrounders',  label: 'ALL-ROUNDERS' },
  { key: 'team',         label: 'TEAM' },
]

export default function Records() {
  const { clubSlug } = useParams()
  const { club, orgId, inactive } = useClub(clubSlug)
  useClubTheme(club)
  const fmt = useNameFormat(club)

  if (inactive) return <ClubInactive />

  const { org, seasons, selectedSeason, setSelectedSeason, loading: clubLoading } = useClubData(orgId)

  const [orgGrades, setOrgGrades] = useState([])
  const [selectedGradeName, setSelectedGradeName] = useState(null)
  const [finalsOnly, setFinalsOnly] = useState(false)
  const [captainOnly, setCaptainOnly] = useState(false)
  const [gender, setGender] = useState(null)
  const [tab, setTab] = useState('batting')
  const [records, setRecords] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!orgId) return
    api.getOrgGrades(orgId, selectedSeason)
      .then(grades => {
        setOrgGrades(grades)
        setSelectedGradeName(prev => (prev && grades.some(g => g.name === prev) ? prev : null))
      })
      .catch(() => setOrgGrades([]))
  }, [orgId, selectedSeason])

  useEffect(() => {
    if (!orgId) return
    setLoading(true)
    api.getRecords(orgId, { seasonId: selectedSeason, gradeName: selectedGradeName, finalsOnly, captainOnly, gender })
      .then(setRecords)
      .catch(() => setRecords(null))
      .finally(() => setLoading(false))
  }, [orgId, selectedSeason, selectedGradeName, finalsOnly, captainOnly, gender])

  if (clubLoading) return <PbSpinner message="Loading club data…" />

  const latestSeason = seasons?.[0]?.name || null

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow={`HALL OF RECORDS · ${org?.name?.toUpperCase() || ''}`}
          title="The record books."
          meta={[<span key="x">Every club benchmark, since day one.</span>]}
        />
        <div className="mb-5 flex flex-wrap gap-3 items-center">
          <SeasonSelector
            seasons={seasons}
            grades={[]}
            selectedSeason={selectedSeason}
            setSelectedSeason={setSelectedSeason}
            selectedGrade={null}
            setSelectedGrade={() => {}}
            finalsOnly={finalsOnly}
            setFinalsOnly={setFinalsOnly}
            captainOnly={captainOnly}
            setCaptainOnly={setCaptainOnly}
            gender={gender}
            setGender={setGender}
          />
          {orgGrades.length > 0 && (
            <div className="flex items-center gap-2">
              <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase whitespace-nowrap">Grade</label>
              <select
                value={selectedGradeName || ''}
                onChange={e => setSelectedGradeName(e.target.value || null)}
                className="bg-pb-surface border pb-hairline text-pb-text text-sm rounded px-3 py-1.5 focus:outline-none focus:border-pb-accent"
              >
                <option value="">All grades</option>
                {orgGrades.map(g => (
                  <option key={g.name} value={g.name}>{g.name}</option>
                ))}
              </select>
            </div>
          )}
        </div>
        <TabBar tabs={TABS} active={tab} onChange={setTab} />
        {loading ? <PbSpinner message="Loading records…" /> : !records ? (
          <p className="text-pb-faint text-sm py-8 text-center">No records data available.</p>
        ) : (
          <>
            {tab === 'batting'      && <BattingTab      data={records.batting}       latestSeason={latestSeason} fmt={fmt} />}
            {tab === 'bowling'      && <BowlingTab      data={records.bowling}       latestSeason={latestSeason} fmt={fmt} />}
            {tab === 'partnerships' && <PartnershipsTab data={records.partnerships}  fmt={fmt} />}
            {tab === 'allrounders'  && <AllRoundersTab  data={records.allrounders}  fmt={fmt} />}
            {tab === 'team'         && <TeamTab         data={records.team}          fmt={fmt} />}
          </>
        )}
      </main>
    </div>
  )
}
