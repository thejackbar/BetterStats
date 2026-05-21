// Full match scorecards — 1920×1080.
// Three styles share the same structural rules:
//   • Header lockup: result + meta (left) · Match info (middle) · MOTM (right)
//   • Single-line batting/bowling rows: dismissal text alongside name, no stacked "balls"
//   • Sponsor footer at the bottom
// Each style applies its own visual identity on top of that scaffold.
//
// All accept { match, dark } where match = SAMPLE_FULL_MATCH and dark toggles light/dark.

const SC_FONT = "'Anton', sans-serif";
const SC_MONO = "'JetBrains Mono', monospace";
const SC_BODY = "'Inter', sans-serif";

// ─────────────────────────────────────────────────────────────
// Shared sponsor footer — same shape across all three styles
// ─────────────────────────────────────────────────────────────
function ScSponsorFooter({ bg, ink, dim, dimmer, rule, style = {} }) {
  return (
    <div style={{
      position: "absolute", left: 32, right: 32, bottom: 16,
      height: 56,
      display: "grid", gridTemplateColumns: "auto 1fr auto", alignItems: "center", gap: 24,
      padding: "0 22px", borderRadius: 12,
      background: bg, border: `1px solid ${rule}`,
      ...style,
    }}>
      <div style={{ fontFamily: SC_BODY, fontSize: 10, letterSpacing: 2.5, color: dim, fontWeight: 600 }}>
        PROUDLY PRESENTED BY
      </div>
      <div style={{
        display: "flex", justifyContent: "center", alignItems: "center", gap: 40,
        fontFamily: SC_FONT, fontSize: 18, letterSpacing: 3, color: dimmer,
      }}>
        <div style={{ padding: "6px 18px", border: `1px dashed ${dimmer}`, borderRadius: 6 }}>SPONSOR LOGO</div>
        <div style={{ padding: "6px 18px", border: `1px dashed ${dimmer}`, borderRadius: 6 }}>SPONSOR LOGO</div>
        <div style={{ padding: "6px 18px", border: `1px dashed ${dimmer}`, borderRadius: 6 }}>SPONSOR LOGO</div>
      </div>
      <div style={{ fontFamily: SC_MONO, fontSize: 10, letterSpacing: 1.5, color: dimmer }}>
        BETTERSTATS · SCORECARD
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// STYLE 1 — BROADCAST  (dense TV scoreboard, dark or light)
// ═══════════════════════════════════════════════════════════════════════
function SC1_Broadcast({ match, dark = true }) {
  const m = match;
  const bg     = dark ? "#0a1224" : "#f4f3ee";
  const panel  = dark ? "#101c38" : "#ffffff";
  const panel2 = dark ? "#0d1730" : "#ebe9e0";
  const ink    = dark ? "#f4f3ee" : "#0a1224";
  const dim    = dark ? "rgba(244,243,238,0.55)" : "rgba(10,18,36,0.55)";
  const dimmer = dark ? "rgba(244,243,238,0.35)" : "rgba(10,18,36,0.35)";
  const rule   = dark ? "rgba(244,243,238,0.10)" : "rgba(10,18,36,0.10)";
  const accent = "#ffc233";
  const homeC  = m.home.color;
  const awayC  = m.away.color;

  const TeamPanel = ({ team, accentC, side }) => (
    <div style={{
      background: panel, border: `1px solid ${rule}`,
      display: "flex", flexDirection: "column", overflow: "hidden",
    }}>
      {/* Team strip */}
      <div style={{
        display: "grid", gridTemplateColumns: "auto 1fr auto",
        alignItems: "center", gap: 18, padding: "14px 22px",
        background: `linear-gradient(90deg, ${accentC}, ${accentC}aa 60%, transparent)`,
        color: "#0a0a0a", borderBottom: `1px solid ${rule}`,
      }}>
        <ClubLogo monogram={team.short} color="#0a0a0a" size={52} shape="shield" />
        <div>
          <div style={{ fontFamily: SC_FONT, fontSize: 34, letterSpacing: 1.5, lineHeight: 1 }}>{team.name}</div>
          <div style={{ fontFamily: SC_MONO, fontSize: 11, letterSpacing: 2, marginTop: 4, opacity: 0.7 }}>
            {side === "home" ? "1ST INNINGS" : "2ND INNINGS · CHASE"} · RR {team.runRate}
          </div>
        </div>
        <div style={{ textAlign: "right", lineHeight: 0.9 }}>
          <div style={{ fontFamily: SC_FONT, fontSize: 56, letterSpacing: -1 }}>
            {team.total}{team.wickets < 10 ? `/${team.wickets}` : ""}
          </div>
          <div style={{ fontFamily: SC_MONO, fontSize: 11, letterSpacing: 2, marginTop: 2 }}>{team.overs} OV</div>
        </div>
      </div>

      {/* Batting */}
      <div style={{ padding: "10px 18px 4px" }}>
        <div style={{
          display: "grid", gridTemplateColumns: "26px 1fr 1.1fr 42px 38px 32px 32px 50px",
          gap: 8, fontFamily: SC_MONO, fontSize: 10, letterSpacing: 1.5,
          color: dim, padding: "0 2px 6px", borderBottom: `1px solid ${rule}`,
        }}>
          <div>#</div><div>BATTER</div><div>HOW OUT</div>
          <div style={{ textAlign: "right" }}>R</div>
          <div style={{ textAlign: "right" }}>B</div>
          <div style={{ textAlign: "right" }}>4s</div>
          <div style={{ textAlign: "right" }}>6s</div>
          <div style={{ textAlign: "right" }}>SR</div>
        </div>
        {team.batting.map((p, i) => {
          const dnb = p.didNotBat;
          return (
            <div key={i} style={{
              display: "grid", gridTemplateColumns: "26px 1fr 1.1fr 42px 38px 32px 32px 50px",
              gap: 8, padding: "5px 2px", alignItems: "baseline",
              borderBottom: i < team.batting.length - 1 ? `1px solid ${rule}` : "none",
              opacity: dnb ? 0.4 : 1,
            }}>
              <div style={{ fontFamily: SC_MONO, fontSize: 11, color: dim }}>{p.num}</div>
              <div style={{ fontFamily: SC_FONT, fontSize: 18, letterSpacing: 0.5, lineHeight: 1, display: "flex", alignItems: "baseline", gap: 6, whiteSpace: "nowrap", overflow: "hidden" }}>
                <span style={{ color: dim, fontSize: 13, fontWeight: 300 }}>{p.first}</span>
                <span>{p.last}</span>
                {p.role && <span style={{ fontFamily: SC_MONO, fontSize: 9, color: accent, letterSpacing: 1, marginLeft: 2 }}>({p.role})</span>}
              </div>
              <div style={{ fontFamily: SC_BODY, fontSize: 12, color: dim, lineHeight: 1.2,
                            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {dnb ? "did not bat" : (p.notOut ? "not out" : p.out)}
              </div>
              <div style={{ textAlign: "right", fontFamily: SC_FONT, fontSize: 20, lineHeight: 1, color: dnb ? dim : ink }}>
                {dnb ? "—" : (p.notOut ? `${p.r}*` : p.r)}
              </div>
              <div style={{ textAlign: "right", fontFamily: SC_MONO, fontSize: 12, color: dim }}>{dnb ? "—" : p.b}</div>
              <div style={{ textAlign: "right", fontFamily: SC_MONO, fontSize: 12, color: dim }}>{dnb ? "—" : p.fours}</div>
              <div style={{ textAlign: "right", fontFamily: SC_MONO, fontSize: 12, color: dim }}>{dnb ? "—" : p.sixes}</div>
              <div style={{ textAlign: "right", fontFamily: SC_MONO, fontSize: 12, color: dnb ? dim : accent }}>{dnb ? "—" : p.sr.toFixed(2)}</div>
            </div>
          );
        })}
        {/* Extras */}
        <div style={{
          display: "grid", gridTemplateColumns: "1fr 56px",
          padding: "8px 2px", borderTop: `1px solid ${rule}`,
          fontFamily: SC_MONO, fontSize: 12, color: dim, letterSpacing: 1,
        }}>
          <div>EXTRAS · b {team.extras.b} · lb {team.extras.lb} · nb {team.extras.nb} · wd {team.extras.wd}</div>
          <div style={{ textAlign: "right", color: ink }}>{team.extras.total}</div>
        </div>
      </div>

      {/* Bowling */}
      <div style={{ padding: "6px 18px 14px", background: panel2, marginTop: "auto" }}>
        <div style={{
          display: "grid", gridTemplateColumns: "1fr 42px 38px 42px 38px 50px",
          gap: 8, fontFamily: SC_MONO, fontSize: 10, letterSpacing: 2,
          color: dim, padding: "8px 2px 4px", borderBottom: `1px solid ${rule}`,
        }}>
          <div style={{ color: accent }}>{side === "home" ? `${m.away.short} BOWLING` : `${m.home.short} BOWLING`}</div>
          <div style={{ textAlign: "right" }}>O</div>
          <div style={{ textAlign: "right" }}>M</div>
          <div style={{ textAlign: "right" }}>R</div>
          <div style={{ textAlign: "right" }}>W</div>
          <div style={{ textAlign: "right" }}>ECON</div>
        </div>
        {team.bowling.map((p, i) => (
          <div key={i} style={{
            display: "grid", gridTemplateColumns: "1fr 42px 38px 42px 38px 50px",
            gap: 8, padding: "5px 2px", alignItems: "baseline",
            borderBottom: i < team.bowling.length - 1 ? `1px solid ${rule}` : "none",
          }}>
            <div style={{ fontFamily: SC_FONT, fontSize: 17, letterSpacing: 0.5, display: "flex", alignItems: "baseline", gap: 6 }}>
              <span style={{ color: dim, fontSize: 12, fontWeight: 300 }}>{p.first}</span>
              <span>{p.last}</span>
            </div>
            <div style={{ textAlign: "right", fontFamily: SC_MONO, fontSize: 12 }}>{p.o}</div>
            <div style={{ textAlign: "right", fontFamily: SC_MONO, fontSize: 12, color: dim }}>{p.m}</div>
            <div style={{ textAlign: "right", fontFamily: SC_MONO, fontSize: 12 }}>{p.r}</div>
            <div style={{ textAlign: "right", fontFamily: SC_FONT, fontSize: 18, color: p.w > 0 ? accent : ink }}>{p.w}</div>
            <div style={{ textAlign: "right", fontFamily: SC_MONO, fontSize: 12, color: dim }}>{p.econ.toFixed(2)}</div>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div style={{
      width: 1920, height: 1080, position: "relative", overflow: "hidden",
      background: bg, color: ink, fontFamily: SC_BODY,
    }}>
      <Halftone color={ink} opacity={dark ? 0.04 : 0.05} size={12} />

      {/* Header — result + meta · Match info · MOTM */}
      <div style={{ padding: "18px 24px 12px" }}>
        <div style={{
          padding: "16px 24px",
          background: panel, border: `1px solid ${rule}`,
          display: "grid", gridTemplateColumns: "1.4fr 1fr auto", alignItems: "center", gap: 28,
        }}>
          <div>
            <div style={{
              display: "inline-block", padding: "4px 10px",
              background: accent, color: "#0a0a0a",
              fontFamily: SC_FONT, fontSize: 13, letterSpacing: 3,
            }}>{m.meta.competition} · {m.meta.round} · {m.meta.format}</div>
            <div style={{
              fontFamily: SC_FONT, fontSize: 42, letterSpacing: 1, lineHeight: 1.02,
              color: ink, marginTop: 8,
            }}>{m.meta.result}</div>
            <div style={{ fontFamily: SC_MONO, fontSize: 12, letterSpacing: 1.5, color: dim, marginTop: 4 }}>
              {m.meta.date} · {m.meta.venue}
            </div>
          </div>
          <div style={{
            display: "grid", gridTemplateColumns: "auto 1fr", gap: "3px 14px",
            paddingLeft: 24, borderLeft: `1px solid ${rule}`,
            fontFamily: SC_MONO, fontSize: 12,
          }}>
            <span style={{ color: accent, fontWeight: 600, letterSpacing: 1.5 }}>TOSS</span>
            <span style={{ color: ink, fontFamily: SC_BODY }}>{m.meta.toss}</span>
            <span style={{ color: accent, fontWeight: 600, letterSpacing: 1.5 }}>FORMAT</span>
            <span style={{ color: ink, fontFamily: SC_BODY }}>{m.meta.format} · {m.meta.overs} overs/side</span>
            <span style={{ color: accent, fontWeight: 600, letterSpacing: 1.5 }}>SERIES</span>
            <span style={{ color: ink, fontFamily: SC_BODY }}>{m.meta.series}</span>
          </div>
          <div style={{
            display: "flex", alignItems: "center", gap: 12,
            padding: "10px 16px",
            background: `${accent}1a`, border: `1px solid ${accent}66`,
          }}>
            <div style={{ fontFamily: SC_FONT, fontSize: 26, color: accent, lineHeight: 1 }}>★</div>
            <div>
              <div style={{ fontFamily: SC_MONO, fontSize: 10, color: accent, letterSpacing: 2, fontWeight: 600 }}>PLAYER OF THE MATCH</div>
              <div style={{ fontFamily: SC_FONT, fontSize: 22, color: ink, letterSpacing: 1, lineHeight: 1, marginTop: 4 }}>
                {m.meta.motm.first.toUpperCase()} {m.meta.motm.last}
              </div>
              <div style={{ fontFamily: SC_MONO, fontSize: 11, color: dim, marginTop: 4 }}>{m.meta.motm.line}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Two team panels */}
      <div style={{
        display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16,
        padding: "0 24px", height: 808,
      }}>
        <TeamPanel team={m.home} accentC={homeC} side="home" />
        <TeamPanel team={m.away} accentC={awayC} side="away" />
      </div>

      <ScSponsorFooter bg={panel} ink={ink} dim={dim} dimmer={dimmer} rule={rule} />

      <GrainSVG opacity={dark ? 0.22 : 0.16} id="sc1g" />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// STYLE 2 — BRUTALIST  (matches lineup posters; heavy Anton, hard rules)
// ═══════════════════════════════════════════════════════════════════════
function SC2_Brutalist({ match, dark = false }) {
  const m = match;
  const bg     = dark ? "#0a0a0c" : "#f0ece2";
  const ink    = dark ? "#f0ece2" : "#0a0a0c";
  const dim    = dark ? "rgba(240,236,226,0.55)" : "rgba(10,10,12,0.55)";
  const dimmer = dark ? "rgba(240,236,226,0.32)" : "rgba(10,10,12,0.32)";
  const rule   = dark ? "rgba(240,236,226,0.18)" : "rgba(10,10,12,0.18)";
  const ruleStrong = dark ? "rgba(240,236,226,0.7)" : "rgba(10,10,12,0.85)";
  const accent = dark ? "#ffc233" : "#cc1f2c";
  const stripe = dark ? "rgba(240,236,226,0.04)" : "rgba(10,10,12,0.04)";

  // Team column — title bar + batting + bowling, single-line rows
  const TeamCol = ({ team, side }) => (
    <div style={{
      borderLeft: `2px solid ${ruleStrong}`,
      borderRight: `2px solid ${ruleStrong}`,
      display: "flex", flexDirection: "column",
    }}>
      {/* Team title bar */}
      <div style={{
        background: ink, color: bg,
        padding: "16px 22px",
        display: "grid", gridTemplateColumns: "1fr auto", alignItems: "center", gap: 18,
        borderBottom: `2px solid ${ruleStrong}`,
      }}>
        <div>
          <div style={{ fontFamily: SC_MONO, fontSize: 11, letterSpacing: 3, opacity: 0.65 }}>
            {side === "home" ? "1ST INNINGS" : "2ND INNINGS"}
          </div>
          <div style={{ fontFamily: SC_FONT, fontSize: 52, letterSpacing: 1, lineHeight: 0.95, marginTop: 2 }}>
            {team.name}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontFamily: SC_FONT, fontSize: 64, letterSpacing: -1, lineHeight: 0.9, color: accent }}>
            {team.total}{team.wickets < 10 ? `/${team.wickets}` : ""}
          </div>
          <div style={{ fontFamily: SC_MONO, fontSize: 11, letterSpacing: 2, opacity: 0.7, marginTop: 4 }}>
            {team.overs} OV · RR {team.runRate}
          </div>
        </div>
      </div>

      {/* Batting */}
      <div style={{ padding: "10px 18px 0" }}>
        <div style={{
          fontFamily: SC_FONT, fontSize: 18, letterSpacing: 2, color: accent,
          paddingBottom: 6, borderBottom: `2px solid ${ruleStrong}`,
        }}>BATTING</div>
        <div style={{
          display: "grid", gridTemplateColumns: "1fr 1.1fr 44px 38px 32px 32px 50px",
          gap: 8, fontFamily: SC_MONO, fontSize: 10, letterSpacing: 1.5,
          color: dim, padding: "6px 0", borderBottom: `1px solid ${rule}`,
        }}>
          <div>BATTER</div><div>HOW OUT</div>
          <div style={{ textAlign: "right" }}>R</div>
          <div style={{ textAlign: "right" }}>B</div>
          <div style={{ textAlign: "right" }}>4s</div>
          <div style={{ textAlign: "right" }}>6s</div>
          <div style={{ textAlign: "right" }}>SR</div>
        </div>
        {team.batting.map((p, i) => {
          const dnb = p.didNotBat;
          return (
            <div key={i} style={{
              display: "grid", gridTemplateColumns: "1fr 1.1fr 44px 38px 32px 32px 50px",
              gap: 8, padding: "5px 0", alignItems: "baseline",
              borderBottom: i < team.batting.length - 1 ? `1px solid ${rule}` : "none",
              background: i % 2 === 0 ? stripe : "transparent",
              opacity: dnb ? 0.35 : 1,
            }}>
              <div style={{ fontFamily: SC_FONT, fontSize: 20, letterSpacing: 0.5, lineHeight: 1, display: "flex", alignItems: "baseline", gap: 6, whiteSpace: "nowrap", overflow: "hidden" }}>
                <span style={{ color: dim, fontSize: 13, fontWeight: 300 }}>{p.first}</span>
                <span>{p.last}</span>
                {p.role && <span style={{ fontFamily: SC_MONO, fontSize: 9, color: accent, letterSpacing: 1 }}>({p.role})</span>}
              </div>
              <div style={{ fontFamily: SC_BODY, fontSize: 12, color: dim, fontStyle: "italic",
                            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {dnb ? "did not bat" : (p.notOut ? "not out" : p.out)}
              </div>
              <div style={{ textAlign: "right", fontFamily: SC_FONT, fontSize: 22, lineHeight: 1, color: dnb ? dim : ink, letterSpacing: -0.5 }}>
                {dnb ? "—" : (p.notOut ? `${p.r}*` : p.r)}
              </div>
              <div style={{ textAlign: "right", fontFamily: SC_MONO, fontSize: 12, color: dim }}>{dnb ? "—" : p.b}</div>
              <div style={{ textAlign: "right", fontFamily: SC_MONO, fontSize: 12, color: dim }}>{dnb ? "—" : p.fours}</div>
              <div style={{ textAlign: "right", fontFamily: SC_MONO, fontSize: 12, color: dim }}>{dnb ? "—" : p.sixes}</div>
              <div style={{ textAlign: "right", fontFamily: SC_MONO, fontSize: 12, color: dnb ? dim : accent }}>{dnb ? "—" : p.sr.toFixed(2)}</div>
            </div>
          );
        })}
        <div style={{
          display: "grid", gridTemplateColumns: "1fr 56px",
          padding: "6px 0", borderTop: `2px solid ${ruleStrong}`,
          fontFamily: SC_MONO, fontSize: 11, color: dim, letterSpacing: 1,
        }}>
          <div>EXTRAS · b {team.extras.b} · lb {team.extras.lb} · nb {team.extras.nb} · wd {team.extras.wd}</div>
          <div style={{ textAlign: "right", color: ink, fontFamily: SC_FONT, fontSize: 18 }}>{team.extras.total}</div>
        </div>
      </div>

      {/* Bowling */}
      <div style={{ padding: "10px 18px 14px", marginTop: "auto" }}>
        <div style={{
          fontFamily: SC_FONT, fontSize: 18, letterSpacing: 2, color: accent,
          paddingBottom: 6, borderBottom: `2px solid ${ruleStrong}`,
        }}>{side === "home" ? `${m.away.short} BOWLING` : `${m.home.short} BOWLING`}</div>
        <div style={{
          display: "grid", gridTemplateColumns: "1fr 42px 38px 42px 38px 56px",
          gap: 8, fontFamily: SC_MONO, fontSize: 10, letterSpacing: 1.5,
          color: dim, padding: "6px 0", borderBottom: `1px solid ${rule}`,
        }}>
          <div>BOWLER</div>
          <div style={{ textAlign: "right" }}>O</div>
          <div style={{ textAlign: "right" }}>M</div>
          <div style={{ textAlign: "right" }}>R</div>
          <div style={{ textAlign: "right" }}>W</div>
          <div style={{ textAlign: "right" }}>ECON</div>
        </div>
        {team.bowling.map((p, i) => (
          <div key={i} style={{
            display: "grid", gridTemplateColumns: "1fr 42px 38px 42px 38px 56px",
            gap: 8, padding: "5px 0", alignItems: "baseline",
            borderBottom: i < team.bowling.length - 1 ? `1px solid ${rule}` : "none",
            background: i % 2 === 0 ? stripe : "transparent",
          }}>
            <div style={{ fontFamily: SC_FONT, fontSize: 19, letterSpacing: 0.5, display: "flex", alignItems: "baseline", gap: 6 }}>
              <span style={{ color: dim, fontSize: 12, fontWeight: 300 }}>{p.first}</span>
              <span>{p.last}</span>
            </div>
            <div style={{ textAlign: "right", fontFamily: SC_MONO, fontSize: 12 }}>{p.o}</div>
            <div style={{ textAlign: "right", fontFamily: SC_MONO, fontSize: 12, color: dim }}>{p.m}</div>
            <div style={{ textAlign: "right", fontFamily: SC_MONO, fontSize: 12 }}>{p.r}</div>
            <div style={{ textAlign: "right", fontFamily: SC_FONT, fontSize: 20, color: p.w > 0 ? accent : ink, lineHeight: 1 }}>{p.w}</div>
            <div style={{ textAlign: "right", fontFamily: SC_MONO, fontSize: 12, color: dim }}>{p.econ.toFixed(2)}</div>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div style={{
      width: 1920, height: 1080, position: "relative", overflow: "hidden",
      background: bg, color: ink, fontFamily: SC_BODY,
    }}>
      <Stripes color={ink} opacity={0.04} gap={6} angle={0} />
      <Halftone color={ink} opacity={dark ? 0.05 : 0.06} size={12} />

      {/* Giant background type */}
      <div style={{
        position: "absolute", right: -30, top: 200,
        fontFamily: SC_FONT, fontSize: 360, lineHeight: 0.8,
        color: ink, opacity: 0.04, letterSpacing: -10, userSelect: "none",
      }}>FINAL</div>

      {/* Header band — result + Match + MOTM */}
      <div style={{
        background: accent, color: dark ? "#0a0a0c" : "#f0ece2",
        padding: "18px 32px",
        display: "grid", gridTemplateColumns: "1.4fr 1fr auto", alignItems: "center", gap: 32,
        borderBottom: `2px solid ${ruleStrong}`,
      }}>
        <div>
          <div style={{ fontFamily: SC_MONO, fontSize: 12, letterSpacing: 3, opacity: 0.85 }}>
            // {m.meta.competition} · {m.meta.round} · {m.meta.format}
          </div>
          <div style={{ fontFamily: SC_FONT, fontSize: 52, letterSpacing: 1, lineHeight: 1, marginTop: 4 }}>
            {m.meta.result}
          </div>
          <div style={{ fontFamily: SC_MONO, fontSize: 12, letterSpacing: 2, opacity: 0.85, marginTop: 4 }}>
            {m.meta.date} · {m.meta.venue.toUpperCase()}
          </div>
        </div>
        <div style={{
          display: "grid", gridTemplateColumns: "auto 1fr", gap: "3px 14px",
          fontFamily: SC_BODY, fontSize: 12,
          paddingLeft: 24, borderLeft: `2px solid ${ruleStrong}`,
        }}>
          <span style={{ fontWeight: 700, letterSpacing: 1.5, fontFamily: SC_MONO }}>TOSS</span>
          <span>{m.meta.toss}</span>
          <span style={{ fontWeight: 700, letterSpacing: 1.5, fontFamily: SC_MONO }}>FORMAT</span>
          <span>{m.meta.format} · {m.meta.overs} overs/side</span>
          <span style={{ fontWeight: 700, letterSpacing: 1.5, fontFamily: SC_MONO }}>SERIES</span>
          <span>{m.meta.series}</span>
        </div>
        <div style={{
          padding: "10px 16px",
          background: dark ? "#0a0a0c" : "#f0ece2", color: accent,
          border: `2px solid ${dark ? "#0a0a0c" : "#0a0a0c"}`,
        }}>
          <div style={{ fontFamily: SC_MONO, fontSize: 10, letterSpacing: 2, fontWeight: 700, color: ink }}>★ PLAYER OF THE MATCH</div>
          <div style={{ fontFamily: SC_FONT, fontSize: 28, color: ink, letterSpacing: 1, lineHeight: 1, marginTop: 4 }}>
            {m.meta.motm.first.toUpperCase()} {m.meta.motm.last}
          </div>
          <div style={{ fontFamily: SC_MONO, fontSize: 11, color: ink, opacity: 0.7, marginTop: 4 }}>{m.meta.motm.line}</div>
        </div>
      </div>

      {/* Two-column body */}
      <div style={{
        display: "grid", gridTemplateColumns: "1fr 1fr",
        height: 830,
      }}>
        <TeamCol team={m.home} side="home" />
        <TeamCol team={m.away} side="away" />
      </div>

      <ScSponsorFooter
        bg={ink}
        ink={bg}
        dim={dark ? "rgba(10,10,12,0.55)" : "rgba(240,236,226,0.65)"}
        dimmer={dark ? "rgba(10,10,12,0.35)" : "rgba(240,236,226,0.45)"}
        rule={ruleStrong}
        style={{ borderRadius: 0, borderTop: `3px solid ${accent}` }}
      />

      <GrainSVG opacity={dark ? 0.28 : 0.18} id="sc2g" />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// STYLE 3 — DASHBOARD  (soft cards, light, modern app feel)
// ═══════════════════════════════════════════════════════════════════════
function SC3_Dashboard({ match, dark = false }) {
  const m = match;
  const bg     = dark ? "#0e1116" : "#f3f4f6";
  const card   = dark ? "#171b22" : "#ffffff";
  const ink    = dark ? "#e5e7eb" : "#111827";
  const dim    = dark ? "rgba(229,231,235,0.55)" : "rgba(17,24,39,0.55)";
  const dimmer = dark ? "rgba(229,231,235,0.35)" : "rgba(17,24,39,0.4)";
  const rule   = dark ? "rgba(229,231,235,0.08)" : "rgba(17,24,39,0.08)";
  const accent = "#2563eb";              // dashboard blue
  const win    = "#10b981";              // result green

  const Card = ({ children, style }) => (
    <div style={{
      background: card,
      borderRadius: 16,
      border: `1px solid ${rule}`,
      boxShadow: dark ? "0 1px 0 rgba(255,255,255,0.04)" : "0 1px 2px rgba(17,24,39,0.06)",
      padding: 18,
      ...style,
    }}>{children}</div>
  );

  const TeamCard = ({ team, accentC, side }) => (
    <Card style={{ display: "flex", flexDirection: "column", padding: 0 }}>
      {/* Team header */}
      <div style={{
        display: "grid", gridTemplateColumns: "auto 1fr auto",
        alignItems: "center", gap: 16, padding: "18px 20px",
        borderBottom: `1px solid ${rule}`,
      }}>
        <div style={{
          width: 52, height: 52, borderRadius: 12,
          background: `${accentC}22`, color: accentC,
          display: "grid", placeItems: "center",
          fontFamily: SC_FONT, fontSize: 22, letterSpacing: 1,
        }}>{team.short}</div>
        <div>
          <div style={{ fontFamily: SC_BODY, fontSize: 12, letterSpacing: 1.5, color: dim, fontWeight: 500 }}>
            {side === "home" ? "1ST INNINGS" : "2ND INNINGS"}
          </div>
          <div style={{ fontFamily: SC_FONT, fontSize: 28, letterSpacing: 0.5, lineHeight: 1.1, color: ink }}>
            {team.name}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontFamily: SC_FONT, fontSize: 44, lineHeight: 0.9, color: ink, letterSpacing: -1 }}>
            {team.total}{team.wickets < 10 ? `/${team.wickets}` : ""}
          </div>
          <div style={{ fontFamily: SC_BODY, fontSize: 12, color: dim, marginTop: 4, fontWeight: 500 }}>
            {team.overs} ov · RR {team.runRate}
          </div>
        </div>
      </div>

      {/* Batting */}
      <div style={{ padding: "10px 20px 4px" }}>
        <div style={{
          display: "grid", gridTemplateColumns: "1fr 1.1fr 42px 38px 32px 32px 50px",
          gap: 10, alignItems: "baseline", marginBottom: 4,
          paddingBottom: 4, borderBottom: `1px solid ${rule}`,
        }}>
          <div style={{ fontFamily: SC_BODY, fontSize: 10, letterSpacing: 2, color: dim, fontWeight: 600 }}>BATTER</div>
          <div style={{ fontFamily: SC_BODY, fontSize: 10, letterSpacing: 2, color: dim, fontWeight: 600 }}>HOW OUT</div>
          <div style={{ textAlign: "right", fontFamily: SC_BODY, fontSize: 10, letterSpacing: 1.5, color: dimmer, fontWeight: 500 }}>R</div>
          <div style={{ textAlign: "right", fontFamily: SC_BODY, fontSize: 10, letterSpacing: 1.5, color: dimmer, fontWeight: 500 }}>B</div>
          <div style={{ textAlign: "right", fontFamily: SC_BODY, fontSize: 10, letterSpacing: 1.5, color: dimmer, fontWeight: 500 }}>4s</div>
          <div style={{ textAlign: "right", fontFamily: SC_BODY, fontSize: 10, letterSpacing: 1.5, color: dimmer, fontWeight: 500 }}>6s</div>
          <div style={{ textAlign: "right", fontFamily: SC_BODY, fontSize: 10, letterSpacing: 1.5, color: dimmer, fontWeight: 500 }}>SR</div>
        </div>
        {team.batting.map((p, i) => {
          const dnb = p.didNotBat;
          return (
            <div key={i} style={{
              display: "grid", gridTemplateColumns: "1fr 1.1fr 42px 38px 32px 32px 50px",
              gap: 10, padding: "5px 0", alignItems: "baseline",
              borderBottom: i < team.batting.length - 1 ? `1px solid ${rule}` : "none",
              opacity: dnb ? 0.4 : 1,
            }}>
              <div style={{ fontFamily: SC_BODY, fontSize: 14, fontWeight: 600, color: ink, lineHeight: 1.1, display: "flex", alignItems: "baseline", gap: 6, whiteSpace: "nowrap", overflow: "hidden" }}>
                <span style={{ color: dim, fontSize: 12, fontWeight: 400 }}>{p.first}</span>
                <span>{p.last}</span>
                {p.role && (
                  <span style={{
                    fontSize: 9, fontWeight: 600, letterSpacing: 1, padding: "1px 5px",
                    borderRadius: 4, background: `${accent}22`, color: accent,
                  }}>{p.role}</span>
                )}
              </div>
              <div style={{ fontFamily: SC_BODY, fontSize: 11.5, color: dim, lineHeight: 1.2,
                            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {dnb ? "did not bat" : (p.notOut ? "not out" : p.out)}
              </div>
              <div style={{ textAlign: "right", fontFamily: SC_BODY, fontSize: 16, fontWeight: 700, color: dnb ? dim : ink, lineHeight: 1 }}>
                {dnb ? "—" : (p.notOut ? `${p.r}*` : p.r)}
              </div>
              <div style={{ textAlign: "right", fontFamily: SC_MONO, fontSize: 11, color: dim }}>{dnb ? "—" : p.b}</div>
              <div style={{ textAlign: "right", fontFamily: SC_MONO, fontSize: 11, color: dim }}>{dnb ? "—" : p.fours}</div>
              <div style={{ textAlign: "right", fontFamily: SC_MONO, fontSize: 11, color: dim }}>{dnb ? "—" : p.sixes}</div>
              <div style={{ textAlign: "right", fontFamily: SC_MONO, fontSize: 11, color: dnb ? dim : accent, fontWeight: 600 }}>
                {dnb ? "—" : p.sr.toFixed(1)}
              </div>
            </div>
          );
        })}
        <div style={{
          display: "grid", gridTemplateColumns: "1fr auto",
          padding: "6px 0", borderTop: `1px solid ${rule}`,
          fontFamily: SC_BODY, fontSize: 11, color: dim,
        }}>
          <div>Extras · b {team.extras.b} · lb {team.extras.lb} · nb {team.extras.nb} · wd {team.extras.wd}</div>
          <div style={{ fontWeight: 700, color: ink }}>{team.extras.total}</div>
        </div>
      </div>

      {/* Bowling */}
      <div style={{ padding: "6px 20px 14px", marginTop: "auto" }}>
        <div style={{
          display: "grid", gridTemplateColumns: "1fr 42px 38px 42px 38px 50px",
          gap: 10, alignItems: "baseline", marginBottom: 4,
          paddingTop: 8, paddingBottom: 4, borderTop: `1px solid ${rule}`, borderBottom: `1px solid ${rule}`,
        }}>
          <div style={{ fontFamily: SC_BODY, fontSize: 10, letterSpacing: 2, color: dim, fontWeight: 600 }}>
            {side === "home" ? `${m.away.short} BOWLING` : `${m.home.short} BOWLING`}
          </div>
          <div style={{ textAlign: "right", fontFamily: SC_BODY, fontSize: 10, letterSpacing: 1.5, color: dimmer, fontWeight: 500 }}>O</div>
          <div style={{ textAlign: "right", fontFamily: SC_BODY, fontSize: 10, letterSpacing: 1.5, color: dimmer, fontWeight: 500 }}>M</div>
          <div style={{ textAlign: "right", fontFamily: SC_BODY, fontSize: 10, letterSpacing: 1.5, color: dimmer, fontWeight: 500 }}>R</div>
          <div style={{ textAlign: "right", fontFamily: SC_BODY, fontSize: 10, letterSpacing: 1.5, color: dimmer, fontWeight: 500 }}>W</div>
          <div style={{ textAlign: "right", fontFamily: SC_BODY, fontSize: 10, letterSpacing: 1.5, color: dimmer, fontWeight: 500 }}>ECON</div>
        </div>
        {team.bowling.map((p, i) => (
          <div key={i} style={{
            display: "grid", gridTemplateColumns: "1fr 42px 38px 42px 38px 50px",
            gap: 10, padding: "5px 0", alignItems: "baseline",
            borderBottom: i < team.bowling.length - 1 ? `1px solid ${rule}` : "none",
          }}>
            <div style={{ fontFamily: SC_BODY, fontSize: 14, fontWeight: 600, color: ink, display: "flex", alignItems: "baseline", gap: 6 }}>
              <span style={{ color: dim, fontSize: 12, fontWeight: 400 }}>{p.first}</span>
              <span>{p.last}</span>
            </div>
            <div style={{ textAlign: "right", fontFamily: SC_MONO, fontSize: 11, color: dim }}>{p.o}</div>
            <div style={{ textAlign: "right", fontFamily: SC_MONO, fontSize: 11, color: dim }}>{p.m}</div>
            <div style={{ textAlign: "right", fontFamily: SC_MONO, fontSize: 11, color: dim }}>{p.r}</div>
            <div style={{ textAlign: "right", fontFamily: SC_BODY, fontSize: 16, fontWeight: 700, color: p.w > 0 ? accent : ink, lineHeight: 1 }}>{p.w}</div>
            <div style={{ textAlign: "right", fontFamily: SC_MONO, fontSize: 11, color: dim }}>{p.econ.toFixed(2)}</div>
          </div>
        ))}
      </div>
    </Card>
  );

  return (
    <div style={{
      width: 1920, height: 1080, position: "relative", overflow: "hidden",
      background: bg, color: ink, fontFamily: SC_BODY,
    }}>
      {/* Header card */}
      <div style={{ padding: "20px 32px 12px" }}>
        <Card style={{ padding: "16px 24px", display: "grid", gridTemplateColumns: "1.4fr 1fr auto", alignItems: "center", gap: 28 }}>
          <div>
            <div style={{ fontFamily: SC_BODY, fontSize: 11, letterSpacing: 2, color: dim, fontWeight: 600 }}>
              {m.meta.competition} · {m.meta.round} · {m.meta.format}
            </div>
            <div style={{
              fontFamily: SC_FONT, fontSize: 42, letterSpacing: 0.5, lineHeight: 1.02,
              color: ink, marginTop: 4,
            }}>{m.meta.result}</div>
            <div style={{ fontFamily: SC_BODY, fontSize: 13, color: dim, marginTop: 4 }}>
              {m.meta.date} · {m.meta.venue}
            </div>
          </div>
          <div style={{
            display: "grid", gridTemplateColumns: "auto 1fr", gap: "3px 14px",
            fontFamily: SC_BODY, fontSize: 12, paddingLeft: 24, borderLeft: `1px solid ${rule}`,
          }}>
            <span style={{ color: dim, fontWeight: 600, letterSpacing: 1 }}>TOSS</span>
            <span style={{ color: ink }}>{m.meta.toss}</span>
            <span style={{ color: dim, fontWeight: 600, letterSpacing: 1 }}>FORMAT</span>
            <span style={{ color: ink }}>{m.meta.format} · {m.meta.overs} overs/side</span>
            <span style={{ color: dim, fontWeight: 600, letterSpacing: 1 }}>SERIES</span>
            <span style={{ color: ink }}>{m.meta.series}</span>
          </div>
          <div style={{
            display: "flex", alignItems: "center", gap: 12,
            padding: "10px 16px", borderRadius: 12,
            background: `${win}14`, border: `1px solid ${win}55`,
          }}>
            <div style={{ fontSize: 22, lineHeight: 1, color: win }}>★</div>
            <div>
              <div style={{ fontFamily: SC_BODY, fontSize: 10, letterSpacing: 2, color: win, fontWeight: 700 }}>PLAYER OF THE MATCH</div>
              <div style={{ fontFamily: SC_FONT, fontSize: 22, color: ink, letterSpacing: 0.5, lineHeight: 1, marginTop: 4 }}>
                {m.meta.motm.first.toUpperCase()} {m.meta.motm.last}
              </div>
              <div style={{ fontFamily: SC_BODY, fontSize: 11, color: dim, marginTop: 4 }}>{m.meta.motm.line}</div>
            </div>
          </div>
        </Card>
      </div>

      {/* Two innings cards */}
      <div style={{
        padding: "0 32px",
        display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16,
        height: 820,
      }}>
        <TeamCard team={m.home} accentC={m.home.color} side="home" />
        <TeamCard team={m.away} accentC={m.away.color} side="away" />
      </div>

      <ScSponsorFooter bg={card} ink={ink} dim={dim} dimmer={dimmer} rule={rule} />
    </div>
  );
}

Object.assign(window, { SC1_Broadcast, SC2_Brutalist, SC3_Dashboard });
