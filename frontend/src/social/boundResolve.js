// The pure half of bound fields (see boundFields.js for the template file):
// which words mean which live value, and what a bound field prints. No React and
// no imports from the editor, so the canvas and the file reader can both use it.

export function splitPlayerName(name) {
  const n = String(name || '').trim()
  if (!n) return ['', '']
  if (n.includes(', ')) { const [l, f] = n.split(', '); return [f || '', l || ''] }
  const parts = n.split(/\s+/)
  return [parts.slice(0, -1).join(' '), parts.slice(-1)[0] || '']
}

export const LINEUP_SLOTS = 15

const MATCH_KEYS = ['competition', 'round', 'venue', 'date', 'time', 'season']
const norm = (s) => String(s || '').toLowerCase().replace(/[{}]/g, '').replace(/\s+/g, ' ').trim()

const PART_ALIAS = { headshot: 'photo', 'vice captain': 'vice', vc: 'vice', wicketkeeper: 'keeper', 'wicket keeper': 'keeper', wk: 'keeper' }

// "player 3 last" -> "lineup.3.last". null when the words are not a field.
export function bindFromToken(token) {
  const t = norm(token)
  let m = t.match(/^player ?(\d{1,2})(?: (name|first|last|role|photo|headshot|captain|vice captain|vice|vc|keeper|wicketkeeper|wicket keeper|wk|debut))?$/)
  if (m) {
    const n = Number(m[1])
    return n >= 1 && n <= LINEUP_SLOTS ? `lineup.${n}.${PART_ALIAS[m[2]] || m[2] || 'name'}` : null
  }
  if (t === 'captain' || t === 'keeper' || t === 'headline' || t === 'sponsors') return t
  if (t === 'wicketkeeper' || t === 'wicket keeper') return 'keeper'
  if (t === 'vice captain' || t === 'vicecaptain' || t === 'vice') return 'vice'
  if (t === 'opponent') return 'opponent'
  if (t === 'team' || t === 'club') return 'team'
  if (MATCH_KEYS.includes(t)) return `match.${t}`
  return null
}

const WORD = { name: '', first: ' (first name)', last: ' (last name)', role: ' (role)', photo: ' (photo)', captain: ' (captain mark)', vice: ' (vice-captain mark)', keeper: ' (keeper mark)', debut: ' (debut mark)' }
export function bindLabel(bind) {
  if (!bind) return ''
  const p = bind.match(/^lineup\.(\d+)\.(\w+)$/)
  if (p) return `Player ${p[1]}${WORD[p[2]] || ''}`
  if (bind.startsWith('match.')) return bind.slice(6).replace(/^./, (c) => c.toUpperCase())
  return bind.replace(/^./, (c) => c.toUpperCase())
}

// An area block (a photo, the sponsors) takes its size from the template rather than from text.
export const isAreaBind = (bind) => bind === 'sponsors' || /^lineup\.\d+\.photo$/.test(bind || '')
export const isBoundPlayerSlot = (bind) => /^lineup\./.test(bind || '')
export const boundSlotCount = (items) => (items || []).reduce((n, it) => {
  const m = (it.bind || '').match(/^lineup\.(\d+)\./)
  return m ? Math.max(n, Number(m[1])) : n
}, 0)

export const MARKS = { captain: 'C', vice: 'VC', keeper: 'WK', debut: 'DEBUT' }

// What a bound field prints. A string (possibly empty) when the editor holds
// the value, null when it holds nothing for it yet, so the author still sees
// the slot's sample text and a half-filled lineup prints blanks, not "PLAYER 9".
export function resolveBind(bind, data = {}) {
  if (!bind) return null
  const lineup = Array.isArray(data.lineup) ? data.lineup : []
  const p = bind.match(/^lineup\.(\d+)\.(\w+)$/)
  if (p) {
    if (!lineup.length) return null
    const row = lineup[Number(p[1]) - 1]
    if (!row) return ''
    // A row from the editor carries first and last as the post prints them; a bare
    // name is split the way the data blocks split one.
    const part = p[2]
    // The marks print a short word when the player has it and nothing when they do not, so a
    // template can put "C" or "DEBUT" beside every name and only the right ones show.
    if (part === 'photo') return row.photo || ''
    if (MARKS[part]) return row[part === 'vice' ? 'viceCaptain' : part] ? MARKS[part] : ''
    const [sf, sl] = splitPlayerName(row.name || '')
    const first = row.first ?? sf, last = row.last ?? sl
    return { name: row.name || [first, last].filter(Boolean).join(' '), first, last, role: row.role || '' }[p[2]] ?? ''
  }
  if (bind === 'captain' || bind === 'keeper' || bind === 'vice') {
    if (!lineup.length) return null
    return (lineup.find((r) => r[bind === 'vice' ? 'viceCaptain' : bind]) || {}).name || ''
  }
  if (bind === 'opponent') return data.opponent || null
  if (bind === 'team') return (data.team && (data.team.fullName || data.team.name)) || null
  if (bind === 'headline') return data.headline || null
  if (bind.startsWith('match.')) return (data.match || {})[bind.slice(6)] ?? null
  return null
}

