// BetterSocials — Event / Announcement posters. The whitelabel club-event suite
// (Auction Night, 100 Club, Curry Night, Selections, Presentation Night, …).
//
// Same contract as cricket-templates / round-templates so these slot straight
// into the Post Designer (AdminSocialPost) and capture through the shared
// modern-screenshot pipeline (exportImage.js):
//   • every template renders full-bleed at exactly 1080×1080
//   • colour comes from the active `palette` ({ primary, secondary, accent, ink })
//   • display type reads `var(--social-display-font, …)` where it should follow
//     the font picker; stylised directions (Gazette/Ticket/Sticker/…) keep a
//     signature face so the look survives.
//
// WHITELABEL FACTS — the editable post copy lives in one `event` object:
//   { kicker, title, subtitle, date, time, venue, price, cta, sponsor }
//
// BACKGROUNDS — the "curry behind Curry Night / guitar behind Music Night" idea:
//   `motif` = { imageUrl, icon, opacity, label }
//     · imageUrl — a user-uploaded photo, drawn full-bleed behind a dark/accent
//       scrim at `opacity` so text stays legible (the headline feature).
//     · icon — a bundled 3D "thiings" glyph used as a faded watermark when no
//       photo is supplied (auto-picked per preset, override in the editor).
import { AutoFitText, ClubLogo, GrainSVG, Halftone, Stripes } from './cricket-templates'

// Bundled motif glyphs (already in the repo at src/assets/thiings/).
import icoTrophy from '../assets/thiings/trophy.png'
import icoMedal from '../assets/thiings/gold-medal.png'
import icoHandshake from '../assets/thiings/handshake.png'
import icoBat from '../assets/thiings/cricket-bat.png'
import icoStar from '../assets/thiings/star.png'
import icoTarget from '../assets/thiings/target.png'
import icoBolt from '../assets/thiings/lightning-bolt.png'
import icoCalendar from '../assets/thiings/calendar.png'
import icoNecktie from '../assets/thiings/necktie.png'
import icoRibbon from '../assets/thiings/ribbon.png'

// Append an 8-bit alpha to a 6-digit hex (palette colours are always #rrggbb).
const a = (hex, alpha) => {
  if (!hex || hex[0] !== '#' || hex.length < 7) return hex
  return hex + Math.round(Math.max(0, Math.min(1, alpha)) * 255).toString(16).padStart(2, '0')
}

const MONO = "'JetBrains Mono', monospace"
// Sporty directions follow the global font picker; the var falls back to the
// direction's own face when the picker hasn't set one.
const SPORT = "var(--social-display-font, 'Barlow Condensed', sans-serif)"

// Small pink BetterSocials chip-mark used as the export watermark.
function BSMark({ size = 22, color = '#f25aa6' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" style={{ flexShrink: 0 }}>
      <path d="M22 32 L43 19 M22 32 L43 45" fill="none" stroke={color} strokeWidth="5" strokeLinecap="round" />
      <circle cx="20" cy="32" r="8" fill={color} />
      <circle cx="44" cy="18" r="8" fill={color} />
      <circle cx="44" cy="46" r="8" fill={color} />
    </svg>
  )
}

// Full-bleed photo layer + scrim for the directions that take a hero image.
// Falls back to a diagonal accent weave (so the slot reads even with no photo).
function PhotoLayer({ motif, palette, height = '100%', scrimFrom = 0.04, label }) {
  const P = palette
  return (
    <div style={{ position: 'absolute', left: 0, top: 0, right: 0, height, overflow: 'hidden' }}>
      {motif?.imageUrl ? (
        <img src={motif.imageUrl} alt="" crossOrigin="anonymous"
          style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: motif.opacity ?? 0.85 }} />
      ) : (
        <div style={{ position: 'absolute', inset: 0, background: `repeating-linear-gradient(135deg, ${P.primary} 0px, ${P.primary} 17px, ${a(P.accent, 0.1)} 17px, ${a(P.accent, 0.1)} 34px)` }}>
          <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 14, opacity: 0.5 }}>
            <div style={{ width: 60, height: 60, border: `2px solid ${a(P.accent, 0.45)}`, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <div style={{ width: 22, height: 22, border: `2px solid ${a(P.accent, 0.45)}`, borderRadius: '50%' }} />
            </div>
            <div style={{ fontFamily: MONO, fontSize: 15, letterSpacing: 3, textTransform: 'uppercase', color: a(P.accent, 0.55) }}>{label || 'Add a photo'}</div>
          </div>
        </div>
      )}
      <div style={{ position: 'absolute', inset: 0, background: `linear-gradient(180deg, ${a(P.accent, 0.16)} 0%, transparent 38%), linear-gradient(0deg, ${P.primary} ${scrimFrom * 100}%, transparent 64%)` }} />
    </div>
  )
}

// Club lockup (logo or monogram shield + name) used across several directions.
function ClubLockup({ team, palette, color }) {
  const ink = color || palette.ink
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
      {team.logo
        ? <ClubLogo src={team.logo} size={64} />
        : <ClubLogo monogram={team.monogram} color={palette.accent} size={64} shape="shield" />}
      <div style={{ fontFamily: SPORT, fontSize: 26, fontWeight: 600, letterSpacing: 5, textTransform: 'uppercase', color: ink }}>{team.name}</div>
    </div>
  )
}

function Watermark({ sponsor, color = 'rgba(255,255,255,0.42)' }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <BSMark />
        <span style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 2, textTransform: 'uppercase', color }}>Made with BetterSocials</span>
      </div>
      {sponsor ? <div style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 2, textTransform: 'uppercase', color }}>{sponsor}</div> : null}
    </div>
  )
}

const FRAME = { width: 1080, height: 1080, position: 'relative', overflow: 'hidden', fontFamily: "'Inter', sans-serif", boxSizing: 'border-box' }

// ─────────────────────────────────────────────────────────────────────────────
// EV1 — FLOODLIT · full-bleed photo + opacity filter (sporty, BetterStats-native)
// ─────────────────────────────────────────────────────────────────────────────
export function EVT_Floodlit({ team, event = {}, palette, motif }) {
  const P = palette
  return (
    <div style={{ ...FRAME, background: P.primary, color: '#fff' }}>
      <PhotoLayer motif={motif} palette={P} height={680} scrimFrom={0.04} label={motif?.label} />
      <div style={{ position: 'absolute', left: -180, top: -180, width: 520, height: 520, borderRadius: '50%', background: `radial-gradient(circle, ${a(P.accent, 0.3)}, transparent 68%)`, pointerEvents: 'none' }} />

      <div style={{ position: 'absolute', top: 56, left: 64, right: 64, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <ClubLockup team={team} palette={P} color="#fff" />
        <div style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 3, textTransform: 'uppercase', color: P.accent, border: `1.5px solid ${a(P.accent, 0.45)}`, borderRadius: 999, padding: '9px 18px', background: a(P.accent, 0.1) }}>Club Event</div>
      </div>

      <div style={{ position: 'absolute', left: 64, right: 64, bottom: 60, display: 'flex', flexDirection: 'column' }}>
        <div style={{ fontFamily: MONO, fontSize: 18, letterSpacing: 6, textTransform: 'uppercase', color: P.accent, marginBottom: 14 }}>{event.kicker}</div>
        <div style={{ height: 280, display: 'flex', alignItems: 'flex-end' }}>
          <AutoFitText text={(event.title || '').toUpperCase()} max={148} min={56} lines={2} measureDeps={[event.title]}
            style={{ fontFamily: SPORT, fontWeight: 800, lineHeight: 0.86, textTransform: 'uppercase', color: '#fff', letterSpacing: 1 }} />
        </div>
        {event.subtitle ? <div style={{ fontSize: 30, color: 'rgba(255,255,255,0.78)', marginTop: 22, maxWidth: 760, lineHeight: 1.3 }}>{event.subtitle}</div> : null}

        <div style={{ display: 'flex', marginTop: 40, borderTop: '1px solid rgba(255,255,255,0.16)', borderBottom: '1px solid rgba(255,255,255,0.16)' }}>
          {[['Date', event.date], ['Time', event.time], ['Venue', event.venue]].map(([l, v], i) => (
            <div key={l} style={{ flex: i === 2 ? 1.4 : 1, padding: i ? '22px 0 22px 28px' : '22px 0', borderLeft: i ? '1px solid rgba(255,255,255,0.16)' : 'none' }}>
              <div style={{ fontFamily: MONO, fontSize: 14, letterSpacing: 3, textTransform: 'uppercase', color: 'rgba(255,255,255,0.45)' }}>{l}</div>
              <div style={{ fontFamily: SPORT, fontWeight: 700, fontSize: 38, color: '#fff', marginTop: 6 }}>{v}</div>
            </div>
          ))}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 20, marginTop: 30 }}>
          {event.price ? <div style={{ background: P.accent, color: P.primary, fontFamily: SPORT, fontWeight: 800, fontSize: 40, textTransform: 'uppercase', letterSpacing: 1, padding: '12px 26px', borderRadius: 10 }}>{event.price}</div> : null}
          {event.cta ? <div style={{ fontFamily: MONO, fontSize: 17, letterSpacing: 2, textTransform: 'uppercase', color: 'rgba(255,255,255,0.7)' }}>{event.cta}</div> : null}
        </div>

        <div style={{ marginTop: 38 }}><Watermark sponsor={event.sponsor} /></div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// EV2 — COLOUR BLOCK · club colour leads, giant motif (bold, high-energy)
// ─────────────────────────────────────────────────────────────────────────────
export function EVT_Block({ team, event = {}, palette, motif }) {
  const P = palette
  return (
    <div style={{ ...FRAME, background: P.primary, color: '#fff' }}>
      <div style={{ position: 'absolute', left: 0, top: 0, right: 0, height: 606, background: `linear-gradient(150deg, ${P.accent} 0%, ${a(P.accent, 0.78)} 100%)`, overflow: 'hidden' }}>
        {motif?.imageUrl
          ? <img src={motif.imageUrl} alt="" crossOrigin="anonymous" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: 0.3, mixBlendMode: 'overlay' }} />
          : <img src={motif?.icon || icoHandshake} alt="" style={{ position: 'absolute', right: -130, top: 54, width: 560, height: 560, objectFit: 'contain', opacity: 0.26, transform: 'rotate(-8deg)' }} />}
        <div style={{ position: 'absolute', right: -220, top: -40, width: 560, height: 560, borderRadius: '50%', background: 'radial-gradient(circle, rgba(255,255,255,0.18), transparent 66%)' }} />

        <div style={{ position: 'absolute', top: 60, left: 64, right: 64, display: 'flex', alignItems: 'center', gap: 16 }}>
          {team.logo ? <ClubLogo src={team.logo} size={60} /> : <ClubLogo monogram={team.monogram} color="#fff" size={60} shape="shield" />}
          <div style={{ fontFamily: SPORT, fontSize: 26, fontWeight: 600, letterSpacing: 5, textTransform: 'uppercase', color: '#fff' }}>{team.name}</div>
          <div style={{ marginLeft: 'auto', fontFamily: MONO, fontSize: 13, letterSpacing: 3, textTransform: 'uppercase', color: '#fff', border: '1.5px solid rgba(255,255,255,0.55)', borderRadius: 999, padding: '9px 18px' }}>Club Event</div>
        </div>

        <div style={{ position: 'absolute', left: 64, right: 64, bottom: 54 }}>
          <div style={{ fontFamily: MONO, fontSize: 18, letterSpacing: 6, textTransform: 'uppercase', color: 'rgba(255,255,255,0.9)', marginBottom: 16 }}>{event.kicker}</div>
          <div style={{ height: 280, display: 'flex', alignItems: 'flex-end' }}>
            <AutoFitText text={(event.title || '').toUpperCase()} max={158} min={56} lines={2} measureDeps={[event.title]}
              style={{ fontFamily: SPORT, fontWeight: 800, lineHeight: 0.82, textTransform: 'uppercase', color: '#fff', letterSpacing: 1, textShadow: '0 4px 30px rgba(0,0,0,0.18)' }} />
          </div>
        </div>
      </div>

      <div style={{ position: 'absolute', left: 0, top: 606, right: 0, bottom: 0, padding: '46px 64px 56px', boxSizing: 'border-box', display: 'flex', flexDirection: 'column' }}>
        {event.subtitle ? <div style={{ fontSize: 27, color: 'rgba(255,255,255,0.74)', lineHeight: 1.32, maxWidth: 840, marginBottom: 30 }}>{event.subtitle}</div> : null}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1, background: 'rgba(255,255,255,0.12)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 14, overflow: 'hidden' }}>
          {[['Date', event.date], ['Time', event.time], ['Venue', event.venue], ['Entry', event.price]].map(([l, v]) => (
            <div key={l} style={{ background: P.primary, padding: '20px 24px' }}>
              <div style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 3, textTransform: 'uppercase', color: P.accent }}>{l}</div>
              <div style={{ fontFamily: SPORT, fontWeight: 700, fontSize: 40, color: '#fff', marginTop: 4 }}>{v}</div>
            </div>
          ))}
        </div>
        {event.cta ? (
          <div style={{ marginTop: 26, background: P.accent, borderRadius: 14, padding: '20px 28px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontFamily: SPORT, fontWeight: 800, fontSize: 42, textTransform: 'uppercase', letterSpacing: 1, color: P.primary }}>{event.cta}</span>
            <span style={{ fontFamily: MONO, fontSize: 15, color: P.primary, opacity: 0.7 }}>↗</span>
          </div>
        ) : null}
        <div style={{ marginTop: 'auto', paddingTop: 28 }}><Watermark sponsor={event.sponsor} /></div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// EV3 — TICKET · refined, editorial, motif watermark (premium occasions)
// Light "paper" surface: uses palette.ink for paper, primary for type.
// ─────────────────────────────────────────────────────────────────────────────
export function EVT_Ticket({ team, event = {}, palette, motif }) {
  const P = palette
  const paper = P.paper || '#f4efe4'
  const ink = P.deepInk || '#1f1c14'
  const line = a(ink, 0.2)
  const SERIF = "'Cormorant Garamond', serif"
  return (
    <div style={{ ...FRAME, background: paper, color: ink, fontFamily: SERIF }}>
      <img src={motif?.icon || icoTrophy} alt="" style={{ position: 'absolute', left: '50%', top: 300, transform: 'translateX(-50%)', width: 600, height: 600, objectFit: 'contain', opacity: 0.12 }} />
      <div style={{ position: 'absolute', inset: 42, border: `1.5px solid ${line}`, pointerEvents: 'none' }} />
      <div style={{ position: 'absolute', inset: 50, border: `1px solid ${a(ink, 0.12)}`, pointerEvents: 'none' }} />

      {event.price ? (
        <div style={{ position: 'absolute', top: 250, right: 108, width: 148, height: 148, borderRadius: '50%', border: `2px solid ${P.accent}`, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', transform: 'rotate(-9deg)', background: paper }}>
          <div style={{ fontFamily: MONO, fontSize: 12, letterSpacing: 3, textTransform: 'uppercase', color: P.accent }}>Entry</div>
          <div style={{ fontFamily: SERIF, fontWeight: 600, fontSize: 52, lineHeight: 1, color: ink, marginTop: 2 }}>{event.price}</div>
        </div>
      ) : null}

      <div style={{ position: 'absolute', inset: '96px 100px', display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 18, marginTop: 8 }}>
          <div style={{ width: 60, height: 1, background: line }} />
          <div style={{ fontFamily: MONO, fontSize: 15, letterSpacing: 5, textTransform: 'uppercase', color: a(ink, 0.66) }}>{team.fullName || team.name}</div>
          <div style={{ width: 60, height: 1, background: line }} />
        </div>

        <div style={{ marginTop: 'auto' }}>
          <div style={{ fontFamily: MONO, fontSize: 17, letterSpacing: 6, textTransform: 'uppercase', color: P.accent, marginBottom: 18 }}>{event.kicker}</div>
          <AutoFitText text={event.title} max={158} min={64} lines={2} measureDeps={[event.title]}
            style={{ fontFamily: SERIF, fontWeight: 600, lineHeight: 0.92, color: ink, letterSpacing: 1 }} />
          {event.subtitle ? <div style={{ fontFamily: SERIF, fontStyle: 'italic', fontWeight: 500, fontSize: 38, color: a(ink, 0.66), marginTop: 18, maxWidth: 720, lineHeight: 1.3 }}>{event.subtitle}</div> : null}
        </div>

        <div style={{ marginTop: 'auto', width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <div style={{ position: 'relative', width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 34 }}>
            <div style={{ position: 'absolute', left: -58, width: 34, height: 34, borderRadius: '50%', background: a(ink, 0.08), border: `1px solid ${line}` }} />
            <div style={{ flex: 1, borderTop: `2px dashed ${line}` }} />
            <div style={{ position: 'absolute', right: -58, width: 34, height: 34, borderRadius: '50%', background: a(ink, 0.08), border: `1px solid ${line}` }} />
          </div>
          <div style={{ display: 'flex', alignItems: 'stretch' }}>
            {[['Date', event.date], ['Time', event.time], ['Venue', event.venue]].map(([l, v], i) => (
              <div key={l} style={{ padding: '0 36px', textAlign: 'center', borderLeft: i ? `1px solid ${line}` : 'none' }}>
                <div style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 3, textTransform: 'uppercase', color: a(ink, 0.5) }}>{l}</div>
                <div style={{ fontFamily: SERIF, fontWeight: 600, fontSize: 40, color: ink, marginTop: 4 }}>{v}</div>
              </div>
            ))}
          </div>
          {event.cta ? <div style={{ marginTop: 30, fontFamily: MONO, fontSize: 15, letterSpacing: 3, textTransform: 'uppercase', color: P.accent, border: `1.5px solid ${P.accent}`, borderRadius: 999, padding: '11px 26px' }}>{event.cta}</div> : null}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 30 }}>
            <BSMark size={18} color={P.accent} />
            <span style={{ fontFamily: MONO, fontSize: 12, letterSpacing: 2, textTransform: 'uppercase', color: a(ink, 0.5) }}>Made with BetterSocials{event.sponsor ? ` · ${event.sponsor}` : ''}</span>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// EV4 — SCOREBOARD · LED dot-matrix, mono numerals (fixtures & selections)
// ─────────────────────────────────────────────────────────────────────────────
export function EVT_Scoreboard({ team, event = {}, palette, motif }) {
  const P = palette
  return (
    <div style={{ ...FRAME, background: P.primary, color: '#fff' }}>
      <div style={{ position: 'absolute', inset: 0, backgroundImage: `radial-gradient(${a(P.accent, 0.1)} 1.4px, transparent 1.6px)`, backgroundSize: '24px 24px' }} />
      <div style={{ position: 'absolute', left: -160, bottom: -160, width: 560, height: 560, borderRadius: '50%', background: `radial-gradient(circle, ${a(P.accent, 0.16)}, transparent 68%)` }} />
      <img src={motif?.icon || icoBat} alt="" style={{ position: 'absolute', right: 54, top: 64, width: 150, height: 150, objectFit: 'contain', opacity: 0.5 }} />

      <div style={{ position: 'absolute', top: 60, left: 64, right: 64, display: 'flex', alignItems: 'center', gap: 16 }}>
        {team.logo ? <ClubLogo src={team.logo} size={60} /> : <ClubLogo monogram={team.monogram} color={P.accent} size={60} shape="shield" />}
        <div style={{ fontFamily: SPORT, fontSize: 26, fontWeight: 700, letterSpacing: 5, textTransform: 'uppercase', color: '#fff' }}>{team.name}</div>
      </div>

      <div style={{ position: 'absolute', left: 64, right: 64, top: 240 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 18 }}>
          <div style={{ width: 13, height: 13, borderRadius: '50%', background: P.accent, boxShadow: `0 0 16px ${P.accent}` }} />
          <div style={{ fontFamily: MONO, fontSize: 18, letterSpacing: 6, textTransform: 'uppercase', color: P.accent }}>{event.kicker}</div>
        </div>
        <div style={{ height: 270, display: 'flex', alignItems: 'flex-start' }}>
          <AutoFitText text={(event.title || '').toUpperCase()} max={150} min={56} lines={2} measureDeps={[event.title]}
            style={{ fontFamily: SPORT, fontWeight: 800, lineHeight: 0.84, textTransform: 'uppercase', color: '#fff', letterSpacing: 1 }} />
        </div>
        {event.subtitle ? <div style={{ fontFamily: MONO, fontSize: 21, color: 'rgba(255,255,255,0.6)', marginTop: 4, lineHeight: 1.5, maxWidth: 820 }}>{event.subtitle}</div> : null}

        <div style={{ marginTop: 44, border: `1.5px solid ${a(P.accent, 0.3)}`, borderRadius: 18, background: a(P.accent, 0.1), overflow: 'hidden' }}>
          <div style={{ background: a(P.accent, 0.16), padding: '14px 28px', borderBottom: `1px solid ${a(P.accent, 0.3)}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontFamily: MONO, fontSize: 14, letterSpacing: 4, textTransform: 'uppercase', color: P.accent }}>▸ Fixture Card</span>
            <span style={{ fontFamily: MONO, fontSize: 14, letterSpacing: 2, color: 'rgba(255,255,255,0.4)' }}>{event.price}</span>
          </div>
          <div style={{ padding: '6px 28px' }}>
            {[['Date', event.date], ['Time', event.time], ['Venue', event.venue]].map(([l, v], i) => (
              <div key={l} style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', padding: '20px 0', borderBottom: i < 2 ? `1px dashed ${a(P.accent, 0.3)}` : 'none' }}>
                <span style={{ fontFamily: MONO, fontSize: 16, letterSpacing: 4, textTransform: 'uppercase', color: 'rgba(255,255,255,0.5)' }}>{l}</span>
                <span style={{ fontFamily: SPORT, fontWeight: 700, fontSize: 46, color: i === 2 ? P.accent : '#fff' }}>{v}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div style={{ position: 'absolute', left: 64, right: 64, bottom: 54, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ fontFamily: MONO, fontSize: 16, letterSpacing: 2, textTransform: 'uppercase', color: P.accent }}>{event.cta}</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
          {event.sponsor ? <span style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 2, textTransform: 'uppercase', color: 'rgba(255,255,255,0.4)' }}>{event.sponsor}</span> : null}
          <BSMark size={20} />
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// EV5 — GAZETTE · newspaper masthead + serif headline (stately notices)
// ─────────────────────────────────────────────────────────────────────────────
export function EVT_Gazette({ team, event = {}, palette, motif }) {
  const P = palette
  const paper = P.paper || '#f4f0e6'
  const ink = P.deepInk || '#1a1814'
  const line = a(ink, 0.28)
  const faint = a(ink, 0.55)
  const SERIF = "'Playfair Display', serif"
  const BODY = "'Spectral', serif"
  return (
    <div style={{ ...FRAME, background: paper, color: ink, fontFamily: BODY }}>
      <div style={{ position: 'absolute', inset: 56, display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontFamily: MONO, fontSize: 13, letterSpacing: 2, textTransform: 'uppercase', color: faint, paddingBottom: 10 }}>
          <span>Vol. XCIV — No. 12</span><span>Est. 1921</span>
        </div>
        <div style={{ borderTop: `3px solid ${ink}`, borderBottom: `1px solid ${ink}`, padding: '18px 0 14px', textAlign: 'center' }}>
          <div style={{ fontFamily: SERIF, fontWeight: 900, fontSize: 78, lineHeight: 0.95, color: ink, letterSpacing: 0.5 }}>{team.fullName || team.name}</div>
        </div>
        <div style={{ borderBottom: `3px solid ${ink}`, padding: '9px 0', textAlign: 'center', fontFamily: MONO, fontSize: 14, letterSpacing: 5, textTransform: 'uppercase', color: ink }}>{event.kicker}</div>

        <div style={{ textAlign: 'center', padding: '46px 0 10px' }}>
          <div style={{ fontFamily: MONO, fontSize: 15, letterSpacing: 5, textTransform: 'uppercase', color: P.accent, marginBottom: 18 }}>— Official Notice —</div>
          <AutoFitText text={event.title} max={128} min={52} lines={2} measureDeps={[event.title]}
            style={{ fontFamily: SERIF, fontWeight: 900, lineHeight: 0.9, color: ink }} />
          {event.subtitle ? <div style={{ fontFamily: BODY, fontStyle: 'italic', fontSize: 34, color: a(ink, 0.72), marginTop: 20, maxWidth: 840, marginLeft: 'auto', marginRight: 'auto', lineHeight: 1.34 }}>{event.subtitle}</div> : null}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1.35fr 1fr', gap: 40, marginTop: 34, flex: 1, borderTop: `1px solid ${line}`, paddingTop: 34 }}>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <div style={{ flex: 1, border: `1px solid ${ink}`, backgroundColor: '#d8d3c6', backgroundImage: motif?.imageUrl ? undefined : `radial-gradient(${a(ink, 0.42)} 1.3px, transparent 1.6px)`, backgroundSize: '7px 7px', overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              {motif?.imageUrl
                ? <img src={motif.imageUrl} alt="" crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover', filter: 'grayscale(1) contrast(1.1)' }} />
                : <span style={{ fontFamily: MONO, fontSize: 14, letterSpacing: 3, textTransform: 'uppercase', color: a(ink, 0.55), background: paper, padding: '6px 14px' }}>{motif?.label || 'Add a photo'}</span>}
            </div>
            <div style={{ fontFamily: BODY, fontStyle: 'italic', fontSize: 18, color: faint, marginTop: 10 }}>Pictured: members at last year's event.</div>
          </div>

          <div style={{ border: `2px solid ${ink}`, padding: '24px 26px', display: 'flex', flexDirection: 'column' }}>
            <div style={{ fontFamily: SERIF, fontWeight: 700, fontSize: 30, color: ink, borderBottom: `2px solid ${ink}`, paddingBottom: 12, marginBottom: 6 }}>At a Glance</div>
            {[['Date', event.date], ['Time', event.time], ['Venue', event.venue]].map(([l, v]) => (
              <div key={l} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', padding: '15px 0', borderBottom: `1px solid ${line}` }}>
                <span style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 2, textTransform: 'uppercase', color: faint }}>{l}</span>
                <span style={{ fontFamily: SERIF, fontWeight: 700, fontSize: 30, color: ink }}>{v}</span>
              </div>
            ))}
            <div style={{ marginTop: 'auto', background: ink, padding: '14px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 2, textTransform: 'uppercase', color: 'rgba(255,255,255,0.6)' }}>Admission</span>
              <span style={{ fontFamily: SERIF, fontWeight: 900, fontSize: 32, color: '#fff' }}>{event.price}</span>
            </div>
          </div>
        </div>

        <div style={{ borderTop: `3px solid ${ink}`, marginTop: 28, paddingTop: 14, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontFamily: BODY, fontStyle: 'italic', fontSize: 22, color: ink }}>{event.cta}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            {event.sponsor ? <span style={{ fontFamily: MONO, fontSize: 12, letterSpacing: 2, textTransform: 'uppercase', color: faint }}>{event.sponsor}</span> : null}
            <span style={{ color: line }}>|</span>
            <span style={{ fontFamily: MONO, fontSize: 12, letterSpacing: 2, textTransform: 'uppercase', color: faint }}>Made with BetterSocials</span>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// EV6 — STICKER POP · playful rounded badges (casual socials)
// ─────────────────────────────────────────────────────────────────────────────
export function EVT_Sticker({ team, event = {}, palette, motif }) {
  const P = palette
  const paper = P.paper || '#fbf6ec'
  const ink = P.deepInk || '#23202c'
  const FUN = "'Fredoka', sans-serif"
  return (
    <div style={{ ...FRAME, background: paper, color: ink }}>
      <div style={{ position: 'absolute', right: -130, top: -130, width: 480, height: 480, borderRadius: '50%', background: a(P.accent, 0.18) }} />
      <div style={{ position: 'absolute', left: -90, bottom: 110, width: 300, height: 300, borderRadius: '50%', border: `4px dashed ${a(P.accent, 0.4)}` }} />

      <div style={{ position: 'absolute', top: 130, right: 96, width: 280, height: 280, background: '#fff', borderRadius: 36, boxShadow: '0 18px 44px rgba(0,0,0,0.16)', transform: 'rotate(7deg)', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
        {motif?.imageUrl
          ? <img src={motif.imageUrl} alt="" crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          : <img src={motif?.icon || icoTarget} alt="" style={{ width: 200, height: 200, objectFit: 'contain' }} />}
      </div>

      <div style={{ position: 'absolute', inset: 72, display: 'flex', flexDirection: 'column' }}>
        <div style={{ alignSelf: 'flex-start', background: P.accent, color: '#fff', fontFamily: FUN, fontWeight: 600, fontSize: 24, letterSpacing: 1, padding: '12px 26px', borderRadius: 999, transform: 'rotate(-3deg)', boxShadow: `0 8px 22px ${a(P.accent, 0.4)}` }}>{team.name}</div>

        <div style={{ marginTop: 'auto' }}>
          <div style={{ display: 'inline-block', background: a(P.accent, 0.18), color: P.accent, fontFamily: FUN, fontWeight: 600, fontSize: 22, padding: '8px 18px', borderRadius: 999, marginBottom: 18 }}>{event.kicker}</div>
          <div style={{ height: 280, display: 'flex', alignItems: 'flex-end' }}>
            <AutoFitText text={event.title} max={158} min={60} lines={2} measureDeps={[event.title]}
              style={{ fontFamily: FUN, fontWeight: 700, lineHeight: 0.9, color: ink, letterSpacing: -1 }} />
          </div>
          {event.subtitle ? <div style={{ fontWeight: 500, fontSize: 29, color: a(ink, 0.7), marginTop: 20, maxWidth: 760, lineHeight: 1.36 }}>{event.subtitle}</div> : null}
        </div>

        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: 40 }}>
          {[['Date', event.date], ['Time', event.time], ['Venue', event.venue]].map(([l, v]) => (
            <div key={l} style={{ background: '#fff', border: `2.5px solid ${ink}`, borderRadius: 18, padding: '14px 22px', boxShadow: `5px 5px 0 ${ink}` }}>
              <div style={{ fontWeight: 600, fontSize: 13, letterSpacing: 2, textTransform: 'uppercase', color: P.accent }}>{l}</div>
              <div style={{ fontFamily: FUN, fontWeight: 600, fontSize: 34, color: ink, lineHeight: 1.1 }}>{v}</div>
            </div>
          ))}
        </div>

        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: 44 }}>
          {event.cta ? <div style={{ background: ink, color: '#fff', fontFamily: FUN, fontWeight: 600, fontSize: 34, padding: '18px 38px', borderRadius: 999, boxShadow: '0 10px 26px rgba(0,0,0,0.2)' }}>{event.cta}</div> : <span />}
          {event.price ? (
            <div style={{ width: 150, height: 150, borderRadius: '50%', background: P.accent, color: '#fff', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', transform: 'rotate(-9deg)', boxShadow: `0 12px 30px ${a(P.accent, 0.4)}` }}>
              <span style={{ fontWeight: 600, fontSize: 13, letterSpacing: 2, textTransform: 'uppercase', opacity: 0.85 }}>Entry</span>
              <span style={{ fontFamily: FUN, fontWeight: 700, fontSize: 42, lineHeight: 1 }}>{event.price}</span>
            </div>
          ) : null}
        </div>
      </div>

      <div style={{ position: 'absolute', bottom: 30, left: 72, display: 'flex', alignItems: 'center', gap: 9 }}>
        <BSMark size={18} />
        <span style={{ fontWeight: 500, fontSize: 13, letterSpacing: 1, color: a(ink, 0.5) }}>Made with BetterSocials{event.sponsor ? ` · ${event.sponsor}` : ''}</span>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// EV7 — KINETIC · diagonal bands, italic motion type (high-energy sport)
// ─────────────────────────────────────────────────────────────────────────────
export function EVT_Kinetic({ team, event = {}, palette, motif }) {
  const P = palette
  const skew = { transform: 'skewX(-8deg)' }
  const unskew = { display: 'inline-block', transform: 'skewX(8deg)' }
  return (
    <div style={{ ...FRAME, background: P.primary, color: '#fff' }}>
      <div style={{ position: 'absolute', left: 0, top: 0, right: 0, height: 616, clipPath: 'polygon(0 0, 100% 0, 100% 100%, 0 76%)', overflow: 'hidden' }}>
        {motif?.imageUrl
          ? <img src={motif.imageUrl} alt="" crossOrigin="anonymous" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
          : <div style={{ position: 'absolute', inset: 0, background: `repeating-linear-gradient(120deg, ${a(P.accent, 0.06)} 0px, ${a(P.accent, 0.06)} 18px, ${a(P.accent, 0.12)} 18px, ${a(P.accent, 0.12)} 36px)`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <span style={{ fontFamily: MONO, fontSize: 16, letterSpacing: 4, textTransform: 'uppercase', color: a(P.accent, 0.45) }}>{motif?.label || 'Add a photo'}</span>
            </div>}
        <div style={{ position: 'absolute', inset: 0, background: `linear-gradient(180deg, rgba(0,0,0,0.1) 0%, transparent 35%), linear-gradient(0deg, ${P.primary} 2%, transparent 50%)` }} />
      </div>
      <div style={{ position: 'absolute', left: -60, top: 512, width: 1200, height: 18, background: P.accent, transform: 'rotate(8deg)' }} />
      <div style={{ position: 'absolute', left: -60, top: 548, width: 1200, height: 7, background: a(P.accent, 0.45), transform: 'rotate(8deg)' }} />

      <div style={{ position: 'absolute', top: 56, left: 64, right: 64, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {team.logo ? <ClubLogo src={team.logo} size={60} /> : <ClubLogo monogram={team.monogram} color="#fff" size={60} shape="shield" />}
          <div style={{ fontFamily: SPORT, fontStyle: 'italic', fontSize: 26, fontWeight: 700, letterSpacing: 4, textTransform: 'uppercase', color: '#fff' }}>{team.name}</div>
        </div>
        <div style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 3, textTransform: 'uppercase', color: P.accent, border: `1.5px solid ${a(P.accent, 0.45)}`, borderRadius: 4, padding: '9px 16px', ...skew }}><span style={unskew}>Club Event</span></div>
      </div>

      <div style={{ position: 'absolute', left: 56, right: 64, top: 632, ...skew }}>
        <div style={{ fontFamily: MONO, fontSize: 18, letterSpacing: 6, textTransform: 'uppercase', color: P.accent, marginBottom: 12, ...unskew }}>{event.kicker}</div>
        <div style={{ height: 230 }}>
          <AutoFitText text={(event.title || '').toUpperCase()} max={138} min={52} lines={2} measureDeps={[event.title]}
            style={{ fontFamily: SPORT, fontStyle: 'italic', fontWeight: 800, lineHeight: 0.84, textTransform: 'uppercase', color: '#fff' }} />
        </div>
        {event.subtitle ? <div style={{ fontFamily: "'Inter', sans-serif", fontSize: 27, color: 'rgba(255,255,255,0.74)', marginTop: 18, maxWidth: 760, lineHeight: 1.3, ...unskew }}>{event.subtitle}</div> : null}
      </div>

      <div style={{ position: 'absolute', left: 64, right: 64, bottom: 54 }}>
        <div style={{ display: 'flex', alignItems: 'stretch', borderLeft: `4px solid ${P.accent}`, paddingLeft: 22 }}>
          {[['Date', event.date, 1], ['Time', event.time, 1], ['Venue', event.venue, 1.3]].map(([l, v, fl]) => (
            <div key={l} style={{ flex: fl }}>
              <div style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 3, textTransform: 'uppercase', color: 'rgba(255,255,255,0.45)' }}>{l}</div>
              <div style={{ fontFamily: SPORT, fontStyle: 'italic', fontWeight: 800, fontSize: 42, color: '#fff' }}>{v}</div>
            </div>
          ))}
          {event.price ? (
            <div style={{ display: 'flex', alignItems: 'center' }}>
              <div style={{ background: P.accent, color: P.primary, fontFamily: SPORT, fontStyle: 'italic', fontWeight: 800, fontSize: 40, textTransform: 'uppercase', padding: '10px 24px', ...skew }}><span style={unskew}>{event.price}</span></div>
            </div>
          ) : null}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 30, paddingTop: 22, borderTop: '1px solid rgba(255,255,255,0.14)' }}>
          <span style={{ fontFamily: MONO, fontSize: 16, letterSpacing: 2, textTransform: 'uppercase', color: P.accent }}>{event.cta}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            {event.sponsor ? <span style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 2, textTransform: 'uppercase', color: 'rgba(255,255,255,0.42)' }}>{event.sponsor}</span> : null}
            <BSMark size={20} />
          </div>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// EV8 — SWISS · ultra-minimal Helvetica, baseline grid (clean & unmistakable)
// ─────────────────────────────────────────────────────────────────────────────
export function EVT_Swiss({ team, event = {}, palette }) {
  const P = palette
  const paper = P.paper || '#f6f5f2'
  const ink = P.deepInk || '#15171a'
  const faint = a(ink, 0.5)
  const line = a(ink, 0.2)
  const HELV = "'Helvetica Neue', Helvetica, Arial, sans-serif"
  return (
    <div style={{ ...FRAME, background: paper, color: ink, fontFamily: HELV }}>
      <div style={{ position: 'absolute', inset: 80, display: 'flex', flexDirection: 'column' }}>
        <div style={{ borderTop: `2px solid ${ink}`, paddingTop: 16, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <div style={{ fontSize: 22, fontWeight: 700, letterSpacing: -0.3, color: ink }}>{team.fullName || team.name}</div>
          <div style={{ textAlign: 'right', fontSize: 15, fontWeight: 500, letterSpacing: 2, textTransform: 'uppercase', color: faint }}>Club Notice<br />№ 01 / 25–26</div>
        </div>

        <div style={{ marginTop: 'auto' }}>
          <div style={{ fontSize: 16, fontWeight: 700, letterSpacing: 3, textTransform: 'uppercase', color: P.accent, marginBottom: 26 }}>{event.kicker}</div>
          <div style={{ display: 'flex', alignItems: 'stretch', gap: 28 }}>
            <div style={{ width: 10, background: P.accent, flexShrink: 0, margin: '8px 0' }} />
            <div style={{ height: 320, flex: 1 }}>
              <AutoFitText text={event.title} max={152} min={56} lines={2} measureDeps={[event.title]}
                style={{ fontWeight: 800, lineHeight: 0.9, letterSpacing: -3, color: ink }} />
            </div>
          </div>
          {event.subtitle ? <div style={{ fontSize: 30, fontWeight: 400, color: a(ink, 0.62), marginTop: 30, marginLeft: 38, maxWidth: 760, lineHeight: 1.3 }}>{event.subtitle}</div> : null}
        </div>

        <div style={{ marginTop: 'auto', borderTop: `2px solid ${ink}`, paddingTop: 26, display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)' }}>
          {[['Date', event.date], ['Time', event.time], ['Venue', event.venue], ['Entry', event.price]].map(([l, v], i) => (
            <div key={l} style={{ padding: i ? '0 24px' : '0 24px 0 0', borderLeft: i ? `1px solid ${line}` : 'none' }}>
              <div style={{ fontSize: 13, fontWeight: 600, letterSpacing: 2, textTransform: 'uppercase', color: i === 3 ? P.accent : faint, marginBottom: 10 }}>{l}</div>
              <div style={{ fontSize: 34, fontWeight: 700, letterSpacing: -0.5, color: ink }}>{v}</div>
            </div>
          ))}
        </div>

        <div style={{ marginTop: 28, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 16, fontWeight: 500, color: ink }}>{event.cta}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <BSMark size={17} color={P.accent} />
            <span style={{ fontSize: 13, fontWeight: 500, letterSpacing: 1, color: faint }}>Made with BetterSocials{event.sponsor ? ` · ${event.sponsor}` : ''}</span>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// EV9 — CREST · heritage emblem, gold-on-green serif (prestige occasions)
// Uses palette.primary as the deep field, palette.accent as the gold.
// ─────────────────────────────────────────────────────────────────────────────
export function EVT_Crest({ team, event = {}, palette, motif }) {
  const P = palette
  const cream = P.cream || '#f3ead2'
  const SERIF = "'Cormorant Garamond', serif"
  const line = a(P.accent, 0.55)
  return (
    <div style={{ ...FRAME, background: P.primary, color: cream, fontFamily: SERIF }}>
      <div style={{ position: 'absolute', left: 0, right: 0, top: 0, height: 560, background: `radial-gradient(ellipse 600px 420px at 50% 0%, ${a(P.accent, 0.18)}, transparent 70%)` }} />
      <div style={{ position: 'absolute', inset: 44, border: `2px solid ${line}`, pointerEvents: 'none' }} />
      <div style={{ position: 'absolute', inset: 52, border: `1px solid ${a(P.accent, 0.3)}`, pointerEvents: 'none' }} />

      <div style={{ position: 'absolute', inset: '84px 96px', display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
        <div style={{ width: 212, height: 212, borderRadius: '50%', border: `2px solid ${P.accent}`, display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
          <div style={{ position: 'absolute', inset: 11, borderRadius: '50%', border: `1px dashed ${a(P.accent, 0.3)}` }} />
          {team.logo ? <ClubLogo src={team.logo} size={120} /> : <img src={motif?.icon || icoTrophy} alt="" style={{ width: 120, height: 120, objectFit: 'contain' }} />}
        </div>

        <div style={{ marginTop: 26, background: P.accent, color: P.primary, fontFamily: MONO, fontSize: 18, fontWeight: 700, letterSpacing: 4, textTransform: 'uppercase', padding: '11px 46px', clipPath: 'polygon(0 0, 100% 0, calc(100% - 20px) 50%, 100% 100%, 0 100%, 20px 50%)' }}>{team.name}</div>

        <div style={{ marginTop: 'auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 16, marginBottom: 20 }}>
            <div style={{ width: 80, height: 1, background: P.accent }} />
            <div style={{ width: 9, height: 9, background: P.accent, transform: 'rotate(45deg)' }} />
            <div style={{ width: 80, height: 1, background: P.accent }} />
          </div>
          <div style={{ fontFamily: MONO, fontSize: 17, letterSpacing: 6, textTransform: 'uppercase', color: P.accent, marginBottom: 14 }}>{event.kicker}</div>
          <AutoFitText text={event.title} max={130} min={52} lines={2} measureDeps={[event.title]}
            style={{ fontFamily: SERIF, fontWeight: 700, lineHeight: 0.92, color: cream, letterSpacing: 1 }} />
          {event.subtitle ? <div style={{ fontFamily: SERIF, fontStyle: 'italic', fontWeight: 500, fontSize: 36, color: a(cream, 0.72), marginTop: 16, maxWidth: 720, marginLeft: 'auto', marginRight: 'auto', lineHeight: 1.32 }}>{event.subtitle}</div> : null}
        </div>

        <div style={{ marginTop: 'auto', width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 16, marginBottom: 30 }}>
            <div style={{ width: 60, height: 1, background: line }} />
            <div style={{ width: 7, height: 7, background: P.accent, transform: 'rotate(45deg)' }} />
            <div style={{ width: 60, height: 1, background: line }} />
          </div>
          <div style={{ display: 'flex', alignItems: 'stretch' }}>
            {[['Date', event.date], ['Time', event.time], ['Venue', event.venue]].map(([l, v], i) => (
              <div key={l} style={{ padding: '0 40px', textAlign: 'center', borderLeft: i ? `1px solid ${line}` : 'none' }}>
                <div style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 3, textTransform: 'uppercase', color: P.accent }}>{l}</div>
                <div style={{ fontFamily: SERIF, fontWeight: 600, fontSize: 40, color: cream, marginTop: 4 }}>{v}</div>
              </div>
            ))}
          </div>
          {(event.cta || event.price) ? <div style={{ marginTop: 28, fontFamily: MONO, fontSize: 15, letterSpacing: 3, textTransform: 'uppercase', color: cream, border: `1px solid ${P.accent}`, borderRadius: 2, padding: '11px 28px' }}>{[event.cta, event.price].filter(Boolean).join(' · ')}</div> : null}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 26 }}>
            <BSMark size={17} />
            <span style={{ fontFamily: MONO, fontSize: 12, letterSpacing: 2, textTransform: 'uppercase', color: a(cream, 0.72) }}>Made with BetterSocials{event.sponsor ? ` · ${event.sponsor}` : ''}</span>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// EV10 — CHALKBOARD · clubhouse blackboard, chalk handwriting (casual notices)
// ─────────────────────────────────────────────────────────────────────────────
export function EVT_Chalkboard({ team, event = {}, palette }) {
  const P = palette
  const board = P.primary || '#20251f'
  const chalk = '#f1efe4'
  const chalk2 = 'rgba(241,239,228,0.74)'
  const faint = 'rgba(241,239,228,0.4)'
  const HAND = "'Caveat', cursive"
  return (
    <div style={{ ...FRAME, background: board, color: chalk }}>
      <div style={{ position: 'absolute', left: '8%', top: '14%', width: 420, height: 300, background: 'radial-gradient(ellipse, rgba(255,255,255,0.05), transparent 70%)', transform: 'rotate(-18deg)' }} />
      <div style={{ position: 'absolute', right: '6%', bottom: '18%', width: 380, height: 260, background: 'radial-gradient(ellipse, rgba(255,255,255,0.045), transparent 70%)', transform: 'rotate(12deg)' }} />
      <div style={{ position: 'absolute', inset: 44, border: `2px dashed ${faint}`, borderRadius: 8, pointerEvents: 'none' }} />

      <div style={{ position: 'absolute', inset: '88px 92px', display: 'flex', flexDirection: 'column' }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: 18, letterSpacing: 5, textTransform: 'uppercase', color: chalk2 }}>✶ {team.name} · Notice Board</div>
          <div style={{ width: 300, height: 3, background: chalk, borderRadius: 3, transform: 'rotate(-1deg)', marginTop: 10, opacity: 0.85 }} />
        </div>

        <div style={{ marginTop: 'auto' }}>
          <div style={{ fontFamily: HAND, fontWeight: 600, fontSize: 48, color: P.accent, lineHeight: 1, marginBottom: 6, transform: 'rotate(-1deg)' }}>{event.kicker}</div>
          <div style={{ height: 280, transform: 'rotate(-1.5deg)' }}>
            <AutoFitText text={event.title} max={172} min={64} lines={2} measureDeps={[event.title]}
              style={{ fontFamily: HAND, fontWeight: 700, lineHeight: 0.82, color: chalk }} />
          </div>
          {event.subtitle ? <div style={{ fontFamily: HAND, fontWeight: 500, fontSize: 46, color: chalk2, marginTop: 18, maxWidth: 780, lineHeight: 1.15 }}>{event.subtitle}</div> : null}
        </div>

        <div style={{ marginTop: 'auto' }}>
          <div style={{ border: `2px dashed ${faint}`, borderRadius: 10, padding: '22px 30px' }}>
            {[['When', `${event.date || ''}${event.date && event.time ? ' · ' : ''}${event.time || ''}`], ['Where', event.venue], ['Cost', event.price]].map(([l, v]) => (
              <div key={l} style={{ display: 'flex', alignItems: 'center', gap: 18, padding: '11px 0' }}>
                <span style={{ fontWeight: 600, fontSize: 14, letterSpacing: 3, textTransform: 'uppercase', color: P.accent, width: 90 }}>{l}</span>
                <span style={{ fontFamily: HAND, fontWeight: 600, fontSize: 44, color: chalk, lineHeight: 1.08, whiteSpace: 'nowrap' }}>{v}</span>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 26 }}>
            {event.cta ? <div style={{ fontFamily: HAND, fontWeight: 700, fontSize: 46, color: P.accent, border: `3px solid ${P.accent}`, borderRadius: '60% 58% 62% 56%', padding: '8px 34px', transform: 'rotate(-2deg)', lineHeight: 1 }}>{event.cta}</div> : <span />}
            <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
              <BSMark size={18} />
              <span style={{ fontWeight: 500, fontSize: 13, letterSpacing: 1, color: chalk2 }}>BetterSocials{event.sponsor ? ` · ${event.sponsor}` : ''}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// EV11 — POLAROID · taped scrapbook photo + marker pen (photo-led socials)
// ─────────────────────────────────────────────────────────────────────────────
export function EVT_Polaroid({ team, event = {}, palette, motif }) {
  const P = palette
  const paper = P.paper || '#ece3d0'
  const ink = P.deepInk || '#2e2a22'
  const MARKER = "'Permanent Marker', cursive"
  const HAND = "'Caveat', cursive"
  return (
    <div style={{ ...FRAME, background: paper, color: ink }}>
      <div style={{ position: 'absolute', inset: 0, backgroundImage: 'radial-gradient(rgba(120,100,70,0.06) 1px, transparent 1.4px)', backgroundSize: '5px 5px', opacity: 0.6 }} />
      <div style={{ position: 'absolute', inset: 76, display: 'flex', flexDirection: 'column' }}>
        <div>
          <div style={{ fontFamily: HAND, fontWeight: 600, fontSize: 46, color: P.accent, lineHeight: 1, transform: 'rotate(-1deg)' }}>{event.kicker}</div>
          <div style={{ height: 150, marginTop: 4 }}>
            <AutoFitText text={event.title} max={118} min={44} lines={1} measureDeps={[event.title]}
              style={{ fontFamily: MARKER, lineHeight: 0.9, color: ink }} />
          </div>
        </div>

        <div style={{ display: 'flex', gap: 54, alignItems: 'center', marginTop: 'auto', marginBottom: 'auto' }}>
          <div style={{ position: 'relative', flexShrink: 0, transform: 'rotate(-3.5deg)' }}>
            <div style={{ position: 'absolute', top: -20, left: 54, width: 150, height: 42, background: a(P.accent, 0.42), transform: 'rotate(-7deg)', boxShadow: '0 2px 6px rgba(0,0,0,0.08)', zIndex: 2 }} />
            <div style={{ background: '#fff', padding: '18px 18px 26px', boxShadow: '0 22px 50px rgba(60,45,25,0.26)' }}>
              <div style={{ width: 404, height: 404, overflow: 'hidden', background: motif?.imageUrl ? undefined : 'repeating-linear-gradient(135deg, #e8ddc7 0px, #e8ddc7 16px, #ddd0b4 16px, #ddd0b4 32px)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                {motif?.imageUrl
                  ? <img src={motif.imageUrl} alt="" crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  : <span style={{ fontFamily: MONO, fontSize: 14, letterSpacing: 3, textTransform: 'uppercase', color: 'rgba(80,64,40,0.6)', background: '#fff', padding: '6px 14px' }}>{motif?.label || 'Add a photo'}</span>}
              </div>
              <div style={{ fontFamily: HAND, fontWeight: 600, fontSize: 48, color: '#2e2a22', textAlign: 'center', marginTop: 12, lineHeight: 1 }}>{event.date}</div>
            </div>
          </div>

          <div style={{ flex: 1 }}>
            <div style={{ display: 'inline-block', fontWeight: 600, fontSize: 14, letterSpacing: 3, textTransform: 'uppercase', color: P.accent, border: `2px solid ${P.accent}`, padding: '8px 16px', transform: 'rotate(-6deg)', opacity: 0.92 }}>★ Save the Date</div>
            {[['When', `${event.date || ''}${event.date && event.time ? ' · ' : ''}${event.time || ''}`], ['Where', event.venue], ['Cost', event.price]].map(([l, v], i) => (
              <div key={l} style={{ marginTop: i ? 22 : 34 }}>
                <div style={{ fontWeight: 600, fontSize: 13, letterSpacing: 3, textTransform: 'uppercase', color: P.accent, marginBottom: 2 }}>{l}</div>
                <div style={{ fontFamily: HAND, fontWeight: 600, fontSize: 52, color: ink, lineHeight: 1 }}>{v}</div>
              </div>
            ))}
            {event.cta ? <div style={{ marginTop: 30, display: 'inline-block', background: ink, color: paper, fontFamily: MARKER, fontSize: 30, padding: '12px 28px', transform: 'rotate(-1.5deg)' }}>{event.cta}</div> : null}
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
          <BSMark size={18} color="#be185d" />
          <span style={{ fontWeight: 500, fontSize: 13, letterSpacing: 1, color: a(ink, 0.5) }}>{team.name} · Made with BetterSocials{event.sponsor ? ` · ${event.sponsor}` : ''}</span>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// REGISTRY — drop these straight into AdminSocialPost's TEMPLATES array.
// `kind: 'event'` keeps them on their own "Events" tab.
// `surface: 'light'` flags the paper-backed directions so the designer can hide
// the dark-mode toggle for them.
// ─────────────────────────────────────────────────────────────────────────────
export const EVENT_TEMPLATES = [
  { id: 'EV1',  name: 'Floodlit',    component: EVT_Floodlit,   desc: 'Full-bleed photo + opacity filter', surface: 'dark',  photo: true },
  { id: 'EV2',  name: 'Colour Block', component: EVT_Block,      desc: 'Club colour leads, giant motif',    surface: 'dark',  photo: true },
  { id: 'EV3',  name: 'Ticket',      component: EVT_Ticket,     desc: 'Refined, editorial, motif mark',    surface: 'light', photo: false },
  { id: 'EV4',  name: 'Scoreboard',  component: EVT_Scoreboard, desc: 'LED dot-matrix, mono numerals',     surface: 'dark',  photo: false },
  { id: 'EV5',  name: 'Gazette',     component: EVT_Gazette,    desc: 'Newspaper masthead, serif',         surface: 'light', photo: true },
  { id: 'EV6',  name: 'Sticker Pop', component: EVT_Sticker,    desc: 'Playful rounded badges',            surface: 'light', photo: true },
  { id: 'EV7',  name: 'Kinetic',     component: EVT_Kinetic,    desc: 'Diagonal bands, italic motion',     surface: 'dark',  photo: true },
  { id: 'EV8',  name: 'Swiss',       component: EVT_Swiss,      desc: 'Ultra-minimal Helvetica grid',      surface: 'light', photo: false },
  { id: 'EV9',  name: 'Crest',       component: EVT_Crest,      desc: 'Heritage emblem, gold-on-green',    surface: 'dark',  photo: false },
  { id: 'EV10', name: 'Chalkboard',  component: EVT_Chalkboard, desc: 'Clubhouse blackboard handwriting',  surface: 'dark',  photo: false },
  { id: 'EV11', name: 'Polaroid',    component: EVT_Polaroid,   desc: 'Taped scrapbook photo + marker',    surface: 'light', photo: true },
]

// ─────────────────────────────────────────────────────────────────────────────
// MOTIFS — bundled 3D glyphs for the faded watermark (no photo case). Curry /
// Music / Quiz etc. have no literal glyph, so they map to the nearest mark and
// lean on an uploaded background photo for the themed look.
// ─────────────────────────────────────────────────────────────────────────────
export const EVENT_MOTIFS = [
  { key: 'trophy',    label: 'Trophy',     icon: icoTrophy },
  { key: 'medal',     label: 'Medal',      icon: icoMedal },
  { key: 'handshake', label: 'Handshake',  icon: icoHandshake },
  { key: 'bat',       label: 'Cricket bat', icon: icoBat },
  { key: 'star',      label: 'Star',       icon: icoStar },
  { key: 'target',    label: 'Target',     icon: icoTarget },
  { key: 'bolt',      label: 'Lightning',  icon: icoBolt },
  { key: 'calendar',  label: 'Calendar',   icon: icoCalendar },
  { key: 'necktie',   label: 'Black tie',  icon: icoNecktie },
  { key: 'ribbon',    label: 'Ribbon',     icon: icoRibbon },
]
const motifIcon = (key) => (EVENT_MOTIFS.find((m) => m.key === key) || EVENT_MOTIFS[0]).icon

// ─────────────────────────────────────────────────────────────────────────────
// PRESETS — one-click event facts. Selecting a preset fills the `event` object
// and picks a sensible default template + motif; everything stays editable.
// ─────────────────────────────────────────────────────────────────────────────
export const EVENT_PRESETS = [
  {
    key: 'auction', label: 'Auction Night', template: 'EV2', motif: 'handshake', photoLabel: 'Auction / lots photo',
    event: { kicker: 'Annual Fundraiser', title: 'Auction Night', subtitle: 'Bid on signed gear, mystery lots & big-ticket experiences. Every dollar backs the club.', date: 'Sat 9 Aug', time: '6:30 PM', venue: 'Function Room', price: '$40', cta: 'Book your table', sponsor: '' },
  },
  {
    key: '100club', label: 'The 100 Club', template: 'EV2', motif: 'medal', photoLabel: '',
    event: { kicker: "Members' Cash Draw", title: 'The 100 Club', subtitle: 'Ten dollars a number. One drawn each month. Half the pot is yours.', date: 'Drawn 1st Fri', time: 'Monthly', venue: 'The Clubhouse', price: '$10', cta: 'Grab your number', sponsor: 'Junior program fund' },
  },
  {
    key: 'curry', label: 'Curry Night', template: 'EV1', motif: 'star', photoLabel: 'Curry / food photo',
    event: { kicker: 'Club Social', title: 'Curry Night', subtitle: 'A night of spice, cold beers & cricket chat. All members & families welcome.', date: 'Fri 18 Jul', time: '7:00 PM', venue: 'The Clubhouse', price: '$25 / head', cta: 'RSVP by Wed 16 Jul', sponsor: '' },
  },
  {
    key: 'selections', label: 'Selections', template: 'EV4', motif: 'bat', photoLabel: 'Squad / team photo',
    event: { kicker: 'Round 1 · 25/26', title: 'Selections', subtitle: 'First-grade XI named for the season opener. Full team list below.', date: 'Sat 4 Oct', time: '10:30 AM', venue: 'Ashcombe Oval', price: '1ST XI', cta: 'Congrats to all named', sponsor: 'Powered by BetterStats' },
  },
  {
    key: 'presentation', label: 'Presentation Night', template: 'EV9', motif: 'trophy', photoLabel: 'Team photo',
    event: { kicker: 'Founded 1921', title: 'Presentation Night', subtitle: "Celebrating the season's finest — awards, life memberships & a few tall tales.", date: 'Sat 20 Sep', time: '7:00 PM', venue: 'The Pavilion', price: '$55', cta: 'RSVP by 12 Sep', sponsor: '' },
  },
  {
    key: 'launch', label: 'Season Launch', template: 'EV7', motif: 'calendar', photoLabel: 'Action / team photo',
    event: { kicker: 'Round 1 · 25/26', title: 'Season Launch', subtitle: 'New season, new caps. Meet the squads and kick off the campaign.', date: 'Sat 4 Oct', time: '11:00 AM', venue: 'Ashcombe Oval', price: 'Free', cta: 'Bring the family', sponsor: 'Powered by BetterStats' },
  },
  {
    key: 'music', label: 'Live Music', template: 'EV11', motif: 'star', photoLabel: 'Band / live photo',
    event: { kicker: 'Friday Sessions', title: 'Live Music', subtitle: 'Local legends on stage. Bar open late, kitchen running til nine.', date: 'Sat 26 Jul', time: '8:00 PM', venue: 'The Clubhouse', price: '$15 entry', cta: 'Tickets at the bar', sponsor: '' },
  },
  {
    key: 'quiz', label: 'Quiz Night', template: 'EV6', motif: 'target', photoLabel: '',
    event: { kicker: 'Trivia & Pizza', title: 'Quiz Night', subtitle: 'Six rounds, one champion table. Teams of up to six players.', date: 'Thu 14 Aug', time: '7:30 PM', venue: 'The Clubhouse', price: '$12', cta: 'Build your team', sponsor: 'Pizza by Forno 47' },
  },
  {
    key: 'generic', label: 'Generic / Blank', template: 'EV8', motif: 'star', photoLabel: 'Add a photo',
    event: { kicker: 'Save the Date', title: 'Club Notice', subtitle: 'Your headline goes here. One template, any announcement — clean and unmistakable.', date: 'Date', time: 'Time', venue: 'Venue', price: 'Free', cta: 'Details to follow.', sponsor: 'Your sponsor here' },
  },
]

export const DEFAULT_EVENT = { ...EVENT_PRESETS[2].event }
export const DEFAULT_EVENT_MOTIF = { key: 'star', icon: motifIcon('star'), imageUrl: null, opacity: 0.85, label: 'Add a photo' }

// Resolve a motif descriptor for a template, given the chosen motif key + any
// uploaded photo. Pass the result straight to a template's `motif` prop.
export function resolveMotif({ motifKey, imageUrl, opacity, label }) {
  return { key: motifKey, icon: motifIcon(motifKey), imageUrl: imageUrl || null, opacity: opacity ?? 0.85, label: label || 'Add a photo' }
}

// Light-surface directions want a paper/ink pair rather than dark mode. Merge
// these onto the active palette before handing it to a light template so the
// club accent still drives the colour but the surface reads as paper.
export function eventPaletteFor(surface, palette) {
  if (surface !== 'light') return palette
  return { ...palette, paper: palette.paper || '#f4efe4', deepInk: palette.deepInk || '#1f1c14' }
}
