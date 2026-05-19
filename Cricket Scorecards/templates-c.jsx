// Templates 7–9: Captain Spotlight, Asymmetric Mosaic, Festival Flyer
// All artboards are 1080×1080.

// ─────────────────────────────────────────────────────────────
// TEMPLATE 7 — Captain Spotlight
// Featured player full-bleed with the rest of the XI as a small footer strip.
// ─────────────────────────────────────────────────────────────
function T7_CaptainSpotlight({ team, opponent, match, players, palette }) {
  const featured = featuredOf(players);
  const rest = players.slice(0, 11).filter(p => p !== featured).slice(0, 10);
  const featHasHead = !!(featured && featured.headshot);

  return (
    <div style={{
      width: 1080, height: 1080, position: "relative", overflow: "hidden",
      background: `radial-gradient(ellipse at 70% 30%, ${palette.secondary} 0%, ${palette.primary} 70%)`,
      color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Halftone color={palette.ink} opacity={0.06} size={11} />
      <Stripes color={palette.accent} opacity={0.04} gap={26} angle={-22} />

      {/* Giant typographic background */}
      <div style={{
        position: "absolute", left: -40, top: -60,
        fontFamily: "'Anton', sans-serif", fontSize: 600, lineHeight: 0.8,
        color: palette.accent, opacity: 0.07, letterSpacing: -14, userSelect: "none",
      }}>XI</div>

      {/* Featured player */}
      <div style={{
        position: "absolute", left: 0, top: 0, width: 1080, height: 820,
        display: "grid", placeItems: "end center", overflow: "hidden",
      }}>
        {featHasHead ? (
          <img src={featured.headshot} alt={featured.last}
            style={{
              height: 820, width: "auto", objectFit: "contain", objectPosition: "bottom",
              filter: `drop-shadow(0 40px 80px ${palette.primary}ee)`,
            }} />
        ) : (
          <img src={team.logo} alt={team.short}
            style={{ width: 520, height: 520, objectFit: "contain", marginBottom: 100 }} />
        )}
      </div>

      {/* Top bar — competition + opponent */}
      <div style={{
        position: "absolute", left: 0, right: 0, top: 0,
        padding: "32px 48px",
        display: "flex", justifyContent: "space-between", alignItems: "flex-start",
        zIndex: 3,
      }}>
        <div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 2,
            color: palette.accent,
          }}>// CAPTAIN</div>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 22, letterSpacing: 2, marginTop: 4,
          }}>{match.competition} · {match.round}</div>
        </div>
        <div style={{
          display: "flex", alignItems: "center", gap: 14,
        }}>
          <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={56} shape="shield" />
          <div style={{ fontFamily: "'Anton', sans-serif", fontSize: 18, opacity: 0.7 }}>VS</div>
          <ClubLogo src={opponent.logo} monogram={opponent.monogram} color={palette.ink} size={56} shape="shield" />
        </div>
      </div>

      {/* Name plate */}
      {featured && (
        <div style={{
          position: "absolute", left: 48, bottom: 250,
          maxWidth: 600,
          zIndex: 3,
        }}>
          <div style={{
            display: "inline-block", padding: "5px 12px",
            background: palette.accent, color: palette.primary,
            fontFamily: "'Anton', sans-serif", fontSize: 16, letterSpacing: 3,
            marginBottom: 12,
          }}>CAPTAIN · {featured.role}</div>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 38, letterSpacing: 1,
            color: palette.ink, opacity: 0.78, lineHeight: 1,
          }}>{featured.first.toUpperCase()}</div>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 120, letterSpacing: -1,
            color: palette.ink, lineHeight: 0.9, marginTop: -2,
          }}>{featured.last}</div>
        </div>
      )}

      {/* Bottom strip — rest of XI */}
      <div style={{
        position: "absolute", left: 0, right: 0, bottom: 0,
        background: palette.primary,
        borderTop: `3px solid ${palette.accent}`,
        padding: "16px 32px 22px",
        zIndex: 3,
      }}>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: 2,
          color: palette.accent, marginBottom: 8,
        }}>// THE REST OF THE XI</div>
        <div style={{
          display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 6, columnGap: 16,
        }}>
          {rest.map((p, i) => {
            const chip = p.captain ? "C" : p.viceCaptain ? "VC" : p.keeper ? "WK" : null;
            return (
              <div key={i} style={{
                display: "flex", alignItems: "center", gap: 6,
                fontFamily: "'Anton', sans-serif", fontSize: 18, letterSpacing: 0.5,
                color: palette.ink, lineHeight: 1.1,
                borderBottom: `1px solid ${palette.ink}1c`, paddingBottom: 4,
                whiteSpace: "nowrap", overflow: "hidden",
              }}>
                <span style={{ color: palette.accent, fontSize: 12, opacity: 0.8 }}>
                  {String(i + 2).padStart(2, "0")}
                </span>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{p.last}</span>
                {chip && <RoleChip kind={chip} accent={palette.accent} ink={palette.primary} />}
              </div>
            );
          })}
        </div>
        <div style={{
          marginTop: 10, display: "flex", justifyContent: "space-between",
          fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: 1.5,
          color: palette.ink, opacity: 0.6,
        }}>
          <span>{match.venue.toUpperCase()} · {match.date} · {match.time}</span>
          <span>SPONSOR</span>
        </div>
      </div>

      <GrainSVG opacity={0.32} id="g7" />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// TEMPLATE 8 — Asymmetric Mosaic
// Varied tile sizes: featured player gets a 2x2, others fill 1x1 tiles
// in a 5-column grid. Role-coded tile backgrounds.
// ─────────────────────────────────────────────────────────────
function T8_Mosaic({ team, opponent, match, players, palette }) {
  const P = players.slice(0, 11);
  const ROLE_BG = {
    BAT:  palette.accent,
    BOWL: palette.ink,
    AR:   palette.secondary,
    WK:   palette.primary,
  };
  const ROLE_INK = {
    BAT:  palette.primary,
    BOWL: palette.primary,
    AR:   palette.ink,
    WK:   palette.ink,
  };
  return (
    <div style={{
      width: 1080, height: 1080, position: "relative", overflow: "hidden",
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Halftone color={palette.ink} opacity={0.05} size={9} />

      {/* Header */}
      <div style={{
        padding: "32px 36px 18px",
        display: "flex", justifyContent: "space-between", alignItems: "center",
        borderBottom: `2px solid ${palette.accent}`,
      }}>
        <div>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 56, lineHeight: 0.9,
            color: palette.ink, letterSpacing: -1,
          }}>THE STARTING XI</div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.5,
            color: palette.accent, marginTop: 4,
          }}>{team.name} VS {opponent.name} · {match.round} · {match.date}</div>
        </div>
        <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={68} shape="shield" />
      </div>

      {/* Mosaic grid */}
      <div style={{
        position: "absolute", left: 28, right: 28, top: 180, bottom: 100,
        display: "grid",
        gridTemplateColumns: "repeat(5, 1fr)",
        gridTemplateRows: "repeat(4, 1fr)",
        gap: 10,
      }}>
        {P.map((p, i) => {
          // Featured player gets a 2x2 tile at top-left
          const isFeatured = p.captain;
          const role = p.role || "BAT";
          const bg = ROLE_BG[role];
          const ink = ROLE_INK[role];
          const chip = p.captain ? "C" : p.viceCaptain ? "VC" : p.keeper ? "WK" : null;
          return (
            <div key={i} style={{
              gridColumn: isFeatured ? "span 2" : "span 1",
              gridRow: isFeatured ? "span 2" : "span 1",
              background: bg, color: ink,
              position: "relative", overflow: "hidden",
              display: "flex", flexDirection: "column",
              border: `1.5px solid ${palette.ink}1a`,
            }}>
              {/* Photo area */}
              <div style={{
                flex: 1, position: "relative",
                display: "grid", placeItems: "center",
                background: `linear-gradient(180deg, ${bg} 0%, ${palette.primary}aa 100%)`,
                overflow: "hidden",
              }}>
                {p.headshot ? (
                  <img src={p.headshot} alt={p.last}
                    style={{
                      height: "120%", width: "auto", maxWidth: "100%",
                      objectFit: "contain", objectPosition: "bottom",
                    }} />
                ) : (
                  <img src={team.logo} alt={team.short}
                    style={{ width: isFeatured ? 200 : 80, height: isFeatured ? 200 : 80, objectFit: "contain", opacity: 0.85 }} />
                )}
                <div style={{
                  position: "absolute", top: 6, left: 6,
                  fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: 1.5,
                  color: ink, opacity: 0.7,
                }}>#{String(i + 1).padStart(2, "0")}</div>
                {chip && (
                  <div style={{ position: "absolute", top: 6, right: 6 }}>
                    <RoleChip kind={chip} accent={palette.accent} ink={palette.primary} />
                  </div>
                )}
              </div>
              {/* Name strip */}
              <div style={{
                padding: isFeatured ? "10px 12px" : "5px 8px",
                background: ink, color: bg,
                fontFamily: "'Anton', sans-serif",
                fontSize: isFeatured ? 32 : 14,
                letterSpacing: 0.5, lineHeight: 1,
                whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
              }}>{p.last}</div>
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div style={{
        position: "absolute", left: 36, right: 36, bottom: 24,
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
          <div style={{
            display: "flex", alignItems: "center", gap: 6,
            fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: 1.5, color: palette.ink, opacity: 0.7,
          }}>
            <span style={{ width: 12, height: 12, background: palette.accent }} /> BAT
          </div>
          <div style={{
            display: "flex", alignItems: "center", gap: 6,
            fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: 1.5, color: palette.ink, opacity: 0.7,
          }}>
            <span style={{ width: 12, height: 12, background: palette.ink }} /> BOWL
          </div>
          <div style={{
            display: "flex", alignItems: "center", gap: 6,
            fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: 1.5, color: palette.ink, opacity: 0.7,
          }}>
            <span style={{ width: 12, height: 12, background: palette.secondary, border: `1px solid ${palette.ink}55` }} /> ALL-ROUND
          </div>
        </div>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: 1.5,
          color: palette.ink, opacity: 0.7,
        }}>{match.venue.toUpperCase()} · {match.time}</div>
      </div>

      <GrainSVG opacity={0.28} id="g8" />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// TEMPLATE 9 — Festival flyer / tour poster
// Names stacked like a festival lineup — first row biggest, decreasing.
// Big VS banner, gritty atmosphere.
// ─────────────────────────────────────────────────────────────
function T9_Flyer({ team, opponent, match, players, palette }) {
  const P = players.slice(0, 11);
  // Group into 3 tiers like a festival poster: 2 headliners, 3 mid, 6 small
  const tier1 = P.slice(0, 2);
  const tier2 = P.slice(2, 5);
  const tier3 = P.slice(5, 11);

  return (
    <div style={{
      width: 1080, height: 1080, position: "relative", overflow: "hidden",
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Halftone color={palette.ink} opacity={0.08} size={10} />
      <Stripes color={palette.accent} opacity={0.05} gap={32} angle={0} />

      {/* Top "presents" header */}
      <div style={{
        textAlign: "center", padding: "44px 40px 20px", position: "relative", zIndex: 2,
      }}>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 4,
          color: palette.accent,
        }}>{match.competition} · {match.season} · PRESENTS</div>
        <div style={{
          display: "flex", justifyContent: "center", alignItems: "center", gap: 22, marginTop: 14,
        }}>
          <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={70} shape="shield" />
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 80, letterSpacing: 1,
            color: palette.ink, lineHeight: 1,
          }}>{team.name}</div>
        </div>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 38, letterSpacing: 4,
          color: palette.accent, margin: "8px 0",
        }}>— VS —</div>
        <div style={{
          display: "flex", justifyContent: "center", alignItems: "center", gap: 22,
        }}>
          <ClubLogo src={opponent.logo} monogram={opponent.monogram} color={palette.ink} size={56} shape="shield" />
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 54, letterSpacing: 1,
            color: palette.ink, lineHeight: 1, opacity: 0.85,
          }}>{opponent.name}</div>
        </div>
      </div>

      {/* Divider */}
      <div style={{
        width: 200, height: 3, background: palette.accent, margin: "16px auto 24px",
      }} />

      {/* Tier 1 — headliners (last names huge) */}
      <div style={{
        textAlign: "center", padding: "0 40px", lineHeight: 0.9,
        fontFamily: "'Anton', sans-serif", color: palette.ink, letterSpacing: -1,
      }}>
        <div style={{ fontSize: 92, marginBottom: 4 }}>
          {tier1.map((p, i) => (
            <React.Fragment key={i}>
              <span>{p.last}</span>
              {i < tier1.length - 1 && <span style={{ color: palette.accent, margin: "0 18px" }}>·</span>}
            </React.Fragment>
          ))}
        </div>
        {/* Tier 2 */}
        <div style={{ fontSize: 56, marginTop: 14, opacity: 0.95 }}>
          {tier2.map((p, i) => (
            <React.Fragment key={i}>
              <span>{p.last}</span>
              {i < tier2.length - 1 && <span style={{ color: palette.accent, margin: "0 14px" }}>·</span>}
            </React.Fragment>
          ))}
        </div>
        {/* Tier 3 */}
        <div style={{ fontSize: 32, marginTop: 12, opacity: 0.85, letterSpacing: 0 }}>
          {tier3.map((p, i) => (
            <React.Fragment key={i}>
              <span>{p.last}</span>
              {i < tier3.length - 1 && <span style={{ color: palette.accent, margin: "0 10px", opacity: 0.7 }}>·</span>}
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* Bottom band */}
      <div style={{
        position: "absolute", left: 0, right: 0, bottom: 0,
        background: palette.accent, color: palette.primary,
        padding: "20px 40px",
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <div>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 36, letterSpacing: 1, lineHeight: 1,
          }}>{match.date}</div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.5, marginTop: 4,
          }}>GATES {match.time}</div>
        </div>
        <div style={{ textAlign: "center" }}>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 28, letterSpacing: 2, lineHeight: 1,
          }}>{match.venue.toUpperCase()}</div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: 1.5, marginTop: 4,
          }}>{match.round}</div>
        </div>
        <div style={{
          padding: "8px 14px", border: `2px solid ${palette.primary}`,
          fontFamily: "'Anton', sans-serif", fontSize: 14, letterSpacing: 2,
        }}>SPONSOR</div>
      </div>

      <GrainSVG opacity={0.4} id="g9" />
    </div>
  );
}

Object.assign(window, { T7_CaptainSpotlight, T8_Mosaic, T9_Flyer });
