// Points — the per-round breakdown: a big round score, Avg / High / Hit tiles,
// and the lineup (captain doubled, bench dashed + dimmed).
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { DISP, pts, GREEN, RED, ROLE_LABEL, CapBadge, Avatar, tintBg } from './ui'
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

export default function Points({ token, nav, desktop }) {
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
  const roundSelect = (
    <select value={data.round.number} onChange={e => setN(Number(e.target.value))} style={{
      background: 'var(--surface2)', border: '1px solid var(--hairline2)', borderRadius: 9, padding: '6px 11px',
      font: `600 11.5px 'Hanken Grotesk'`, color: 'var(--dim)', outline: 'none',
    }}>
      {data.rounds.map(r => <option key={r.number} value={r.number}>Round {r.number}{r.status === 'scored' ? '' : ' (upcoming)'}</option>)}
    </select>
  )

  if (desktop) return <PointsDesktop data={data} mine={mine} head={head} roundSelect={roundSelect} />

  return (
    <div>
      <ScreenTitle title={`Round ${data.round.number}`} right={roundSelect} />

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

// Desktop: a big score header, the lineup as a table, and a stats rail.
function PointsDesktop({ data, mine, head, roundSelect }) {
  const captain = mine?.lineup?.find(e => e.captained)
  return (
    <div style={{ background: 'var(--bg)', border: '1px solid var(--hairline)', borderRadius: 18, overflow: 'hidden', boxShadow: 'var(--frame-shadow)' }}>
      <div style={{ position: 'relative', overflow: 'hidden', borderBottom: '1px solid var(--hairline)' }}>
        <div style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 18, padding: '18px 26px' }}>
          <div style={{ font: `800 56px/0.82 ${DISP}`, color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{head}</div>
          <div style={{ lineHeight: 1 }}>
            <div style={{ font: `800 19px ${DISP}`, textTransform: 'uppercase', color: 'var(--text)' }}>Round {data.round.number} points</div>
            <div style={{ font: `500 12px 'Hanken Grotesk'`, color: 'var(--faint)', marginTop: 5 }}>Best 11 count · captain doubled</div>
          </div>
          <div style={{ marginLeft: 'auto' }}>{roundSelect}</div>
        </div>
      </div>
      <div style={{ height: 3, background: 'linear-gradient(90deg, var(--pb-accent, #8C82F0), #22D3EE 40%, #00E58E 65%, #EC4899)' }} />
      {!mine ? <p style={{ padding: 26, font: `500 13px 'Hanken Grotesk'`, color: 'var(--faint)' }}>This round hasn't been scored yet.</p> : (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px' }}>
          <div style={{ padding: '18px 26px', borderRight: '1px solid var(--hairline)' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '2.4fr 1fr 0.6fr', padding: '0 8px 9px' }}>
              {['Player', 'Role', 'Pts'].map((h, i) => <span key={h} style={{ font: `700 8.5px 'Hanken Grotesk'`, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--faint)', textAlign: i === 2 ? 'right' : 'left' }}>{h}</span>)}
            </div>
            {mine.lineup.map(e => {
              const val = e.eff_points != null ? e.eff_points : e.points
              return (
                <div key={e.player_id} style={{ display: 'grid', gridTemplateColumns: '2.4fr 1fr 0.6fr', alignItems: 'center', padding: '9px 8px', borderTop: '1px solid var(--surface2)', opacity: e.counted ? 1 : 0.5 }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <Avatar name={e.name} photoUrl={e.photo_url} size={30} dim={!e.counted} />
                    <span style={{ font: `700 13px 'Hanken Grotesk'`, color: e.counted ? 'var(--text)' : 'var(--dim)' }}>{e.name}</span>
                    {e.captained && <CapBadge />}
                  </span>
                  <span style={{ font: `500 11.5px 'Hanken Grotesk'`, color: 'var(--faint)' }}>{ROLE_LABEL[e.role]}{e.counted ? '' : ' · bench'}</span>
                  <span style={{ textAlign: 'right', font: `700 16px ${DISP}`, color: e.counted ? 'var(--text)' : 'var(--faint)', fontVariantNumeric: 'tabular-nums' }}>{pts(val)}</span>
                </div>
              )
            })}
          </div>
          <div style={{ padding: '18px 22px', display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
              <MiniTile label="Avg" value={data.stats.avg ?? '—'} />
              <MiniTile label="High" value={data.stats.high != null ? pts(data.stats.high) : '—'} color={GREEN} />
              <MiniTile label="Hit" value={mine.transfer_hit ? `−${mine.transfer_hit}` : '0'} color={mine.transfer_hit ? RED : 'var(--text)'} />
            </div>
            {captain && (
              <div style={{ background: tintBg(11, 'var(--surface)'), border: `1px solid ${tintBg(30)}`, borderRadius: 13, padding: 14 }}>
                <div style={{ font: `700 9px 'Hanken Grotesk'`, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--accent-strong)' }}>Captain of the week</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 11, marginTop: 9 }}>
                  <Avatar name={captain.name} photoUrl={captain.photo_url} size={40} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ font: `800 16px ${DISP}`, textTransform: 'uppercase', color: 'var(--text)' }}>{captain.name}</div>
                    <div style={{ font: `500 10.5px 'Hanken Grotesk'`, color: 'var(--faint)' }}>{pts(captain.points)} × 2 captain</div>
                  </div>
                  <div style={{ font: `800 24px ${DISP}`, color: 'var(--text)' }}>{pts(captain.eff_points)}</div>
                </div>
              </div>
            )}
            {mine.chip_used && (
              <div>
                <div style={{ font: `700 10px 'Hanken Grotesk'`, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--faint)', marginBottom: 8 }}>Chip played</div>
                <div style={{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 12, padding: '12px 14px', display: 'flex', alignItems: 'center' }}>
                  <span style={{ font: `800 14px ${DISP}`, textTransform: 'uppercase', color: 'var(--text)' }}>{mine.chip_used.replace('_', ' ')}</span>
                  <span style={{ marginLeft: 'auto', font: `700 10px 'Hanken Grotesk'`, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--accent-strong)' }}>Active</span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
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
