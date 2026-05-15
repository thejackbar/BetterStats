/**
 * Format a player name stored as "Last, First" into the desired display format.
 * If the name doesn't contain a comma (e.g. a display_name_override), it's returned as-is.
 */
export function formatPlayerName(name, format) {
  if (!name) return name
  if (!format || format === 'last_first') return name

  const commaIdx = name.indexOf(',')
  if (commaIdx === -1) return name  // custom override or unusual format — don't touch

  const last = name.slice(0, commaIdx).trim()
  const first = name.slice(commaIdx + 1).trim()
  if (!first) return name

  switch (format) {
    case 'first_last':
      return `${first} ${last}`
    case 'first_initial_last':
      return `${first[0]}. ${last}`
    case 'last_first_initial':
      return `${last}, ${first[0]}.`
    default:
      return name
  }
}

/**
 * Returns a formatter function bound to the club's player_name_format.
 * Use this in components: const fmt = useNameFormat(club)  →  fmt(player.name)
 */
export function useNameFormat(club) {
  const format = club?.player_name_format || 'last_first'
  return (name) => formatPlayerName(name, format)
}

/**
 * Tokenized search: returns true if every word in the query appears somewhere
 * in the name (case-insensitive), regardless of order.
 * Handles searching "John Smith" against "Smith, John" by checking each token.
 */
export function nameMatchesSearch(name, query) {
  if (!query) return true
  const haystack = (name || '').toLowerCase()
  return query.toLowerCase().split(/\s+/).filter(Boolean).every(t => haystack.includes(t))
}
