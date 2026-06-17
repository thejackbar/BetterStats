// BetterFantasyCricket — public member play (no login, magic link + PIN).
//
// Reached via a per-club link (/fantasy/:token). Members and supporters register
// with a name, email and PIN, build a 12-man squad within budget and the role
// quota, captain it, then track the club ladder and their mini-leagues. Once the
// season is live, squad changes go through transfers and chips. White-labelled
// from the club's own colours.
import { useState, useEffect, useMemo, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../lib/api'

const ROLE_ORDER = ['keeper', 'batter', 'allrounder', 'bowler']
const ROLE_LABEL = { keeper: 'Keeper', batter: 'Batter', allrounder: 'All-rounder', bowler: 'Bowler' }
const money = (n) => Number(n ?? 0).toFixed(2)

function ClubHeader({ club, sub }) {
  const initials = (club?.name || 'Club').split(' ').map(w => w[0]).join('').slice(0, 3).toUpperCase()
  return (
    <div className="flex flex-col items-center text-center gap-3 mb-6">
      {club?.logo_url
        ? <img src={club.logo_url} alt="" className="w-16 h-16 rounded-xl object-contain bg-pb-surface2 p-1" />
        : <span className="w-16 h-16 rounded-xl flex items-center justify-center font-display font-bold text-xl text-pb-bg" style={{ background: 'var(--pb-accent)' }}>{initials}</span>}
      <div>
        <div className="font-display font-bold text-xl leading-tight">{club?.name || 'Fantasy Cricket'}</div>
        <div className="font-mono text-[11px] tracking-wide2 text-pb-faint mt-1">{sub || 'FANTASY CRICKET'}</div>
      </div>
    </div>
  )
}

function Banner({ tone = 'error', children }) {
  if (!children) return null
  const color = tone === 'error' ? 'var(--pb-red)' : tone === 'ok' ? 'var(--pb-positive)' : 'var(--pb-amber)'
  return (
    <div className="rounded-lg px-3.5 py-2.5 mb-4 text-sm"
      style={{ background: `color-mix(in srgb, ${color} 12%, transparent)`, color, border: `1px solid color-mix(in srgb, ${color} 35%, transparent)` }}>
      {children}
    </div>
  )
}

const btn = 'px-3 py-2 rounded-lg text-sm font-medium disabled:opacity-50'
const btnAccent = `${btn} text-pb-bg`
const accentStyle = { background: 'var(--pb-accent)' }

export default function PublicFantasy() {
  const { token } = useParams()
  const [phase, setPhase] = useState('loading')   // loading | dead | auth | app
  const [club, setClub] = useState(null)
  const [season, setSeason] = useState(null)
  const [manager, setManager] = useState(null)
  const [squad, setSquad] = useState(null)
  const [pool, setPool] = useState(null)
  const [rules, setRules] = useState(null)
  const [view, setView] = useState('team')         // team | pick | ladder | leagues
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  const accent = club?.accent_color || club?.primary_color || null
  const flash = (m) => { setMsg(m); setError(''); setTimeout(() => setMsg(''), 3500) }
  const fail = (e) => { setError(e.message || String(e)); setMsg('') }

  const loadApp = useCallback(async () => {
    const [m, p] = await Promise.all([api.fanMe(token), api.fanPool(token).catch(() => null)])
    setManager(m.manager); setSquad(m.squad)
    if (p) { setPool(p.players); setRules(p.rules) }
    setView(m.squad ? 'team' : 'pick')
  }, [token])

  useEffect(() => {
    (async () => {
      try {
        const d = await api.fanLanding(token)
        setClub(d.club); setSeason(d.season)
        if (!d.season) { setPhase('dead'); return }
        setRules(d.season.rules)
        if (d.me) { setManager(d.me); await loadApp(); setPhase('app') }
        else setPhase('auth')
      } catch { setPhase('dead') }
    })()
  }, [token, loadApp])

  const onAuthed = async () => { await loadApp(); setPhase('app') }
  const logout = async () => { await api.fanLogout(token).catch(() => {}); setManager(null); setSquad(null); setPhase('auth') }

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text" style={accent ? { '--pb-accent': accent } : undefined}>
      <div className="max-w-xl mx-auto px-4 py-8">
        {phase === 'loading' && <p className="text-center text-pb-faint mt-16">Loading…</p>}
        {phase === 'dead' && (
          <>
            <ClubHeader club={club} />
            <Banner>This fantasy link isn't active yet. Check with your club.</Banner>
          </>
        )}
        {phase === 'auth' && (
          <Auth token={token} club={club} season={season} onAuthed={onAuthed} />
        )}
        {phase === 'app' && (
          <>
            <ClubHeader club={club} sub={season?.name?.toUpperCase()} />
            <div className="flex items-center justify-between mb-4">
              <div className="text-sm text-pb-faint">Hi, <span className="text-pb-text font-medium">{manager?.display_name}</span></div>
              <button onClick={logout} className="text-xs text-pb-faint underline">Sign out</button>
            </div>
            <Banner tone="ok">{msg}</Banner>
            <Banner>{error}</Banner>
            <nav className="flex gap-1 mb-5 text-sm">
              {[['team', 'My team'], ['pick', squad ? 'Edit' : 'Pick'], ['ladder', 'Ladder'], ['leagues', 'Leagues'], ['draft', 'Draft']].map(([k, label]) => (
                <button key={k} onClick={() => setView(k)}
                  className={`px-3 py-1.5 rounded-lg ${view === k ? 'text-pb-bg' : 'text-pb-faint bg-pb-surface2'}`}
                  style={view === k ? accentStyle : undefined}>{label}</button>
              ))}
            </nav>

            {view === 'team' && (
              <MyTeam token={token} squad={squad} season={season} pool={pool} rules={rules}
                onChange={loadApp} flash={flash} fail={fail} goPick={() => setView('pick')} />
            )}
            {view === 'pick' && (
              <Builder token={token} pool={pool} rules={rules} squad={squad} season={season}
                onSaved={async () => { flash('Squad saved.'); await loadApp(); setView('team') }} fail={fail} />
            )}
            {view === 'ladder' && <Ladder token={token} />}
            {view === 'leagues' && <Leagues token={token} flash={flash} fail={fail} />}
            {view === 'draft' && <Draft token={token} flash={flash} fail={fail} />}
          </>
        )}
      </div>
    </div>
  )
}

// ── Auth ───────────────────────────────────────────────────────────────────

function Auth({ token, club, season, onAuthed }) {
  const [mode, setMode] = useState('register')
  const [form, setForm] = useState({ display_name: '', email: '', pin: '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('')
    try {
      if (mode === 'register') await api.fanRegister(token, form)
      else await api.fanLogin(token, { email: form.email, pin: form.pin })
      await onAuthed()
    } catch (ex) { setErr(ex.message || 'Something went wrong') } finally { setBusy(false) }
  }

  return (
    <>
      <ClubHeader club={club} sub={season?.name?.toUpperCase()} />
      <div className="flex gap-1 mb-4 text-sm justify-center">
        {['register', 'login'].map(m => (
          <button key={m} onClick={() => { setErr(''); setMode(m) }}
            className={`px-3 py-1.5 rounded-lg ${mode === m ? 'text-pb-bg' : 'text-pb-faint bg-pb-surface2'}`}
            style={mode === m ? accentStyle : undefined}>{m === 'register' ? 'New player' : 'Sign in'}</button>
        ))}
      </div>
      <Banner>{err}</Banner>
      <form onSubmit={submit} className="space-y-3">
        {mode === 'register' && (
          <input className="w-full rounded-lg border pb-hairline bg-pb-surface px-3 py-2 text-sm"
            placeholder="Display name" value={form.display_name} onChange={set('display_name')} required />
        )}
        <input type="email" className="w-full rounded-lg border pb-hairline bg-pb-surface px-3 py-2 text-sm"
          placeholder="Email" value={form.email} onChange={set('email')} required />
        <input type="password" inputMode="numeric" className="w-full rounded-lg border pb-hairline bg-pb-surface px-3 py-2 text-sm"
          placeholder="PIN (4+ digits)" value={form.pin} onChange={set('pin')} required />
        <button type="submit" disabled={busy} className={`${btnAccent} w-full`} style={accentStyle}>
          {busy ? '…' : mode === 'register' ? 'Create & play' : 'Sign in'}
        </button>
      </form>
      <p className="text-xs text-pb-faintest text-center mt-4">No app, no account needed beyond this. Your PIN keeps your team yours.</p>
    </>
  )
}

// ── Squad builder ────────────────────────────────────────────────────────────

function Builder({ token, pool, rules, squad, onSaved, fail }) {
  const quota = rules?.role_quota || { keeper: 1, batter: 4, allrounder: 3, bowler: 4 }
  const budget = rules?.budget ?? 100
  const size = rules?.squad_size ?? 12
  const [picked, setPicked] = useState(() => {
    const init = {}
    ;(squad?.players || []).forEach(p => { init[p.player_id] = { ...p } })
    return init
  })
  const [teamName, setTeamName] = useState(squad?.team_name || '')
  const [filter, setFilter] = useState('keeper')
  const [busy, setBusy] = useState(false)

  const chosen = Object.values(picked)
  const spend = chosen.reduce((s, p) => s + Number(p.price || p.current_price || 0), 0)
  const left = budget - spend
  const byRole = (r) => chosen.filter(p => p.role === r).length
  const poolByRole = useMemo(() => (pool || []).filter(p => p.role === filter), [pool, filter])

  const toggle = (pp) => {
    setPicked(cur => {
      const next = { ...cur }
      if (next[pp.player_id]) { delete next[pp.player_id]; return next }
      if (chosen.length >= size) return cur
      if (byRole(pp.role) >= (quota[pp.role] || 0)) return cur
      if (Number(pp.price) > left + 1e-6) return cur
      next[pp.player_id] = { player_id: pp.player_id, name: pp.name, role: pp.role, price: pp.price, is_captain: false, is_vice_captain: false }
      return next
    })
  }
  // Toggle captain (or vice) on one player and clear it on every other, so there
  // is only ever one of each.
  const setCap = (pid, key) => setPicked(cur => {
    const next = {}
    for (const [id, p] of Object.entries(cur)) {
      next[id] = { ...p, [key]: id === pid ? !p[key] : false }
    }
    return next
  })

  const quotaOk = ROLE_ORDER.every(r => byRole(r) === (quota[r] || 0))
  const hasCap = chosen.some(p => p.is_captain)
  const valid = chosen.length === size && quotaOk && left >= -1e-6 && hasCap

  const save = async () => {
    setBusy(true)
    try {
      await api.fanSaveSquad(token, {
        team_name: teamName,
        picks: chosen.map(p => ({ player_id: p.player_id, is_captain: !!p.is_captain, is_vice_captain: !!p.is_vice_captain })),
      })
      await onSaved()
    } catch (e) { fail(e) } finally { setBusy(false) }
  }

  return (
    <div className="space-y-4">
      <div className="pb-card p-3 flex items-center justify-between text-sm">
        <div><span className="text-pb-faint">Budget left</span> <span className="font-bold">{money(left)}</span></div>
        <div><span className="text-pb-faint">Picked</span> <span className="font-bold">{chosen.length}/{size}</span></div>
      </div>
      <input className="w-full rounded-lg border pb-hairline bg-pb-surface px-3 py-2 text-sm"
        placeholder="Team name" value={teamName} onChange={e => setTeamName(e.target.value)} />

      <div className="flex gap-1 text-xs">
        {ROLE_ORDER.map(r => (
          <button key={r} onClick={() => setFilter(r)}
            className={`px-2.5 py-1.5 rounded-lg flex-1 ${filter === r ? 'text-pb-bg' : 'bg-pb-surface2 text-pb-faint'}`}
            style={filter === r ? accentStyle : undefined}>
            {ROLE_LABEL[r]}<br /><span className="opacity-80">{byRole(r)}/{quota[r] || 0}</span>
          </button>
        ))}
      </div>

      <div className="space-y-1.5">
        {poolByRole.map(pp => {
          const on = !!picked[pp.player_id]
          const blocked = !on && (chosen.length >= size || byRole(pp.role) >= (quota[pp.role] || 0) || Number(pp.price) > left + 1e-6)
          return (
            <button key={pp.player_id} onClick={() => toggle(pp)} disabled={blocked}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm border ${on ? 'border-transparent text-pb-bg' : 'pb-hairline bg-pb-surface'} disabled:opacity-40`}
              style={on ? accentStyle : undefined}>
              <span>{pp.name}</span>
              <span className="tabular-nums">{money(pp.price)}</span>
            </button>
          )
        })}
      </div>

      {chosen.length > 0 && (
        <div className="pb-card p-3">
          <div className="text-xs text-pb-faint mb-2">Your squad — tap C for captain, V for vice</div>
          {chosen.map(p => (
            <div key={p.player_id} className="flex items-center justify-between py-1 text-sm">
              <span>{p.name} <span className="text-pb-faintest text-xs">{ROLE_LABEL[p.role]}</span></span>
              <span className="flex gap-1">
                <button onClick={() => setCap(p.player_id, 'is_captain')}
                  className={`w-7 h-7 rounded text-xs font-bold ${p.is_captain ? 'text-pb-bg' : 'bg-pb-surface2 text-pb-faint'}`}
                  style={p.is_captain ? accentStyle : undefined}>C</button>
                <button onClick={() => setCap(p.player_id, 'is_vice_captain')}
                  className={`w-7 h-7 rounded text-xs font-bold ${p.is_vice_captain ? 'text-pb-bg' : 'bg-pb-surface2 text-pb-faint'}`}
                  style={p.is_vice_captain ? accentStyle : undefined}>V</button>
              </span>
            </div>
          ))}
        </div>
      )}

      <button onClick={save} disabled={!valid || busy} className={`${btnAccent} w-full`} style={accentStyle}>
        {busy ? 'Saving…' : valid ? 'Save squad' : `${chosen.length}/${size} · pick a full, captained, in-budget squad`}
      </button>
    </div>
  )
}

// ── My team (with transfers, captain, chips) ──────────────────────────────────

function MyTeam({ token, squad, season, pool, rules, onChange, flash, fail, goPick }) {
  const [swapOut, setSwapOut] = useState(null)
  const active = season?.status === 'active'

  if (!squad) {
    return (
      <div className="pb-card p-5 text-center">
        <p className="text-sm text-pb-faint mb-3">You haven't picked a squad yet.</p>
        <button onClick={goPick} className={btnAccent} style={accentStyle}>Pick your squad</button>
      </div>
    )
  }

  const sameRolePool = (role) => (pool || []).filter(p => p.role === role && !squad.players.some(s => s.player_id === p.player_id))

  const doTransfer = async (inId) => {
    try { const r = await api.fanTransfer(token, swapOut.player_id, inId); setSwapOut(null); flash(r.hit ? `Done — ${r.hit} pt hit.` : 'Transfer done.'); await onChange() }
    catch (e) { fail(e) }
  }
  const setCaptain = async (pid, vice) => {
    try { await api.fanSetCaptain(token, vice ? squad.players.find(s => s.is_captain)?.player_id : pid, vice ? pid : squad.players.find(s => s.is_vice_captain)?.player_id); flash('Captain updated.'); await onChange() }
    catch (e) { fail(e) }
  }
  const playChip = async (chip) => {
    try { await api.fanChip(token, chip); flash(chip === 'wildcard' ? 'Wildcard on — transfers are free this round.' : 'Triple captain armed.'); await onChange() }
    catch (e) { fail(e) }
  }

  return (
    <div className="space-y-4">
      <div className="pb-card p-3 flex items-center justify-between text-sm">
        <div><span className="text-pb-faint">Points</span> <span className="font-bold">{money(squad.total_points)}</span></div>
        {squad.budget_remaining != null && <div><span className="text-pb-faint">Bank</span> <span className="font-bold">{money(squad.budget_remaining)}</span></div>}
        <button onClick={goPick} className="text-xs underline text-pb-faint">{active ? '' : 'Edit squad'}</button>
      </div>

      {active && (
        <div className="flex gap-2 text-xs">
          <button onClick={() => playChip('wildcard')} className="flex-1 px-3 py-2 rounded-lg bg-pb-surface2 text-pb-text">Wildcard</button>
          <button onClick={() => playChip('triple_captain')} className="flex-1 px-3 py-2 rounded-lg bg-pb-surface2 text-pb-text">Triple captain</button>
        </div>
      )}

      {ROLE_ORDER.map(role => {
        const rows = squad.players.filter(p => p.role === role)
        if (!rows.length) return null
        return (
          <div key={role} className="pb-card p-3">
            <div className="text-xs text-pb-faint mb-1.5">{ROLE_LABEL[role]}</div>
            {rows.map(p => (
              <div key={p.player_id}>
                <div className="flex items-center justify-between py-1 text-sm">
                  <span>
                    {p.name}
                    {p.is_captain && <span className="ml-1 text-[10px] font-bold" style={{ color: 'var(--pb-accent)' }}>C</span>}
                    {p.is_vice_captain && <span className="ml-1 text-[10px] font-bold text-pb-faint">V</span>}
                  </span>
                  <span className="flex items-center gap-2">
                    <span className="tabular-nums text-pb-faint text-xs">{money(p.purchase_price)}</span>
                    {!p.is_captain && <button onClick={() => setCaptain(p.player_id, false)} className="text-[10px] text-pb-faint underline">C</button>}
                    {!p.is_vice_captain && <button onClick={() => setCaptain(p.player_id, true)} className="text-[10px] text-pb-faint underline">V</button>}
                    {active && !p.is_captain && !p.is_vice_captain && (
                      <button onClick={() => setSwapOut(swapOut?.player_id === p.player_id ? null : p)} className="text-[10px] underline" style={{ color: 'var(--pb-accent)' }}>swap</button>
                    )}
                  </span>
                </div>
                {swapOut?.player_id === p.player_id && (
                  <div className="ml-2 mt-1 mb-2 border-l pb-hairline pl-2 space-y-1">
                    {sameRolePool(p.role).slice(0, 30).map(c => (
                      <button key={c.player_id} onClick={() => doTransfer(c.player_id)}
                        className="w-full flex justify-between text-xs py-1 text-pb-faint hover:text-pb-text">
                        <span>{c.name}</span><span className="tabular-nums">{money(c.price)}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )
      })}
    </div>
  )
}

// ── Ladder + leagues ───────────────────────────────────────────────────────

function LadderList({ rows }) {
  if (!rows?.length) return <p className="text-sm text-pb-faint">No teams yet.</p>
  return (
    <div className="pb-card">
      {rows.map((r, i) => (
        <div key={r.rank} className={`flex items-center justify-between px-3 py-2 text-sm ${i ? 'border-t pb-hairline' : ''}`}>
          <span className="flex gap-2"><span className="text-pb-faint w-5 text-right">{r.rank}</span><span>{r.team_name} <span className="text-pb-faintest text-xs">{r.manager}</span></span></span>
          <span className="font-bold tabular-nums">{money(r.points)}</span>
        </div>
      ))}
    </div>
  )
}

function Ladder({ token }) {
  const [rows, setRows] = useState(null)
  useEffect(() => { api.fanLadder(token).then(d => setRows(d.ladder)).catch(() => setRows([])) }, [token])
  if (rows === null) return <p className="text-pb-faint text-sm">Loading…</p>
  return <LadderList rows={rows} />
}

function Leagues({ token, flash, fail }) {
  const [leagues, setLeagues] = useState(null)
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const load = useCallback(() => api.fanLeagues(token).then(d => setLeagues(d.leagues)).catch(() => setLeagues([])), [token])
  useEffect(() => { load() }, [load])

  const create = async () => { try { const r = await api.fanCreateLeague(token, name); flash(`Created — code ${r.league.join_code}`); setName(''); await load() } catch (e) { fail(e) } }
  const join = async () => { try { await api.fanJoinLeague(token, code); flash('Joined.'); setCode(''); await load() } catch (e) { fail(e) } }

  return (
    <div className="space-y-4">
      <div className="pb-card p-3 space-y-2">
        <div className="text-xs text-pb-faint">Create a private league</div>
        <div className="flex gap-2">
          <input className="flex-1 rounded-lg border pb-hairline bg-pb-surface px-3 py-2 text-sm" placeholder="League name" value={name} onChange={e => setName(e.target.value)} />
          <button onClick={create} className={btnAccent} style={accentStyle}>Create</button>
        </div>
        <div className="text-xs text-pb-faint pt-1">Join with a code</div>
        <div className="flex gap-2">
          <input className="flex-1 rounded-lg border pb-hairline bg-pb-surface px-3 py-2 text-sm uppercase" placeholder="CODE" value={code} onChange={e => setCode(e.target.value)} />
          <button onClick={join} className={`${btn} bg-pb-surface2 text-pb-text`}>Join</button>
        </div>
      </div>
      {leagues === null ? <p className="text-pb-faint text-sm">Loading…</p>
        : !leagues.length ? <p className="text-sm text-pb-faint">You're not in any private leagues yet.</p>
        : leagues.map(lg => (
          <div key={lg.id}>
            <div className="flex items-center justify-between mb-1">
              <div className="font-display font-bold text-sm">{lg.name}</div>
              <div className="text-[11px] font-mono text-pb-faint">{lg.join_code}</div>
            </div>
            <LadderList rows={lg.ladder} />
          </div>
        ))}
    </div>
  )
}

// ── Draft ────────────────────────────────────────────────────────────────────

function Draft({ token, flash, fail }) {
  const [leagues, setLeagues] = useState(null)
  const [active, setActive] = useState(null)
  const [state, setState] = useState(null)
  const [ladder, setLadder] = useState(null)

  const loadLeagues = useCallback(() => api.fanDraftLeagues(token).then(d => setLeagues(d.leagues)).catch(() => setLeagues([])), [token])
  useEffect(() => { loadLeagues() }, [loadLeagues])

  const refresh = useCallback(async (id) => {
    try {
      const s = await api.fanDraftState(token, id); setState(s)
      if (s.status === 'complete') setLadder(await api.fanDraftLadder(token, id).catch(() => null))
    } catch (e) { fail(e) }
  }, [token, fail])

  useEffect(() => {
    if (!active || state?.status !== 'in_progress') return
    const t = setInterval(() => refresh(active), 10000)
    return () => clearInterval(t)
  }, [active, state?.status, refresh])

  const enter = async (id) => { setActive(id); setState(null); setLadder(null); await refresh(id) }
  const join = async (id) => { try { await api.fanJoinDraft(token, id); flash('Joined the draft league.'); await loadLeagues() } catch (e) { fail(e) } }
  const pick = async (pid) => { try { await api.fanDraftPick(token, active, pid); await refresh(active) } catch (e) { fail(e) } }

  if (active) return <DraftBoard state={state} ladder={ladder} onBack={() => { setActive(null); setState(null) }} onPick={pick} />

  if (leagues === null) return <p className="text-pb-faint text-sm">Loading…</p>
  if (!leagues.length) return <p className="text-sm text-pb-faint">No draft leagues yet. Your club admin sets these up.</p>
  return (
    <div className="space-y-2">
      {leagues.map(lg => (
        <div key={lg.id} className="pb-card p-3 flex items-center justify-between text-sm">
          <div>
            <div className="font-medium">{lg.name}</div>
            <div className="text-xs text-pb-faint">{lg.draft_type} · {lg.scoring_type === 'h2h' ? 'head-to-head' : 'total points'} · {lg.members}/{lg.capacity} · {lg.draft_status || 'not started'}</div>
          </div>
          {lg.joined
            ? <button onClick={() => enter(lg.id)} className="px-3 py-1.5 rounded-lg text-pb-bg text-xs" style={accentStyle}>Open</button>
            : (!lg.draft_status || lg.draft_status === 'scheduled')
              ? <button onClick={() => join(lg.id)} className="px-3 py-1.5 rounded-lg bg-pb-surface2 text-pb-text text-xs">Join</button>
              : <span className="text-xs text-pb-faintest">drafting</span>}
        </div>
      ))}
    </div>
  )
}

function DraftBoard({ state, ladder, onBack, onPick }) {
  if (!state) return <p className="text-pb-faint text-sm">Loading…</p>
  const needed = (role) => (state.quota?.[role] || 0) - (state.my_role_counts?.[role] || 0)
  return (
    <div className="space-y-4">
      <button onClick={onBack} className="text-xs text-pb-faint underline">← all draft leagues</button>
      {state.status === 'not_started' && <div className="pb-card p-4 text-sm text-pb-faint">The draft hasn't started yet. Your admin will kick it off.</div>}
      {state.status === 'in_progress' && (
        <>
          <div className="pb-card p-3 text-sm">
            {state.my_turn
              ? <span className="font-bold" style={{ color: 'var(--pb-accent)' }}>You're on the clock — pick a player.</span>
              : <span className="text-pb-faint">On the clock: <span className="text-pb-text">{state.on_clock?.manager}</span> (round {state.on_clock?.round})</span>}
          </div>
          {state.my_turn && (
            <div className="pb-card p-3">
              <div className="text-xs text-pb-faint mb-2">Still need: {ROLE_ORDER.filter(r => needed(r) > 0).map(r => `${needed(r)} ${ROLE_LABEL[r].toLowerCase()}`).join(', ') || 'nothing'}</div>
              <div className="space-y-1 max-h-80 overflow-y-auto">
                {state.available.filter(p => needed(p.role) > 0).slice(0, 60).map(p => (
                  <button key={p.player_id} onClick={() => onPick(p.player_id)}
                    className="w-full flex justify-between px-3 py-2 rounded-lg bg-pb-surface text-sm border pb-hairline">
                    <span>{p.name} <span className="text-pb-faintest text-xs">{ROLE_LABEL[p.role]}</span></span>
                    <span className="tabular-nums text-pb-faint">{money(p.price)}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="pb-card p-3">
            <div className="text-xs text-pb-faint mb-1">Picks</div>
            <div className="space-y-0.5 max-h-60 overflow-y-auto text-sm">
              {state.picks.slice().reverse().map(pk => (
                <div key={pk.pick} className="flex justify-between">
                  <span><span className="text-pb-faintest">{pk.pick}.</span> {pk.player}</span>
                  <span className="text-pb-faint text-xs">{pk.manager}{pk.auto ? ' (auto)' : ''}</span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
      {state.status === 'complete' && (
        <>
          <div className="pb-card p-3 text-sm text-pb-faint">Draft complete. Your squad now scores each round.</div>
          {ladder && <LadderList rows={ladder.type === 'h2h'
            ? ladder.ladder.map(r => ({ rank: r.rank, team_name: r.team_name, manager: `${r.w}-${r.l}-${r.d}`, points: r.pts }))
            : ladder.ladder} />}
        </>
      )}
    </div>
  )
}
