// Club launch announcement poster — the whitelabel version of the "Applecross
// is now on Better Cricket" social card. Renders at exactly 1080×1080px and
// reuses the BetterSocials primitives (AutoFitText, ClubLogo, grain/halftone/
// stripes, orgToPalette) so it captures cleanly through the shared
// modern-screenshot export. Every panel is recreated from the club's own data
// (branding, headline stats, a featured player, the XI) rather than screenshot,
// so the poster is fully whitelabelled per club.
import { AutoFitText, ClubLogo, GrainSVG, Halftone, Stripes } from './cricket-templates'
import brandWordmark from '../assets/bettercricket-white.svg'

import statsLogo from '../assets/modules/betterstats.svg'
import selectLogo from '../assets/modules/betterselect.svg'
import socialsLogo from '../assets/modules/bettersocials.svg'
import adminLogo from '../assets/modules/betteradmin.svg'
import iqLogo from '../assets/modules/betteriq.svg'
import fantasyLogo from '../assets/modules/betterfantasy.svg'

// The six Better modules as shown on the poster footer. Blurbs are kept short so
// six tiles read across one row. Editable copy lives on the announce page; this
// is the fallback set.
export const LAUNCH_MODULES = [
  { name: 'BetterStats',   blurb: 'Stats, ladders and history across every team.',  logo: statsLogo },
  { name: 'BetterSelect',  blurb: 'Availability and team selection for every game.', logo: selectLogo },
  { name: 'BetterSocials', blurb: 'News, photos and match-day posts in your voice.', logo: socialsLogo },
  { name: 'BetterAdmin',   blurb: 'Members, fees, emails and merch in one place.',   logo: adminLogo },
  { name: 'BetterIQ',      blurb: 'Analytics and opposition scouting to plan ahead.', logo: iqLogo },
  { name: 'BetterFantasy', blurb: 'Run a club fantasy comp off your own games.',     logo: fantasyLogo },
]

export const LAUNCH_VALUE_PROPS = [
  { icon: 'chart',    title: 'More stats, more insight', body: 'Track performance and milestones.' },
  { icon: 'people',   title: 'Better connections',       body: 'Keep your community informed and involved.' },
  { icon: 'check',    title: 'All in one place',         body: 'Everything your club needs on one platform.' },
]

function ValueIcon({ kind, color }) {
  const common = { width: 26, height: 26, viewBox: '0 0 24 24', fill: 'none', stroke: color, strokeWidth: 2.2, strokeLinecap: 'round', strokeLinejoin: 'round' }
  if (kind === 'people') return (
    <svg {...common}><circle cx="9" cy="8" r="3" /><path d="M3 20c0-3.3 2.7-5 6-5s6 1.7 6 5" /><path d="M16 5.5a3 3 0 0 1 0 5.6" /><path d="M18.5 20c0-2.5-1-4-3-4.7" /></svg>
  )
  if (kind === 'check') return (
    <svg {...common}><rect x="3" y="3" width="18" height="18" rx="3" /><path d="M8 12.5l2.5 2.5L16 9" /></svg>
  )
  return ( // chart
    <svg {...common}><path d="M4 20V10" /><path d="M10 20V4" /><path d="M16 20v-7" /><path d="M22 20H2" /></svg>
  )
}

// Club mark — the uploaded logo if we have one, otherwise a shield monogram in
// the club's accent so a brand-new club without a logo still looks finished.
function Mark({ club, palette, size }) {
  if (club.logo) return <ClubLogo src={club.logo} size={size} />
  return <ClubLogo monogram={club.monogram} color={palette.accent} size={size} shape="shield" />
}

function StatCell({ label, value, accent, ink, big }) {
  return (
    <div style={{ flex: 1, textAlign: 'center', minWidth: 0, padding: '0 4px' }}>
      <div style={{
        fontFamily: "var(--social-display-font, 'Anton', sans-serif)",
        fontSize: big ? 30 : 26, lineHeight: 1, color: big ? accent : ink, letterSpacing: 0.5,
      }}>{value}</div>
      <div style={{ fontSize: 10, letterSpacing: 1.5, opacity: 0.6, marginTop: 5, textTransform: 'uppercase', color: ink }}>{label}</div>
    </div>
  )
}

// A frosted "device" card — the recreated UI panels (dashboard / player / XI).
function Panel({ children, ink, style = {} }) {
  return (
    <div style={{
      background: 'rgba(255,255,255,0.05)',
      border: `1px solid ${ink}1f`,
      borderRadius: 14,
      padding: 16,
      boxShadow: '0 18px 40px rgba(0,0,0,0.35)',
      ...style,
    }}>{children}</div>
  )
}

export function ClubLaunchPoster({
  club = { name: 'Cricket Club', slug: '', logo: null, monogram: 'CC' },
  palette,
  stats = { played: '0', runs: '0', wickets: '0', players: '0', winRate: '0%' },
  featured = null,
  lineup = null,
  valueProps = LAUNCH_VALUE_PROPS,
  modules = LAUNCH_MODULES,
  headline = 'BIG NEWS!',
  subhead = 'A smarter way to run our club, and a better experience for our players, coaches and supporters.',
  footerUrl = 'betterat.cricket',
}) {
  const P = palette || { primary: '#0d1b2a', secondary: '#16263a', accent: '#16c784', ink: '#ffffff' }
  const ink = P.ink || '#ffffff'
  const accent = P.accent || '#16c784'
  const xiRows = (lineup?.rows || []).slice(0, 11)
  const half = Math.ceil(xiRows.length / 2)

  return (
    <div style={{
      width: 1080, height: 1080, position: 'relative', overflow: 'hidden',
      background: `linear-gradient(140deg, ${P.primary} 0%, ${P.secondary} 100%)`,
      color: ink, fontFamily: "'Inter', sans-serif",
      display: 'flex', flexDirection: 'column', padding: 40, boxSizing: 'border-box',
    }}>
      {/* texture + brand energy */}
      <Halftone color={accent} opacity={0.10} size={16} angle={0} />
      <Stripes color={accent} opacity={0.05} angle={-32} gap={26} />
      <div style={{ position: 'absolute', top: -160, right: -160, width: 460, height: 460, borderRadius: '50%', background: `radial-gradient(circle, ${accent}33 0%, transparent 70%)`, pointerEvents: 'none' }} />
      <GrainSVG opacity={0.22} id="launch-grain" />

      {/* ── Header: club mark | BetterCricket wordmark ───────────────────── */}
      <div style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 18, marginBottom: 18 }}>
        <Mark club={club} palette={P} size={76} />
        <div style={{ width: 2, height: 56, background: `${ink}26` }} />
        <img src={brandWordmark} alt="Better Cricket" style={{ height: 38, objectFit: 'contain' }} />
        <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
          <div style={{ fontSize: 11, letterSpacing: 2, opacity: 0.55, textTransform: 'uppercase' }}>Now live on</div>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 22, color: accent, letterSpacing: 0.5 }}>betterat.cricket</div>
        </div>
      </div>

      {/* ── Main: headline + value props | recreated panels ──────────────── */}
      <div style={{ position: 'relative', display: 'flex', gap: 26, flex: 1, minHeight: 0 }}>
        {/* Left */}
        <div style={{ width: 430, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 56, lineHeight: 0.92, color: accent, letterSpacing: 0.5 }}>{headline}</div>
          {/* Fixed-height box so AutoFitText fits the name to *this* 200px, not the whole column. */}
          <div style={{ height: 200, marginTop: 6 }}>
            <AutoFitText
              text={(club.name || 'Cricket Club').toUpperCase()}
              max={72} min={28} lines={3} measureDeps={[club.name]}
              style={{
                fontFamily: "var(--social-display-font, 'Anton', sans-serif)",
                lineHeight: 0.92, letterSpacing: 0.5, color: ink, height: '100%',
              }}
            />
          </div>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 30, color: ink, opacity: 0.92, marginTop: 4, letterSpacing: 0.5 }}>
            IS NOW ON <span style={{ color: accent }}>BETTER CRICKET</span>
          </div>
          <p style={{ fontSize: 16, lineHeight: 1.45, opacity: 0.78, marginTop: 14, marginBottom: 0 }}>{subhead}</p>

          <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 14, paddingTop: 18 }}>
            {valueProps.slice(0, 3).map((v, i) => (
              <div key={i} style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
                <div style={{ flexShrink: 0, width: 44, height: 44, borderRadius: 12, background: `${accent}1f`, border: `1px solid ${accent}55`, display: 'grid', placeItems: 'center' }}>
                  <ValueIcon kind={v.icon} color={accent} />
                </div>
                <div>
                  <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 20, letterSpacing: 0.5, color: ink }}>{(v.title || '').toUpperCase()}</div>
                  <div style={{ fontSize: 14, opacity: 0.72, lineHeight: 1.3 }}>{v.body}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right: recreated panels */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 14, minHeight: 0 }}>
          {/* Dashboard panel */}
          <Panel ink={ink}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
              <Mark club={club} palette={P} size={40} />
              <AutoFitText text={club.name} max={22} min={13} measureDeps={[club.name]}
                style={{ fontWeight: 700, color: ink, flex: 1 }} />
            </div>
            <div style={{ display: 'flex', alignItems: 'stretch' }}>
              <StatCell label="Played" value={stats.played} ink={ink} accent={accent} />
              <StatCell label="Runs" value={stats.runs} ink={ink} accent={accent} />
              <StatCell label="Wickets" value={stats.wickets} ink={ink} accent={accent} />
              <StatCell label="Players" value={stats.players} ink={ink} accent={accent} />
              <StatCell label="Win Rate" value={stats.winRate} ink={ink} accent={accent} big />
            </div>
          </Panel>

          {/* Featured player panel */}
          {featured && (
            <Panel ink={ink} style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
              <div style={{ width: 78, height: 78, borderRadius: '50%', flexShrink: 0, overflow: 'hidden', background: `${accent}22`, border: `2px solid ${accent}`, display: 'grid', placeItems: 'center' }}>
                {featured.photo
                  ? <img src={featured.photo} alt={featured.name} style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'top' }} />
                  : <span style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 30, color: accent }}>{featured.monogram || (featured.name || '?').slice(0, 1)}</span>}
              </div>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontSize: 10, letterSpacing: 1.5, opacity: 0.55, textTransform: 'uppercase' }}>Featured player</div>
                <AutoFitText text={featured.name} max={26} min={15} measureDeps={[featured.name]}
                  style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", color: ink, letterSpacing: 0.5, marginTop: 2 }} />
                {featured.honours?.length ? (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
                    {featured.honours.slice(0, 4).map((h, i) => (
                      <span key={i} style={{ fontSize: 11, padding: '3px 8px', borderRadius: 5, background: `${accent}1f`, border: `1px solid ${accent}55`, color: ink, whiteSpace: 'nowrap' }}>{h}</span>
                    ))}
                  </div>
                ) : (
                  <div style={{ display: 'flex', gap: 18, marginTop: 8 }}>
                    {(featured.lines || []).slice(0, 3).map((s, i) => (
                      <div key={i}>
                        <span style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 22, color: accent }}>{s.value}</span>
                        <span style={{ fontSize: 12, opacity: 0.65, marginLeft: 5 }}>{s.label}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </Panel>
          )}

          {/* Lineup / 1st XI panel */}
          {xiRows.length > 0 && (
            <Panel ink={ink} style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
              <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 10 }}>
                <span style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 24, color: accent, letterSpacing: 1 }}>{(lineup.title || '1ST XI').toUpperCase()}</span>
                {lineup.round && <span style={{ fontSize: 12, opacity: 0.6 }}>{lineup.round}</span>}
              </div>
              <div style={{ display: 'flex', gap: 18, flex: 1 }}>
                {[xiRows.slice(0, half), xiRows.slice(half)].map((col, ci) => (
                  <div key={ci} style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                    {col.map((name, i) => {
                      const num = ci === 0 ? i + 1 : half + i + 1
                      return (
                        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14 }}>
                          <span style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 13, color: accent, width: 18, textAlign: 'right' }}>{String(num).padStart(2, '0')}</span>
                          <span style={{ color: ink, opacity: 0.92, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{name}</span>
                        </div>
                      )
                    })}
                  </div>
                ))}
              </div>
              {(lineup.venue || lineup.time) && (
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 10, paddingTop: 10, borderTop: `1px solid ${ink}1a`, fontSize: 12, opacity: 0.7 }}>
                  <span>{lineup.venue || ''}</span>
                  <span>{lineup.time || ''}</span>
                </div>
              )}
            </Panel>
          )}
        </div>
      </div>

      {/* ── Modules band ──────────────────────────────────────────────────── */}
      <div style={{ position: 'relative', marginTop: 18 }}>
        <div style={{ textAlign: 'center', fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 18, letterSpacing: 2, opacity: 0.85, marginBottom: 12 }}>
          POWERED BY THE <span style={{ color: accent }}>BETTER</span> MODULES
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          {modules.slice(0, 6).map((m, i) => (
            <div key={i} style={{ flex: 1, minWidth: 0, textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5 }}>
              <img src={m.logo} alt={m.name} style={{ width: 38, height: 38, objectFit: 'contain' }} />
              <div style={{ fontWeight: 700, fontSize: 12, color: ink }}>{m.name}</div>
              <div style={{ fontSize: 10, opacity: 0.6, lineHeight: 1.25 }}>{m.blurb}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Footer CTA ────────────────────────────────────────────────────── */}
      <div style={{ position: 'relative', marginTop: 16, display: 'flex', alignItems: 'center', gap: 14, background: ink, borderRadius: 12, padding: '12px 16px' }}>
        <div style={{ width: 36, height: 36, borderRadius: '50%', background: P.primary, display: 'grid', placeItems: 'center', flexShrink: 0 }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={accent} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1" /><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1" /></svg>
        </div>
        <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 22, letterSpacing: 1, color: P.primary }}>
          EXPLORE. ENGAGE. GROW.
        </div>
        <div style={{ marginLeft: 'auto', fontFamily: "'JetBrains Mono', monospace", fontSize: 18, fontWeight: 700, color: P.primary, background: `${accent}33`, padding: '6px 14px', borderRadius: 8 }}>
          {footerUrl}
        </div>
      </div>
    </div>
  )
}
