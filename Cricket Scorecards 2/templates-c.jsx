// Templates 7–9: Milestone Spotlight, Asymmetric Mosaic, Festival Flyer
// All artboards are 1080×1080.

// ─────────────────────────────────────────────────────────────
// TEMPLATE 7 — Milestone Spotlight
// Showcases a player's achievement (200th game, club record, etc).
// Takes an optional `milestone` prop: { player, value, unit, reason, detail }.
// Falls back to captain + "CAPTAIN" if no milestone supplied.
// ─────────────────────────────────────────────────────────────
function T7_CaptainSpotlight({ team, opponent, match, players, palette, milestone }) {
  const player = milestone?.player || featuredOf(players);
  const value  = milestone?.value  || "1ST";
  const unit   = milestone?.unit   || "XI";
  const reason = milestone?.reason || "NAMED IN THE STARTING XI";
  const detail = milestone?.detail || `${player?.roleLong || ""}`;
  const rest = players.slice(0, 13).filter(p => p !== player);

  const hasHead = !!(player && player.headshot);

  return (
    <div style={{
      width: 1080, height: 1080, position: "relative", overflow: "hidden",
      background: `linear-gradient(135deg, ${palette.primary} 0%, ${palette.secondary} 100%)`,
      color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Halftone color={palette.ink} opacity={0.06} size={11} />
      <Stripes color={palette.accent} opacity={0.04} gap={26} angle={-22} />

      {/* Giant value as a faded background mark */}
      <div style={{
        position: "absolute", right: -40, top: -50,
        fontFamily: "'Anton', sans-serif", fontSize: 720, lineHeight: 0.8,
        color: palette.accent, opacity: 0.08, letterSpacing: -16, userSelect: "none",
      }}>{value}</div>

      {/* Top bar — match meta */}
      <div style={{
        position: "absolute", left: 0, right: 0, top: 0,
        padding: "28px 40px",
        display: "flex", justifyContent: "space-between", alignItems: "center",
        zIndex: 4,
      }}>
        <div>
          <div style={{
            display: "inline-block", padding: "5px 12px",
            background: palette.accent, color: palette.primary,
            fontFamily: "'Anton', sans-serif", fontSize: 16, letterSpacing: 3,
          }}>★ MILESTONE</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={60} shape="shield" />
          <div style={{ fontFamily: "'Anton', sans-serif", fontSize: 18, opacity: 0.7 }}>VS</div>
          <ClubLogo src={opponent.logo} monogram={opponent.monogram} color={palette.ink} size={60} shape="shield" />
        </div>
      </div>

      {/* Featured player — right half */}
      <div style={{
        position: "absolute", right: 0, top: 60, width: 540, height: 660,
        display: "grid", placeItems: "end center", overflow: "hidden",
      }}>
        {hasHead ? (
          <img src={player.headshot} alt={player.last}
            style={{
              height: 720, width: "auto", objectFit: "contain", objectPosition: "bottom",
              filter: `drop-shadow(0 40px 80px ${palette.primary}ee)`,
            }} />
        ) : (
          <img src={team.logo} alt={team.short}
            style={{ width: 380, height: 380, objectFit: "contain", marginBottom: 40 }} />
        )}
      </div>

      {/* Left lockup — big value + reason */}
      <div style={{
        position: "absolute", left: 40, top: 96, width: 540, zIndex: 3,
      }}>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 14, letterSpacing: 3,
          color: palette.accent, marginBottom: 10,
        }}>// {reason}</div>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 320, lineHeight: 0.82,
          color: palette.ink, letterSpacing: -8,
        }}>{value}</div>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 80, letterSpacing: 2,
          color: palette.accent, lineHeight: 1, marginTop: -8,
        }}>{unit}</div>

        {/* Player name */}
        <div style={{
          marginTop: 22, paddingTop: 16, borderTop: `2px solid ${palette.accent}`,
        }}>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 32, letterSpacing: 1,
            color: palette.ink, opacity: 0.78, lineHeight: 1,
          }}>{(player?.first || "").toUpperCase()}</div>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 76, letterSpacing: -1,
            color: palette.ink, lineHeight: 0.9, marginTop: 2,
          }}>{player?.last || ""}</div>
          {detail && (
            <div style={{
              fontFamily: "'JetBrains Mono', monospace", fontSize: 13, letterSpacing: 1.2,
              color: palette.ink, opacity: 0.7, marginTop: 10, lineHeight: 1.4,
            }}>{detail}</div>
          )}
        </div>
      </div>

      {/* Bottom strip — rest of XI in a 3-column grid (more room than before) */}
      <div style={{
        position: "absolute", left: 0, right: 0, bottom: 0, height: 270,
        background: palette.primary,
        borderTop: `3px solid ${palette.accent}`,
        padding: "18px 40px 18px",
        zIndex: 3,
      }}>
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          marginBottom: 12,
        }}>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 2,
            color: palette.accent,
          }}>// JOINED BY THE XI</div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 1.5,
            color: palette.ink, opacity: 0.6,
          }}>{match.venue.toUpperCase()} · {match.date} · {match.time}</div>
        </div>
        <div style={{
          display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 4, columnGap: 24,
        }}>
          {rest.slice(0, 12).map((p, i) => {
            const chip = p.captain ? "C" : p.viceCaptain ? "VC" : p.keeper ? "WK" : null;
            return (
              <div key={i} style={{
                display: "flex", alignItems: "baseline", gap: 8,
                fontFamily: "'Anton', sans-serif", lineHeight: 1.1,
                color: palette.ink,
                borderBottom: `1px solid ${palette.ink}1c`, paddingBottom: 5,
                whiteSpace: "nowrap", overflow: "hidden",
              }}>
                <span style={{ color: palette.accent, fontSize: 13, opacity: 0.85, width: 22 }}>
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span style={{ fontSize: 16, opacity: 0.6, fontWeight: 300 }}>{p.first[0]}.</span>
                <span style={{ fontSize: 22, overflow: "hidden", textOverflow: "ellipsis", flex: 1 }}>{p.last}</span>
                {chip && <RoleChip kind={chip} accent={palette.accent} ink={palette.primary} />}
              </div>
            );
          })}
        </div>
      </div>

      <GrainSVG opacity={0.32} id="g7" />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// TEMPLATE 8 — Asymmetric Mosaic
// Featured player gets a 2×2 tile. featuredIdx prop chooses who that is.
// ─────────────────────────────────────────────────────────────
function T8_Mosaic({ team, opponent, match, players, palette, featuredIdx = 0 }) {
  // Re-order so the featured player is at index 0 → gets the 2×2 slot.
  // Slice to 11, then move featured to front.
  const playersXI = players.slice(0, 11);
  const featuredP = playersXI[featuredIdx] || playersXI.find(p => p.captain) || playersXI[0];
  const rest = playersXI.filter(p => p !== featuredP);
  const P = [featuredP, ...rest];

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

      {/* Top spacer with background wordmark */}
      <div style={{
        position: "absolute", left: 0, right: 0, top: 0, height: 220,
        overflow: "hidden",
      }}>
        <div style={{
          position: "absolute", left: -40, top: -40,
          fontFamily: "'Anton', sans-serif", fontSize: 280, lineHeight: 0.8,
          color: palette.ink, opacity: 0.07, letterSpacing: -6, userSelect: "none",
        }}>THE XI</div>
      </div>

      {/* Header — shifted down, more prominent match info */}
      <div style={{
        position: "relative",
        padding: "36px 36px 18px",
        display: "flex", justifyContent: "space-between", alignItems: "center",
        zIndex: 2,
      }}>
        <div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 2,
            color: palette.accent, marginBottom: 6,
          }}>// STARTING XI · {match.competition}</div>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 60, lineHeight: 0.9,
            color: palette.ink, letterSpacing: -1,
          }}>{team.name} <span style={{ color: palette.accent }}>v</span> {opponent.name}</div>
        </div>
        <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={76} shape="shield" />
      </div>

      {/* Match-info band */}
      <div style={{
        margin: "0 36px",
        padding: "14px 18px",
        background: palette.secondary,
        borderLeft: `3px solid ${palette.accent}`,
        display: "flex", justifyContent: "space-between", alignItems: "center", gap: 18,
        position: "relative", zIndex: 2,
      }}>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 22, letterSpacing: 1, color: palette.ink,
        }}>{match.round}</div>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 22, letterSpacing: 1, color: palette.accent,
        }}>{match.date}</div>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 13, letterSpacing: 1.5, color: palette.ink, opacity: 0.85,
        }}>{match.time}</div>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 13, letterSpacing: 1.5, color: palette.ink, opacity: 0.85,
        }}>{match.venue.toUpperCase()}</div>
      </div>

      {/* Mosaic grid — shifted down */}
      <div style={{
        position: "absolute", left: 28, right: 28, top: 280, bottom: 80,
        display: "grid",
        gridTemplateColumns: "repeat(5, 1fr)",
        gridTemplateRows: "repeat(4, 1fr)",
        gap: 10,
      }}>
        {P.map((p, i) => {
          // Featured player gets a 2x2 tile at top-left (i === 0 after re-order)
          const isFeatured = i === 0;
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
        position: "absolute", left: 36, right: 36, bottom: 22,
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
          <div style={{
            display: "flex", alignItems: "center", gap: 6,
            fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.5, color: palette.ink, opacity: 0.7,
          }}>
            <span style={{ width: 14, height: 14, background: palette.accent }} /> BAT
          </div>
          <div style={{
            display: "flex", alignItems: "center", gap: 6,
            fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.5, color: palette.ink, opacity: 0.7,
          }}>
            <span style={{ width: 14, height: 14, background: palette.ink }} /> BOWL
          </div>
          <div style={{
            display: "flex", alignItems: "center", gap: 6,
            fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.5, color: palette.ink, opacity: 0.7,
          }}>
            <span style={{ width: 14, height: 14, background: palette.secondary, border: `1px solid ${palette.ink}55` }} /> ALL-ROUND
          </div>
        </div>
        <div style={{
          padding: "6px 12px", border: `1.5px solid ${palette.ink}55`,
          fontFamily: "'Anton', sans-serif", fontSize: 11, letterSpacing: 2,
          color: palette.ink, opacity: 0.8,
        }}>SPONSOR</div>
      </div>

      <GrainSVG opacity={0.28} id="g8" />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// TEMPLATE 9 — Festival flyer / tour poster
// Names stacked like a festival lineup with a strong typographic background.
// ─────────────────────────────────────────────────────────────
function T9_Flyer({ team, opponent, match, players, palette }) {
  const P = players.slice(0, 11);
  const tier1 = P.slice(0, 2);
  const tier2 = P.slice(2, 5);
  const tier3 = P.slice(5, 11);

  return (
    <div style={{
      width: 1080, height: 1080, position: "relative", overflow: "hidden",
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Halftone color={palette.ink} opacity={0.08} size={10} />
      <Stripes color={palette.accent} opacity={0.06} gap={20} angle={0} />

      {/* Background watermark — huge "XI" filling the upper third */}
      <div style={{
        position: "absolute", left: 0, right: 0, top: 130,
        textAlign: "center",
        fontFamily: "'Anton', sans-serif", fontSize: 520, lineHeight: 0.8,
        color: palette.accent, opacity: 0.07, letterSpacing: -10, userSelect: "none",
      }}>XI</div>

      {/* Corner ornaments */}
      <div style={{
        position: "absolute", left: 32, top: 32, width: 40, height: 40,
        borderTop: `3px solid ${palette.accent}`, borderLeft: `3px solid ${palette.accent}`,
      }} />
      <div style={{
        position: "absolute", right: 32, top: 32, width: 40, height: 40,
        borderTop: `3px solid ${palette.accent}`, borderRight: `3px solid ${palette.accent}`,
      }} />
      <div style={{
        position: "absolute", left: 32, bottom: 160, width: 40, height: 40,
        borderBottom: `3px solid ${palette.accent}`, borderLeft: `3px solid ${palette.accent}`,
      }} />
      <div style={{
        position: "absolute", right: 32, bottom: 160, width: 40, height: 40,
        borderBottom: `3px solid ${palette.accent}`, borderRight: `3px solid ${palette.accent}`,
      }} />

      {/* Top "presents" header */}
      <div style={{
        textAlign: "center", padding: "44px 40px 12px", position: "relative", zIndex: 2,
      }}>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 13, letterSpacing: 4,
          color: palette.accent, marginBottom: 14,
        }}>★ {match.competition} · {match.season} · PRESENTS ★</div>
        <div style={{
          display: "flex", justifyContent: "center", alignItems: "center", gap: 20,
        }}>
          <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={68} shape="shield" />
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 70, letterSpacing: 1,
            color: palette.ink, lineHeight: 1,
          }}>{team.name}</div>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 30, letterSpacing: 3,
            color: palette.accent, padding: "0 8px",
          }}>vs</div>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 46, letterSpacing: 1,
            color: palette.ink, lineHeight: 1, opacity: 0.85,
          }}>{opponent.name}</div>
          <ClubLogo src={opponent.logo} monogram={opponent.monogram} color={palette.ink} size={48} shape="shield" />
        </div>
      </div>

      {/* Decorative divider with stars */}
      <div style={{
        display: "flex", justifyContent: "center", alignItems: "center", gap: 12,
        margin: "8px 0 16px",
        fontFamily: "'Anton', sans-serif", fontSize: 18, letterSpacing: 6,
        color: palette.accent,
      }}>
        <span style={{ flex: "0 1 180px", height: 2, background: palette.accent, opacity: 0.5 }} />
        <span>★ ★ ★ THE LINEUP ★ ★ ★</span>
        <span style={{ flex: "0 1 180px", height: 2, background: palette.accent, opacity: 0.5 }} />
      </div>

      {/* Tier 1 — headliners */}
      <div style={{
        textAlign: "center", padding: "0 40px", lineHeight: 0.88,
        fontFamily: "'Anton', sans-serif", color: palette.ink, letterSpacing: -1,
      }}>
        <div style={{ fontSize: 108, marginBottom: 6 }}>
          {tier1.map((p, i) => (
            <React.Fragment key={i}>
              <span>{p.last}</span>
              {i < tier1.length - 1 && <span style={{ color: palette.accent, margin: "0 18px" }}>·</span>}
            </React.Fragment>
          ))}
        </div>
        {/* Tier 2 */}
        <div style={{ fontSize: 68, marginTop: 16, opacity: 0.95 }}>
          {tier2.map((p, i) => (
            <React.Fragment key={i}>
              <span>{p.last}</span>
              {i < tier2.length - 1 && <span style={{ color: palette.accent, margin: "0 16px" }}>·</span>}
            </React.Fragment>
          ))}
        </div>
        {/* Tier 3 — split into two lines for better balance */}
        <div style={{ fontSize: 40, marginTop: 18, opacity: 0.88, letterSpacing: 0 }}>
          <div>
            {tier3.slice(0, 3).map((p, i) => (
              <React.Fragment key={i}>
                <span>{p.last}</span>
                {i < 2 && <span style={{ color: palette.accent, margin: "0 14px", opacity: 0.7 }}>·</span>}
              </React.Fragment>
            ))}
          </div>
          <div style={{ marginTop: 6 }}>
            {tier3.slice(3).map((p, i) => (
              <React.Fragment key={i}>
                <span>{p.last}</span>
                {i < tier3.slice(3).length - 1 && <span style={{ color: palette.accent, margin: "0 14px", opacity: 0.7 }}>·</span>}
              </React.Fragment>
            ))}
          </div>
        </div>
      </div>

      {/* Bottom band */}
      <div style={{
        position: "absolute", left: 0, right: 0, bottom: 0,
        background: palette.accent, color: palette.primary,
        padding: "22px 40px",
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <div>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 40, letterSpacing: 1, lineHeight: 1,
          }}>{match.date}</div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 1.5, marginTop: 4,
          }}>GATES {match.time}</div>
        </div>
        <div style={{ textAlign: "center" }}>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 32, letterSpacing: 2, lineHeight: 1,
          }}>{match.venue.toUpperCase()}</div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.5, marginTop: 4,
          }}>{match.round}</div>
        </div>
        <div style={{
          padding: "10px 16px", border: `2px solid ${palette.primary}`,
          fontFamily: "'Anton', sans-serif", fontSize: 14, letterSpacing: 2,
        }}>SPONSOR</div>
      </div>

      <GrainSVG opacity={0.4} id="g9" />
    </div>
  );
}

Object.assign(window, { T7_CaptainSpotlight, T8_Mosaic, T9_Flyer });
