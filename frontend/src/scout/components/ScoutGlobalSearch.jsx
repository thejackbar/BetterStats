import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { scoutApi } from '../lib/scoutApi'
import { Icon } from '../../pages/admin/betterselect/ui'
import { PlayerAvatar } from './ScoutUi'

const POLL_MS = 2500
const MAX_POLLS = 60 // bounded so a wedged club-roster build doesn't poll forever (~2.5min)

// The one always-visible search bar — clubs and players together, in
// ScoutModuleLayout's header on every screen. Backed by the REAL API behind
// play.cricket.com.au's own header search (services/scout_live_search.py) —
// genuinely national coverage, not limited to clubs BetterScout has already
// cached.
export default function ScoutGlobalSearch() {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [activeIdx, setActiveIdx] = useState(-1)
  const [addingId, setAddingId] = useState(null)
  const [addError, setAddError] = useState(null)
  const rootRef = useRef(null)
  const pollCount = useRef(0)

  const query = q.trim()

  useEffect(() => {
    if (query.length < 2) { setData(null); setLoading(false); return }
    setLoading(true)
    const t = setTimeout(() => {
      scoutApi.unifiedSearch(query)
        .then((res) => { setData(res); setActiveIdx(-1) })
        .catch(() => setData(null))
        .finally(() => setLoading(false))
    }, 280)
    return () => clearTimeout(t)
  }, [query])

  useEffect(() => {
    function onDocClick(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  const flatResults = data
    ? [
        ...(data.clubs || []).map((c) => ({ kind: 'club', ...c })),
        ...(data.players || []).map((p) => ({ kind: 'player', ...p })),
      ]
    : []

  const pickClub = (c) => {
    setOpen(false); setQ('')
    navigate('/betterscout/app/discover', { state: { club: { id: c.id, name: c.name } } })
  }
  const pickPlayer = (p) => {
    if (p.tracked && p.scouted_player_id) {
      setOpen(false); setQ('')
      navigate(`/betterscout/app/players/${p.scouted_player_id}?q=${encodeURIComponent(query)}`)
      return
    }
    // Untracked — add and track them directly rather than sending the scout
    // off to the old club-then-player Search page (which needs a club
    // already picked and can't do anything useful with just a name).
    trackAndOpen(p)
  }

  const callAdd = (p) => scoutApi.addPlayerFromSearch({
    orgGuid: p.club_org_guid, playerName: p.name, clubName: p.club_name,
    canonicalParticipantId: p.player_id,
  })

  const trackAndOpen = async (p) => {
    setAddError(null)
    setAddingId(p.player_id)
    pollCount.current = 0
    try {
      await pollUntilReady(p, await callAdd(p))
    } catch (e) {
      setAddError(e.message || 'Could not add this player.')
      setAddingId(null)
    }
  }

  const pollUntilReady = async (p, res) => {
    if (res.status === 'building') {
      if (++pollCount.current >= MAX_POLLS) {
        setAddError('That club is taking a while to load. Try again shortly.')
        setAddingId(null)
        return
      }
      setTimeout(async () => {
        try {
          await pollUntilReady(p, await callAdd(p))
        } catch (e) {
          setAddError(e.message || 'Could not add this player.')
          setAddingId(null)
        }
      }, POLL_MS)
      return
    }
    setAddingId(null)
    setOpen(false); setQ('')
    navigate(`/betterscout/app/players/${res.id}?q=${encodeURIComponent(query)}`)
  }

  const pick = (r) => (r.kind === 'club' ? pickClub(r) : pickPlayer(r))

  const onKeyDown = (e) => {
    if (!open || flatResults.length === 0) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setActiveIdx((i) => Math.min(i + 1, flatResults.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActiveIdx((i) => Math.max(i - 1, 0)) }
    else if (e.key === 'Enter') { e.preventDefault(); const r = flatResults[activeIdx]; if (r) pick(r) }
    else if (e.key === 'Escape') { setOpen(false) }
  }

  return (
    <div ref={rootRef} className="relative min-w-0 flex-1 max-w-[360px]">
      <div className="flex items-center gap-2 bg-pb-surface2 border border-pb-hairline rounded-lg px-3 h-[38px] text-pb-faint focus-within:border-pb-accent">
        <Icon name="search" size={16} />
        <input
          value={q}
          onChange={(e) => { setQ(e.target.value); setOpen(true); setAddError(null) }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder="Search a club or player…"
          className="bg-transparent border-0 outline-none text-pb-text text-sm w-full placeholder:text-pb-faint"
        />
      </div>

      {open && query.length >= 2 && (
        <div className="scout-no-print absolute left-0 right-0 top-[calc(100%+6px)] z-50 pb-card overflow-hidden shadow-lg max-h-[70vh] overflow-y-auto">
          {loading && <div className="px-4 py-3 text-sm text-pb-faint">Searching…</div>}

          {!loading && data && flatResults.length === 0 && (
            <div className="px-4 py-3 text-sm text-pb-faint">No clubs or players found.</div>
          )}

          {!loading && data && data.clubs.length > 0 && (
            <div>
              <div className="px-4 pt-2.5 pb-1 font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest">Clubs</div>
              {data.clubs.map((c, i) => {
                const idx = i
                return (
                  <button key={c.id} type="button" onClick={() => pickClub(c)}
                    className={`w-full text-left px-4 py-2 text-sm flex items-center gap-2 ${activeIdx === idx ? 'bg-pb-surface2' : 'hover:bg-pb-surface2'}`}>
                    <Icon name="teams" size={14} className="text-pb-faint shrink-0" />
                    <span className="truncate">{c.name}</span>
                  </button>
                )
              })}
            </div>
          )}

          {!loading && addError && (
            <div className="px-4 py-2 text-xs text-pb-red border-t pb-hairline">{addError}</div>
          )}

          {!loading && data && data.players.length > 0 && (
            <div className="border-t pb-hairline">
              <div className="px-4 pt-2.5 pb-1 font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest">Players</div>
              {data.players.map((p, i) => {
                const idx = data.clubs.length + i
                const isAdding = addingId === p.player_id
                return (
                  <button key={p.player_id} type="button" onClick={() => pickPlayer(p)} disabled={isAdding}
                    className={`w-full text-left px-4 py-2 text-sm flex items-center gap-2.5 disabled:opacity-60 ${activeIdx === idx ? 'bg-pb-surface2' : 'hover:bg-pb-surface2'}`}>
                    <PlayerAvatar name={p.name} size={22} />
                    <span className="min-w-0 flex-1">
                      <span className="truncate block">{p.name}</span>
                      <span className="block font-mono text-[10px] text-pb-faint uppercase truncate">
                        {p.club_name || 'Unknown club'}{p.club_count > 1 ? ` +${p.club_count - 1} more` : ''}
                      </span>
                    </span>
                    {isAdding && <span className="font-mono text-[9px] uppercase tracking-wide2 text-pb-faint shrink-0">Adding…</span>}
                    {!isAdding && p.tracked && <span className="font-mono text-[9px] uppercase tracking-wide2 text-pb-faint shrink-0">Tracked</span>}
                    {!isAdding && !p.tracked && <span className="font-mono text-[9px] uppercase tracking-wide2 text-pb-accent shrink-0">+ Track</span>}
                  </button>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
