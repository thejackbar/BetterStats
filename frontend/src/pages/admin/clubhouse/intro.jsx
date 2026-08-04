import { useState, useEffect, useCallback } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../../../contexts/AuthContext'
import { Button, Caption, Note, TINT } from '../../../components/admin/ui'

// Screen introductions.
//
// A club officer asked for these directly, and for the switch to turn them off:
// the introduction pages help a new committee and irritate a practised one. So
// they are a per-person preference, not a per-club one — a treasurer joining in
// March gets them even if the rest of the committee turned them off in October.
//
// Rules, all enforced here rather than per screen:
//   · Today never gets one. It is the front door.
//   · A deep link always skips it and marks the screen seen. Pressing "Open
//     accounts" on Today means you already said what you wanted; landing on an
//     explanation instead would be a small insult.
//   · Only sidebar navigation can trigger one.
//   · The `?` beside every screen title reopens it on demand, in every mode.

export const INTRO_MODES = [
  { key: 'always', label: 'Every time', note: 'Every screen introduces itself each time you open it from the sidebar.' },
  { key: 'once', label: 'First visit only', note: 'A screen introduces itself the first time you open it, then gets out of the way.' },
  { key: 'never', label: 'Never', note: 'Screens open straight to the work. The ? beside a title still explains one on demand.' },
]

const DEFAULT_MODE = 'once'
const modeKey = uid => `bs_clubhouse_intro_mode_${uid || 'anon'}`
const seenKey = uid => `bs_clubhouse_intro_seen_${uid || 'anon'}`

const read = (k, fallback) => {
  try { const v = localStorage.getItem(k); return v == null ? fallback : JSON.parse(v) } catch { return fallback }
}
const write = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)) } catch { /* private mode */ } }

export function useIntroSettings() {
  const { user } = useAuth()
  const uid = user?.id
  const [mode, setModeState] = useState(() => read(modeKey(uid), DEFAULT_MODE))
  const [seen, setSeenState] = useState(() => read(seenKey(uid), {}))

  useEffect(() => {
    setModeState(read(modeKey(uid), DEFAULT_MODE))
    setSeenState(read(seenKey(uid), {}))
  }, [uid])

  const setMode = useCallback(m => { setModeState(m); write(modeKey(uid), m) }, [uid])
  const markSeen = useCallback(key => {
    setSeenState(s => { const next = { ...s, [key]: true }; write(seenKey(uid), next); return next })
  }, [uid])
  const resetSeen = useCallback(() => { setSeenState({}); write(seenKey(uid), {}) }, [uid])

  return { mode, setMode, seen, markSeen, resetSeen, seenCount: Object.keys(seen).length }
}

// What a screen calls. Returns whether to render the introduction instead of
// the screen, plus the `?` handler for the header.
export function useScreenIntro(key) {
  const { mode, setMode, seen, markSeen } = useIntroSettings()
  const location = useLocation()
  // A deep link says "take me to the work" — Today's actions and the
  // Email-these-N buttons all navigate with it.
  const deepLinked = !!location.state?.skipIntro

  // Decided ONCE, on arrival. Marking the screen seen (below) re-renders with
  // `seen[key]` true, so a value derived live would show the introduction for a
  // single frame and then yank it away.
  const [open, setOpen] = useState(() =>
    !!key && !deepLinked && mode !== 'never' && (mode === 'always' || !seen[key]))
  const [forced, setForced] = useState(false)
  const showing = open || forced

  // Arriving marks the screen introduced either way, so a deep link doesn't
  // leave an introduction lying in wait for the next visit.
  useEffect(() => { if (key && !seen[key]) markSeen(key) }, [key])   // eslint-disable-line react-hooks/exhaustive-deps

  return {
    showing,
    reopen: () => setForced(true),
    dismiss: () => { setForced(false); setOpen(false) },
    turnOff: () => { setMode('never'); setForced(false); setOpen(false) },
  }
}

function Bullet({ children }) {
  return (
    <li className="flex items-start gap-2.5 text-[13.5px] text-pb-dim leading-[1.65]">
      <span className="w-[5px] h-[5px] rounded-full mt-[7px] shrink-0" style={{ background: 'var(--pb-accent)' }} />
      <span style={{ textWrap: 'pretty' }}>{children}</span>
    </li>
  )
}

// The interim page itself. `intro` is one entry from INTROS below.
export default function ScreenIntro({ intro, onContinue, onTurnOff }) {
  return (
    <div className="max-w-[74rem]">
      <Caption>What this screen is for</Caption>
      <h2 className="font-display font-semibold text-[19px] text-pb-text mt-2 leading-[1.4]" style={{ maxWidth: '46ch' }}>
        {intro.lede}
      </h2>
      <ul className="mt-5 space-y-2.5 max-w-[52ch]">
        {intro.points.map((p, i) => <Bullet key={i}>{p}</Bullet>)}
      </ul>
      {intro.history && (
        <Note className="mt-5 max-w-[56ch]">{intro.history}</Note>
      )}
      <div className="flex items-center gap-2.5 mt-7 flex-wrap">
        <Button variant="primary" size="lg" onClick={onContinue}>Continue to {intro.title} →</Button>
        <Button onClick={onTurnOff}>Don't show introductions again</Button>
      </div>
      <div className="text-[12.5px] text-pb-faint mt-6 leading-[1.6]" style={{ borderTop: `1px solid ${TINT.border}`, paddingTop: 14, maxWidth: '56ch' }}>
        You are seeing this because screen introductions are set to show on a first visit.{' '}
        <Link to="/admin/clubhouse/settings" className="underline" style={{ color: 'var(--pb-accent-ink)' }}>Change that in Settings</Link>,
        or press the ? beside a screen title to read one again.
      </div>
    </div>
  )
}

// One entry per screen. The three not-yet-rebuilt screens are here too, so the
// registry is the functional brief for them when they land.
export const INTROS = {
  directory: {
    title: 'Directory',
    lede: 'One record per person, whatever their relationship to the club.',
    points: [
      'Find anyone — a player, a volunteer, a committee member, a parent — without guessing which list they are on.',
      'Read a person whole: their balance, club roles, qualifications, hours and kit in one record.',
      'Filter to a group and email it from the same screen, instead of rebuilding the group somewhere else.',
    ],
    history: 'This replaced three separate people lists — the Fees member list, the Comms contact list and the club directory — which each held part of the same person and none of the whole.',
  },
  accounts: {
    title: 'Accounts',
    lede: 'One balance per person, covering everything they owe the club.',
    points: [
      'Subs and match fees sit beside issued kit, so a member has one balance rather than two.',
      'A payment settles their games oldest first, and the per-game status is worked out on read — edit a payment and it re-allocates itself.',
      'Filter to who owes and email exactly those people.',
    ],
    history: 'Stock charges land here now. Kit used to be owed in the merch ledger, which never met the fee ledger, so nobody could answer "what does this person owe us".',
  },
  audiences: {
    title: 'Audiences',
    lede: 'One way to describe a group of people, and it resolves when you send.',
    points: [
      'An audience is a set of conditions, not a frozen copy — someone who joins tomorrow is in it tomorrow.',
      'A hand-picked list is just an audience whose rule is "these people". There is no second mechanism to learn.',
      'Every audience reports how many people it matches and how many can actually be reached by email.',
    ],
    history: 'This replaced Contacts, Lists and Segments — three answers to one question, each with its own screen and its own idea of who a person was.',
  },
  inventory: {
    title: 'Inventory',
    lede: 'What the club holds, and what happens to the money when it moves.',
    points: [
      'Apparel, equipment and canteen run on one engine: a product, its variants, and a running balance per variant.',
      'Issuing something to a member takes it out of stock and posts the charge to their account in the same motion.',
      'Low stock, expiring lines and service-due gear all surface on Today rather than waiting to be noticed.',
    ],
  },
  integrations: {
    title: 'Integrations',
    lede: 'Every outside connection the club runs on, in one place with a live status.',
    points: [
      'Square is connected once for the club, not once per screen that happens to use it.',
      'Xero pulls bank transactions in so they can be matched against what members owe.',
      'The email provider that sends your campaigns is set up here too.',
    ],
    history: 'Square used to be connected twice — once under fees and once under stock — with no sign on either screen that the other existed.',
  },
  reports: {
    title: 'Reports',
    lede: 'The club\'s numbers, with one place to choose which part you are asking about.',
    points: [
      'Money and stock report from the same screen instead of one each.',
      'Every figure is derived from the same records the rest of the module reads, so nothing can quietly disagree.',
    ],
  },
  emails: {
    title: 'Emails',
    lede: 'Write once, send to an audience, and see what happened.',
    points: [
      'Pick an audience rather than building a recipient list by hand.',
      'Templates keep the club\'s look consistent without anyone editing HTML.',
      'Opens, clicks and bounces come back against the person, not just the send.',
    ],
  },
  payments: {
    title: 'Payments',
    lede: 'Money in, matched to the people it came from.',
    points: [
      'Import a bank CSV and match rows to members instead of typing them in.',
      'A match-fee payment settles that member\'s games oldest first, automatically.',
    ],
  },
  rateCard: {
    title: 'Rate card',
    lede: 'What each kind of member pays, for the season.',
    points: [
      'One tier per kind of member, carrying both the subs and the per-match rate.',
      'A member with no tier is flagged rather than silently charged nothing.',
    ],
    history: 'This merged the Fee Schedule and Membership Types screens, which described the same thing from two directions.',
  },
}
