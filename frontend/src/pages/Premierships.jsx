import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useClub } from '../hooks/useClub'
import { useClubTheme } from '../hooks/useClubTheme'
import { api } from '../lib/api'
import ClubInactive from './ClubInactive'
import ClubPinGate from './ClubPinGate'
import { Label, PageHeader, PbSpinner } from '../lib/presskit'
import { useNameFormat } from '../lib/nameFormat'
import { useSectionNames } from '../lib/sectionNames'
import { useAuth } from '../contexts/AuthContext'
import { CAP } from '../lib/capabilities'

// Every flag the club has recorded, as the squad that won it — read out of the
// Premiership awards already sitting on players' profiles, so a club that has
// filled in its honour roll gets this for nothing.
//
// A card is one (season, team, competition). The competition is the card's own
// title and is never repeated under each name: every player on the card
// already means "was in the side that won this". What sits under a name is a
// genuine part in the win — Captain, Player of the Match, 12th Man.
// Cricket's twin of the football page; both read the same backend service.

// A photo where the club holds one, the club crest where it doesn't, so a
// squad never renders as a column of blank circles. Same pattern the Lineups
// page uses, and the same reason: a hotlinked photo can 404 at any time.
function Avatar({ photoUrl, logoUrl, name, size = 26 }) {
  const [failed, setFailed] = useState(false)
  if (photoUrl && !failed) {
    return (
      <img src={photoUrl} alt="" onError={() => setFailed(true)}
           className="shrink-0 rounded-full object-cover bg-pb-surface2"
           style={{ width: size, height: size }} />
    )
  }
  const initials = (name || '?').replace(/,/g, ' ').trim().split(/\s+/)
    .slice(0, 2).map(w => w[0]).join('').toUpperCase()
  if (logoUrl) {
    return <img src={logoUrl} alt="" className="shrink-0 rounded-full object-contain bg-pb-surface2"
                style={{ width: size, height: size }} />
  }
  return (
    <span className="shrink-0 rounded-full grid place-items-center font-semibold"
          style={{ width: size, height: size, fontSize: Math.round(size * 0.38),
                   background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)',
                   color: 'var(--pb-accent)' }}>
      {initials}
    </span>
  )
}

function PlayerLine({ player, logoUrl, fmt }) {
  const name = fmt(player.name)
  const extra = [...player.roles, player.detail].filter(Boolean).join(' · ')
  const body = (
    <>
      <Avatar photoUrl={player.photo_url} logoUrl={logoUrl} name={player.name} />
      {/* min-w-0 + truncate: a long name is cut with an ellipsis rather than
          wrapping onto a second line and breaking the grid's rhythm. The
          title attribute keeps the whole name reachable. */}
      <span className="min-w-0 flex-1">
        <span className="block truncate" title={player.name}>{name}</span>
        {extra && (
          <span className="block truncate font-mono text-[10px] tracking-wide2 uppercase"
                title={extra} style={{ color: 'var(--pb-accent)' }}>{extra}</span>
        )}
      </span>
    </>
  )
  const cls = 'flex items-center gap-2 min-w-0 py-0.5'
  return (
    <li className="min-w-0">
      {player.player_id
        ? <Link to={`/players/${player.player_id}`}
                className={`${cls} text-pb-text hover:text-pb-accent transition-colors`}>{body}</Link>
        : <span className={`${cls} text-pb-text`}>{body}</span>}
    </li>
  )
}

// 2026-03-14 -> 14 Mar 2026. Built from the parts, so a date never shifts with the viewer's timezone.
function fmtDay(iso) {
  const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number)
  if (!y || !m || !d) return ''
  return `${d} ${['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][m - 1]} ${y}`
}

// What an admin can mark on a player of a card. A 12th or 13th man did not play: the mark alone puts them on it.
const ROLES = ['Player of the Match', '12th Man', '13th Man']

// Edits one premiership card in place: who is on it and what each person did. Only for a card linked to a
// scorecard; a flag typed in by hand is edited from Admin, Awards. Every change is saved as it is made.
function SquadEditor({ card, orgId, fmt, onChanged }) {
  const [roster, setRoster] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [pick, setPick] = useState('')
  const [pickRole, setPickRole] = useState('')

  useEffect(() => {
    let live = true
    api.listPlayers(orgId).then(r => { if (live) setRoster(r || []) }).catch(() => { if (live) setRoster([]) })
    return () => { live = false }
  }, [orgId])

  const send = async (body) => {
    setBusy(true); setError(null)
    try {
      await api.editPremiershipSquad(orgId, { game_id: card.game_id, ...body })
      await onChanged()
    } catch (e) {
      setError(e.message || 'That change could not be saved')
    } finally {
      setBusy(false)
    }
  }

  const onCard = new Set(card.players.map(p => p.player_id).filter(Boolean))
  const candidates = (roster || []).filter(p => !onCard.has(p.id))
    .sort((a, b) => String(a.name || '').localeCompare(String(b.name || '')))
  const has = (pl, role) => (pl.roles || []).some(r => r.trim().toLowerCase() === role.toLowerCase())

  return (
    <div className="px-4 sm:px-5 py-4 pb-hairline-t bg-pb-surface2/30" data-testid="squad-editor">
      <ul className="grid gap-y-2">
        {card.players.map(pl => (
          <li key={pl.player_id || pl.name} className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="min-w-0 flex-1 basis-40 truncate text-[13px]" title={pl.name}>{fmt(pl.name)}</span>
            <span className="flex flex-wrap gap-1.5">
              {ROLES.map(role => {
                const on = has(pl, role)
                return (
                  <button key={role} type="button" disabled={busy || !pl.player_id} aria-pressed={on}
                          onClick={() => send({ action: 'role', player_id: pl.player_id, role, on: !on })}
                          className="px-2 py-0.5 rounded font-mono text-[10px] tracking-wide2 border pb-hairline disabled:opacity-50"
                          style={on ? { background: 'var(--pb-accent)', color: 'var(--pb-bg)', borderColor: 'var(--pb-accent)' } : undefined}>
                    {role}
                  </button>
                )
              })}
              <button type="button" disabled={busy || !pl.player_id}
                      onClick={() => { if (window.confirm(`Take ${fmt(pl.name)} off this premiership?`)) send({ action: 'remove', player_id: pl.player_id }) }}
                      className="px-2 py-0.5 rounded font-mono text-[10px] text-pb-red/80 hover:text-pb-red disabled:opacity-50"
                      aria-label={`Remove ${pl.name}`}>
                Remove
              </button>
            </span>
          </li>
        ))}
      </ul>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <select value={pick} onChange={e => setPick(e.target.value)} aria-label="Player to add"
                className="min-w-0 max-w-full bg-pb-surface2 pb-hairline rounded px-3 py-1.5 text-sm text-pb-text">
          <option value="">{roster === null ? 'Loading players…' : 'Add a player…'}</option>
          {candidates.map(p => <option key={p.id} value={p.id}>{fmt(p.name)}</option>)}
        </select>
        <select value={pickRole} onChange={e => setPickRole(e.target.value)} aria-label="Their part"
                className="bg-pb-surface2 pb-hairline rounded px-3 py-1.5 text-sm text-pb-text">
          <option value="">Played</option>
          <option value="12th Man">12th Man</option>
          <option value="13th Man">13th Man</option>
        </select>
        <button type="button" disabled={busy || !pick}
                onClick={async () => { await send({ action: 'add', player_id: pick, role: pickRole || null }); setPick(''); setPickRole('') }}
                className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50"
                style={{ background: 'var(--pb-accent)' }}>
          Add
        </button>
      </div>
      {error && <p className="mt-2 text-[12px] text-pb-red" role="alert">{error}</p>}
    </div>
  )
}

export default function Premierships() {
  const { clubSlug } = useParams()
  const sec = useSectionNames(clubSlug)
  const { club, orgId, inactive, notFound, locked, unlock, requestAccess } = useClub(clubSlug)
  useClubTheme(club)
  const fmt = useNameFormat(club)

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [team, setTeam] = useState(null)
  const { hasCapability } = useAuth()
  const canEdit = hasCapability(CAP.MANAGE_AWARDS)
  const [editing, setEditing] = useState(null)   // the game id of the card being edited

  const reload = () => api.getPremierships(orgId).then(setData).catch(() => {})

  useEffect(() => {
    if (!orgId) return
    setLoading(true)
    api.getPremierships(orgId)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [orgId])

  if (locked) return <ClubPinGate slug={clubSlug} lockInfo={locked} unlock={unlock} requestAccess={requestAccess} />
  if (inactive) return <ClubInactive slug={clubSlug} />
  if (notFound) return <ClubInactive variant="notfound" slug={clubSlug} />

  const all = data?.premierships || []
  const teams = [...new Set(all.map(p => p.team).filter(Boolean))]
  const shown = team ? all.filter(p => p.team === team) : all
  const players = shown.reduce((a, p) => a + p.player_count, 0)

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text">
      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6 sm:py-8">
        <PageHeader
          eyebrow={sec.renamed('premierships') ? (club?.name?.toUpperCase() || '') : `PREMIERSHIPS · ${club?.name?.toUpperCase() || ''}`}
          title={sec.name('premierships', "Flags on the wall.")}
          meta={[<span key="x">Every premiership side the club has recorded.</span>]}
        />

        {loading && !data ? <PbSpinner message="Loading premierships…" /> : all.length === 0 ? (
          <div className="pb-card p-6 text-sm text-pb-dim">
            No premierships recorded yet. A grand final the club wins is added here by
            itself once its scorecard has synced. Older flags come from the Premiership
            awards on each player's profile: add them under Admin → Awards, or bring a
            whole honour roll in at once with the awards import.
          </div>
        ) : (
          <>
            <div className="mb-5 flex flex-wrap gap-3 items-center">
              {teams.length > 1 && (
                <select
                  value={team || ''}
                  onChange={e => setTeam(e.target.value || null)}
                  className="bg-pb-surface2 pb-hairline rounded px-3 py-1.5 text-sm text-pb-text"
                >
                  <option value="">All teams</option>
                  {teams.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              )}
              <Label>
                {shown.length} flag{shown.length === 1 ? '' : 's'} · {players} player{players === 1 ? '' : 's'}
              </Label>
            </div>

            <div className="space-y-4">
              {shown.map(p => (
                <div key={`${p.season}|${p.team}|${p.competition}`} className="pb-card overflow-hidden">
                  <div className="px-4 sm:px-5 py-3 pb-hairline-b bg-pb-surface2/40 flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <Label style={{ color: 'var(--pb-accent)' }}>
                      {[p.season || 'Season not recorded', p.team].filter(Boolean).join(' · ')}
                    </Label>
                    {/* The competition the flag was won in — the card's own
                        title, which is why it is not repeated under every
                        name below. */}
                    {p.competition && (
                      <span className="min-w-0 truncate text-[13px] text-pb-dim" title={p.competition}>
                        {p.competition}
                      </span>
                    )}
                    {/* The grand final itself, where the club's scorecards hold it. A flag typed in
                        by hand with no match to a game just has no line. */}
                    {p.game && p.game.opponent && (
                      <span className="min-w-0 truncate text-[12px] text-pb-faint"
                            title={`v ${p.game.opponent}`}>
                        v {p.game.opponent}{p.game.played_at ? ` · ${fmtDay(p.game.played_at)}` : ''}
                      </span>
                    )}
                    <span className="sm:ml-auto flex items-baseline gap-3 font-mono text-[11px] text-pb-faint whitespace-nowrap">
                      {canEdit && p.game_id && (
                        <button type="button" onClick={() => setEditing(editing === p.game_id ? null : p.game_id)}
                                aria-expanded={editing === p.game_id} className="hover:underline"
                                style={{ color: 'var(--pb-accent)' }}>
                          {editing === p.game_id ? 'Done' : 'Edit squad'}
                        </button>
                      )}
                      {p.game_id && (
                        <Link to={`/games/${p.game_id}?org=${orgId}`}
                              className="hover:underline" style={{ color: 'var(--pb-accent)' }}>
                          Scorecard →
                        </Link>
                      )}
                      <span>{p.player_count} player{p.player_count === 1 ? '' : 's'}</span>
                    </span>
                  </div>
                  {editing === p.game_id && p.game_id
                    ? <SquadEditor card={p} orgId={orgId} fmt={fmt} onChanged={reload} />
                    : (
                  <ul className="px-4 sm:px-5 py-4 grid gap-x-6 gap-y-1.5 text-[13px] sm:grid-cols-2 lg:grid-cols-3">
                    {p.players.map(pl => (
                      <PlayerLine key={pl.player_id || pl.name} player={pl}
                                  logoUrl={club?.logo_url} fmt={fmt} />
                    ))}
                  </ul>
                    )}
                </div>
              ))}
            </div>
          </>
        )}
      </main>
    </div>
  )
}
