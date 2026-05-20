// Templates 4–6: Probable XI batting order, Brutalist typography, Diagonal poster
// All artboards are 1080×1080.

const ROLE_LABEL = { BAT: "BAT", BOWL: "BOWL", AR: "AR", WK: "WK" };
const ROLE_COLOR_BG = (palette, role) => {
  switch (role) {
    case "BAT":return palette.accent;
    case "BOWL":return palette.ink + "1a";
    case "AR":return palette.secondary;
    case "WK":return palette.ink + "33";
    default:return palette.ink + "1a";
  }
};
const ROLE_COLOR_INK = (palette, role) => {
  switch (role) {
    case "BAT":return palette.primary;
    case "BOWL":return palette.ink;
    case "AR":return palette.accent;
    case "WK":return palette.ink;
    default:return palette.ink;
  }
};

// ─────────────────────────────────────────────────────────────
// TEMPLATE 4 — Probable XI batting order with role-coded rows
// Tactical scorecard style: structured grid, role pill, position #.
// Supports up to 13 players (XI + 12th + 13th man).
// ─────────────────────────────────────────────────────────────
function T4_BattingOrder({ team, opponent, match, players, palette }) {
  const P = players.slice(0, 13);
  return (
    <div style={{
      width: 1080, height: 1080, position: "relative", overflow: "hidden",
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif"
    }}>
      <Stripes color={palette.ink} opacity={0.04} gap={40} angle={0} />
      <Halftone color={palette.ink} opacity={0.04} size={11} />

      {/* Top bar */}
      <div style={{
        position: "relative", padding: "32px 56px 18px",
        borderBottom: `3px solid ${palette.accent}`,
        display: "flex", justifyContent: "space-between", alignItems: "center"
      }}>
        <div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 13, letterSpacing: 2,
            color: palette.accent, marginBottom: 4
          }}>// PROBABLE XI</div>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 68, lineHeight: 0.85,
            color: palette.ink, letterSpacing: -1
          }}>BATTING ORDER</div>
        </div>
        <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={84} shape="shield" />
      </div>

      {/* Match info strip — promoted to two lines, bigger type */}
      <div style={{
        padding: "16px 56px",
        background: palette.secondary,
        borderBottom: `1px solid ${palette.ink}22`,
        display: "flex", justifyContent: "space-between", alignItems: "center"
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={44} shape="shield" />
            <div style={{ fontFamily: "'Anton', sans-serif", fontSize: 28, letterSpacing: 1, color: palette.accent }}>v</div>
            <ClubLogo src={opponent.logo} monogram={opponent.monogram} color={palette.ink} size={44} shape="shield" />
          </div>
          <div style={{
            display: "flex", flexDirection: "column", gap: 1,
            fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 1.5,
            color: palette.ink, opacity: 0.78
          }}>
            <span>{match.competition} · {match.round}</span>
            <span style={{ opacity: 0.7 }}>{match.venue.toUpperCase()}</span>
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 28, letterSpacing: 1, lineHeight: 1,
            color: palette.accent
          }}>{match.date}</div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.5,
            color: palette.ink, opacity: 0.7, marginTop: 4
          }}>{match.time}</div>
        </div>
      </div>

      {/* Order rows */}
      <div style={{
        padding: "16px 56px 0",
        display: "flex", flexDirection: "column", gap: 4
      }}>
        {P.map((p, i) => {
          const chip = p.captain ? "C" : p.viceCaptain ? "VC" : p.keeper ? "WK" : null;
          const isRole = p.role || "BAT";
          return (
            <div key={i} style={{
              display: "grid",
              gridTemplateColumns: "60px 1fr auto",
              alignItems: "center",
              gap: 14,
              padding: "8px 16px",
              background: i % 2 === 0 ? `${palette.ink}08` : "transparent",
              borderLeft: `3px solid ${i === 10 ? palette.accent : "transparent"}` // mark 12th man boundary
            }}>
              {/* Position number */}
              <div style={{
                fontFamily: "'Anton', sans-serif", fontSize: 40, color: palette.accent,
                lineHeight: 1, textAlign: "center"
              }}>{i + 1}</div>
              {/* Name + C/VC/WK chip inline */}
              <div style={{
                display: "flex", alignItems: "center", gap: 10,
                whiteSpace: "nowrap", overflow: "hidden"
              }}>
                <span style={{
                  fontFamily: "'Anton', sans-serif", fontSize: 22,
                  color: palette.ink, opacity: 0.62, fontWeight: 300, letterSpacing: 0.5
                }}>{p.first.toUpperCase()}</span>
                <span style={{
                  fontFamily: "'Anton', sans-serif", fontSize: 30, letterSpacing: 0.5,
                  color: palette.ink, lineHeight: 1
                }}>{p.last}</span>
                {chip && <RoleChip kind={chip} accent={palette.accent} ink={palette.primary} />}
              </div>
              {/* Role pill — unified style for all roles, right-aligned column */}
              <div style={{
                width: 64, textAlign: "center",
                padding: "5px 0",
                background: "transparent",
                border: `1.5px solid ${palette.ink}55`,
                color: palette.ink,
                fontFamily: "'Anton', sans-serif", fontSize: 14, letterSpacing: 1.5,
                lineHeight: 1, borderRadius: 2
              }}>{ROLE_LABEL[isRole]}</div>
            </div>);

        })}
      </div>

      {/* Footer */}
      <div style={{
        position: "absolute", left: 56, right: 56, bottom: 22,
        display: "flex", justifyContent: "space-between", alignItems: "center",
        paddingTop: 12, borderTop: `1px solid ${palette.ink}22`
      }}>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.5,
          color: palette.ink, opacity: 0.5
        }}>{(team.fullName || team.name).toUpperCase()} · {match.season}</div>
        <div style={{
          padding: "6px 14px", border: `1.5px solid ${palette.ink}55`,
          fontFamily: "'Anton', sans-serif", fontSize: 11, letterSpacing: 2,
          color: palette.ink, opacity: 0.7
        }}>SPONSOR LOGO</div>
      </div>

      <GrainSVG opacity={0.25} id="g4" />
    </div>);

}

// ─────────────────────────────────────────────────────────────
// TEMPLATE 5 — Brutalist / Typographic
// Names AS the design: each one a full-width condensed line.
// ─────────────────────────────────────────────────────────────
function T5_Brutalist({ team, opponent, match, players, palette }) {
  const P = players.slice(0, 11);
  return (
    <div style={{
      width: 1080, height: 1080, position: "relative", overflow: "hidden",
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif"
    }}>
      <Stripes color={palette.ink} opacity={0.06} gap={6} angle={0} />

      {/* Background graphic layer: oversized wordmark + halftone + diagonal slabs */}
      <div style={{
        position: "absolute", left: 0, right: 0, top: 320, textAlign: "center",
        fontFamily: "'Anton', sans-serif", fontSize: 520, lineHeight: 0.8,
        color: palette.ink, opacity: 0.05, letterSpacing: -10, userSelect: "none"
      }}>XI</div>
      <Halftone color={palette.ink} opacity={0.08} size={14} angle={-20} />
      <div style={{
        position: "absolute", left: -100, top: 360, width: 1300, height: 100,
        background: palette.accent, opacity: 0.08, transform: "rotate(-3deg)"
      }} />
      <div style={{
        position: "absolute", left: -120, top: 700, width: 1300, height: 60,
        background: palette.accent, opacity: 0.1, transform: "rotate(2deg)"
      }} />
      <svg style={{ position: "absolute", right: -180, top: 220, width: 520, height: 520, opacity: 0.08 }}>
        <circle cx="260" cy="260" r="240" fill="none" stroke={palette.accent} strokeWidth="3" />
        <circle cx="260" cy="260" r="180" fill="none" stroke={palette.accent} strokeWidth="3" />
      </svg>

      {/* Header band */}
      <div style={{
        background: palette.accent, color: palette.primary,
        padding: "24px 44px", display: "flex", justifyContent: "space-between", alignItems: "center",
        position: "relative", zIndex: 2
      }}>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 52, letterSpacing: 2, lineHeight: 1
        }}>{team.name} XI</div>
        <div style={{ textAlign: "right" }}>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 30, letterSpacing: 1.5, lineHeight: 1
          }}>VS {opponent.name}</div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 2, marginTop: 6
          }}>{match.round} · {match.date}</div>
        </div>
      </div>

      {/* Names — each row a giant condensed line */}
      <div style={{
        padding: "32px 44px 0", display: "flex", flexDirection: "column", gap: 0
      }}>
        {P.map((p, i) => {
          const chip = p.captain ? "C" : p.viceCaptain ? "VC" : p.keeper ? "WK" : null;
          return (
            <div key={i} style={{
              display: "grid",
              gridTemplateColumns: "56px 1fr 70px 60px",
              alignItems: "center",
              gap: 14,
              borderBottom: `1px solid ${palette.ink}1a`,
              padding: "4px 0"
            }}>
              <div style={{
                fontFamily: "'JetBrains Mono', monospace", fontSize: 14, letterSpacing: 1.5,
                color: palette.accent, opacity: 0.9
              }}>{String(i + 1).padStart(2, "0")}</div>
              <div style={{
                display: "flex", alignItems: "baseline", gap: 12, lineHeight: 0.95,
                overflow: "hidden"
              }}>
                <span style={{
                  fontFamily: "'Anton', sans-serif", fontSize: 30,
                  color: palette.ink, opacity: 0.5, letterSpacing: 0.5,
                  whiteSpace: "nowrap"
                }}>{p.first.toUpperCase()}</span>
                <span style={{
                  fontFamily: "'Anton', sans-serif", fontSize: 64,
                  color: palette.ink, letterSpacing: -1, whiteSpace: "nowrap", lineHeight: 0.95
                }}>{p.last}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                {chip && <RoleChip kind={chip} accent={palette.accent} ink={palette.primary} />}
              </div>
              <div style={{
                fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.5,
                color: palette.ink, opacity: 0.5, textAlign: "right"
              }}>{p.role}</div>
            </div>);

        })}
      </div>

      {/* Footer band */}
      <div style={{
        position: "absolute", left: 0, right: 0, bottom: 0,
        background: palette.secondary,
        padding: "22px 44px", display: "grid", gridTemplateColumns: "1fr 1fr 1fr", alignItems: "center",
        borderTop: `3px solid ${palette.accent}`, zIndex: 2
      }}>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 30, letterSpacing: 2,
          color: palette.ink, lineHeight: 1, textAlign: "left"
        }}>STARTING XI</div>
        <div style={{ textAlign: "center" }}>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 22, letterSpacing: 2,
            color: palette.accent, lineHeight: 1
          }}>{match.venue.toUpperCase()}</div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 2,
            color: palette.ink, opacity: 0.85, marginTop: 6
          }}>{match.competition} · {match.time}</div>
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <div style={{
            padding: "8px 14px", border: `1.5px solid ${palette.ink}55`,
            fontFamily: "'Anton', sans-serif", fontSize: 13, letterSpacing: 2,
            color: palette.ink, opacity: 0.8
          }}>SPONSOR</div>
        </div>
      </div>

      <GrainSVG opacity={0.32} id="g5" />
    </div>);

}

// ─────────────────────────────────────────────────────────────
// TEMPLATE 6 — Diagonal poster / gritty match-day
// Diagonal accent strip slicing across the canvas, name stack right-aligned.
// ─────────────────────────────────────────────────────────────
function T6_Diagonal({ team, opponent, match, players, palette }) {
  const P = players.slice(0, 11);
  return (
    <div style={{
      width: 1080, height: 1080, position: "relative", overflow: "hidden",
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif"
    }}>
      <Halftone color={palette.ink} opacity={0.07} size={10} />

      {/* Huge diagonal accent slab */}
      <div style={{
        position: "absolute", left: -200, top: 0, width: 1500, height: 220,
        background: palette.accent,
        transform: "rotate(-8deg)", transformOrigin: "top left", top: -40, padding: "100px 0px 0px"
      }}>
        <div style={{
          padding: "70px 240px 0", color: palette.primary,
          fontFamily: "'Anton', sans-serif", fontSize: 100, lineHeight: 0.9,
          letterSpacing: -1, transform: "rotate(0deg)",
          display: "flex", alignItems: "center", gap: 28
        }}>
          1ST XI
          <span style={{
            fontSize: 22, letterSpacing: 3, opacity: 0.85, fontFamily: "'Anton', sans-serif"
          }}>· {match.date.toUpperCase()} ·</span>
          <span style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <ClubLogo src={team.logo} monogram={team.monogram} color={palette.primary} size={70} shape="shield" />
            <span style={{ fontFamily: "'Anton', sans-serif", fontSize: 56, letterSpacing: 1, lineHeight: 1 }}>v</span>
            <ClubLogo src={opponent.logo} monogram={opponent.monogram} color={palette.primary} size={70} shape="shield" />
          </span>
        </div>
      </div>

      {/* Center hero block — club logo left, big featured player cutout right */}
      <div style={{
        position: "absolute", left: 56, top: 220, right: 56, height: 420,
        display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 24
      }}>
        {/* Left — club logo + club name */}
        <div style={{ flexShrink: 0, maxWidth: 320, paddingBottom: 24 }}>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 14, letterSpacing: 2,
            color: palette.accent, marginBottom: 14
          }}>// 1ST XI</div>
          <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={260} shape="shield" />
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 26, letterSpacing: 1,
            color: palette.ink, opacity: 0.85, marginTop: 14
          }}>{(team.fullName || team.name).toUpperCase()}</div>
        </div>

        {/* Right — featured player cutout (bigger, hugs the right edge) */}
        <div style={{
          flex: 1, height: 500, display: "grid", placeItems: "end center",
          position: "relative", overflow: "visible"
        }}>
          {(() => {
            const featured = featuredOf(players);
            const hasHead = !!(featured && featured.headshot);
            const src = hasHead ? featured.headshot : team.logo;
            return (
              <img src={src} alt={featured?.last || team.short}
              style={{ ...{
                  height: hasHead ? 520 : 280,
                  width: "auto", objectFit: "contain", objectPosition: "bottom",
                  filter: `drop-shadow(0 20px 40px ${palette.primary}cc)`, padding: "0px"
                }, height: "486px", width: "324px", margin: "0px 0px 200px" }} />);

          })()}
        </div>
      </div>

      {/* Two-column name list */}
      <div style={{
        position: "absolute", left: 56, right: 56, top: 620,
        display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8
      }}>
        {P.map((p, i) => {
          const chip = p.captain ? "C" : p.viceCaptain ? "VC" : p.keeper ? "WK" : null;
          return (
            <div key={i} style={{
              display: "flex", alignItems: "center", gap: 12, padding: "6px 0",
              borderBottom: `1px solid ${palette.ink}1a`
            }}>
              <div style={{
                fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 1.5,
                color: palette.accent, width: 26
              }}>{String(i + 1).padStart(2, "0")}</div>
              <div style={{
                fontFamily: "'Anton', sans-serif", fontSize: 26, letterSpacing: 0.5,
                color: palette.ink, lineHeight: 1.1, flex: 1,
                whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis"
              }}>
                <span style={{ opacity: 0.55, fontWeight: 300 }}>{p.first.toUpperCase()}</span>{" "}
                <span>{p.last}</span>
              </div>
              {chip && <RoleChip kind={chip} accent={palette.accent} ink={palette.primary} />}
            </div>);

        })}
      </div>

      {/* Bottom diagonal strip with match info — cleaner three-up summary */}
      <div style={{
        position: "absolute", left: -200, bottom: -40, width: 1500, height: 130,
        background: palette.secondary, transform: "rotate(-4deg)", transformOrigin: "bottom left",
        display: "grid", gridTemplateColumns: "1fr 1fr 1fr", alignItems: "center", padding: "0 240px"
      }}>
        <div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: 1.5,
            color: palette.accent, opacity: 0.85
          }}>VENUE</div>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 22, letterSpacing: 1.5, color: palette.ink, marginTop: 2
          }}>{match.venue.toUpperCase()}</div>
        </div>
        <div style={{ textAlign: "center" }}>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: 1.5,
            color: palette.accent, opacity: 0.85
          }}>{match.competition} · {match.round}</div>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 24, letterSpacing: 1.5, color: palette.ink, marginTop: 2
          }}>{match.date.toUpperCase()} · {match.time}</div>
        </div>
        <div style={{
          justifySelf: "end",
          padding: "6px 14px", border: `1.5px solid ${palette.ink}55`,
          fontFamily: "'Anton', sans-serif", fontSize: 12, letterSpacing: 2,
          color: palette.ink, opacity: 0.85
        }}>SPONSOR</div>
      </div>

      <GrainSVG opacity={0.35} id="g6" />
    </div>);

}

Object.assign(window, { T4_BattingOrder, T5_Brutalist, T6_Diagonal });