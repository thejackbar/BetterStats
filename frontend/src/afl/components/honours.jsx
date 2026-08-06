// The honour board on a BetterFootball player profile — the pills that sit
// under a player's name, and the full Honours section below their numbers.
//
// Same idea and the same badge styling as BetterStats (Core)'s player profile
// (pages/PlayerProfile.jsx): one --pb-cat-* colour per kind of honour, a card
// per award, repeated wins of the one trophy collapsed into a single entry
// carrying every year. Kept here rather than in the AFL profile page so the
// Players list or a club dashboard can show the same pills later without a
// second copy of the sorting and grouping rules.
//
// The one AFL-specific piece is the icon for a premiership — Core's map points
// that at a cricket bat.
import { thiings } from '../../assets/thiings'
import '../../styles/honour-badge.css'
import './honours.css'

const CATEGORY_ICON = {
  'Club Award': thiings.trophy,
  'Association Award': thiings.goldMedal,
  'Office Bearer': thiings.necktie,
  'Premiership': thiings.goldMedal,
  'Hall of Fame': thiings.star,
  'Life Membership': thiings.ribbon,
  'Milestone': thiings.locationPin,
}

// Which --pb-cat-* colour an award takes. The four buckets are the same ones
// the Honours section groups by, so a pill and its card always agree.
export function honourType(a) {
  if (['Hall of Fame', 'Life Membership', 'Premiership'].includes(a.category)) return 'honour'
  if (a.category === 'Office Bearer') return 'role'
  if (a.category === 'Milestone') return 'milestone'
  return 'award'
}

// What goes at the front. A life membership outranks a best and fairest, which
// outranks a committee post — and inside milestones, the bigger number wins,
// so a pill row never leads with 50 games when the player also has 300.
const EXEC_RANK = { president: 1, 'vice president': 2, 'vice-president': 2, secretary: 3, treasurer: 3 }

export function honourPriority(a) {
  if (a.category === 'Hall of Fame') return 0
  if (a.category === 'Life Membership') return 1
  if (a.category === 'Premiership') return 2
  if (a.category === 'Milestone') {
    const n = parseInt((a.achievement || '').match(/(\d+)/)?.[1] || '0', 10)
    if (n >= 300) return 3
    if (n >= 200) return 3.5
    if (n >= 100) return 4
    return 6.5
  }
  if (a.category === 'Club Award') return 5
  if (a.category === 'Association Award') return 5.5
  if (a.category === 'Office Bearer') return EXEC_RANK[(a.achievement || '').toLowerCase()] ?? 7
  return 99
}

const bySeasonDesc = (a, b) => String(b.season || '').localeCompare(String(a.season || ''))

// One trophy won five times is one honour with five years against it, not
// five honours. Grouped on what actually identifies the award, so the same
// trophy under two different teams stays two entries.
export function groupHonours(achievements) {
  const map = new Map()
  for (const a of achievements || []) {
    const key = `${a.category}|${a.subcategory || ''}|${a.achievement}`
    const g = map.get(key)
    if (g) g.instances.push(a)
    else map.set(key, { ...a, instances: [a] })
  }
  const out = [...map.values()]
  out.forEach(g => g.instances.sort(bySeasonDesc))
  return out.sort((a, b) => {
    const d = honourPriority(a) - honourPriority(b)
    return d || bySeasonDesc(a.instances[0], b.instances[0])
  })
}

// The years a grouped honour was won. Beyond three, the count says more than
// the list does — a nine-time winner's pill would otherwise be a paragraph.
export function seasonsLabel(g) {
  const years = g.instances.map(i => {
    const s = String(i.season || '').trim()
    const e = String(i.season_end || '').trim()
    return e && e !== s ? `${s}–${e}` : s
  }).filter(Boolean)
  if (!years.length) return null
  if (years.length <= 3) return years.slice().reverse().join(', ')
  return `${years.length}× · ${years[years.length - 1]}–${years[0]}`
}

function catVars(type) {
  const c = `var(--pb-cat-${type})`
  return {
    '--hb-accent-text': c,
    '--hb-border': `color-mix(in srgb, ${c} 30%, transparent)`,
    '--hb-border-hover': `color-mix(in srgb, ${c} 70%, transparent)`,
    '--hb-icon-bg': `color-mix(in srgb, ${c} 15%, transparent)`,
    '--hb-wash': `linear-gradient(135deg, color-mix(in srgb, ${c} 6%, transparent) 0%, transparent 60%)`,
    '--hb-shadow-b': `color-mix(in srgb, ${c} 12%, transparent)`,
  }
}

/** The coloured pills under a player's name. */
export function HonourPills({ achievements, limit = 6 }) {
  const groups = groupHonours(achievements).slice(0, limit)
  if (!groups.length) return null
  return (
    <div className="flex flex-wrap gap-2 mt-2.5">
      {groups.map((g, i) => {
        const c = `var(--pb-cat-${honourType(g)})`
        const years = seasonsLabel(g)
        return (
          <span key={i} className="font-mono text-[12.5px] tracking-wide2 px-3 py-1.5 rounded-sm border"
            style={{
              borderColor: `color-mix(in srgb, ${c} 40%, transparent)`,
              color: c,
              background: `color-mix(in srgb, ${c} 10%, transparent)`,
            }}>
            {g.achievement}{years ? ` (${years})` : ''}
          </span>
        )
      })}
    </div>
  )
}

function HonourCard({ g, type }) {
  const years = seasonsLabel(g)
  const detail = g.instances.map(i => i.detail).find(Boolean)
  return (
    <div className="hb-parent" style={catVars(type)}>
      <div className="hb-card">
        <div className="hb-icon">
          {/* Sized against .afl-honours' own 34px icon circle (honours.css),
              not Core's 28px one — this card is only ever rendered inside it. */}
          <img src={CATEGORY_ICON[g.category] || thiings.trophy} alt=""
            style={{ width: 22, height: 22, objectFit: 'contain' }} />
        </div>
        <div className="hb-content">
          <span className="hb-category">{g.category}</span>
          <span className="hb-title">{g.achievement}</span>
          {(g.subcategory || detail) && (
            <span className="hb-sub">
              {g.subcategory && <span>{g.subcategory}</span>}
              {detail && <span style={{ color: 'var(--hb-accent-text)', marginLeft: 3 }}>{detail}</span>}
            </span>
          )}
        </div>
        {years && <span className="hb-season">{years}</span>}
      </div>
    </div>
  )
}

const SECTIONS = [
  ['honour', 'HONOURS'],
  ['award', 'AWARDS'],
  ['milestone', 'MILESTONES'],
  ['role', 'ROLES'],
]

/** The full honour board, grouped the way the pills are coloured. */
export function HonourBoard({ achievements }) {
  const groups = groupHonours(achievements)
  if (!groups.length) return null
  return (
    <div className="afl-honours space-y-5">
      {SECTIONS.map(([type, label]) => {
        const rows = groups.filter(g => honourType(g) === type)
        if (!rows.length) return null
        return (
          <div key={type}>
            <h3 className="font-mono text-xs uppercase tracking-wide3 text-pb-faint mb-3">{label}</h3>
            <div className="flex flex-wrap gap-4">
              {rows.map((g, i) => <HonourCard key={i} g={g} type={type} />)}
            </div>
          </div>
        )
      })}
    </div>
  )
}
