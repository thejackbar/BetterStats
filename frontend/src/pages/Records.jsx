import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import SeasonSelector from '../components/SeasonSelector'
import { useClubData } from '../hooks/useClubData'
import { AnimatedNum, Label, Card, PageHeader, PbSpinner, TabBar } from '../lib/presskit'

const ORDINALS = ['1st','2nd','3rd','4th','5th','6th','7th','8th','9th','10th']

function fmtDate(iso) {
  if (!iso) return null
  return new Date(iso + 'T00:00:00').toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

function opponent(row) {
  return row.home_team && row.away_team ? `${row.home_team} v ${row.away_team}` : null
}

function PlayerLink({ id, name }) {
  if (!id) return <span className="text-pb-text">{name}</span>
  return <Link to={`/players/${id}`} className="text-pb-text hover:text-pb-accent transition-colors">{name}</Link>
}

function RankNum({ rank }) {
  const color = rank === 1 ? 'var(--pb-amber)' : rank === 2 ? 'var(--pb-text)' : rank === 3 ? '#a07028' : 'var(--pb-faintest)'
  return (
    <span className="font-mono text-[12px] w-6 inline-block text-right mr-2" style={{ color }}>
      {rank}
    </span>
  )
}

function RecordSection({ title, empty, children }) {
  return (
    <div className="pb-card overflow-hidden mb-4">
      <div className="px-5 py-3 pb-hairline-b bg-pb-surface2/40">
        <Label style={{ color: 'var(--pb-accent)' }}>{title}</Label>
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
            <th key={i} className={`py-2.5 px-3 font-medium ${i > 0 && i === headers.length - 1 ? 'text-right' : i > 0 ? 'text-right' : ''}`}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className={`${i ? 'pb-hairline-t' : ''} hover:bg-pb-surface2`}>
            {r.map((cell, j) => (
              <td key={j} className={`py-2.5 px-3 font-mono ${j > 0 && j === r.length - 1 ? 'text-right' : j > 0 ? 'text-right' : ''} ${j > 0 ? 'text-pb-dim' : ''}`}>
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// ── Batting tab ────────────────────────────────────────────────────────
function BattingTab({ data }) {
  if (!data) return <PbSpinner />

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <RecordSection title="MOST CAREER RUNS" empty={!data.top_career_runs?.length}>
        <RecordTable
          headers={['Player', 'Runs', 'Inn', 'Avg', 'HS']}
          rows={(data.top_career_runs || []).map((r, i) => [
            <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></span>,
            <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.runs?.toLocaleString()}</span>,
            r.innings ?? '—', r.average ?? '—', r.high_score ?? '—',
          ])}
        />
      </RecordSection>

      <RecordSection title="HIGHEST INDIVIDUAL SCORES" empty={!data.top_high_scores?.length}>
        <RecordTable
          headers={['Player', 'Score', 'Season']}
          rows={(data.top_high_scores || []).map((r, i) => [
            <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></span>,
            <span className="font-bold" style={{ color: r.runs >= 100 ? 'var(--pb-amber)' : 'var(--pb-accent)' }}>{r.runs}{r.not_out ? '*' : ''}</span>,
            <span className="text-pb-faintest text-[11px]">{r.season_name}</span>,
          ])}
        />
      </RecordSection>

      <RecordSection title="BEST BATTING AVERAGE" empty={!data.top_batting_avg?.length}>
        <RecordTable
          headers={['Player', 'Avg', 'Runs', 'Inn']}
          rows={(data.top_batting_avg || []).map((r, i) => [
            <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></span>,
            <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.average}</span>,
            r.runs ?? '—', r.innings ?? '—',
          ])}
        />
      </RecordSection>

      <RecordSection title="BEST STRIKE RATE (MIN. 50 BALLS)" empty={!data.top_strike_rate?.length}>
        <RecordTable
          headers={['Player', 'SR', 'Runs', 'Inn']}
          rows={(data.top_strike_rate || []).map((r, i) => [
            <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></span>,
            <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.strike_rate}</span>,
            r.runs ?? '—', r.innings ?? '—',
          ])}
        />
      </RecordSection>

      <RecordSection title="MOST HUNDREDS" empty={!data.most_hundreds?.length}>
        <RecordTable
          headers={['Player', '100s', 'Runs']}
          rows={(data.most_hundreds || []).map((r, i) => [
            <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></span>,
            <span className="font-bold" style={{ color: 'var(--pb-amber)' }}>{r.hundreds}</span>,
            r.runs ?? '—',
          ])}
        />
      </RecordSection>

      <RecordSection title="MOST FIFTIES" empty={!data.most_fifties?.length}>
        <RecordTable
          headers={['Player', '50s', '100s', 'Runs']}
          rows={(data.most_fifties || []).map((r, i) => [
            <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></span>,
            <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.fifties}</span>,
            r.hundreds ?? '—', r.runs ?? '—',
          ])}
        />
      </RecordSection>

      {data.most_runs_season?.length > 0 && (
        <RecordSection title="MOST RUNS IN A SEASON">
          <RecordTable
            headers={['Player', 'Runs', 'Season']}
            rows={(data.most_runs_season || []).map((r, i) => [
              <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></span>,
              <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.runs?.toLocaleString()}</span>,
              <span className="text-pb-faintest text-[11px]">{r.season_name}</span>,
            ])}
          />
        </RecordSection>
      )}

      {data.most_sixes?.length > 0 && (
        <RecordSection title="MOST SIXES (CAREER)">
          <RecordTable
            headers={['Player', '6s', 'Runs']}
            rows={(data.most_sixes || []).map((r, i) => [
              <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></span>,
              <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.sixes ?? r.total_sixes}</span>,
              r.runs ?? '—',
            ])}
          />
        </RecordSection>
      )}
    </div>
  )
}

// ── Bowling tab ────────────────────────────────────────────────────────
function BowlingTab({ data }) {
  if (!data) return <PbSpinner />

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <RecordSection title="MOST CAREER WICKETS" empty={!data.top_career_wickets?.length}>
        <RecordTable
          headers={['Player', 'Wkts', 'Avg', 'Econ']}
          rows={(data.top_career_wickets || []).map((r, i) => [
            <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></span>,
            <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.wickets}</span>,
            r.average ?? '—', r.economy ?? '—',
          ])}
        />
      </RecordSection>

      <RecordSection title="BEST INNINGS FIGURES" empty={!data.best_innings_figures?.length}>
        <RecordTable
          headers={['Player', 'Figures', 'Season']}
          rows={(data.best_innings_figures || []).map((r, i) => [
            <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></span>,
            <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.wickets}/{r.runs}</span>,
            <span className="text-pb-faintest text-[11px]">{r.season_name}</span>,
          ])}
        />
      </RecordSection>

      <RecordSection title="BEST BOWLING AVERAGE" empty={!data.top_bowling_avg?.length}>
        <RecordTable
          headers={['Player', 'Avg', 'Wkts']}
          rows={(data.top_bowling_avg || []).map((r, i) => [
            <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></span>,
            <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.average}</span>,
            r.wickets ?? '—',
          ])}
        />
      </RecordSection>

      <RecordSection title="BEST ECONOMY RATE" empty={!data.top_economy?.length}>
        <RecordTable
          headers={['Player', 'Econ', 'Wkts', 'Ov']}
          rows={(data.top_economy || []).map((r, i) => [
            <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></span>,
            <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.economy}</span>,
            r.wickets ?? '—', r.overs ?? '—',
          ])}
        />
      </RecordSection>

      {data.most_five_fers?.length > 0 && (
        <RecordSection title="MOST FIVE-WICKET HAULS">
          <RecordTable
            headers={['Player', '5W', 'Wkts']}
            rows={(data.most_five_fers || []).map((r, i) => [
              <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></span>,
              <span className="font-bold" style={{ color: 'var(--pb-amber)' }}>{r.five_wicket_innings}</span>,
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
              <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></span>,
              <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.wickets}</span>,
              <span className="text-pb-faintest text-[11px]">{r.season_name}</span>,
            ])}
          />
        </RecordSection>
      )}
    </div>
  )
}

// ── Partnerships tab ────────────────────────────────────────────────────
function PartnershipsTab({ data }) {
  if (!data) return <PbSpinner />

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <RecordSection title="TOP PARTNERSHIPS (ALL WICKETS)" empty={!data.top_partnerships?.length}>
        <RecordTable
          headers={['Partnership', 'Runs', 'Match']}
          rows={(data.top_partnerships || []).map((r, i) => [
            <span key={i}><RankNum rank={i+1} />
              <Link to={`/players/${r.player1_id}`} className="text-pb-text hover:text-pb-accent">{r.player1_name}</Link>
              <span className="text-pb-faintest mx-1">&</span>
              <Link to={`/players/${r.player2_id}`} className="text-pb-text hover:text-pb-accent">{r.player2_name}</Link>
            </span>,
            <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.runs}</span>,
            <span className="text-pb-faintest text-[11px]">{r.season_name}</span>,
          ])}
        />
      </RecordSection>

      {ORDINALS.map((ord, wi) => {
        const key = `wicket_${wi + 1}`
        const recs = data[key] || data[`wicket${wi + 1}`] || []
        if (!recs.length) return null
        return (
          <RecordSection key={wi} title={`${ord.toUpperCase()} WICKET PARTNERSHIPS`}>
            <RecordTable
              headers={['Partnership', 'Runs', 'Match']}
              rows={recs.map((r, i) => [
                <span key={i}><RankNum rank={i+1} />
                  <Link to={`/players/${r.player1_id}`} className="text-pb-text hover:text-pb-accent">{r.player1_name}</Link>
                  <span className="text-pb-faintest mx-1">&</span>
                  <Link to={`/players/${r.player2_id}`} className="text-pb-text hover:text-pb-accent">{r.player2_name}</Link>
                </span>,
                <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.runs}</span>,
                <span className="text-pb-faintest text-[11px]">{r.season_name}</span>,
              ])}
            />
          </RecordSection>
        )
      })}
    </div>
  )
}

// ── Team tab ─────────────────────────────────────────────────────────────
function TeamTab({ data }) {
  if (!data) return <PbSpinner />

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <RecordSection title="MOST MATCHES PLAYED" empty={!data.most_matches?.length}>
        <RecordTable
          headers={['Player', 'Matches', 'Seasons']}
          rows={(data.most_matches || []).map((r, i) => [
            <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></span>,
            <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.matches}</span>,
            r.seasons ?? '—',
          ])}
        />
      </RecordSection>

      <RecordSection title="BEST FIELDING (CATCHES)" empty={!data.top_fielders?.length}>
        <RecordTable
          headers={['Player', 'Catches', 'Run Outs']}
          rows={(data.top_fielders || []).map((r, i) => [
            <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></span>,
            <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.total_catches}</span>,
            r.total_run_outs ?? '—',
          ])}
        />
      </RecordSection>

      {data.top_all_rounders?.length > 0 && (
        <RecordSection title="BEST ALL-ROUNDERS">
          <RecordTable
            headers={['Player', 'Runs', 'Wkts', 'Matches']}
            rows={(data.top_all_rounders || []).map((r, i) => [
              <span key={r.player_id}><RankNum rank={i+1} /><PlayerLink id={r.player_id} name={r.name} /></span>,
              r.runs ?? '—',
              <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>{r.wickets}</span>,
              r.matches ?? '—',
            ])}
          />
        </RecordSection>
      )}
    </div>
  )
}

const TABS = [
  { key: 'batting',      label: 'BATTING' },
  { key: 'bowling',      label: 'BOWLING' },
  { key: 'partnerships', label: 'PARTNERSHIPS' },
  { key: 'team',         label: 'TEAM' },
]

export default function Records() {
  const { clubSlug } = useParams()
  const { club, orgId, inactive } = useClub(clubSlug)
  useClubTheme(club)

  if (inactive) return <ClubInactive />

  const { org, seasons, grades, selectedSeason, setSelectedSeason, selectedGrade, setSelectedGrade, loading: clubLoading } = useClubData(orgId)

  const [tab, setTab] = useState('batting')
  const [records, setRecords] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!orgId) return
    setLoading(true)
    api.getRecords(orgId, { seasonId: selectedSeason, gradeId: selectedGrade })
      .then(setRecords)
      .catch(() => setRecords(null))
      .finally(() => setLoading(false))
  }, [orgId, selectedSeason, selectedGrade])

  if (clubLoading) return <PbSpinner message="Loading club data…" />

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow={`HALL OF RECORDS · ${org?.name?.toUpperCase() || ''}`}
          title="The record books."
          meta={[<span key="x">Every club benchmark, since day one.</span>]}
        />

        {/* Filters */}
        <div className="mb-5">
          <SeasonSelector
            seasons={seasons}
            grades={grades}
            selectedSeason={selectedSeason}
            setSelectedSeason={setSelectedSeason}
            selectedGrade={selectedGrade}
            setSelectedGrade={setSelectedGrade}
          />
        </div>

        {/* Tabs */}
        <TabBar tabs={TABS} active={tab} onChange={setTab} />

        {loading ? <PbSpinner message="Loading records…" /> : !records ? (
          <p className="text-pb-faint text-sm py-8 text-center">No records data available.</p>
        ) : (
          <>
            {tab === 'batting'      && <BattingTab      data={records.batting} />}
            {tab === 'bowling'      && <BowlingTab      data={records.bowling} />}
            {tab === 'partnerships' && <PartnershipsTab data={records.partnerships} />}
            {tab === 'team'         && <TeamTab         data={records.team} />}
          </>
        )}
      </main>
    </div>
  )
}
