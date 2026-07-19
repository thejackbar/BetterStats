/* Clickable player names, IQ-wide.
 *
 * Wherever a player's name appears in a BetterIQ surface it should open their
 * profile: our own players → the Player trends deep-dive
 * (/admin/betteriq/trends?player=<id>), opposition players → the opposition
 * player profile (/admin/betteriq/opposition-player?opponent=<key>&player=<guid>).
 * Renders plain text when there's no id to link (a name-only row, a redacted
 * player) so callers can pass rows through unconditionally.
 */
import { useNavigate } from 'react-router-dom'

const linkStyle = {
  cursor: 'pointer',
  textDecoration: 'underline',
  textDecorationColor: 'color-mix(in srgb, var(--pb-faint) 35%, transparent)',
  textUnderlineOffset: 3,
}

function NameButton({ onClick, className, style, title, children }) {
  return (
    <span
      role="link"
      tabIndex={0}
      title={title}
      className={className}
      style={{ ...linkStyle, ...style }}
      onClick={(e) => { e.stopPropagation(); onClick() }}
      onKeyDown={(e) => { if (e.key === 'Enter') { e.stopPropagation(); onClick() } }}
      onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--pb-accent)' }}
      onMouseLeave={(e) => { e.currentTarget.style.color = '' }}
    >
      {children}
    </span>
  )
}

/* One of OUR players → Player trends deep-dive. */
export function PlayerLink({ id, className = '', style, children }) {
  const navigate = useNavigate()
  if (!id) return <span className={className} style={style}>{children}</span>
  return (
    <NameButton className={className} style={style} title="Open player trends"
      onClick={() => navigate(`/admin/betteriq/trends?player=${encodeURIComponent(id)}`)}>
      {children}
    </NameButton>
  )
}

/* An OPPOSITION player (dossier participant GUID) → opposition player profile.
   `oppKey` is the opponent club's opp_key; `oppName` rides along so a club
   outside our history still resolves (same contract as OppositionPlayer's
   URL seeding). A row that only knows the player's NAME (the instant report's
   danger batters) can pass `fallbackName` — the profile page resolves it
   against the squad once the dossier is built (?playerName= seeding). */
export function OppPlayerLink({ playerId, oppKey, oppName, fallbackName, className = '', style, children }) {
  const navigate = useNavigate()
  if (!oppKey || (!playerId && !fallbackName)) return <span className={className} style={style}>{children}</span>
  const go = () => {
    const qs = new URLSearchParams({ opponent: oppKey })
    if (playerId) qs.set('player', playerId)
    else qs.set('playerName', fallbackName)
    if (oppName) qs.set('name', oppName)
    navigate(`/admin/betteriq/opposition-player?${qs}`)
  }
  return (
    <NameButton className={className} style={style} title="Open opposition player profile" onClick={go}>
      {children}
    </NameButton>
  )
}
