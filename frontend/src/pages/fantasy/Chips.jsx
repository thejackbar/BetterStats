// Chips — a card per chip with its state: Available ("Play"), Armed this round
// (accent, pulsing dot, "Cancel"), or Used (dimmed). Four chips: Wildcard, Triple
// Captain, Bench Boost, Free Hit.
import { useState } from 'react'
import { api } from '../../lib/api'
import { DISP, tintBg, GREEN, Btn } from './ui'
import { ScreenTitle } from './shell'

export default function Chips({ token, squad, round, onChange, flash, fail, nav }) {
  const [busy, setBusy] = useState('')
  if (!squad) return (
    <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--faint)' }}>
      <p style={{ font: `500 13px 'Hanken Grotesk'` }}>Build a squad to play chips.</p>
      <button onClick={() => nav('pick')} style={{ marginTop: 8, background: 'none', border: 'none', color: 'var(--accent-strong)', font: `600 12px 'Hanken Grotesk'`, cursor: 'pointer' }}>Pick your squad →</button>
    </div>
  )
  const chips = squad.chips || []
  const locked = !!round?.locked

  const play = async (key) => {
    setBusy(key)
    try { await api.fanChip(token, key); flash('Chip armed for this round.'); await onChange() }
    catch (e) { fail(e) } finally { setBusy('') }
  }
  const cancel = async (key) => {
    setBusy(key)
    try { await api.fanCancelChip(token, key); flash('Chip cancelled.'); await onChange() }
    catch (e) { fail(e) } finally { setBusy('') }
  }

  return (
    <div>
      <ScreenTitle title="Chips" sub="One play each, per half" back onBack={() => nav('team')} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, paddingTop: 14 }}>
        {chips.map(c => {
          if (c.state === 'armed') {
            return (
              <div key={c.key} style={{ background: tintBg(14, 'var(--bg)'), border: `1px solid ${tintBg(40)}`, borderRadius: 15, padding: '14px 15px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--pb-accent, #06B6D4)', boxShadow: '0 0 8px var(--pb-accent, #06B6D4)' }} />
                  <span style={{ font: `800 16px ${DISP}`, textTransform: 'uppercase', color: 'var(--text)' }}>{c.name}</span>
                  <span style={{ marginLeft: 'auto', font: `700 10px 'Hanken Grotesk'`, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--accent-strong)' }}>{c.status}</span>
                </div>
                <div style={{ font: `500 12px 'Hanken Grotesk'`, color: 'var(--dim)', marginTop: 7 }}>{c.desc}</div>
                <Btn variant="soft" full disabled={busy === c.key || locked} onClick={() => cancel(c.key)} style={{ marginTop: 11, padding: 10, fontSize: 12.5 }}>Cancel for this round</Btn>
              </div>
            )
          }
          if (c.state === 'used') {
            return (
              <div key={c.key} style={{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 15, padding: '14px 15px', opacity: 0.55 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ font: `800 16px ${DISP}`, textTransform: 'uppercase', color: 'var(--dim)' }}>{c.name}</span>
                  <span style={{ marginLeft: 'auto', font: `700 10px 'Hanken Grotesk'`, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--faint)' }}>{c.status}</span>
                </div>
                <div style={{ font: `500 12px 'Hanken Grotesk'`, color: 'var(--faint)', marginTop: 7 }}>{c.desc}</div>
              </div>
            )
          }
          return (
            <div key={c.key} style={{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 15, padding: '14px 15px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ font: `800 16px ${DISP}`, textTransform: 'uppercase', color: 'var(--text)' }}>{c.name}</span>
                <span style={{ marginLeft: 'auto', font: `700 10px 'Hanken Grotesk'`, letterSpacing: '.08em', textTransform: 'uppercase', color: GREEN }}>{c.status}</span>
              </div>
              <div style={{ font: `500 12px 'Hanken Grotesk'`, color: 'var(--dim)', marginTop: 7 }}>{c.desc}</div>
              <Btn full disabled={busy === c.key || locked} onClick={() => play(c.key)} style={{ marginTop: 11, padding: 10, fontSize: 12.5 }}>Play {c.name}</Btn>
            </div>
          )
        })}
      </div>
      {locked && <p style={{ font: `500 11.5px 'Hanken Grotesk'`, color: 'var(--faint)', textAlign: 'center', marginTop: 12 }}>This round has locked. Chips open again next round.</p>}
    </div>
  )
}
