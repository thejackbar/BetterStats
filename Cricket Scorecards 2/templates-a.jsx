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
      {/* Vertical "CRICKET CLUB" branding strip on the far left */}
      <div style={{
        position: "absolute", left: 0, top: 0, bottom: 0, width: 56,
        background: palette.secondary,
        borderRight: `1px solid ${palette.ink}1a`,
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        <div style={{
          transform: "rotate(-90deg)",
          whiteSpace: "nowrap",
          fontFamily: "'Anton', sans-serif", fontSize: 22, letterSpacing: 8,
          color: palette.ink, opacity: 0.7,
        }}>{(team.fullName || team.name).toUpperCase()}</div>
      </div>

      {/* Full club name as huge faded vertical type behind the player */}
      <div style={{
        position: "absolute", left: 70, top: 80,
        fontFamily: "'Anton', sans-serif", fontSize: 160, lineHeight: 0.88,
        color: palette.ink, opacity: 0.06, letterSpacing: -2, userSelect: "none",
        maxWidth: 540,
      }}>{(team.fullName || team.name + " CRICKET CLUB").toUpperCase()}</div>

      <Halftone color={palette.ink} opacity={0.08} size={12} />
      <Stripes color={palette.ink} opacity={0.04} gap={20} angle={-30} />

      {/* Left — player image area */}
      <div style={{
        position: "absolute", left: 56, top: 0, width: 564, height: 1080,
        display: "grid", placeItems: "end center", overflow: "hidden",
      }}>
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

      {/* Top-left — Match Day info (moved from footer) */}
      <div style={{
        position: "absolute", left: 80, top: 40, zIndex: 5,
        fontFamily: "'Anton', sans-serif", letterSpacing: 3,
        color: palette.ink, lineHeight: 1.1, maxWidth: 240,
      }}>
        <div style={{ background: palette.accent, color: palette.primary, padding: "4px 10px", display: "inline-block", fontSize: 16 }}>MATCH DAY</div>
        <div style={{ marginTop: 10, fontSize: 16 }}>{match.venue.toUpperCase()}</div>
        <div style={{ opacity: 0.65, marginTop: 2, fontSize: 14, fontFamily: "'JetBrains Mono', monospace", letterSpacing: 1.5 }}>{match.date} · {match.time}</div>
      </div>

      {/* Right — content panel */}
      <div style={{
        position: "absolute", right: 40, top: 56, width: 480,
      }}>
        {/* Comp ribbon */}
        <div style={{
          display: "flex", justifyContent: "flex-end", alignItems: "flex-start",
        }}>
          <div style={{ textAlign: "right" }}>
            <div style={{
              fontFamily: "'Anton', sans-serif", fontSize: 22, letterSpacing: 2,
              color: palette.ink, opacity: 0.85, lineHeight: 1,
            }}>{match.competition}</div>
            <div style={{
              fontFamily: "'JetBrains Mono', monospace", fontSize: 12, letterSpacing: 1.5,
              color: palette.accent, marginTop: 6,
            }}>{match.season}</div>
          </div>
        </div>

        {/* SQUAD title */}
        <div style={{
          fontFamily: "'Anton', sans-serif", fontSize: 180, lineHeight: 0.85,
          letterSpacing: -2, marginTop: 28, color: palette.ink,
        }}>SQUAD</div>
        <div style={{
          width: 60, height: 4, background: palette.accent, marginTop: 10, marginBottom: 24,
        }} />

        {/* Versus row — names larger, logos slightly smaller */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "flex-end",
          gap: 16, marginBottom: 26, flexWrap: "wrap",
        }}>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontFamily: "'Anton', sans-serif", fontSize: 30, letterSpacing: 1.5, lineHeight: 1 }}>{team.name}</div>
          </div>
          <ClubLogo src={team.logo} monogram={team.monogram} color={palette.accent} size={52} shape="shield" />
          <div style={{ fontFamily: "'Anton', sans-serif", fontSize: 22, opacity: 0.7 }}>V</div>
          <ClubLogo src={opponent.logo} monogram={opponent.monogram} color={palette.ink} size={52} shape="shield" />
          <div style={{ textAlign: "left" }}>
            <div style={{ fontFamily: "'Anton', sans-serif", fontSize: 30, letterSpacing: 1.5, lineHeight: 1 }}>{opponent.name}</div>
          </div>
        </div>

        {/* Names */}
        <div style={{ display: "flex", flexDirection: "column", gap: 1, textAlign: "right" }}>
          {P.map((p, i) => {
            const chip = p.captain ? "C" : p.viceCaptain ? "VC" : p.keeper ? "WK" : null;
            return (
              <div key={i} style={{
                fontFamily: "'Anton', sans-serif", fontSize: 40, lineHeight: 1.05,
                letterSpacing: 0.5, color: palette.ink,
                display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 10,
              }}>
                <span style={{ fontWeight: 300, opacity: 0.72, fontSize: 30 }}>{p.first.toUpperCase()}</span>
                <span style={{ color: palette.ink }}>{p.last}</span>
                {chip && <RoleChip kind={chip} accent={palette.accent} ink={palette.primary} />}
              </div>
            );
          })}
        </div>
      </div>

      {/* Footer — sponsor only (match day moved to top-left) */}
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

      {/* Big rotated wordmark in the background */}
      <div style={{
        position: "absolute", left: -50, bottom: -60,
        fontFamily: "'Anton', sans-serif", fontSize: 320, lineHeight: 0.8,
        color: palette.ink, opacity: 0.04, letterSpacing: -6,
        transform: "rotate(-8deg)", userSelect: "none", whiteSpace: "nowrap",
      }}>LINEUP</div>
      {/* Concentric arcs in the corners */}
      <svg style={{ position: "absolute", left: -180, top: -180, width: 560, height: 560, opacity: 0.08 }}>
        <circle cx="280" cy="280" r="260" fill="none" stroke={palette.ink} strokeWidth="2" />
        <circle cx="280" cy="280" r="200" fill="none" stroke={palette.ink} strokeWidth="2" />
        <circle cx="280" cy="280" r="140" fill="none" stroke={palette.ink} strokeWidth="2" />
      </svg>
      <svg style={{ position: "absolute", right: -160, bottom: -160, width: 480, height: 480, opacity: 0.06 }}>
        <circle cx="240" cy="240" r="220" fill="none" stroke={palette.accent} strokeWidth="3" />
        <circle cx="240" cy="240" r="160" fill="none" stroke={palette.accent} strokeWidth="3" />
      </svg>
      {/* Diagonal accent bar bottom-left */}
      <div style={{
        position: "absolute", left: -40, bottom: 80, width: 240, height: 4,
        background: palette.accent, transform: "rotate(-30deg)", opacity: 0.7,
      }} />

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

      {/* Extra graphical elements across the top */}
      {/* Dotted scatter top-left */}
      <svg style={{ position: "absolute", left: 40, top: 16, width: 220, height: 60, opacity: 0.55 }}>
        {Array.from({ length: 36 }).map((_, i) => (
          <circle key={i} cx={(i % 12) * 18 + 6} cy={Math.floor(i / 12) * 18 + 6} r={2.4}
                  fill={palette.accent} />
        ))}
      </svg>
      {/* Horizontal accent rule with dot */}
      <div style={{
        position: "absolute", left: 260, top: 36, width: 220, height: 3,
        background: palette.accent, opacity: 0.7,
      }} />
      <div style={{
        position: "absolute", left: 482, top: 30, width: 14, height: 14,
        background: palette.accent, borderRadius: "50%",
      }} />
      {/* Ticker mark column */}
      <div style={{
        position: "absolute", left: 40, top: 90, display: "flex", gap: 6, alignItems: "center",
      }}>
        {[20, 32, 14, 28, 22, 36, 18, 26].map((h, i) => (
          <div key={i} style={{ width: 5, height: h, background: palette.accent, opacity: 0.6 }} />
        ))}
      </div>
      {/* Subtle plus marks scattered */}
      <svg style={{ position: "absolute", left: 0, top: 0, width: 1080, height: 360, opacity: 0.18, pointerEvents: "none" }}>
        {[[140, 220], [340, 180], [560, 130], [720, 240], [880, 90]].map(([x, y], i) => (
          <g key={i} stroke={palette.ink} strokeWidth="1.5">
            <line x1={x - 8} y1={y} x2={x + 8} y2={y} />
            <line x1={x} y1={y - 8} x2={x} y2={y + 8} />
          </g>
        ))}
      </svg>
      {/* Thin diagonal hash bars top-right */}
      <svg style={{ position: "absolute", right: 0, top: 160, width: 320, height: 80, opacity: 0.5 }}>
        {Array.from({ length: 8 }).map((_, i) => (
          <line key={i} x1={i * 40} y1={80} x2={i * 40 + 60} y2={0}
                stroke={palette.accent} strokeWidth="2" />
        ))}
      </svg>

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
            fontFamily: "'Anton', sans-serif", fontSize: 30, letterSpacing: 2,
            color: palette.ink, opacity: 0.95,
          }}>{team.name} <span style={{ opacity: 0.5 }}>×</span> {opponent.name}</div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 16, letterSpacing: 1.8,
            color: palette.accent, marginTop: 10, fontWeight: 500,
          }}>{match.round} · {match.date} · {match.time}</div>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 14, letterSpacing: 1.5,
            color: palette.ink, opacity: 0.7, marginTop: 4,
          }}>{match.venue.toUpperCase()}</div>
        </div>
        <ClubLogo src={team.logo} monogram={team.monogram} color={palette.ink} size={100} shape="shield" />
      </div>

      {/* Card grid */}
      <div style={{
        position: "absolute", left: 56, right: 56, top: 380, bottom: 100,
        display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gridTemplateRows: "repeat(3, 1fr)",
        gap: 14,
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
                padding: "10px 10px", textAlign: "center",
                fontFamily: "'Anton', sans-serif", fontSize: 26, letterSpacing: 1,
                lineHeight: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
              }}>{p.last}</div>
            </div>
          );
        })}
      </div>

      {/* Footer — sponsor only (venue moved to header) */}
      <div style={{
        position: "absolute", left: 56, right: 56, bottom: 32,
        display: "flex", justifyContent: "flex-end", alignItems: "center",
      }}>
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
      {/* Left image panel — player cutout fills the full strip */}
      <div style={{
        position: "absolute", left: 0, top: 0, width: 380, height: 1080,
        background: `linear-gradient(180deg, ${palette.secondary} 0%, ${palette.primary} 100%)`,
        overflow: "hidden",
      }}>
        <Halftone color={palette.ink} opacity={0.1} size={8} />
        {/* Soft accent glow behind player */}
        <div style={{
          position: "absolute", left: -120, bottom: -120, width: 600, height: 600,
          background: `radial-gradient(circle at center, ${palette.accent}33 0%, transparent 60%)`,
        }} />
        {(() => {
          const featured = featuredOf(players);
          const hasHead = !!(featured && featured.headshot);
          const src = hasHead ? featured.headshot : team.logo;
          return (
            <img
              src={src}
              alt={featured ? (featured.first + " " + featured.last) : team.short}
              style={{
                position: "absolute", inset: 0,
                width: "100%", height: "100%",
                objectFit: hasHead ? "cover" : "contain",
                objectPosition: hasHead ? "top center" : "center",
                padding: hasHead ? 0 : 80,
              }}
            />
          );
        })()}
        {/* Bottom gradient fade so text on top reads */}
        <div style={{
          position: "absolute", left: 0, right: 0, bottom: 0, height: 240,
          background: `linear-gradient(180deg, transparent 0%, ${palette.primary}ee 100%)`,
        }} />
        {/* Featured player name strip at bottom of image */}
        {(() => {
          const featured = featuredOf(players);
          if (!featured) return null;
          const chip = featured.captain ? "C" : featured.viceCaptain ? "VC" : featured.keeper ? "WK" : null;
          return (
            <div style={{
              position: "absolute", left: 16, right: 16, bottom: 22, zIndex: 2,
            }}>
              <div style={{
                fontFamily: "'Anton', sans-serif", fontSize: 20, letterSpacing: 1,
                color: palette.ink, opacity: 0.78, lineHeight: 1,
              }}>{featured.first.toUpperCase()}</div>
              <div style={{
                fontFamily: "'Anton', sans-serif", fontSize: 44, letterSpacing: 0.5,
                color: palette.ink, lineHeight: 1, marginTop: 2,
                display: "flex", alignItems: "baseline", gap: 8,
              }}>
                <span>{featured.last}</span>
                {chip && <RoleChip kind={chip} accent={palette.accent} ink={palette.primary} />}
              </div>
            </div>
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
          color: palette.ink, opacity: 0.7, marginBottom: 4,
        }}>{match.competition} · {match.round} · {match.date}</div>
        <div style={{
          textAlign: "center",
          fontFamily: "'Anton', sans-serif", fontSize: 16, letterSpacing: 2,
          color: palette.accent, marginBottom: 22, lineHeight: 1,
        }}>{match.venue.toUpperCase()}</div>

        {/* Numbered list */}
        <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1 }}>
          {P.map((p, i) => {
            const chip = p.captain ? "C" : p.viceCaptain ? "VC" : p.keeper ? "WK" : null;
            return (
              <div key={i} style={{
                display: "flex", alignItems: "center", gap: 12, padding: "7px 0",
                borderBottom: `1px solid ${palette.ink}1c`,
              }}>
                <div style={{
                  fontFamily: "'Anton', sans-serif", fontSize: 42,
                  color: palette.accent, lineHeight: 1, width: 50, textAlign: "right",
                  flexShrink: 0,
                }}>{i + 1}</div>
                <div style={{
                  flex: 1, display: "flex", alignItems: "baseline", gap: 10,
                  whiteSpace: "nowrap", overflow: "hidden",
                }}>
                  <span style={{
                    fontFamily: "'Anton', sans-serif", fontSize: 28,
                    color: palette.ink, opacity: 0.65, fontWeight: 300, letterSpacing: 0.5,
                  }}>{p.first.toUpperCase()}</span>
                  <span style={{
                    fontFamily: "'Anton', sans-serif", fontSize: 38, letterSpacing: 0.5,
                    color: palette.ink, lineHeight: 1,
                  }}>{p.last}</span>
                </div>
                {chip && <RoleChip kind={chip} accent={palette.accent} ink={palette.primary} />}
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div style={{
          display: "flex", justifyContent: "flex-end", alignItems: "center",
          marginTop: 12, paddingTop: 10, borderTop: `2px solid ${palette.accent}`,
        }}>
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
