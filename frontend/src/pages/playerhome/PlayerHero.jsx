// The top of the player's own page: their photo, name, shirt number and squads,
// the club they play for, and the way to their public profile. Their own details
// only; nothing here names another player.
import { useState } from 'react'

function initialsOf(name) {
  const parts = (name || '').trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0][0].toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

// The photo, or their initials in the club colour when there is none (or it will
// not load, which a stale link to a deleted photo does).
function Avatar({ player }) {
  const [failed, setFailed] = useState(false)
  const size = 'w-[76px] h-[76px] sm:w-[92px] sm:h-[92px]'
  if (player?.photo_url && !failed) {
    return (
      <img src={player.photo_url} alt="" data-hero-photo onError={() => setFailed(true)}
        className={`${size} rounded-2xl object-cover shrink-0 bg-pb-surface2`} />
    )
  }
  return (
    <span data-hero-initials aria-hidden="true"
      className={`${size} rounded-2xl shrink-0 flex items-center justify-center font-display font-bold text-2xl`}
      style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}>
      {initialsOf(player?.display_name)}
    </span>
  )
}

export default function PlayerHero({ club, player, squads, onSwitch, onUpdateDetails }) {
  const short = club?.short_name || club?.name
  return (
    <section data-hero className="rounded-2xl border pb-hairline p-4 mb-3"
      style={{ background: 'color-mix(in srgb, var(--pb-accent) 6%, transparent)' }}>
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          {club?.logo_url && <img src={club.logo_url} alt="" className="w-6 h-6 rounded object-contain shrink-0" />}
          <span className="font-mono text-[10.5px] uppercase tracking-wide2 text-pb-faint truncate">{short}</span>
        </div>
        <button onClick={onSwitch} className="text-pb-faint text-xs hover:text-pb-text underline shrink-0">Not you?</button>
      </div>
      <div className="flex items-center gap-4">
        <div className="relative shrink-0">
          <Avatar player={player} />
          {player?.shirt_number ? (
            <span data-shirt className="absolute -bottom-1.5 -right-1.5 min-w-[26px] text-center rounded-full px-1.5 py-0.5 font-display font-bold text-[12px] border"
              style={{ background: 'var(--pb-bg)', borderColor: 'var(--pb-accent)', color: 'var(--pb-accent)' }}>
              {String(player.shirt_number).startsWith('#') ? player.shirt_number : `#${player.shirt_number}`}
            </span>
          ) : null}
        </div>
        <div className="min-w-0">
          <div className="font-display font-bold text-[22px] sm:text-[26px] leading-tight break-words" data-hero-name>{player?.display_name}</div>
          {(squads || []).length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 mt-1.5" data-my-squads>
              {squads.map((n) => (
                <span key={n} className="text-[12px] font-semibold rounded-full px-2.5 py-0.5"
                  style={{ background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)', color: 'var(--pb-accent)' }}>{n}</span>
              ))}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 mt-2">
            {onUpdateDetails && (
              <button type="button" onClick={onUpdateDetails} data-update-details
                className="px-3 py-1.5 rounded-lg border pb-hairline text-[12.5px] font-semibold text-pb-text hover:bg-pb-surface2">
                Update details
              </button>
            )}
            {player?.profile_path && (
              <a href={player.profile_path} data-profile-link className="text-[12.5px] font-semibold"
                style={{ color: 'var(--pb-accent)' }}>
                Your public profile →
              </a>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
