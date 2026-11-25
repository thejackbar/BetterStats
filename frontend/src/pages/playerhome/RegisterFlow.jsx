// "Can't find your name?" on the player's own page (/playerdash/:token).
//
// Most past players are already on the club's books with their stats, only hidden from the name
// list because they have not played lately, so the first step is a search of past players. Then one
// form, in four short sections (about you, how you're connected, your cricket, getting involved).
//
// The server does the matching (routers/public_player_register.py). Its answer drives what happens:
//   signed_in         straight to their page. `matched` means they were linked to their own record
//                     (the mobile they typed is the club's one for them, or the old number's digits).
//   need_pin          the club has a different mobile for that record: ask for its last 4 digits.
//   possible_matches  a new sign-up whose name is already on the books: "Is one of these you?"
//   pending           a record with no mobile on it: the club confirms it first.
//
// Every component here is declared at module level (never inside a render function).
import { useEffect, useRef, useState } from 'react'
import { api } from '../../lib/api'
import { BOWLING_OPTS } from '../../lib/playerAttributes'

const inputCls = 'w-full bg-pb-surface2 border pb-hairline rounded-xl px-4 py-3 text-base focus:outline-none focus:border-pb-accent'
const PLAYING_ROLES = ['current_player', 'ex_player']
const CRICKET_ROLES = [
  ['Batter', 'Batter'], ['Bowler', 'Bowler'], ['All Rounder', 'All-rounder'],
  ['Wicketkeeper', 'Wicketkeeper'], ['Wicketkeeper-Batter', 'Keeper and batter'],
]
const HANDS = [['RIGHT', 'Right handed'], ['LEFT', 'Left handed']]

function splitName(display) {
  const n = (display || '').trim()
  if (n.includes(',')) {
    const [last, ...rest] = n.split(',')
    return { first: rest.join(',').trim(), last: last.trim() }
  }
  const parts = n.split(/\s+/)
  return parts.length > 1 ? { first: parts.slice(0, -1).join(' '), last: parts[parts.length - 1] } : { first: '', last: n }
}

function Field({ label, hint, children, htmlFor }) {
  return (
    <div className="mb-4">
      <label htmlFor={htmlFor} className="block text-sm font-semibold mb-1.5">{label}</label>
      {children}
      {hint && <p className="text-[11.5px] text-pb-faintest mt-1">{hint}</p>}
    </div>
  )
}

function Section({ title, children, attr }) {
  return (
    <section className="pt-5 mt-5 border-t pb-hairline first:border-t-0 first:pt-0 first:mt-0" {...attr}>
      <h2 className="font-mono text-[10.5px] uppercase tracking-wide2 text-pb-faint mb-3">{title}</h2>
      {children}
    </section>
  )
}

function Chip({ on, onClick, children, attr }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={on} {...attr}
      className={`px-3 py-2 rounded-full border text-sm transition-colors ${on ? 'font-semibold text-pb-bg' : 'pb-hairline text-pb-dim hover:bg-pb-surface2'}`}
      style={on ? { background: 'var(--pb-accent)', borderColor: 'var(--pb-accent)' } : undefined}>
      {children}
    </button>
  )
}

function ChipGroup({ label, id, children, attr }) {
  return (
    <div className="mb-4" role="group" aria-labelledby={id}>
      <div id={id} className="text-sm font-semibold mb-1.5">{label}</div>
      <div className="flex flex-wrap gap-2" {...attr}>{children}</div>
    </div>
  )
}

function Tick({ id, checked, onChange, children, attr }) {
  return (
    <div className="flex items-start gap-3 mb-3">
      <input id={id} type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-1 h-4 w-4 shrink-0" {...attr} />
      <label htmlFor={id} className="text-sm text-pb-dim">{children}</label>
    </div>
  )
}

function Notice({ tone = 'red', children }) {
  if (!children) return null
  const c = tone === 'red' ? 'var(--pb-red)' : 'var(--pb-amber)'
  return (
    <div role="alert" className="rounded-xl px-4 py-3 mb-4 text-sm" style={{ background: `color-mix(in srgb, ${c} 12%, transparent)`, color: c }}>
      {children}
    </div>
  )
}

function FindStep({ token, initialQuery, fmtName, onPick, onNew, onBack }) {
  const [q, setQ] = useState(initialQuery || '')
  const [results, setResults] = useState(null) // null: not searched yet
  const [error, setError] = useState('')
  const seq = useRef(0)

  useEffect(() => {
    const term = q.trim()
    if (term.replace(/\s/g, '').length < 3) { setResults(null); return undefined }
    const mine = ++seq.current
    const t = setTimeout(() => {
      api.availPublicPastPlayers(token, term)
        .then((d) => { if (mine === seq.current) { setResults(d.players || []); setError('') } })
        .catch((e) => { if (mine === seq.current) setError(e.message || 'Search failed. Try again.') })
    }, 250)
    return () => clearTimeout(t)
  }, [q, token])

  return (
    <div data-register-find>
      <h1 className="font-display font-bold text-xl text-center mb-1">Played here before?</h1>
      <p className="text-center text-pb-faint text-sm mb-4">
        Your old record may be tucked away because you haven’t played lately. Find it and your stats come with you.
      </p>
      <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search your name…"
        className={`${inputCls} mb-3`} data-register-search />
      <Notice>{error}</Notice>
      {results === null && <p className="text-center text-pb-faintest text-xs mb-3">Type at least three letters.</p>}
      {results !== null && (
        <div className="rounded-xl border pb-hairline overflow-hidden divide-y divide-pb-hairline max-h-[45vh] overflow-y-auto mb-3">
          {results.length === 0 && (
            <div className="px-4 py-5 text-center text-pb-faint text-sm">No past players match “{q.trim()}”.</div>
          )}
          {results.map((p) => (
            <button key={p.id} type="button" onClick={() => onPick(p)} data-register-past={p.id}
              className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-pb-surface2 transition-colors">
              <span className="min-w-0">
                <span className="block text-[15px] font-medium truncate">{fmtName(p.display_name)}</span>
                <span className="block text-[11.5px] text-pb-faintest">
                  {p.last_played_year ? `Last played ${p.last_played_year}` : 'No games on record'}
                </span>
              </span>
              <span className="text-pb-faintest shrink-0 text-sm">That’s me →</span>
            </button>
          ))}
        </div>
      )}
      <div className="rounded-xl border pb-hairline p-4 mt-4 text-center">
        <div className="text-sm font-semibold mb-1">Not a past player, or can’t find yourself?</div>
        <p className="text-pb-faint text-[12.5px] mb-3">New players, parents, volunteers and supporters are all welcome.</p>
        <button type="button" onClick={onNew} data-register-new
          className="w-full py-3 rounded-xl font-semibold text-pb-bg" style={{ background: 'var(--pb-accent)' }}>
          Sign up
        </button>
      </div>
      <button type="button" onClick={onBack} className="block mx-auto mt-5 text-sm text-pb-faint underline">
        Back to the name list
      </button>
    </div>
  )
}

function MatchesPanel({ players, fmtName, onPick, onNone, busy }) {
  return (
    <div className="rounded-xl border p-4 mb-4" style={{ borderColor: 'var(--pb-accent)' }} data-register-matches>
      <div className="font-semibold mb-1">Is one of these you?</div>
      <p className="text-pb-faint text-[12.5px] mb-3">The club already has someone with your name. Pick yourself so your record and stats stay together.</p>
      <div className="flex flex-col gap-2 mb-3">
        {players.map((p) => (
          <button key={p.id} type="button" disabled={busy} onClick={() => onPick(p)} data-register-match={p.id}
            className="flex items-center justify-between gap-3 rounded-lg border pb-hairline px-3 py-2.5 text-left hover:bg-pb-surface2">
            <span className="min-w-0">
              <span className="block font-medium truncate">{fmtName(p.display_name)}</span>
              <span className="block text-[11.5px] text-pb-faintest">{p.last_played_year ? `Last played ${p.last_played_year}` : 'No games on record'}</span>
            </span>
            <span className="text-sm shrink-0" style={{ color: 'var(--pb-accent)' }}>That’s me</span>
          </button>
        ))}
      </div>
      <button type="button" disabled={busy} onClick={onNone} className="text-sm text-pb-faint underline" data-register-not-me>
        None of these are me
      </button>
    </div>
  )
}

function CricketFields({ f, set, isClaim }) {
  const pl = f.playing
  const setPl = (k, v) => set('playing', { ...pl, [k]: v })
  const bowlLabel = BOWLING_OPTS.find((o) => o[1] === (pl.bowling_action || null) && o[2] === (pl.bowling_type || null))?.[0] || '—'
  return (
    <>
      <ChipGroup label="What did you do?" id="reg-crole" attr={{ 'data-register-cricket-role': true }}>
        {CRICKET_ROLES.map(([v, label]) => (
          <Chip key={v} on={pl.player_role === v} onClick={() => setPl('player_role', pl.player_role === v ? undefined : v)} attr={{ 'data-crole': v }}>{label}</Chip>
        ))}
      </ChipGroup>
      <ChipGroup label="Bats" id="reg-hand">
        {HANDS.map(([v, label]) => (
          <Chip key={v} on={pl.batting_hand === v} onClick={() => setPl('batting_hand', pl.batting_hand === v ? undefined : v)} attr={{ 'data-hand': v }}>{label}</Chip>
        ))}
      </ChipGroup>
      <Field label="Bowls" htmlFor="reg-bowl">
        <select id="reg-bowl" value={bowlLabel} className={inputCls} data-register-bowling
          onChange={(e) => {
            const hit = BOWLING_OPTS.find((o) => o[0] === e.target.value)
            set('playing', { ...pl, bowling_action: hit?.[1] || undefined, bowling_type: hit?.[2] || undefined })
          }}>
          {BOWLING_OPTS.map(([label]) => <option key={label} value={label}>{label === '—' ? 'Doesn’t bowl' : label}</option>)}
        </select>
      </Field>
      <Tick id="reg-opener" checked={!!pl.is_opening_batsman} onChange={(v) => setPl('is_opening_batsman', v || undefined)} attr={{ 'data-register-opener': true }}>
        Opening batter
      </Tick>
      <Tick id="reg-overseas" checked={!!pl.is_overseas} onChange={(v) => set('playing', { ...pl, is_overseas: v || undefined, overseas_country: v ? pl.overseas_country : undefined })} attr={{ 'data-register-overseas': true }}>
        Overseas player
      </Tick>
      {pl.is_overseas && (
        <Field label="Which country?" htmlFor="reg-country">
          <input id="reg-country" value={pl.overseas_country || ''} onChange={(e) => setPl('overseas_country', e.target.value)} className={inputCls} />
        </Field>
      )}
      {!isClaim && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-3 mt-2">
          <Field label="Years at the club" htmlFor="reg-years" hint="For example 2008 to 2015.">
            <input id="reg-years" value={f.years_played} onChange={(e) => set('years_played', e.target.value)} className={inputCls} />
          </Field>
          <Field label="Grades or teams" htmlFor="reg-grades" hint="For example 2nd XI, Under 16s.">
            <input id="reg-grades" value={f.grades_played} onChange={(e) => set('grades_played', e.target.value)} className={inputCls} />
          </Field>
        </div>
      )}
    </>
  )
}

// Only what was actually picked goes to the server; undefined keys are dropped.
function cleanPlaying(pl) {
  return Object.fromEntries(Object.entries(pl).filter(([, v]) => v !== undefined && v !== ''))
}

function FormStep({ token, initialClaim, roles, interests, fmtName, onDone, onBack }) {
  const start = initialClaim ? splitName(initialClaim.display_name) : { first: '', last: '' }
  const [claim, setClaim] = useState(initialClaim)
  const [f, setF] = useState({
    first_name: start.first, last_name: start.last, role: initialClaim ? 'ex_player' : '',
    phone: '', email: '', date_of_birth: '', years_played: '', grades_played: '', notes: '',
    interests: [], contact_consent: false, pin: '', playing: {},
  })
  const [needPin, setNeedPin] = useState(false)
  const [matches, setMatches] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }))
  const playing = PLAYING_ROLES.includes(f.role)

  const toggleInterest = (k) => set('interests', f.interests.includes(k) ? f.interests.filter((x) => x !== k) : [...f.interests, k])

  const send = async ({ asClaim = claim, confirmedNew = false } = {}) => {
    setError('')
    setBusy(true)
    try {
      const body = {
        first_name: f.first_name, last_name: f.last_name, role: f.role, phone: f.phone, email: f.email,
        date_of_birth: f.date_of_birth || null, notes: f.notes, interests: f.interests, contact_consent: f.contact_consent,
        playing: playing ? cleanPlaying(f.playing) : {},
        years_played: playing && !asClaim ? f.years_played : '', grades_played: playing && !asClaim ? f.grades_played : '',
      }
      if (asClaim) body.claim_player_id = asClaim.id
      if (asClaim && needPin && f.pin) body.pin = f.pin
      if (confirmedNew) body.confirmed_new = true
      const r = await api.availPublicRegister(token, body)
      if (r?.status === 'need_pin') { setClaim(asClaim); setMatches(null); setNeedPin(true); return }
      if (r?.status === 'possible_matches') { setMatches(r.players || []); return }
      onDone(r, asClaim)
    } catch (err) {
      setError(err.message || 'That didn’t go through. Please try again.')
    } finally { setBusy(false) }
  }

  const submit = (e) => {
    e.preventDefault()
    if (!f.role) { setError('Pick how you’re connected to the club.'); return }
    if (needPin && f.pin.length < 4) { setError('Enter the last 4 digits of the mobile the club has for you.'); return }
    send()
  }

  const title = claim ? `Welcome back, ${splitName(claim.display_name).first || fmtName(claim.display_name)}` : 'Sign up'
  const intro = claim
    ? (claim.has_phone
      ? 'Use the mobile the club has for you and you’ll go straight to your page.'
      : 'There’s no mobile on this record yet, so the club will confirm it’s you before you can log in.')
    : 'Tell the club a little about yourself. You’ll go straight to your page.'

  return (
    <form onSubmit={submit} data-register-form={claim ? 'claim' : 'new'}>
      <h1 className="font-display font-bold text-xl text-center mb-1">{title}</h1>
      {claim && (
        <p className="text-center text-[12.5px] text-pb-faintest mb-1" data-register-claim-name>
          {fmtName(claim.display_name)}{claim.last_played_year ? ` · last played ${claim.last_played_year}` : ''}
        </p>
      )}
      <p className="text-center text-pb-faint text-sm mb-5">{intro}</p>
      <Notice>{error}</Notice>

      <Section title="About you">
        <div className="grid grid-cols-2 gap-3">
          <Field label="First name" htmlFor="reg-first">
            <input id="reg-first" value={f.first_name} onChange={(e) => set('first_name', e.target.value)} className={inputCls} autoComplete="given-name" required />
          </Field>
          <Field label="Surname" htmlFor="reg-last">
            <input id="reg-last" value={f.last_name} onChange={(e) => set('last_name', e.target.value)} className={inputCls} autoComplete="family-name" required />
          </Field>
        </div>
        <Field label="Mobile" htmlFor="reg-phone" hint="Its last four digits are how you log in next time.">
          <input id="reg-phone" type="tel" value={f.phone} onChange={(e) => set('phone', e.target.value)} className={inputCls} autoComplete="tel" required />
        </Field>
        {needPin && claim && (
          <div data-register-pin-box>
            <Notice tone="amber">
              The club has a different mobile for {fmtName(claim.display_name)}. Enter the last 4 digits of that number to show it’s you. We’ll pass your new number to the club.
            </Notice>
            <Field label="Last 4 digits of your old mobile" htmlFor="reg-pin">
              <input id="reg-pin" value={f.pin} onChange={(e) => set('pin', e.target.value.replace(/\D/g, '').slice(0, 4))}
                inputMode="numeric" autoComplete="one-time-code" placeholder="••••" autoFocus
                className={`${inputCls} text-center tracking-[0.6em] font-mono`} data-register-pin />
            </Field>
          </div>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-3">
          <Field label="Email (optional)" htmlFor="reg-email">
            <input id="reg-email" type="email" value={f.email} onChange={(e) => set('email', e.target.value)} className={inputCls} autoComplete="email" />
          </Field>
          <Field label="Date of birth (optional)" htmlFor="reg-dob">
            <input id="reg-dob" type="date" value={f.date_of_birth} onChange={(e) => set('date_of_birth', e.target.value)} className={inputCls} autoComplete="bday" />
          </Field>
        </div>
      </Section>

      <Section title="How you’re connected">
        <div className="flex flex-wrap gap-2" role="group" aria-label="How you’re connected to the club" data-register-roles>
          {roles.map((r) => (
            <Chip key={r.key} on={f.role === r.key} onClick={() => set('role', r.key)} attr={{ 'data-role': r.key }}>{r.label}</Chip>
          ))}
        </div>
      </Section>

      {playing && (
        <Section title="Your cricket" attr={{ 'data-register-cricket': true }}>
          <CricketFields f={f} set={set} isClaim={!!claim} />
        </Section>
      )}

      <Section title="Getting involved">
        <ChipGroup label="Would you like to help with anything?" id="reg-int" attr={{ 'data-register-interests': true }}>
          {interests.map((i) => (
            <Chip key={i.key} on={f.interests.includes(i.key)} onClick={() => toggleInterest(i.key)} attr={{ 'data-interest': i.key }}>{i.label}</Chip>
          ))}
        </ChipGroup>
        <Field label="Anything else for the club? (optional)" htmlFor="reg-notes">
          <textarea id="reg-notes" rows={2} value={f.notes} onChange={(e) => set('notes', e.target.value)} className={inputCls}
            placeholder="For example, when you’re free, or who you played with" />
        </Field>
        <Tick id="reg-consent" checked={f.contact_consent} onChange={(v) => set('contact_consent', v)} attr={{ 'data-register-consent': true }}>
          The club can contact me about playing, volunteering and club news.
        </Tick>
      </Section>

      {matches && matches.length > 0 && (
        <MatchesPanel players={matches} fmtName={fmtName} busy={busy}
          onPick={(p) => { setMatches(null); setClaim(p); send({ asClaim: p }) }}
          onNone={() => { setMatches(null); send({ asClaim: null, confirmedNew: true }) }} />
      )}

      {!(matches && matches.length) && (
        <button type="submit" disabled={busy} data-register-submit
          className="w-full mt-4 py-3.5 rounded-xl font-semibold text-pb-bg transition disabled:opacity-50" style={{ background: 'var(--pb-accent)' }}>
          {busy ? 'Saving…' : (claim && !claim.has_phone ? 'Send to the club' : 'Open my page')}
        </button>
      )}
      <button type="button" onClick={onBack} className="block mx-auto mt-4 text-sm text-pb-faint underline">Back</button>
    </form>
  )
}

function PendingStep({ name, onBack }) {
  return (
    <div className="text-center py-6" data-register-pending>
      <div className="text-3xl mb-3">👍</div>
      <h1 className="font-display font-bold text-xl mb-2">Thanks, we’ve told the club</h1>
      <p className="text-pb-faint text-sm">
        They’ll check that {name ? `${name} is you` : 'the record is yours'} and add your mobile. Once they have, come back,
        tap “Can’t find your name?”, find yourself and use that mobile.
      </p>
      <button type="button" onClick={onBack} className="mt-6 text-sm text-pb-faint underline">Back to the name list</button>
    </div>
  )
}

export default function RegisterFlow({ token, initialQuery, fmtName, onSignedIn, onBack }) {
  const [step, setStep] = useState('find') // find | form | pending
  const [claim, setClaim] = useState(null)
  const [opts, setOpts] = useState(null)
  const [error, setError] = useState('')
  const [pendingName, setPendingName] = useState('')

  useEffect(() => {
    api.availPublicRegisterForm(token).then(setOpts).catch((e) => setError(e.message || 'Signing up isn’t available.'))
  }, [token])

  if (error) {
    return (
      <div className="text-center py-6">
        <Notice>{error}</Notice>
        <button type="button" onClick={onBack} className="text-sm text-pb-faint underline">Back to the name list</button>
      </div>
    )
  }
  if (!opts) return <div className="py-16 text-center text-pb-faint text-sm">Loading…</div>

  if (step === 'pending') return <PendingStep name={pendingName} onBack={onBack} />
  if (step === 'form') {
    return (
      <FormStep key={claim?.id || 'new'} token={token} initialClaim={claim} roles={opts.roles || []}
        interests={opts.interests || []} fmtName={fmtName}
        onBack={() => { setClaim(null); setStep('find') }}
        onDone={(r, asClaim) => {
          if (r?.status === 'signed_in') onSignedIn()
          else { setPendingName(asClaim ? fmtName(asClaim.display_name) : ''); setStep('pending') }
        }} />
    )
  }
  return (
    <FindStep token={token} initialQuery={initialQuery} fmtName={fmtName} onBack={onBack}
      onPick={(p) => { setClaim(p); setStep('form') }}
      onNew={() => { setClaim(null); setStep('form') }} />
  )
}
