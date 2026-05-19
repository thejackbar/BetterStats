// Reusable visual primitives: textures, halftones, grain, captain chips, club logos.
// These are dumb components — they take props and render. No state.

// SVG noise/grain — applied as a CSS filter overlay for gritty texture.
function GrainSVG({ opacity = 0.35, id = "grain" }) {
  return (
    <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none", mixBlendMode: "overlay", opacity }}>
      <filter id={id}>
        <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch" />
        <feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.55 0" />
      </filter>
      <rect width="100%" height="100%" filter={`url(#${id})`} />
    </svg>
  );
}

// Halftone dot field — radial-gradient based, scales with size prop
function Halftone({ color = "#fff", size = 14, opacity = 0.12, angle = 0, style = {} }) {
  return (
    <div style={{
      position: "absolute", inset: 0, pointerEvents: "none", opacity,
      backgroundImage: `radial-gradient(${color} 1.2px, transparent 1.6px)`,
      backgroundSize: `${size}px ${size}px`,
      transform: `rotate(${angle}deg) scale(1.4)`,
      transformOrigin: "center",
      ...style,
    }} />
  );
}

// Diagonal stripes overlay
function Stripes({ color = "#fff", angle = -45, gap = 14, opacity = 0.06, style = {} }) {
  return (
    <div style={{
      position: "absolute", inset: 0, pointerEvents: "none", opacity,
      backgroundImage: `repeating-linear-gradient(${angle}deg, ${color} 0 1px, transparent 1px ${gap}px)`,
      ...style,
    }} />
  );
}

// Club logo placeholder — a chunky monogram in a hex or shield.
// In production, replace internals with <img src={teamLogoUrl} />.
function ClubLogo({ monogram = "NG", color = "#fff", bg = "transparent", size = 120, shape = "shield", src = null }) {
  // If we have a real image, render that and ignore monogram/shape decorations
  if (src) {
    return (
      <img src={src} alt={monogram + " logo"}
        style={{ width: size, height: size, objectFit: "contain", display: "block" }} />
    );
  }
  const stroke = Math.max(2, size * 0.04);
  const fontSize = size * 0.42;
  if (shape === "circle") {
    return (
      <div style={{
        width: size, height: size, borderRadius: "50%",
        background: bg, border: `${stroke}px solid ${color}`,
        display: "grid", placeItems: "center", color,
        fontFamily: "'Anton', sans-serif", fontSize, letterSpacing: 1,
      }}>{monogram}</div>
    );
  }
  // Shield
  return (
    <svg width={size} height={size * 1.08} viewBox="0 0 100 108" style={{ display: "block" }}>
      <path d="M5 8 L50 0 L95 8 L92 60 Q88 88 50 104 Q12 88 8 60 Z"
        fill={bg === "transparent" ? "none" : bg}
        stroke={color} strokeWidth="3" />
      <text x="50" y="62" textAnchor="middle"
        fontFamily="'Anton', sans-serif" fontSize="38" fill={color} letterSpacing="1">{monogram}</text>
    </svg>
  );
}

// Captain / VC / WK chip — colored badge next to a player name
function RoleChip({ kind, accent = "#ffc233", ink = "#0b1530" }) {
  if (!kind) return null;
  const labels = { C: "C", VC: "VC", WK: "WK" };
  const label = labels[kind];
  if (!label) return null;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      minWidth: 32, height: 24, padding: "0 8px",
      background: accent, color: ink,
      fontFamily: "'Anton', sans-serif", fontSize: 16, fontWeight: 400,
      letterSpacing: 1, lineHeight: 1, borderRadius: 2,
      verticalAlign: "middle",
    }}>{label}</span>
  );
}

// Player silhouette placeholder — used when no headshot exists.
// Falls back to a big club monogram + role label.
function PlayerSilhouette({ team, role, ink = "#fff", style = {} }) {
  return (
    <div style={{
      position: "relative", width: "100%", height: "100%",
      display: "grid", placeItems: "center",
      ...style,
    }}>
      <div style={{
        fontFamily: "'Anton', sans-serif",
        fontSize: "min(60%, 280px)",
        lineHeight: 0.85,
        color: ink,
        opacity: 0.18,
        letterSpacing: -2,
        userSelect: "none",
      }}>{team.monogram}</div>
    </div>
  );
}

// vs separator block
function VsBlock({ accent = "#ffc233", ink = "#fff", size = 18 }) {
  return (
    <div style={{
      fontFamily: "'Anton', sans-serif", fontSize: size, color: ink,
      letterSpacing: 2, opacity: 0.85,
    }}>VS</div>
  );
}

// Player image with intelligent fallback:
//   1. player.headshot (transparent-bg cutout URL)
//   2. team.logo (club shield)
//   3. team monogram letterform
// Use `fit="contain"` for cutouts (preserve aspect), `cover` for cropping to box.
function PlayerImage({ player, team, palette, fit = "contain", size = 200, style = {} }) {
  if (player && player.headshot) {
    return (
      <img src={player.headshot} alt={(player.first || "") + " " + (player.last || "")}
        style={{
          width: "100%", height: "100%", objectFit: fit, objectPosition: "bottom",
          ...style,
        }} />
    );
  }
  if (team && team.logo) {
    return (
      <div style={{
        width: "100%", height: "100%", display: "grid", placeItems: "center",
        ...style,
      }}>
        <img src={team.logo} alt={team.short || "club"}
          style={{ width: "65%", height: "65%", objectFit: "contain", opacity: 0.92 }} />
      </div>
    );
  }
  return (
    <div style={{
      width: "100%", height: "100%", display: "grid", placeItems: "center",
      fontFamily: "'Anton', sans-serif", fontSize: size * 0.5, color: (palette && palette.accent) || "#fff",
      opacity: 0.85, letterSpacing: -2, lineHeight: 1, ...style,
    }}>{(team && team.monogram) || "?"}</div>
  );
}

// Find the featured player for hero templates (captain by default).
function featuredOf(players) {
  if (!players || !players.length) return null;
  return players.find(p => p.captain) || players[0];
}

Object.assign(window, { GrainSVG, Halftone, Stripes, ClubLogo, RoleChip, PlayerSilhouette, VsBlock, PlayerImage, featuredOf });
