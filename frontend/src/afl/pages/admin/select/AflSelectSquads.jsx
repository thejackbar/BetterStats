import { useEffect, useMemo, useState } from 'react'
import { aflApi } from '../../../aflApi'
import { useToast } from '../../../../contexts/ToastContext'
import LoadingSpinner from '../../../../components/LoadingSpinner'
import { Btn, Card, INPUT, PageHead, PositionChips } from './ui'

// A football club's sides, top to bottom, and who is in each squad. The
// order matters beyond looks: it is what makes one side "higher" than another
// for the rules that count games played in a higher side.
//
// A player not in a squad is filed three ways rather than listed in one long
// column: playing (seen inside the club's dormancy window), lapsed (played
// before, not lately) and never played (a new signing, or a name nobody has
// used). Nobody is hidden; everybody can be moved.

export default function AflSelectSquads() {
  const toast = useToast()
  const [teams, setTeams] = useState(null)
  const [players, setPlayers] = useState([])
  const [months, setMonths] = useState(24)
  const [q, setQ] = useState('')
  const [newName, setNewName] = useState('')
  const [busy, setBusy] = useState(false)
  const [showLapsed, setShowLapsed] = useState(false)

  async function load() {
    const [t, s] = await Promise.all([aflApi.selTeams(), aflApi.selSquads()])
    setTeams(t)
    setPlayers(s.players)
    setMonths(s.dormancy_months)
  }
  useEffect(() => { load().catch(e => toast.error(e.message)) }, [])

  async function run(fn, ok) {
    setBusy(true)
    try { const r = await fn(); if (ok) toast.success(ok(r)); await load() }
    catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  async function move(p, teamId) {
    setPlayers(ps => ps.map(x => x.id === p.id ? { ...x, squad_id: teamId } : x))
    try { await aflApi.selSetSquad(p.id, teamId) } catch (e) { toast.error(e.message); load() }
  }

  async function reorder(idx, dir) {
    const next = [...teams]
    const [row] = next.splice(idx, 1)
    next.splice(idx + dir, 0, row)
    setTeams(next)
    try { await aflApi.selReorderTeams(next.map(t => t.id)) } catch (e) { toast.error(e.message); load() }
  }

  const match = p => !q || p.name.toLowerCase().includes(q.toLowerCase())
  const active = players.filter(p => p.status !== 'inactive')
  const groups = useMemo(() => {
    const out = { playing: [], lapsed: [], never: [] }
    for (const p of active) {
      if (p.squad_id || !match(p)) continue
      if (p.lapsed) out.lapsed.push(p)
      else if (!p.last_played) out.never.push(p)
      else out.playing.push(p)
    }
    return out
  }, [players, q])

  if (!teams) return <div className="pt-16 flex justify-center"><LoadingSpinner /></div>

  const sides = teams.filter(t => t.is_active)
  const PlayerRow = ({ p }) => (
    <div className="flex items-center gap-2 py-1.5 pb-hairline-b last:border-0" data-testid="squad-player">
      <div className="min-w-0 flex-1">
        <div className="text-sm truncate">{p.jumper ? <span className="font-mono text-pb-faint mr-1">#{p.jumper}</span> : null}{p.name}</div>
        <div className="flex items-center gap-2 mt-0.5">
          <PositionChips positions={p.positions} />
          <span className="font-mono text-[10px] text-pb-faint">{p.games_this_year} games this year</span>
        </div>
      </div>
      <select aria-label={`Squad for ${p.name}`} value={p.squad_id || ''} onChange={e => move(p, e.target.value || null)}
        className={`${INPUT} !py-1 !text-xs max-w-[9rem]`}>
        <option value="">No squad</option>
        {sides.map(t => <option key={t.id} value={t.id}>{t.short_name || t.name}</option>)}
      </select>
    </div>
  )

  return (
    <div>
      <PageHead title="Squads"
        caption="Your sides in order, top side first, and who is in each squad. The order decides which side is higher for the rules that count games in a higher side."
        right={<>
          <Btn onClick={() => run(aflApi.selSeedTeams, r => r.created ? `Added ${r.created} side${r.created === 1 ? '' : 's'} from PlayHQ` : 'Every PlayHQ side is already here')} disabled={busy}>Add sides from PlayHQ</Btn>
          <Btn onClick={() => run(aflApi.selAutoAssign, r => `Filed ${r.assigned} player${r.assigned === 1 ? '' : 's'}`)} disabled={busy || !sides.length}
            title="Put every player with no squad in the side they played most for this season">Fill squads from this season</Btn>
        </>} />

      <Card className="p-4 mb-5">
        <h2 className="font-mono text-xs uppercase tracking-wide3 text-pb-faint mb-2">Sides</h2>
        {teams.length === 0 && <p className="text-sm text-pb-dim mb-2">No sides yet. Add them from PlayHQ, or by name below.</p>}
        {teams.map((t, i) => (
          <div key={t.id} className="flex flex-wrap items-center gap-2 py-1.5 pb-hairline-b" data-testid="side-row">
            <span className="font-mono text-xs text-pb-faint w-5">{i + 1}</span>
            <span className={`flex-1 min-w-0 text-sm ${t.is_active ? '' : 'text-pb-faint line-through'}`}>{t.name}</span>
            <span className="font-mono text-[10px] text-pb-faint">{t.squad_count} in squad</span>
            <Btn small onClick={() => reorder(i, -1)} disabled={i === 0} aria-label={`Move ${t.name} up`}>↑</Btn>
            <Btn small onClick={() => reorder(i, 1)} disabled={i === teams.length - 1} aria-label={`Move ${t.name} down`}>↓</Btn>
            <Btn small onClick={() => run(() => aflApi.selUpdateTeam(t.id, { is_active: !t.is_active }))}>{t.is_active ? 'Retire' : 'Restore'}</Btn>
            <Btn small danger onClick={() => {
              if (window.confirm(`Delete ${t.name}? Its players go back to no squad; nothing they played is lost.`))
                run(() => aflApi.selDeleteTeam(t.id))
            }}>Delete</Btn>
          </div>
        ))}
        <form className="flex gap-2 mt-3" onSubmit={e => { e.preventDefault(); if (newName.trim()) run(() => aflApi.selCreateTeam({ name: newName.trim() }).then(r => { setNewName(''); return r })) }}>
          <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="New side, e.g. Under 19s" className={`${INPUT} flex-1 min-w-0`} />
          <Btn type="submit" disabled={busy || !newName.trim()}>Add side</Btn>
        </form>
      </Card>

      <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search players" className={`${INPUT} w-full sm:w-72 mb-4`} />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {sides.map(t => {
          const list = active.filter(p => p.squad_id === t.id && match(p))
          return (
            <Card key={t.id} className="p-3" data-testid="squad-column">
              <div className="flex items-baseline justify-between mb-1">
                <h3 className="font-semibold text-sm">{t.name}</h3>
                <span className="font-mono text-[10px] text-pb-faint">{list.length}</span>
              </div>
              {list.length === 0 ? <p className="text-xs text-pb-faint py-2">Nobody in this squad yet.</p>
                : list.map(p => <PlayerRow key={p.id} p={p} />)}
            </Card>
          )
        })}
        <Card className="p-3">
          <h3 className="font-semibold text-sm mb-1">Not in a squad</h3>
          <p className="text-xs text-pb-faint mb-2">Played inside the last {months} months.</p>
          {groups.playing.length === 0 ? <p className="text-xs text-pb-faint py-2">Everyone who has played lately is in a squad.</p>
            : groups.playing.map(p => <PlayerRow key={p.id} p={p} />)}
          {groups.never.length > 0 && <>
            <h4 className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mt-3 mb-1">Not yet played ({groups.never.length})</h4>
            {groups.never.map(p => <PlayerRow key={p.id} p={p} />)}
          </>}
          <button onClick={() => setShowLapsed(v => !v)} className="mt-3 text-xs underline text-pb-dim">
            {showLapsed ? 'Hide' : 'Show'} players who haven't played for {months} months ({groups.lapsed.length})
          </button>
          {showLapsed && groups.lapsed.map(p => <PlayerRow key={p.id} p={p} />)}
        </Card>
      </div>
    </div>
  )
}
