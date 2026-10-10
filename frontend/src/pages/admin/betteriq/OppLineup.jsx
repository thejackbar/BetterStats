/* BetterIQ: the opposition's NAMED XI for one fixture, matched to the players the
   scout has already scanned.

   Read live from the fixture's match record (GET /iq/opposition/lineup), so it
   moves as they publish: the list is not part of the cached dossier. Each named
   player carries the scouted figures they matched, and `pool` says where those
   figures came from: the grade scout the page is showing, or their other sides
   (a 1st XI player named in the 3rds). Only shown for a fixture scout. */
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../../lib/api'
import { Card, Tag, Note, Btn, Icon, LoadingBar } from './ui'
import { OppPlayerLink } from './PlayerLink'

const POLL_MS = 3000
const MAX_POLLS = 40

const n1 = v => (v == null || Number.isNaN(Number(v)) ? '—' : String(Math.round(Number(v) * 10) / 10))
const n2 = v => (v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toFixed(2))

function figures(p) {
  const bits = []
  if (p.bat && p.bat.innings) bits.push(`${p.bat.runs} runs${p.bat.average != null ? ` @ ${n1(p.bat.average)}` : ''}${p.bat.strike_rate != null ? ` · SR ${n1(p.bat.strike_rate)}` : ''}`)
  if (p.bowl && p.bowl.wickets != null && (p.bowl.overs || p.bowl.wickets)) bits.push(`${p.bowl.wickets} wkts${p.bowl.economy != null ? ` · econ ${n2(p.bowl.economy)}` : ''}`)
  return bits.join('  |  ')
}

const rank = p => (p.alert?.level === 'danger' || p.danger ? 0 : p.matched ? 1 : p.redacted ? 3 : 2)

function PlayerRow({ p, oppKey, oppName }) {
  const nm = p.redacted ? 'Name withheld (junior)' : p.name
  const label = (
    <span className="font-semibold text-[13.5px] min-w-0 break-words">{nm}</span>
  )
  const fig = figures(p)
  return (
    <div className="py-2.5" style={{ borderTop: '1px solid var(--pb-hairline)' }}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        {p.matched ? <OppPlayerLink playerId={p.player_id} oppKey={oppKey} oppName={oppName}>{label}</OppPlayerLink> : label}
        {p.is_captain && <Tag tone="faint">C</Tag>}
        {p.is_keeper && <Tag tone="faint">WK</Tag>}
        {p.alert?.level === 'danger' && <Tag tone="red">Danger</Tag>}
        {p.alert?.level === 'caution' && <Tag tone="amber">Caution</Tag>}
        {p.matched && p.pool === 'other_sides' && <Tag tone="amber">From another side</Tag>}
        {p.matched && p.basis && p.basis !== 'id' && <Tag tone="faint">Name match</Tag>}
        {!p.matched && !p.redacted && <Tag tone="faint">New to us</Tag>}
      </div>
      {p.matched && fig && <div className="text-pb-faint text-[12px] mt-1 leading-snug">{fig}</div>}
      {p.matched && p.pool === 'other_sides' && (
        <div className="text-pb-faint text-[11.5px] mt-0.5 leading-snug">These are their numbers in other grades and formats, so read them with care.</div>
      )}
      {p.matched && p.plan && p.alert && <div className="text-[12px] mt-1 leading-snug"><span className="text-pb-faint">Plan:</span> {p.plan}</div>}
    </div>
  )
}

export default function OppLineup({ fixtureId, opponent, name, team, grade, oppKey, oppName, ready }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(false)
  const [tick, setTick] = useState(0)          // bumped by "Check again"
  const refreshRef = useRef(false)

  useEffect(() => {
    if (!fixtureId || !ready) return undefined
    let alive = true
    let timer = null
    let polls = 0
    setData(null); setError(false)
    const load = () => {
      const refresh = refreshRef.current
      refreshRef.current = false
      api.iqOppositionLineup({ opponent, fixtureId, team, grade, name, refresh }).then(d => {
        if (!alive) return
        setData(d)
        if ((d.status === 'building' || d.pending) && ++polls < MAX_POLLS) timer = setTimeout(load, POLL_MS)
      }).catch(() => { if (alive) setError(true) })
    }
    load()
    return () => { alive = false; if (timer) clearTimeout(timer) }
  }, [fixtureId, opponent, name, team, grade, ready, tick])

  const players = useMemo(
    () => [...(data?.players || [])].sort((a, b) => rank(a) - rank(b) || ((b.bat?.runs || 0) + 20 * (b.bowl?.wickets || 0)) - ((a.bat?.runs || 0) + 20 * (a.bowl?.wickets || 0))),
    [data],
  )

  if (!fixtureId || !ready) return null
  const checkAgain = () => { refreshRef.current = true; setTick(t => t + 1) }
  const when = data?.date ? new Date(`${data.date}T00:00:00`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }) : null

  let body
  if (error) {
    body = <Note>Couldn't read their team list just now. Try again in a moment.</Note>
  } else if (!data || data.status === 'building') {
    body = <LoadingBar label="Reading their team list…" expectedMs={6000} />
  } else if (data.status === 'not_named') {
    body = (
      <div className="flex flex-wrap items-center gap-3">
        <div className="text-[13px]">{data.team_name || 'They'} haven't named their side yet. Clubs usually put it up a day or two before the game.</div>
        <Btn sm icon="refresh" onClick={checkAgain}>Check again</Btn>
      </div>
    )
  } else if (data.status === 'named') {
    body = (
      <>
        <div className="text-[12.5px] text-pb-faint mb-2">
          {data.named_count} named · {data.scouted_count} scouted
          {data.other_sides_count > 0 && ` · ${data.other_sides_count} from another side`}
          {data.new_count > 0 && ` · ${data.new_count} new to us`}
          {data.redacted_count > 0 && ` · ${data.redacted_count} junior${data.redacted_count > 1 ? 's' : ''} with names withheld`}
        </div>
        {data.danger_missing?.length > 0 && (
          <div className="flex gap-2 text-[13px] mb-1.5" style={{ color: 'var(--pb-brand)' }}>
            <Icon name="check" size={15} className="mt-0.5 shrink-0" />
            <span>Not named: {data.danger_missing.map(d => d.name).join(', ')}, from the players you've scouted as dangerous.</span>
          </div>
        )}
        {data.danger_named?.length > 0 && (
          <div className="flex gap-2 text-[13px] mb-1.5" style={{ color: 'var(--pb-red)' }}>
            <Icon name="info" size={15} className="mt-0.5 shrink-0" />
            <span>Named and dangerous: {data.danger_named.map(d => d.name).join(', ')}.</span>
          </div>
        )}
        {data.pending && <Note>Still checking their other sides for the players we haven't placed yet.</Note>}
        <div className="mt-2">
          {players.map((p, i) => <PlayerRow key={p.participant_id || `${p.name}-${i}`} p={p} oppKey={oppKey} oppName={oppName} />)}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Btn sm icon="refresh" onClick={checkAgain}>Check again</Btn>
        </div>
        <Note>Read from the match record Cricket Australia holds for this game, so it changes as they update it. Matched to the scouted squad by player id first, then by name.</Note>
      </>
    )
  } else {
    body = <Note>{data.reason || 'No team list is available for this game.'}</Note>
  }

  return (
    <Card accent eyebrow="their selection" title={data?.status === 'named' && data.match_status === 'COMPLETED' ? 'Who they played' : 'Who they have named'}
      >
      {/* Team and date sit in the body: as header tags they squeeze the title to a word a line on a phone. */}
      {(data?.team_name || when) && <div className="text-[12.5px] text-pb-dim -mt-2 mb-3">{[data.team_name, when].filter(Boolean).join(' · ')}</div>}
      {body}
    </Card>
  )
}
