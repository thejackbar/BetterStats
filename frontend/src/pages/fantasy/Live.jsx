// Live gameweek — provisional points while a round is in progress. Polls the
// read-only live endpoint and stops once the round is scored.
import { useEffect, useRef, useState } from 'react'
import { api } from '../../lib/api'
import { Aurora, DISP, GREEN, RED, pts } from './ui'
import { LineupList } from './Points'

export default function Live({ token, nav }) {
  const [data, setData] = useState(null)
  const timer = useRef(null)

  useEffect(() => {
    let on = true
    const load = async () => {
      try {
        const d = await api.fanLive(token)
        if (on) setData(d)
        // Keep polling only while the round is genuinely in progress.
        if (on && !d?.live && timer.current) { clearInterval(timer.current); timer.current = null }
      } catch { /* keep last frame */ }
    }
    load()
    timer.current = setInterval(load, 45000)
    return () => { on = false; if (timer.current) clearInterval(timer.current) }
  }, [token])

  if (!data) return <p style={{ color: 'var(--faint)', font: `500 13px 'Hanken Grotesk'` }}>Loading…</p>
  const mine = data.mine
  if (!data.round || !mine) {
    return (
      <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--faint)' }}>
        <p style={{ font: `500 13px 'Hanken Grotesk'` }}>Nothing live right now.</p>
        <button onClick={() => nav('points')} style={{ marginTop: 8, background: 'none', border: 'none', color: 'var(--accent-strong)', font: `600 12px 'Hanken Grotesk'`, cursor: 'pointer' }}>See your latest points →</button>
      </div>
    )
  }
  const isLive = data.live
  const rank = data.provisional_rank ?? data.overall_rank

  return (
    <div>
      <div style={{ position: 'relative', overflow: 'hidden', borderRadius: 16, padding: '14px 0 6px' }}>
        <Aurora style={{ inset: '-30% -15% auto', height: '180%' }} blur={46} blobs={[
          { c: 'var(--pb-accent, #06B6D4)', a: 'bfcAuroraA', s: 17, pos: { width: '55%', height: '60%', left: '6%', top: '0' } },
          { c: '#00E58E', a: 'bfcAuroraD', s: 21, pos: { width: '50%', height: '55%', right: '2%', top: '6%' } },
        ]} />
        <div style={{ position: 'relative' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {isLive && <span style={{ width: 9, height: 9, borderRadius: '50%', background: RED, boxShadow: `0 0 10px ${RED}` }} />}
            <span style={{ font: `700 10px 'Hanken Grotesk'`, letterSpacing: '.18em', textTransform: 'uppercase', color: isLive ? RED : 'var(--faint)' }}>
              {isLive ? 'Live · ' : ''}Round {data.round.number}
            </span>
            {isLive && data.playing_now != null && (
              <span style={{ marginLeft: 'auto', font: `600 10px 'Hanken Grotesk'`, color: 'var(--faint)' }}>{data.playing_now} playing now</span>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 14, marginTop: 8 }}>
            <div>
              <div style={{ font: `800 58px/0.82 ${DISP}`, color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{pts(mine.points)}</div>
              <div style={{ font: `600 9.5px 'Hanken Grotesk'`, letterSpacing: '.14em', textTransform: 'uppercase', color: 'var(--faint)', marginTop: 4 }}>{isLive ? 'Live points' : 'Round points'}</div>
            </div>
            {rank && (
              <div style={{ paddingBottom: 6 }}>
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '4px 9px', borderRadius: 7, font: `800 12px ${DISP}`, background: `color-mix(in srgb, ${GREEN} 16%, transparent)`, color: GREEN }}>▲ {rank}{ordSuffix(rank)}</div>
                <div style={{ font: `500 10.5px 'Hanken Grotesk'`, color: 'var(--faint)', marginTop: 6 }}>club standing</div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div style={{ paddingTop: 6 }}>
        <LineupList lineup={mine.lineup} />
      </div>
    </div>
  )
}

const ordSuffix = (n) => (n % 100 >= 11 && n % 100 <= 13) ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th')
