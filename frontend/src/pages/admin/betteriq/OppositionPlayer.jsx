import { useState, useEffect, useMemo, useRef } from 'react'
import IQLayout from '../../../components/admin/IQLayout'
import { api } from '../../../lib/api'
import { Empty, Search, Btn } from '../betterselect/ui'
import { OppPlayerDetail, buildOppPlayerIndex } from './OppPlayerProfile'

const POLL_MS = 2500

function Card({ title, right, children }) {
  return (
    <div className="pb-card p-4 md:p-5">
      {(title || right) && (
        <div className="flex items-center justify-between gap-3 mb-3">
          <h3 className="font-display font-bold">{title}</h3>
          {right}
        </div>
      )}
      {children}
    </div>
  )
}

// A focus-driven combobox (same pattern as the player-trends picker).
function Combo({ value, onChange, placeholder, matches, render, onPick, empty }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="relative" onFocusCapture={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}>
      <Search value={value} onChange={(v) => { onChange(v); setOpen(true) }} placeholder={placeholder} className="w-full" />
      {open && (
        <div className="absolute z-30 mt-1 w-full pb-card p-1 max-h-80 overflow-auto shadow-lg" style={{ background: 'var(--pb-surface)' }}>
          {matches.length === 0 ? <div className="px-2.5 py-2 text-pb-faint text-sm">{empty || 'No match.'}</div>
            : matches.map(m => (
              <button key={m.key} type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => { onPick(m); setOpen(false) }}
                className="w-full flex items-center justify-between gap-3 px-2.5 py-1.5 rounded-lg hover:bg-pb-surface2 text-left">
                {render(m)}
              </button>
            ))}
        </div>
      )}
    </div>
  )
}

export default function OppositionPlayer() {
  const [opponents, setOpponents] = useState([])
  const [club, setClub] = useState(null)        // { opp_key, name }
  const [dossier, setDossier] = useState(null)
  const [status, setStatus] = useState(null)    // 'building' | 'ready' | 'error' | 'unavailable'
  const [sel, setSel] = useState(null)          // player_id
  const [clubQ, setClubQ] = useState('')
  const [playerQ, setPlayerQ] = useState('')
  const pollRef = useRef(null)

  useEffect(() => { api.iqListOpponents().then(d => setOpponents(d?.opponents || [])).catch(() => setOpponents([])) }, [])
  const stopPoll = () => { if (pollRef.current) { clearTimeout(pollRef.current); pollRef.current = null } }
  useEffect(() => stopPoll, [])

  const loadClub = (c) => {
    stopPoll()
    setClub(c); setSel(null); setDossier(null); setStatus('building'); setClubQ(''); setPlayerQ('')
    const params = { opponent: c.opp_key }
    const poll = () => {
      api.iqOppositionDossier(params).then(d => {
        setDossier(d); setStatus(d.status)
        if (d.status === 'building') pollRef.current = setTimeout(poll, POLL_MS)
      }).catch(() => setStatus('error'))
    }
    poll()
  }

  const index = useMemo(() => buildOppPlayerIndex(dossier), [dossier])
  const enriched = useMemo(() => {
    const m = new Map()
    for (const d of [...(dossier?.danger_batters || []), ...(dossier?.danger_bowlers || [])]) m.set(d.player_id, d)
    return m
  }, [dossier])
  const all = useMemo(() => [...index.entries()].map(([id, v]) => ({ id, ...v })), [index])
  const selected = sel ? index.get(sel) : null

  const cq = clubQ.trim().toLowerCase()
  const clubMatches = (cq ? opponents.filter(o => (o.name || '').toLowerCase().includes(cq)) : opponents)
    .slice(0, 30).map(o => ({ key: o.opp_key, ...o }))
  const pq = playerQ.trim().toLowerCase()
  const playerMatches = (pq ? all.filter(p => p.name.toLowerCase().includes(pq)) : all).slice(0, 40).map(p => ({ key: p.id, ...p }))

  return (
    <IQLayout title="Opposition player">
      <p className="text-pb-faint text-sm mb-4 max-w-2xl">Pick an opponent club, then search any of their players for a full profile — season form, dismissal patterns and their complete record against us. (Built live from their scorecards — we don't hold opponents' full history, so it's current-season + head-to-head.)</p>

      {/* Club picker */}
      <div className="flex flex-wrap items-center gap-2 mb-4 max-w-xl">
        {club ? (
          <div className="flex items-center gap-2">
            <span className="font-display font-bold">{club.name}</span>
            <Btn variant="ghost" sm icon="back" onClick={() => { stopPoll(); setClub(null); setDossier(null); setSel(null); setStatus(null) }}>Change club</Btn>
          </div>
        ) : (
          <div className="flex-1 min-w-[260px]">
            <Combo value={clubQ} onChange={setClubQ} placeholder="Search an opponent club…" matches={clubMatches}
              empty={opponents.length === 0 ? 'No opponents with history yet.' : 'No match.'}
              onPick={loadClub}
              render={(o) => (<>
                <span className="font-medium truncate">{o.name}</span>
                <span className="text-pb-faintest text-[11px] pb-num whitespace-nowrap">{o.meetings} mtgs{o.coverage === 'rich' ? ' · rich' : ''}</span>
              </>)} />
          </div>
        )}
      </div>

      {!club && <div className="pb-card p-5"><Empty>Pick an opponent club above to scout their players.</Empty></div>}
      {club && status === 'building' && <div className="pb-card p-5 animate-pulse text-pb-faint text-sm">Building {club.name}'s squad live from their scorecards… first time can take ~30s.</div>}
      {club && (status === 'error' || status === 'unavailable') && <div className="pb-card p-5"><Empty>Couldn't build a live dossier for {club.name} right now — try again shortly.</Empty></div>}

      {club && status === 'ready' && (
        <div className="space-y-4">
          <div className="max-w-xl">
            <Combo value={playerQ} onChange={setPlayerQ} placeholder={`Search ${club.name} players…`} matches={playerMatches}
              empty={all.length === 0 ? 'No current-season players for this club.' : 'No match.'}
              onPick={(p) => { setSel(p.id); setPlayerQ('') }}
              render={(p) => (<>
                <span className="font-medium truncate">{p.name}</span>
                <span className="text-pb-faintest text-[11px] pb-num whitespace-nowrap">{p.bat?.runs ? `${p.bat.runs}r` : ''}{p.bowl?.wickets ? ` · ${p.bowl.wickets}w` : ''}</span>
              </>)} />
          </div>
          {selected
            ? <Card><OppPlayerDetail entry={selected} enriched={enriched.get(sel)} opponentName={club.name} /></Card>
            : <div className="pb-card p-5"><Empty>Search and pick one of {club.name}'s players for their full profile.</Empty></div>}
          {dossier?.coverage?.notes?.length > 0 && (
            <div className="text-pb-faintest text-[11px]">{dossier.coverage.notes.join(' ')}</div>
          )}
        </div>
      )}
    </IQLayout>
  )
}
