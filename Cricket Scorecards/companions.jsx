// Companion templates (1080×1080) — single-moment posts that go with the lineup set.
// Each takes its own data shape (described above each component).

// ─────────────────────────────────────────────────────────────
// COMPANION 1 — Captain announcement
// Data: { player, team, opponent, match, palette }
//   player has { first, last, role, roleLong, headshot? }
// ─────────────────────────────────────────────────────────────
function C1_CaptainAnnounce({ player, team, opponent, match, palette }) {
  const hasHead = !!(player && player.headshot);
  return (
    <div style={{
      width: 1080, height: 1080, position: "relative", overflow: "hidden",
      background: `linear-gradient(160deg, ${palette.primary} 0%, ${palette.secondary} 100%)`,
      color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Halftone color={palette.ink} opacity={0.07} size={11} />
      <Stripes color={palette.accent} opacity={0.04} gap={28} angle={-22} />

      {/* Huge ghost word */}
      <div style={{
        position: "absolute", left: -40, top: -40,
        fontFamily: "'Anton', sans-serif", fontSize: 520, lineHeight: 0.8,
        color: palette.accent, opacity: 0.08, letterSpacing: -10, userSelect: "none",
      }}>CAPTAIN</div>

      {/* Player */}
      <div style={{
        position: "absolute", left: 60, top: 100, right: 60, bottom: 200,
        display: "grid", placeItems: "end center", overflow: "hidden",
      }}>
        {hasHead ? (
          <img src={player.headshot} alt={player.last}
            style={{
              height: 780, width: "auto", objectFit: "contain", objectPosition: "bottom",
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
        padding: "36px 48px", display: "flex", justifyContent: "space-between", alignItems: "center", zIndex: 3,
      }}>
        <div>
          <div style={{
            display: "inline-block", padding: "5px 12px",
            background: palette.accent, color: palette.primary,
            fontFamily: "'Anton', sans-serif", fontSize: 16, letterSpacing: 3,
          }}>ANNOUNCEMENT</div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 1.5,
            color: palette.ink, opacity: 0.7, marginTop: 8,
          }}>{match.competition} · {match.season}</div>
        </div>
        <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={84} shape="shield" />
      </div>

      {/* Name lockup */}
      <div style={{
        position: "absolute", left: 48, bottom: 160, zIndex: 3,
      }}>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 24, letterSpacing: 4,
          color: palette.accent, marginBottom: 6,
        }}>NAMED CAPTAIN</div>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 44, letterSpacing: 1,
          color: palette.ink, opacity: 0.78, lineHeight: 1,
        }}>{(player?.first || "").toUpperCase()}</div>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 160, letterSpacing: -2,
          color: palette.ink, lineHeight: 0.88, marginTop: -4,
        }}>{player?.last || "—"}</div>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 13, letterSpacing: 2,
          color: palette.ink, opacity: 0.7, marginTop: 8,
        }}>{(player?.roleLong || player?.role || "").toUpperCase()}</div>
      </div>

      {/* Footer */}
      <div style={{
        position: "absolute", left: 0, right: 0, bottom: 0,
        padding: "18px 48px",
        background: palette.primary, borderTop: `2px solid ${palette.accent}`,
        display: "flex", justifyContent: "space-between", alignItems: "center", zIndex: 3,
      }}>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 18, letterSpacing: 2, color: palette.ink,
        }}>{team.name}</div>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.5,
          color: palette.ink, opacity: 0.65,
        }}>VS {opponent.name} · {match.date} · {match.venue.toUpperCase()}</div>
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
// Data: { toss: { winner: "TEAM" | "OPPONENT", decision: "BAT" | "BOWL" }, team, opponent, match, palette }
// ─────────────────────────────────────────────────────────────
function C2_TossWon({ toss, team, opponent, match, palette }) {
  const winnerTeam = toss?.winner === "OPPONENT" ? opponent : team;
  const decision = (toss?.decision || "BAT").toUpperCase();
  const decisionLong = decision === "BAT" ? "BATTING FIRST" : "BOWLING FIRST";

  return (
    <div style={{
      width: 1080, height: 1080, position: "relative", overflow: "hidden",
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Halftone color={palette.ink} opacity={0.07} size={10} />

      {/* Spinning coin element */}
      <div style={{
        position: "absolute", right: -60, top: -60, width: 580, height: 580,
        borderRadius: "50%",
        background: `radial-gradient(circle at 35% 30%, ${palette.accent} 0%, ${palette.accent}cc 50%, ${palette.accent}55 100%)`,
        boxShadow: `inset 0 0 0 12px ${palette.primary}, inset 0 0 0 16px ${palette.accent}`,
      }} />
      <div style={{
        position: "absolute", right: 130, top: 120,
        fontFamily: "'Anton', sans-serif", fontSize: 240, letterSpacing: -4,
        color: palette.primary, lineHeight: 0.85,
      }}>TOSS</div>

      {/* Top bar */}
      <div style={{
        position: "absolute", left: 0, right: 0, top: 0,
        padding: "36px 48px", display: "flex", justifyContent: "space-between", alignItems: "center", zIndex: 3,
      }}>
        <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={64} shape="shield" />
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 2,
          color: palette.ink, opacity: 0.7,
        }}>{match.competition} · {match.round}</div>
      </div>

      {/* Main lockup */}
      <div style={{
        position: "absolute", left: 60, top: 360, right: 60,
      }}>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 14, letterSpacing: 4,
          color: palette.accent, marginBottom: 6,
        }}>// {toss?.winner === "OPPONENT" ? opponent.name : team.name} WON THE TOSS</div>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 56, letterSpacing: 2,
          color: palette.ink, opacity: 0.6, lineHeight: 1,
        }}>WE'RE</div>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 220, letterSpacing: -3,
          color: palette.ink, lineHeight: 0.85,
        }}>{decision}</div>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 56, letterSpacing: 2,
          color: palette.accent, lineHeight: 1, marginTop: -4,
        }}>FIRST</div>
      </div>

      {/* Side info */}
      <div style={{
        position: "absolute", left: 60, bottom: 130,
        display: "flex", alignItems: "center", gap: 28,
      }}>
        <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={84} shape="shield" />
        <div style={{ fontFamily: "'Anton', sans-serif", fontSize: 30, opacity: 0.7 }}>VS</div>
        <ClubLogo src={opponent.logo} monogram={opponent.monogram} color={palette.ink} size={84} shape="shield" />
      </div>

      {/* Footer */}
      <div style={{
        position: "absolute", left: 0, right: 0, bottom: 0,
        padding: "18px 48px", background: palette.secondary,
        display: "flex", justifyContent: "space-between", alignItems: "center", zIndex: 3,
      }}>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 18, letterSpacing: 2, color: palette.ink,
        }}>{match.venue.toUpperCase()}</div>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 1.5, color: palette.accent,
        }}>{match.date} · {match.time}</div>
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
// COMPANION 3 — Man of the Match
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
        padding: "36px 48px", display: "flex", justifyContent: "space-between", alignItems: "flex-start", zIndex: 3,
      }}>
        <div>
          <div style={{
            display: "inline-block", padding: "5px 12px",
            background: palette.accent, color: palette.primary,
            fontFamily: "'Anton', sans-serif", fontSize: 16, letterSpacing: 3,
          }}>★ MAN OF THE MATCH</div>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 26, letterSpacing: 2, marginTop: 12,
            color: palette.ink,
          }}>{team.name} vs {opponent.name}</div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.5,
            color: palette.ink, opacity: 0.6, marginTop: 4,
          }}>{match.competition} · {match.round} · {match.date}</div>
        </div>
        <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={80} shape="shield" />
      </div>

      {/* Player image area */}
      <div style={{
        position: "absolute", left: 0, top: 200, width: 560, height: 720,
        display: "grid", placeItems: "end center", overflow: "hidden",
      }}>
        {hasHead ? (
          <img src={player.headshot} alt={player?.last}
            style={{
              height: 720, width: "auto", objectFit: "contain", objectPosition: "bottom",
              filter: `drop-shadow(0 40px 80px ${palette.primary}ee)`,
            }} />
        ) : (
          <img src={team.logo} alt={team.short}
            style={{ width: 400, height: 400, objectFit: "contain", marginBottom: 80 }} />
        )}
      </div>

      {/* Right side — name + stats */}
      <div style={{
        position: "absolute", right: 48, top: 220, width: 460, zIndex: 3,
      }}>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 40, letterSpacing: 1,
          color: palette.ink, opacity: 0.78, lineHeight: 1,
        }}>{(player?.first || "").toUpperCase()}</div>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 110, letterSpacing: -1,
          color: palette.ink, lineHeight: 0.88, marginTop: -2,
        }}>{player?.last || ""}</div>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 2,
          color: palette.accent, marginTop: 8,
        }}>{(player?.roleLong || player?.role || "").toUpperCase()}</div>

        {/* Stats grid */}
        <div style={{
          display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 30,
        }}>
          {stats.map((s, i) => (
            <div key={i} style={{
              padding: "14px 16px",
              background: `${palette.ink}0c`,
              border: `1.5px solid ${palette.accent}`,
            }}>
              <div style={{
                fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: 2,
                color: palette.ink, opacity: 0.6,
              }}>{s.label.toUpperCase()}</div>
              <div style={{
                fontFamily: "'Anton', sans-serif", fontSize: 48, lineHeight: 1,
                color: palette.ink, marginTop: 4,
              }}>{s.value}</div>
            </div>
          ))}
        </div>

        {motm?.summary && (
          <div style={{
            marginTop: 16, fontFamily: "'Inter', sans-serif", fontSize: 14, lineHeight: 1.4,
            color: palette.ink, opacity: 0.75, fontStyle: "italic",
            borderLeft: `3px solid ${palette.accent}`, paddingLeft: 12,
          }}>"{motm.summary}"</div>
        )}
      </div>

      {/* Footer */}
      <div style={{
        position: "absolute", left: 0, right: 0, bottom: 0,
        padding: "16px 48px", background: palette.primary, borderTop: `2px solid ${palette.accent}`,
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
// COMPANION 4 — Final score
// Data: { result: { winner: "TEAM"|"OPPONENT"|"TIE", margin: "by 28 runs", teamScore: "182/6 (20)", oppScore: "154/9 (20)", motmLast?: "HOLT" } }
// ─────────────────────────────────────────────────────────────
function C4_FinalScore({ result, team, opponent, match, palette }) {
  const winnerSide = result?.winner === "OPPONENT" ? "opponent" : (result?.winner === "TIE" ? "tie" : "team");
  return (
    <div style={{
      width: 1080, height: 1080, position: "relative", overflow: "hidden",
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Halftone color={palette.ink} opacity={0.06} size={10} />

      {/* Header */}
      <div style={{
        padding: "40px 48px 24px", display: "flex", justifyContent: "space-between", alignItems: "center",
        borderBottom: `3px solid ${palette.accent}`,
      }}>
        <div>
          <div style={{
            display: "inline-block", padding: "5px 12px",
            background: palette.accent, color: palette.primary,
            fontFamily: "'Anton', sans-serif", fontSize: 16, letterSpacing: 3,
          }}>FULL TIME</div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 1.5,
            color: palette.ink, opacity: 0.7, marginTop: 10,
          }}>{match.competition} · {match.round} · {match.date}</div>
        </div>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 32, letterSpacing: 2, color: palette.ink,
        }}>RESULT</div>
      </div>

      {/* Scores row */}
      <div style={{
        padding: "44px 48px 30px",
        display: "grid", gridTemplateColumns: "1fr auto 1fr", gap: 30, alignItems: "center",
      }}>
        {/* Team */}
        <div style={{
          textAlign: "center",
          padding: "26px 18px",
          background: winnerSide === "team" ? `${palette.accent}22` : "transparent",
          border: `2px solid ${winnerSide === "team" ? palette.accent : palette.ink + "22"}`,
          position: "relative",
        }}>
          {winnerSide === "team" && (
            <div style={{
              position: "absolute", top: -12, left: "50%", transform: "translateX(-50%)",
              padding: "3px 10px", background: palette.accent, color: palette.primary,
              fontFamily: "'Anton', sans-serif", fontSize: 14, letterSpacing: 2,
            }}>WINNER</div>
          )}
          <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={120} shape="shield" />
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 32, letterSpacing: 1, marginTop: 10, color: palette.ink,
          }}>{team.name}</div>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 64, letterSpacing: -1, lineHeight: 1, marginTop: 8,
            color: palette.ink,
          }}>{result?.teamScore || "—"}</div>
        </div>

        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 48, letterSpacing: 2, color: palette.accent,
        }}>VS</div>

        {/* Opponent */}
        <div style={{
          textAlign: "center",
          padding: "26px 18px",
          background: winnerSide === "opponent" ? `${palette.accent}22` : "transparent",
          border: `2px solid ${winnerSide === "opponent" ? palette.accent : palette.ink + "22"}`,
          position: "relative",
        }}>
          {winnerSide === "opponent" && (
            <div style={{
              position: "absolute", top: -12, left: "50%", transform: "translateX(-50%)",
              padding: "3px 10px", background: palette.accent, color: palette.primary,
              fontFamily: "'Anton', sans-serif", fontSize: 14, letterSpacing: 2,
            }}>WINNER</div>
          )}
          <ClubLogo src={opponent.logo} monogram={opponent.monogram} color={palette.ink} size={120} shape="shield" />
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 32, letterSpacing: 1, marginTop: 10, color: palette.ink,
          }}>{opponent.name}</div>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 64, letterSpacing: -1, lineHeight: 1, marginTop: 8,
            color: palette.ink,
          }}>{result?.oppScore || "—"}</div>
        </div>
      </div>

      {/* Result statement */}
      <div style={{
        margin: "0 48px", padding: "24px 28px",
        background: palette.secondary, borderLeft: `4px solid ${palette.accent}`,
        textAlign: "center",
      }}>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 2,
          color: palette.accent, marginBottom: 6,
        }}>// MATCH RESULT</div>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 56, letterSpacing: -0.5, lineHeight: 1.05,
          color: palette.ink,
        }}>
          {result?.winner === "TIE"
            ? "MATCH TIED"
            : `${(winnerSide === "team" ? team.name : opponent.name)} WIN ${result?.margin || ""}`.trim()}
        </div>
      </div>

      {/* MOTM */}
      {result?.motmLast && (
        <div style={{
          margin: "20px 48px 0", padding: "14px 20px",
          display: "flex", justifyContent: "space-between", alignItems: "center",
          background: `${palette.ink}08`, border: `1.5px solid ${palette.accent}`,
        }}>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 2,
            color: palette.accent,
          }}>★ MAN OF THE MATCH</div>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 30, letterSpacing: 1, color: palette.ink,
          }}>{result.motmLast}</div>
        </div>
      )}

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
