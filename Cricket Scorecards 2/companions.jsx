// Companion templates (1080×1080) — single-moment posts that go with the lineup set.

// ─────────────────────────────────────────────────────────────
// COMPANION 1 — Generic Announcement
// Use for captain appointments, milestones, debuts, retirements, awards, etc.
// Data: { announcement: { kind, headline, subheadline, player }, team, opponent, match, palette }
//   kind          — short eyebrow chip text (e.g. "APPOINTMENT", "MILESTONE", "AWARD")
//   headline      — large caps line above the player name
//   subheadline   — small caps line below the player name
//   player        — { first, last, role, roleLong, headshot? }
// ─────────────────────────────────────────────────────────────
function C1_CaptainAnnounce({ announcement, team, opponent, match, palette, player: legacyPlayer }) {
  // Support old call-signature (just `player`) for back-compat.
  const a = announcement || {
    kind: "ANNOUNCEMENT",
    headline: "NAMED",
    subheadline: "",
    player: legacyPlayer,
  };
  const player = a.player || legacyPlayer;
  const hasHead = !!(player && player.headshot);

  return (
    <div style={{
      width: 1080, height: 1080, position: "relative", overflow: "hidden",
      background: `linear-gradient(160deg, ${palette.primary} 0%, ${palette.secondary} 100%)`,
      color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Halftone color={palette.ink} opacity={0.07} size={11} />
      <Stripes color={palette.accent} opacity={0.04} gap={28} angle={-22} />

      {/* Giant background headline as type-art */}
      <div style={{
        position: "absolute", left: -40, top: -30,
        fontFamily: "'Anton', sans-serif", fontSize: 360, lineHeight: 0.82,
        color: palette.accent, opacity: 0.09, letterSpacing: -8, userSelect: "none",
        whiteSpace: "nowrap",
      }}>{(a.kind || "ANNOUNCEMENT")}</div>

      {/* Player */}
      <div style={{
        position: "absolute", left: 60, top: 90, right: 60, bottom: 200,
        display: "grid", placeItems: "end center", overflow: "hidden",
      }}>
        {hasHead ? (
          <img src={player.headshot} alt={player.last}
            style={{
              height: 820, width: "auto", objectFit: "contain", objectPosition: "bottom",
              filter: `drop-shadow(0 40px 80px ${palette.primary}ee)`,
            }} />
        ) : (
          <img src={team.logo} alt={team.short}
            style={{ width: 460, height: 460, objectFit: "contain", marginBottom: 60 }} />
        )}
      </div>

      {/* Top bar */}
      <div style={{
        position: "absolute", left: 0, right: 0, top: 0,
        padding: "36px 40px", display: "flex", justifyContent: "space-between", alignItems: "flex-start", zIndex: 3,
      }}>
        <div>
          <div style={{
            display: "inline-block", padding: "7px 14px",
            background: palette.accent, color: palette.primary,
            fontFamily: "'Anton', sans-serif", fontSize: 22, letterSpacing: 3,
          }}>{(a.kind || "ANNOUNCEMENT").toUpperCase()}</div>
        </div>
        <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={92} shape="shield" />
      </div>

      {/* Name lockup */}
      <div style={{
        position: "absolute", left: 40, bottom: 130, right: 40, zIndex: 3,
      }}>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 56, letterSpacing: 3,
          color: palette.accent, marginBottom: 8, lineHeight: 1,
        }}>{(a.headline || "").toUpperCase()}</div>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 64, letterSpacing: 1,
          color: palette.ink, opacity: 0.78, lineHeight: 1,
        }}>{(player?.first || "").toUpperCase()}</div>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 200, letterSpacing: -3,
          color: palette.ink, lineHeight: 0.84, marginTop: -6,
        }}>{player?.last || "—"}</div>
        {a.subheadline && (
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 28, letterSpacing: 2,
            color: palette.accent, marginTop: 10,
          }}>{a.subheadline.toUpperCase()}</div>
        )}
      </div>

      {/* Footer */}
      <div style={{
        position: "absolute", left: 0, right: 0, bottom: 0,
        padding: "16px 40px",
        background: palette.primary, borderTop: `2px solid ${palette.accent}`,
        display: "flex", justifyContent: "space-between", alignItems: "center", zIndex: 3,
      }}>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 22, letterSpacing: 2, color: palette.ink,
        }}>{(team.fullName || team.name).toUpperCase()}</div>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 1.5,
          color: palette.ink, opacity: 0.65,
        }}>{match.competition} · {match.season}</div>
        <div style={{
          padding: "6px 12px", border: `1.5px solid ${palette.ink}55`,
          fontFamily: "'Anton', sans-serif", fontSize: 11, letterSpacing: 2,
          color: palette.ink, opacity: 0.8,
        }}>SPONSOR</div>
      </div>

      <GrainSVG opacity={0.32} id="ca1" />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// COMPANION 2 — Toss
// Data: { toss: { winner: "TEAM" | "OPPONENT", decision: "BAT" | "BOWL" } }
// ─────────────────────────────────────────────────────────────
function C2_TossWon({ toss, team, opponent, match, palette }) {
  const winnerIsOpponent = toss?.winner === "OPPONENT";
  const decision = (toss?.decision || "BAT").toUpperCase();
  const decisionLong = decision === "BAT" ? "BATTING FIRST" : "BOWLING FIRST";

  return (
    <div style={{
      width: 1080, height: 1080, position: "relative", overflow: "hidden",
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Halftone color={palette.ink} opacity={0.07} size={10} />
      <Stripes color={palette.accent} opacity={0.04} gap={24} angle={-20} />

      {/* Big coin element top-right */}
      <div style={{
        position: "absolute", right: -100, top: -100, width: 660, height: 660,
        borderRadius: "50%",
        background: `radial-gradient(circle at 35% 30%, ${palette.accent} 0%, ${palette.accent}dd 50%, ${palette.accent}88 100%)`,
        boxShadow: `inset 0 0 0 14px ${palette.primary}, inset 0 0 0 20px ${palette.accent}`,
      }} />
      <div style={{
        position: "absolute", right: 90, top: 130,
        fontFamily: "'Anton', sans-serif", fontSize: 280, letterSpacing: -4,
        color: palette.primary, lineHeight: 0.85, transform: "rotate(-6deg)",
      }}>TOSS</div>

      {/* Background watermark */}
      <div style={{
        position: "absolute", left: -50, bottom: 180,
        fontFamily: "'Anton', sans-serif", fontSize: 460, lineHeight: 0.8,
        color: palette.ink, opacity: 0.05, letterSpacing: -10, userSelect: "none",
      }}>{decision}</div>

      {/* Top bar */}
      <div style={{
        position: "absolute", left: 0, right: 0, top: 0,
        padding: "32px 40px", display: "flex", justifyContent: "flex-start", alignItems: "center", gap: 14, zIndex: 3,
      }}>
        <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={72} shape="shield" />
        <div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 2,
            color: palette.accent,
          }}>// {match.competition} · {match.round}</div>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 28, letterSpacing: 1.5, marginTop: 2,
            color: palette.ink,
          }}>{team.name} <span style={{ color: palette.accent }}>v</span> {opponent.name}</div>
        </div>
      </div>

      {/* Main lockup — moved up, tighter */}
      <div style={{
        position: "absolute", left: 40, top: 320, right: 40,
      }}>
        <div style={{
          display: "inline-block", padding: "6px 14px",
          background: palette.accent, color: palette.primary,
          fontFamily: "'Anton', sans-serif", fontSize: 20, letterSpacing: 3,
          marginBottom: 12,
        }}>{winnerIsOpponent ? `${opponent.name} WON THE TOSS` : `${team.name} WON THE TOSS`}</div>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 88, letterSpacing: 2,
          color: palette.ink, opacity: 0.55, lineHeight: 1, marginTop: 16,
        }}>{winnerIsOpponent ? "THEY'RE" : "WE'RE"}</div>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 280, letterSpacing: -6,
          color: palette.ink, lineHeight: 0.85, marginTop: -4,
        }}>{decision}</div>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 72, letterSpacing: 3,
          color: palette.accent, lineHeight: 1, marginTop: -8,
        }}>FIRST</div>
      </div>

      {/* Side info — vs row + match details */}
      <div style={{
        position: "absolute", left: 40, right: 40, bottom: 100,
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: "20px 28px",
        background: palette.secondary,
        borderLeft: `4px solid ${palette.accent}`,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={64} shape="shield" />
          <div style={{ fontFamily: "'Anton', sans-serif", fontSize: 30, color: palette.accent }}>VS</div>
          <ClubLogo src={opponent.logo} monogram={opponent.monogram} color={palette.ink} size={64} shape="shield" />
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 30, letterSpacing: 1, color: palette.ink, lineHeight: 1,
          }}>{match.date}</div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 13, letterSpacing: 1.5,
            color: palette.ink, opacity: 0.75, marginTop: 4,
          }}>{match.time} · {match.venue.toUpperCase()}</div>
        </div>
      </div>

      {/* Footer */}
      <div style={{
        position: "absolute", left: 0, right: 0, bottom: 0,
        padding: "16px 40px", background: palette.primary, borderTop: `2px solid ${palette.accent}`,
        display: "flex", justifyContent: "space-between", alignItems: "center", zIndex: 3,
      }}>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 16, letterSpacing: 2, color: palette.ink, opacity: 0.85,
        }}>{(team.fullName || team.name).toUpperCase()}</div>
        <div style={{
          padding: "6px 12px", border: `1.5px solid ${palette.ink}55`,
          fontFamily: "'Anton', sans-serif", fontSize: 11, letterSpacing: 2,
          color: palette.ink, opacity: 0.8,
        }}>SPONSOR</div>
      </div>

      <GrainSVG opacity={0.3} id="ca2" />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// COMPANION 3 — Man of the Match (larger, bolder stats)
// Data: { motm: { player, stats: [{label,value}], summary } }
// ─────────────────────────────────────────────────────────────
function C3_ManOfMatch({ motm, team, opponent, match, palette }) {
  const player = motm?.player;
  const stats = motm?.stats || [];
  const hasHead = !!(player && player.headshot);

  return (
    <div style={{
      width: 1080, height: 1080, position: "relative", overflow: "hidden",
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      {/* Diagonal accent block */}
      <div style={{
        position: "absolute", left: -100, top: -100, width: 700, height: 1400,
        background: palette.secondary, transform: "rotate(8deg)", transformOrigin: "top left",
      }} />
      <Halftone color={palette.ink} opacity={0.06} size={11} />
      <Stripes color={palette.accent} opacity={0.04} gap={28} angle={-22} />

      {/* Big trophy / star */}
      <div style={{
        position: "absolute", right: 60, top: 90,
        fontFamily: "'Anton', sans-serif", fontSize: 320, lineHeight: 0.8,
        color: palette.accent, opacity: 0.18, letterSpacing: -8, userSelect: "none",
      }}>★</div>

      {/* Header */}
      <div style={{
        position: "absolute", left: 0, right: 0, top: 0,
        padding: "32px 40px", display: "flex", justifyContent: "space-between", alignItems: "flex-start", zIndex: 3,
      }}>
        <div>
          <div style={{
            display: "inline-block", padding: "6px 14px",
            background: palette.accent, color: palette.primary,
            fontFamily: "'Anton', sans-serif", fontSize: 18, letterSpacing: 3,
          }}>★ MAN OF THE MATCH</div>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 32, letterSpacing: 1.5, marginTop: 14,
            color: palette.ink,
          }}>{team.name} <span style={{ color: palette.accent }}>v</span> {opponent.name}</div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 1.5,
            color: palette.ink, opacity: 0.7, marginTop: 6,
          }}>{match.competition} · {match.round} · {match.date}</div>
        </div>
        <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={84} shape="shield" />
      </div>

      {/* Player image area */}
      <div style={{
        position: "absolute", left: 0, top: 220, width: 520, height: 700,
        display: "grid", placeItems: "end center", overflow: "hidden",
      }}>
        {hasHead ? (
          <img src={player.headshot} alt={player?.last}
            style={{
              height: 760, width: "auto", objectFit: "contain", objectPosition: "bottom",
              filter: `drop-shadow(0 40px 80px ${palette.primary}ee)`,
            }} />
        ) : (
          <img src={team.logo} alt={team.short}
            style={{ width: 400, height: 400, objectFit: "contain", marginBottom: 80 }} />
        )}
      </div>

      {/* Right side — name + stats */}
      <div style={{
        position: "absolute", right: 36, top: 230, width: 520, zIndex: 3,
      }}>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 44, letterSpacing: 1,
          color: palette.ink, opacity: 0.78, lineHeight: 1,
        }}>{(player?.first || "").toUpperCase()}</div>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 124, letterSpacing: -1,
          color: palette.ink, lineHeight: 0.88, marginTop: -2,
        }}>{player?.last || ""}</div>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 13, letterSpacing: 2,
          color: palette.accent, marginTop: 8,
        }}>{(player?.roleLong || player?.role || "").toUpperCase()}</div>

        {/* Stats grid — much larger */}
        <div style={{
          display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 22,
        }}>
          {stats.map((s, i) => (
            <div key={i} style={{
              padding: "14px 18px",
              background: i === 0 ? palette.accent : `${palette.ink}0c`,
              border: i === 0 ? `1.5px solid ${palette.accent}` : `1.5px solid ${palette.accent}`,
              color: i === 0 ? palette.primary : palette.ink,
            }}>
              <div style={{
                fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 2,
                opacity: 0.75,
              }}>{s.label.toUpperCase()}</div>
              <div style={{
                fontFamily: "'Anton', sans-serif", fontSize: 76, lineHeight: 0.9, letterSpacing: -1,
                marginTop: 4,
              }}>{s.value}</div>
            </div>
          ))}
        </div>

        {motm?.summary && (
          <div style={{
            marginTop: 16, fontFamily: "'Inter', sans-serif", fontSize: 15, lineHeight: 1.4,
            color: palette.ink, opacity: 0.78, fontStyle: "italic",
            borderLeft: `3px solid ${palette.accent}`, paddingLeft: 14,
          }}>"{motm.summary}"</div>
        )}
      </div>

      {/* Footer */}
      <div style={{
        position: "absolute", left: 0, right: 0, bottom: 0,
        padding: "16px 40px", background: palette.primary, borderTop: `2px solid ${palette.accent}`,
        display: "flex", justifyContent: "space-between", alignItems: "center", zIndex: 3,
      }}>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 18, letterSpacing: 2, color: palette.ink,
        }}>{match.venue.toUpperCase()}</div>
        <div style={{
          padding: "6px 12px", border: `1.5px solid ${palette.ink}55`,
          fontFamily: "'Anton', sans-serif", fontSize: 11, letterSpacing: 2,
          color: palette.ink, opacity: 0.8,
        }}>SPONSOR</div>
      </div>

      <GrainSVG opacity={0.3} id="ca3" />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// COMPANION 4 — Final score with top performers per side
// Data: { result: { winner, margin, teamScore, oppScore, motmLast?,
//                   topBatters: { team: [{last,line}], opponent: [...] },
//                   topBowlers: { team: [...],          opponent: [...] } } }
// ─────────────────────────────────────────────────────────────
function C4_FinalScore({ result, team, opponent, match, palette }) {
  const winnerSide = result?.winner === "OPPONENT" ? "opponent" : (result?.winner === "TIE" ? "tie" : "team");
  const tb = result?.topBatters || {};
  const tw = result?.topBowlers || {};
  const teamBatters = tb.team || [];
  const teamBowlers = tw.team || [];
  const oppBatters  = tb.opponent || [];
  const oppBowlers  = tw.opponent || [];

  // Reusable performer row
  const Perf = ({ p, accent }) => (
    <div style={{
      display: "flex", justifyContent: "space-between", alignItems: "baseline",
      borderBottom: `1px solid ${palette.ink}1a`, padding: "5px 0",
      fontFamily: "'Anton', sans-serif", color: palette.ink, lineHeight: 1.05,
      whiteSpace: "nowrap", overflow: "hidden",
    }}>
      <span style={{ fontSize: 18, letterSpacing: 0.5, overflow: "hidden", textOverflow: "ellipsis", paddingRight: 8 }}>{p.last}</span>
      <span style={{ fontSize: 16, color: accent || palette.accent, letterSpacing: 1 }}>{p.line}</span>
    </div>
  );

  return (
    <div style={{
      width: 1080, height: 1080, position: "relative", overflow: "hidden",
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Halftone color={palette.ink} opacity={0.06} size={10} />
      <Stripes color={palette.accent} opacity={0.03} gap={28} angle={0} />

      {/* Full-canvas flex column so content fills the whole frame */}
      <div style={{
        position: "absolute", inset: 0, paddingBottom: 64,
        display: "flex", flexDirection: "column",
      }}>
      {/* Header */}
      <div style={{
        padding: "40px 48px 24px", display: "flex", justifyContent: "space-between", alignItems: "center",
        borderBottom: `3px solid ${palette.accent}`,
      }}>
        <div>
          <div style={{
            display: "inline-block", padding: "8px 16px",
            background: palette.accent, color: palette.primary,
            fontFamily: "'Anton', sans-serif", fontSize: 22, letterSpacing: 3,
          }}>FULL TIME</div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 14, letterSpacing: 1.5,
            color: palette.ink, opacity: 0.7, marginTop: 10,
          }}>{match.competition} · {match.round} · {match.date}</div>
        </div>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 56, letterSpacing: 2, color: palette.ink,
        }}>RESULT</div>
      </div>

      {/* Scores row */}
      <div style={{
        padding: "36px 48px 24px",
        display: "grid", gridTemplateColumns: "1fr auto 1fr", gap: 24, alignItems: "center",
      }}>
        {/* Team */}
        <div style={{
          textAlign: "center",
          padding: "22px 18px",
          background: winnerSide === "team" ? `${palette.accent}22` : "transparent",
          border: `2px solid ${winnerSide === "team" ? palette.accent : palette.ink + "22"}`,
          position: "relative",
        }}>
          {winnerSide === "team" && (
            <div style={{
              position: "absolute", top: -14, left: "50%", transform: "translateX(-50%)",
              padding: "4px 12px", background: palette.accent, color: palette.primary,
              fontFamily: "'Anton', sans-serif", fontSize: 16, letterSpacing: 2,
            }}>WINNER</div>
          )}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 18 }}>
            <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={96} shape="shield" />
            <div style={{ textAlign: "left" }}>
              <div style={{ fontFamily: "'Anton', sans-serif", fontSize: 28, letterSpacing: 1, color: palette.ink, lineHeight: 1 }}>{team.name}</div>
              <div style={{ fontFamily: "'Anton', sans-serif", fontSize: 64, letterSpacing: -0.5, lineHeight: 1, color: palette.ink, marginTop: 6 }}>{result?.teamScore || "—"}</div>
            </div>
          </div>
        </div>

        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 52, letterSpacing: 2, color: palette.accent,
        }}>VS</div>

        {/* Opponent */}
        <div style={{
          textAlign: "center",
          padding: "22px 18px",
          background: winnerSide === "opponent" ? `${palette.accent}22` : "transparent",
          border: `2px solid ${winnerSide === "opponent" ? palette.accent : palette.ink + "22"}`,
          position: "relative",
        }}>
          {winnerSide === "opponent" && (
            <div style={{
              position: "absolute", top: -14, left: "50%", transform: "translateX(-50%)",
              padding: "4px 12px", background: palette.accent, color: palette.primary,
              fontFamily: "'Anton', sans-serif", fontSize: 16, letterSpacing: 2,
            }}>WINNER</div>
          )}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 18 }}>
            <ClubLogo src={opponent.logo} monogram={opponent.monogram} color={palette.ink} size={96} shape="shield" />
            <div style={{ textAlign: "left" }}>
              <div style={{ fontFamily: "'Anton', sans-serif", fontSize: 28, letterSpacing: 1, color: palette.ink, lineHeight: 1 }}>{opponent.name}</div>
              <div style={{ fontFamily: "'Anton', sans-serif", fontSize: 64, letterSpacing: -0.5, lineHeight: 1, color: palette.ink, marginTop: 6 }}>{result?.oppScore || "—"}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Top performers — fills remaining vertical space */}
      <div style={{
        margin: "0 48px 20px", flex: 1,
        display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, minHeight: 0,
      }}>
        {/* Team side */}
        <div style={{
          padding: "20px 22px",
          background: `${palette.ink}08`,
          borderLeft: `3px solid ${palette.accent}`,
          display: "flex", flexDirection: "column",
        }}>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 22, letterSpacing: 2, lineHeight: 1,
            color: palette.accent, marginBottom: 14,
          }}>{team.short} · TOP PERFORMERS</div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.5,
            color: palette.ink, opacity: 0.6, marginBottom: 6,
          }}>BATTING</div>
          {teamBatters.slice(0, 3).map((p, i) => <Perf key={i} p={p} />)}
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.5,
            color: palette.ink, opacity: 0.6, marginTop: 14, marginBottom: 6,
          }}>BOWLING</div>
          {teamBowlers.slice(0, 3).map((p, i) => <Perf key={i} p={p} />)}
        </div>

        {/* Opponent side */}
        <div style={{
          padding: "20px 22px",
          background: `${palette.ink}08`,
          borderLeft: `3px solid ${palette.ink}55`,
          display: "flex", flexDirection: "column",
        }}>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 22, letterSpacing: 2, lineHeight: 1,
            color: palette.ink, opacity: 0.85, marginBottom: 14,
          }}>{opponent.short} · TOP PERFORMERS</div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.5,
            color: palette.ink, opacity: 0.6, marginBottom: 6,
          }}>BATTING</div>
          {oppBatters.slice(0, 3).map((p, i) => <Perf key={i} p={p} />)}
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.5,
            color: palette.ink, opacity: 0.6, marginTop: 14, marginBottom: 6,
          }}>BOWLING</div>
          {oppBowlers.slice(0, 3).map((p, i) => <Perf key={i} p={p} />)}
        </div>
      </div>

      {/* Result statement */}
      <div style={{
        margin: "0 48px 20px", padding: "26px 28px",
        background: palette.secondary, borderLeft: `4px solid ${palette.accent}`,
        textAlign: "center",
      }}>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 13, letterSpacing: 2,
          color: palette.accent, marginBottom: 10,
        }}>// MATCH RESULT</div>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 60, letterSpacing: -0.5, lineHeight: 1.05,
          color: palette.ink,
        }}>
          {result?.winner === "TIE"
            ? "MATCH TIED"
            : `${(winnerSide === "team" ? team.name : opponent.name)} WIN ${result?.margin || ""}`.trim()}
        </div>
        {result?.motmLast && (
          <div style={{
            display: "inline-block", marginTop: 12, padding: "6px 14px",
            background: `${palette.ink}10`, border: `1px solid ${palette.accent}`,
            fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 1.5,
            color: palette.ink, opacity: 0.85,
          }}>★ MOTM · {result.motmLast}</div>
        )}
      </div>
      </div>{/* end full-canvas flex column */}

      {/* Footer */}
      <div style={{
        position: "absolute", left: 0, right: 0, bottom: 0,
        padding: "18px 48px", background: palette.primary, borderTop: `2px solid ${palette.accent}`,
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 18, letterSpacing: 2, color: palette.ink,
        }}>{match.venue.toUpperCase()}</div>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.5,
          color: palette.ink, opacity: 0.65,
        }}>{match.season} SEASON</div>
        <div style={{
          padding: "6px 12px", border: `1.5px solid ${palette.ink}55`,
          fontFamily: "'Anton', sans-serif", fontSize: 11, letterSpacing: 2,
          color: palette.ink, opacity: 0.8,
        }}>SPONSOR</div>
      </div>

      <GrainSVG opacity={0.3} id="ca4" />
    </div>
  );
}

Object.assign(window, { C1_CaptainAnnounce, C2_TossWon, C3_ManOfMatch, C4_FinalScore });
