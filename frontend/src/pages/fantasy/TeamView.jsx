// Another manager's team as they locked it for the most recently locked round, with the points it has
// scored. Opened from the club ladder and from a league's standings once a round has locked. It shows
// nothing later: no transfers they have lined up, no changes made after the round was scored.
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { DISP, pts, tintBg } from './ui'
import { ScreenTitle } from './shell'
import { LineupList } from './Points'

const CHIP = { wildcard: 'Wildcard', triple_captain: 'Triple Captain', bench_boost: 'Bench Boost', free_hit: 'Free Hit' }

export default function TeamView({ token, squadId, onBack }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    let on = true, timer = null
    setD(null); setErr('')
    const load = () => api.fanTeam(token, squadId).then(x => {
      if (!on) return
      setD(x)
      if (x?.round?.status !== 'live' && timer) { clearInterval(timer); timer = null }
    }).catch(e => on && setErr(e.message || 'Could not load this team.'))
    load()
    timer = setInterval(load, 60000)
    return () => { on = false; if (timer) clearInterval(timer) }
  }, [token, squadId])

  if (err) {
    return (
      <div>
        <ScreenTitle title="Team" back onBack={onBack} />
        <p style={{ color: 'var(--faint)', font: `500 13px 'Hanken Grotesk'`, paddingTop: 16 }}>{err}</p>
      </div>
    )
  }
  if (!d) return <p style={{ color: 'var(--faint)', font: `500 13px 'Hanken Grotesk'` }}>Loading…</p>

  const live = d.round?.status === 'live'
  return (
    <div>
      <ScreenTitle title={d.team_name} sub={`${d.manager}${d.you ? ' · you' : ''}`} back onBack={onBack} />
      <div style={{ marginTop: 14, padding: 16, borderRadius: 16, background: 'var(--surface)', border: '1px solid var(--hairline)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {live && <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#ef5b5b', boxShadow: '0 0 8px #ef5b5b' }} />}
          <span style={{ font: `700 10px 'Hanken Grotesk'`, letterSpacing: '.16em', textTransform: 'uppercase', color: live ? '#ef5b5b' : 'var(--faint)' }}>
            {live ? 'Live · ' : ''}Round {d.round.number}
          </span>
          {d.chip_used && (
            <span style={{ marginLeft: 'auto', font: `700 10px 'Hanken Grotesk'`, color: 'var(--accent-strong)', background: tintBg(14), border: `1px solid ${tintBg(30)}`, padding: '3px 8px', borderRadius: 6 }}>
              {CHIP[d.chip_used] || d.chip_used}
            </span>
          )}
        </div>
        {d.lineup && (
          <div style={{ display: 'flex', gap: 24, marginTop: 10 }}>
            <div>
              <div style={{ font: `800 40px/0.9 ${DISP}`, color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{pts(d.points)}</div>
              <div style={{ font: `600 9px 'Hanken Grotesk'`, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--faint)', marginTop: 4 }}>{live ? 'Live points' : 'Round points'}</div>
            </div>
            <div>
              <div style={{ font: `800 40px/0.9 ${DISP}`, color: 'var(--dim)', fontVariantNumeric: 'tabular-nums' }}>{pts(d.total_points)}</div>
              <div style={{ font: `600 9px 'Hanken Grotesk'`, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--faint)', marginTop: 4 }}>Total</div>
            </div>
          </div>
        )}
        <p style={{ font: `500 11px 'Hanken Grotesk'`, color: 'var(--faint)', margin: '12px 0 0' }}>
          {d.lineup
            ? `This is the team they locked for round ${d.round.number}. Anything they change after that stays private until the next round locks.`
            : d.note}
        </p>
      </div>
      {d.lineup && <div style={{ paddingTop: 12 }}><LineupList lineup={d.lineup} /></div>}
    </div>
  )
}
