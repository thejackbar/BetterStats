// BetterSelect — the player's own page (public, no login).
//
// Reached via a per-club magic link (/avail/:token) pinned in a group chat or a
// QR. Pick your name, prove it's you with the last 4 digits of your mobile, and
// land on one dashboard: your photo and squads, the next games to answer
// (Available / Maybe / Unavailable), and whichever cards the club has turned on
// (votes, selected sides, training, ladder, season, fantasy, fees, fines).
// A signed cookie keeps you verified (~30 days); "Not you?" clears it.
//
// White-labelled from the club's own colours; the only dependency on the rest of
// the app is the shared availability colour map so a player's chips match the
// admin matrix exactly.
import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import { AvailabilityEditor, ALL_CHOICES, unansweredNextWeek } from './playerhome/AvailabilityEditor'
import Group, { useOpenSections } from './playerhome/Group'
import FantasyCard, { fmtLockShort, nextDeadline, ordinal } from './playerhome/FantasyCard'
import PlayerHero from './playerhome/PlayerHero'
import SeasonDashboard from './playerhome/SeasonDashboard'
import { Muted, Section, fmtShort, money } from './playerhome/ui'


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

// ─── The modules of the player's own page ───
// Each one is a Section the club can turn on or off in BetterSelect. They are
// declared here, at module level, and picked by key from the server's list.

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

// What the player has paid, newest first, across seasons. Five show, the rest open on a tap.
function PaymentsList({ payments }) {
  const [all, setAll] = useState(false)
  if (!payments || payments.length === 0) return null
  const shown = all ? payments : payments.slice(0, 5)
  // The season is only worth saying when the payments span more than one.
  const manySeasons = new Set(payments.map((p) => p.season)).size > 1
  return (
    <div className="mt-3" data-fee-payments>
      <div className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-1">Fees paid</div>
      {shown.map((p, i) => (
        <div key={`${p.date}-${i}`} className="flex items-baseline gap-3 py-1.5 border-t pb-hairline first:border-t-0 text-[13px]" data-fee-payment>
          <span className="w-[84px] shrink-0 text-pb-faint">{p.date ? fmtShort(p.date) : 'No date'}</span>
          <span className="min-w-0 flex-1 truncate">
            {p.kind}{p.method ? ` · ${p.method}` : ''}
            {manySeasons && p.season ? <span className="text-pb-faint"> · {p.season}</span> : null}
          </span>
          <span className="shrink-0 font-semibold">{money(p.amount)}</span>
        </div>
      ))}
      {payments.length > 5 && (
        <button type="button" data-fee-payments-more onClick={() => setAll((v) => !v)} className="text-[12px] text-pb-faint underline mt-1">
          {all ? 'Show fewer' : `Show all ${payments.length} payments`}
        </button>
      )}
    </div>
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
          <PaymentsList payments={f.payments} />
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

// The sections of the page, in the order a player reads them. Each holds the club's
// modules that belong to it, in the club's own order; a section with none drops out.
// Selection always shows, because the answer buttons are in it.
const GROUPS = [
  { id: 'selection', title: 'Selection', keys: ['squad', 'selected', 'training', 'ladder'] },
  { id: 'admin', title: 'Club admin', keys: ['fees', 'fines'] },
  { id: 'voting', title: 'Voting', keys: ['votes'], hideTitle: true },
  { id: 'stats', title: 'Stats', keys: ['season'] },
  { id: 'fantasy', title: 'Fantasy', keys: ['fantasy'], hideTitle: true },
]

const AMBER = 'var(--pb-amber)'
const GREEN = 'var(--pb-positive)'

// One line per section, from data the page already holds, shown even when the
// section is closed. Left empty rather than made up when there is nothing true to say.
function summaryFor(id, { me, data, ladder }) {
  if (id === 'selection') {
    const n = unansweredNextWeek(me)
    if (n > 0) return { text: `${n} to answer`, tone: AMBER }
    const side = (data?.selected || [])[0]
    if (side) return { text: `Selected ${fmtShort(side.date)} ${side.home_away === 'AWAY' ? 'at' : 'vs'} ${side.opponent_name || side.label || 'TBC'}` }
    return (me.dates || []).length ? { text: 'All answered', tone: GREEN } : { text: 'No games to answer yet' }
  }
  if (!data) return {}
  if (id === 'admin') {
    const fees = data.fees?.on_record ? data.fees.total_outstanding : null
    const fines = (data.fines || []).length ? data.fines.reduce((a, f) => a + Math.max(f.owing, 0), 0) : null
    if (fees === null && fines === null) return {}
    const owing = (fees || 0) + (fines || 0)
    return owing > 0 ? { text: `${money(owing)} owing`, tone: AMBER } : { text: 'All square', tone: GREEN }
  }
  if (id === 'voting') {
    const n = (data.votes || []).length
    if (n > 0) return { text: n === 1 ? '1 vote to cast' : `${n} votes to cast`, tone: AMBER }
    return (data.votes_cast || []).length ? { text: 'Up to date', tone: GREEN } : {}
  }
  if (id === 'stats') {
    const s = data.season
    return s ? { text: `${s.matches} ${s.matches === 1 ? 'match' : 'matches'} · ${s.runs} runs · ${s.wickets} wkts` } : { text: 'No games yet' }
  }
  if (id === 'fantasy') {
    const f = data.fantasy
    const next = f && nextDeadline(f.deadlines)
    if (!next) return {}
    const rank = f.team && f.team.built && f.team.rank ? ` · ${ordinal(f.team.rank)}` : ''
    return next.locked
      ? { text: `${next.name || `Round ${next.number}`} locked${rank}` }
      : { text: `Locks ${fmtLockShort(next.lock_at)}${rank}`, tone: AMBER }
  }
  return {}
}

// The player's own page: who they are, then collapsible sections (Selection with the
// answer buttons, Club admin, Voting, Stats, Fantasy). Only their own data, behind
// the same PIN cookie as the availability answers. The answers live in the page's own
// state (`availability` is the editor, built by the parent so a tap saves from here);
// the rest arrives in one call. A phone gets one column, a wide screen two.
function MyPage({ token, me, club, availability, onSwitch }) {
  const [data, setData] = useState(null)
  const [failed, setFailed] = useState(false)
  const [ladder, setLadder] = useState({ status: 'loading', ladders: [] })
  const sections = useOpenSections()
  useEffect(() => {
    let alive = true
    const load = () => api.availPublicProfile(token).then((d) => { if (alive) setData(d) }).catch(() => { if (alive) setFailed(true) })
    load()
    // Coming back with the browser's Back button restores this page as it was, so a vote
    // cast in between would still read as due. Read it again when that happens.
    const onShow = (e) => { if (e.persisted) load() }
    window.addEventListener('pageshow', onShow)
    return () => { alive = false; window.removeEventListener('pageshow', onShow) }
  }, [token])

  // A server that doesn't send the list is the page as it was before clubs could choose.
  const modules = data ? (data.modules ?? ['squad', 'selected', 'training']) : []
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
      case 'votes': return <VotesModule key={key} data={data} />
      case 'squad': return <SquadModule key={key} data={data} />
      case 'selected': return <SelectedModule key={key} data={data} />
      case 'training': return <TrainingModule key={key} data={data} />
      case 'ladder': return <LadderModule key={key} state={ladder} />
      case 'season': return <SeasonDashboard key={key} data={data} />
      case 'fantasy': return <FantasyCard key={key} data={data} />
      case 'fees': return <FeesModule key={key} data={data} />
      case 'fines': return <FinesModule key={key} data={data} />
      default: return null
    }
  }

  // The profile call names the squads the club lets players see; until it lands the
  // availability call already carries them, so the hero does not wait.
  const squads = data ? (data.squads || []) : (me.squads || [])
  const shown = GROUPS
    .map((g) => ({ ...g, mods: modules.filter((m) => g.keys.includes(m)) }))
    .filter((g) => g.id === 'selection' || g.mods.length > 0)
  const allOpen = shown.every((g) => sections.isOpen(g.id))

  return (
    <div data-my-page>
      <PlayerHero club={club} player={data?.player || me.player} squads={squads} onSwitch={onSwitch} />
      {failed && <div className="text-sm text-pb-faint mb-3" data-profile-failed>The rest of your page could not load. Reload to try again.</div>}
      {!data && !failed && <div className="text-sm text-pb-faint mb-3" data-profile-loading>Loading your page…</div>}
      <div className="flex justify-end mb-2">
        <button type="button" data-toggle-all onClick={() => sections.setAll(shown.map((g) => g.id), !allOpen)}
          className="text-[12px] text-pb-faint underline">{allOpen ? 'Collapse all' : 'Expand all'}</button>
      </div>
      <div className="md:columns-2 md:gap-3" data-groups>
        {shown.map((g) => {
          const { text, tone } = summaryFor(g.id, { me, data, ladder })
          return (
            <Group key={g.id} id={g.id} hideTitle={g.hideTitle}
              title={g.id === 'fantasy' && data?.fantasy?.name ? data.fantasy.name : g.title}
              summary={text} tone={tone} open={sections.isOpen(g.id)} onToggle={sections.toggle}>
              {g.id === 'selection' && availability}
              {g.mods.map(render)}
            </Group>
          )
        })}
      </div>
    </div>
  )
}

export default function PublicAvailability() {
  const { token } = useParams()
  // Arriving from the voting page: `?player=<id>` has them already picked, so it is
  // only the PIN left to type. (`?tab=mine` on older links is ignored: there is one page now.)
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
  const pinRef = useRef(null)
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
    setMe(null); setChosen(null); setPin(''); setSearch(''); setError('')
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

  // Both weeks of a two-day game in one tap. `statuses` is [week 1, week 2] (a
  // lone status means the same for both). Two writes, one per date (the store is
  // per date), each rolled back on its own if it fails.
  const setBoth = async (pair, statuses) => {
    const dates = [pair.day1, pair.day2]
    const per = Array.isArray(statuses) ? statuses : [statuses, statuses]
    const prior = Object.fromEntries(dates.map((d) => [d, me.availability?.[d]]))
    setMe((m) => ({ ...m, availability: { ...(m.availability || {}), ...Object.fromEntries(dates.map((d, i) => [d, { status: per[i], source: 'self' }])) } }))
    setSavingDate(pair.key)
    const results = await Promise.allSettled(dates.map((d, i) => api.availPublicSet(token, { date: d, status: per[i] })))
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
      {/* The dashboard opens out on a wide screen; the name and PIN steps stay a phone-width column. */}
      <div className={`${step === 'weekend' ? 'max-w-md md:max-w-5xl' : 'max-w-md'} mx-auto px-4 py-6 sm:py-10`}>
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

        {(step === 'pick' || step === 'pin') && <ClubHeader club={club} />}

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

        {/* Step 3 — your page: who you are, the next games to answer, and the club's cards */}
        {step === 'weekend' && me && (
          <div>
            <Banner>{error}</Banner>
            <MyPage
              token={token}
              me={me}
              club={club}
              onSwitch={switchPlayer}
              availability={(
                <AvailabilityEditor
                  me={me}
                  choices={choices}
                  savingDate={savingDate}
                  savedDate={savedDate}
                  onAnswer={setAnswer}
                  onBoth={setBoth}
                />
              )}
            />
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
