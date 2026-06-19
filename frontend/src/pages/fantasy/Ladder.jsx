// Club ladder — ranked squads with round-on-round movement arrows, the GW and
// total columns, and the manager's own row highlighted. A "···" marks the jump
// to the manager's position when they sit below the visible window.
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { DISP, pts, tintBg, MoveArrow } from './ui'
import { ScreenTitle } from './shell'

export function LadderRow({ r, compact }) {
  if (r.you) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '11px 12px', margin: '3px 0', borderRadius: 13, background: tintBg(14, 'var(--bg)'), border: `1px solid ${tintBg(40)}` }}>
        <span style={{ width: 24, textAlign: 'center', font: `700 16px ${DISP}`, color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{r.rank}</span>
        {!compact && <MoveArrow delta={r.rank_delta} />}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ font: `700 13.5px 'Hanken Grotesk'`, color: 'var(--text)' }}>{r.team_name} <span style={{ font: `700 9px 'Hanken Grotesk'`, color: 'var(--ink)', background: 'var(--pb-accent, #8C82F0)', padding: '1px 5px', borderRadius: 4, verticalAlign: 'middle' }}>YOU</span></div>
          <div style={{ font: `500 10.5px 'Hanken Grotesk'`, color: 'var(--accent-strong)' }}>{r.manager}</div>
        </div>
        {!compact && <span style={{ font: `600 12px ${DISP}`, color: 'var(--dim)', fontVariantNumeric: 'tabular-nums' }}>{pts(r.gw)}</span>}
        <span style={{ width: 50, textAlign: 'right', font: `700 16px ${DISP}`, color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{pts(r.points)}</span>
      </div>
    )
  }
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '10px 12px', borderBottom: '1px solid var(--surface2)' }}>
      <span style={{ width: 24, textAlign: 'center', font: `700 16px ${DISP}`, color: 'var(--dim)', fontVariantNumeric: 'tabular-nums' }}>{r.rank}</span>
      {!compact && <MoveArrow delta={r.rank_delta} />}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ font: `700 13.5px 'Hanken Grotesk'`, color: 'var(--text)' }}>{r.team_name}</div>
        <div style={{ font: `500 10.5px 'Hanken Grotesk'`, color: 'var(--faint)' }}>{r.manager}</div>
      </div>
      {!compact && <span style={{ font: `600 12px ${DISP}`, color: 'var(--faint)', fontVariantNumeric: 'tabular-nums' }}>{pts(r.gw)}</span>}
      <span style={{ width: 50, textAlign: 'right', font: `700 16px ${DISP}`, color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{pts(r.points)}</span>
    </div>
  )
}

const Th = ({ children, w, right }) => (
  <span style={{ width: w, flex: w ? undefined : 1, textAlign: right ? 'right' : 'left', font: `700 8.5px 'Hanken Grotesk'`, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--faint)' }}>{children}</span>
)

const ordSuffix = (n) => (n % 100 >= 11 && n % 100 <= 13) ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th')

// A highlight card for the desktop rail — the manager's own row and the leader.
function PositionCard({ r, label, you }) {
  return (
    <div style={{ background: you ? tintBg(10, 'var(--surface)') : 'var(--surface)', border: `1px solid ${you ? tintBg(30) : 'var(--hairline)'}`, borderRadius: 16, padding: 16 }}>
      <div style={{ font: `700 9.5px 'Hanken Grotesk'`, letterSpacing: '.14em', textTransform: 'uppercase', color: you ? 'var(--accent-strong)' : 'var(--faint)' }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 8 }}>
        <span style={{ font: `800 34px ${DISP}`, color: 'var(--text)', lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>{r.rank}<span style={{ font: `700 14px ${DISP}`, color: 'var(--faint)' }}>{ordSuffix(r.rank)}</span></span>
        <MoveArrow delta={r.rank_delta} />
      </div>
      <div style={{ font: `800 16px ${DISP}`, textTransform: 'uppercase', color: 'var(--text)', marginTop: 12, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.team_name}</div>
      <div style={{ font: `500 11px 'Hanken Grotesk'`, color: 'var(--faint)' }}>{r.manager}</div>
      <div style={{ display: 'flex', gap: 20, marginTop: 13 }}>
        <div>
          <div style={{ font: `700 8.5px 'Hanken Grotesk'`, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--faint)' }}>Total</div>
          <div style={{ font: `800 22px ${DISP}`, color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>{pts(r.points)}</div>
        </div>
        <div>
          <div style={{ font: `700 8.5px 'Hanken Grotesk'`, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--faint)' }}>This round</div>
          <div style={{ font: `800 22px ${DISP}`, color: 'var(--dim)', fontVariantNumeric: 'tabular-nums' }}>{pts(r.gw)}</div>
        </div>
      </div>
    </div>
  )
}

export default function Ladder({ token, season, desktop }) {
  const [data, setData] = useState(null)
  useEffect(() => { api.fanLadder(token).then(setData).catch(() => setData({ ladder: [] })) }, [token])
  if (!data) return <p style={{ color: 'var(--faint)', font: `500 13px 'Hanken Grotesk'` }}>Loading…</p>
  const rows = data.ladder || []
  if (!rows.length) return (
    <div>
      <ScreenTitle title="Club ladder" />
      <p style={{ font: `500 13px 'Hanken Grotesk'`, color: 'var(--faint)', paddingTop: 16 }}>No teams yet. Be the first to build a squad.</p>
    </div>
  )

  const top = rows.slice(0, 20)
  const me = rows.find(r => r.you)
  const showJump = me && !top.some(r => r.you)
  const leader = rows[0]

  const header = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '13px 0 7px' }}>
      <Th w={24}>#</Th><span style={{ width: 18 }} /><Th>Team</Th><Th>GW</Th><Th w={50} right>Total</Th>
    </div>
  )
  const tableRows = (
    <div>
      {top.map(r => <LadderRow key={r.rank} r={r} />)}
      {showJump && (
        <>
          <div style={{ textAlign: 'center', color: 'var(--faintest)', font: `700 14px ${DISP}`, padding: '4px 0' }}>· · ·</div>
          <LadderRow r={me} />
        </>
      )}
    </div>
  )

  if (desktop) {
    return (
      <div>
        <ScreenTitle title="Club ladder" sub={`${rows.length} managers`} />
        <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: 22, alignItems: 'start', paddingTop: 16 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14, position: 'sticky', top: 12 }}>
            {me && <PositionCard r={me} label="Your position" you />}
            {leader && (!me || !leader.you) && <PositionCard r={leader} label="Top of the table" />}
          </div>
          <div style={{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 16, padding: '4px 16px 12px' }}>
            {header}
            {tableRows}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div>
      <ScreenTitle title="Club ladder" sub={`${rows.length} managers`} />
      {header}
      {tableRows}
    </div>
  )
}
