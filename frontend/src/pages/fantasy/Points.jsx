// Points — the per-round breakdown: a big round score, Avg / High / Hit tiles,
// and the lineup (captain doubled, bench dashed + dimmed).
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { DISP, pts, GREEN, RED, ROLE_LABEL, CapBadge } from './ui'
import { ScreenTitle, PlayerRow, RowPoints } from './shell'

export function LineupList({ lineup }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {lineup.map(e => {
        const counted = e.counted
        const val = e.eff_points != null ? e.eff_points : e.points
        return (
          <PlayerRow
            key={e.player_id} name={e.name} photoUrl={e.photo_url}
            sub={ROLE_LABEL[e.role] + (counted ? '' : ' · bench')}
            tone={counted ? 'plain' : 'bench'}
            badge={e.captained ? <CapBadge /> : null}
            avatarSize={32}
            right={<RowPoints value={pts(val)} color={counted ? 'var(--text)' : 'var(--faint)'} />}
          />
        )
      })}
    </div>
  )
}

export default function Points({ token, nav }) {
  const [data, setData] = useState(null)
  const [n, setN] = useState(null)

  useEffect(() => {
    let on = true
    api.fanRound(token, n).then(d => on && setData(d)).catch(() => on && setData({ round: null, rounds: [] }))
    return () => { on = false }
  }, [token, n])

  if (!data) return <p style={{ color: 'var(--faint)', font: `500 13px 'Hanken Grotesk'` }}>Loading…</p>
  if (!data.round) return <Empty nav={nav} />
  const mine = data.mine
  const head = mine ? pts(mine.points) : '—'

  return (
    <div>
      <ScreenTitle
        title={`Round ${data.round.number}`}
        right={(
          <select value={data.round.number} onChange={e => setN(Number(e.target.value))} style={{
            background: 'var(--surface2)', border: '1px solid var(--hairline2)', borderRadius: 9, padding: '6px 11px',
            font: `600 11.5px 'Hanken Grotesk'`, color: 'var(--dim)', outline: 'none',
          }}>
            {data.rounds.map(r => <option key={r.number} value={r.number}>Round {r.number}{r.status === 'scored' ? '' : ' (upcoming)'}</option>)}
          </select>
        )}
      />

      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 14, padding: '18px 0 6px' }}>
        <div>
          <div style={{ font: `800 52px/0.85 ${DISP}`, color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{head}</div>
          <div style={{ font: `600 10px 'Hanken Grotesk'`, letterSpacing: '.14em', textTransform: 'uppercase', color: 'var(--faint)', marginTop: 4 }}>Round points</div>
        </div>
        <div style={{ flex: 1, display: 'flex', gap: 7, paddingBottom: 4 }}>
          <MiniTile label="Avg" value={data.stats.avg ?? '—'} />
          <MiniTile label="High" value={data.stats.high != null ? pts(data.stats.high) : '—'} color={GREEN} />
          <MiniTile label="Hit" value={mine?.transfer_hit ? `−${mine.transfer_hit}` : '0'} color={mine?.transfer_hit ? RED : 'var(--text)'} />
        </div>
      </div>

      {mine?.chip_used && (
        <div style={{ font: `700 11px 'Hanken Grotesk'`, color: 'var(--accent-strong)', textTransform: 'capitalize', padding: '2px 0 8px' }}>
          {mine.chip_used.replace('_', ' ')} played
        </div>
      )}

      <div style={{ paddingTop: 10 }}>
        {!mine
          ? <p style={{ font: `500 13px 'Hanken Grotesk'`, color: 'var(--faint)' }}>This round hasn't been scored yet.</p>
          : <LineupList lineup={mine.lineup} />}
      </div>
    </div>
  )
}

function MiniTile({ label, value, color = 'var(--text)' }) {
  return (
    <div style={{ flex: 1, background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 11, padding: '8px 10px' }}>
      <div style={{ font: `600 8.5px 'Hanken Grotesk'`, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--faint)' }}>{label}</div>
      <div style={{ font: `700 16px ${DISP}`, color }}>{value}</div>
    </div>
  )
}

function Empty({ nav }) {
  return (
    <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--faint)' }}>
      <p style={{ font: `500 13px 'Hanken Grotesk'` }}>No rounds have been scored yet.</p>
      <button onClick={() => nav('fixtures')} style={{ marginTop: 8, background: 'none', border: 'none', color: 'var(--accent-strong)', font: `600 12px 'Hanken Grotesk'`, cursor: 'pointer' }}>See the fixtures →</button>
    </div>
  )
}
