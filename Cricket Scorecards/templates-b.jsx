// Templates 4–6: Probable XI batting order, Brutalist typography, Diagonal poster
// All artboards are 1080×1080.

const ROLE_LABEL = { BAT: "BATTER", BOWL: "BOWLER", AR: "ALL-ROUNDER", WK: "WICKET-KEEPER" };
const ROLE_GLYPH = { BAT: "B", BOWL: "↻", AR: "★", WK: "▼" };

// ─────────────────────────────────────────────────────────────
// TEMPLATE 4 — Probable XI batting order with role-coded rows
// Tactical scorecard style: structured grid, role pill, position #.
// ─────────────────────────────────────────────────────────────
function T4_BattingOrder({ team, opponent, match, players, palette }) {
  const P = players.slice(0, 11);
  return (
    <div style={{
      width: 1080, height: 1080, position: "relative", overflow: "hidden",
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Stripes color={palette.ink} opacity={0.04} gap={40} angle={0} />

      {/* Top bar */}
      <div style={{
        position: "relative", padding: "40px 56px 28px",
        borderBottom: `3px solid ${palette.accent}`,
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 2,
            color: palette.accent, marginBottom: 6,
          }}>// PROBABLE XI</div>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 84, lineHeight: 0.85,
            color: palette.ink, letterSpacing: -1,
          }}>BATTING ORDER</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={84} shape="shield" />
        </div>
      </div>

      {/* Match info strip */}
      <div style={{
        padding: "14px 56px", display: "flex", justifyContent: "space-between",
        fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 1.5,
        color: palette.ink, opacity: 0.75,
        background: palette.secondary,
      }}>
        <span>{team.short} vs {opponent.short}</span>
        <span>{match.competition}</span>
        <span>{match.round}</span>
        <span>{match.date}</span>
        <span>{match.venue}</span>
      </div>

      {/* Order rows */}
      <div style={{
        padding: "20px 56px 0",
        display: "flex", flexDirection: "column", gap: 6,
      }}>
        {P.map((p, i) => {
          const chip = p.captain ? "C" : p.viceCaptain ? "VC" : p.keeper ? "WK" : null;
          const isRole = p.role || "BAT";
          return (
            <div key={i} style={{
              display: "grid",
              gridTemplateColumns: "70px 60px 1fr 220px 80px",
              alignItems: "center",
              gap: 14,
              padding: "10px 18px",
              background: i % 2 === 0 ? `${palette.ink}06` : "transparent",
              border: `1px solid ${palette.ink}10`,
            }}>
              {/* Position number */}
              <div style={{
                fontFamily: "'Anton', sans-serif", fontSize: 44, color: palette.accent,
                lineHeight: 1, textAlign: "center",
              }}>{i + 1}</div>
              {/* Role glyph */}
              <div style={{
                width: 50, height: 50, borderRadius: "50%",
                background: palette.ink + "0c",
                border: `1.5px solid ${palette.accent}`,
                display: "grid", placeItems: "center",
                fontFamily: "'Anton', sans-serif", fontSize: 24, color: palette.accent,
              }}>{ROLE_GLYPH[isRole]}</div>
              {/* Name */}
              <div>
                <div style={{
                  fontFamily: "'Anton', sans-serif", fontSize: 28, letterSpacing: 0.5,
                  color: palette.ink, lineHeight: 1.05,
                }}>
                  <span style={{ opacity: 0.65, fontWeight: 300 }}>{p.first.toUpperCase()}</span>{" "}
                  <span>{p.last}</span>
                </div>
                <div style={{
                  fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: 1.5,
                  color: palette.ink, opacity: 0.5, marginTop: 2,
                }}>{p.roleLong?.toUpperCase()}</div>
              </div>
              {/* Role text label */}
              <div style={{
                fontFamily: "'Anton', sans-serif", fontSize: 14, letterSpacing: 2,
                color: palette.ink, opacity: 0.6, textAlign: "right",
              }}>{ROLE_LABEL[isRole]}</div>
              {/* Chip */}
              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                {chip && <RoleChip kind={chip} accent={palette.accent} ink={palette.primary} />}
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div style={{
        position: "absolute", left: 56, right: 56, bottom: 28,
        display: "flex", justifyContent: "space-between", alignItems: "center",
        paddingTop: 14, borderTop: `1px solid ${palette.ink}22`,
      }}>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.5,
          color: palette.ink, opacity: 0.5,
        }}>{team.name} · {match.season}</div>
        <div style={{
          padding: "6px 14px", border: `1.5px solid ${palette.ink}55`,
          fontFamily: "'Anton', sans-serif", fontSize: 11, letterSpacing: 2,
          color: palette.ink, opacity: 0.7,
        }}>SPONSOR LOGO</div>
      </div>

      <GrainSVG opacity={0.25} id="g4" />
    </div>
  );
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
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Stripes color={palette.ink} opacity={0.06} gap={6} angle={0} />

      {/* Header band */}
      <div style={{
        background: palette.accent, color: palette.primary,
        padding: "18px 40px", display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 36, letterSpacing: 2,
        }}>{team.name} XI</div>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 2,
        }}>VS {opponent.name} · {match.date}</div>
      </div>

      {/* Names — each row a giant condensed line */}
      <div style={{
        padding: "26px 36px 0", display: "flex", flexDirection: "column", gap: 0,
      }}>
        {P.map((p, i) => {
          const chip = p.captain ? "C" : p.viceCaptain ? "VC" : p.keeper ? "WK" : null;
          return (
            <div key={i} style={{
              display: "grid",
              gridTemplateColumns: "56px 1fr auto",
              alignItems: "baseline",
              gap: 12,
              borderBottom: `1px solid ${palette.ink}1a`,
              padding: "2px 0",
            }}>
              <div style={{
                fontFamily: "'JetBrains Mono', monospace", fontSize: 14, letterSpacing: 1.5,
                color: palette.accent, opacity: 0.9,
              }}>{String(i + 1).padStart(2, "0")}</div>
              <div style={{
                display: "flex", alignItems: "baseline", gap: 12, lineHeight: 0.95,
                overflow: "hidden",
              }}>
                <span style={{
                  fontFamily: "'Anton', sans-serif", fontSize: 30,
                  color: palette.ink, opacity: 0.5, letterSpacing: 0.5,
                  whiteSpace: "nowrap",
                }}>{p.first.toUpperCase()}</span>
                <span style={{
                  fontFamily: "'Anton', sans-serif", fontSize: 68,
                  color: palette.ink, letterSpacing: -1, whiteSpace: "nowrap", lineHeight: 0.95,
                }}>{p.last}</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                {chip && <RoleChip kind={chip} accent={palette.accent} ink={palette.primary} />}
                <div style={{
                  fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: 1.5,
                  color: palette.ink, opacity: 0.45, minWidth: 38, textAlign: "right",
                }}>{p.role}</div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer band */}
      <div style={{
        position: "absolute", left: 0, right: 0, bottom: 0,
        background: palette.secondary,
        padding: "18px 40px", display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 22, letterSpacing: 2,
          color: palette.ink,
        }}>STARTING XI</div>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.5,
          color: palette.ink, opacity: 0.8,
        }}>{match.venue.toUpperCase()} · {match.time}</div>
        <div style={{
          padding: "6px 12px", border: `1.5px solid ${palette.ink}55`,
          fontFamily: "'Anton', sans-serif", fontSize: 11, letterSpacing: 2,
          color: palette.ink, opacity: 0.8,
        }}>SPONSOR</div>
      </div>

      <GrainSVG opacity={0.32} id="g5" />
    </div>
  );
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
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Halftone color={palette.ink} opacity={0.07} size={10} />

      {/* Huge diagonal accent slab */}
      <div style={{
        position: "absolute", left: -200, top: 0, width: 1500, height: 220,
        background: palette.accent,
        transform: "rotate(-8deg)", transformOrigin: "top left", top: -40,
      }}>
        <div style={{
          padding: "70px 240px 0", color: palette.primary,
          fontFamily: "'Anton', sans-serif", fontSize: 100, lineHeight: 0.9,
          letterSpacing: -1, transform: "rotate(0deg)",
          display: "flex", alignItems: "center", gap: 28,
        }}>
          MATCH DAY
          <span style={{
            fontSize: 22, letterSpacing: 3, opacity: 0.85, fontFamily: "'Anton', sans-serif",
          }}>· {match.date.toUpperCase()} ·</span>
          <span style={{ fontFamily: "'Anton', sans-serif" }}>{team.short} v {opponent.short}</span>
        </div>
      </div>

      {/* Center hero block */}
      <div style={{
        position: "absolute", left: 56, top: 260, right: 56,
        display: "flex", justifyContent: "space-between", alignItems: "flex-start",
      }}>
        <div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 13, letterSpacing: 2,
            color: palette.accent, marginBottom: 6,
          }}>// THE STARTING XI</div>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 220, lineHeight: 0.85,
            color: palette.ink, letterSpacing: -4,
          }}>{team.short}</div>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 36, letterSpacing: 1,
            color: palette.ink, opacity: 0.85, marginTop: 4,
          }}>{team.name}</div>
        </div>
        <ClubLogo src={team.logo} monogram={team.monogram} color={palette.accent} size={180} shape="shield" />
      </div>

      {/* Two-column name list */}
      <div style={{
        position: "absolute", left: 56, right: 56, top: 620,
        display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8,
      }}>
        {P.map((p, i) => {
          const chip = p.captain ? "C" : p.viceCaptain ? "VC" : p.keeper ? "WK" : null;
          return (
            <div key={i} style={{
              display: "flex", alignItems: "center", gap: 12, padding: "6px 0",
              borderBottom: `1px solid ${palette.ink}1a`,
            }}>
              <div style={{
                fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 1.5,
                color: palette.accent, width: 26,
              }}>{String(i + 1).padStart(2, "0")}</div>
              <div style={{
                fontFamily: "'Anton', sans-serif", fontSize: 26, letterSpacing: 0.5,
                color: palette.ink, lineHeight: 1.1, flex: 1,
                whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
              }}>
                <span style={{ opacity: 0.55, fontWeight: 300 }}>{p.first.toUpperCase()}</span>{" "}
                <span>{p.last}</span>
              </div>
              {chip && <RoleChip kind={chip} accent={palette.accent} ink={palette.primary} />}
            </div>
          );
        })}
      </div>

      {/* Bottom diagonal strip with match info */}
      <div style={{
        position: "absolute", left: -200, bottom: -40, width: 1500, height: 130,
        background: palette.secondary, transform: "rotate(-4deg)", transformOrigin: "bottom left",
        display: "flex", alignItems: "center", padding: "0 240px",
        justifyContent: "space-between",
      }}>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 22, letterSpacing: 2, color: palette.ink,
        }}>{match.venue.toUpperCase()}</div>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 13, letterSpacing: 2, color: palette.accent,
        }}>{match.competition} · {match.round} · {match.time}</div>
        <div style={{
          padding: "6px 14px", border: `1.5px solid ${palette.ink}55`,
          fontFamily: "'Anton', sans-serif", fontSize: 12, letterSpacing: 2,
          color: palette.ink, opacity: 0.85,
        }}>SPONSOR</div>
      </div>

      <GrainSVG opacity={0.35} id="g6" />
    </div>
  );
}

Object.assign(window, { T4_BattingOrder, T5_Brutalist, T6_Diagonal });
