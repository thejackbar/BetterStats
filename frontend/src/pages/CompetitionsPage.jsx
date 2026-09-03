import { useParams } from 'react-router-dom'
import { useState, useEffect, useMemo } from 'react'
import { useClub } from '../hooks/useClub'
import { useClubData } from '../hooks/useClubData'
import { useClubTheme } from '../hooks/useClubTheme'
import { usePageMeta } from '../hooks/usePageMeta'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import ClubPinGate from './ClubPinGate'
import SeasonSelector from '../components/SeasonSelector'
import { Card, PageHeader, PbSpinner } from '../lib/presskit'

// The club and team halves of the by-competition breakdown, on one page.
//
// A competition is the club's own named group of grades (see the backend's
// services/competitions.py for why Cricket Australia cannot supply one). Most
// clubs play in more than one, and a single side can play in several inside
// ONE season — which is the thing a flat grade list cannot say, and the reason
// this page exists rather than being another filter on Games.
//
// The player half lives on the player profile, under Analysis, because it is a
// question about a person rather than about the club.

function fmt(n) {
  return typeof n === 'number' ? n.toLocaleString('en-AU') : '—'
}

function WinPct({ value }) {
  // A win percentage over a denominator of nothing is unanswerable, not zero —
  // the same rule every other W/L panel here follows.
  if (value == null) return <span className="text-pb-faint">—</span>
  return <span className="text-pb-text tabular-nums">{value}%</span>
}

function Years({ first, last }) {
  if (!first && !last) return null
  const span = first && last && first !== last ? `${first}–${String(last).slice(-2)}` : (last || first)
  return <span className="text-pb-faint text-xs">{span}</span>
}

function CompetitionCard({ row, grades }) {
  const held = grades.filter(g => g.competition_id === row.competition_id)
  return (
    <Card className="p-4 sm:p-5 mb-4">
      <div className="flex items-start justify-between gap-3 flex-wrap mb-3">
        <div className="min-w-0">
          <h2 className="text-pb-text font-semibold text-[17px] leading-tight">
            {row.competition_name}
          </h2>
          <p className="text-pb-faint text-xs mt-1">
            {row.association_name ? `${row.association_name} · ` : ''}
            {row.seasons} season{row.seasons === 1 ? '' : 's'} ·{' '}
            {row.grades} grade{row.grades === 1 ? '' : 's'}
            {' · '}
            <Years first={row.first_year} last={row.last_year} />
          </p>
        </div>
        <div className="flex items-baseline gap-4 shrink-0 font-mono">
          <div className="text-right">
            <p className="text-[10px] tracking-wide3 text-pb-faint uppercase">Played</p>
            <p className="text-pb-text text-lg tabular-nums">{fmt(row.matches)}</p>
          </div>
          <div className="text-right">
            <p className="text-[10px] tracking-wide3 text-pb-faint uppercase">W · L · D</p>
            <p className="text-pb-text text-lg tabular-nums">
              {row.won} · {row.lost} · {row.drawn}
            </p>
          </div>
          <div className="text-right">
            <p className="text-[10px] tracking-wide3 text-pb-faint uppercase">Win rate</p>
            <p className="text-lg"><WinPct value={row.win_pct} /></p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        {[
          ['Runs', row.runs],
          ['Wickets', row.wickets],
          ['Catches', row.catches],
          ['Stumpings', row.stumpings],
        ].map(([label, value]) => (
          <div key={label} className="bg-pb-surface2 rounded px-3 py-2">
            <p className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">{label}</p>
            <p className="font-mono text-pb-text text-[15px] tabular-nums">{fmt(value)}</p>
          </div>
        ))}
      </div>

      {held.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[420px]">
            <thead>
              <tr className="text-left font-mono text-[10px] tracking-wide3 text-pb-faint uppercase">
                <th className="py-2 pr-3 font-normal">Grade</th>
                <th className="py-2 px-2 font-normal text-right">Played</th>
                <th className="py-2 px-2 font-normal text-right">W</th>
                <th className="py-2 px-2 font-normal text-right">L</th>
                <th className="py-2 px-2 font-normal text-right">D</th>
                <th className="py-2 pl-2 font-normal text-right">Win rate</th>
              </tr>
            </thead>
            <tbody>
              {held.map(g => (
                <tr key={`${row.competition_id}-${g.grade_name}`} className="pb-hairline-t">
                  <td className="py-2 pr-3 text-pb-text">
                    {g.grade_name}
                    {g.seasons > 1 && (
                      <span className="text-pb-faint text-xs ml-2">
                        {g.seasons} seasons
                      </span>
                    )}
                  </td>
                  <td className="py-2 px-2 text-right font-mono tabular-nums text-pb-dim">{g.matches}</td>
                  <td className="py-2 px-2 text-right font-mono tabular-nums text-pb-dim">{g.won}</td>
                  <td className="py-2 px-2 text-right font-mono tabular-nums text-pb-dim">{g.lost}</td>
                  <td className="py-2 px-2 text-right font-mono tabular-nums text-pb-dim">{g.drawn}</td>
                  <td className="py-2 pl-2 text-right font-mono"><WinPct value={g.win_pct} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

export default function CompetitionsPage() {
  const { clubSlug } = useParams()
  const { club, orgId, inactive, notFound, locked, unlock, requestAccess } = useClub(clubSlug)
  useClubTheme(club)
  usePageMeta({
    title: club?.name ? `${club.name} Competitions — BetterCricket` : null,
    description: club?.name
      ? `How ${club.name} has gone in each competition it plays, and every grade under it.`
      : null,
    image: club?.logo_url || null,
  })

  const {
    seasons, selectedSeason, setSelectedSeason, loading: clubLoading,
  } = useClubData(orgId)

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  // Opens on the whole history rather than the newest season. The question this
  // page answers is "which competitions do we play in", and a club that has
  // moved between them has most of that answer outside the current year.
  useEffect(() => {
    if (!orgId) return
    setLoading(true)
    api.orgCompetitions(orgId, selectedSeason || undefined)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [orgId, selectedSeason])

  const rows = data?.rows || []
  const grades = data?.grades || []

  // Every grade the breakdown holds, whether or not its competition has a card
  // above. Shown, never dropped: an un-grouped grade still counts in every
  // unfiltered figure, it simply has no competition to be found under.
  const ungroupedGrades = useMemo(
    () => grades.filter(g => !rows.some(r => r.competition_id === g.competition_id)),
    [rows, grades],
  )

  if (locked) return <ClubPinGate slug={clubSlug} lockInfo={locked} unlock={unlock} requestAccess={requestAccess} />
  if (inactive) return <ClubInactive slug={clubSlug} />
  if (notFound) return <ClubInactive variant="notfound" slug={clubSlug} />
  if (clubLoading) return <PbSpinner message="Loading club data…" />

  const seasonLabel = seasons?.find(s => s.id === selectedSeason)?.name || 'ALL SEASONS'

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1300px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow={`BY COMPETITION · ${seasonLabel.toUpperCase()}`}
          title="Competitions."
          meta={[
            <span key="c">
              {rows.length > 0
                ? `${rows.length} competition${rows.length === 1 ? '' : 's'} · ${fmt(data?.total_matches)} matches`
                : 'Every competition the club has played in.'}
            </span>,
          ]}
        />

        <div className="mb-5">
          {/* Season only. The page IS the grade and competition breakdown, so a
              grade picker above it would be filtering the answer out. */}
          <SeasonSelector
            seasons={seasons}
            grades={[]}
            selectedSeason={selectedSeason}
            setSelectedSeason={setSelectedSeason}
            showCategoryFilter={false}
            showGenderFilter={false}
            showFinalsFilter={false}
            showCaptainFilter={false}
          />
        </div>

        {loading ? (
          <PbSpinner />
        ) : rows.length === 0 ? (
          <p className="text-pb-faint text-sm py-8 text-center">
            No competitions recorded for this selection yet.
          </p>
        ) : (
          <>
            {rows.map(row => (
              <CompetitionCard
                key={row.competition_id || 'ungrouped'}
                row={row}
                grades={grades}
              />
            ))}
            {ungroupedGrades.length > 0 && (
              <Card className="p-4 sm:p-5">
                <h2 className="text-pb-text font-semibold text-[17px] mb-1">Other grades</h2>
                <p className="text-pb-faint text-xs mb-3">
                  Not in a competition yet. These still count in every unfiltered
                  figure.
                </p>
                <ul className="text-sm text-pb-dim space-y-1">
                  {ungroupedGrades.map(g => (
                    <li key={g.grade_name}>
                      {g.grade_name} <span className="text-pb-faint">· {g.matches} matches</span>
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </>
        )}
      </main>
    </div>
  )
}
