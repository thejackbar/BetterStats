// The availability editor on the player's own page: the next games, a card per
// date with the answer buttons, and the quick "which weeks?" card for a two-day
// game. The page owns the answers (optimistic save, roll back on failure); this
// only draws them and reports taps.
import { Fragment, useMemo, useState } from 'react'
import { AVAILABILITY, weekPatterns, weekPatternOf, DEFAULT_WEEK_NAMES } from '../../lib/availability'
import { Tag, fmtDay, fmtShort, fmtTime, weekLabel } from './ui'

// The three answers a player can give (NO_RESPONSE is the absence of one).
export const ALL_CHOICES = ['AVAILABLE', 'MAYBE', 'UNAVAILABLE']

// Dates grouped into Monday to Sunday weeks, in order. The page opens on the
// first week with games (a Tuesday T20 and the Saturday game sit together) and
// reveals one more week per tap, so a long fixture list is not the first thing
// a player sees.
function weekKey(iso) {
  const d = new Date(iso + 'T00:00:00')
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7))
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
export function groupByWeek(dates) {
  // A two-day game spans two weeks. Its weeks join into one group, so week 2 is
  // never hidden behind "See more games" while week 1 is open.
  const parent = {}
  const find = (x) => { parent[x] = parent[x] ?? x; while (parent[x] !== x) { parent[x] = parent[parent[x]]; x = parent[x] } return x }
  const have = new Set(dates.map((d) => d.date))
  for (const d of dates) {
    find(weekKey(d.date))
    for (const f of d.fixtures || []) {
      if (f.two_day && f.day1 && f.day2 && have.has(f.day1) && have.has(f.day2)) {
        parent[find(weekKey(f.day2))] = find(weekKey(f.day1))
      }
    }
  }
  const order = []
  const byRoot = {}
  for (const d of dates) {
    const k = find(weekKey(d.date))
    if (!byRoot[k]) { byRoot[k] = []; order.push(k) }
    byRoot[k].push(d)
  }
  return order.map((k) => byRoot[k])
}

// The pairs of dates that are the two weeks of one game (or several games on the
// same two dates): [{ key, day1, day2, teams: [name], opponents: [name] }].
export function twoDayPairs(dates) {
  const have = new Set(dates.map((d) => d.date))
  const out = {}
  for (const d of dates) {
    for (const f of d.fixtures || []) {
      if (f.two_day && f.role === 'day1' && f.day1 && f.day2 && have.has(f.day1) && have.has(f.day2)) {
        const key = `${f.day1}|${f.day2}`
        out[key] = out[key] || { key, day1: f.day1, day2: f.day2, fixtures: [] }
        out[key].fixtures.push(f)
      }
    }
  }
  return out
}

// The player's own games first, then by start time (untimed last), then team.
function orderFixtures(fxs) {
  return [...fxs].sort((a, b) =>
    (b.mine ? 1 : 0) - (a.mine ? 1 : 0)
    || (a.start_time || '99:99').localeCompare(b.start_time || '99:99')
    || (a.team_name || '').localeCompare(b.team_name || ''))
}

// One game: when, which of our teams, home or away, against whom, where.
function FixtureRow({ f }) {
  const opp = f.opponent_name || f.label || 'TBC'
  const bye = f.home_away === 'BYE'
  const where = f.home_away === 'AWAY' ? 'at' : 'vs'
  return (
    <div data-fixture data-mine={f.mine ? 'yes' : 'no'}
      className={`flex gap-3 rounded-lg px-2.5 py-2 ${f.mine ? 'border-l-[3px]' : ''}`}
      style={f.mine
        ? { borderColor: 'var(--pb-accent)', background: 'color-mix(in srgb, var(--pb-accent) 8%, transparent)' }
        : undefined}>
      <div className={`w-[58px] shrink-0 font-mono text-[12px] pt-0.5 ${f.mine ? 'text-pb-text font-bold' : 'text-pb-faint'}`}>
        {fmtTime(f.start_time) || 'TBC'}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          {f.team_name && (
            <span className={f.mine ? 'font-display font-bold text-[15px] text-pb-text' : 'text-[13px] font-medium text-pb-dim'}>
              {f.team_name}
            </span>
          )}
          {f.mine && <Tag tone="var(--pb-accent)">Your squad</Tag>}
          {bye ? <Tag>Bye</Tag> : f.home_away ? <Tag>{f.home_away === 'AWAY' ? 'Away' : 'Home'}</Tag> : null}
        </div>
        {!bye && (
          <div className={`mt-0.5 ${f.mine ? 'text-[14px] text-pb-text' : 'text-[12.5px] text-pb-faint'}`}>
            {where} {opp}
          </div>
        )}
        {f.two_day && f.day1 && f.day2 && (
          <div className="text-[11.5px] text-pb-faint mt-0.5" data-two-day-note>
            Two-day game: {fmtShort(f.day1)} and {fmtShort(f.day2)}
          </div>
        )}
        {f.venue && <div className="text-[11.5px] text-pb-faint mt-0.5">{f.venue}</div>}
      </div>
    </div>
  )
}

// A date's games. The player's own come first and bold. When some are theirs and
// the rest are other grades' games, the rest wait behind a tap; with none of
// theirs (a fill-in, or a player in no squad) everything stays open.
function FixtureList({ fixtures }) {
  const [showAll, setShowAll] = useState(false)
  const ordered = orderFixtures(fixtures)
  const mine = ordered.filter((f) => f.mine)
  const others = ordered.filter((f) => !f.mine)
  const collapse = mine.length > 0 && others.length > 0 && !showAll
  const shown = collapse ? mine : ordered
  return (
    <div className="flex flex-col gap-1 mb-3">
      {shown.map((f, i) => <FixtureRow key={`${f.id}-${f.role}-${i}`} f={f} />)}
      {mine.length > 0 && others.length > 0 && (
        <button type="button" onClick={() => setShowAll((v) => !v)}
          className="self-start px-2.5 py-1 text-[12px] text-pb-faint underline">
          {showAll ? 'Hide other club games' : `Show ${others.length} other club game${others.length === 1 ? '' : 's'}`}
        </button>
      )}
    </div>
  )
}

// One tap for a two-day game: both weeks, week 1 only, week 2 only, or neither.
// Each week keeps its own answer underneath (a player can be free for week 1 and
// away for week 2, or say Maybe); this is the quick way to say the usual things.
function BothWeeks({ pair, me, choices, onPick, busy }) {
  const weekNames = { ...DEFAULT_WEEK_NAMES, ...(me.week_names || {}) }
  const a = me.availability?.[pair.day1]?.status || 'NO_RESPONSE'
  const b = me.availability?.[pair.day2]?.status || 'NO_RESPONSE'
  const same = a === b ? a : null
  const pattern = weekPatternOf([a, b])
  const names = [...new Set(pair.fixtures.map((f) => f.team_name).filter(Boolean))]
  const btn = (meta, active, extra) => (active
    ? { background: meta.cssVar, color: 'var(--pb-bg)', ...extra }
    : { background: `color-mix(in srgb, ${meta.cssVar} 12%, transparent)`, color: meta.cssVar, border: `1px solid color-mix(in srgb, ${meta.cssVar} 30%, transparent)`, ...extra })
  // The data-both values keep the old same-answer names for the two that are one
  // (AVAILABLE, UNAVAILABLE); the half answers are W1 and W2.
  const attr = { both: 'AVAILABLE', w1: 'W1', w2: 'W2', none: 'UNAVAILABLE' }
  return (
    <div data-both-weeks={pair.key} className="rounded-xl border p-3.5"
      style={{ borderColor: 'color-mix(in srgb, var(--pb-amber) 45%, transparent)', background: 'color-mix(in srgb, var(--pb-amber) 6%, transparent)' }}>
      <div className="flex items-baseline justify-between gap-2 mb-0.5">
        <div className="font-display font-bold text-[16px]">Two-day game: which weeks?</div>
        <Tag tone="var(--pb-amber)">2 weeks</Tag>
      </div>
      <div className="text-[12.5px] text-pb-dim mb-2.5">
        {fmtShort(pair.day1)} and {fmtShort(pair.day2)}{names.length ? ` · ${names.join(', ')}` : ''}
      </div>
      <div className="grid grid-cols-2 gap-2">
        {weekPatterns(weekNames).map((w) => (
          <button key={w.key} type="button" data-both={attr[w.key]} data-week-pattern={w.key}
            onClick={() => onPick(pair, w.statuses)} disabled={busy}
            className="py-2.5 rounded-lg text-sm font-semibold transition disabled:opacity-60"
            style={btn(AVAILABILITY[w.tone], pattern === w.key)}>
            {w.title}
          </button>
        ))}
        {choices.includes('MAYBE') && (
          <button type="button" data-both="MAYBE" onClick={() => onPick(pair, ['MAYBE', 'MAYBE'])} disabled={busy}
            className="col-span-2 py-2.5 rounded-lg text-sm font-semibold transition disabled:opacity-60"
            style={btn(AVAILABILITY.MAYBE, same === 'MAYBE')}>
            {AVAILABILITY.MAYBE.glyph} Maybe for both weeks
          </button>
        )}
      </div>
      <div className="text-[12px] mt-2" data-both-summary style={{ color: same ? 'var(--pb-faint)' : 'var(--pb-amber)' }}>
        {same
          ? `Same answer for both weeks. You can still change one week below.`
          : `${weekNames.w1}: ${(AVAILABILITY[a] || AVAILABILITY.NO_RESPONSE).label} · ${weekNames.w2}: ${(AVAILABILITY[b] || AVAILABILITY.NO_RESPONSE).label}`}
      </div>
    </div>
  )
}

// The next games with their answer buttons. Opens on the first week with games and
// reveals one more per tap, so a long fixture list is not the first thing a player
// sees. `onAnswer(date, status)` saves one date, `onBoth(pair, statuses)` both weeks
// of a two-day game.
export function AvailabilityEditor({ me, choices, savingDate, savedDate, onAnswer, onBoth }) {
  const [weeksOpen, setWeeksOpen] = useState(1)
  const weeks = useMemo(() => groupByWeek(me?.dates || []), [me?.dates])
  const pairs = useMemo(() => twoDayPairs(me?.dates || []), [me?.dates])
  const shown = weeks.slice(0, weeksOpen).flat()
  const answered = (d) => (me.availability?.[d.date]?.status || 'NO_RESPONSE') !== 'NO_RESPONSE'
  const toAnswer = shown.filter((d) => !answered(d)).length

  return (
    <section data-availability className="mb-3 min-w-0">
      <div className="flex items-baseline justify-between gap-2 mb-2">
        <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Your availability</div>
        {shown.length > 0 && (
          <span className="text-[12px]" data-to-answer
            style={{ color: toAnswer ? 'var(--pb-amber)' : 'var(--pb-positive)' }}>
            {toAnswer ? `${toAnswer} to answer` : 'All answered'}
          </span>
        )}
      </div>

      {(me.dates || []).length === 0 && (
        <div className="rounded-xl border pb-hairline px-4 py-10 text-center text-pb-faint text-sm">
          No upcoming fixtures to set availability for yet. Check back soon.
        </div>
      )}

      <div className="flex flex-col gap-3">
        {shown.map((d) => {
          const cur = me.availability?.[d.date]?.status || 'NO_RESPONSE'
          const startsPair = Object.values(pairs).filter((pr) => pr.day1 === d.date)
          const wk = weekLabel(d, me.week_names)
          return (
            <Fragment key={d.date}>
              {startsPair.map((pr) => (
                <div key={pr.key} className="relative">
                  <BothWeeks pair={pr} me={me} choices={choices} onPick={onBoth} busy={savingDate === pr.key} />
                  {savedDate === pr.key && <span className="absolute right-3 bottom-2 font-mono text-[10px]" style={{ color: 'var(--pb-positive)' }}>SAVED ✓</span>}
                </div>
              ))}
              <div className="rounded-xl border pb-hairline p-3.5" data-date-card={d.date}>
                <div className="flex items-baseline justify-between gap-2 mb-2">
                  <div className="font-display font-bold text-[16px]">{fmtDay(d.date)}</div>
                  <div className="flex items-baseline gap-2 shrink-0">
                    {wk && <Tag tone="var(--pb-amber)">{wk}</Tag>}
                    {savedDate === d.date && <span className="font-mono text-[10px]" style={{ color: 'var(--pb-positive)' }}>SAVED ✓</span>}
                  </div>
                </div>
                <FixtureList fixtures={d.fixtures || []} />
                <div className={`grid ${choices.length === 3 ? 'grid-cols-3' : 'grid-cols-2'} gap-2`}>
                  {choices.map((s) => {
                    const meta = AVAILABILITY[s]
                    const active = cur === s
                    return (
                      <button
                        key={s}
                        onClick={() => onAnswer(d.date, s)}
                        disabled={savingDate === d.date}
                        className="py-2.5 rounded-lg text-sm font-semibold transition disabled:opacity-60"
                        style={active
                          ? { background: meta.cssVar, color: 'var(--pb-bg)' }
                          : { background: `color-mix(in srgb, ${meta.cssVar} 12%, transparent)`, color: meta.cssVar, border: `1px solid color-mix(in srgb, ${meta.cssVar} 30%, transparent)` }}
                      >
                        {meta.glyph} {meta.label}
                      </button>
                    )
                  })}
                </div>
              </div>
            </Fragment>
          )
        })}
      </div>
      {weeks.length > weeksOpen && (
        <button type="button" data-see-more onClick={() => setWeeksOpen((n) => n + 1)}
          className="w-full mt-3 py-3 rounded-lg border pb-hairline text-sm font-semibold text-pb-text hover:bg-pb-surface2 transition-colors">
          See more games
          <span className="block text-[11.5px] font-normal text-pb-faint mt-0.5">
            {(() => { const n = weeks.slice(weeksOpen).flat().length; return `${n} more day${n === 1 ? '' : 's'} with games` })()}
          </span>
        </button>
      )}
      {weeksOpen > 1 && (
        <button type="button" data-show-fewer onClick={() => setWeeksOpen(1)}
          className="block mx-auto mt-3 text-[12px] text-pb-faint underline">
          Show only the next games
        </button>
      )}
      <p className="text-center text-pb-faintest text-[11px] mt-4">
        Your answers save automatically. One tap covers every game that day. For a two-day game, answer each week or both at once.
      </p>
    </section>
  )
}
