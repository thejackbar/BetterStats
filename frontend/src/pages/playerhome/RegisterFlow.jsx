// "Can't find your name?" on the player's own page (/playerdash/:token).
//
// Two ways in. Most past players are already on the club's books with their stats, only
// hidden from the name list because they have not played lately, so the first step is a
// search of past players: pick yourself and claim that record (proven with the last four
// digits of the mobile on file). Only someone who is not there at all fills in the form as
// new. The server decides who is signed in straight away and what waits for the club
// (routers/public_player_register.py).
//
// Every component here is declared at module level (never inside a render function).
import { useEffect, useRef, useState } from 'react'
import { api } from '../../lib/api'

const inputCls = 'w-full bg-pb-surface2 border pb-hairline rounded-xl px-4 py-3 text-base focus:outline-none focus:border-pb-accent'
const PLAYING_ROLES = ['current_player', 'ex_player']

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

function Chip({ on, onClick, children, attr }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={on} {...attr}
      className={`px-3 py-2 rounded-full border text-sm transition-colors ${on ? 'font-semibold text-pb-bg' : 'pb-hairline text-pb-dim hover:bg-pb-surface2'}`}
      style={on ? { background: 'var(--pb-accent)', borderColor: 'var(--pb-accent)' } : undefined}>
      {children}
    </button>
  )
}

function ErrorBox({ children }) {
  if (!children) return null
  return (
    <div role="alert" className="rounded-xl px-4 py-3 mb-4 text-sm"
      style={{ background: 'color-mix(in srgb, var(--pb-red) 12%, transparent)', color: 'var(--pb-red)' }}>
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
      <h1 className="font-display font-bold text-xl text-center mb-1">Can’t find your name?</h1>
      <p className="text-center text-pb-faint text-sm mb-4">
        Played here before? Your old record may be tucked away because you haven’t played lately. Search for it first so your stats come with you.
      </p>
      <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search past players…"
        className={`${inputCls} mb-3`} data-register-search />
      <ErrorBox>{error}</ErrorBox>
      {results === null && <p className="text-center text-pb-faintest text-xs mb-3">Type at least three letters of your name.</p>}
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
              <span className="text-pb-faintest shrink-0">That’s me →</span>
            </button>
          ))}
        </div>
      )}
      <button type="button" onClick={onNew} data-register-new
        className="w-full py-3.5 rounded-xl font-semibold text-pb-bg mt-2" style={{ background: 'var(--pb-accent)' }}>
        I’m not on any list. Add me
      </button>
      <p className="text-center text-pb-faint text-[12px] mt-2">
        For anyone connected to the club: current and past players, parents, volunteers and supporters.
      </p>
      <button type="button" onClick={onBack} className="block mx-auto mt-5 text-sm text-pb-faint underline">
        Back to the name list
      </button>
    </div>
  )
}

function FormStep({ token, claim, requirePin, roles, interests, fmtName, onDone, onBack }) {
  const start = claim ? splitName(claim.display_name) : { first: '', last: '' }
  const [f, setF] = useState({
    first_name: start.first, last_name: start.last, role: claim ? 'ex_player' : '',
    phone: '', email: '', date_of_birth: '', years_played: '', grades_played: '', notes: '',
    interests: [], contact_consent: false, pin: '',
  })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }))
  const needPin = !!claim && requirePin && claim.has_phone
  const playing = !!claim || PLAYING_ROLES.includes(f.role)

  const toggleInterest = (k) => set('interests', f.interests.includes(k) ? f.interests.filter((x) => x !== k) : [...f.interests, k])

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    if (!f.role) { setError('Pick what best describes you.'); return }
    if (needPin && f.pin.length < 4) { setError(`Enter the last 4 digits of the mobile on file for ${fmtName(claim.display_name)}.`); return }
    setBusy(true)
    try {
      const body = { ...f, date_of_birth: f.date_of_birth || null }
      if (claim) body.claim_player_id = claim.id
      if (!needPin) delete body.pin
      const r = await api.availPublicRegister(token, body)
      onDone(r)
    } catch (err) {
      setError(err.message || 'That didn’t go through. Please try again.')
    } finally { setBusy(false) }
  }

  return (
    <form onSubmit={submit} data-register-form={claim ? 'claim' : 'new'}>
      <h1 className="font-display font-bold text-xl text-center mb-1">
        {claim ? `Is this you, ${fmtName(claim.display_name)}?` : 'Add yourself'}
      </h1>
      <p className="text-center text-pb-faint text-sm mb-5">
        {claim
          ? (claim.has_phone
            ? 'Tell the club a little about yourself and you’ll go straight to your page.'
            : 'There’s no mobile on file for this record, so the club will confirm it’s you before you can log in.')
          : 'Fill this in and you’ll go straight to your page. The club sees what you tell them here.'}
      </p>
      <ErrorBox>{error}</ErrorBox>

      <div className="grid grid-cols-2 gap-3">
        <Field label="First name" htmlFor="reg-first">
          <input id="reg-first" value={f.first_name} onChange={(e) => set('first_name', e.target.value)} className={inputCls} autoComplete="given-name" required />
        </Field>
        <Field label="Surname" htmlFor="reg-last">
          <input id="reg-last" value={f.last_name} onChange={(e) => set('last_name', e.target.value)} className={inputCls} autoComplete="family-name" required />
        </Field>
      </div>

      <div className="mb-4" role="group" aria-labelledby="reg-role-label">
        <div id="reg-role-label" className="text-sm font-semibold mb-1.5">Which best describes you?</div>
        <div className="flex flex-wrap gap-2" data-register-roles>
          {roles.map((r) => (
            <Chip key={r.key} on={f.role === r.key} onClick={() => set('role', r.key)} attr={{ 'data-role': r.key }}>{r.label}</Chip>
          ))}
        </div>
      </div>

      {needPin && (
        <Field label={`Last 4 digits of the mobile on file for ${fmtName(claim.display_name)}`} htmlFor="reg-pin"
          hint="This proves the record is yours. If you’ve changed numbers since, ask your club.">
          <input id="reg-pin" value={f.pin} onChange={(e) => set('pin', e.target.value.replace(/\D/g, '').slice(0, 4))}
            inputMode="numeric" autoComplete="one-time-code" placeholder="••••"
            className={`${inputCls} text-center tracking-[0.6em] font-mono`} data-register-pin />
        </Field>
      )}

      <Field label="Mobile" htmlFor="reg-phone"
        hint={claim ? 'Your current number, so the club can reach you.' : 'Its last four digits are how you log in next time.'}>
        <input id="reg-phone" type="tel" value={f.phone} onChange={(e) => set('phone', e.target.value)} className={inputCls} autoComplete="tel" required />
      </Field>
      <Field label="Email" htmlFor="reg-email" hint="Optional.">
        <input id="reg-email" type="email" value={f.email} onChange={(e) => set('email', e.target.value)} className={inputCls} autoComplete="email" />
      </Field>
      <Field label="Date of birth" htmlFor="reg-dob" hint="Optional.">
        <input id="reg-dob" type="date" value={f.date_of_birth} onChange={(e) => set('date_of_birth', e.target.value)} className={inputCls} autoComplete="bday" />
      </Field>

      {playing && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-3">
          <Field label="Years you played here" htmlFor="reg-years" hint="For example 2008 to 2015.">
            <input id="reg-years" value={f.years_played} onChange={(e) => set('years_played', e.target.value)} className={inputCls} />
          </Field>
          <Field label="Grades or teams" htmlFor="reg-grades" hint="For example 2nd XI, Under 16s.">
            <input id="reg-grades" value={f.grades_played} onChange={(e) => set('grades_played', e.target.value)} className={inputCls} />
          </Field>
        </div>
      )}

      <div className="mb-4" role="group" aria-labelledby="reg-int-label">
        <div id="reg-int-label" className="text-sm font-semibold mb-1.5">Interested in…</div>
        <div className="flex flex-wrap gap-2" data-register-interests>
          {interests.map((i) => (
            <Chip key={i.key} on={f.interests.includes(i.key)} onClick={() => toggleInterest(i.key)} attr={{ 'data-interest': i.key }}>{i.label}</Chip>
          ))}
        </div>
      </div>

      <Field label="Anything else the club should know?" htmlFor="reg-notes" hint="Optional.">
        <textarea id="reg-notes" rows={3} value={f.notes} onChange={(e) => set('notes', e.target.value)} className={inputCls} />
      </Field>

      <div className="flex items-start gap-3 mb-5">
        <input id="reg-consent" type="checkbox" checked={f.contact_consent} onChange={(e) => set('contact_consent', e.target.checked)}
          className="mt-1 h-4 w-4 shrink-0" data-register-consent />
        <label htmlFor="reg-consent" className="text-sm text-pb-dim">
          The club can contact me about playing, volunteering and club news.
        </label>
      </div>

      <button type="submit" disabled={busy} data-register-submit
        className="w-full py-3.5 rounded-xl font-semibold text-pb-bg transition disabled:opacity-50" style={{ background: 'var(--pb-accent)' }}>
        {busy ? 'Saving…' : (claim && !claim.has_phone ? 'Send to the club' : 'Add me and open my page')}
      </button>
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
        tap “Can’t find your name?”, find yourself and log in with the last four digits of your mobile.
      </p>
      <button type="button" onClick={onBack} className="mt-6 text-sm text-pb-faint underline">Back to the name list</button>
    </div>
  )
}

export default function RegisterFlow({ token, requirePin, initialQuery, fmtName, onSignedIn, onBack }) {
  const [step, setStep] = useState('find') // find | form | pending
  const [claim, setClaim] = useState(null)
  const [opts, setOpts] = useState(null)
  const [error, setError] = useState('')
  const [pendingName, setPendingName] = useState('')

  useEffect(() => {
    api.availPublicRegisterForm(token).then(setOpts).catch((e) => setError(e.message || 'Registration isn’t available.'))
  }, [token])

  if (error) {
    return (
      <div className="text-center py-6">
        <ErrorBox>{error}</ErrorBox>
        <button type="button" onClick={onBack} className="text-sm text-pb-faint underline">Back to the name list</button>
      </div>
    )
  }
  if (!opts) return <div className="py-16 text-center text-pb-faint text-sm">Loading…</div>

  if (step === 'pending') return <PendingStep name={pendingName} onBack={onBack} />
  if (step === 'form') {
    return (
      <FormStep token={token} claim={claim} requirePin={opts.require_pin ?? requirePin} roles={opts.roles || []}
        interests={opts.interests || []} fmtName={fmtName}
        onBack={() => { setClaim(null); setStep('find') }}
        onDone={(r) => {
          if (r?.status === 'signed_in') onSignedIn()
          else { setPendingName(claim ? fmtName(claim.display_name) : ''); setStep('pending') }
        }} />
    )
  }
  return (
    <FindStep token={token} initialQuery={initialQuery} fmtName={fmtName} onBack={onBack}
      onPick={(p) => { setClaim(p); setStep('form') }}
      onNew={() => { setClaim(null); setStep('form') }} />
  )
}
