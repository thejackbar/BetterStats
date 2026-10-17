// BetterSelect — self-service player availability (public, no login).
//
// Reached via a per-club magic link (/avail/:token) pinned in a group chat or a
// QR. Three mobile-first steps: pick your name → prove it's you with the last 4
// digits of your mobile → tap Available / Maybe / Unavailable for the weekend.
// A signed cookie keeps you verified (~30 days); "Not you?" clears it.
//
// White-labelled from the club's own colours; the only dependency on the rest of
// the app is the shared availability colour map so a player's chips match the
// admin matrix exactly.
import { Fragment, useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import { AVAILABILITY } from '../lib/availability'

// The three answers a player can give (NO_RESPONSE is the absence of one).
const ALL_CHOICES = ['AVAILABLE', 'MAYBE', 'UNAVAILABLE']

function fmtDay(d) {
  try {
    return new Date(d + 'T00:00:00').toLocaleDateString(undefined, {
      weekday: 'long', day: 'numeric', month: 'short',
    })
  } catch { return d }
}

// Dates grouped into Monday to Sunday weeks, in order. The page opens on the
// first week with games (a Tuesday T20 and the Saturday game sit together) and
// reveals one more week per tap, so a long fixture list is not the first thing
// a player sees.
function weekKey(iso) {
  const d = new Date(iso + 'T00:00:00')
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7))
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function groupByWeek(dates) {
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
function twoDayPairs(dates) {
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

// "13:00" → "1:00pm". The time is the club's own local display string, so an
// unexpected format is shown as it came rather than guessed at.
function fmtTime(t) {
  const m = /^(\d{1,2}):(\d{2})(?::\d{2})?$/.exec((t || '').trim())
  if (!m) return (t || '').trim()
  const h = Number(m[1])
  if (h > 23) return t
  return `${h % 12 === 0 ? 12 : h % 12}:${m[2]}${h >= 12 ? 'pm' : 'am'}`
}

// The player's own games first, then by start time (untimed last), then team.
function orderFixtures(fxs) {
  return [...fxs].sort((a, b) =>
    (b.mine ? 1 : 0) - (a.mine ? 1 : 0)
    || (a.start_time || '99:99').localeCompare(b.start_time || '99:99')
    || (a.team_name || '').localeCompare(b.team_name || ''))
}

function Tag({ children, tone }) {
  return (
    <span className="font-mono text-[9.5px] tracking-wide2 uppercase rounded px-1.5 py-0.5 shrink-0"
      style={tone
        ? { background: `color-mix(in srgb, ${tone} 16%, transparent)`, color: tone }
        : { background: 'var(--pb-surface2)', color: 'var(--pb-faint)' }}>
      {children}
    </span>
  )
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

// One answer for both weeks of a two-day game. Each week keeps its own answer
// underneath (a player can be free for week 1 and away for week 2); this is the
// quick way to say the same thing twice.
function BothWeeks({ pair, me, choices, onPick, busy }) {
  const a = me.availability?.[pair.day1]?.status || 'NO_RESPONSE'
  const b = me.availability?.[pair.day2]?.status || 'NO_RESPONSE'
  const same = a === b ? a : null
  const names = [...new Set(pair.fixtures.map((f) => f.team_name).filter(Boolean))]
  return (
    <div data-both-weeks={pair.key} className="rounded-xl border p-3.5"
      style={{ borderColor: 'color-mix(in srgb, var(--pb-amber) 45%, transparent)', background: 'color-mix(in srgb, var(--pb-amber) 6%, transparent)' }}>
      <div className="flex items-baseline justify-between gap-2 mb-0.5">
        <div className="font-display font-bold text-[16px]">Two-day game: both weeks</div>
        <Tag tone="var(--pb-amber)">2 weeks</Tag>
      </div>
      <div className="text-[12.5px] text-pb-dim mb-2.5">
        {fmtShort(pair.day1)} and {fmtShort(pair.day2)}{names.length ? ` · ${names.join(', ')}` : ''}
      </div>
      <div className={`grid ${choices.length === 3 ? 'grid-cols-3' : 'grid-cols-2'} gap-2`}>
        {choices.map((s) => {
          const meta = AVAILABILITY[s]
          const active = same === s
          return (
            <button key={s} type="button" data-both={s} onClick={() => onPick(pair, s)} disabled={busy}
              className="py-2.5 rounded-lg text-sm font-semibold transition disabled:opacity-60"
              style={active
                ? { background: meta.cssVar, color: 'var(--pb-bg)' }
                : { background: `color-mix(in srgb, ${meta.cssVar} 12%, transparent)`, color: meta.cssVar, border: `1px solid color-mix(in srgb, ${meta.cssVar} 30%, transparent)` }}>
              {meta.glyph} {meta.label}
            </button>
          )
        })}
      </div>
      <div className="text-[12px] mt-2" data-both-summary style={{ color: same ? 'var(--pb-faint)' : 'var(--pb-amber)' }}>
        {same
          ? `Same answer for both weeks. You can still change one week below.`
          : `Week 1: ${(AVAILABILITY[a] || AVAILABILITY.NO_RESPONSE).label} · Week 2: ${(AVAILABILITY[b] || AVAILABILITY.NO_RESPONSE).label}`}
      </div>
    </div>
  )
}

function ClubHeader({ club }) {
  const initials = (club?.name || 'Club').split(' ').map((w) => w[0]).join('').slice(0, 3).toUpperCase()
  return (
    <div className="flex flex-col items-center text-center gap-3 mb-6">
      {club?.logo_url
        ? <img src={club.logo_url} alt="" className="w-16 h-16 rounded-xl object-contain bg-pb-surface2 p-1" />
        : <span className="w-16 h-16 rounded-xl flex items-center justify-center font-display font-bold text-xl" style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}>{initials}</span>}
      <div>
        <div className="font-display font-bold text-xl leading-tight">{club?.name || 'Set your availability'}</div>
        <div className="font-mono text-[11px] tracking-wide2 text-pb-faint mt-1">SET YOUR AVAILABILITY</div>
      </div>
    </div>
  )
}

function Banner({ tone = 'error', children }) {
  if (!children) return null
  const color = tone === 'error' ? 'var(--pb-red)' : tone === 'ok' ? 'var(--pb-positive)' : 'var(--pb-amber)'
  return (
    <div className="rounded-lg px-3.5 py-2.5 mb-4 text-sm" style={{ background: `color-mix(in srgb, ${color} 12%, transparent)`, color, border: `1px solid color-mix(in srgb, ${color} 35%, transparent)` }}>
      {children}
    </div>
  )
}

function fmtShort(d) {
  try { return new Date(d + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' }) } catch { return d }
}

// "Week 1 of 2" for the days of a two-day game, '' for an ordinary date.
function weekLabel(d) {
  const f = (d.fixtures || []).find((x) => x.two_day)
  return f ? (f.role === 'day2' ? 'Week 2 of 2' : 'Week 1 of 2') : ''
}

function Section({ title, children, className = '' }) {
  return (
    <section className={`rounded-xl border pb-hairline p-3.5 mb-3 min-w-0 break-inside-avoid ${className}`}>
      <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-2">{title}</div>
      {children}
    </section>
  )
}

const money = (n) => `${n < 0 ? '-' : ''}$${Math.abs(Number(n) || 0).toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

function Muted({ children, ...rest }) {
  return <div className="text-sm text-pb-faint" {...rest}>{children}</div>
}

// A line of label and value, for the small figure grids.
function Stat({ label, value }) {
  return (
    <div className="rounded-lg px-3 py-2" style={{ background: 'var(--pb-surface2)' }}>
      <div className="font-display font-bold text-[18px] leading-tight">{value ?? '-'}</div>
      <div className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faint mt-0.5">{label}</div>
    </div>
  )
}

// ─── The modules of the player's own page ───
// Each one is a Section the club can turn on or off in BetterSelect. They are
// declared here, at module level, and picked by key from the server's list.

function AvailabilityModule({ me }) {
  const upcoming = (me.dates || []).slice(0, 6)
  return (
    <Section title="Your availability">
      {upcoming.length === 0 && <Muted>No upcoming games to answer yet.</Muted>}
      <div className="flex flex-col gap-1.5">
        {upcoming.map((d) => {
          const cur = me.availability?.[d.date]?.status || 'NO_RESPONSE'
          const meta = AVAILABILITY[cur] || AVAILABILITY.NO_RESPONSE
          return (
            <div key={d.date} className="flex items-center justify-between gap-3 text-sm">
              <span>{fmtShort(d.date)}{weekLabel(d) ? <span className="text-pb-faint"> · {weekLabel(d)}</span> : null}</span>
              <span className="font-semibold" style={{ color: meta.cssVar }}>{meta.glyph} {meta.label}</span>
            </div>
          )
        })}
      </div>
    </Section>
  )
}

// Games the player can still vote on and has not, then (for reference) the votes
// they have already cast with who they gave 3, 2 and 1 to. Each to-cast game links
// to its ballot on the vote page (which asks for their PIN once); a cast vote on a
// game still open links to the same ballot to change it.
function VotesModule({ data }) {
  const due = data.votes || []
  const cast = data.votes_cast || []
  return (
    <Section title={due.length ? 'Votes to cast' : 'Your votes'}>
      {due.length > 0 && (
        <div data-votes>
          {due.map((v) => (
            <div key={`${v.medal}-${v.fixture_id}`} className="flex items-center gap-3 py-2 border-t pb-hairline first:border-t-0" data-vote-due={v.fixture_id}>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold truncate">{v.round ? `${v.round} · ` : ''}vs {v.opponent || 'TBC'}</div>
                <div className="text-[12px] text-pb-faint">
                  {v.medal}{v.date ? ` · played ${fmtShort(v.date)}` : ''}{v.closes_on ? ` · voting closes ${fmtShort(v.closes_on)}` : ''}
                </div>
              </div>
              <a href={v.link} className="shrink-0 px-3.5 py-2 rounded-lg text-[13px] font-semibold"
                style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}>Vote</a>
            </div>
          ))}
        </div>
      )}
      {cast.length > 0 && (
        <div className={due.length ? 'mt-4' : ''} data-votes-cast>
          {due.length > 0 && <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1">Already cast</div>}
          {cast.map((c) => (
            <div key={`${c.medal}-${c.fixture_id}`} className="py-2 border-t pb-hairline first:border-t-0" data-vote-cast={c.fixture_id}>
              <div className="text-sm font-semibold truncate">{c.round ? `${c.round} · ` : ''}vs {c.opponent || 'TBC'}</div>
              <div className="text-[12px] text-pb-faint">{c.medal}{c.date ? ` · played ${fmtShort(c.date)}` : ''}</div>
              {c.picks.length === 0
                ? <div className="text-[12.5px] text-pb-faint mt-1">No picks recorded.</div>
                : (
                  <div className="mt-1.5 flex flex-col gap-0.5">
                    {c.picks.map((pk, i) => (
                      <div key={i} className="flex items-baseline gap-2 text-[13px]" data-pick>
                        <span className="font-mono font-bold w-5 text-right shrink-0" style={{ color: 'var(--pb-accent)' }}>{pk.points ?? ''}</span>
                        <span className="min-w-0 truncate">{pk.name}</span>
                      </div>
                    ))}
                  </div>
                )}
              {c.open && c.link && (
                <a href={c.link} data-change-vote className="inline-block text-[12px] underline text-pb-dim mt-1.5">
                  Change my votes{c.closes_on ? ` (until ${fmtShort(c.closes_on)})` : ''}
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </Section>
  )
}

// A reminder above everything else while a vote is due.
function VotesBanner({ votes }) {
  const n = votes.length
  return (
    <div className="rounded-xl px-4 py-3 mb-3 flex items-center gap-3" data-votes-banner
      style={{ background: 'color-mix(in srgb, var(--pb-amber) 12%, transparent)', border: '1px solid color-mix(in srgb, var(--pb-amber) 40%, transparent)' }}>
      <div className="min-w-0 flex-1 text-sm">
        <b>{n === 1 ? 'You have a vote to cast.' : `You have ${n} votes to cast.`}</b>
        <span className="text-pb-dim"> {n === 1 ? 'A game you played is still open for voting.' : 'Games you played are still open for voting.'}</span>
      </div>
      <a href={votes[0].link} className="shrink-0 px-3.5 py-2 rounded-lg text-[13px] font-semibold"
        style={{ background: 'var(--pb-accent)', color: 'var(--pb-on-accent)' }}>{n === 1 ? 'Vote now' : 'Vote'}</a>
    </div>
  )
}

function SquadModule({ data }) {
  return (
    <Section title="Your squad">
      {!data.squads_visible
        ? <Muted>Your club has not turned on squad names for this page.</Muted>
        : data.squads.length
        ? <div className="flex flex-wrap gap-1.5">{data.squads.map((n) => <span key={n} className="text-[13px] font-semibold rounded-full px-3 py-1" style={{ background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)', color: 'var(--pb-accent)' }}>{n}</span>)}</div>
        : <Muted>You are not in a squad yet. Your club will add you.</Muted>}
    </Section>
  )
}

function SelectedModule({ data }) {
  const selected = data.selected || []
  return (
    <Section title="Selected">
      {selected.length === 0
        ? <Muted data-no-selection>Nothing yet. Sides show here once your selectors have locked them in.</Muted>
        : (
          <div className="flex flex-col gap-2.5">
            {selected.map((s) => (
              <div key={`${s.date}-${s.opponent_name}`} className="rounded-lg px-3 py-2.5" style={{ background: 'color-mix(in srgb, var(--pb-positive) 10%, transparent)' }}>
                <div className="font-display font-bold text-[15px]">
                  {fmtShort(s.date)}{s.team_name ? ` · ${s.team_name}` : ''}
                </div>
                <div className="text-[13px] text-pb-dim">
                  {s.home_away === 'AWAY' ? '@ ' : 'vs '}{s.opponent_name || s.label || 'TBC'}{s.start_time ? ` · ${s.start_time}` : ''}{s.venue ? ` · ${s.venue}` : ''}
                </div>
                {(s.is_captain || s.is_wicket_keeper) && (
                  <div className="text-[12px] font-semibold mt-0.5" style={{ color: 'var(--pb-accent)' }}>
                    {[s.is_captain && 'Captain', s.is_wicket_keeper && 'Keeper'].filter(Boolean).join(' and ')}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
    </Section>
  )
}

function TrainingModule({ data }) {
  const t = data.training || { upcoming: [], attended_8_weeks: 0 }
  return (
    <Section title="Training">
      {t.upcoming.length === 0
        ? <Muted>No nets listed for you yet.</Muted>
        : t.upcoming.map((n) => (
          <div key={`${n.date}-${n.label}`} className="flex justify-between gap-3 text-sm py-0.5">
            <span>{fmtShort(n.date)}</span><span className="text-pb-dim truncate">{n.label || 'Nets'}</span>
          </div>
        ))}
      <div className="text-[12.5px] text-pb-faint mt-2">
        {t.attended_8_weeks > 0
          ? `You were at ${t.attended_8_weeks} session${t.attended_8_weeks === 1 ? '' : 's'} in the last eight weeks${t.last_attended ? `, most recently ${fmtShort(t.last_attended)}` : ''}.`
          : 'No nets recorded for you in the last eight weeks.'}
      </div>
    </Section>
  )
}

// The ladder asks Cricket Australia, which the rest of the page does not, so the
// page loads it on its own (see MyPage) and nothing else waits on it.
function LadderModule({ state }) {
  return (
    <Section title="Ladder">
      {state.status === 'loading' && <Muted>Loading the ladder…</Muted>}
      {state.status === 'failed' && <Muted>The ladder could not load right now. Try again in a minute.</Muted>}
      {state.status === 'ok' && state.ladders.length === 0 && <Muted data-no-ladder>No ladder is linked to your team yet.</Muted>}
      {state.ladders.map((l) => (
        <div key={l.team} className="mb-3 last:mb-0" data-ladder={l.team}>
          <div className="text-[13px] font-semibold mb-1.5">{l.team}{l.grade ? <span className="text-pb-faint font-normal"> · {l.grade}</span> : null}</div>
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="text-pb-faint font-mono text-[9.5px] uppercase tracking-wide2">
                <th className="text-left font-normal w-6">#</th>
                <th className="text-left font-normal">Team</th>
                {l.columns.map((c) => <th key={c.id} className="text-right font-normal w-9">{c.heading}</th>)}
              </tr>
            </thead>
            <tbody>
              {l.rows.map((r, i) => (
                <tr key={`${r.team_name}-${i}`} data-mine={r.is_club ? 'yes' : 'no'}
                  className={r.is_club ? 'font-bold' : 'text-pb-dim'}
                  style={r.is_club ? { background: 'color-mix(in srgb, var(--pb-accent) 12%, transparent)' } : undefined}>
                  <td className="py-1 pl-1">{r.rank ?? ''}</td>
                  <td className="py-1 pr-2 truncate max-w-[160px]">{r.team_name}</td>
                  {l.columns.map((c) => <td key={c.id} className="py-1 text-right">{r.stats[c.id] ?? ''}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </Section>
  )
}

function SeasonModule({ data }) {
  const s = data.season
  return (
    <Section title={s?.season ? `Your season: ${s.season}` : 'Your season'}>
      {!s ? <Muted data-no-season>No games recorded for you yet.</Muted> : (
        <>
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Matches" value={s.matches} />
            <Stat label="Runs" value={s.runs} />
            <Stat label="High score" value={s.high_score} />
            <Stat label="Bat avg" value={s.batting_average} />
            <Stat label="Wickets" value={s.wickets} />
            <Stat label="Catches" value={s.catches} />
          </div>
          {s.best_bowling && <div className="text-[12.5px] text-pb-dim mt-2">Best bowling {s.best_bowling}</div>}
          <div className="text-[11.5px] text-pb-faintest mt-2">
            {s.auto_shown ? 'Counts the grades you have played. ' : 'Counts the grade types your club shows in its public stats. '}
            Your latest season with games.
          </div>
        </>
      )}
    </Section>
  )
}

function FeesModule({ data }) {
  const f = data.fees
  return (
    <Section title="Fees">
      {!f || !f.on_record ? <Muted data-no-fees>No fees are recorded for you this season yet. Ask your club if you think that is wrong.</Muted> : (
        <>
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-sm text-pb-dim">{f.total_outstanding > 0 ? 'You owe' : 'Nothing owing'}</span>
            <span className="font-display font-bold text-[22px]" style={{ color: f.total_outstanding > 0 ? 'var(--pb-amber)' : 'var(--pb-positive)' }}>
              {money(f.total_outstanding)}
            </span>
          </div>
          {f.total_outstanding > 0 && (f.membership_outstanding > 0 || f.match_fee_outstanding > 0) && (
            <div className="text-[12.5px] text-pb-dim mt-1.5">
              {[f.membership_outstanding > 0 && `Membership ${money(f.membership_outstanding)}`, f.match_fee_outstanding > 0 && `Match fees ${money(f.match_fee_outstanding)}`].filter(Boolean).join(' · ')}
            </div>
          )}
          {f.credit > 0 && <div className="text-[12.5px] text-pb-dim mt-1.5">You are {money(f.credit)} in credit.</div>}
          <div className="text-[11.5px] text-pb-faintest mt-2">{f.season ? `${f.season}. ` : ''}Paid so far {money(f.total_paid)}.</div>
        </>
      )}
    </Section>
  )
}

function CopyRow({ label, value }) {
  const [done, setDone] = useState(false)
  const copy = async () => {
    try { await navigator.clipboard.writeText(value); setDone(true); setTimeout(() => setDone(false), 1500) } catch { /* the value is on screen to type */ }
  }
  return (
    <div className="flex items-center justify-between gap-3 py-1.5 border-t pb-hairline first:border-t-0 text-sm">
      <div className="min-w-0">
        <div className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faint">{label}</div>
        <div className="font-semibold break-all">{value}</div>
      </div>
      <button type="button" onClick={copy} className="shrink-0 text-[12px] underline text-pb-faint">{done ? 'Copied' : 'Copy'}</button>
    </div>
  )
}

const PAY_LABELS = [
  ['payid', 'PayID'], ['payid_name', 'Name that shows'], ['account_name', 'Account name'],
  ['bsb', 'BSB'], ['account_number', 'Account number'], ['reference_hint', 'Reference'],
]

function FinesBlock({ f }) {
  const pay = f.how_to_pay || {}
  const hasPay = PAY_LABELS.some(([k]) => pay[k]) || pay.other_instructions
  return (
    <div className="mb-4 last:mb-0" data-fines-squad={f.squad}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm text-pb-dim">{f.owing > 0 ? `You owe the ${f.squad} fines pot` : f.owing < 0 ? 'You are in credit' : 'You are all square'}</span>
        <span className="font-display font-bold text-[22px]" style={{ color: f.owing > 0 ? 'var(--pb-amber)' : 'var(--pb-positive)' }}>
          {money(Math.abs(f.owing))}
        </span>
      </div>
      <div className="text-[12px] text-pb-faint mt-0.5">Fined {money(f.fined)} · paid {money(f.paid)}</div>

      {f.weeks.length > 0 && (
        <div className="mt-3">
          <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1">Week by week</div>
          {f.weeks.map((w) => (
            <div key={w.date} className="py-1.5 border-t pb-hairline first:border-t-0">
              <div className="flex justify-between gap-3 text-sm"><span>{fmtShort(w.date)}</span><span className="font-semibold">{money(w.total)}</span></div>
              <div className="text-[12px] text-pb-faint">{w.items.map((i) => `${i.reason} ${money(i.amount)}${i.note ? ` (${i.note})` : ''}`).join(' · ')}</div>
            </div>
          ))}
        </div>
      )}
      {f.weeks.length === 0 && <div className="text-[12.5px] text-pb-faint mt-2">No fines yet.</div>}

      {f.payments.length > 0 && (
        <div className="text-[12.5px] text-pb-dim mt-3">
          Your payments: {f.payments.map((p) => `${money(p.amount)} on ${fmtShort(p.date)}`).join(', ')}
        </div>
      )}

      {f.owing > 0 && (
        <div className="mt-3 rounded-lg p-3" style={{ background: 'var(--pb-surface2)' }} data-how-to-pay>
          <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1">How to pay</div>
          {hasPay ? (
            <>
              {PAY_LABELS.filter(([k]) => pay[k]).map(([k, label]) => <CopyRow key={k} label={label} value={pay[k]} />)}
              {pay.other_instructions && <div className="text-[12.5px] text-pb-dim mt-1.5">{pay.other_instructions}</div>}
            </>
          ) : <div className="text-[12.5px] text-pb-faint">Your fines master has not added payment details yet. Ask them how to pay.</div>}
        </div>
      )}
      <div className="text-[11.5px] text-pb-faintest mt-2">In the pot so far: {money(f.pot)}.</div>
    </div>
  )
}

function FinesModule({ data }) {
  return (
    <Section title="Fines">
      {(data.fines || []).map((f) => <FinesBlock key={f.squad} f={f} />)}
    </Section>
  )
}

// A headline figure at the top of the dashboard.
function Tile({ label, value, hint, tone, id }) {
  return (
    <div className="rounded-xl border pb-hairline px-3 py-2.5 min-w-0" data-tile={id}>
      <div className="font-mono text-[9.5px] uppercase tracking-wide2 text-pb-faint truncate">{label}</div>
      <div className="font-display font-bold text-[19px] leading-tight mt-0.5 truncate" style={tone ? { color: tone } : undefined}>{value}</div>
      {hint && <div className="text-[11.5px] text-pb-faint mt-0.5 truncate">{hint}</div>}
    </div>
  )
}

// The tiles for the modules the club has on, from data the page already holds.
// A tile is left out rather than shown empty when it has nothing true to say.
function dashboardTiles({ me, data, modules, ladder }) {
  const tiles = []
  const has = (k) => modules.includes(k)
  const dates = (me.dates || []).slice(0, 6)
  const side = (data.selected || [])[0]
  if (has('selected') && side) {
    tiles.push({ id: 'next', label: 'Next game', value: fmtShort(side.date), hint: `${side.home_away === 'AWAY' ? '@' : 'vs'} ${side.opponent_name || side.label || 'TBC'}` })
  } else if ((has('availability') || has('selected')) && dates[0]) {
    const st = me.availability?.[dates[0].date]?.status || 'NO_RESPONSE'
    tiles.push({ id: 'next', label: 'Next game', value: fmtShort(dates[0].date), hint: st === 'NO_RESPONSE' ? 'Not answered yet' : `You said ${(AVAILABILITY[st] || AVAILABILITY.NO_RESPONSE).label}` })
  }
  if (has('availability') && dates.length) {
    const answered = dates.filter((d) => (me.availability?.[d.date]?.status || 'NO_RESPONSE') !== 'NO_RESPONSE').length
    tiles.push({ id: 'availability', label: 'Availability', value: `${answered} of ${dates.length}`, hint: 'next games answered', tone: answered < dates.length ? 'var(--pb-amber)' : 'var(--pb-positive)' })
  }
  const due = data.votes || []
  if (has('votes') && due.length) {
    tiles.push({ id: 'votes', label: 'Votes due', value: due.length, hint: due.length === 1 ? 'game to vote on' : 'games to vote on', tone: 'var(--pb-amber)' })
  }
  const first = ladder.ladders?.[0]
  const mine = first?.rows.find((r) => r.is_club)
  if (has('ladder') && ladder.status === 'ok' && mine && mine.rank != null) {
    tiles.push({ id: 'ladder', label: 'Ladder', value: `#${mine.rank}`, hint: first.team })
  }
  if (has('season') && data.season) {
    tiles.push({ id: 'season', label: 'Runs this season', value: data.season.runs, hint: `${data.season.wickets} wickets · ${data.season.matches} matches` })
  }
  if (has('fines') && (data.fines || []).length) {
    const owing = data.fines.reduce((a, f) => a + Math.max(f.owing, 0), 0)
    tiles.push({ id: 'fines', label: 'Fines owing', value: owing > 0 ? money(owing) : 'All square', tone: owing > 0 ? 'var(--pb-amber)' : 'var(--pb-positive)' })
  }
  if (has('fees') && data.fees?.on_record) {
    const owe = data.fees.total_outstanding
    tiles.push({ id: 'fees', label: 'Fees owing', value: owe > 0 ? money(owe) : 'Nothing owing', tone: owe > 0 ? 'var(--pb-amber)' : 'var(--pb-positive)' })
  }
  if (has('training') && data.training) {
    tiles.push({ id: 'training', label: 'Training', value: data.training.attended_8_weeks, hint: 'sessions in 8 weeks' })
  }
  return tiles
}

// The player's own page: whichever modules the club has turned on, in the club's
// order, under a row of headline tiles. Only their own data, behind the same PIN
// cookie as the availability answers. Availability comes from the page's own
// state; the rest from one call. On a wide screen the modules sit in a grid, on a
// phone they are one column.
function MyPage({ token, me }) {
  const [data, setData] = useState(null)
  const [failed, setFailed] = useState(false)
  const [ladder, setLadder] = useState({ status: 'loading', ladders: [] })
  useEffect(() => {
    let alive = true
    api.availPublicProfile(token).then((d) => { if (alive) setData(d) }).catch(() => { if (alive) setFailed(true) })
    return () => { alive = false }
  }, [token])

  // A server that doesn't send the list is the page as it was before clubs could choose.
  const modules = data ? (data.modules ?? ['availability', 'squad', 'selected', 'training']) : []
  const wantsLadder = modules.includes('ladder')
  useEffect(() => {
    if (!wantsLadder) return undefined
    let alive = true
    api.availPublicLadder(token)
      .then((d) => { if (alive) setLadder({ status: 'ok', ladders: d.ladders || [] }) })
      .catch(() => { if (alive) setLadder({ status: 'failed', ladders: [] }) })
    return () => { alive = false }
  }, [token, wantsLadder])

  const render = (key) => {
    switch (key) {
      case 'availability': return <AvailabilityModule key={key} me={me} />
      case 'votes': return <VotesModule key={key} data={data} />
      case 'squad': return <SquadModule key={key} data={data} />
      case 'selected': return <SelectedModule key={key} data={data} />
      case 'training': return <TrainingModule key={key} data={data} />
      case 'ladder': return <LadderModule key={key} state={ladder} />
      case 'season': return <SeasonModule key={key} data={data} />
      case 'fees': return <FeesModule key={key} data={data} />
      case 'fines': return <FinesModule key={key} data={data} />
      default: return null
    }
  }

  const tiles = data ? dashboardTiles({ me, data, modules, ladder }) : []

  return (
    <div data-my-page>
      {failed && <div className="text-sm text-pb-faint mb-3">Your page could not load. Pull down to try again.</div>}
      {!data && !failed && <div className="text-sm text-pb-faint mb-3">Loading your page…</div>}
      {data && modules.length === 0 && (
        <div className="text-sm text-pb-faint" data-no-modules>Your club has not added anything to this page yet.</div>
      )}
      {data && modules.includes('votes') && (data.votes || []).length > 0 && <VotesBanner votes={data.votes} />}
      {tiles.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-2.5 mb-3" data-tiles>
          {tiles.map((t) => <Tile key={t.id} {...t} />)}
        </div>
      )}
      {data && modules.length > 0 && (
        // Columns rather than a grid: the cards differ a lot in height (Fines is tall), and
        // columns pack them tight with no gaps. The club's order runs down each column in turn.
        <div className="md:columns-2 lg:columns-3 md:gap-3" data-modules>
          {modules.map(render)}
        </div>
      )}
    </div>
  )
}

export default function PublicAvailability() {
  const { token } = useParams()
  // Arriving from the voting page: `?tab=mine` opens the player's own page and
  // `?player=<id>` has them already picked, so it is only the PIN left to type.
  const [searchParams] = useSearchParams()
  const playerParam = searchParams.get('player') || ''
  const autoPicked = useRef(false)
  const [step, setStep] = useState('loading') // loading | pick | pin | weekend | dead
  const [club, setClub] = useState(null)
  const [requirePin, setRequirePin] = useState(true)
  const [players, setPlayers] = useState([])
  const [search, setSearch] = useState('')
  const [chosen, setChosen] = useState(null) // {id, display_name, has_phone}
  const [pin, setPin] = useState('')
  const [verifying, setVerifying] = useState(false)
  const [error, setError] = useState('')
  const [me, setMe] = useState(null) // {player, dates, availability}
  const [savingDate, setSavingDate] = useState(null)
  const [savedDate, setSavedDate] = useState(null)
  const [weeksOpen, setWeeksOpen] = useState(1) // weeks of games showing, from the next one
  const [tab, setTab] = useState(searchParams.get('tab') === 'mine' ? 'mine' : 'weekend') // weekend | mine
  const pinRef = useRef(null)
  const weeks = useMemo(() => groupByWeek(me?.dates || []), [me?.dates])
  const pairs = useMemo(() => twoDayPairs(me?.dates || []), [me?.dates])
  // A club that has switched Maybe off offers only Available and Unavailable.
  const choices = me?.allow_maybe === false ? ALL_CHOICES.filter((c) => c !== 'MAYBE') : ALL_CHOICES

  // White-label: re-point --pb-accent (and its rgb form, used by a few tints) to
  // the club's colour for this page only. Falls back to the brand green.
  const accent = club?.accent_color || club?.primary_color || null

  const enterWeekend = useCallback(async () => {
    try {
      const data = await api.availPublicMe(token)
      setMe(data)
      if (data.club) setClub((c) => c || data.club)
      setStep('weekend')
      setError('')
    } catch (e) {
      // Cookie missing/expired — fall back to picking a name.
      setStep('pick')
    }
  }, [token])

  // Load branding + roster, and resume an existing verified session if present.
  useEffect(() => {
    let alive = true
    api.availPublicLanding(token)
      .then(async (d) => {
        if (!alive) return
        setClub(d.club)
        setRequirePin(d.require_pin)
        setPlayers(d.players || [])
        // Already verified on this device? Jump straight to the weekend.
        try {
          const mine = await api.availPublicMe(token)
          if (!alive) return
          setMe(mine)
          setStep('weekend')
        } catch {
          if (alive) setStep('pick')
        }
      })
      .catch(() => { if (alive) setStep('dead') })
    return () => { alive = false }
  }, [token])

  useEffect(() => { if (step === 'pin' && pinRef.current) pinRef.current.focus() }, [step])

  // A page left open in a group chat goes stale: once a game starts it is no
  // longer offered. Re-read when the tab comes back into view, unless a save is
  // in flight (the answer on screen is newer than the server's).
  const savingRef = useRef(null)
  useEffect(() => { savingRef.current = savingDate }, [savingDate])
  useEffect(() => {
    if (step !== 'weekend') return undefined
    const onVisible = () => {
      if (document.visibilityState !== 'visible' || savingRef.current) return
      api.availPublicMe(token).then((d) => { if (!savingRef.current) setMe(d) }).catch(() => {})
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [step, token])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return players
    return players.filter((p) => p.display_name.toLowerCase().includes(q))
  }, [players, search])

  const pickPlayer = async (p) => {
    setChosen(p)
    setPin('')
    setError('')
    if (requirePin) {
      setStep('pin')
      return
    }
    // No PIN required — verify with the name alone.
    await doVerify(p, '')
  }

  const doVerify = async (player, pinValue) => {
    setVerifying(true)
    setError('')
    try {
      await api.availPublicVerify(token, player.id, pinValue)
      await enterWeekend()
    } catch (e) {
      setError(e.message || 'That didn’t match. Please try again.')
    } finally {
      setVerifying(false)
    }
  }

  // From the voting page with ?player=<id>: pick that player once, on the name
  // step, so they land on the PIN box instead of searching for themselves.
  useEffect(() => {
    if (step !== 'pick' || !playerParam || autoPicked.current) return
    const p = players.find((x) => x.id === playerParam)
    if (p) { autoPicked.current = true; pickPlayer(p) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, playerParam, players])

  const submitPin = (e) => {
    e.preventDefault()
    if (!chosen || pin.length < 4) return
    doVerify(chosen, pin)
  }

  const switchPlayer = async () => {
    try { await api.availPublicSwitch(token) } catch {}
    setMe(null); setChosen(null); setPin(''); setSearch(''); setError(''); setWeeksOpen(1)
    setStep('pick')
  }

  const setAnswer = async (d, status) => {
    const prev = me
    // Optimistic — reflect the tap immediately.
    setMe((m) => ({ ...m, availability: { ...(m.availability || {}), [d]: { status, source: 'self' } } }))
    setSavingDate(d)
    try {
      await api.availPublicSet(token, { date: d, status })
      setSavedDate(d)
      setTimeout(() => setSavedDate((cur) => (cur === d ? null : cur)), 1600)
    } catch (e) {
      setMe(prev) // roll back
      setError(e.message || 'Couldn’t save — please try again.')
    } finally {
      setSavingDate((cur) => (cur === d ? null : cur))
    }
  }

  // Both weeks of a two-day game in one tap. Two writes, one per date (the store
  // is per date), each rolled back on its own if it fails.
  const setBoth = async (pair, status) => {
    const dates = [pair.day1, pair.day2]
    const prior = Object.fromEntries(dates.map((d) => [d, me.availability?.[d]]))
    setMe((m) => ({ ...m, availability: { ...(m.availability || {}), ...Object.fromEntries(dates.map((d) => [d, { status, source: 'self' }])) } }))
    setSavingDate(pair.key)
    const results = await Promise.allSettled(dates.map((d) => api.availPublicSet(token, { date: d, status })))
    const failed = dates.filter((_, i) => results[i].status === 'rejected')
    if (failed.length) {
      setMe((m) => {
        const av = { ...(m.availability || {}) }
        for (const d of failed) { if (prior[d]) av[d] = prior[d]; else delete av[d] }
        return { ...m, availability: av }
      })
      const first = results.find((r) => r.status === 'rejected')
      setError((first?.reason && first.reason.message) || 'Couldn’t save both weeks. Please try again.')
    } else {
      setSavedDate(pair.key)
      setTimeout(() => setSavedDate((cur) => (cur === pair.key ? null : cur)), 1600)
    }
    setSavingDate((cur) => (cur === pair.key ? null : cur))
  }

  return (
    <div className="min-h-screen bg-pb-bg text-pb-text" style={accent ? { '--pb-accent': accent } : undefined}>
      {/* The dashboard tab opens out on a wide screen; everything else stays a phone-width column. */}
      <div className={`${step === 'weekend' && tab === 'mine' ? 'max-w-md md:max-w-5xl' : 'max-w-md'} mx-auto px-4 py-8 sm:py-12`}>
        {step === 'loading' && (
          <div className="py-24 text-center text-pb-faint text-sm">Loading…</div>
        )}

        {step === 'dead' && (
          <div className="py-20 text-center">
            <div className="text-3xl mb-3">🔗</div>
            <div className="font-display font-bold text-lg">This link isn’t active</div>
            <p className="text-pb-faint text-sm mt-2">It may have been turned off or replaced. Ask your club for the current availability link.</p>
          </div>
        )}

        {step !== 'loading' && step !== 'dead' && <ClubHeader club={club} />}

        {/* Step 1 — pick your name */}
        {step === 'pick' && (
          <div>
            <input
              autoFocus
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search your name…"
              className="w-full bg-pb-surface2 border pb-hairline rounded-xl px-4 py-3 text-base focus:outline-none focus:border-pb-accent mb-3"
            />
            <div className="rounded-xl border pb-hairline overflow-hidden divide-y divide-pb-hairline max-h-[55vh] overflow-y-auto">
              {filtered.length === 0 && (
                <div className="px-4 py-6 text-center text-pb-faint text-sm">No players match “{search}”.</div>
              )}
              {filtered.map((p) => (
                <button
                  key={p.id}
                  onClick={() => pickPlayer(p)}
                  className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-pb-surface2 transition-colors"
                >
                  <span className="text-[15px] font-medium">{p.display_name}</span>
                  {requirePin && !p.has_phone
                    ? <span className="font-mono text-[10px] text-pb-faintest uppercase shrink-0">no mobile</span>
                    : <span className="text-pb-faintest shrink-0">→</span>}
                </button>
              ))}
            </div>
            <p className="text-center text-pb-faintest text-[11px] mt-5">
              Can’t find yourself, or no mobile on file? Ask your club admin.
            </p>
          </div>
        )}

        {/* Step 2 — prove it's you */}
        {step === 'pin' && chosen && (
          <form onSubmit={submitPin}>
            <div className="text-center mb-5">
              <div className="text-sm text-pb-faint">Hi</div>
              <div className="font-display font-bold text-2xl">{chosen.display_name}</div>
            </div>
            <Banner>{error}</Banner>
            {!chosen.has_phone ? (
              <div className="text-center text-pb-faint text-sm py-4">
                There’s no mobile number on file for you yet. Ask your club admin to add it, or to set your availability for you.
                <div className="mt-5"><button type="button" onClick={switchPlayer} className="text-pb-accent text-sm underline">← Pick a different name</button></div>
              </div>
            ) : (
              <>
                <label className="block text-center font-mono text-[11px] tracking-wide2 text-pb-faint uppercase mb-2">
                  Last 4 digits of your mobile
                </label>
                <input
                  ref={pinRef}
                  value={pin}
                  onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 4))}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="••••"
                  className="w-full text-center tracking-[0.6em] text-2xl font-mono bg-pb-surface2 border pb-hairline rounded-xl px-4 py-3.5 focus:outline-none focus:border-pb-accent"
                />
                <button
                  type="submit"
                  disabled={pin.length < 4 || verifying}
                  className="w-full mt-4 py-3.5 rounded-xl font-semibold text-pb-bg transition disabled:opacity-50"
                  style={{ background: 'var(--pb-accent)' }}
                >
                  {verifying ? 'Checking…' : 'Continue'}
                </button>
                <button type="button" onClick={switchPlayer} className="block mx-auto mt-4 text-pb-faint text-sm hover:text-pb-text">
                  ← Not you? Pick a different name
                </button>
              </>
            )}
          </form>
        )}

        {/* Step 3 — your weekend */}
        {step === 'weekend' && me && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="font-mono text-[11px] text-pb-faint">Signed in as</div>
                <div className="font-display font-bold text-lg">{me.player?.display_name}</div>
              </div>
              <button onClick={switchPlayer} className="text-pb-faint text-xs hover:text-pb-text underline shrink-0">Not you?</button>
            </div>
            {(me.squads || []).length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 -mt-2 mb-4" data-my-squads>
                <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint">Your squad</span>
                {me.squads.map((n) => (
                  <span key={n} className="text-[12px] font-semibold rounded-full px-2.5 py-0.5"
                    style={{ background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)', color: 'var(--pb-accent)' }}>{n}</span>
                ))}
              </div>
            )}
            <div role="tablist" className="grid grid-cols-2 gap-1 p-1 rounded-xl bg-pb-surface2 mb-4 md:max-w-sm">
              {[['weekend', 'Availability'], ['mine', 'My page']].map(([id, label]) => (
                <button key={id} role="tab" aria-selected={tab === id} data-tab={id} onClick={() => setTab(id)}
                  className={`py-2 rounded-lg text-sm font-semibold transition-colors ${tab === id ? 'bg-pb-surface text-pb-text shadow-sm' : 'text-pb-faint'}`}>{label}</button>
              ))}
            </div>
            <Banner>{error}</Banner>

            {tab === 'mine' && <MyPage token={token} me={me} />}
            {tab === 'weekend' && (<>

            {(me.dates || []).length === 0 && (
              <div className="rounded-xl border pb-hairline px-4 py-10 text-center text-pb-faint text-sm">
                No upcoming fixtures to set availability for yet. Check back soon.
              </div>
            )}

            <div className="flex flex-col gap-3">
              {weeks.slice(0, weeksOpen).flat().map((d) => {
                const cur = me.availability?.[d.date]?.status || 'NO_RESPONSE'
                const startsPair = Object.values(pairs).filter((pr) => pr.day1 === d.date)
                const wk = weekLabel(d)
                return (
                  <Fragment key={d.date}>
                  {startsPair.map((pr) => (
                    <div key={pr.key} className="relative">
                      <BothWeeks pair={pr} me={me} choices={choices} onPick={setBoth} busy={savingDate === pr.key} />
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
                            onClick={() => setAnswer(d.date, s)}
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
            <p className="text-center text-pb-faintest text-[11px] mt-6">
              Your answers save automatically. One tap covers every game that day. For a two-day game, answer each week or both at once.
            </p>
            </>)}
          </div>
        )}

        {step !== 'loading' && step !== 'dead' && (
          <div className="text-center mt-10">
            <span className="font-mono text-[10px] tracking-wide2 text-pb-faintest uppercase">Powered by BetterCricket</span>
          </div>
        )}
      </div>
    </div>
  )
}
