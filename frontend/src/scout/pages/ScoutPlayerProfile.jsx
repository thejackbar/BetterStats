import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { scoutApi } from '../lib/scoutApi'
import { WINDOW_OPTIONS, rollupSeasons } from '../lib/seasonRollup'
import ScoutModuleLayout from '../ScoutModuleLayout'
import { PlayerAvatar } from '../components/ScoutUi'
import { Btn, Icon, Search, Segmented } from '../../pages/admin/betterselect/ui'
import { bowlingLabel, bowlingFromLabel, BOWLING_OPTS, ROLE_OPTS, BAT_HANDS, REGION_OPTS } from '../lib/watchlistOptions'
import ScoutingCard from '../../pages/admin/betteriq/ScoutingCard'
import '../../pages/admin/betteriq/iq-theme.css'

const TABS = ['batting', 'bowling', 'fielding', 'career']

const RECRUITING_FIELDS = [
  ['visa_status', 'Visa / eligibility'],
  ['transfer_preference', 'Transfer preference'],
  ['availability_window', 'Availability'],
  ['fee_expectations', 'Fee expectations'],
  ['agent_contact', 'Agent / contact'],
]

const NOTE_KINDS = [
  ['watched_live', 'Watched live'],
  ['phone', 'Phone'],
  ['scorecard_review', 'Scorecard review'],
  ['other', 'Other'],
]

const inputCls = 'w-full bg-pb-surface2 border border-pb-hairline rounded px-2 py-1.5 text-sm'

function Stat({ label, value, accent }) {
  return (
    <div>
      <div className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faint">{label}</div>
      <div className="font-mono text-[21px] font-bold mt-0.5" style={accent ? { color: 'var(--pb-accent)' } : undefined}>{value ?? '—'}</div>
    </div>
  )
}

export default function ScoutPlayerProfile() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [player, setPlayer] = useState(undefined)
  const [error, setError] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [removing, setRemoving] = useState(false)
  const [activeTab, setActiveTab] = useState('batting')
  const [windowN, setWindowN] = useState(null)
  const [notes, setNotes] = useState([])
  const [selectedCardId, setSelectedCardId] = useState(null)
  const [mergeOpen, setMergeOpen] = useState(false)
  const fileRef = useRef(null)

  const load = () => {
    scoutApi.getPlayer(id, searchParams.get('q')).then((p) => {
      setPlayer(p)
      if (p.cards?.length) setSelectedCardId((cur) => cur && p.cards.some((c) => c.id === cur) ? cur : p.cards[0].id)
      const bat = p.stats?.totals
      if (bat && (bat.wickets || 0) > (bat.runs || 0) / 20) setActiveTab('bowling')
    }).catch((err) => setError(err.message))
  }
  useEffect(() => { load() }, [id])
  useEffect(() => { scoutApi.listNotes(id).then(setNotes).catch(() => {}) }, [id])

  const refresh = async () => {
    setRefreshing(true)
    setError(null)
    try {
      await scoutApi.refreshPlayer(id)
      setTimeout(load, 2500)
    } catch (err) {
      setError(err.message)
    } finally {
      setRefreshing(false)
    }
  }

  const removeEverywhere = async () => {
    if (!player) return
    if (!window.confirm(`Remove ${player.name} from My Players? This removes them from every one of your boards.`)) return
    setRemoving(true)
    setError(null)
    try {
      await scoutApi.removePlayerEverywhere(id)
      navigate('/betterscout/app/players')
    } catch (err) {
      setError(err.message)
      setRemoving(false)
    }
  }

  const uploadPhoto = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      await scoutApi.uploadPlayerPhoto(id, file)
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  const selectedCard = player?.cards?.find((c) => c.id === selectedCardId)

  const seasons = player?.stats?.seasons || []
  const latestActiveYear = useMemo(() => {
    let max = null
    for (const s of seasons) if (s.matches > 0 && (max === null || s.year > max)) max = s.year
    return max
  }, [seasons])
  const cutoffYear = windowN != null && latestActiveYear ? latestActiveYear - (windowN - 1) : null
  const windowedSeasons = cutoffYear != null ? seasons.filter((s) => s.year >= cutoffYear) : seasons
  const totals = useMemo(() => rollupSeasons(windowedSeasons), [windowedSeasons])

  const moveStage = async (columnId) => {
    if (!selectedCard) return
    const prevBoard = player.cards
    setPlayer((p) => ({ ...p, cards: p.cards.map((c) => c.id === selectedCard.id ? { ...c, column_id: columnId } : c) }))
    try {
      await scoutApi.moveCard(selectedCard.id, columnId, 0)
      load()
    } catch (err) {
      setError(err.message)
      setPlayer((p) => ({ ...p, cards: prevBoard }))
    }
  }

  if (error && player === undefined) {
    return <ScoutModuleLayout title="Player"><p className="text-sm text-pb-red">{error}</p></ScoutModuleLayout>
  }
  if (player === undefined) {
    return <ScoutModuleLayout title="Player"><p className="text-sm text-pb-dim">Loading…</p></ScoutModuleLayout>
  }

  return (
    <ScoutModuleLayout
      title={player.name}
      caption={[player.club_name, player.grade_name].filter(Boolean).join(' · ') || 'No club recorded'}
      actions={
        <div className="flex items-center gap-2">
          {player.source === 'au_grassroots' && (
            <Btn variant="ghost" sm onClick={refresh} disabled={refreshing}>{refreshing ? 'Refreshing…' : 'Refresh stats'}</Btn>
          )}
          <Btn variant="ghost" sm onClick={() => navigator.clipboard?.writeText(window.location.href)}>Share profile</Btn>
          <Btn variant="primary" sm onClick={() => navigate(`/betterscout/app/compare?players=${player.id}`)}>Compare</Btn>
          <Btn variant="ghost" sm onClick={() => setMergeOpen(true)}>Merge duplicate…</Btn>
          <Btn variant="ghost" sm onClick={removeEverywhere} disabled={removing} className="text-pb-red">
            {removing ? 'Removing…' : 'Remove from My Players'}
          </Btn>
        </div>
      }
    >
      <div className="space-y-5 max-w-[1200px]">
        <Link to="/betterscout/app/players" className="text-sm text-pb-faint hover:text-pb-text">← My players</Link>
        {error && <p className="text-sm text-pb-red">{error}</p>}

        <div className="flex items-start gap-4 flex-wrap">
          <button onClick={() => fileRef.current?.click()}
            className="w-[76px] h-[92px] shrink-0 rounded-lg border border-dashed border-pb-hairline2 flex flex-col items-center justify-center gap-1.5 bg-pb-surface hover:border-pb-faint">
            <PlayerAvatar name={player.name} photoUrl={player.photo_url} size={44} dashed />
            <span className="font-mono text-[7.5px] text-pb-faintest text-center leading-tight px-1">
              {player.photo_url ? 'Change photo' : 'Drop photo or paste URL'}
            </span>
          </button>
          <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={uploadPhoto} />

          <div className="flex-1 min-w-0 space-y-2">
            {selectedCard && (
              <div className="flex flex-wrap gap-1.5">
                {[
                  selectedCard.role,
                  (BAT_HANDS.find(([c]) => c === selectedCard.batting_hand) || [])[1],
                  bowlingLabel(selectedCard.bowling_action, selectedCard.bowling_type),
                  selectedCard.region,
                  selectedCard.is_opening_batsman ? 'Opening bat' : null,
                  selectedCard.is_wicket_keeper ? 'Wicketkeeper' : null,
                  selectedCard.fielding_position ? `Fields at ${selectedCard.fielding_position}` : null,
                ]
                  .filter((v) => v && v !== 'None' && v !== '—')
                  .map((v, i) => <span key={i} className="text-xs px-2 py-0.5 rounded-full bg-pb-surface2 text-pb-dim">{v}</span>)}
                {(selectedCard.tags || []).map((t) => (
                  <span key={t} className="text-xs px-2 py-0.5 rounded-full border border-pb-accent/40 text-pb-accent">{t}</span>
                ))}
              </div>
            )}

            {player.cards?.length > 0 && (
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  {player.cards.length > 1 && (
                    <select value={selectedCardId} onChange={(e) => setSelectedCardId(e.target.value)}
                      className="font-mono text-[10px] uppercase tracking-wide2 bg-pb-surface2 border border-pb-hairline rounded px-1.5 py-1 text-pb-faint">
                      {player.cards.map((c) => <option key={c.id} value={c.id}>{c.watchlist_name}</option>)}
                    </select>
                  )}
                  {player.cards.length === 1 && (
                    <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">{selectedCard?.watchlist_name} stage</span>
                  )}
                </div>
                {selectedCard && <StageControl card={selectedCard} onMove={moveStage} />}
              </div>
            )}
          </div>
        </div>

        {player.source === 'au_grassroots' && (
          <ClubsSection player={player} onChanged={load} setError={setError} />
        )}

        {!totals.matches && !totals.wickets ? (
          <p className="text-sm text-pb-dim">
            {player.source === 'manual' ? 'No automated stats — manually added.' : 'No stats available yet.'}
          </p>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_356px] gap-5">
            <div className="space-y-5">
              <div className="pb-card p-4 space-y-4">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex gap-4">
                    {TABS.map((t) => (
                      <button key={t} onClick={() => setActiveTab(t)}
                        className="font-mono text-[11px] uppercase tracking-wide2 pb-1.5 border-b-2 transition-colors"
                        style={{ borderColor: activeTab === t ? 'var(--pb-accent)' : 'transparent', color: activeTab === t ? 'var(--pb-accent)' : 'var(--pb-faint)' }}>
                        {t}
                      </button>
                    ))}
                  </div>
                  <Segmented
                    options={WINDOW_OPTIONS.map((o) => ({ value: o.n ?? 'full', label: o.label.replace('Last ', '').replace(' seasons', ' SEASONS').replace(' season', ' SEASON').toUpperCase() }))}
                    value={windowN ?? 'full'} onChange={(v) => setWindowN(v === 'full' ? null : v)} sm
                  />
                </div>

                <DisciplineGrid tab={activeTab} totals={totals} />

                <SeasonChart seasons={seasons} activeYears={cutoffYear != null ? new Set(Array.from({ length: latestActiveYear - cutoffYear + 1 }, (_, i) => cutoffYear + i)) : null} />

                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-pb-hairline font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faintest">
                        <th className="text-left px-2 py-1.5">Season</th>
                        <th className="text-left px-2 py-1.5">Grade</th>
                        <th className="text-right px-2 py-1.5">Mat</th>
                        <th className="text-right px-2 py-1.5">Runs</th>
                        <th className="text-right px-2 py-1.5">Avg</th>
                        <th className="text-right px-2 py-1.5">SR</th>
                        <th className="text-right px-2 py-1.5">HS</th>
                        <th className="text-right px-2 py-1.5">Wkts</th>
                        <th className="text-right px-2 py-1.5">Econ</th>
                      </tr>
                    </thead>
                    <tbody>
                      {seasons.map((s) => (
                        <tr key={s.year} className="border-b border-pb-hairline last:border-0">
                          <td className="px-2 py-1.5 font-mono">{s.year}</td>
                          <td className="px-2 py-1.5">{s.grade || '—'}</td>
                          <td className="px-2 py-1.5 text-right font-mono">{s.matches}</td>
                          <td className="px-2 py-1.5 text-right font-mono">{s.runs}</td>
                          <td className="px-2 py-1.5 text-right font-mono">{s.average ?? '—'}</td>
                          <td className="px-2 py-1.5 text-right font-mono">{s.strike_rate ?? '—'}</td>
                          <td className="px-2 py-1.5 text-right font-mono">{s.high_score ?? '—'}</td>
                          <td className="px-2 py-1.5 text-right font-mono">{s.wickets}</td>
                          <td className="px-2 py-1.5 text-right font-mono">{s.economy ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <div className="space-y-5">
              {selectedCard && <AttributesPanel card={selectedCard} onSaved={load} />}
              {selectedCard && <RecruitingPanel card={selectedCard} onSaved={load} />}
              <NotesPanel playerId={id} notes={notes} onChange={setNotes} />
              {player.cards?.length > 0 && (
                <div className="pb-card p-4 space-y-2">
                  <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">On watchlists</div>
                  {player.cards.map((c) => (
                    <div key={c.id} className="flex items-center justify-between text-sm py-1">
                      <span>{c.watchlist_name}</span>
                      <span className="font-mono text-[9.5px] uppercase px-1.5 py-0.5 rounded"
                        style={c.id === selectedCardId ? { background: 'color-mix(in srgb, var(--pb-accent) 15%, transparent)', color: 'var(--pb-accent)' } : { background: 'var(--pb-surface2)', color: 'var(--pb-faint)' }}>
                        {c.column_name}
                      </span>
                    </div>
                  ))}
                  <Link to="/betterscout/app/watchlists" className="text-xs text-pb-faint hover:text-pb-text underline block pt-1">+ Add to another watchlist</Link>
                </div>
              )}
            </div>
          </div>
        )}

        {selectedCard && (
          <ScoutingCard
            keyId={selectedCard.id}
            batting={selectedCard.batting_intel}
            bowling={selectedCard.bowling_intel}
            defaultSide={(totals.wickets || 0) > (totals.runs || 0) / 20 ? 'bowl' : 'bat'}
            onSave={async (body) => { await scoutApi.updateCard(selectedCard.id, body); load() }}
          />
        )}
      </div>

      {mergeOpen && (
        <MergeDuplicateModal
          keepId={player.id} keepName={player.name}
          onMerged={load} onClose={() => setMergeOpen(false)}
        />
      )}
    </ScoutModuleLayout>
  )
}

// Two tracked profiles that turn out to be the same real person — e.g.
// added from two clubs whose own CA feeds minted different participant ids
// for them. The keep side is always THIS profile; pick which other tracked
// profile is the duplicate and its clubs/notes/tracking fold in (see
// scout_discovery.merge_scouted_players).
function MergeDuplicateModal({ keepId, keepName, onMerged, onClose }) {
  const [query, setQuery] = useState('')
  const [players, setPlayers] = useState(null)
  const [merging, setMerging] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => { scoutApi.listPlayers().then(setPlayers).catch(() => setPlayers([])) }, [])

  const q = query.trim().toLowerCase()
  const candidates = (players || [])
    .filter((p) => p.id !== keepId)
    .filter((p) => !q || p.name.toLowerCase().includes(q))

  const doMerge = async (other) => {
    if (!window.confirm(
      `Merge "${other.name}"'s profile into "${keepName}"? Their clubs, scouting notes and watchlist tracking move onto this profile, and the "${other.name}" profile is deleted. This can't be undone.`
    )) return
    setMerging(true)
    setError(null)
    try {
      await scoutApi.mergePlayers(keepId, other.id)
      onMerged()
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setMerging(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="pb-card w-full max-w-md p-4 space-y-3" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <div className="font-display font-bold text-sm">Merge a duplicate into {keepName}</div>
          <button onClick={onClose} className="text-pb-faint hover:text-pb-text"><Icon name="close" size={16} /></button>
        </div>
        <p className="text-xs text-pb-faint">
          Pick the other tracked profile that's really this same person. Their clubs, notes and board tracking move here; theirs is deleted.
        </p>
        <Search value={query} onChange={setQuery} placeholder="Search your tracked players…" className="w-full" />
        {error && <p className="text-xs text-pb-red">{error}</p>}
        <div className="max-h-64 overflow-y-auto divide-y divide-pb-hairline border border-pb-hairline rounded-lg">
          {players === null && <p className="px-3 py-2 text-xs text-pb-faint">Loading…</p>}
          {players !== null && candidates.length === 0 && <p className="px-3 py-2 text-xs text-pb-faint">No match.</p>}
          {candidates.map((p) => (
            <button key={p.id} onClick={() => doMerge(p)} disabled={merging}
              className="w-full text-left px-3 py-2 text-sm hover:bg-pb-surface2 disabled:opacity-50 flex items-center justify-between gap-2">
              <span className="truncate">{p.name}</span>
              <span className="font-mono text-[10px] text-pb-faint uppercase truncate shrink-0">{p.club_name || 'No club'}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

const OTHER_CLUB_POLL_MS = 2500
const OTHER_CLUB_MAX_POLLS = 60

// Spencer Green plays for several clubs — this is the whole cross-club
// linking UI: the clubs already confirmed for this player, name-match
// suggestions from other cached clubs (never auto-linked, always a confirm
// click), and an on-demand "search a specific club" flow.
function ClubsSection({ player, onChanged, setError }) {
  const [linkingKey, setLinkingKey] = useState(null)
  const [unlinkingId, setUnlinkingId] = useState(null)
  const [scanning, setScanning] = useState(false)
  const [dismissed, setDismissed] = useState(new Set())
  const [findOpen, setFindOpen] = useState(false)
  const [findQuery, setFindQuery] = useState('')
  const [findClubs, setFindClubs] = useState([])
  const [findSearching, setFindSearching] = useState(false)
  const [searchingClub, setSearchingClub] = useState(null) // { id, name } while polling
  const pollRef = useRef(null)
  const pollCount = useRef(0)
  const confirmPollRef = useRef(null)
  const confirmPollCount = useRef(0)

  useEffect(() => () => { clearTimeout(pollRef.current); clearTimeout(confirmPollRef.current) }, [])

  const clubs = player.clubs || []
  const candidateKey = (c) => `${c.club_org_guid}:${c.player_id || c.canonical_participant_id || ''}`
  const candidates = (player.other_club_candidates || []).filter((c) => !dismissed.has(candidateKey(c)))

  const rescan = async () => {
    setScanning(true)
    setError(null)
    try {
      await scoutApi.rescanOtherClubs(player.id)
      onChanged()
    } catch (err) {
      setError(err.message)
    } finally {
      setScanning(false)
    }
  }

  // Confirming a candidate may need to build that club's roster first (a
  // live-search-sourced candidate only names the club, not a locally
  // resolved player id — see scout_discovery.link_player_club) — same
  // build/poll contract as "Find at a club" below.
  const confirmCandidate = (c) => {
    const key = candidateKey(c)
    setLinkingKey(key)
    setError(null)
    confirmPollCount.current = 0
    pollConfirm(c, key)
  }

  const pollConfirm = (c, key) => {
    scoutApi.linkPlayerClub(player.id, {
      orgGuid: c.club_org_guid, playerId: c.player_id, canonicalParticipantId: c.canonical_participant_id,
    }).then((res) => {
      if (res.status === 'building') {
        if (++confirmPollCount.current < OTHER_CLUB_MAX_POLLS) {
          confirmPollRef.current = setTimeout(() => pollConfirm(c, key), OTHER_CLUB_POLL_MS)
        } else {
          setError("Timed out waiting for that club's roster to build.")
          setLinkingKey(null)
        }
        return
      }
      setLinkingKey(null)
      onChanged()
    }).catch((err) => { setError(err.message); setLinkingKey(null) })
  }

  const dismissCandidate = (c) => {
    setDismissed((s) => new Set(s).add(candidateKey(c)))
  }

  const unlinkClub = async (clubRow) => {
    if (!window.confirm(`Unlink ${clubRow.club_name || 'this club'} from ${player.name}?`)) return
    setUnlinkingId(clubRow.id)
    setError(null)
    try {
      await scoutApi.unlinkPlayerClub(player.id, clubRow.id)
      onChanged()
    } catch (err) {
      setError(err.message)
    } finally {
      setUnlinkingId(null)
    }
  }

  const searchFindClub = async (e) => {
    e?.preventDefault()
    if (findQuery.trim().length < 2) return
    setFindSearching(true)
    setError(null)
    try {
      setFindClubs(await scoutApi.searchClubs(findQuery.trim()))
    } catch (err) {
      setError(err.message)
    } finally {
      setFindSearching(false)
    }
  }

  const pollFindClub = (c) => {
    scoutApi.searchOtherClub(player.id, { orgGuid: c.id, clubName: c.name }).then((res) => {
      if (res.status === 'building') {
        if (++pollCount.current < OTHER_CLUB_MAX_POLLS) {
          pollRef.current = setTimeout(() => pollFindClub(c), OTHER_CLUB_POLL_MS)
        } else {
          setError('Timed out waiting for that club\'s roster to build.')
          setSearchingClub(null)
        }
        return
      }
      setSearchingClub(null)
      onChanged()
    }).catch((err) => { setError(err.message); setSearchingClub(null) })
  }

  const pickFindClub = (c) => {
    clearTimeout(pollRef.current)
    pollCount.current = 0
    setFindClubs([])
    setFindQuery('')
    setSearchingClub(c)
    pollFindClub(c)
  }

  return (
    <div className="pb-card p-4 space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Clubs</div>
        <div className="flex items-center gap-2">
          <Btn sm variant="ghost" onClick={rescan} disabled={scanning}>{scanning ? 'Scanning…' : 'Scan for other clubs'}</Btn>
          <Btn sm variant="ghost" onClick={() => setFindOpen((v) => !v)}>Find at a club…</Btn>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {clubs.map((c) => (
          <div key={c.id} className="flex items-center gap-1.5 pl-3 pr-1.5 py-1 rounded-full border border-pb-hairline2 bg-pb-surface2 text-sm">
            <span>{c.club_name || 'Unknown club'}</span>
            {c.is_primary && (
              <span className="font-mono text-[9px] uppercase tracking-wide2 px-1.5 py-0.5 rounded-full"
                style={{ background: 'color-mix(in srgb, var(--pb-accent) 18%, transparent)', color: 'var(--pb-accent)' }}>
                Primary
              </span>
            )}
            {clubs.length > 1 && (
              <button onClick={() => unlinkClub(c)} disabled={unlinkingId === c.id}
                title="Unlink this club" aria-label="Unlink this club"
                className="text-pb-faint hover:text-pb-red p-0.5 rounded-full disabled:opacity-50">
                <Icon name="close" size={12} />
              </button>
            )}
          </div>
        ))}
        {clubs.length === 0 && <p className="text-sm text-pb-faint">No club linked.</p>}
      </div>

      {candidates.length > 0 && (
        <div className="rounded-lg border border-pb-accent/30 bg-[color-mix(in_srgb,var(--pb-accent)_6%,transparent)] p-3 space-y-2">
          <div className="text-sm font-medium">
            {candidates.length} other club{candidates.length === 1 ? '' : 's'} found for {player.name}
          </div>
          <div className="space-y-1.5">
            {candidates.map((c) => {
              const key = candidateKey(c)
              // A live-search candidate (see scout_discovery.suggest_other_clubs)
              // carries no `confidence` — it's a verified PlayHQ membership, not
              // a name-similarity guess, so there's nothing to show a % for. A
              // manual "Find at a club" hit still is a guess and shows one.
              const verified = c.confidence == null
              return (
                <div key={key} className="flex items-center justify-between gap-2 text-sm">
                  <span className="min-w-0 truncate">
                    {verified
                      ? <span>Registered at <strong>{c.club_name || 'an unnamed club'}</strong></span>
                      : <span><strong>{c.name}</strong> at {c.club_name || 'an unnamed club'}
                          <span className="text-pb-faint font-mono text-[10.5px] ml-2">{Math.round(c.confidence * 100)}% match</span>
                        </span>}
                  </span>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <Btn sm variant="primary" onClick={() => confirmCandidate(c)} disabled={linkingKey === key}>
                      {linkingKey === key ? 'Linking…' : 'Confirm — same person'}
                    </Btn>
                    <Btn sm variant="ghost" onClick={() => dismissCandidate(c)}>Dismiss</Btn>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {findOpen && (
        <div className="rounded-lg border border-pb-hairline2 p-3 space-y-2">
          <form onSubmit={searchFindClub} className="flex gap-2">
            <Search value={findQuery} onChange={setFindQuery} placeholder="Search for a club this player might also play for…" className="flex-1" />
            <Btn sm variant="primary" onClick={searchFindClub} disabled={findSearching || findQuery.trim().length < 2}>
              {findSearching ? 'Searching…' : 'Search'}
            </Btn>
          </form>
          {searchingClub && (
            <p className="text-xs text-pb-dim">Checking {searchingClub.name}'s roster for a name match…</p>
          )}
          {!searchingClub && findClubs.length > 0 && (
            <div className="divide-y divide-pb-hairline border border-pb-hairline rounded-lg overflow-hidden">
              {findClubs.map((c) => (
                <button key={c.id} onClick={() => pickFindClub(c)} className="w-full text-left px-3 py-2 hover:bg-pb-surface2 text-sm">
                  {c.name}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function DisciplineGrid({ tab, totals: t }) {
  if (tab === 'bowling') {
    return (
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-4">
        <Stat label="Wickets" value={t.wickets} accent />
        <Stat label="Overs" value={t.overs} />
        <Stat label="Economy" value={t.economy} />
        <Stat label="Bowl avg" value={t.bowling_average} />
        <Stat label="Best" value={t.best} />
        <Stat label="5-fors" value={t.five_fors} />
      </div>
    )
  }
  if (tab === 'fielding') {
    return (
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-4">
        <Stat label="Catches" value={t.catches} accent />
        <Stat label="Wk catches" value={t.catches_wk} />
        <Stat label="Stumpings" value={t.stumpings} />
        <Stat label="Run outs" value={t.run_outs} />
      </div>
    )
  }
  if (tab === 'career') {
    return (
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-4">
        <Stat label="Matches" value={t.matches} accent />
        <Stat label="Runs" value={t.runs} />
        <Stat label="Wickets" value={t.wickets} />
        <Stat label="Catches" value={t.catches} />
        <Stat label="50s / 100s" value={`${t.fifties ?? 0} / ${t.hundreds ?? 0}`} />
        <Stat label="5-fors" value={t.five_fors} />
      </div>
    )
  }
  return (
    <div className="grid grid-cols-3 sm:grid-cols-6 gap-4">
      <Stat label="Innings" value={t.innings} />
      <Stat label="Runs" value={t.runs} />
      <Stat label="Average" value={t.average} accent />
      <Stat label="Strike rate" value={t.strike_rate} />
      <Stat label="High score" value={t.high_score} />
      <Stat label="50s / 100s" value={`${t.fifties ?? 0} / ${t.hundreds ?? 0}`} />
    </div>
  )
}

function SeasonChart({ seasons, activeYears }) {
  if (!seasons.length) return null
  const maxRuns = Math.max(1, ...seasons.map((s) => s.runs || 0))
  const maxWkts = Math.max(1, ...seasons.map((s) => s.wickets || 0))
  const sorted = [...seasons].sort((a, b) => a.year - b.year)
  return (
    <div>
      <div className="flex items-center gap-4 mb-2">
        <span className="flex items-center gap-1.5 text-xs text-pb-dim"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: 'var(--pb-accent)' }} />Runs</span>
        <span className="flex items-center gap-1.5 text-xs text-pb-dim"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: '#3b82f6' }} />Wickets</span>
      </div>
      <div className="flex items-end gap-[26px] overflow-x-auto pb-2" style={{ height: 120 }}>
        {sorted.map((s) => {
          const inWindow = !activeYears || activeYears.has(s.year)
          const rh = Math.max(2, Math.round(((s.runs || 0) / maxRuns) * 100))
          const wh = Math.max(2, Math.round(((s.wickets || 0) / maxWkts) * 100))
          return (
            <div key={s.year} className="flex flex-col items-center gap-1.5 shrink-0" style={{ opacity: inWindow ? 1 : 0.5 }}>
              <div className="flex items-end gap-1" style={{ height: 100 }}>
                <div style={{ width: 22, height: rh, background: 'var(--pb-accent)', borderRadius: 2 }} title={`${s.runs} runs`} />
                <div style={{ width: 22, height: wh, background: '#3b82f6', borderRadius: 2 }} title={`${s.wickets} wickets`} />
              </div>
              <div className="font-mono text-[10px]" style={{ color: inWindow ? 'var(--pb-text)' : 'var(--pb-faint)' }}>{s.year}</div>
              <div className="text-[9.5px] text-pb-faint">{s.grade || ''}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function StageControl({ card, onMove }) {
  const [board, setBoard] = useState(null)
  useEffect(() => { scoutApi.getBoard(card.watchlist_id).then(setBoard).catch(() => {}) }, [card.watchlist_id])
  if (!board) return <span className="text-xs text-pb-faint">{card.column_name}</span>
  return (
    <Segmented
      options={board.columns.map((c) => ({ value: c.id, label: c.name.toUpperCase() }))}
      value={card.column_id} onChange={onMove}
    />
  )
}

const ATTR_FIELDS = ['role', 'batting_hand', 'bowling_label', 'region', 'is_opening_batsman', 'is_wicket_keeper', 'fielding_position']

function AttributesPanel({ card, onSaved }) {
  const [form, setForm] = useState({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  useEffect(() => {
    setForm({
      role: card.role || '',
      batting_hand: card.batting_hand || '',
      bowling_label: bowlingLabel(card.bowling_action, card.bowling_type),
      region: card.region || '',
      is_opening_batsman: !!card.is_opening_batsman,
      is_wicket_keeper: !!card.is_wicket_keeper,
      fielding_position: card.fielding_position || '',
    })
  }, [card.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const dirty = form.role !== undefined && ATTR_FIELDS.some((k) => {
    if (k === 'bowling_label') return form[k] !== bowlingLabel(card.bowling_action, card.bowling_type)
    if (k === 'is_opening_batsman') return !!form[k] !== !!card.is_opening_batsman
    if (k === 'is_wicket_keeper') return !!form[k] !== !!card.is_wicket_keeper
    return (form[k] || '') !== (card[k] || '')
  })

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      const { bowling_action, bowling_type } = bowlingFromLabel(form.bowling_label)
      await scoutApi.updateCard(card.id, {
        role: form.role, batting_hand: form.batting_hand, bowling_action, bowling_type,
        region: form.region, is_opening_batsman: form.is_opening_batsman,
        is_wicket_keeper: form.is_wicket_keeper, fielding_position: form.fielding_position,
      })
      onSaved()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="pb-card p-4 space-y-3">
      <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Scouting attributes</div>
      {error && <p className="text-xs text-pb-red">{error}</p>}
      <div className="grid grid-cols-2 gap-2.5">
        <label className="block">
          <div className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faint mb-1">Role</div>
          <select value={form.role || ''} onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))} className={inputCls}>
            {ROLE_OPTS.map((r) => <option key={r} value={r}>{r || '—'}</option>)}
          </select>
        </label>
        <label className="block">
          <div className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faint mb-1">Batting hand</div>
          <select value={form.batting_hand || ''} onChange={(e) => setForm((f) => ({ ...f, batting_hand: e.target.value }))} className={inputCls}>
            {BAT_HANDS.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
          </select>
        </label>
        <label className="block col-span-2">
          <div className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faint mb-1">Bowling style</div>
          <select value={form.bowling_label || '—'} onChange={(e) => setForm((f) => ({ ...f, bowling_label: e.target.value }))} className={inputCls}>
            {BOWLING_OPTS.map(([label]) => <option key={label} value={label}>{label}</option>)}
          </select>
        </label>
        <label className="block">
          <div className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faint mb-1">Origin / region</div>
          <select value={form.region || ''} onChange={(e) => setForm((f) => ({ ...f, region: e.target.value }))} className={inputCls}>
            {REGION_OPTS.map((r) => <option key={r} value={r}>{r || '— none —'}</option>)}
          </select>
        </label>
        <label className="block">
          <div className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faint mb-1">Usual fielding position</div>
          <input value={form.fielding_position || ''} onChange={(e) => setForm((f) => ({ ...f, fielding_position: e.target.value }))} placeholder="e.g. Gully, Cover" className={inputCls} />
        </label>
      </div>
      <div className="flex items-center gap-4 pt-1">
        <label className="flex items-center gap-1.5 text-sm cursor-pointer select-none">
          <input type="checkbox" checked={!!form.is_opening_batsman} onChange={(e) => setForm((f) => ({ ...f, is_opening_batsman: e.target.checked }))} />
          Opening batsman
        </label>
        <label className="flex items-center gap-1.5 text-sm cursor-pointer select-none">
          <input type="checkbox" checked={!!form.is_wicket_keeper} onChange={(e) => setForm((f) => ({ ...f, is_wicket_keeper: e.target.checked }))} />
          Wicketkeeper
        </label>
      </div>
      {dirty && (
        <Btn variant="primary" sm onClick={save} disabled={saving} className="w-full justify-center">
          {saving ? 'Saving…' : 'Save'}
        </Btn>
      )}
    </div>
  )
}

function RecruitingPanel({ card, onSaved }) {
  const [form, setForm] = useState({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  useEffect(() => {
    setForm(Object.fromEntries(RECRUITING_FIELDS.map(([k]) => [k, card[k] || ''])))
  }, [card.id])

  const dirty = RECRUITING_FIELDS.some(([k]) => (form[k] || '') !== (card[k] || ''))

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      await scoutApi.updateCard(card.id, form)
      onSaved()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="pb-card p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Recruiting</div>
        <span className="font-mono text-[9px] uppercase tracking-wide2 text-pb-faintest">Never shared</span>
      </div>
      {error && <p className="text-xs text-pb-red">{error}</p>}
      {RECRUITING_FIELDS.map(([key, label]) => (
        <label key={key} className="block">
          <div className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faint mb-1">{label}</div>
          <input value={form[key] || ''} onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))} className={inputCls} />
        </label>
      ))}
      {dirty && (
        <Btn variant="primary" sm onClick={save} disabled={saving} className="w-full justify-center">
          {saving ? 'Saving…' : 'Save'}
        </Btn>
      )}
      <p className="text-[11px] text-pb-faint">These five fields stay internal — a shared profile carries stats, tags and notes only.</p>
    </div>
  )
}

function NotesPanel({ playerId, notes, onChange }) {
  const [adding, setAdding] = useState(false)
  const [body, setBody] = useState('')
  const [kind, setKind] = useState('other')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    if (!body.trim()) return
    setBusy(true)
    try {
      const note = await scoutApi.createNote(playerId, body.trim(), kind)
      onChange((prev) => [note, ...prev])
      setBody('')
      setAdding(false)
    } catch { /* keep the form open with the entered text on failure */ }
    finally { setBusy(false) }
  }

  const remove = async (id) => {
    await scoutApi.deleteNote(id)
    onChange((prev) => prev.filter((n) => n.id !== id))
  }

  return (
    <div className="pb-card p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Scouting notes</div>
        <button onClick={() => setAdding((v) => !v)} className="text-xs text-pb-accent hover:underline">+ Add note</button>
      </div>
      {adding && (
        <form onSubmit={submit} className="space-y-2">
          <select value={kind} onChange={(e) => setKind(e.target.value)} className={inputCls}>
            {NOTE_KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} placeholder="What did you see?" className={inputCls} autoFocus />
          <Btn variant="primary" sm type="submit" disabled={busy || !body.trim()}>{busy ? 'Saving…' : 'Save note'}</Btn>
        </form>
      )}
      <div className="space-y-3">
        {notes.length === 0 && !adding && <p className="text-xs text-pb-faint">No notes yet.</p>}
        {notes.map((n) => (
          <div key={n.id} className="group">
            <div className="font-mono text-[10px] text-pb-faint uppercase tracking-wide2 flex items-center justify-between">
              <span>{new Date(n.occurred_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })} · {n.author_name || 'Unknown'} · {NOTE_KINDS.find(([v]) => v === n.kind)?.[1] || n.kind}</span>
              <button onClick={() => remove(n.id)} className="opacity-0 group-hover:opacity-100 text-pb-faint hover:text-pb-red transition-opacity">✕</button>
            </div>
            <p className="text-[13px] mt-0.5">{n.body}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
