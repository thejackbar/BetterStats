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
 * Split a stored display value into { first, last } for editing in two fields.
 * Accepts the canonical "Last, First" shape and best-effort-parses a legacy
 * free-text override ("First Last" -> first/last; a single token -> first).
 * The inverse of joinDisplayName for values it produced.
 */
export function splitDisplayName(value) {
  const s = (value || '').trim()
  if (!s) return { first: '', last: '' }
  const comma = s.indexOf(',')
  if (comma !== -1) {
    return { first: s.slice(comma + 1).trim(), last: s.slice(0, comma).trim() }
  }
  const words = s.split(/\s+/).filter(Boolean)
  if (words.length <= 1) return { first: s, last: '' }
  return { first: words.slice(0, -1).join(' '), last: words[words.length - 1] }
}

/**
 * Join first + last into the canonical "Last, First" string used for storage,
 * so a display-name override sorts by surname AND flows through formatPlayerName
 * (i.e. respects the club's name-format setting) exactly like a synced name.
 * Returns '' when both are blank → clears the override.
 */
export function joinDisplayName(first, last) {
  const f = (first || '').trim()
  const l = (last || '').trim()
  if (f && l) return `${l}, ${f}`
  return f || l || ''
}

/**
 * Surname-first, case-insensitive sort key for a player name in either the
 * "Last, First" or free-text shape — mirrors the backend name_sort_key so
 * client-side ordering matches the API.
 */
export function nameSortKey(name) {
  const { first, last } = splitDisplayName(name)
  const surname = (last || first).trim()
  const given = (last ? first : '').trim()
  return `${surname} ${given}`.toLowerCase()
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
