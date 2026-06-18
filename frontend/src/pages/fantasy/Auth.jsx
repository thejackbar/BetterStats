// Auth — register / sign in. Centred crest + wordmark over a soft aurora.
import { useState } from 'react'
import { api } from '../../lib/api'
import { Aurora, Crest, Btn, Segmented, DISP, tintBg, useFantasy } from './ui'
import { Banner } from './shell'

export default function Auth({ token, season, onAuthed }) {
  const { club } = useFantasy()
  const [mode, setMode] = useState('register')
  const [form, setForm] = useState({ display_name: '', email: '', pin: '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setErr('')
    try {
      if (mode === 'register') await api.fanRegister(token, form)
      else await api.fanLogin(token, { email: form.email, pin: form.pin })
      await onAuthed()
    } catch (ex) { setErr(ex.message || 'Something went wrong') } finally { setBusy(false) }
  }

  const inputSx = {
    width: '100%', background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 11,
    padding: '13px 14px', font: `500 13.5px 'Hanken Grotesk'`, color: 'var(--text)', outline: 'none',
  }

  return (
    <div style={{ position: 'relative', overflow: 'hidden', borderRadius: 24 }}>
      <Aurora style={{ inset: '-15% -25% 30%', height: 'auto', bottom: '30%' }} blur={50} blobs={[
        { c: 'var(--pb-accent, #8C82F0)', a: 'bfcAuroraA', s: 18, pos: { width: '60%', height: '70%', left: '-8%', top: '-5%' } },
        { c: '#22D3EE', a: 'bfcAuroraB', s: 22, pos: { width: '55%', height: '65%', right: '-6%', top: '0%' } },
        { c: '#EC4899', a: 'bfcAuroraC', s: 20, pos: { width: '55%', height: '60%', left: '18%', top: '18%' } },
      ]} />
      <div style={{ position: 'relative', padding: '30px 6px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <div style={{
          width: 64, height: 64, borderRadius: 19, display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'var(--pb-accent, #8C82F0)', color: 'var(--ink)', font: `800 22px ${DISP}`,
          boxShadow: `inset 0 0 0 1px rgba(255,255,255,.18), 0 12px 34px -8px ${tintBg(70)}`,
        }}>{(club?.short_name || club?.name || 'BFC').slice(0, 4).toUpperCase()}</div>
        <div style={{ font: `800 25px ${DISP}`, textTransform: 'uppercase', letterSpacing: '.02em', color: 'var(--text)', marginTop: 16 }}>{club?.name || 'Fantasy Cricket'}</div>
        <div style={{ font: `600 10px 'Hanken Grotesk'`, letterSpacing: '.22em', textTransform: 'uppercase', color: 'var(--accent-strong)', marginTop: 5 }}>
          Fantasy Cricket{season?.name ? ` · ${season.name}` : ''}
        </div>
        <div style={{ font: `500 12.5px 'Hanken Grotesk'`, color: 'var(--dim)', textAlign: 'center', marginTop: 12, lineHeight: 1.5, maxWidth: 250 }}>
          Build your 12, captain a star, climb the club ladder.
        </div>

        <div style={{ width: '100%', marginTop: 22 }}>
          <Segmented options={[['register', 'New player'], ['login', 'Sign in']]} value={mode} onChange={(m) => { setErr(''); setMode(m) }} />
        </div>

        {err && <div style={{ width: '100%', marginTop: 14 }}><Banner>{err}</Banner></div>}

        <form onSubmit={submit} style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 10, marginTop: 14 }}>
          {mode === 'register' && (
            <input style={inputSx} placeholder="Display name" value={form.display_name} onChange={set('display_name')} required />
          )}
          <input style={inputSx} type="email" placeholder="Email" value={form.email} onChange={set('email')} required />
          <input style={inputSx} type="password" inputMode="numeric" placeholder="PIN (4+ digits)" value={form.pin} onChange={set('pin')} required />
          <Btn type="submit" full disabled={busy} style={{ marginTop: 4, boxShadow: `0 10px 26px -8px ${tintBg(65)}` }}>
            {busy ? '…' : mode === 'register' ? 'Create & play' : 'Sign in'}
          </Btn>
        </form>
        <div style={{ font: `500 11.5px 'Hanken Grotesk'`, color: 'var(--faint)', textAlign: 'center', marginTop: 16, lineHeight: 1.5 }}>
          No app, no account needed beyond this.<br />Your PIN keeps your team yours.
        </div>
      </div>
    </div>
  )
}
