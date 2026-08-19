// BetterFootball — team lists.
//
// The side PlayHQ returned with each game. The match page already shows one
// game's list; this is the browse view — every recent game with whether a team
// list came through, so a club can see at a glance where its records have gaps.
//
// Post-game only: a game reaches us once PlayHQ marks it FINAL, so a scheduled
// match isn't listed at all rather than shown as a side nobody named.
import { useEffect, useState } from 'react'
import { Link, useOutletContext, useParams } from 'react-router-dom'
import { aflApi, mediaUrl } from '../aflApi'
import { SectionTitle } from '../components/bits'

const fmtDate = (d) => (d ? new Date(d).toLocaleDateString('en-AU',
  { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }) : '')

function Side({ team }) {
  return (
    <div className="flex-1 min-w-[240px]">
      <div className="flex items-center gap-2 mb-2">
        {team.logo_url
          ? <img src={mediaUrl(team.logo_url)} alt="" className="w-6 h-6 object-contain" />
          : null}
        <div className="font-display font-bold text-sm truncate">{team.name || '—'}</div>
        {team.is_ours && (
          <span className="font-mono text-[9px] px-1 rounded border pb-hairline text-pb-faint">US</span>
        )}
      </div>
      {team.players.length === 0 ? (
        <div className="text-[12.5px] text-pb-faint">No team list.</div>
      ) : (
        <ul className="text-[13px] space-y-0.5">
          {team.players.map((p, i) => (
            <li key={`${p.name}-${p.jumper_number}-${i}`} className="flex items-center gap-1.5">
              <span className="pb-num text-pb-faint w-6 text-right">{p.jumper_number || ''}</span>
              {p.player_id
                ? <Link to={`../players/${p.player_id}`} className="hover:text-pb-accent">{p.name}</Link>
                : <span>{p.name}</span>}
              {p.is_captain && (
                <span className="font-mono text-[9px] border pb-hairline rounded px-1 text-pb-faint">C</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function TeamLists() {
  const { clubSlug } = useParams()
  const { club } = useOutletContext()
  const orgId = club?.id
  const [games, setGames] = useState(null)
  const [openId, setOpenId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!orgId) return
    aflApi.aflLineupGames(orgId, { limit: 30 })
      .then((d) => setGames(d.games || []))
      .catch((e) => setError(e.message))
  }, [orgId])

  useEffect(() => {
    if (!openId || !orgId) { setDetail(null); return }
    let alive = true
    setDetail(null)
    aflApi.aflGameLineups(openId, orgId)
      .then((d) => { if (alive) setDetail(d) })
      .catch((e) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [openId, orgId])

  if (error) return <div className="text-pb-red text-sm">{error}</div>
  if (!games) return <div className="text-pb-faint text-sm">Loading team lists…</div>

  return (
    <div className="space-y-4">
      <SectionTitle>Team lists</SectionTitle>
      {games.length === 0 && (
        <div className="pb-card px-4 py-6 text-center text-sm text-pb-faint">
          No games yet.
        </div>
      )}
      <div className="space-y-2">
        {games.map((g) => {
          const open = openId === g.id
          return (
            <div key={g.id} className="pb-card overflow-hidden">
              <button onClick={() => setOpenId(open ? null : g.id)}
                className="w-full flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 text-left">
                <div className="min-w-0 flex-1">
                  <div className="font-medium text-sm truncate">
                    {g.home_team} v {g.away_team}
                  </div>
                  <div className="text-[12px] text-pb-faint">
                    {[g.round, fmtDate(g.date), g.grade].filter(Boolean).join(' · ')}
                  </div>
                </div>
                {g.named > 0 ? (
                  <span className="font-mono text-[11px] text-pb-faint">{g.named} named</span>
                ) : (
                  // `published` is PlayHQ's own flag: false means the club
                  // genuinely never named a side, null means it never told us
                  // either way. Saying so beats one vague "no team list".
                  <span className="font-mono text-[11px] text-pb-faint">
                    {g.published === false ? 'not published' : 'no team list'}
                  </span>
                )}
                <span className="text-pb-faintest text-xs">{open ? '▾' : '▸'}</span>
              </button>
              {open && (
                <div className="px-4 pb-4 border-t pb-hairline pt-3">
                  {!detail ? (
                    <div className="text-[12.5px] text-pb-faint">Loading…</div>
                  ) : (
                    <div className="flex flex-wrap gap-6">
                      {detail.teams.map((t) => <Side key={t.side} team={t} />)}
                    </div>
                  )}
                  <div className="mt-3">
                    <Link to={`/${clubSlug}/games/${g.id}`}
                      className="text-[12.5px] text-pb-accent hover:underline">
                      Full match →
                    </Link>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
