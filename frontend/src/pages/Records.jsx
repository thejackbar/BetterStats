import { useState, useEffect } from 'react'
import { RateMark, RateInfo } from '../components/RateCoverage'
import { useParams, Link } from 'react-router-dom'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { useGradeFilters } from '../hooks/useGradeCategories'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import ClubPinGate from './ClubPinGate'
import SeasonSelector from '../components/SeasonSelector'
import { useClubData } from '../hooks/useClubData'
import { Label, Card, PageHeader, PbSpinner, TabBar } from '../lib/presskit'
import { useNameFormat } from '../lib/nameFormat'
import { fmtOvers, formatSeason } from '../lib/cricketFormat'
import { normalizeGender } from '../lib/playerAttributes'

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

/**
 * Why a rate record is filed by season and where a range of seasons is
 * answered instead.
 *
 * An all-time strike rate would blend decades of differently scored cricket
 * into one number nobody can check: older seasons rarely recorded balls faced
 * at all. A season is a period that was scored one way, so it is a figure that
 * can be stood behind. StatLab already takes several seasons at once, which is
 * where a range belongs.
 */
function SeasonRateNote({ unit = 'innings', slug }) {
  return (
    <p className="px-5 py-2.5 pb-hairline-t font-mono text-[10px] text-pb-dim flex flex-wrap items-center gap-1.5">
      <span>
        Filed by season rather than all time, because how much was recorded
        changed from one era to the next. For a range of seasons, use{' '}
        <Link to={slug ? `/${slug}/statlab` : 'statlab'} className="underline hover:text-pb-accent">StatLab</Link>.
      </span>
      <RateInfo unit={unit} />
    </p>
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

function BattingTab({ data, latestSeason, fmt = n => n, slug }) {
  if (!data) return <PbSpinner />
  const isNew = (seasonName) => latestSeason && seasonName && formatSeason(seasonName) === formatSeason(latestSeason)
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
            <span className="text-pb-faintest text-[11px]">{formatSeason(r.season_name)}{isNew(r.season_name) && <NewBadge />}</span>,
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
              <span className="text-pb-faintest text-[11px]">{formatSeason(r.season_name)}{isNew(r.season_name) && <NewBadge />}</span>,
            ])}
          />
        </RecordSection>
      )}
      {data.best_strike_rate_season?.length > 0 && (
        <RecordSection
          title="BEST STRIKE RATE IN A SEASON"
          filter="MIN. 10 INNINGS WITH BALLS FACED"
        >
          <RecordTable
            headers={['Player', 'SR', 'Runs', 'Season']}
            rows={(data.best_strike_rate_season || []).map((r, i) => [
              <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} fmt={fmt} /></span>,
              <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>
                {r.strike_rate != null ? Number(r.strike_rate).toFixed(2) : '—'}
                <RateMark coverage={r.strike_rate_coverage} />
              </span>,
              r.runs ?? '—',
              <span className="text-pb-faintest text-[11px]">{formatSeason(r.season_name)}{isNew(r.season_name) && <NewBadge />}</span>,
            ])}
          />
          <SeasonRateNote slug={slug} />
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

function BowlingTab({ data, latestSeason, fmt = n => n, slug }) {
  if (!data) return <PbSpinner />
  const isNew = (seasonName) => latestSeason && seasonName && formatSeason(seasonName) === formatSeason(latestSeason)
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
            <span className="text-pb-faintest text-[11px]">{formatSeason(r.season_name)}{isNew(r.season_name) && <NewBadge />}</span>,
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
            <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>
              {r.economy != null ? Number(r.economy).toFixed(2) : '—'}
              <RateMark coverage={r.economy_coverage} unit="spells" />
            </span>,
            r.wickets ?? '—', fmtOvers(r.overs),
          ])}
        />
      </RecordSection>
      {data.best_economy_season?.length > 0 && (
        <RecordSection
          title="BEST ECONOMY IN A SEASON"
          filter="MIN. 50 OVERS"
        >
          <RecordTable
            headers={['Player', 'Econ', 'Wkts', 'Ov', 'Season']}
            rows={(data.best_economy_season || []).map((r, i) => [
              <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} fmt={fmt} /></span>,
              <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>
                {r.economy != null ? Number(r.economy).toFixed(2) : '—'}
                <RateMark coverage={r.economy_coverage} unit="spells" />
              </span>,
              r.wickets ?? '—', fmtOvers(r.overs),
              <span className="text-pb-faintest text-[11px]">{formatSeason(r.season_name)}{isNew(r.season_name) && <NewBadge />}</span>,
            ])}
          />
          <SeasonRateNote unit="spells" slug={slug} />
        </RecordSection>
      )}
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
              <span className="text-pb-faintest text-[11px]">{formatSeason(r.season_name)}{isNew(r.season_name) && <NewBadge />}</span>,
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
                    <td className="py-2.5 px-3 font-mono text-pb-faintest text-[11px] text-right">{formatSeason(r.season_name) || '—'}</td>
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
                        <td className="py-2 px-3 font-mono text-pb-faintest text-[11px] text-right">{formatSeason(r.season_name) || '—'}</td>
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
                        <td className="py-2.5 px-3 font-mono text-pb-faintest text-[11px] text-right">{formatSeason(r.season_name) || '—'}</td>
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


// ── The club's own records ───────────────────────────────────────────────────
// Every figure here is a TEAM figure, rebuilt per game from the per-innings
// rows (cricket stores no team score anywhere). The backend marks each row
// `exact` — true when it holds the scorecard's own innings total, which counts
// extras, false when it could only add up the batters. The two are not the
// same kind of number and this screen never presents them as one.

function GameCell({ r }) {
  const label = r.opponent || 'Unknown opponent'
  const inner = (
    <>
      <span className="text-pb-text">{r.our_venue === 'AWAY' ? 'at ' : 'v '}{label}</span>
      {r.is_final && (
        <span className="ml-1.5 font-mono text-[9px] tracking-wide3 text-pb-accent">FINAL</span>
      )}
    </>
  )
  return (
    <span>
      {r.game_id
        ? <Link to={`/games/${r.game_id}`} className="hover:underline">{inner}</Link>
        : inner}
      <span className="block font-mono text-[10px] text-pb-faint">
        {[fmtDate(r.played_at), r.grade_name, r.season_name].filter(Boolean).join(' · ')}
      </span>
    </span>
  )
}

// An approximate figure is marked where it is READ, not only counted in a
// footnote — a reader comparing two rows needs to know which of them is a
// bat-only sum at the moment they compare them.
function Approx() {
  return (
    <span
      className="ml-1 font-mono text-[9px] text-pb-faintest"
      title="Bat-only figure: the club doesn't hold this innings' extras, so the real total was higher."
    >~</span>
  )
}

function Val({ r, suffix, wkts }) {
  // A team total reads as a score: 8/323 all out is 323, and the two are
  // different facts a reader wants side by side.
  const score = (suffix === 'runs' && wkts != null && wkts < 10)
    ? `${wkts}/${r.value}` : r.value
  return (
    <span>
      <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{score}</span>
      {suffix ? <span className="text-pb-faint"> {suffix}</span> : null}
      {r.exact === false && <Approx />}
    </span>
  )
}

function ScoreCell({ runs, wkts }) {
  if (runs == null) return '—'
  return wkts != null && wkts < 10 ? `${wkts}/${runs}` : `${runs}`
}

// `innings` marks a board whose VALUE is a single innings rather than a
// match figure. A two-day match puts two rows on such a board, so each says
// which innings it was — without it they read as a duplicated game.
function GameBoard({ title, board, suffix, note, innings = false, chase = false }) {
  const rows = board?.rows || []
  const multi = innings && rows.some(r => (r.our_innings_count || 0) > 1
                                       || (r.their_innings_count || 0) > 1)
  return (
    <RecordSection title={title} filter={note} empty={!rows.length}>
      <RecordTable
        headers={chase
          ? ['Match', 'TARGET', 'Made']
          : multi
            ? ['Match', 'Inns', suffix ? suffix.toUpperCase() : 'VALUE']
            : ['Match', suffix ? suffix.toUpperCase() : 'VALUE', 'Result']}
        rows={rows.map((r, i) => chase ? [
          <span key={r.game_id || i}><RankNum rank={i + 1} /><GameCell r={r} /></span>,
          <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.value}</span>,
          // What we made getting there — without it a 251 target beside a
          // 240-run innings reads as an error rather than a chase.
          <span className="text-pb-faint">
            {r.chased_with != null
              ? `${r.innings_wickets != null && r.innings_wickets < 10
                    ? `${r.innings_wickets}/` : ''}${r.chased_with}`
              : '—'}
          </span>,
        ] : multi ? [
          <span key={r.game_id || i}><RankNum rank={i + 1} /><GameCell r={r} /></span>,
          <span className="text-pb-faint">{ordinalInnings(r.innings_number)}</span>,
          <Val r={r} suffix={suffix} wkts={r.innings_wickets} />,
        ] : [
          <span key={r.game_id || i}><RankNum rank={i + 1} /><GameCell r={r} /></span>,
          <Val r={r} suffix={suffix} wkts={r.innings_wickets} />,
          <span className="text-pb-faint">
            <ScoreCell runs={r.our_runs} wkts={r.our_wickets} />
            {' v '}
            <ScoreCell runs={r.opp_runs} wkts={r.opp_wickets} />
          </span>,
        ])}
      />
    </RecordSection>
  )
}

function ordinalInnings(n) {
  return n == null ? '—' : (['1st', '2nd', '3rd', '4th'][n - 1] || `${n}`)
}

function StreakBoard({ title, board, losses = false }) {
  const rows = board?.rows || []
  return (
    // Consecutive COMPLETED matches in date order across whatever the filters
    // above cover — so picking a grade gives that grade's own run. A washed-out
    // fixture has no result and never breaks a streak.
    <RecordSection title={title} empty={!rows.length}
                   filter="consecutive matches, in date order">
      <RecordTable
        headers={['Run', 'Games', losses ? 'Lost' : 'Won', 'Grades']}
        rows={rows.map((r, i) => [
          <span key={i}>
            <RankNum rank={i + 1} />
            <span className="text-pb-text">
              {[r.from_season, r.to_season].filter(Boolean).filter((v, j, a) => a.indexOf(v) === j).join(' – ')}
            </span>
            <span className="block font-mono text-[10px] text-pb-faint">
              {[fmtDate(r.from), fmtDate(r.to)].filter(Boolean).join(' – ')}
            </span>
          </span>,
          <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.value}</span>,
          <span className="text-pb-faint">
            {losses ? r.losses : r.wins}{r.draws ? ` (${r.draws} drawn)` : ''}
          </span>,
          <span className="text-pb-faint text-[11px]">
            {(r.grades || []).join(', ') || '—'}
          </span>,
        ])}
      />
    </RecordSection>
  )
}

const CATEGORY_LABELS = {
  senior: 'Senior', junior: 'Juniors', womens: "Women's",
  masters: 'Masters', mixed: 'Mixed',
}
const FORMAT_LABELS = { two_day: 'Two day', one_day: 'One day', t20: 'T20' }

// Named from the scope the SERVER reports back, never from the page's own
// filter state — what a reader needs is what the figures actually cover, and
// the two can differ (an explicitly picked grade drops the category half).
function describeScope(scope, { season, grade, finals }) {
  const parts = []
  if (season) parts.push(season)
  if (grade) parts.push(grade)
  if (scope?.competition_active && (scope.competition_names || []).length)
    parts.push(scope.competition_names.join(', '))
  if (scope?.category_active && (scope.categories || []).length)
    parts.push(scope.categories.map(c => CATEGORY_LABELS[c] || c).join(' + '))
  if (scope?.format_active && (scope.formats || []).length)
    parts.push(scope.formats.map(f => FORMAT_LABELS[f] || f).join(' + '))
  if (finals) parts.push('Finals only')
  return parts.length ? parts.join(' · ') : 'All grades, all seasons'
}

function ClubTab({ data, seasonLabel, gradeLabel, finalsOnly }) {
  if (!data) return <PbSpinner />
  const b = data.boards || {}
  const s = data.summary || {}
  const cov = data.coverage || {}
  const scopeLine = describeScope(data.grade_scope, {
    season: seasonLabel, grade: gradeLabel, finals: finalsOnly })

  if (!s.played) {
    return (
      <Card>
        <p className="text-pb-faintest text-sm px-1 py-3 italic">
          No completed matches yet, so there are no club records to show.
        </p>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      {/* WHAT THESE FIGURES COVER. Every filter above genuinely narrows the
          board, but the top of a 25-row board drawn from decades of cricket
          often doesn't visibly move — so a filter that IS working reads as one
          that isn't. Saying the scope out loud, with the match count beside
          it, is what makes it checkable. */}
      {scopeLine && (
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint px-1">
          COVERING {s.played} {s.played === 1 ? 'MATCH' : 'MATCHES'} · {scopeLine}
        </p>
      )}
      <div className="pb-card px-5 py-4 flex flex-wrap gap-x-8 gap-y-3">
        {[
          ['PLAYED', s.played], ['WON', s.wins], ['LOST', s.losses],
          ['DRAWN', s.draws], ['SEASONS', s.seasons],
        ].map(([label, v]) => (
          <div key={label}>
            <div className="font-mono text-[10px] tracking-wide3 text-pb-faint">{label}</div>
            <div className="text-xl font-bold" style={{ color: 'var(--pb-accent)' }}>{v}</div>
          </div>
        ))}
      </div>

      {/* The club is told what its figures are made of, once, up front —
          an approximate total reads LOW, which flatters a lowest-total
          record and undersells a highest one. */}
      {cov.note && (
        <div className="pb-card px-5 py-3">
          <p className="text-[12px] text-pb-dim">
            <span className="font-mono text-[10px] tracking-wide3 text-pb-faint mr-2">
              {cov.approximate_totals} OF {cov.games_with_a_total} TOTALS ARE APPROXIMATE
            </span>
            {cov.note} Marked <span className="font-mono">~</span> below.
          </p>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {/* Every one of these is a SINGLE INNINGS. The match aggregate is a
            different record and has its own board below. */}
        <GameBoard title="HIGHEST TEAM TOTALS" board={b.highest_totals}
                   suffix="runs" note="one innings" innings />
        <GameBoard title="HIGHEST OPPOSITION TOTALS" board={b.highest_conceded}
                   suffix="runs" note="one innings" innings />
        <GameBoard title="LOWEST TEAM TOTALS" board={b.lowest_totals} suffix="runs"
                   note="all out only" innings />
        <GameBoard title="LOWEST OPPOSITION TOTALS" board={b.lowest_conceded}
                   suffix="runs" note="bowled out only" innings />
        <GameBoard title="HIGHEST MATCH TOTALS" board={b.highest_match_totals}
                   suffix="runs" note="both our innings, two-day matches" />
        <GameBoard title="HIGHEST MATCH AGGREGATES" board={b.highest_match_aggregates}
                   suffix="runs" note="both sides, whole match" />
        <GameBoard title="HIGHEST SUCCESSFUL CHASES" board={b.highest_chases}
                   suffix="runs" note="the target we ran down" chase />
        <GameBoard title="MOST EXTRAS CONCEDED" board={b.most_extras_conceded}
                   suffix="extras" note="one innings, from cards that add up" innings />
        <GameBoard title="NARROWEST WINS (RUNS)" board={b.narrowest_wins_runs}
                   suffix="runs" />
        <GameBoard title="NARROWEST WINS (WICKETS)" board={b.narrowest_wins_wickets}
                   suffix="wkts" />
        <GameBoard title="BIGGEST WINS (RUNS)" board={b.biggest_wins_runs} suffix="runs" />
        <GameBoard title="BIGGEST WINS (WICKETS)" board={b.biggest_wins_wickets} suffix="wkts" />
        <GameBoard title="HEAVIEST DEFEATS (RUNS)" board={b.heaviest_defeats_runs} suffix="runs" />
        <GameBoard title="HEAVIEST DEFEATS (WICKETS)" board={b.heaviest_defeats_wickets} suffix="wkts" />
        <StreakBoard title="LONGEST WINNING RUN" board={b.longest_win_streak} />
        <StreakBoard title="LONGEST UNBEATEN RUN" board={b.longest_unbeaten_streak} />
        <StreakBoard title="LONGEST LOSING RUN" board={b.longest_losing_streak}
                     losses />
      </div>

      <RecordSection title="HEAD TO HEAD" filter="every club we have played"
                     empty={!b.head_to_head?.rows?.length}>
        <RecordTable
          headers={['Opponent', 'P', 'W', 'L', 'D', 'Win %', 'Runs for', 'Runs against']}
          rows={(b.head_to_head?.rows || []).map((r, i) => [
            <span key={r.opponent}><RankNum rank={i + 1} />
              <span className="text-pb-text">{r.opponent}</span></span>,
            r.played,
            <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.wins}</span>,
            r.losses, r.draws, `${r.win_rate}%`,
            <span>{r.runs_for}{r.exact === false && <Approx />}</span>,
            <span>{r.runs_against}{r.exact === false && <Approx />}</span>,
          ])}
        />
      </RecordSection>

      <RecordSection title="SEASON BY SEASON" empty={!b.best_seasons?.rows?.length}>
        <RecordTable
          headers={['Season', 'P', 'W', 'L', 'D', 'Win %', 'Runs for', 'Runs against']}
          rows={(b.best_seasons?.rows || []).map((r, i) => [
            <span key={r.season_id}><RankNum rank={i + 1} />
              <span className="text-pb-text">{r.season_name}</span></span>,
            r.played,
            <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.wins}</span>,
            r.losses, r.draws, `${r.win_rate}%`,
            <span>{r.runs_for}{r.exact === false && <Approx />}</span>,
            <span>{r.runs_against}{r.exact === false && <Approx />}</span>,
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

const MILESTONE_CAT_LABELS = { batting: 'BATTING', bowling: 'BOWLING', fielding: 'FIELDING', matches: 'MATCHES' }
const MILESTONE_CAT_COLORS = {
  batting: 'text-blue-400 bg-blue-400/10 border-blue-400/20',
  bowling: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/20',
  fielding: 'text-amber-400 bg-amber-400/10 border-amber-400/20',
  matches: 'text-purple-400 bg-purple-400/10 border-purple-400/20',
}

function fmtMilestoneDate(iso) {
  if (!iso) return null
  return new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

function milestoneLabel(item, isUpcoming) {
  const { type, milestone_value, target } = item
  const value = isUpcoming ? target : milestone_value
  if (type === 'grade_matches') return `${value} games`
  if (type === 'grade_runs' || type === 'runs') return `${Number(value).toLocaleString()} runs`
  if (type === 'grade_wickets' || type === 'wickets') return `${value} wickets`
  if (type === 'grade_catches' || type === 'catches') return `${value} catches`
  if (type === 'matches') return `${value} club games`
  return `${value}`
}

function MilestoneCatBadge({ cat }) {
  return (
    <span className={`inline-block font-mono text-[9px] tracking-wide3 px-1.5 py-0.5 rounded border ${MILESTONE_CAT_COLORS[cat] || 'text-pb-faint bg-pb-surface2 border-pb-hairline'}`}>
      {MILESTONE_CAT_LABELS[cat] || (cat || '').toUpperCase()}
    </span>
  )
}

function MilestoneProgressBar({ current, target }) {
  const pct = Math.min(100, Math.round((current / target) * 100))
  return (
    <div className="flex items-center gap-2 justify-end">
      <div className="w-20 h-1.5 bg-pb-surface2 rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: 'var(--pb-accent)' }} />
      </div>
      <span className="font-mono text-[10px] text-pb-faint">{pct}%</span>
    </div>
  )
}

function MilestonesTab({ data, loading, gradeName, fmt = n => n }) {
  const [status, setStatus] = useState('upcoming')
  const [category, setCategory] = useState('all')
  const [gender, setGender] = useState('all')

  if (loading) return <PbSpinner message="Loading milestones…" />
  if (!data) return <p className="text-pb-faint text-sm py-8 text-center">No milestones data available.</p>

  const catMatch = item => category === 'all' || item.category === category
  const genderMatch = item => gender === 'all' || normalizeGender(item.gender) === gender
  const upcomingFiltered = (data.upcoming || []).filter(i => catMatch(i) && genderMatch(i))
  const achievedFiltered = (data.achieved || []).filter(i => catMatch(i) && genderMatch(i))
  const showUpcoming = status === 'upcoming' || status === 'all'
  const showAchieved = status === 'achieved' || status === 'all'

  return (
    <div>
      <p className="text-pb-faintest text-sm mb-4">
        {gradeName
          ? <>Milestones within <span className="text-pb-text">{gradeName}</span> — runs, wickets, catches and games played in that grade specifically.</>
          : <>Career milestones across the whole club. Pick a grade above to see milestones within that grade instead.</>}
      </p>
      <div className="flex flex-wrap items-center gap-3 mb-5">
        <div className="flex border pb-hairline rounded overflow-hidden">
          {[['upcoming', 'Upcoming'], ['achieved', 'Achieved'], ['all', 'All']].map(([val, label]) => (
            <button
              key={val}
              onClick={() => setStatus(val)}
              className="px-3 py-1.5 font-mono text-[10px] tracking-wide2 transition-colors hover:text-pb-text"
              style={status === val ? { color: 'var(--pb-accent)', background: 'var(--pb-surface2)' } : { color: 'var(--pb-faint)' }}
            >
              {label.toUpperCase()}
            </button>
          ))}
        </div>
        <div className="flex border pb-hairline rounded overflow-hidden">
          {[['all', 'All'], ['batting', 'Batting'], ['bowling', 'Bowling'], ['fielding', 'Fielding'], ['matches', 'Matches']].map(([val, label]) => (
            <button
              key={val}
              onClick={() => setCategory(val)}
              className="px-3 py-1.5 font-mono text-[10px] tracking-wide2 transition-colors hover:text-pb-text"
              style={category === val ? { color: 'var(--pb-accent)', background: 'var(--pb-surface2)' } : { color: 'var(--pb-faint)' }}
            >
              {label.toUpperCase()}
            </button>
          ))}
        </div>
        <div className="flex border pb-hairline rounded overflow-hidden">
          {[['all', 'All'], ['male', 'Men'], ['female', 'Women']].map(([val, label]) => (
            <button
              key={val}
              onClick={() => setGender(val)}
              className="px-3 py-1.5 font-mono text-[10px] tracking-wide2 transition-colors hover:text-pb-text"
              style={gender === val ? { color: 'var(--pb-accent)', background: 'var(--pb-surface2)' } : { color: 'var(--pb-faint)' }}
            >
              {label.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-6">
        {showUpcoming && (
          <RecordSection title="MILESTONES IN REACH" empty={!upcomingFiltered.length}>
            <table className="w-full text-[13px]">
              <thead>
                <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left">
                  <th className="py-2.5 px-3 font-medium">Player</th>
                  <th className="py-2.5 px-3 font-medium hidden sm:table-cell">Category</th>
                  <th className="py-2.5 px-3 font-medium">Milestone</th>
                  <th className="py-2.5 px-3 font-medium text-right">Progress</th>
                  <th className="py-2.5 px-3 font-medium text-right">To Go</th>
                </tr>
              </thead>
              <tbody>
                {upcomingFiltered.map((item, i) => (
                  <tr key={`${item.player_id}-${item.type}-${item.target}`} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                    <td className="py-2.5 px-3"><PlayerLink id={item.player_id} name={item.player_name} fmt={fmt} /></td>
                    <td className="py-2.5 px-3 hidden sm:table-cell"><MilestoneCatBadge cat={item.category} /></td>
                    <td className="py-2.5 px-3 font-mono text-pb-dim">
                      {milestoneLabel(item, true)}
                      <span className="block text-pb-faintest text-[10px] mt-0.5">{item.current.toLocaleString()} / {item.target.toLocaleString()}</span>
                    </td>
                    <td className="py-2.5 px-3 text-right"><MilestoneProgressBar current={item.current} target={item.target} /></td>
                    <td className="py-2.5 px-3 font-mono font-bold text-right" style={{ color: 'var(--pb-accent)' }}>{item.needed}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </RecordSection>
        )}

        {showAchieved && (
          <RecordSection title="ACHIEVED" empty={!achievedFiltered.length}>
            <table className="w-full text-[13px]">
              <thead>
                <tr className="text-pb-faint font-mono text-[10px] tracking-wide3 text-left">
                  <th className="py-2.5 px-3 font-medium">Player</th>
                  <th className="py-2.5 px-3 font-medium hidden sm:table-cell">Category</th>
                  <th className="py-2.5 px-3 font-medium">Milestone</th>
                  <th className="py-2.5 px-3 font-medium text-right">Date</th>
                </tr>
              </thead>
              <tbody>
                {achievedFiltered.map((item, i) => (
                  <tr key={`${item.player_id}-${item.type}-${item.milestone_value}-${item.detail}-${i}`} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
                    <td className="py-2.5 px-3"><PlayerLink id={item.player_id} name={item.player_name} fmt={fmt} /></td>
                    <td className="py-2.5 px-3 hidden sm:table-cell"><MilestoneCatBadge cat={item.category} /></td>
                    <td className="py-2.5 px-3 font-mono text-pb-dim">{milestoneLabel(item, false)}</td>
                    <td className="py-2.5 px-3 font-mono text-[11px] text-pb-faintest text-right whitespace-nowrap">{fmtMilestoneDate(item.achieved_at) || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </RecordSection>
        )}
      </div>
    </div>
  )
}

const TABS = [
  { key: 'club',         label: 'CLUB' },
  { key: 'batting',      label: 'BATTING' },
  { key: 'bowling',      label: 'BOWLING' },
  { key: 'partnerships', label: 'PARTNERSHIPS' },
  { key: 'allrounders',  label: 'ALL-ROUNDERS' },
  { key: 'milestones',   label: 'MILESTONES' },
  { key: 'team',         label: 'TEAM' },
]

export default function Records() {
  const { clubSlug } = useParams()
  const { club, orgId, inactive, notFound, locked, unlock, requestAccess } = useClub(clubSlug)
  useClubTheme(club)
  const fmt = useNameFormat(club)

  const { org, seasons, selectedSeason, setSelectedSeason, loading: clubLoading } = useClubData(orgId)

  const [orgGrades, setOrgGrades] = useState([])
  const [selectedGradeName, setSelectedGradeName] = useState(null)
  const [finalsOnly, setFinalsOnly] = useState(false)
  const [captainOnly, setCaptainOnly] = useState(false)
  const [gender, setGender] = useState(null)
  // Grade type and match type, the same two rows every other stats screen has.
  const {
    available: availableCategories, availableFormats, defaultCategories,
    gradeType, setGradeType, matchFormat, setMatchFormat,
    categoriesParam, formatsParam, competitionsParam,
    competition, setCompetition, availableCompetitions,
  } = useGradeFilters(orgId)
  const [tab, setTab] = useState('batting')
  const [records, setRecords] = useState(null)
  const [loading, setLoading] = useState(true)
  const [milestones, setMilestones] = useState(null)
  const [milestonesLoading, setMilestonesLoading] = useState(true)
  const [clubRecords, setClubRecords] = useState(null)
  const [clubLoadingRecs, setClubLoadingRecs] = useState(false)

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
    api.getRecords(orgId, { seasonId: selectedSeason, gradeName: selectedGradeName, finalsOnly, captainOnly, gender, categories: categoriesParam, formats: formatsParam, competitions: competitionsParam })
      .then(setRecords)
      .catch(() => setRecords(null))
      .finally(() => setLoading(false))
  }, [orgId, selectedSeason, selectedGradeName, finalsOnly, captainOnly, gender, categoriesParam, formatsParam, competitionsParam])

  useEffect(() => {
    if (!orgId || tab !== 'club') return
    setClubLoadingRecs(true)
    api.getClubRecords(orgId, {
      seasonId: selectedSeason, gradeName: selectedGradeName,
      finalsOnly, categories: categoriesParam, formats: formatsParam,
      competitions: competitionsParam,
    })
      .then(setClubRecords)
      .catch(() => setClubRecords(null))
      .finally(() => setClubLoadingRecs(false))
  }, [orgId, tab, selectedSeason, selectedGradeName, finalsOnly, categoriesParam,
      formatsParam, competitionsParam])

  useEffect(() => {
    if (!orgId) return
    setMilestonesLoading(true)
    api.getRecordsMilestones(orgId, selectedGradeName)
      .then(setMilestones)
      .catch(() => setMilestones(null))
      .finally(() => setMilestonesLoading(false))
  }, [orgId, selectedGradeName])

  if (locked) return <ClubPinGate slug={clubSlug} lockInfo={locked} unlock={unlock} requestAccess={requestAccess} />
  if (inactive) return <ClubInactive slug={clubSlug} />
  if (notFound) return <ClubInactive variant="notfound" slug={clubSlug} />
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
            gradeType={gradeType}
            setGradeType={setGradeType}
            matchFormat={matchFormat}
            setMatchFormat={setMatchFormat}
            competition={competition}
            setCompetition={setCompetition}
            availableCompetitions={availableCompetitions}
            availableCategories={availableCategories}
            availableFormats={availableFormats}
            defaultCategories={defaultCategories}
            showCompetitionFilter
            showGradeTypeFilter
            showMatchFormatFilter
            showGenderFilter={tab !== 'club'}
            showCaptainFilter={tab !== 'club'}
          />
          {orgGrades.length > 0 && (
            <div className="flex items-center gap-2">
              <label className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase whitespace-nowrap hidden sm:block">Grade</label>
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
        {/* The club board is its own fetch, so it renders outside the player
            records gate: a failure on one must not blank the other, and a
            reader on CLUB shouldn't wait on ~40 per-player rankings. */}
        {tab === 'club' ? (
          clubLoadingRecs && !clubRecords
            ? <PbSpinner message="Loading club records…" />
            : !clubRecords
              ? <p className="text-pb-faint text-sm py-8 text-center">No club records available.</p>
              : <ClubTab
                  data={clubRecords}
                  seasonLabel={selectedSeason
                    ? formatSeason(seasons.find(x => x.id === selectedSeason)?.name)
                    : null}
                  gradeLabel={selectedGradeName}
                  finalsOnly={finalsOnly}
                />
        ) : loading ? <PbSpinner message="Loading records…" /> : !records ? (
          <p className="text-pb-faint text-sm py-8 text-center">No records data available.</p>
        ) : (
          <>
            {tab === 'batting'      && <BattingTab      data={records.batting}       latestSeason={latestSeason} fmt={fmt} slug={clubSlug} />}
            {tab === 'bowling'      && <BowlingTab      data={records.bowling}       latestSeason={latestSeason} fmt={fmt} slug={clubSlug} />}
            {tab === 'partnerships' && <PartnershipsTab data={records.partnerships}  fmt={fmt} />}
            {tab === 'allrounders'  && <AllRoundersTab  data={records.allrounders}  fmt={fmt} />}
            {tab === 'milestones'   && <MilestonesTab   data={milestones} loading={milestonesLoading} gradeName={selectedGradeName} fmt={fmt} />}
            {tab === 'team'         && <TeamTab         data={records.team}          fmt={fmt} />}
          </>
        )}
      </main>
    </div>
  )
}
