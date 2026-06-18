// Profile & settings — manager card, appearance (Dark / Light / Auto), local
// notification prefs, and account actions (rename team, change PIN, sign out).
// Plus How to play, whose points table reads the season's real scoring config.
import { useState } from 'react'
import { api } from '../../lib/api'
import { DISP, tintBg, mix, Btn, Field, Segmented, Toggle, RED, useFantasy } from './ui'
import { ScreenTitle } from './shell'

const PREFS_KEY = 'bfc-prefs'
const loadPrefs = () => { try { return { deadline: true, price: true, chat: false, ...JSON.parse(localStorage.getItem(PREFS_KEY) || '{}') } } catch { return { deadline: true, price: true, chat: false } } }
const savePrefs = (p) => { try { localStorage.setItem(PREFS_KEY, JSON.stringify(p)) } catch { /* private */ } }

export default function Settings({ token, manager, squad, themePref, setThemePref, onChange, flash, fail, logout, nav }) {
  const { club } = useFantasy()
  const [prefs, setPrefs] = useState(loadPrefs())
  const [editing, setEditing] = useState(null)   // 'team' | 'pin'
  const [teamName, setTeamName] = useState(squad?.team_name || '')
  const [pin, setPin] = useState('')
  const [busy, setBusy] = useState(false)

  const togglePref = (k) => { const next = { ...prefs, [k]: !prefs[k] }; setPrefs(next); savePrefs(next) }
  const initials = (manager?.display_name || 'P').split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase()

  const saveTeam = async () => {
    setBusy(true)
    try { await api.fanUpdateProfile(token, { team_name: teamName }); flash('Team renamed.'); setEditing(null); await onChange() }
    catch (e) { fail(e) } finally { setBusy(false) }
  }
  const savePin = async () => {
    setBusy(true)
    try { await api.fanUpdateProfile(token, { pin }); flash('PIN changed.'); setPin(''); setEditing(null) }
    catch (e) { fail(e) } finally { setBusy(false) }
  }

  return (
    <div>
      <div style={{ position: 'relative', overflow: 'hidden', borderRadius: 16, padding: '12px 0' }}>
        <div style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 13 }}>
          <div style={{ width: 54, height: 54, borderRadius: 15, flex: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', font: `800 16px ${DISP}`, background: `linear-gradient(135deg, ${mix('var(--pb-accent, #8C82F0)', 80, '#000')}, var(--pb-accent, #8C82F0))` }}>{initials}</div>
          <div>
            <div style={{ font: `800 18px ${DISP}`, textTransform: 'uppercase', color: 'var(--text)' }}>{squad?.team_name || manager?.display_name}</div>
            <div style={{ font: `500 11px 'Hanken Grotesk'`, color: 'var(--faint)' }}>{manager?.display_name}{manager?.email ? ` · ${manager.email}` : ''}</div>
          </div>
        </div>
      </div>

      <Group title="Appearance">
        <div style={{ padding: 2 }}>
          <Segmented options={[['dark', 'Dark'], ['light', 'Light'], ['auto', 'Auto']]} value={themePref} onChange={setThemePref} />
        </div>
      </Group>

      <Group title="Notifications">
        <Card>
          <Row label="Deadline reminders" sub="Before each round locks" right={<Toggle on={prefs.deadline} onClick={() => togglePref('deadline')} />} />
          <Row label="Price-change alerts" sub="When your players rise or fall" right={<Toggle on={prefs.price} onClick={() => togglePref('price')} />} />
          <Row label="League chat" sub="Banter from your mini-leagues" right={<Toggle on={prefs.chat} onClick={() => togglePref('chat')} />} last />
        </Card>
        <p style={{ font: `500 10.5px 'Hanken Grotesk'`, color: 'var(--faint)', marginTop: 8 }}>Saved on this device.</p>
      </Group>

      <Group title="Account">
        <Card>
          {editing === 'team' ? (
            <div style={{ padding: 12, display: 'flex', gap: 8 }}>
              <Field value={teamName} onChange={e => setTeamName(e.target.value)} placeholder="Team name" style={{ padding: '10px 12px', fontSize: 12.5 }} />
              <Btn disabled={busy || !teamName.trim()} onClick={saveTeam} style={{ padding: '10px 14px', fontSize: 12.5 }}>Save</Btn>
            </div>
          ) : <RowBtn label="Rename team" onClick={() => { setTeamName(squad?.team_name || ''); setEditing('team') }} disabled={!squad} />}
          {editing === 'pin' ? (
            <div style={{ padding: 12, display: 'flex', gap: 8, borderTop: '1px solid var(--surface2)' }}>
              <Field value={pin} onChange={e => setPin(e.target.value)} placeholder="New PIN (4+ digits)" type="password" inputMode="numeric" style={{ padding: '10px 12px', fontSize: 12.5 }} />
              <Btn disabled={busy || pin.trim().length < 4} onClick={savePin} style={{ padding: '10px 14px', fontSize: 12.5 }}>Save</Btn>
            </div>
          ) : <RowBtn label="Change PIN" onClick={() => { setPin(''); setEditing('pin') }} />}
          <RowBtn label="Sign out" danger onClick={logout} last />
        </Card>
      </Group>

      <div style={{ paddingTop: 8 }}>
        <button onClick={() => nav('help')} style={{ background: 'none', border: 'none', color: 'var(--accent-strong)', font: `600 12px 'Hanken Grotesk'`, cursor: 'pointer' }}>How scoring works →</button>
      </div>
    </div>
  )
}

const Group = ({ title, children }) => (
  <div style={{ paddingTop: 18 }}>
    <div style={{ font: `700 9.5px 'Hanken Grotesk'`, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--faint)', marginBottom: 8 }}>{title}</div>
    {children}
  </div>
)
const Card = ({ children }) => <div style={{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 13, overflow: 'hidden' }}>{children}</div>
const Row = ({ label, sub, right, last }) => (
  <div style={{ display: 'flex', alignItems: 'center', padding: '13px 14px', borderBottom: last ? 'none' : '1px solid var(--surface2)' }}>
    <div style={{ flex: 1 }}>
      <div style={{ font: `600 13px 'Hanken Grotesk'`, color: 'var(--text)' }}>{label}</div>
      {sub && <div style={{ font: `500 10.5px 'Hanken Grotesk'`, color: 'var(--faint)' }}>{sub}</div>}
    </div>
    {right}
  </div>
)
const RowBtn = ({ label, onClick, danger, last, disabled }) => (
  <button onClick={onClick} disabled={disabled} style={{
    display: 'flex', alignItems: 'center', width: '100%', textAlign: 'left', padding: '13px 14px', cursor: disabled ? 'default' : 'pointer',
    border: 'none', borderBottom: last ? 'none' : '1px solid var(--surface2)', background: 'transparent', opacity: disabled ? 0.5 : 1,
    font: `600 13px 'Hanken Grotesk'`, color: danger ? RED : 'var(--text)',
  }}>{label}<span style={{ marginLeft: 'auto', color: danger ? RED : 'var(--faint)' }}>{'›'}</span></button>
)

// ── How to play / scoring ──────────────────────────────────────────────────────
export function HowToPlay({ season, nav }) {
  const sc = season?.scoring || {}
  const rules = season?.rules || {}
  const q = rules.role_quota || { keeper: 1, batter: 4, allrounder: 3, bowler: 4 }
  const sign = (n) => (n >= 0 ? `+${n}` : `${n}`)
  const table = [
    ['Run scored', sc.run ?? 1], ['Four hit', sc.four ?? 1], ['Six hit', sc.six ?? 2],
    ['Half-century', sc.fifty ?? 16], ['Century', sc.hundred ?? 32],
    ['Wicket taken', sc.wicket ?? 25], ['Three-wicket haul', sc.three_wickets ?? 8], ['Five-wicket haul', sc.five_wickets ?? 16],
    ['Maiden over', sc.maiden ?? 8], ['Catch', sc.catch ?? 8], ['Stumping', sc.stumping ?? 12],
    ['Run-out', sc.run_out ?? 12], ['Took the field', sc.appearance ?? 4], ['Duck (batter)', sc.duck ?? -4],
  ]
  return (
    <div>
      <ScreenTitle title="How scoring works" sub="Earn points every round" back onBack={() => nav('settings')} />
      <div style={{ paddingTop: 14 }}>
        <div style={{ background: tintBg(9, 'var(--surface)'), border: `1px solid ${tintBg(26)}`, borderRadius: 13, padding: '12px 14px', font: `500 12px 'Hanken Grotesk'`, color: 'var(--text)', lineHeight: 1.5 }}>
          Pick {rules.squad_size || 12} within a <b>${(rules.budget ?? 100)}</b> budget: {q.batter} batters, {q.allrounder} all-rounders, {q.keeper} wicketkeeper, {q.bowler} bowlers. Your <b style={{ color: 'var(--accent-strong)' }}>captain</b> scores double, and each round counts your best {rules.count_best_n || 11}.
        </div>
      </div>
      <div style={{ font: `700 10px 'Hanken Grotesk'`, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--faint)', padding: '14px 0 8px' }}>Points table</div>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 13, overflow: 'hidden' }}>
        {table.map(([act, p], i) => (
          <div key={act} style={{ display: 'flex', alignItems: 'center', padding: '10px 14px', borderBottom: i === table.length - 1 ? 'none' : '1px solid var(--surface2)' }}>
            <span style={{ flex: 1, font: `600 12.5px 'Hanken Grotesk'`, color: 'var(--text)' }}>{act}</span>
            <span style={{ font: `800 14px ${DISP}`, color: p < 0 ? RED : 'var(--accent-strong)', fontVariantNumeric: 'tabular-nums' }}>{sign(p)}</span>
          </div>
        ))}
      </div>
      <p style={{ font: `500 11px 'Hanken Grotesk'`, color: 'var(--faint)', padding: '12px 2px' }}>Bowler runs and batter wickets score one-and-a-half times, since they're out of role.</p>
    </div>
  )
}
