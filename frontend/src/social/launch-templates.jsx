// Club launch announcement poster — the whitelabel version of the "Applecross
// is now on Better Cricket" social card. Renders at exactly 1080×1080px and
// reuses the BetterSocials primitives (AutoFitText, ClubLogo, grain/halftone/
// stripes) so it captures cleanly through the shared modern-screenshot export.
// Every panel is recreated from the club's own data (branding, headline stats,
// a featured player, top performers) rather than screenshot, so the poster is
// fully whitelabelled per club. Copy reads from the club's point of view.
import { AutoFitText, ClubLogo, GrainSVG, Halftone, Stripes } from './cricket-templates'
import brandWordmark from '../assets/bettercricket-white.svg'

import statsLogo from '../assets/modules/betterstats.svg'
import selectLogo from '../assets/modules/betterselect.svg'
import socialsLogo from '../assets/modules/bettersocials.svg'
import adminLogo from '../assets/modules/betteradmin.svg'
import iqLogo from '../assets/modules/betteriq.svg'
import fantasyLogo from '../assets/modules/betterfantasy.svg'

const BRAND_GREEN = '#16C784'
const GOLD = '#F5B324'

// The six Better modules, described from the club's point of view (what we get).
export const LAUNCH_MODULES = [
  { name: 'BetterStats',   blurb: 'Our stats, ladders and history across every team.',  logo: statsLogo },
  { name: 'BetterSelect',  blurb: 'Availability and team selection for every game.',     logo: selectLogo },
  { name: 'BetterSocials', blurb: 'Our news, photos and match-day updates for members.', logo: socialsLogo },
  { name: 'BetterAdmin',   blurb: 'Members, fees, emails and merch in one place.',       logo: adminLogo },
  { name: 'BetterIQ',      blurb: 'Analytics and opposition scouting so we can plan ahead.', logo: iqLogo },
  { name: 'BetterFantasy', blurb: 'A fantasy comp for our members, run off our own games.', logo: fantasyLogo },
]

// Value props, in the club's voice. Each icon gets its own colour (green / club
// accent / gold) to match the launch graphic.
export const LAUNCH_VALUE_PROPS = [
  { icon: 'chart',  title: 'More stats, more insight', body: 'Track our performance and milestones.' },
  { icon: 'people', title: 'Better connections',       body: 'Keep our community informed and involved.' },
  { icon: 'check',  title: 'All in one place',         body: 'Everything our club needs, on one platform.' },
]

function ValueIcon({ kind, color }) {
  const common = { width: 28, height: 28, viewBox: '0 0 24 24', fill: 'none', stroke: color, strokeWidth: 2.2, strokeLinecap: 'round', strokeLinejoin: 'round' }
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
function Mark({ club, accent, size }) {
  if (club.logo) return <ClubLogo src={club.logo} size={size} />
  return <ClubLogo monogram={club.monogram} color={accent} size={size} shape="shield" />
}

function StatCell({ label, value, accent, ink, big }) {
  return (
    <div style={{ flex: 1, textAlign: 'center', minWidth: 0, padding: '0 4px' }}>
      <div style={{
        fontFamily: "var(--social-display-font, 'Anton', sans-serif)",
        fontSize: big ? 30 : 27, lineHeight: 1, color: big ? accent : ink, letterSpacing: 0.5,
      }}>{value}</div>
      <div style={{ fontSize: 10, letterSpacing: 1.5, opacity: 0.6, marginTop: 5, textTransform: 'uppercase', color: ink }}>{label}</div>
    </div>
  )
}

// A frosted "device" card — the recreated UI panels (dashboard / player / lists).
function Panel({ children, ink, style = {} }) {
  return (
    <div style={{
      background: `${ink}0d`,
      border: `1px solid ${ink}1f`,
      borderRadius: 14,
      padding: 16,
      boxShadow: '0 18px 40px rgba(0,0,0,0.35)',
      ...style,
    }}>{children}</div>
  )
}

// A browser-chrome strip so the dashboard panel reads as a screenshot.
function NavStrip({ ink, accent }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, paddingBottom: 10, borderBottom: `1px solid ${ink}14` }}>
      <span style={{ width: 9, height: 9, borderRadius: '50%', background: accent, opacity: 0.85 }} />
      <span style={{ width: 9, height: 9, borderRadius: '50%', background: GOLD, opacity: 0.7 }} />
      <span style={{ width: 9, height: 9, borderRadius: '50%', background: BRAND_GREEN, opacity: 0.7 }} />
      <span style={{ marginLeft: 6, fontSize: 11, opacity: 0.5, color: ink, letterSpacing: 0.5 }}>Home · Players · Stats · Games · Yearbook</span>
      <span style={{ marginLeft: 'auto', fontSize: 10, letterSpacing: 1, color: ink, opacity: 0.6, border: `1px solid ${ink}33`, borderRadius: 4, padding: '2px 7px' }}>ADMIN</span>
    </div>
  )
}

function LeaderColumn({ title, rows, accent, ink, valueKey }) {
  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 17, color: accent, letterSpacing: 1, marginBottom: 8 }}>{title}</div>
      {rows.length === 0 ? (
        <div style={{ fontSize: 12, opacity: 0.5, color: ink }}>No data yet.</div>
      ) : rows.slice(0, 5).map((r, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0', borderTop: i ? `1px solid ${ink}12` : 'none' }}>
          <span style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 12, color: ink, opacity: 0.5, width: 14 }}>{i + 1}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: ink, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.name}</div>
            {r.sub && <div style={{ fontSize: 10, opacity: 0.55, color: ink, fontFamily: "'JetBrains Mono', monospace" }}>{r.sub}</div>}
          </div>
          <span style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 17, color: accent }}>{r[valueKey]}</span>
        </div>
      ))}
    </div>
  )
}

export function ClubLaunchPoster({
  club = { name: 'Cricket Club', slug: '', logo: null, monogram: 'CC' },
  palette,
  stats = { played: '0', runs: '0', wickets: '0', players: '0', winRate: '0%' },
  featured = null,
  topBatters = [],
  topBowlers = [],
  valueProps = LAUNCH_VALUE_PROPS,
  modules = LAUNCH_MODULES,
  headline = 'BIG NEWS!',
  subhead = 'A smarter way to run our club. A better experience for our players, coaches, members and supporters.',
  footerUrl = 'betterat.cricket',
  showCallout = true,
}) {
  const P = palette || {}
  const bg = P.bg || '#0b0c10'
  const bg2 = P.bg2 || '#2a0a0c'
  const accent = P.accent || '#e21f26'
  const ink = P.ink || '#ffffff'
  const propColors = [BRAND_GREEN, accent, GOLD]

  // Decorative confetti — a few rotated flecks in the three brand colours.
  const confetti = [
    [60, 230, 18, BRAND_GREEN], [120, 90, -32, accent], [300, 60, 20, GOLD],
    [760, 70, -18, accent], [900, 150, 28, BRAND_GREEN], [990, 300, -24, GOLD],
    [40, 620, 24, accent], [980, 560, -30, BRAND_GREEN], [560, 40, 14, accent],
    [1010, 760, 22, GOLD], [30, 430, -20, GOLD],
  ]

  return (
    <div style={{
      width: 1080, height: 1080, position: 'relative', overflow: 'hidden',
      background: `linear-gradient(120deg, ${bg} 38%, ${bg2} 100%)`,
      color: ink, fontFamily: "'Inter', sans-serif",
      display: 'flex', flexDirection: 'column', padding: 40, boxSizing: 'border-box',
    }}>
      {/* texture + accent energy */}
      <div style={{ position: 'absolute', top: -180, right: -160, width: 520, height: 520, borderRadius: '50%', background: `radial-gradient(circle, ${accent}40 0%, transparent 70%)`, pointerEvents: 'none' }} />
      <Halftone color={ink} opacity={0.05} size={16} angle={0} />
      <Stripes color={ink} opacity={0.04} angle={-32} gap={26} />
      {confetti.map(([x, y, rot, c], i) => (
        <div key={i} style={{ position: 'absolute', left: x, top: y, width: 26, height: 11, background: c, opacity: 0.85, transform: `rotate(${rot}deg)`, borderRadius: 2, pointerEvents: 'none' }} />
      ))}
      <GrainSVG opacity={0.18} id="launch-grain" />

      {/* ── Header: club mark | BetterCricket wordmark ───────────────────── */}
      <div style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 18, marginBottom: 14 }}>
        <Mark club={club} accent={accent} size={72} />
        <div style={{ width: 2, height: 52, background: `${ink}26` }} />
        <img src={brandWordmark} alt="Better Cricket" style={{ height: 34, objectFit: 'contain' }} />
      </div>

      {/* ── Main: headline + value props | recreated panels ──────────────── */}
      <div style={{ position: 'relative', display: 'flex', gap: 28, flex: 1, minHeight: 0 }}>
        {/* Left */}
        <div style={{ width: 452, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 60, lineHeight: 0.9, color: ink, letterSpacing: 0.5, transform: 'rotate(-2deg)', transformOrigin: 'left' }}>{headline}</div>
          {/* Fixed-height box so AutoFitText fits the name to *this* 190px, not the whole column. */}
          <div style={{ height: 188, marginTop: 8, transform: 'rotate(-2deg)', transformOrigin: 'left' }}>
            <AutoFitText
              text={(club.name || 'Cricket Club').toUpperCase()}
              max={78} min={28} lines={3} measureDeps={[club.name]}
              style={{
                fontFamily: "var(--social-display-font, 'Anton', sans-serif)",
                lineHeight: 0.9, letterSpacing: 0.5, color: accent, height: '100%',
              }}
            />
          </div>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 27, color: ink, opacity: 0.9, marginTop: 2, letterSpacing: 1 }}>IS NOW ON</div>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 50, letterSpacing: 0.5, lineHeight: 0.95, marginTop: 2 }}>
            <span style={{ color: BRAND_GREEN }}>BETTER</span><span style={{ color: ink }}>CRICKET</span>
          </div>
          <p style={{ fontSize: 16, lineHeight: 1.45, opacity: 0.78, marginTop: 14, marginBottom: 0 }}>{subhead}</p>

          <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 14, paddingTop: 18 }}>
            {valueProps.slice(0, 3).map((v, i) => {
              const c = propColors[i] || accent
              return (
                <div key={i} style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
                  <div style={{ flexShrink: 0, width: 46, height: 46, borderRadius: 12, background: `${c}1f`, border: `1px solid ${c}66`, display: 'grid', placeItems: 'center' }}>
                    <ValueIcon kind={v.icon} color={c} />
                  </div>
                  <div>
                    <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 21, letterSpacing: 0.5, color: ink }}>{(v.title || '').toUpperCase()}</div>
                    <div style={{ fontSize: 14, opacity: 0.72, lineHeight: 1.3 }}>{v.body}</div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Right: recreated panels */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12, minHeight: 0, position: 'relative' }}>
          {showCallout && (
            <div style={{ position: 'absolute', top: -6, right: 2, transform: 'rotate(-6deg)', zIndex: 2, fontFamily: "'Permanent Marker', cursive", fontSize: 15, color: BRAND_GREEN, textShadow: `0 1px 0 ${bg}` }}>
              Check out our club page!
            </div>
          )}

          {/* Dashboard panel */}
          <Panel ink={ink}>
            <NavStrip ink={ink} accent={accent} />
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
              <Mark club={club} accent={accent} size={38} />
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
              <div style={{ width: 76, height: 76, borderRadius: '50%', flexShrink: 0, overflow: 'hidden', background: `${accent}22`, border: `2px solid ${accent}`, display: 'grid', placeItems: 'center' }}>
                {featured.photo
                  ? <img src={featured.photo} alt={featured.name} style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'top' }} />
                  : <span style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 30, color: accent }}>{featured.monogram || (featured.name || '?').slice(0, 1)}</span>}
              </div>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontSize: 10, letterSpacing: 1.5, opacity: 0.55, textTransform: 'uppercase' }}>Featured player</div>
                <AutoFitText text={featured.name} max={26} min={15} measureDeps={[featured.name]}
                  style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", color: ink, letterSpacing: 0.5, marginTop: 2 }} />
                {featured.badges?.length ? (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
                    {featured.badges.slice(0, 6).map((h, i) => (
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

          {/* Top performers panel */}
          <Panel ink={ink} style={{ flex: 1, minHeight: 0 }}>
            <div style={{ display: 'flex', gap: 22 }}>
              <LeaderColumn title="TOP BATTERS" rows={topBatters} accent={accent} ink={ink} valueKey="runs" />
              <div style={{ width: 1, background: `${ink}14` }} />
              <LeaderColumn title="TOP BOWLERS" rows={topBowlers} accent={accent} ink={ink} valueKey="wickets" />
            </div>
          </Panel>
        </div>
      </div>

      {/* ── Modules band ──────────────────────────────────────────────────── */}
      <div style={{ position: 'relative', marginTop: 16 }}>
        <div style={{ textAlign: 'center', fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 18, letterSpacing: 2, opacity: 0.9, marginBottom: 12 }}>
          POWERED BY THE <span style={{ color: BRAND_GREEN }}>BETTER</span> MODULES
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          {modules.slice(0, 6).map((m, i) => (
            <div key={i} style={{ flex: 1, minWidth: 0, textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5 }}>
              <img src={m.logo} alt={m.name} style={{ width: 38, height: 38, objectFit: 'contain' }} />
              <div style={{ fontWeight: 700, fontSize: 12, color: ink }}>{m.name}</div>
              <div style={{ fontSize: 10, opacity: 0.62, lineHeight: 1.25 }}>{m.blurb}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Footer CTA ────────────────────────────────────────────────────── */}
      <div style={{ position: 'relative', marginTop: 16, display: 'flex', alignItems: 'center', gap: 14, background: ink, borderRadius: 12, padding: '11px 16px' }}>
        <div style={{ width: 36, height: 36, borderRadius: '50%', background: bg, display: 'grid', placeItems: 'center', flexShrink: 0 }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={accent} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1" /><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1" /></svg>
        </div>
        <div>
          <div style={{ fontFamily: "var(--social-display-font, 'Anton', sans-serif)", fontSize: 21, letterSpacing: 1, color: bg, lineHeight: 1 }}>EXPLORE. ENGAGE. GROW.</div>
          <div style={{ fontSize: 12, color: accent, fontWeight: 700, letterSpacing: 0.5, marginTop: 2 }}>VISIT OUR CLUB PAGE TODAY</div>
        </div>
        <div style={{ marginLeft: 'auto', fontFamily: "'JetBrains Mono', monospace", fontSize: 17, fontWeight: 700, color: bg, background: `${accent}26`, padding: '7px 14px', borderRadius: 8 }}>
          {footerUrl}
        </div>
      </div>
    </div>
  )
}
