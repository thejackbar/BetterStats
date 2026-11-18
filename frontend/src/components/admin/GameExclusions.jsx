import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { PbSpinner } from '../../lib/presskit'

// A club marks a player as named for a synced match but not having played it (12th man, 13th man,
// a late withdrawal). The game stays on the team list with the reason and comes off every games
// played count. Backed by routers/game_exclusions.py; see services/game_exclusions.py for why.

const BTN = 'px-3 py-1.5 rounded border pb-hairline font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text hover:bg-pb-surface2 disabled:opacity-40'
const BTN_PRIMARY = 'px-4 py-2 rounded bg-pb-accent text-white text-sm font-semibold hover:opacity-90 disabled:opacity-40'

const STATUS = {
  played: { label: 'Played', tone: 'text-pb-faint', note: 'Batted or bowled, so the game counts.' },
  fielded: { label: 'Counted', tone: 'text-pb-text', note: 'Fielded only (a catch, stumping or run out). If they were a substitute fielder, mark them as not played.' },
  named: { label: 'Counted', tone: 'text-pb-text', note: 'Named in the side with nothing recorded. Counted as a game played.' },
  marked: { label: 'Not counted', tone: 'text-pb-accent', note: null },
  game_not_played: { label: 'Not counted', tone: 'text-pb-faint', note: 'The match was called off or never started.' },
  auto_reserve: { label: 'Not counted', tone: 'text-pb-faint', note: 'Read as 12th man: listed 12th or lower and nothing recorded.' },
  auto_withdrawn: { label: 'Not counted', tone: 'text-pb-faint', note: "Not on Cricket Australia's final team sheet." },
}

export function statusNote(row) {
  if (row.status === 'marked') return `Marked by the club: ${row.reason_label || 'did not play'}${row.note ? `. ${row.note}` : ''}`
  return STATUS[row.status]?.note || ''
}

function matchLabel(row) {
  const teams = [row.home_team, row.away_team].filter(Boolean).join(' v ')
  return teams || 'Match'
}

function dateLabel(iso) {
  if (!iso) return ''
  const d = new Date(`${iso}T00:00:00`)
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

// The dialog that asks for the reason, and offers to move a -1 season adjustment onto the game.
export function NotPlayedDialog({ row, reasons, onClose, onDone }) {
  const [reason, setReason] = useState('twelfth_man')
  const [note, setNote] = useState('')
  const [adjustments, setAdjustments] = useState(null)
  const [swap, setSwap] = useState(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true
    api.getNotPlayedAdjustments(row.game_id, row.player_id)
      .then(d => {
        if (!alive) return
        const list = d.adjustments || []
        setAdjustments(list)
        // Default to moving the adjustment across: leaving it would take the game off twice.
        if (list.length) setSwap(list[0].id)
      })
      .catch(() => { if (alive) setAdjustments([]) })
    return () => { alive = false }
  }, [row.game_id, row.player_id])

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      const out = await api.markNotPlayed(row.game_id, {
        player_id: row.player_id, reason, note: note.trim() || null, swap_adjustment_id: swap,
      })
      onDone(out)
    } catch (e) {
      setError(e.message)
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start sm:items-center justify-center bg-black/60 px-4 py-6 overflow-y-auto" onClick={onClose}>
      <div className="pb-card w-full max-w-md p-5" onClick={e => e.stopPropagation()} data-testid="not-played-dialog">
        <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-2">DID NOT PLAY</p>
        <p className="text-sm text-pb-text mb-1 font-semibold">{row.player_name}</p>
        <p className="text-xs text-pb-faint mb-4">
          {matchLabel(row)}{row.played_at ? `, ${dateLabel(row.played_at)}` : ''}{row.grade_name ? ` (${row.grade_name})` : ''}.
          {' '}They stay on the team list with the reason you pick, and this game comes off their games played
          everywhere: profile, season table, leaderboards and milestones.
        </p>

        {row.status === 'fielded' && (
          <p className="text-xs text-pb-text mb-4 rounded border border-pb-accent/40 p-3" data-testid="sub-fielder-note">
            {row.player_name} has a fielding line in this game. If they were a substitute fielder, the catch, stumping
            or run out was taken as a sub, so it comes off their fielding figures along with the game. The scorecard
            still shows it.
          </p>
        )}

        <fieldset className="mb-4">
          <legend className="font-mono text-[10px] text-pb-faint mb-2">REASON</legend>
          <div className="grid grid-cols-2 gap-2">
            {reasons.map(r => (
              <label key={r.key}
                className={`flex items-center gap-2 px-3 py-2 rounded border text-sm cursor-pointer ${reason === r.key ? 'border-pb-accent text-pb-text' : 'pb-hairline text-pb-faint'}`}>
                <input type="radio" name="reason" value={r.key} checked={reason === r.key}
                  onChange={() => setReason(r.key)} className="accent-pb-accent" />
                {r.label}
              </label>
            ))}
          </div>
        </fieldset>

        <label className="block mb-4">
          <span className="font-mono text-[10px] text-pb-faint block mb-1">NOTE (OPTIONAL)</span>
          <input type="text" value={note} maxLength={300} onChange={e => setNote(e.target.value)}
            placeholder="e.g. came on as a substitute fielder only"
            className="w-full bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 focus:outline-none focus:border-pb-accent" />
        </label>

        {adjustments === null && <div className="py-2"><PbSpinner /></div>}
        {adjustments?.length > 0 && (
          <div className="mb-4 rounded border border-pb-accent/40 p-3" data-testid="swap-adjustment">
            <p className="text-xs text-pb-text mb-2">
              This player already has a season adjustment taking games off {adjustments[0].season_name}.
              If it was for this game, move it onto the game so it is not taken off twice.
            </p>
            {adjustments.map(a => (
              <label key={a.id} className="flex items-center gap-2 text-xs text-pb-text mb-1">
                <input type="radio" name="swap" checked={swap === a.id} onChange={() => setSwap(a.id)} className="accent-pb-accent" />
                It was for this game: change the {a.season_name}{a.grade_name ? `, ${a.grade_name}` : ''} adjustment from {a.matches} to {a.matches + 1}
              </label>
            ))}
            <label className="flex items-center gap-2 text-xs text-pb-faint">
              <input type="radio" name="swap" checked={swap === null} onChange={() => setSwap(null)} className="accent-pb-accent" />
              Keep the adjustment as it is (it was for a different game)
            </label>
          </div>
        )}

        {error && <p className="text-pb-red text-sm mb-3" role="alert">{error}</p>}

        <div className="flex justify-end gap-2">
          <button type="button" className={BTN} onClick={onClose}>CANCEL</button>
          <button type="button" className={BTN_PRIMARY} onClick={save} disabled={saving} data-testid="confirm-not-played">
            {saving ? 'Saving…' : 'Mark as not played'}
          </button>
        </div>
      </div>
    </div>
  )
}

// One row with its action, shared by the match page, the player picker and Games to check.
function GameRow({ row, reasons, showMatch, showPlayer, onChanged, extra }) {
  const [dialog, setDialog] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const st = STATUS[row.status] || STATUS.named

  const unmark = async () => {
    setBusy(true)
    setError(null)
    try {
      onChanged(await api.unmarkNotPlayed(row.game_id, row.player_id))
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  return (
    <li className="py-2.5 border-b pb-hairline last:border-b-0" data-testid="game-row" data-status={row.status}>
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1.5">
        <div className="min-w-0 flex-1">
          {showPlayer && <p className="text-sm text-pb-text font-semibold truncate">{row.player_name}</p>}
          {showMatch && (
            <p className="text-sm text-pb-text">
              <Link to={`/games/${row.game_id}`} className="hover:text-pb-accent">{matchLabel(row)}</Link>
              <span className="text-pb-faint text-xs"> {dateLabel(row.played_at)}{row.grade_name ? `, ${row.grade_name}` : ''}</span>
            </p>
          )}
          {!showPlayer && !showMatch && <p className="text-sm text-pb-text font-semibold">{row.player_name}</p>}
          <p className="text-xs text-pb-faint">
            <span className={`font-mono text-[10px] tracking-wide2 uppercase mr-1.5 ${st.tone}`}>{st.label}</span>
            {statusNote(row)}
          </p>
          {extra}
          {error && <p className="text-pb-red text-xs mt-1" role="alert">{error}</p>}
        </div>
        <div className="flex gap-2 shrink-0">
          {row.can_mark && (
            <button type="button" className={BTN} onClick={() => setDialog(true)} data-testid="mark-not-played">
              DIDN&apos;T PLAY
            </button>
          )}
          {row.status === 'marked' && (
            <button type="button" className={BTN} onClick={unmark} disabled={busy} data-testid="unmark-not-played">
              COUNT AGAIN
            </button>
          )}
        </div>
      </div>
      {dialog && (
        <NotPlayedDialog row={row} reasons={reasons} onClose={() => setDialog(false)}
          onDone={out => { setDialog(false); onChanged(out) }} />
      )}
    </li>
  )
}

// On the match page, for a club admin: the club's players named in this match.
export function TeamListPanel({ gameId, onChanged }) {
  const [state, setState] = useState({ loading: true, players: [], reasons: [], error: null })
  const [notice, setNotice] = useState(null)

  const load = () => api.getTeamList(gameId)
    .then(d => setState({ loading: false, players: d.players || [], reasons: d.reasons || [], error: null }))
    .catch(e => setState({ loading: false, players: [], reasons: [], error: e.message }))

  useEffect(() => { load() }, [gameId]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!state.loading && !state.error && !state.players.length) return null
  return (
    <div className="pb-card p-5 mt-4" data-testid="team-list-panel">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1">GAMES PLAYED: YOUR TEAM LIST</p>
      <p className="text-xs text-pb-faint mb-3">
        Only club admins see this. If someone was named but did not play (12th man, 13th man or a late withdrawal),
        mark it here and the game comes off their games played.
      </p>
      {state.loading && <PbSpinner />}
      {state.error && <p className="text-pb-red text-sm">{state.error}</p>}
      {notice && <p className="text-xs text-pb-text mb-2" role="status">{notice}</p>}
      <ul>
        {state.players.map(r => (
          <GameRow key={r.player_id} row={r} reasons={state.reasons}
            onChanged={out => { setNotice(out?.summary || null); load(); onChanged?.() }} />
        ))}
      </ul>
    </div>
  )
}

// Adjustments screen: pick a player and the exact game.
export function PlayerGamePicker({ players }) {
  const [playerId, setPlayerId] = useState('')
  const [query, setQuery] = useState('')
  const [season, setSeason] = useState('')
  const [state, setState] = useState({ loading: false, games: [], reasons: [], error: null })
  const [notice, setNotice] = useState(null)

  const options = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (players || [])
      .filter(p => !q || (p.display_name || p.name || '').toLowerCase().includes(q))
      .slice(0, 50)
  }, [players, query])

  const load = (pid) => {
    if (!pid) return
    setState(s => ({ ...s, loading: true, error: null }))
    api.getPlayerGamesForExclusion(pid)
      .then(d => setState({ loading: false, games: d.games || [], reasons: d.reasons || [], error: null }))
      .catch(e => setState({ loading: false, games: [], reasons: [], error: e.message }))
  }

  useEffect(() => { setSeason(''); setNotice(null); load(playerId) }, [playerId])

  const seasons = useMemo(() => [...new Set(state.games.map(g => g.season_name).filter(Boolean))], [state.games])
  const shown = state.games.filter(g => !season || g.season_name === season)
  const counted = shown.filter(g => g.counts).length

  return (
    <div className="pb-card p-5 mb-4" data-testid="player-game-picker">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1">REMOVE A GAME FROM A PLAYER&apos;S COUNT</p>
      <p className="text-xs text-pb-faint mb-3">
        Pick the exact game a player was named in but did not play. This is better than a -1 adjustment because
        the game stays on record with the reason. Only synced games are listed here; edit an uploaded or imported
        card from Manual Games.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
        <div className="min-w-0">
          <span className="font-mono text-[10px] text-pb-faint block mb-1">PLAYER</span>
          <input type="text" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search players" aria-label="Search players"
            className="w-full bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2 mb-2 focus:outline-none focus:border-pb-accent" />
          <select value={playerId} onChange={e => setPlayerId(e.target.value)} data-testid="picker-player" aria-label="Player"
            className="w-full bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2">
            <option value="">Choose a player</option>
            {options.map(p => <option key={p.id} value={p.id}>{p.display_name || p.name}</option>)}
          </select>
        </div>
        {seasons.length > 0 && (
          <label className="block min-w-0">
            <span className="font-mono text-[10px] text-pb-faint block mb-1">SEASON</span>
            <select value={season} onChange={e => setSeason(e.target.value)} data-testid="picker-season"
              className="w-full bg-pb-surface2 border pb-hairline text-pb-text text-sm rounded px-3 py-2">
              <option value="">All seasons</option>
              {seasons.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
        )}
      </div>
      {state.loading && <PbSpinner />}
      {state.error && <p className="text-pb-red text-sm">{state.error}</p>}
      {notice && <p className="text-xs text-pb-text mb-2" role="status">{notice}</p>}
      {playerId && !state.loading && !state.error && (
        shown.length
          ? <>
              <p className="text-xs text-pb-faint mb-1">{shown.length} game{shown.length === 1 ? '' : 's'} named, {counted} counted as played.</p>
              <ul>
                {shown.map(r => (
                  <GameRow key={r.game_id} row={r} reasons={state.reasons} showMatch
                    onChanged={out => { setNotice(out?.summary || null); load(playerId) }} />
                ))}
              </ul>
            </>
          : <p className="text-xs text-pb-faint">No synced games for this player.</p>
      )}
    </div>
  )
}

// The review list: named, nothing recorded, in a season where we count more than Cricket Australia.
export function GamesToCheck() {
  const [state, setState] = useState({ loading: true, items: [], reasons: [], truncated: false, error: null })
  const [notice, setNotice] = useState(null)

  const load = () => api.getGamesToCheck()
    .then(d => setState({ loading: false, items: d.items || [], reasons: d.reasons || [], truncated: !!d.truncated, error: null }))
    .catch(e => setState({ loading: false, items: [], reasons: [], truncated: false, error: e.message }))

  useEffect(() => { load() }, [])

  const keep = async (row) => {
    try {
      await api.dismissGameToCheck({ game_id: row.game_id, player_id: row.player_id })
      setNotice(`Kept as played: ${row.player_name}, ${matchLabel(row)}`)
      load()
    } catch (e) { setNotice(e.message) }
  }

  return (
    <div className="pb-card p-5" data-testid="games-to-check">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1">GAMES TO CHECK</p>
      <p className="text-xs text-pb-faint mb-3">
        Players named in a game where they did not bat, bowl or take a catch, in a season where we count more
        games than Cricket Australia&apos;s total for them. These are often 12th man games. Nothing changes until
        you choose: mark the game as not played, or keep it as played and it will not be listed again.
      </p>
      {state.loading && <PbSpinner />}
      {state.error && <p className="text-pb-red text-sm">{state.error}</p>}
      {notice && <p className="text-xs text-pb-text mb-2" role="status">{notice}</p>}
      {!state.loading && !state.error && !state.items.length && (
        <p className="text-xs text-pb-faint" data-testid="games-to-check-empty">
          Nothing to check. Every player&apos;s games agree with Cricket Australia&apos;s totals, or the differences
          have been looked at.
        </p>
      )}
      <ul>
        {state.items.map(r => (
          <GameRow key={`${r.player_id}:${r.game_id}`} row={r} reasons={state.reasons} showPlayer showMatch
            onChanged={out => { setNotice(out?.summary || null); load() }}
            extra={(
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1">
                <span className="text-xs text-pb-faint">
                  {r.season_name}: we count {r.our_season_total}, Cricket Australia counts {r.ca_season_total}.
                </span>
                <button type="button" className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-accent"
                  onClick={() => keep(r)} data-testid="keep-as-played">KEEP AS PLAYED</button>
              </div>
            )} />
        ))}
      </ul>
      {state.truncated && (
        <p className="text-xs text-pb-faint mt-2">Showing the first 500. Work through these and the rest will appear.</p>
      )}
    </div>
  )
}

// One side's sheet with more than 11 still counted: the club marks the extras or calls it checked.
function BigSheet({ sheet, onChanged }) {
  const [open, setOpen] = useState(false)
  const [state, setState] = useState({ loading: false, players: [], reasons: [], error: null })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const load = () => {
    setState(s => ({ ...s, loading: true, error: null }))
    return api.getTeamList(sheet.game_id)
      .then(d => setState({ loading: false, reasons: d.reasons || [], error: null,
                            players: (d.players || []).filter(p => (p.team_name || '') === (sheet.team_name || '')) }))
      .catch(e => setState({ loading: false, players: [], reasons: [], error: e.message }))
  }

  const toggle = () => { if (!open) load(); setOpen(o => !o) }

  const checked = async () => {
    setBusy(true); setError(null)
    try {
      await api.checkSheet({ game_id: sheet.game_id, team_name: sheet.team_name || '' })
      onChanged(`Checked: ${matchLabel(sheet)}, ${dateLabel(sheet.played_at)}`)
    } catch (e) { setError(e.message); setBusy(false) }
  }

  const counted = state.players.filter(p => p.counts).length
  return (
    <li className="py-2.5 border-b pb-hairline last:border-b-0" data-testid="big-sheet">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1.5">
        <div className="min-w-0 flex-1">
          <p className="text-sm text-pb-text">
            <Link to={`/games/${sheet.game_id}`} className="hover:text-pb-accent">{matchLabel(sheet)}</Link>
            <span className="text-pb-faint text-xs"> {dateLabel(sheet.played_at)}{sheet.grade_name ? `, ${sheet.grade_name}` : ''}</span>
          </p>
          <p className="text-xs text-pb-faint">
            {sheet.team_name ? `${sheet.team_name}: ` : ''}{sheet.counted} players counted as playing, so at least {sheet.extras} {sheet.extras === 1 ? 'was an extra' : 'were extras'}.
          </p>
          {error && <p className="text-pb-red text-xs mt-1" role="alert">{error}</p>}
        </div>
        <div className="flex gap-2 shrink-0">
          <button type="button" className={BTN} onClick={toggle} aria-expanded={open} data-testid="review-sheet">
            {open ? 'HIDE' : 'REVIEW'}
          </button>
          <button type="button" className={BTN} onClick={checked} disabled={busy} data-testid="sheet-checked">
            CHECKED
          </button>
        </div>
      </div>
      {open && (
        <div className="mt-2 pl-3 border-l pb-hairline" data-testid="big-sheet-players">
          {state.loading && <PbSpinner />}
          {state.error && <p className="text-pb-red text-xs">{state.error}</p>}
          {!state.loading && !state.error && (
            <p className="text-xs text-pb-faint mb-1">
              {counted} of {state.players.length} named are counted. Mark anyone who was 12th man, 13th man or a sub fielder.
            </p>
          )}
          <ul>
            {state.players.map(r => (
              <GameRow key={r.player_id} row={r} reasons={state.reasons} onChanged={() => load()} />
            ))}
          </ul>
        </div>
      )}
    </li>
  )
}

// Sides with more than 11 names still counted: every one named at least one extra.
export function BigSheets() {
  const [state, setState] = useState({ loading: true, items: [], truncated: false, error: null })
  const [notice, setNotice] = useState(null)

  const load = () => api.getBigSheets()
    .then(d => setState({ loading: false, items: d.items || [], truncated: !!d.truncated, error: null }))
    .catch(e => setState({ loading: false, items: [], truncated: false, error: e.message }))

  useEffect(() => { load() }, [])

  return (
    <div className="pb-card p-5 mt-4" data-testid="big-sheets">
      <p className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1">TEAM SHEETS WITH MORE THAN 11 NAMES</p>
      <p className="text-xs text-pb-faint mb-3">
        A side is eleven, so each of these sheets named at least one extra, such as a sub fielder who came
        along or the 12th and 13th men in a final. Cricket Australia often counts them as games played, so the
        list above can miss them. Review the sheet and mark the extras, or mark it checked if everyone named
        did play. A sheet leaves the list once no more than 11 are counted.
      </p>
      {state.loading && <PbSpinner />}
      {state.error && <p className="text-pb-red text-sm">{state.error}</p>}
      {notice && <p className="text-xs text-pb-text mb-2" role="status">{notice}</p>}
      {!state.loading && !state.error && !state.items.length && (
        <p className="text-xs text-pb-faint" data-testid="big-sheets-empty">No team sheets with more than 11 players counted.</p>
      )}
      <ul>
        {state.items.map(sh => (
          <BigSheet key={`${sh.game_id}:${sh.team_name}`} sheet={sh}
            onChanged={msg => { setNotice(msg); load() }} />
        ))}
      </ul>
      {state.truncated && <p className="text-xs text-pb-faint mt-2">Showing the newest 200. Work through these and older ones will appear.</p>}
    </div>
  )
}

// Public match page: who the club marked as named but not playing.
export function NotPlayedNote({ gameId, fmtName = n => n, refreshKey }) {
  const [players, setPlayers] = useState([])
  useEffect(() => {
    let alive = true
    api.getNotPlayed(gameId).then(d => { if (alive) setPlayers(d.players || []) }).catch(() => {})
    return () => { alive = false }
  }, [gameId, refreshKey])
  if (!players.length) return null
  return (
    <p className="text-xs text-pb-faint mt-4" data-testid="not-played-note">
      Named but did not play:{' '}
      {players.map((p, i) => (
        <span key={p.player_id}>
          {i > 0 && ', '}
          <Link to={`/players/${p.player_id}`} className="text-pb-text hover:text-pb-accent">{fmtName(p.player_name)}</Link>
          {' '}({p.reason_label})
        </span>
      ))}
    </p>
  )
}
