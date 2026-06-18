// Shareable cards — a Gameweek-result square (430×430) and a recruit-a-mate story
// (300×533), both over the aurora. Rendered to PNG with modern-screenshot for
// web-share / download (the same exporter the admin social posts use).
import { useEffect, useRef, useState } from 'react'
import { api } from '../../lib/api'
import { Aurora, DISP, GREEN, pts, Btn, useFantasy } from './ui'
import { ScreenTitle } from './shell'

const ordSuffix = (n) => (n % 100 >= 11 && n % 100 <= 13) ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th')

export default function Share({ token, squad, nav }) {
  const { club, crest } = useFantasy()
  const [round, setRound] = useState(null)
  const [ladder, setLadder] = useState(null)
  const [leagues, setLeagues] = useState([])
  const gwRef = useRef(null)
  const storyRef = useRef(null)
  const [busy, setBusy] = useState('')

  useEffect(() => {
    api.fanRound(token).then(setRound).catch(() => {})
    api.fanLadder(token).then(d => setLadder(d.ladder || [])).catch(() => {})
    api.fanLeagues(token).then(d => setLeagues(d.leagues || [])).catch(() => {})
  }, [token])

  const total = ladder?.length || 0
  const rank = squad?.overall_rank
  const beat = total && rank ? Math.round(((total - rank) / total) * 100) : null
  const captain = round?.mine?.lineup?.find(e => e.captained)
  const gwPoints = round?.mine ? pts(round.mine.points) : (squad ? pts(squad.last_round?.points ?? 0) : '0')
  const gwNum = round?.round?.number
  const code = leagues[0]?.join_code
  const host = (typeof window !== 'undefined' && window.location?.host) || 'betterat.cricket'

  const exportCard = async (ref, name, w, h) => {
    if (!ref.current) return
    setBusy(name)
    try {
      await document.fonts.ready
      const { domToBlob } = await import('modern-screenshot')
      const blob = await domToBlob(ref.current, { type: 'image/png', scale: 2, width: w, height: h, backgroundColor: '#0a0d14' })
      if (!blob) return
      const file = new File([blob], `${name}.png`, { type: 'image/png' })
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        await navigator.share({ files: [file] })
      } else {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a'); a.href = url; a.download = `${name}.png`
        document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(url)
      }
    } catch { /* user dismissed share */ } finally { setBusy('') }
  }

  return (
    <div>
      <ScreenTitle title="Share" sub="Spread the word" back onBack={() => nav('team')} />

      {/* GW result card */}
      <div style={{ paddingTop: 16 }}>
        <div style={{ font: `600 11px 'Hanken Grotesk'`, letterSpacing: '.14em', textTransform: 'uppercase', color: 'var(--faint)', marginBottom: 10 }}>Gameweek result</div>
        <div style={{ overflowX: 'auto' }}>
          <div ref={gwRef} data-theme="dark" style={{ position: 'relative', width: 430, height: 430, background: '#0a0d14', borderRadius: 22, overflow: 'hidden', boxShadow: 'var(--frame-shadow)' }}>
            <Aurora style={{ inset: '-10%', height: 'auto', bottom: '-10%' }} opacity={0.7} blur={48} blobs={[
              { c: 'var(--pb-accent, #8C82F0)', a: 'bfcAuroraA', s: 17, pos: { width: '55%', height: '55%', left: '-6%', top: '-6%' } },
              { c: '#22D3EE', a: 'bfcAuroraB', s: 21, pos: { width: '52%', height: '52%', right: '-6%', top: '8%' } },
              { c: '#EC4899', a: 'bfcAuroraC', s: 19, pos: { width: '55%', height: '55%', left: '20%', bottom: '-12%' } },
            ]} />
            <div style={{ position: 'relative', height: '100%', padding: 26, display: 'flex', flexDirection: 'column', fontFamily: "'Hanken Grotesk',sans-serif" }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{ width: 34, height: 34, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#fff', color: '#0a0d14', font: `800 12px ${DISP}` }}>{crest}</div>
                <div style={{ font: `800 15px ${DISP}`, letterSpacing: '.04em', textTransform: 'uppercase', color: '#fff' }}>{club?.name || 'Club'} Fantasy</div>
                <div style={{ marginLeft: 'auto', font: `700 10px 'Hanken Grotesk'`, letterSpacing: '.16em', textTransform: 'uppercase', color: 'rgba(255,255,255,.6)' }}>{gwNum ? `Gameweek ${gwNum}` : 'Fantasy'}</div>
              </div>
              <div style={{ marginTop: 'auto' }}>
                <div style={{ font: `600 11px 'Hanken Grotesk'`, letterSpacing: '.22em', textTransform: 'uppercase', color: 'rgba(255,255,255,.7)' }}>{squad?.team_name || 'My XI'} scored</div>
                <div style={{ display: 'flex', alignItems: 'flex-end', gap: 14 }}>
                  <div style={{ font: `800 110px/0.8 ${DISP}`, color: '#fff', letterSpacing: '-.01em', fontVariantNumeric: 'tabular-nums' }}>{gwPoints}</div>
                  {rank && (
                    <div style={{ paddingBottom: 16 }}>
                      <div style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: GREEN, color: '#04140d', padding: '4px 9px', borderRadius: 7, font: `800 12px ${DISP}`, letterSpacing: '.04em' }}>▲ {rank}{ordSuffix(rank)}</div>
                      <div style={{ font: `600 12px 'Hanken Grotesk'`, color: 'rgba(255,255,255,.8)', marginTop: 6 }}>{total ? `of ${total}` : 'on the ladder'}</div>
                    </div>
                  )}
                </div>
              </div>
              {captain && (
                <div style={{ marginTop: 20, background: 'rgba(255,255,255,.1)', border: '1px solid rgba(255,255,255,.16)', borderRadius: 14, padding: '13px 15px', display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{ width: 40, height: 40, borderRadius: '50%', flex: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', font: `700 13px ${DISP}`, color: '#fff', background: 'rgba(255,255,255,.18)', boxShadow: 'inset 0 0 0 1px rgba(255,255,255,.3)' }}>{captain.initials}</div>
                  <div style={{ flex: 1 }}>
                    <div style={{ font: `700 9px 'Hanken Grotesk'`, letterSpacing: '.16em', textTransform: 'uppercase', color: 'rgba(255,255,255,.65)' }}>Captain of the week</div>
                    <div style={{ font: `800 17px ${DISP}`, textTransform: 'uppercase', color: '#fff' }}>{captain.name} (C)</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ font: `800 26px ${DISP}`, color: '#fff', lineHeight: 1 }}>{pts(captain.eff_points)}</div>
                    <div style={{ font: `600 8px 'Hanken Grotesk'`, letterSpacing: '.1em', textTransform: 'uppercase', color: 'rgba(255,255,255,.6)' }}>pts</div>
                  </div>
                </div>
              )}
              <div style={{ marginTop: 13, font: `600 11px 'Hanken Grotesk'`, color: 'rgba(255,255,255,.55)', textAlign: 'center' }}>
                {host}{beat != null ? ` · beat ${beat}% of the club` : ''}
              </div>
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <Btn full disabled={busy === 'gameweek'} onClick={() => exportCard(gwRef, 'gameweek', 430, 430)}>{busy === 'gameweek' ? 'Rendering…' : 'Share result'}</Btn>
          <Btn variant="soft" disabled={busy === 'gameweek'} onClick={() => exportCard(gwRef, 'gameweek', 430, 430)} style={{ padding: '12px 16px' }}>Save</Btn>
        </div>
      </div>

      {/* Recruit-a-mate story */}
      <div style={{ paddingTop: 24 }}>
        <div style={{ font: `600 11px 'Hanken Grotesk'`, letterSpacing: '.14em', textTransform: 'uppercase', color: 'var(--faint)', marginBottom: 10 }}>Recruit a mate</div>
        <div style={{ overflowX: 'auto' }}>
          <div ref={storyRef} data-theme="dark" style={{ position: 'relative', width: 300, height: 533, background: '#0a0d14', borderRadius: 22, overflow: 'hidden', boxShadow: 'var(--frame-shadow)' }}>
            <Aurora style={{ inset: '-10%', height: 'auto', bottom: '-10%' }} opacity={0.72} blur={50} blobs={[
              { c: 'var(--pb-accent, #8C82F0)', a: 'bfcAuroraA', s: 18, pos: { width: '70%', height: '40%', left: '-10%', top: '-4%' } },
              { c: '#22D3EE', a: 'bfcAuroraD', s: 23, pos: { width: '65%', height: '38%', right: '-10%', top: '34%' } },
              { c: '#EC4899', a: 'bfcAuroraC', s: 20, pos: { width: '75%', height: '40%', left: '0%', bottom: '-8%' } },
            ]} />
            <div style={{ position: 'relative', height: '100%', padding: '26px 24px', display: 'flex', flexDirection: 'column', textAlign: 'center', alignItems: 'center', fontFamily: "'Hanken Grotesk',sans-serif" }}>
              <div style={{ width: 48, height: 48, borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#fff', color: '#0a0d14', font: `800 16px ${DISP}` }}>{crest}</div>
              <div style={{ font: `600 10px 'Hanken Grotesk'`, letterSpacing: '.24em', textTransform: 'uppercase', color: 'rgba(255,255,255,.7)', marginTop: 16 }}>{club?.name || 'Club'} Fantasy</div>
              <div style={{ font: `800 40px/0.95 ${DISP}`, textTransform: 'uppercase', color: '#fff', marginTop: 14 }}>Think you<br />know cricket?</div>
              <div style={{ font: `500 13px 'Hanken Grotesk'`, color: 'rgba(255,255,255,.78)', marginTop: 12, lineHeight: 1.5 }}>Pick 12, captain a gun, and take on the clubhouse every round.</div>
              <div style={{ marginTop: 'auto', width: '100%', background: 'rgba(255,255,255,.1)', border: '1px solid rgba(255,255,255,.16)', borderRadius: 14, padding: 14 }}>
                <div style={{ font: `700 9px 'Hanken Grotesk'`, letterSpacing: '.16em', textTransform: 'uppercase', color: 'rgba(255,255,255,.6)' }}>{code ? 'Join my league' : 'Play here'}</div>
                <div style={{ font: `800 30px ${DISP}`, letterSpacing: code ? '.18em' : '.02em', color: '#fff', marginTop: 4 }}>{code || (club?.name || 'Fantasy')}</div>
                <div style={{ font: `600 11px 'Hanken Grotesk'`, color: 'rgba(255,255,255,.65)', marginTop: 2 }}>{total ? `${total} playing` : 'Free to play'}</div>
              </div>
              <div style={{ marginTop: 14, width: '100%', background: 'var(--pb-accent, #8C82F0)', color: '#11102a', padding: 13, borderRadius: 12, font: `800 14px ${DISP}`, letterSpacing: '.04em', textTransform: 'uppercase' }}>Play free →</div>
              <div style={{ font: `600 10px 'Hanken Grotesk'`, color: 'rgba(255,255,255,.5)', marginTop: 10 }}>{host}/fantasy</div>
            </div>
          </div>
        </div>
        <div style={{ marginTop: 10 }}>
          <Btn full disabled={busy === 'recruit'} onClick={() => exportCard(storyRef, 'recruit', 300, 533)}>{busy === 'recruit' ? 'Rendering…' : 'Share invite'}</Btn>
        </div>
      </div>
    </div>
  )
}
