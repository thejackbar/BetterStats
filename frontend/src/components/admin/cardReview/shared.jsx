import { SEG_GROUP_CLS, Badge, TONES } from '../ui'

// The three things a paired match can show. The words are the club's, not the database's: the
// synced card is "Cricket Australia", the other is the club's own scorecard (imported from a
// file, typed in, or read from a photo), and the third is the club's numbers with Cricket
// Australia's detail added where it fits.
export const CHOICES = [
  { key: 'ca', label: 'Cricket Australia', short: 'Cricket Australia', tone: 'ok' },
  { key: 'club', label: 'Club scorecard', short: 'Club card', tone: 'warn' },
  { key: 'hybrid', label: 'Club + CA detail', short: 'Club + CA detail', tone: 'blue' },
]

export const CHOICE_NAME = { ca: 'Cricket Australia', club: 'Club scorecard', hybrid: 'Club scorecard with Cricket Australia detail' }

export const GROUPS = {
  agree: { label: 'Scores agree', tone: 'ok', blurb: 'Same runs, wickets and result on both. Cricket Australia also holds bowler and fielder names, balls faced and the opposition innings.' },
  small: { label: 'Small differences', tone: 'accent', blurb: 'The batting agrees. The date, the extras, the bowling figures or how a batter was out differ slightly.' },
  differ: { label: 'Scores differ', tone: 'warn', blurb: 'At least one batter, or the winner, is different. These need a person to choose.' },
  pairing: { label: 'Pairing looks wrong', tone: 'block', blurb: 'The two cards may not be the same match. Check the pairing before choosing.' },
  nocard: { label: 'No Cricket Australia card', tone: 'calm', blurb: 'Only the club scorecard holds our batters for this match, so there is nothing to compare.' },
}

const ACTIVE = {
  ok: { background: 'rgba(22,199,132,0.9)', color: '#04140d' },
  warn: { background: '#f5b542', color: '#1a1203' },
  blue: { background: '#3b82f6', color: '#ffffff' },
}

// The three-way choice, drawn the same wherever a match shows it: the queue, the compare page
// and the bar on the match page. `onChange` receives the key; the caller decides what a click
// does (the combined choice needs a preview first, so a list sends it to the compare page).
export function ChoiceControl({ value, onChange, disabled = false, compact = false, labelFor = 'short', 'data-testid': testId }) {
  return (
    <div className={`${SEG_GROUP_CLS} max-w-full flex-nowrap overflow-x-auto`} role="group" aria-label="What the site shows for this match" data-testid={testId}>
      {CHOICES.map(c => {
        const on = c.key === value
        return (
          <button
            key={c.key} type="button" disabled={disabled}
            aria-pressed={on} onClick={() => onChange(c.key)}
            data-choice={c.key}
            className={`rounded-md font-semibold whitespace-nowrap ${compact ? 'px-2.5 py-1 text-[11.5px]' : 'px-3 py-[5px] text-[12.5px]'} ${on ? '' : 'text-pb-faint hover:text-pb-text'} disabled:opacity-60`}
            style={on ? ACTIVE[c.tone] : undefined}
          >
            {labelFor === 'label' ? c.label : c.short}
          </button>
        )
      })}
    </div>
  )
}

export function GroupBadge({ group }) {
  const g = GROUPS[group]
  return g ? <Badge toneKey={g.tone}>{g.label}</Badge> : null
}

export function SuggestionBadge({ suggested }) {
  if (!suggested) return <Badge toneKey="calm">No suggestion</Badge>
  const c = CHOICES.find(x => x.key === suggested)
  return <Badge toneKey={c.tone === 'blue' ? 'accent' : c.tone}>{c.short}</Badge>
}

export function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(`${String(iso).slice(0, 10)}T00:00:00`)
  if (Number.isNaN(d.getTime())) return String(iso)
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

const CATEGORY_TONE = { batting: 'warn', bowling: 'accent', extras: 'calm', total: 'block', result: 'block', date: 'calm' }
const CATEGORY_WORD = { batting: 'Batting', bowling: 'Bowling', extras: 'Extras', total: 'Totals', result: 'Result', date: 'Date' }

// Every difference in one match, behind the caret on a queue row and under the cards on the
// compare page. A value only one card holds shows a dash rather than a made-up zero.
export function DifferenceTable({ items }) {
  if (!items?.length) return <p className="text-[12.5px] text-pb-dim">Nothing differs between the two cards.</p>
  const cell = v => (v === null || v === undefined ? '—' : String(v))
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12.5px]" data-testid="difference-table">
        <thead>
          <tr className="text-left font-mono text-[9.5px] uppercase tracking-[0.1em] text-pb-faint">
            <th className="py-1.5 pr-3 font-normal">What</th>
            <th className="py-1.5 px-3 font-normal text-right">Cricket Australia</th>
            <th className="py-1.5 px-3 font-normal text-right">Club scorecard</th>
            <th className="py-1.5 pl-3 font-normal">Counts toward</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it, i) => (
            <tr key={`${it.kind}-${i}`} className="border-t border-pb-hairline">
              <td className="py-1.5 pr-3 text-pb-text">{it.label}</td>
              <td className="py-1.5 px-3 text-right font-mono">{cell(it.ca)}</td>
              <td className="py-1.5 px-3 text-right font-mono">{cell(it.club)}</td>
              <td className="py-1.5 pl-3"><Badge toneKey={CATEGORY_TONE[it.category] || 'calm'}>{CATEGORY_WORD[it.category] || it.category}</Badge></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function SizeBar({ size }) {
  const col = size >= 40 ? TONES.block.hex : TONES.warn.hex
  return (
    <div className="h-2 w-[60px] rounded bg-pb-hairline overflow-hidden" title={`Size of the difference: ${size} of 100`}>
      <div className="h-full" style={{ width: `${Math.max(4, size)}%`, background: col }} />
    </div>
  )
}

// Where a card's own page lives, so a reviewer can look at the real thing.
export const matchPageUrl = id => `/games/${id}`
