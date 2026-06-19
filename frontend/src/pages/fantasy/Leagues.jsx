// Leagues — create / join mini-leagues, each league's detail (Standings /
// Matchups / About) and a round head-to-head against another member.
import { useEffect, useState, useCallback } from 'react'
import { api } from '../../lib/api'
import { DISP, tintBg, pts, Btn, Field } from './ui'
import { ScreenTitle } from './shell'
import { LadderRow } from './Ladder'

export default function Leagues({ token, flash, fail, desktop }) {
  const [open, setOpen] = useState(null)   // league id
  if (open) return (
    <div style={desktop ? { maxWidth: 820, margin: '0 auto' } : undefined}>
      <LeagueDetail token={token} leagueId={open} onBack={() => setOpen(null)} flash={flash} fail={fail} />
    </div>
  )
  return <LeaguesHome token={token} onOpen={setOpen} flash={flash} fail={fail} desktop={desktop} />
}

function LeaguesHome({ token, onOpen, flash, fail, desktop }) {
  const [leagues, setLeagues] = useState(null)
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const load = useCallback(() => api.fanLeagues(token).then(d => setLeagues(d.leagues)).catch(() => setLeagues([])), [token])
  useEffect(() => { load() }, [load])

  const create = async () => { try { const r = await api.fanCreateLeague(token, name); flash(`Created. Code ${r.league.join_code}`); setName(''); await load() } catch (e) { fail(e) } }
  const join = async () => { try { await api.fanJoinLeague(token, code); flash('Joined.'); setCode(''); await load() } catch (e) { fail(e) } }

  return (
    <div>
      <ScreenTitle title="Mini-leagues" sub="Play your mates" />
      <div style={{ paddingTop: 14, display: 'flex', flexDirection: 'column', gap: 9, maxWidth: desktop ? 560 : undefined }}>
        <div style={{ font: `600 9.5px 'Hanken Grotesk'`, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--faint)' }}>Create a private league</div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Field placeholder="League name…" value={name} onChange={e => setName(e.target.value)} style={{ padding: '10px 12px', fontSize: 12.5 }} />
          <Btn onClick={create} disabled={!name.trim()} style={{ padding: '10px 16px', fontSize: 12.5 }}>Create</Btn>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Field placeholder="CODE" value={code} onChange={e => setCode(e.target.value.toUpperCase())} style={{ padding: '10px 12px', fontSize: 12.5, letterSpacing: '.18em' }} />
          <Btn variant="soft" onClick={join} disabled={!code.trim()} style={{ padding: '10px 18px', fontSize: 12.5 }}>Join</Btn>
        </div>
      </div>

      <div style={desktop
        ? { paddingTop: 18, display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: 18, alignItems: 'start' }
        : { paddingTop: 18, display: 'flex', flexDirection: 'column', gap: 16 }}>
        {leagues === null ? <p style={{ color: 'var(--faint)', font: `500 13px 'Hanken Grotesk'` }}>Loading…</p>
          : !leagues.length ? <p style={{ font: `500 13px 'Hanken Grotesk'`, color: 'var(--faint)' }}>You're not in any private leagues yet.</p>
            : leagues.map(lg => {
              const you = (lg.ladder || []).find(r => r.you)
              return (
                <button key={lg.id} onClick={() => onOpen(lg.id)} style={{ textAlign: 'left', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 9 }}>
                    <div>
                      <div style={{ font: `800 15px ${DISP}`, textTransform: 'uppercase', color: 'var(--text)' }}>{lg.name}</div>
                      <div style={{ font: `500 10.5px 'Hanken Grotesk'`, color: 'var(--faint)', marginTop: 1 }}>{you ? `You're ${ordr(you.rank)} of ${lg.members}` : `${lg.members} managers`}</div>
                    </div>
                    <div style={{ font: `700 11px 'Hanken Grotesk'`, letterSpacing: '.14em', color: 'var(--accent-strong)', background: tintBg(14), border: `1px solid ${tintBg(30)}`, padding: '5px 9px', borderRadius: 7 }}>{lg.join_code}</div>
                  </div>
                  <div style={{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 14, overflow: 'hidden' }}>
                    {(lg.ladder || []).slice(0, 4).map(r => <MiniRow key={r.rank} r={r} />)}
                  </div>
                </button>
              )
            })}
      </div>
    </div>
  )
}

function MiniRow({ r }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 11, padding: '10px 13px',
      borderBottom: '1px solid var(--surface2)',
      background: r.you ? tintBg(14) : 'transparent', borderLeft: r.you ? '3px solid var(--pb-accent, #8C82F0)' : '3px solid transparent',
    }}>
      <span style={{ width: 18, textAlign: 'center', font: `700 15px ${DISP}`, color: r.you ? 'var(--text)' : 'var(--dim)' }}>{r.rank}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ font: `700 13px 'Hanken Grotesk'`, color: 'var(--text)' }}>{r.team_name}{r.you && <span style={{ marginLeft: 6, font: `600 9px 'Hanken Grotesk'`, color: 'var(--ink)', background: 'var(--pb-accent, #8C82F0)', padding: '1px 5px', borderRadius: 4 }}>YOU</span>}</div>
        <div style={{ font: `500 10px 'Hanken Grotesk'`, color: r.you ? 'var(--accent-strong)' : 'var(--faint)' }}>{r.manager}</div>
      </div>
      <span style={{ font: `700 16px ${DISP}`, color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{pts(r.points)}</span>
    </div>
  )
}

function LeagueDetail({ token, leagueId, onBack, flash, fail }) {
  const [data, setData] = useState(null)
  const [tab, setTab] = useState('standings')
  const load = useCallback(() => api.fanLeague(token, leagueId).then(setData).catch(() => fail(new Error('Could not load league'))), [token, leagueId, fail])
  useEffect(() => { load() }, [load])

  if (!data) return <p style={{ color: 'var(--faint)', font: `500 13px 'Hanken Grotesk'` }}>Loading…</p>

  const invite = async () => {
    const text = `Join my Better Cricket fantasy league with code ${data.join_code}`
    try { if (navigator.share) await navigator.share({ text }); else { await navigator.clipboard.writeText(data.join_code); flash('Code copied.') } }
    catch { /* dismissed */ }
  }
  const leave = async () => { try { await api.fanLeaveLeague(token, leagueId); flash('Left the league.'); onBack() } catch (e) { fail(e) } }

  return (
    <div>
      <div style={{ position: 'relative', overflow: 'hidden', borderRadius: 16, padding: '10px 0 0' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button onClick={onBack} aria-label="Back" style={{ width: 30, height: 30, borderRadius: '50%', cursor: 'pointer', flex: 'none', background: 'var(--surface2)', border: '1px solid var(--hairline2)', color: 'var(--dim)', font: `700 16px 'Hanken Grotesk'` }}>{'‹'}</button>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ font: `800 18px ${DISP}`, textTransform: 'uppercase', color: 'var(--text)' }}>{data.name}</div>
            <div style={{ font: `500 10px 'Hanken Grotesk'`, color: 'var(--faint)' }}>{data.members} managers · classic scoring</div>
          </div>
          <div style={{ font: `700 11px 'Hanken Grotesk'`, letterSpacing: '.14em', color: 'var(--accent-strong)', background: tintBg(14), border: `1px solid ${tintBg(30)}`, padding: '5px 9px', borderRadius: 7 }}>{data.join_code}</div>
        </div>
        <div style={{ display: 'flex', gap: 6, marginTop: 14 }}>
          {[['standings', 'Standings'], ['matchups', 'Matchups'], ['about', 'About']].map(([k, l]) => {
            const on = tab === k
            return <button key={k} onClick={() => setTab(k)} style={{ font: `${on ? 700 : 600} 11.5px 'Hanken Grotesk'`, color: on ? 'var(--ink)' : 'var(--dim)', background: on ? 'var(--pb-accent, #8C82F0)' : 'var(--surface2)', padding: '7px 13px', borderRadius: 8, border: 'none', cursor: 'pointer' }}>{l}</button>
          })}
        </div>
      </div>

      <div style={{ paddingTop: 14 }}>
        {tab === 'standings' && (data.ladder || []).map(r => <LadderRow key={r.rank} r={r} />)}
        {tab === 'matchups' && <H2H token={token} leagueId={leagueId} members={data.ladder || []} mySquadId={data.my_squad_id} />}
        {tab === 'about' && (
          <div>
            <div style={{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 13, overflow: 'hidden' }}>
              <Meta k="Members" v={data.members} />
              <Meta k="Scoring" v="Classic · total points" />
              {data.created_by && <Meta k="Run by" v={data.created_by} />}
              <Meta k="Join code" v={data.join_code} last />
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <Btn full onClick={invite} style={{ padding: 11, fontSize: 12.5 }}>Invite · share code</Btn>
              {data.is_member && <Btn variant="soft" onClick={leave} style={{ padding: '11px 15px', fontSize: 12.5 }}>Leave</Btn>}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

const Meta = ({ k, v, last }) => (
  <div style={{ display: 'flex', alignItems: 'center', padding: '12px 14px', borderBottom: last ? 'none' : '1px solid var(--surface2)' }}>
    <span style={{ flex: 1, font: `600 12.5px 'Hanken Grotesk'`, color: 'var(--dim)' }}>{k}</span>
    <span style={{ font: `700 12.5px 'Hanken Grotesk'`, color: 'var(--text)' }}>{v}</span>
  </div>
)

function H2H({ token, leagueId, members, mySquadId }) {
  const opps = members.filter(m => m.squad_id !== mySquadId)
  const [opp, setOpp] = useState(opps[0]?.squad_id || '')
  const [data, setData] = useState(null)
  useEffect(() => {
    if (!opp) { setData({ empty: true }); return }
    setData(null)
    api.fanH2H(token, leagueId, { opponent_squad_id: opp }).then(setData).catch(() => setData({ empty: true }))
  }, [token, leagueId, opp])

  if (!opps.length) return <p style={{ font: `500 12.5px 'Hanken Grotesk'`, color: 'var(--faint)' }}>No one else has joined yet.</p>

  return (
    <div>
      <div style={{ marginBottom: 12 }}>
        <select value={opp} onChange={e => setOpp(e.target.value)} style={{ width: '100%', background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 10, padding: '9px 12px', font: `600 12.5px 'Hanken Grotesk'`, color: 'var(--text)', outline: 'none' }}>
          {opps.map(o => <option key={o.squad_id} value={o.squad_id}>vs {o.team_name}</option>)}
        </select>
      </div>
      {!data ? <p style={{ color: 'var(--faint)', font: `500 12.5px 'Hanken Grotesk'` }}>Loading…</p>
        : data.empty || !data.me ? <p style={{ color: 'var(--faint)', font: `500 12.5px 'Hanken Grotesk'` }}>No scored round to compare yet.</p>
          : <H2HCard data={data} />}
    </div>
  )
}

function H2HCard({ data }) {
  return (
    <div>
      <div style={{ position: 'relative', overflow: 'hidden', borderRadius: 16, padding: '14px 6px 16px', marginBottom: 6 }}>
        <div style={{ textAlign: 'center', font: `600 9.5px 'Hanken Grotesk'`, letterSpacing: '.18em', textTransform: 'uppercase', color: 'var(--faint)' }}>Round {data.round?.number} · head-to-head</div>
        <div style={{ display: 'flex', alignItems: 'center', marginTop: 12 }}>
          <Side s={data.me} you />
          <div style={{ font: `800 16px ${DISP}`, color: 'var(--faint)', padding: '0 6px' }}>vs</div>
          <Side s={data.opp} />
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {(data.rows || []).map((r, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Cell text={r.mine} lead={r.me_lead} align="right" />
            <div style={{ width: 74, textAlign: 'center', font: `600 8.5px 'Hanken Grotesk'`, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--faint)' }}>{r.role}</div>
            <Cell text={r.theirs} lead={r.opp_lead} cyan />
          </div>
        ))}
      </div>
    </div>
  )
}

const Side = ({ s, you }) => (
  <div style={{ flex: 1, textAlign: 'center' }}>
    <div style={{ font: `800 15px ${DISP}`, textTransform: 'uppercase', color: 'var(--text)' }}>{s.team}</div>
    <div style={{ font: `500 10px 'Hanken Grotesk'`, color: you ? 'var(--accent-strong)' : 'var(--faint)' }}>{s.manager}{you ? ' · YOU' : ''}</div>
    <div style={{ font: `800 46px/0.9 ${DISP}`, color: you ? 'var(--text)' : 'var(--dim)', marginTop: 6, fontVariantNumeric: 'tabular-nums' }}>{pts(s.score)}</div>
  </div>
)
const Cell = ({ text, lead, align, cyan }) => (
  <div style={{
    flex: 1, textAlign: align || 'left', borderRadius: 8, padding: '9px 12px',
    font: `${lead ? 700 : 600} 12px 'Hanken Grotesk'`,
    color: lead ? (cyan ? '#22a8c4' : 'var(--accent-strong)') : 'var(--dim)',
    background: lead ? (cyan ? 'color-mix(in srgb, #22D3EE 11%, transparent)' : tintBg(11)) : 'var(--surface)',
    border: lead ? 'none' : '1px solid var(--hairline)',
  }}>{text}</div>
)

const ordr = (n) => `${n}${(n % 100 >= 11 && n % 100 <= 13) ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th')}`
