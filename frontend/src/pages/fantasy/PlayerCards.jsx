// My Team as cards: one trading card per player in the XI, grouped by role like the team sheet. A card is the
// same look as the share cards (black frame, the club's colour, the photo in a ring, an angled band along the
// bottom) at a size that fits two across a phone. Tapping one selects it; the actions for it (captain, vice,
// profile) open under its group exactly as they do on the sheet.
import { splitName } from '../../components/PlayerTradingCard'
import { DISP, ROLE_GROUP, ROLE_SHORT, money, pts, PriceArrow, Avatar } from './ui'
import { SectionLabel } from './shell'

export const CARD_W = 164
export const CARD_H = 236
const INK = '#050a0c'
const FRAME = 5
const PANEL_W = CARD_W - FRAME * 2

export function FantasyPlayerCard({ p, gw, selected, onClick }) {
  const { first, last } = splitName(p.name)
  const size = last.length <= 8 ? 21 : last.length <= 11 ? 17 : 14
  const photo = p.photo_url
  return (
    <button onClick={onClick} aria-pressed={!!selected} aria-label={`${p.name}${p.is_captain ? ', captain' : p.is_vice_captain ? ', vice captain' : ''}`} style={{
      position: 'relative', flex: 'none', width: CARD_W, height: CARD_H, padding: FRAME, boxSizing: 'border-box', border: 'none', cursor: 'pointer', textAlign: 'left',
      borderRadius: 18, background: INK, color: '#fff', fontFamily: "'Hanken Grotesk',sans-serif",
      boxShadow: selected ? '0 0 0 3px var(--pb-accent, #06B6D4), 0 10px 24px rgba(0,0,0,.35)' : '0 8px 20px rgba(0,0,0,.28)',
      transition: 'transform .15s', transform: selected ? 'translateY(-3px)' : 'none',
    }}>
      <div style={{
        position: 'relative', width: '100%', height: '100%', borderRadius: 13, overflow: 'hidden',
        background: 'linear-gradient(170deg, color-mix(in srgb, var(--pb-accent, #06B6D4) 88%, #000) 0%, color-mix(in srgb, var(--pb-accent, #06B6D4) 34%, #050a0c) 62%, #050a0c 100%)',
      }}>
        <div style={{ position: 'absolute', top: 0, right: -14, width: 110, height: 150, background: 'rgba(255,255,255,.1)', clipPath: 'polygon(40% 0, 100% 0, 100% 100%, 0 70%)' }} />
        <div style={{ position: 'absolute', top: 9, left: 9, font: `800 9px ${DISP}`, letterSpacing: '.08em', background: 'rgba(5,10,12,.6)', border: '1px solid rgba(255,255,255,.25)', padding: '2px 6px', borderRadius: 5 }}>{ROLE_SHORT[p.role] || ''}</div>
        {(p.is_captain || p.is_vice_captain) && (
          <div style={{ position: 'absolute', top: 8, right: 9, width: 20, height: 20, borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center', font: `800 11px ${DISP}`, background: p.is_captain ? '#fff' : 'rgba(255,255,255,.3)', color: p.is_captain ? INK : '#fff' }}>{p.is_captain ? 'C' : 'V'}</div>
        )}
        <div style={{ position: 'absolute', top: 30, left: (PANEL_W - 88) / 2, width: 88, height: 88, borderRadius: '50%', boxShadow: '0 0 0 3px color-mix(in srgb, var(--pb-accent, #06B6D4) 55%, #fff), 0 8px 18px rgba(0,0,0,.45)', overflow: 'hidden', background: 'rgba(5,10,12,.55)' }}>
          {photo
            ? <img src={photo} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: '50% 22%', display: 'block' }} />
            : <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Avatar name={p.name} size={88} accentRing={false} /></div>}
        </div>
        <div style={{ position: 'absolute', left: 6, right: 6, top: 126, textAlign: 'center' }}>
          {first && <div style={{ font: `600 italic 9.5px 'Hanken Grotesk',sans-serif`, textTransform: 'uppercase', letterSpacing: '.08em', opacity: 0.9, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{first}</div>}
          <div style={{ font: `800 italic ${size}px/1 ${DISP}`, textTransform: 'uppercase', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', textShadow: '0 2px 8px rgba(0,0,0,.5)' }}>{last}</div>
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 4, marginTop: 4, font: `600 10.5px 'Hanken Grotesk',sans-serif`, opacity: 0.92 }}>
            <span>{money(p.price ?? p.purchase_price)}</span><PriceArrow change={p.price_change} />
          </div>
        </div>
        <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: 52 }}>
          <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(180deg, var(--pb-accent, #06B6D4), color-mix(in srgb, var(--pb-accent, #06B6D4) 78%, #000))', clipPath: 'polygon(0 24%, 100% 0, 100% 100%, 0 100%)' }} />
          <div style={{ position: 'absolute', left: 0, right: 0, bottom: 6, textAlign: 'center', color: 'var(--ink, #fff)' }}>
            <div style={{ font: `800 26px/1 ${DISP}`, fontVariantNumeric: 'tabular-nums' }}>{gw != null ? pts(gw) : '-'}</div>
            <div style={{ font: `700 8px 'Hanken Grotesk',sans-serif`, letterSpacing: '.14em', textTransform: 'uppercase', opacity: 0.85, marginTop: 2 }}>pts</div>
          </div>
        </div>
      </div>
    </button>
  )
}

// Every role group, a grid of cards each, with the open player's actions under their group.
export default function SquadCards({ groups, gwPts, openId, onPlayer, actions, desktop }) {
  return (
    <div>
      {groups.map(g => (
        <div key={g.role}>
          <SectionLabel right={<span style={{ font: `600 10.5px 'Hanken Grotesk'`, color: 'var(--faint)' }}>{g.rows.length}{g.quota ? ` / ${g.quota}` : ''}</span>}>{ROLE_GROUP[g.role]}</SectionLabel>
          <div style={{ display: 'grid', gridTemplateColumns: `repeat(auto-fill, ${CARD_W}px)`, gap: 12, justifyContent: desktop ? 'start' : 'center' }}>
            {g.rows.map(p => <FantasyPlayerCard key={p.player_id} p={p} gw={gwPts?.[p.player_id]} selected={openId === p.player_id} onClick={() => onPlayer(p.player_id)} />)}
          </div>
          {g.rows.some(p => p.player_id === openId) && actions(g.rows.find(p => p.player_id === openId))}
        </div>
      ))}
    </div>
  )
}
