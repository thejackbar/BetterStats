// Every team in the league as it was locked for the most recently locked round, two ways: a list (tap a row
// to open the XI) and a stack of trading cards you swap through. Both read one request, `GET /teams`, which
// shows exactly what opening each team on its own does: no transfers lined up for later, no prices or bank.
// A card can be shared as an image, the manager's own included.
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../lib/api'
import { exportNodePng } from '../../lib/exportNodePng'
import CardSwap from '../../components/CardSwap'
import { DISP, pts, tintBg, MoveArrow, Avatar, Btn, Segmented, PINK, useFantasy, fantasyName } from './ui'
import { ScreenTitle } from './shell'
import { LineupList } from './Points'

const CHIP = { wildcard: 'Wildcard', triple_captain: 'Triple Captain', bench_boost: 'Bench Boost', free_hit: 'Free Hit' }
const MODE_KEY = 'bfc_teams_mode'
const CARD_W = 300
const CARD_H = 520
const ordSuffix = (n) => (n % 100 >= 11 && n % 100 <= 13) ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th')
const slug = (s) => String(s || 'team').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'team'

function readMode() {
  try { return localStorage.getItem(MODE_KEY) === 'cards' ? 'cards' : 'list' } catch { return 'list' }
}
function saveMode(m) { try { localStorage.setItem(MODE_KEY, m) } catch { /* private window */ } }

const note = { font: `500 12px 'Hanken Grotesk',sans-serif`, color: 'var(--faint)' }

// One manager's trading card, drawn flat. The stack moves it in 3D; sharing renders this same markup to a PNG.
export function TeamCard({ team, round }) {
  const { club, crest, logoUrl } = useFantasy()
  const lineup = team.lineup || []
  const firstBench = lineup.findIndex(e => !e.counted)
  const host = (typeof window !== 'undefined' && window.location?.host) || 'betterat.cricket'
  const chip = team.chip_used ? CHIP[team.chip_used] || team.chip_used : null
  return (
    <div data-theme="dark" style={{
      position: 'relative', width: CARD_W, height: CARD_H, borderRadius: 22, overflow: 'hidden', background: '#0a0d14', color: '#fff',
      fontFamily: "'Hanken Grotesk',sans-serif", boxShadow: '0 18px 40px rgba(0,0,0,.45), inset 0 0 0 1px rgba(255,255,255,.14)',
      backfaceVisibility: 'hidden',
    }}>
      <div style={{
        position: 'absolute', inset: 0,
        background: `radial-gradient(120% 55% at 0% 0%, color-mix(in srgb, var(--pb-accent, #06B6D4) 60%, transparent), transparent 62%), radial-gradient(90% 45% at 100% 100%, ${PINK}40, transparent 62%)`,
      }} />
      <div style={{ position: 'relative', height: '100%', padding: '18px 16px 12px', display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
          <div style={{ font: `800 46px/0.85 ${DISP}`, fontVariantNumeric: 'tabular-nums' }}>
            {team.rank}<span style={{ font: `700 16px ${DISP}`, color: 'rgba(255,255,255,.6)' }}>{ordSuffix(team.rank)}</span>
          </div>
          <div style={{ paddingTop: 2 }}><MoveArrow delta={team.rank_delta} /></div>
          {team.you && <span style={{ marginTop: 3, font: `800 9px ${DISP}`, letterSpacing: '.06em', background: '#fff', color: '#0a0d14', padding: '2px 6px', borderRadius: 5 }}>YOU</span>}
          <div style={{ marginLeft: 'auto' }}>
            {logoUrl
              ? <img src={logoUrl} alt="" style={{ width: 30, height: 30, borderRadius: 9, objectFit: 'contain', background: '#fff', padding: 3 }} />
              : <div style={{ width: 30, height: 30, borderRadius: 9, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#fff', color: '#0a0d14', font: `800 10px ${DISP}` }}>{crest}</div>}
          </div>
        </div>
        <div style={{ font: `800 23px/1.05 ${DISP}`, textTransform: 'uppercase', marginTop: 12, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{team.team_name}</div>
        <div style={{ font: `600 11px 'Hanken Grotesk',sans-serif`, color: 'rgba(255,255,255,.7)', marginTop: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{team.manager}</div>

        <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
          {[[round?.status === 'live' ? 'Live points' : `Round ${round?.number ?? ''}`, team.points != null ? pts(team.points) : '-'], ['Total', pts(team.total_points)]].map(([l, v]) => (
            <div key={l} style={{ flex: 1, background: 'rgba(255,255,255,.1)', border: '1px solid rgba(255,255,255,.14)', borderRadius: 12, padding: '8px 10px' }}>
              <div style={{ font: `700 8.5px 'Hanken Grotesk',sans-serif`, letterSpacing: '.14em', textTransform: 'uppercase', color: 'rgba(255,255,255,.65)' }}>{l}</div>
              <div style={{ font: `800 24px/1 ${DISP}`, marginTop: 3, fontVariantNumeric: 'tabular-nums' }}>{v}</div>
            </div>
          ))}
        </div>
        {chip && <div style={{ alignSelf: 'flex-start', marginTop: 8, font: `700 9.5px 'Hanken Grotesk',sans-serif`, letterSpacing: '.08em', textTransform: 'uppercase', background: 'rgba(255,255,255,.16)', padding: '3px 8px', borderRadius: 6 }}>{chip} played</div>}

        <div style={{ marginTop: 10, flex: 1, minHeight: 0, overflow: 'hidden' }}>
          {team.lineup ? lineup.map((e, i) => (
            <div key={e.player_id}>
              {i === firstBench && firstBench > 0 && <div style={{ font: `700 8px 'Hanken Grotesk',sans-serif`, letterSpacing: '.16em', textTransform: 'uppercase', color: 'rgba(255,255,255,.5)', padding: '4px 0 2px' }}>Bench</div>}
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, height: 23, opacity: e.counted ? 1 : 0.55 }}>
                <Avatar name={e.name} photoUrl={e.photo_url} size={19} accentRing={false} />
                <div style={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: 5 }}>
                  <span style={{ minWidth: 0, font: `700 11.5px 'Hanken Grotesk',sans-serif`, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{e.name}</span>
                  {e.captained && <span style={{ flex: 'none', font: `800 8px ${DISP}`, background: '#fff', color: '#0a0d14', width: 14, height: 14, borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>C</span>}
                </div>
                <span style={{ width: 30, textAlign: 'right', font: `700 13px ${DISP}`, fontVariantNumeric: 'tabular-nums' }}>{pts(e.eff_points != null ? e.eff_points : e.points)}</span>
              </div>
            </div>
          )) : <p style={{ font: `500 12px 'Hanken Grotesk',sans-serif`, color: 'rgba(255,255,255,.7)', lineHeight: 1.5, margin: '14px 0 0' }}>{team.note || 'No locked team on record.'}</p>}
        </div>
        <div style={{ font: `600 9px 'Hanken Grotesk',sans-serif`, color: 'rgba(255,255,255,.5)', textAlign: 'center', paddingTop: 6 }}>
          {fantasyName(club) || `${club?.name || 'Club'} Fantasy`} · {host}
        </div>
      </div>
    </div>
  )
}

function TeamRow({ t, open, onToggle, onShare, sharing }) {
  const cap = (t.lineup || []).find(e => e.captained)
  return (
    <div style={{
      margin: t.you ? '3px 0' : 0, borderRadius: t.you ? 13 : 0,
      background: t.you ? tintBg(14, 'var(--bg)') : undefined, border: t.you ? `1px solid ${tintBg(40)}` : undefined,
      borderBottom: t.you ? undefined : '1px solid var(--surface2)',
    }}>
      <button onClick={onToggle} aria-expanded={open} aria-label={`${open ? 'Hide' : 'Show'} ${t.team_name}'s team`} style={{
        display: 'flex', alignItems: 'center', gap: 11, width: '100%', padding: '10px 12px', textAlign: 'left', cursor: 'pointer', background: 'transparent', border: 'none',
      }}>
        <span style={{ width: 24, textAlign: 'center', font: `700 16px ${DISP}`, color: t.you ? 'var(--text)' : 'var(--dim)', fontVariantNumeric: 'tabular-nums' }}>{t.rank}</span>
        <MoveArrow delta={t.rank_delta} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ font: `700 13.5px 'Hanken Grotesk',sans-serif`, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {t.team_name}{t.you && <span style={{ marginLeft: 6, font: `700 9px 'Hanken Grotesk',sans-serif`, color: 'var(--ink)', background: 'var(--pb-accent, #06B6D4)', padding: '1px 5px', borderRadius: 4, verticalAlign: 'middle' }}>YOU</span>}
          </div>
          <div style={{ font: `500 10.5px 'Hanken Grotesk',sans-serif`, color: t.you ? 'var(--accent-strong)' : 'var(--faint)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {t.manager}{cap ? ` · C ${cap.name}` : ''}
          </div>
        </div>
        <span style={{ width: 40, textAlign: 'right', font: `600 12px ${DISP}`, color: 'var(--dim)', fontVariantNumeric: 'tabular-nums' }}>{t.points != null ? pts(t.points) : '-'}</span>
        <span style={{ width: 50, textAlign: 'right', font: `700 16px ${DISP}`, color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{pts(t.total_points)}</span>
        <span aria-hidden style={{ width: 12, color: 'var(--faint)', font: `700 12px 'Hanken Grotesk',sans-serif`, transform: open ? 'rotate(90deg)' : 'none', transition: 'transform .15s' }}>›</span>
      </button>
      {open && (
        <div style={{ padding: '2px 12px 14px' }}>
          {t.lineup
            ? <LineupList lineup={t.lineup} />
            : <p style={{ ...note, margin: '4px 0 8px' }}>{t.note}</p>}
          <div style={{ marginTop: 10 }}>
            <Btn variant="soft" disabled={sharing} onClick={onShare} style={{ padding: '9px 14px', fontSize: 12.5 }}>{sharing ? 'Rendering…' : 'Share this team'}</Btn>
          </div>
        </div>
      )}
    </div>
  )
}

const Th = ({ children, w, right }) => (
  <span style={{ width: w, flex: w ? undefined : 1, textAlign: right ? 'right' : 'left', font: `700 8.5px 'Hanken Grotesk',sans-serif`, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--faint)' }}>{children}</span>
)

export default function Teams({ token }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [mode, setMode] = useState(readMode)
  const [openId, setOpenId] = useState(null)
  const [front, setFront] = useState(0)
  const [start, setStart] = useState(0)
  const [sharing, setSharing] = useState('')
  const [shareErr, setShareErr] = useState('')
  const [exportTeam, setExportTeam] = useState(null)
  const swapRef = useRef(null)
  const exportRef = useRef(null)

  useEffect(() => {
    let on = true, timer = null, first = true
    setData(null); setErr('')
    const load = () => api.fanTeams(token).then(d => {
      if (!on) return
      setData(d)
      if (first) {   // open the stack on the manager's own team
        first = false
        const mine = (d.teams || []).findIndex(t => t.you)
        const at = mine >= 0 ? mine : 0
        setStart(at); setFront(at)
      }
      if (d?.round?.status !== 'live' && timer) { clearInterval(timer); timer = null }
    }).catch(e => on && setErr(e.message || 'Could not load the teams.'))
    load()
    timer = setInterval(load, 60000)
    return () => { on = false; if (timer) clearInterval(timer) }
  }, [token])

  const teams = useMemo(() => data?.teams || [], [data])
  const round = data?.round
  const youIdx = teams.findIndex(t => t.you)

  const pick = (m) => { setMode(m); saveMode(m) }

  const share = async (t) => {
    setSharing(t.squad_id); setShareErr(''); setExportTeam(t)
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))
    try {
      await exportNodePng(exportRef.current, `${slug(t.team_name)}-round-${round?.number ?? ''}`, { width: CARD_W, height: CARD_H })
    } catch { setShareErr('Could not make the image. Try again.') } finally { setSharing(''); setExportTeam(null) }
  }

  if (err) {
    return (
      <div>
        <ScreenTitle title="Teams" />
        <p style={{ ...note, fontSize: 13, paddingTop: 16 }}>{err}</p>
      </div>
    )
  }
  if (!data) return <p style={{ ...note, fontSize: 13 }}>Loading…</p>
  if (!teams.length) {
    return (
      <div>
        <ScreenTitle title="Teams" />
        <p style={{ ...note, fontSize: 13, paddingTop: 16 }}>No teams yet.</p>
      </div>
    )
  }

  const frontTeam = teams[front] || teams[0]
  return (
    <div>
      <ScreenTitle title="Teams" sub={`${round.status === 'live' ? 'Live · ' : ''}Round ${round.number} · as locked`} />
      <div style={{ paddingTop: 14 }}>
        <Segmented options={[['list', 'List'], ['cards', 'Cards']]} value={mode} onChange={pick} />
      </div>

      {mode === 'list' ? (
        <div style={{ paddingTop: 6 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '13px 12px 7px' }}>
            <Th w={24}>#</Th><span style={{ width: 18 }} /><Th>Team</Th><Th w={40} right>Rd</Th><Th w={50} right>Total</Th><span style={{ width: 12 }} />
          </div>
          {teams.map(t => (
            <TeamRow key={t.squad_id} t={t} open={openId === t.squad_id}
              onToggle={() => setOpenId(openId === t.squad_id ? null : t.squad_id)}
              onShare={() => share(t)} sharing={sharing === t.squad_id} />
          ))}
        </div>
      ) : (
        <div style={{ paddingTop: 18 }}>
          <CardSwap ref={swapRef} width={CARD_W} height={CARD_H} initialFront={start} onFront={setFront}
            onCardClick={() => swapRef.current?.next()} label="Teams in this league">
            {teams.map(t => <TeamCard key={t.squad_id} team={t} round={round} />)}
          </CardSwap>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, paddingTop: 18 }}>
            <Btn variant="ghost" onClick={() => swapRef.current?.prev()} style={{ padding: '9px 16px' }}>‹ Prev</Btn>
            <span style={{ ...note, fontVariantNumeric: 'tabular-nums', minWidth: 64, textAlign: 'center' }}>{front + 1} of {teams.length}</span>
            <Btn variant="ghost" onClick={() => swapRef.current?.next()} style={{ padding: '9px 16px' }}>Next ›</Btn>
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap', paddingTop: 12 }}>
            <label style={{ display: 'flex' }}>
              <span style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)' }}>Jump to a team</span>
              <select value={front} onChange={e => swapRef.current?.goTo(Number(e.target.value))} style={{
                maxWidth: 190, background: 'var(--surface)', color: 'var(--text)', border: '1px solid var(--hairline)', borderRadius: 11, padding: '9px 10px', font: `600 12.5px 'Hanken Grotesk',sans-serif`,
              }}>
                {teams.map((t, i) => <option key={t.squad_id} value={i}>{t.rank}. {t.team_name}</option>)}
              </select>
            </label>
            {youIdx >= 0 && <Btn variant="soft" onClick={() => swapRef.current?.goTo(youIdx)} style={{ padding: '9px 14px', fontSize: 12.5 }}>My team</Btn>}
            <Btn disabled={!!sharing} onClick={() => share(frontTeam)} style={{ padding: '9px 14px', fontSize: 12.5 }}>{sharing ? 'Rendering…' : 'Share card'}</Btn>
          </div>
        </div>
      )}

      {shareErr && <p style={{ ...note, color: 'var(--red, #ef5b5b)', textAlign: 'center', paddingTop: 10 }}>{shareErr}</p>}
      <p style={{ ...note, fontSize: 11, paddingTop: 16 }}>
        Teams are shown as they were locked for round {round.number}. Anything a manager changes after that stays private until the next round locks.
      </p>

      {/* The card that gets rendered to an image; kept off screen and mounted only while sharing. */}
      <div aria-hidden style={{ position: 'fixed', left: -10000, top: 0, pointerEvents: 'none' }}>
        {exportTeam && <div ref={exportRef} style={{ width: CARD_W, height: CARD_H }}><TeamCard team={exportTeam} round={round} /></div>}
      </div>
    </div>
  )
}
