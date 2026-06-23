/* BetterIQ — Opposition player (v2 design).
 *
 * Club → searchable squad list → full per-player profile (Radar, scout-entered
 * WagonWheel scoring zones, batting/bowling clusters, dismissal breakdown,
 * record vs us, editable scouting tags). The profile card itself lives in
 * OppPlayerProfile.jsx (shared with OppositionScout); this screen owns the
 * club/player navigation, the live dossier poll and the URL state.
 *
 * Real wiring preserved: iqListOpponents / iqOppositionDossier (polled while
 * status === 'building') / iqOpponentTags / iqSaveOpponentTag, plus URL params
 * ?opponent=<opp_key> and ?player=<participant_id>.
 */
import { Fragment, useState, useEffect, useMemo, useRef } from 'react'
import Dropdown from '../../../components/Dropdown'
import { useSearchParams } from 'react-router-dom'
import IQLayout from '../../../components/admin/IQLayout'
import { api } from '../../../lib/api'
import { Icon, Tag, Btn, Search, Empty, PageIntro, Note, LoadingBar, runsPhrase, wktsPhrase } from './ui'
import AnyClubSearch from './AnyClubSearch'
import { OppPlayerDetail, buildOppPlayerIndex } from './OppPlayerProfile'
import { useClubPlayers, careerOnlyEntries, entryWithThreat, bestNameMatch, isOrgGuid } from './clubPlayers'

const POLL_MS = 2500

export default function OppositionPlayer() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [opponents, setOpponents] = useState([])
  const [club, setClub] = useState(null)        // { opp_key, name }
  const [dossier, setDossier] = useState(null)
  const [status, setStatus] = useState(null)    // 'building' | 'ready' | 'error' | 'unavailable'
  const [sel, setSel] = useState(null)          // participant_id
  const [clubQ, setClubQ] = useState('')
  const [playerQ, setPlayerQ] = useState('')
  const [clubOpen, setClubOpen] = useState(false)
  const [tags, setTags] = useState({})          // participant_id → scouting tag
  const [pSearch, setPSearch] = useState('')    // player-first search query
  const [pResults, setPResults] = useState([])
  const [pOpen, setPOpen] = useState(false)
  // Squad list is collapsible — once you've picked a player it's just eating the
  // width the profile wants, so let it minimise (persisted). When collapsed the
  // top-bar search becomes a combobox so you can still switch players.
  const [squadOpen, setSquadOpen] = useState(() => { try { return localStorage.getItem('iq.oppPlayer.squad') !== 'closed' } catch { return true } })
  const [playerComboOpen, setPlayerComboOpen] = useState(false)
  const pollRef = useRef(null)
  const seededRef = useRef(false)
  const pendingNameRef = useRef(null)           // player name to select once a dossier is ready

  const stopPoll = () => { if (pollRef.current) { clearTimeout(pollRef.current); pollRef.current = null } }
  useEffect(() => stopPoll, [])

  // Pull opponent list + saved scouting tags once.
  useEffect(() => { api.iqListOpponents().then(d => setOpponents(d?.opponents || [])).catch(() => setOpponents([])) }, [])
  useEffect(() => { api.iqOpponentTags().then(d => setTags(d || {})).catch(() => setTags({})) }, [])

  const saveTag = async (playerId, body) => {
    const saved = await api.iqSaveOpponentTag(playerId, body)
    setTags(t => ({ ...t, [playerId]: saved }))
    return saved
  }

  // Build/poll a club's live dossier. `name` rides along so a club outside our
  // history (CA-wide search → opp_key is a bare org GUID) still shows its name.
  const loadClub = (c, keepPlayer = false) => {
    stopPoll()
    setClub(c); setDossier(null); setStatus('building'); setClubQ(''); setClubOpen(false); setPlayerQ('')
    if (!keepPlayer) setSel(null)
    const params = { opponent: c.opp_key, name: c.name }
    const poll = () => {
      api.iqOppositionDossier(params).then(d => {
        setDossier(d); setStatus(d.status)
        if (d.status === 'building') pollRef.current = setTimeout(poll, POLL_MS)
      }).catch(() => setStatus('error'))
    }
    poll()
  }

  const pickClub = (c) => {
    loadClub(c)
    const sp = { opponent: c.opp_key }
    if (c.name) sp.name = c.name
    setSearchParams(sp, { replace: true })
  }
  // Player-first: pick an opposition player → load their club, then select them
  // by name once the live squad is built.
  const pickOpponentPlayer = (r) => {
    pendingNameRef.current = (r.name || '').trim().toLowerCase()
    setPSearch(''); setPResults([]); setPOpen(false)
    loadClub({ opp_key: r.opp_key, name: r.club_name })
    setSearchParams({ opponent: r.opp_key }, { replace: true })
  }
  const pickPlayer = (id) => {
    setSel(id); setPlayerQ('')
    const sp = { opponent: club.opp_key, player: id }
    if (club.name) sp.name = club.name
    setSearchParams(sp, { replace: true })
  }
  const changeClub = () => {
    stopPoll(); setClub(null); setDossier(null); setSel(null); setStatus(null); setSearchParams({}, { replace: true })
  }

  // Seed from the URL. A club outside our history won't be in the opponents
  // list — its ?name= param is enough to load it without waiting for the list.
  useEffect(() => {
    if (seededRef.current) return
    const opp = searchParams.get('opponent')
    const player = searchParams.get('player')
    const nameParam = searchParams.get('name')
    if (opp && nameParam) {
      seededRef.current = true
      if (player) setSel(player)
      loadClub({ opp_key: opp, name: nameParam }, !!player)
      return
    }
    if (!opponents.length) return
    if (opp) {
      const match = opponents.find(o => o.opp_key === opp)
      if (match) {
        seededRef.current = true
        if (player) setSel(player)
        loadClub({ opp_key: match.opp_key, name: match.name }, !!player)
      }
    } else {
      seededRef.current = true
    }
  }, [opponents])  // eslint-disable-line react-hooks/exhaustive-deps

  const index = useMemo(() => buildOppPlayerIndex(dossier), [dossier])
  const enriched = useMemo(() => {
    const m = new Map()
    for (const d of [...(dossier?.danger_batters || []), ...(dossier?.danger_bowlers || [])]) m.set(d.player_id, d)
    return m
  }, [dossier])
  const all = useMemo(() => [...index.entries()].map(([id, v]) => ({ id, ...v }))
    .sort((a, b) => (b.bat?.runs || 0) - (a.bat?.runs || 0) || (b.bowl?.wickets || 0) - (a.bowl?.wickets || 0)), [index])

  // The club's full five-year roster, merged behind the current-season squad —
  // a player who hasn't appeared this season (e.g. S Morgan) is still
  // searchable and selectable, with the career/deep cards as their profile.
  const orgGuid = dossier?.opponent?.org_id || (club && isOrgGuid(club.opp_key) ? club.opp_key : null)
  const clubPlayers = useClubPlayers(orgGuid, club?.name)
  const careerOnly = useMemo(() => careerOnlyEntries(index, clubPlayers), [index, clubPlayers])
  const everyone = useMemo(() => [...all, ...careerOnly], [all, careerOnly])
  const selected = useMemo(() => {
    if (!sel) return null
    const e = index.get(sel) || careerOnly.find(p => p.id === sel) || null
    return entryWithThreat(e, dossier)
  }, [sel, index, careerOnly, dossier])

  // Debounced opponent-player search (player-first entry).
  useEffect(() => {
    const q = pSearch.trim()
    if (q.length < 2) { setPResults([]); return }
    let alive = true
    const t = setTimeout(() => {
      api.iqSearchOpponentPlayers(q).then(d => { if (alive) setPResults(d || []) }).catch(() => { if (alive) setPResults([]) })
    }, 250)
    return () => { alive = false; clearTimeout(t) }
  }, [pSearch])

  // Once a club's live squad is ready, resolve a pending player name (from the
  // player-first search) to a participant and select them. The vs-us index
  // holds short names ("S Morgan") while rosters/aggregates hold "Simon Morgan"
  // / "Morgan, Simon", so this is a token/initial scorer, not a substring test.
  // A player absent from the current-season squad resolves against the
  // five-year list instead — wait for it before giving up on the name.
  useEffect(() => {
    if (status !== 'ready' || !pendingNameRef.current || !everyone.length) return
    const want = pendingNameRef.current
    const hit = bestNameMatch(want, everyone)
    const fiveYearPending = orgGuid && (!clubPlayers || clubPlayers.status === 'building')
    if (!hit && fiveYearPending) return
    pendingNameRef.current = null
    if (hit) {
      setSel(hit.id)
      if (club) {
        const sp = { opponent: club.opp_key, player: hit.id }
        if (club.name) sp.name = club.name
        setSearchParams(sp, { replace: true })
      }
    }
  }, [status, everyone, clubPlayers])  // eslint-disable-line react-hooks/exhaustive-deps

  const cq = clubQ.trim().toLowerCase()
  const clubMatches = (cq ? opponents.filter(o => (o.name || '').toLowerCase().includes(cq)) : opponents).slice(0, 40)
  const pq = playerQ.trim().toLowerCase()
  const playerMatches = pq ? everyone.filter(p => p.name.toLowerCase().includes(pq)) : everyone
  const clubRef = useRef(null)
  const playerRef = useRef(null)
  const playerComboRef = useRef(null)

  const toggleSquad = () => setSquadOpen(o => {
    const next = !o
    try { localStorage.setItem('iq.oppPlayer.squad', next ? 'open' : 'closed') } catch { /* ignore */ }
    return next
  })
  const playerRightText = (p) => p.careerOnly
    ? `${p.career?.runs ? runsPhrase(p.career.runs) : ''}${p.career?.wickets ? `${p.career?.runs ? ' · ' : ''}${wktsPhrase(p.career.wickets)}` : ''}`
    : `${p.bat?.runs ? runsPhrase(p.bat.runs) : ''}${p.bowl?.wickets ? ` · ${wktsPhrase(p.bowl.wickets)}` : ''}`
  // Squad rows — shared by the sidebar list and (when collapsed) the search
  // combobox dropdown, so both read identically. `compact` adds the mousedown
  // guard the dropdown needs to fire its click before the blur closes it.
  const playerRows = (list, { compact = false } = {}) => list.map((p, i) => {
    const on = p.id === sel
    const danger = tags[p.id]?.is_danger || enriched.get(p.id)?.alert?.level === 'danger'
    const firstCareer = p.careerOnly && (i === 0 || !list[i - 1].careerOnly)
    return (
      <Fragment key={p.id}>
        {firstCareer && <div className="iq-eyebrow px-2 pt-3 pb-1">Earlier years</div>}
        <button type="button" onMouseDown={compact ? (e => e.preventDefault()) : undefined}
          onClick={() => { pickPlayer(p.id); if (compact) setPlayerComboOpen(false) }}
          className="w-full flex items-center justify-between gap-2 px-2.5 py-2 text-left transition hover:bg-pb-surface2"
          style={{ borderRadius: 9, background: on ? 'color-mix(in srgb, var(--pb-accent) 12%, transparent)' : 'transparent' }}>
          <span className="font-medium text-[13.5px] truncate flex items-center gap-1.5" style={{ color: on ? 'var(--pb-accent)' : 'var(--pb-text)' }}>
            {p.name}
            {p.bat?.form === 'hot' && <Icon name="flame" size={12} style={{ color: 'var(--pb-red)' }} />}
            {danger && <span style={{ width: 6, height: 6, borderRadius: 99, background: 'var(--pb-red)' }} />}
          </span>
          <span className="iq-mono text-pb-faint shrink-0" style={{ fontSize: 10.5 }}>{playerRightText(p)}</span>
        </button>
      </Fragment>
    )
  })

  return (
    <IQLayout
      title="Opposition player"
      actions={club ? <Btn variant="ghost" sm icon="back" onClick={changeClub}>Change club</Btn> : null}
    >
      <PageIntro>Scout any individual at any club — their form, season history, how they get out, their record against us, and your own scouting notes (and scoring zones) that travel with them.</PageIntro>

      {/* Club picker */}
      {!club && (
        <div className="iq-fade">
          <div className="flex flex-wrap items-center gap-3 mb-5">
            <span className="iq-eyebrow">Club</span>
            <div ref={clubRef} className="relative flex-1 min-w-[260px] max-w-md"
              onFocusCapture={() => setClubOpen(true)} onBlur={() => setTimeout(() => setClubOpen(false), 150)}>
              <Search value={clubQ} onChange={(v) => { setClubQ(v); setClubOpen(true) }} placeholder="Search an opponent club…" className="w-full" />
              <Dropdown
                anchorRef={clubRef}
                open={clubOpen}
                onClose={() => setClubOpen(false)}
                maxHeight={320}
                className="iq-card p-1 iq-scroll shadow-lg"
                style={{ background: 'var(--pb-surface)' }}
              >
                {clubMatches.length === 0
                  ? <div className="px-2.5 py-2 text-pb-faint text-sm">{opponents.length === 0 ? 'No opponents with history yet.' : 'No match.'}</div>
                  : clubMatches.map(o => (
                    <button key={o.opp_key} type="button" onMouseDown={e => e.preventDefault()} onClick={() => pickClub(o)}
                      className="w-full flex items-center justify-between gap-3 px-2.5 py-1.5 rounded-lg hover:bg-pb-surface2 text-left">
                      <span className="font-medium truncate">{o.name}</span>
                      <span className="text-pb-faintest text-[11px] iq-num whitespace-nowrap">{o.shared_grade ? 'shared grade' : `${o.meetings} mtgs${o.coverage === 'rich' ? ' · rich' : ''}`}</span>
                    </button>
                  ))}
              </Dropdown>
            </div>
          </div>

          {/* CA-wide club search — scout a club we've NEVER met (new grade after
              relegation/promotion, another association, anyone on PlayHQ). */}
          <div className="flex flex-wrap items-center gap-3 mb-5">
            <span className="iq-eyebrow">Any club</span>
            <AnyClubSearch className="flex-1 min-w-[260px] max-w-md"
              placeholder="…or search every club on PlayHQ"
              onPick={(org) => pickClub({ opp_key: org.id, name: org.name })} />
          </div>

          {/* Player-first search — jump straight to an opposition player */}
          <div className="flex flex-wrap items-center gap-3 mb-6">
            <span className="iq-eyebrow">Player</span>
            <div ref={playerRef} className="relative flex-1 min-w-[260px] max-w-md"
              onFocusCapture={() => setPOpen(true)} onBlur={() => setTimeout(() => setPOpen(false), 150)}>
              <Search value={pSearch} onChange={(v) => { setPSearch(v); setPOpen(true) }} placeholder="…or search an opposition player by name" className="w-full" />
              <Dropdown
                anchorRef={playerRef}
                open={pOpen && pSearch.trim().length >= 2}
                onClose={() => setPOpen(false)}
                maxHeight={320}
                className="iq-card p-1 iq-scroll shadow-lg"
                style={{ background: 'var(--pb-surface)' }}
              >
                {pResults.length === 0
                  ? <div className="px-2.5 py-2 text-pb-faint text-sm">No opposition player found — we index batters our bowlers have dismissed.</div>
                  : pResults.map((r, i) => (
                    <button key={`${r.opp_key}-${r.name}-${i}`} type="button" onMouseDown={e => e.preventDefault()} onClick={() => pickOpponentPlayer(r)}
                      className="w-full flex items-center justify-between gap-3 px-2.5 py-1.5 rounded-lg hover:bg-pb-surface2 text-left">
                      <span className="min-w-0">
                        <span className="font-medium truncate block">{r.name}</span>
                        <span className="text-pb-faintest text-[11px] truncate block">{r.club_name}</span>
                      </span>
                      <span className="text-pb-faint text-[11px] iq-num whitespace-nowrap">{runsPhrase(r.runs)} vs us</span>
                    </button>
                  ))}
              </Dropdown>
            </div>
          </div>

          {opponents.length > 0 && (
            <>
              <div className="iq-eyebrow mb-3">All opponents ({opponents.length})</div>
              <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
                {opponents.slice(0, 60).map((o, i) => (
                  <button key={o.opp_key} onClick={() => pickClub(o)}
                    className="iq-card text-left px-4 py-3.5 transition flex items-center justify-between gap-2 iq-rise"
                    style={{ animationDelay: `${i * 22}ms` }}
                    onMouseEnter={e => e.currentTarget.style.borderColor = 'color-mix(in srgb, var(--pb-accent) 45%, transparent)'}
                    onMouseLeave={e => e.currentTarget.style.borderColor = ''}>
                    <div className="min-w-0">
                      <div className="iq-display font-semibold truncate">{o.name}</div>
                      <div className="text-pb-faint text-[11.5px] mt-0.5 iq-num">{o.shared_grade ? 'Shared grade · scout live' : `${o.meetings} meetings${o.last_played ? ` · last ${o.last_played.slice(0, 4)}` : ''}`}</div>
                    </div>
                    {o.coverage === 'rich' && <Tag tone="accent">Synced</Tag>}
                  </button>
                ))}
              </div>
            </>
          )}
          {opponents.length === 0 && <div className="iq-card p-6"><Empty>No opponents with history yet — play some games or sync history.</Empty></div>}
        </div>
      )}

      {/* Building / error states */}
      {club && status === 'building' && (
        <div className="iq-card iq-accent-card p-8 text-center iq-fade">
          <div className="iq-display font-bold text-[16px]">Building {club.name}'s squad…</div>
          <div className="text-pb-faint text-[13px] mt-1.5 max-w-md mx-auto">Pulling their recent scorecards live — first time can take up to a minute.</div>
          <div className="max-w-md mx-auto mt-5"><LoadingBar expectedMs={35000} /></div>
        </div>
      )}
      {club && (status === 'error' || status === 'unavailable') && (
        <div className="iq-card p-6"><Empty>Couldn't build a live dossier for {club.name} right now — try again shortly.</Empty></div>
      )}

      {/* Club selected + ready → searchable squad list + profile */}
      {club && status === 'ready' && (
        <div className="iq-fade">
          <div className="flex flex-wrap items-center gap-3 mb-5">
            <span className="iq-eyebrow">Club</span>
            <span className="px-3 py-1.5 iq-display font-semibold text-[13px]" style={{ borderRadius: 99, background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)', color: 'var(--pb-accent)', border: '1px solid color-mix(in srgb, var(--pb-accent) 35%, transparent)' }}>{club.name}</span>
            <Btn variant="soft" sm icon="teams" onClick={toggleSquad} title={squadOpen ? 'Hide the squad list' : 'Show the squad list'}>
              {squadOpen ? 'Hide list' : `Squad (${all.length})`}
            </Btn>
            <div ref={playerComboRef} className="relative flex-1 min-w-[220px] max-w-xs"
              onFocusCapture={() => { if (!squadOpen) setPlayerComboOpen(true) }}
              onBlur={() => setTimeout(() => setPlayerComboOpen(false), 150)}>
              <Search value={playerQ} onChange={(v) => { setPlayerQ(v); if (!squadOpen) setPlayerComboOpen(true) }} placeholder={`Search ${club.name} players…`} className="w-full" />
              {!squadOpen && (
                <Dropdown anchorRef={playerComboRef} open={playerComboOpen} onClose={() => setPlayerComboOpen(false)} maxHeight={360}
                  className="iq-card p-1 iq-scroll shadow-lg" style={{ background: 'var(--pb-surface)' }}>
                  {playerMatches.length === 0
                    ? <div className="px-2.5 py-2 text-pb-faint text-sm">{everyone.length === 0 ? 'No players found.' : 'No match.'}</div>
                    : playerRows(playerMatches.slice(0, 60), { compact: true })}
                </Dropdown>
              )}
            </div>
          </div>

          <div className={`grid gap-6 items-start ${squadOpen ? 'lg:grid-cols-[260px_1fr]' : 'grid-cols-1'}`}>
            {/* Squad list — current-season squad first, then everyone else CA's
                aggregates have seen at this club in the last five years. Collapsible
                so the profile can take the full width once you've picked someone. */}
            {squadOpen && (
              <div className="iq-card p-2 lg:sticky lg:top-20">
                <div className="flex items-center justify-between px-2 py-2">
                  <span className="iq-eyebrow">Squad ({all.length})</span>
                  <button type="button" onClick={toggleSquad} title="Hide list"
                    className="text-pb-faint hover:text-pb-text transition" style={{ lineHeight: 0 }}>
                    <Icon name="chevron" size={16} style={{ transform: 'rotate(180deg)' }} />
                  </button>
                </div>
                <div className="max-h-[64vh] overflow-y-auto iq-scroll">
                  {playerMatches.length === 0
                    ? <Empty className="px-2.5 py-2">{everyone.length === 0
                        ? (clubPlayers?.status === 'building' ? 'Pulling their player history…' : 'No players found.')
                        : 'No match.'}</Empty>
                    : playerRows(playerMatches)}
                  {clubPlayers?.status === 'building' && everyone.length > 0 && (
                    <div className="iq-eyebrow px-2 pt-3 pb-2 animate-pulse">Pulling their player history…</div>
                  )}
                </div>
              </div>
            )}

            {/* Profile */}
            <div>
              {selected
                ? <OppPlayerDetail entry={selected} enriched={enriched.get(sel)} opponentName={club.name} playerId={sel} tag={tags[sel]} onSaveTag={saveTag}
                    dossierBatting={dossier?.batting || []} dossierBowling={dossier?.bowling || []}
                    orgGuid={orgGuid} />
                : <div className="iq-card p-8"><Empty>Pick one of {club.name}'s players for their full profile — radar, scoring zones, form, season history, dismissal patterns and record vs us.</Empty></div>}
            </div>
          </div>

          {dossier?.coverage?.notes?.length > 0 && (
            <Note>{dossier.coverage.notes.join(' ')}{dossier.built_at ? ` · built ${new Date(dossier.built_at).toLocaleString()}` : ''}</Note>
          )}
        </div>
      )}
    </IQLayout>
  )
}
