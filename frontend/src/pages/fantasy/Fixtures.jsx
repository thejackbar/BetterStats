// Fixtures — the round list. The live round is an accent card with a red LIVE
// tag, upcoming rounds are plain, scored rounds dim with the manager's points.
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { DISP, tintBg, pts } from './ui'
import { ScreenTitle } from './shell'

const when = (r) => {
  if (r.status === 'scored') return 'Scored'
  if (r.lock_at) {
    const d = new Date(r.lock_at)
    const txt = d.toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })
    return r.status === 'live' ? `Live now · locked ${txt}` : `Locks ${txt}`
  }
  return r.status === 'live' ? 'Live now' : 'To be scheduled'
}

export default function Fixtures({ token, season, nav, desktop }) {
  const [rounds, setRounds] = useState(null)
  useEffect(() => { api.fanRounds(token).then(d => setRounds(d.rounds || [])).catch(() => setRounds([])) }, [token])

  if (rounds === null) return <p style={{ color: 'var(--faint)', font: `500 13px 'Hanken Grotesk'` }}>Loading…</p>

  return (
    <div>
      <ScreenTitle title="Rounds" sub={`${season?.name || 'Season'} · ${rounds.length} rounds`} back onBack={() => nav('team')} />
      {!rounds.length
        ? <p style={{ font: `500 13px 'Hanken Grotesk'`, color: 'var(--faint)', paddingTop: 16 }}>The club admin generates rounds from the fixture list.</p>
        : (
          <div style={desktop
            ? { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 10, paddingTop: 14 }
            : { display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 14 }}>
            {rounds.map(r => {
              const live = r.status === 'live'
              const scored = r.status === 'scored'
              const go = live ? () => nav('live') : scored ? () => nav('points') : undefined
              return (
                <button key={r.number} onClick={go} style={{
                  display: 'flex', alignItems: 'center', gap: 12, padding: '13px 14px', borderRadius: 14, width: '100%', textAlign: 'left',
                  cursor: go ? 'pointer' : 'default', border: 'none', opacity: scored ? 0.78 : 1,
                  background: live ? tintBg(13, 'var(--bg)') : 'var(--surface)',
                  boxShadow: live ? `inset 0 0 0 1px ${tintBg(38)}` : 'inset 0 0 0 1px var(--hairline)',
                }}>
                  <div style={{
                    width: 38, height: 38, borderRadius: 11, flex: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', font: `800 15px ${DISP}`,
                    background: live ? 'var(--pb-accent, #8C82F0)' : 'var(--surface2)', color: live ? 'var(--ink)' : 'var(--dim)',
                  }}>{r.number}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                      <span style={{ font: `800 14px ${DISP}`, textTransform: 'uppercase', color: 'var(--text)' }}>{r.name || `Round ${r.number}`}</span>
                      {live && <span style={{ font: `700 8px 'Hanken Grotesk'`, letterSpacing: '.1em', color: '#fff', background: '#ef5b5b', padding: '2px 6px', borderRadius: 4 }}>LIVE</span>}
                    </div>
                    <div style={{ font: `500 10.5px 'Hanken Grotesk'`, color: live ? 'var(--accent-strong)' : 'var(--faint)', marginTop: 2 }}>{when(r)}</div>
                  </div>
                  {r.my_points != null && (
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ font: `700 16px ${DISP}`, color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{pts(r.my_points)}</div>
                      <div style={{ font: `600 8px 'Hanken Grotesk'`, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--faint)' }}>pts</div>
                    </div>
                  )}
                </button>
              )
            })}
          </div>
        )}
    </div>
  )
}
