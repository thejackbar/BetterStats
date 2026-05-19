// Templates 1–3: Hero+List, Trading Card Grid, Side Image + Numbered XI
// All artboards are 1080×1080. Each takes ({ team, opponent, match, players, palette }).

// ─────────────────────────────────────────────────────────────
// TEMPLATE 1 — Hero cutout + bold name list
// Inspired by squad-announce posters: big player area on the left,
// match meta + name list right.
// ─────────────────────────────────────────────────────────────
function T1_HeroList({ team, opponent, match, players, palette }) {
  const P = players.slice(0, 13);
  return (
    <div style={{
      width: 1080, height: 1080, position: "relative", overflow: "hidden",
      background: `linear-gradient(135deg, ${palette.primary} 0%, ${palette.secondary} 100%)`,
      color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      {/* huge faded monogram behind everything */}
      <div style={{
        position: "absolute", left: -120, top: 60,
        fontFamily: "'Anton', sans-serif", fontSize: 900, lineHeight: 0.8,
        color: palette.ink, opacity: 0.04, letterSpacing: -20, userSelect: "none",
      }}>{team.monogram}</div>

      <Halftone color={palette.ink} opacity={0.08} size={12} />
      <Stripes color={palette.ink} opacity={0.04} gap={20} angle={-30} />

      {/* Left — player image area */}
      <div style={{
        position: "absolute", left: 0, top: 0, width: 620, height: 1080,
        display: "grid", placeItems: "end center", overflow: "hidden",
      }}>
        {/* Giant accent monogram sits behind the cutout */}
        <div style={{
          position: "absolute", left: -30, top: 140,
          fontFamily: "'Anton', sans-serif", fontSize: 520, lineHeight: 0.8,
          color: palette.accent, opacity: 0.18, letterSpacing: -10, userSelect: "none",
        }}>{team.monogram}</div>
        {/* Accent diagonal slash behind player */}
        <div style={{
          position: "absolute", left: -100, bottom: -100, width: 700, height: 700,
          background: `radial-gradient(circle at 40% 40%, ${palette.accent}33 0%, transparent 60%)`,
        }} />
        {/* Player cutout — falls back to club logo when no headshot */}
        {(() => {
          const featured = featuredOf(players);
          const hasHead = !!(featured && featured.headshot);
          const src = hasHead ? featured.headshot : team.logo;
          return (
            <img
              src={src}
              alt={featured ? (featured.first + " " + featured.last) : team.short}
              style={{
                position: "relative",
                height: hasHead ? 980 : 460,
                width: "auto", marginBottom: hasHead ? -20 : 200,
                objectFit: "contain", objectPosition: "bottom",
                filter: `drop-shadow(0 30px 60px ${palette.primary}cc)`,
              }}
            />
          );
        })()}
      </div>

      {/* Right — content panel */}
      <div style={{
        position: "absolute", right: 40, top: 56, width: 480,
      }}>
        {/* Comp ribbon */}
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "flex-start",
        }}>
          <div>
            <div style={{
              fontFamily: "'Anton', sans-serif", fontSize: 22, letterSpacing: 2,
              color: palette.ink, opacity: 0.85, lineHeight: 1,
            }}>{match.competition}</div>
            <div style={{
              fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 1.5,
              color: palette.accent, marginTop: 6,
            }}>{match.season}</div>
          </div>
          <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={64} shape="shield" />
        </div>

        {/* SQUAD title */}
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 180, lineHeight: 0.85,
          letterSpacing: -2, marginTop: 28, color: palette.ink,
        }}>SQUAD</div>
        <div style={{
          width: 60, height: 4, background: palette.accent, marginTop: 10, marginBottom: 24,
        }} />

        {/* Versus row */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "flex-end",
          gap: 24, marginBottom: 26,
        }}>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontFamily: "'Anton', sans-serif", fontSize: 18, letterSpacing: 1.5 }}>{team.name}</div>
          </div>
          <ClubLogo src={team.logo} monogram={team.monogram} color={palette.accent} size={64} shape="shield" />
          <div style={{ fontFamily: "'Anton', sans-serif", fontSize: 22, opacity: 0.7 }}>V</div>
          <ClubLogo src={opponent.logo} monogram={opponent.monogram} color={palette.ink} size={64} shape="shield" />
          <div style={{ textAlign: "left" }}>
            <div style={{ fontFamily: "'Anton', sans-serif", fontSize: 18, letterSpacing: 1.5 }}>{opponent.name}</div>
          </div>
        </div>

        {/* Names */}
        <div style={{ display: "flex", flexDirection: "column", gap: 4, textAlign: "right" }}>
          {P.map((p, i) => {
            const chip = p.captain ? "C" : p.viceCaptain ? "VC" : p.keeper ? "WK" : null;
            return (
              <div key={i} style={{
                fontFamily: "'Anton', sans-serif", fontSize: 30, lineHeight: 1.05,
                letterSpacing: 0.5, color: palette.ink,
                display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 8,
              }}>
                <span style={{ fontWeight: 300, opacity: 0.78 }}>{p.first.toUpperCase()}</span>
                <span style={{ color: palette.ink }}>{p.last}</span>
                {chip && <RoleChip kind={chip} accent={palette.accent} ink={palette.primary} />}
              </div>
            );
          })}
        </div>
      </div>

      {/* Footer */}
      <div style={{
        position: "absolute", left: 40, bottom: 36,
        fontFamily: "'Anton', sans-serif", fontSize: 14, letterSpacing: 3,
        color: palette.ink, opacity: 0.8, lineHeight: 1.1, maxWidth: 180,
      }}>
        <div style={{ background: palette.accent, color: palette.primary, padding: "3px 8px", display: "inline-block" }}>MATCH DAY</div>
        <div style={{ marginTop: 8 }}>{match.venue}</div>
        <div style={{ opacity: 0.6, marginTop: 2 }}>{match.date} · {match.time}</div>
      </div>
      <div style={{
        position: "absolute", right: 40, bottom: 36,
        display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6,
      }}>
        <div style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 10,
          color: palette.ink, opacity: 0.5, letterSpacing: 1.5,
        }}>SPONSOR</div>
        <div style={{
          padding: "10px 18px", border: `1.5px solid ${palette.ink}55`,
          fontFamily: "'Anton', sans-serif", fontSize: 14, letterSpacing: 2,
          color: palette.ink, opacity: 0.8,
        }}>YOUR LOGO</div>
      </div>

      <GrainSVG opacity={0.35} id="g1" />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// TEMPLATE 2 — Trading card grid (4×3 of 12 cards, or 3×3 + header for 11)
// ─────────────────────────────────────────────────────────────
function T2_CardGrid({ team, opponent, match, players, palette }) {
  const P = players.slice(0, 12); // 4 columns × 3 rows
  return (
    <div style={{
      width: 1080, height: 1080, position: "relative", overflow: "hidden",
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      <Halftone color={palette.ink} opacity={0.05} size={10} />
      <Stripes color={palette.accent} opacity={0.04} gap={30} angle={45} />

      {/* paint splatter / brush stripe accents */}
      <div style={{
        position: "absolute", top: -20, right: -40, width: 380, height: 180,
        background: palette.accent, opacity: 0.9,
        clipPath: "polygon(0% 30%, 100% 0%, 100% 70%, 18% 100%)",
      }} />
      <div style={{
        position: "absolute", top: 30, right: 60, width: 4, height: 80,
        background: palette.primary,
      }} />

      {/* Header */}
      <div style={{
        position: "relative", padding: "44px 56px 0", display: "flex",
        justifyContent: "space-between", alignItems: "flex-start", zIndex: 2,
      }}>
        <div>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 96, lineHeight: 0.85,
            color: palette.ink, letterSpacing: -1,
          }}>LINEUP</div>
          <div style={{
            width: 84, height: 4, background: palette.accent, margin: "10px 0 14px",
          }} />
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 22, letterSpacing: 2,
            color: palette.ink, opacity: 0.9,
          }}>{team.name} <span style={{ opacity: 0.5 }}>×</span> {opponent.name}</div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 1.5,
            color: palette.accent, marginTop: 6,
          }}>{match.round} · {match.date} · {match.time}</div>
        </div>
        <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={100} shape="shield" />
      </div>

      {/* Card grid */}
      <div style={{
        position: "absolute", left: 56, right: 56, top: 340, bottom: 110,
        display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gridTemplateRows: "repeat(3, 1fr)",
        gap: 16,
      }}>
        {P.map((p, i) => {
          const chip = p.captain ? "C" : p.viceCaptain ? "VC" : p.keeper ? "WK" : null;
          return (
            <div key={i} style={{
              position: "relative", overflow: "hidden",
              background: `linear-gradient(180deg, ${palette.secondary} 0%, ${palette.primary} 100%)`,
              border: `2px solid ${palette.accent}`,
              display: "flex", flexDirection: "column",
            }}>
              {/* Card photo area */}
              <div style={{
                flex: 1, display: "grid", placeItems: "center", position: "relative", overflow: "hidden",
              }}>
                <Halftone color={palette.ink} opacity={0.08} size={6} />
                {p.headshot ? (
                  <img src={p.headshot} alt={p.first + " " + p.last}
                    style={{
                      width: "100%", height: "100%", objectFit: "cover", objectPosition: "top center",
                    }} />
                ) : team.logo ? (
                  <img src={team.logo} alt={team.short}
                    style={{ width: "68%", height: "68%", objectFit: "contain", opacity: 0.92 }} />
                ) : (
                  <div style={{
                    fontFamily: "'Anton', sans-serif", fontSize: 96, color: palette.accent,
                    opacity: 0.85, letterSpacing: -2, lineHeight: 1,
                  }}>{team.monogram}</div>
                )}
                {chip && (
                  <div style={{ position: "absolute", top: 8, right: 8 }}>
                    <RoleChip kind={chip} accent={palette.accent} ink={palette.primary} />
                  </div>
                )}
                <div style={{
                  position: "absolute", top: 8, left: 8,
                  fontFamily: "'JetBrains Mono', monospace", fontSize: 9,
                  color: palette.ink, opacity: 0.4, letterSpacing: 1.5,
                }}>#{String(i + 1).padStart(2, "0")}</div>
              </div>
              {/* Name strip */}
              <div style={{
                background: palette.accent, color: palette.primary,
                padding: "8px 10px", textAlign: "center",
                fontFamily: "'Anton', sans-serif", fontSize: 22, letterSpacing: 1,
                lineHeight: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
              }}>{p.last}</div>
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div style={{
        position: "absolute", left: 56, right: 56, bottom: 32,
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 16, letterSpacing: 2,
          color: palette.ink, opacity: 0.7,
        }}>{match.venue.toUpperCase()}</div>
        <div style={{
          padding: "10px 18px", border: `1.5px solid ${palette.ink}55`,
          fontFamily: "'Anton', sans-serif", fontSize: 14, letterSpacing: 2,
          color: palette.ink, opacity: 0.8,
        }}>SPONSOR LOGO</div>
      </div>

      <GrainSVG opacity={0.4} id="g2" />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// TEMPLATE 3 — Side image + numbered XI
// Inspired by "POSSIBLE XI" posters: vertical photo strip left,
// header + numbered list right.
// ─────────────────────────────────────────────────────────────
function T3_SideNumbered({ team, opponent, match, players, palette }) {
  const P = players.slice(0, 11);
  return (
    <div style={{
      width: 1080, height: 1080, position: "relative", overflow: "hidden",
      background: palette.primary, color: palette.ink, fontFamily: "'Inter', sans-serif",
    }}>
      {/* Background flowing wave shapes */}
      <svg width="1080" height="1080" style={{ position: "absolute", inset: 0 }}>
        <defs>
          <linearGradient id="bgwv" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor={palette.primary} />
            <stop offset="1" stopColor={palette.secondary} />
          </linearGradient>
        </defs>
        <rect width="1080" height="1080" fill="url(#bgwv)" />
        <path d="M 900 0 C 1050 200 950 400 1080 600 L 1080 0 Z" fill={palette.ink} opacity="0.04" />
        <path d="M 1000 1080 C 850 900 1100 700 980 500 L 1080 500 L 1080 1080 Z" fill={palette.accent} opacity="0.06" />
      </svg>

      {/* Left image panel */}
      <div style={{
        position: "absolute", left: 0, top: 0, width: 380, height: 1080,
        background: `linear-gradient(180deg, ${palette.secondary} 0%, ${palette.primary} 100%)`,
        display: "grid", placeItems: "end center", overflow: "hidden",
      }}>
        <Halftone color={palette.ink} opacity={0.1} size={8} />
        {/* faded monogram behind cutout */}
        <div style={{
          position: "absolute", left: -20, top: 60,
          fontFamily: "'Anton', sans-serif", fontSize: 360, lineHeight: 0.8,
          color: palette.accent, opacity: 0.18, letterSpacing: -8, userSelect: "none",
        }}>{team.monogram}</div>
        {(() => {
          const featured = featuredOf(players);
          const hasHead = !!(featured && featured.headshot);
          const src = hasHead ? featured.headshot : team.logo;
          return (
            <img
              src={src}
              alt={featured ? (featured.first + " " + featured.last) : team.short}
              style={{
                position: "relative",
                width: hasHead ? 360 : 260,
                height: "auto",
                maxHeight: 880, objectFit: "contain", objectPosition: "bottom",
                marginBottom: hasHead ? 40 : 220,
                filter: `drop-shadow(0 20px 40px ${palette.primary}cc)`,
              }}
            />
          );
        })()}
      </div>

      {/* Rotated "STARTING XI" */}
      <div style={{
        position: "absolute", left: 360, top: 540,
        transform: "rotate(-90deg)", transformOrigin: "left top",
        fontFamily: "'Anton', sans-serif", fontSize: 80, letterSpacing: 4,
        color: "transparent", WebkitTextStroke: `2px ${palette.accent}`,
        whiteSpace: "nowrap", lineHeight: 0.8,
      }}>STARTING XI</div>

      {/* Right side */}
      <div style={{
        position: "absolute", left: 460, top: 60, right: 40, bottom: 40,
        display: "flex", flexDirection: "column",
      }}>
        {/* Top: VS */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "center",
          gap: 28, marginBottom: 28,
        }}>
          <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={110} shape="circle" />
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 28, letterSpacing: 3,
            color: palette.accent,
          }}>VS</div>
          <ClubLogo src={opponent.logo} monogram={opponent.monogram} color={palette.ink} size={110} shape="circle" />
        </div>

        {/* Match strip */}
        <div style={{
          textAlign: "center",
          fontFamily: "'JetBrains Mono', monospace", fontSize: 11, letterSpacing: 1.8,
          color: palette.ink, opacity: 0.7, marginBottom: 22,
        }}>{match.competition} · {match.round} · {match.date}</div>

        {/* Numbered list */}
        <div style={{ display: "flex", flexDirection: "column", gap: 6, flex: 1 }}>
          {P.map((p, i) => {
            const chip = p.captain ? "C" : p.viceCaptain ? "VC" : p.keeper ? "WK" : null;
            return (
              <div key={i} style={{
                display: "grid", gridTemplateColumns: "50px 1fr 60px", alignItems: "center",
                gap: 14, padding: "6px 0",
                borderBottom: `1px solid ${palette.ink}1c`,
              }}>
                <div style={{
                  fontFamily: "'Anton', sans-serif", fontSize: 36,
                  color: palette.accent, lineHeight: 1, textAlign: "right",
                }}>{i + 1}</div>
                <div style={{
                  fontFamily: "'Anton', sans-serif", fontSize: 30, letterSpacing: 1,
                  color: palette.ink, lineHeight: 1.1, whiteSpace: "nowrap",
                }}>{p.last}</div>
                <div style={{ display: "flex", justifyContent: "flex-end" }}>
                  {chip && <RoleChip kind={chip} accent={palette.accent} ink={palette.primary} />}
                </div>
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          marginTop: 12, paddingTop: 10, borderTop: `2px solid ${palette.accent}`,
        }}>
          <div style={{
            fontFamily: "'Anton', sans-serif", fontSize: 12, letterSpacing: 2,
            color: palette.ink, opacity: 0.7,
          }}>{match.venue.toUpperCase()}</div>
          <div style={{
            padding: "6px 12px", border: `1.5px solid ${palette.ink}55`,
            fontFamily: "'Anton', sans-serif", fontSize: 11, letterSpacing: 2,
            color: palette.ink, opacity: 0.7,
          }}>SPONSOR</div>
        </div>
      </div>

      <GrainSVG opacity={0.3} id="g3" />
    </div>
  );
}

Object.assign(window, { T1_HeroList, T2_CardGrid, T3_SideNumbered });
