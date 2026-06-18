// Profile & settings — manager card, appearance (Dark / Light / Auto), local
// notification prefs, and account actions (rename team, change PIN, sign out).
// Plus How to play, whose points table reads the season's real scoring config.
import { useState } from 'react'
import { api } from '../../lib/api'
import { DISP, tintBg, mix, Btn, Field, Segmented, Toggle, RED, GREEN, useFantasy } from './ui'
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
        <button onClick={() => nav('help')} style={{ background: 'none', border: 'none', color: 'var(--accent-strong)', font: `600 12px 'Hanken Grotesk'`, cursor: 'pointer' }}>How to play & scoring →</button>
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

// ── How to play / rules / scoring ───────────────────────────────────────────────
const RuleSection = ({ children }) => (
  <div style={{ font: `700 10px 'Hanken Grotesk'`, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--faint)', padding: '18px 0 8px' }}>{children}</div>
)

export function HowToPlay({ season, nav }) {
  const sc = season?.scoring || {}
  const rules = season?.rules || {}
  const q = rules.role_quota || { keeper: 1, batter: 4, allrounder: 3, bowler: 4 }
  const squadSize = rules.squad_size || (q.keeper + q.batter + q.allrounder + q.bowler) || 12
  const bestN = rules.count_best_n || 11
  const budget = rules.budget ?? 100
  const freeT = rules.free_transfers_per_round ?? 1
  const hit = rules.transfer_hit ?? 4
  const m = sc.off_role_multiplier ?? 1.5
  const capMult = sc.captain_multiplier ?? 2
  const appearance = sc.appearance ?? 4
  const sign = (n) => (n >= 0 ? `+${n}` : `${n}`)
  const f = (n) => (Number.isInteger(n) ? n : Math.round(n * 100) / 100)

  // The general way the game is played.
  const steps = [
    `Sign up with a name and a PIN. There's no app to download and no account to make.`,
    `Build a squad of ${squadSize} within a $${budget} budget: ${q.batter} batters, ${q.allrounder} all-rounders, ${q.keeper} wicketkeeper and ${q.bowler} bowlers. Better players cost more, so you can't pick all the stars.`,
    `Name a captain, who scores ×${f(capMult)}, and a vice-captain who steps in if your captain doesn't take the field.`,
    `Every club weekend is a round, scored off your players' real games. Every grade counts the same: a run in 5ths is worth a run in 1sts.`,
    `Each round only your best ${bestN} of ${squadSize} count, so a player who has a quiet week or doesn't play just drops out.`,
    `You get ${freeT} free transfer${freeT === 1 ? '' : 's'} a round; extra ones cost ${hit} points. Save your chips for the big weeks.`,
    `Climb the club ladder, and start private mini-leagues with a join code to settle it with your mates.`,
  ]

  // The points table (the scoring structure).
  const table = [
    ['Run scored', sc.run ?? 1], ['Four hit', sc.four ?? 1], ['Six hit', sc.six ?? 2],
    ['Half-century', sc.fifty ?? 16], ['Century', sc.hundred ?? 32],
    ['Wicket taken', sc.wicket ?? 25], ['Three-wicket haul', sc.three_wickets ?? 8], ['Five-wicket haul', sc.five_wickets ?? 16],
    ['Maiden over', sc.maiden ?? 8], ['Catch', sc.catch ?? 8], ['Stumping', sc.stumping ?? 12],
    ['Run-out', sc.run_out ?? 12], ['Took the field', appearance], ['Duck (batter out for 0)', sc.duck ?? -4],
  ]

  // Worked examples, computed from this season's real values so they stay right
  // even if the club tunes the points.
  const batPts = (runs, fours, sixes) => {
    let p = runs * (sc.run ?? 1) + fours * (sc.four ?? 1) + sixes * (sc.six ?? 2)
    if (runs >= 100) p += sc.hundred ?? 32
    else if (runs >= 50) p += sc.fifty ?? 16
    return p
  }
  const bowlPts = (wkts) => {
    let p = wkts * (sc.wicket ?? 25)
    if (wkts >= 5) p += sc.five_wickets ?? 16
    else if (wkts >= 3) p += sc.three_wickets ?? 8
    return p
  }
  const fifty = batPts(50, 5, 0)
  const threeFor = bowlPts(3)
  const examples = [
    { title: 'A top-order fifty', line: 'A batter makes 50 with 5 fours.', calc: `50 runs + 5 fours + ${sc.fifty ?? 16} for reaching 50`, pts: fifty },
    { title: 'A three-wicket haul', line: 'A bowler takes 3 wickets.', calc: `3 × ${sc.wicket ?? 25} + ${sc.three_wickets ?? 8} haul bonus`, pts: threeFor },
    { title: 'Out of role pays more', line: `Those same 3 wickets, but taken by a batter. Wickets aren't a batter's job, so they're worth ×${f(m)}.`, calc: `${f(threeFor)} × ${f(m)}`, pts: threeFor * m, hot: true },
  ]

  return (
    <div>
      <ScreenTitle title="How to play" sub="Rules & scoring" back onBack={() => nav('team')} />

      <div style={{ paddingTop: 14 }}>
        <div style={{ background: tintBg(9, 'var(--surface)'), border: `1px solid ${tintBg(26)}`, borderRadius: 13, padding: '12px 14px', font: `500 12.5px 'Hanken Grotesk'`, color: 'var(--text)', lineHeight: 1.5 }}>
          Build a squad from your club's own players, captain it, and score points off how they really go each weekend. The more runs, wickets and catches your picks rack up, the higher you climb.
        </div>
      </div>

      <RuleSection>The basics</RuleSection>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 13, overflow: 'hidden' }}>
        {steps.map((s, i) => (
          <div key={i} style={{ display: 'flex', gap: 11, alignItems: 'flex-start', padding: '11px 14px', borderBottom: i === steps.length - 1 ? 'none' : '1px solid var(--surface2)' }}>
            <span style={{ flex: 'none', width: 22, height: 22, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent-strong)', background: tintBg(14), font: `800 11px ${DISP}` }}>{i + 1}</span>
            <span style={{ font: `500 12.5px 'Hanken Grotesk'`, color: 'var(--text)', lineHeight: 1.45 }}>{s}</span>
          </div>
        ))}
      </div>

      <RuleSection>Points table</RuleSection>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 13, overflow: 'hidden' }}>
        {table.map(([act, p], i) => (
          <div key={act} style={{ display: 'flex', alignItems: 'center', padding: '10px 14px', borderBottom: i === table.length - 1 ? 'none' : '1px solid var(--surface2)' }}>
            <span style={{ flex: 1, font: `600 12.5px 'Hanken Grotesk'`, color: 'var(--text)' }}>{act}</span>
            <span style={{ font: `800 14px ${DISP}`, color: p < 0 ? RED : 'var(--accent-strong)', fontVariantNumeric: 'tabular-nums' }}>{sign(p)}</span>
          </div>
        ))}
      </div>
      <p style={{ font: `500 11px 'Hanken Grotesk'`, color: 'var(--faint)', padding: '10px 2px 0' }}>
        Output outside a player's role scores ×{f(m)}: a bowler's runs, a batter's wickets, and a keeper's batting and dismissals. All-rounders score both at the base rate.
      </p>

      <RuleSection>Examples</RuleSection>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {examples.map((ex, i) => (
          <div key={i} style={{ background: ex.hot ? tintBg(9, 'var(--surface)') : 'var(--surface)', border: `1px solid ${ex.hot ? tintBg(26) : 'var(--hairline)'}`, borderRadius: 13, padding: '12px 14px' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
              <span style={{ font: `700 13px 'Hanken Grotesk'`, color: 'var(--text)' }}>{ex.title}</span>
              <span style={{ font: `800 18px ${DISP}`, color: GREEN, fontVariantNumeric: 'tabular-nums', lineHeight: 1 }}>{f(ex.pts)}<span style={{ font: `700 9px 'Hanken Grotesk'`, color: 'var(--faint)', marginLeft: 3 }}>PTS</span></span>
            </div>
            <div style={{ font: `500 11.5px 'Hanken Grotesk'`, color: 'var(--faint)', marginTop: 4, lineHeight: 1.45 }}>{ex.line}</div>
            <div style={{ font: `600 11px 'Hanken Grotesk'`, color: 'var(--dim)', marginTop: 5, fontVariantNumeric: 'tabular-nums' }}>{ex.calc} = {f(ex.pts)}</div>
          </div>
        ))}
        <div style={{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 13, padding: '12px 14px' }}>
          <span style={{ font: `700 13px 'Hanken Grotesk'`, color: 'var(--text)' }}>Your captain</span>
          <div style={{ font: `500 11.5px 'Hanken Grotesk'`, color: 'var(--faint)', marginTop: 4, lineHeight: 1.45 }}>
            Whoever you captain has their whole round score multiplied by {f(capMult)} before your best {bestN} are counted. Pick the player you back to have the biggest weekend.
          </div>
        </div>
      </div>
      <p style={{ font: `500 11px 'Hanken Grotesk'`, color: 'var(--faint)', padding: '10px 2px 0' }}>
        Every player who takes the field also gets {sign(appearance)} just for playing, added on top and never multiplied.
      </p>
    </div>
  )
}
