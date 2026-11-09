// Club and team names as a post prints them. Cricket Australia names a side by its
// grade ("Maddington Seventh Grade") and the club by its full name ("Maddington
// Cricket Club"); a post often wants neither, only "Maddington".

// "Leeming Spartan Cricket Club" -> "Leeming Spartan" (keeps it on one line).
const CLUB_SUFFIX_RE = /\s+(cricket\s+club|cricket\s+association|football\s+club|cc|c\.c\.|fc)\s*$/i
export function shortClubName(n) {
  const out = String(n || '').replace(CLUB_SUFFIX_RE, '').trim()
  return out || String(n || '')
}

// "Maddington Seventh Grade" -> "Maddington", "Canning Vale ODA" -> "Canning Vale".
const GRADE_TAIL_RE = /\s+(?:(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|\d{1,2}(?:st|nd|rd|th))\s+(?:grade|xi|team|div(?:ision)?)|(?:grade|div(?:ision)?)\s*\w+|under\s*\d{1,2}s?|u\d{1,2}s?|od[a-z])\s*$/i
export function stripGradeTail(n) {
  const out = String(n || '').replace(GRADE_TAIL_RE, '').trim()
  return out || String(n || '')
}

// A side's name as a club: grade taken off, then "Cricket Club" if asked.
export function clubOfTeamName(n, { short = true } = {}) {
  const base = stripGradeTail(n)
  return short ? shortClubName(base) : base
}
