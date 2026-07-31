import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { api } from '../lib/api'

const PASSWORD_MIN_LEN = 10

function Brand() {
  return (
    <div className="text-center mb-8">
      <div className="inline-flex items-center gap-2.5 mb-3">
        <span
          className="w-8 h-8 rounded font-mono font-bold text-sm flex items-center justify-center text-pb-bg"
          style={{ background: 'var(--pb-accent)' }}
        >
          BC
        </span>
        <span className="font-display font-bold text-xl tracking-wider uppercase text-pb-text">
          BetterCricket
        </span>
      </div>
      <p className="font-mono text-[11px] tracking-wide3 text-pb-faint">CLUB ADMIN LOGIN</p>
    </div>
  )
}

function ShowHideInput({ value, onChange, show, onToggleShow, autoComplete }) {
  return (
    <div className="relative">
      <input
        type={show ? 'text' : 'password'}
        autoComplete={autoComplete}
        value={value}
        onChange={onChange}
        required
        className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2.5 pr-14 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
      />
      <button
        type="button"
        onClick={onToggleShow}
        className="absolute right-3 top-1/2 -translate-y-1/2 font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors"
      >
        {show ? 'HIDE' : 'SHOW'}
      </button>
    </div>
  )
}

// A club-user invite (routers/club_admin.py's "Invite admin") lands here via
// betterat.cricket/login?invite=<token>, and an admin-triggered password
// reset (routers/club_admin.py's "Send password reset email" — an existing
// account, not a new one) lands here via ?reset=<token> — no separate pages,
// per the explicit ask for the invite flow; the reset flow mirrors it.
// Same password rule as self-serve trial registration
// (services/password_policy.py on the backend) for both.
function AcceptInvite({ token, mode = 'invite' }) {
  const { acceptInvite, resetPassword } = useAuth()
  const navigate = useNavigate()
  const [invite, setInvite] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [accepting, setAccepting] = useState(false)

  const isReset = mode === 'reset'
  const fallbackError = isReset
    ? 'This reset link is invalid or has expired.'
    : 'This invite link is invalid or has expired.'

  useEffect(() => {
    let cancelled = false
    const fetchIdentity = isReset ? api.getPasswordReset : api.getInvite
    fetchIdentity(token)
      .then((d) => { if (!cancelled) setInvite(d) })
      .catch((e) => { if (!cancelled) setLoadError(e?.message || fallbackError) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, isReset])

  const checks = {
    length: password.length >= PASSWORD_MIN_LEN,
    upper: /[A-Z]/.test(password),
    digit: /\d/.test(password),
    special: /[^A-Za-z0-9]/.test(password),
    match: !!password && password === confirmPassword,
  }
  const valid = Object.values(checks).every(Boolean)

  const submit = async (e) => {
    e.preventDefault()
    setSubmitError('')
    setAccepting(true)
    try {
      await (isReset ? resetPassword : acceptInvite)(token, password, confirmPassword)
      navigate('/admin')
    } catch (err) {
      setSubmitError(err.message || `Could not ${isReset ? 'reset' : 'set'} your password`)
    } finally {
      setAccepting(false)
    }
  }

  if (loading) {
    return (
      <div className="pb-card p-6">
        <p className="font-mono text-[11px] text-pb-faint">
          Loading your {isReset ? 'reset link' : 'invite'}…
        </p>
      </div>
    )
  }

  if (!invite) {
    return (
      <div className="pb-card p-6">
        <p className="font-mono text-[11px] text-pb-red">{loadError}</p>
      </div>
    )
  }

  return (
    <form onSubmit={submit} className="pb-card p-6 space-y-4">
      <p className="text-pb-text text-sm">
        {isReset ? (
          <>
            Hi{invite.display_name ? ` ${invite.display_name}` : ''} — choose a new password
            for your admin account{invite.club_name ? ` at ${invite.club_name}` : ''}.
          </>
        ) : (
          <>
            Welcome{invite.display_name ? `, ${invite.display_name}` : ''} — set a password to
            activate your admin account{invite.club_name ? ` for ${invite.club_name}` : ''}.
          </>
        )}
      </p>
      {invite.username && (
        <p className="font-mono text-[11px] text-pb-faint">
          Your username is <strong className="text-pb-text">{invite.username}</strong> — use it to log in from now on.
        </p>
      )}

      <div>
        <label className="block font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1.5">Password</label>
        <ShowHideInput value={password} onChange={(e) => setPassword(e.target.value)}
          show={showPassword} onToggleShow={() => setShowPassword((s) => !s)} autoComplete="new-password" />
      </div>
      <div>
        <label className="block font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1.5">Repeat password</label>
        <ShowHideInput value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)}
          show={showConfirmPassword} onToggleShow={() => setShowConfirmPassword((s) => !s)} autoComplete="new-password" />
      </div>

      <ul className="font-mono text-[10px] space-y-0.5">
        <li className={checks.length ? 'text-emerald-400' : 'text-pb-faintest'}>{checks.length ? '✓' : '·'} At least 10 characters</li>
        <li className={checks.upper ? 'text-emerald-400' : 'text-pb-faintest'}>{checks.upper ? '✓' : '·'} One uppercase letter</li>
        <li className={checks.digit ? 'text-emerald-400' : 'text-pb-faintest'}>{checks.digit ? '✓' : '·'} One number</li>
        <li className={checks.special ? 'text-emerald-400' : 'text-pb-faintest'}>{checks.special ? '✓' : '·'} One special character</li>
        <li className={checks.match ? 'text-emerald-400' : 'text-pb-faintest'}>{checks.match ? '✓' : '·'} Passwords match</li>
      </ul>

      {submitError && <p className="font-mono text-[11px] text-pb-red">{submitError}</p>}

      <button
        type="submit"
        disabled={!valid || accepting}
        className="w-full py-2.5 rounded font-mono text-[11px] tracking-wide3 font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed text-pb-bg"
        style={{ background: 'var(--pb-accent)' }}
      >
        {accepting
          ? (isReset ? 'RESETTING…' : 'ACTIVATING…')
          : (isReset ? 'RESET PASSWORD & SIGN IN' : 'SET PASSWORD & SIGN IN')}
      </button>
    </form>
  )
}

// Self-serve "forgot password" request — the counterpart to AcceptInvite's
// mode="reset" step above (which handles the link once it's clicked; this
// is what sends it). Always shows the same generic confirmation regardless
// of whether the email matched an account, matching the backend's own
// enumeration-safe response.
function ForgotPassword({ onBack }) {
  const [email, setEmail] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [sent, setSent] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setSending(true)
    try {
      await api.forgotPassword(email.trim())
      setSent(true)
    } catch (err) {
      setError(err.message || 'Could not send a reset link — try again shortly.')
    } finally {
      setSending(false)
    }
  }

  if (sent) {
    return (
      <div className="pb-card p-6 space-y-4">
        <p className="text-pb-text text-sm">
          If that email is registered, a reset link is on its way. It's valid for 24 hours.
        </p>
        <p className="font-mono text-[10px] text-pb-faintest">
          Nothing arriving? Check your spam folder, or contact{' '}
          <a href="mailto:support@bettersports.com.au" className="text-pb-faint hover:text-pb-text transition-colors">
            support@bettersports.com.au
          </a>.
        </p>
        <button type="button" onClick={onBack}
          className="font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors">
          &larr; BACK TO SIGN IN
        </button>
      </div>
    )
  }

  return (
    <form onSubmit={submit} className="pb-card p-6 space-y-4">
      <p className="text-pb-text text-sm">
        Enter the email address on your admin account and we'll send you a link to reset your password.
      </p>
      <div>
        <label className="block font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1.5">
          Email
        </label>
        <input
          type="email"
          autoComplete="email"
          value={email}
          onChange={e => setEmail(e.target.value)}
          required
          className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent"
        />
      </div>
      {error && <p className="font-mono text-[11px] text-pb-red">{error}</p>}
      <button
        type="submit"
        disabled={sending}
        className="w-full py-2.5 rounded font-mono text-[11px] tracking-wide3 font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed text-pb-bg"
        style={{ background: 'var(--pb-accent)' }}
      >
        {sending ? 'SENDING…' : 'SEND RESET LINK'}
      </button>
      <button type="button" onClick={onBack}
        className="w-full font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text transition-colors">
        &larr; BACK TO SIGN IN
      </button>
    </form>
  )
}

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const inviteToken = searchParams.get('invite')
  const resetToken = searchParams.get('reset')

  // Where the user was headed before ProtectedRoute bounced them here (set as
  // navigation state). Fall back to the dashboard for a direct visit to /login.
  const from = location.state?.from
  const redirectTo = from
    ? `${from.pathname || '/admin'}${from.search || ''}${from.hash || ''}`
    : '/admin'

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showForgot, setShowForgot] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(username.trim(), password)
      navigate(redirectTo, { replace: true })
    } catch (err) {
      setError(err.message || 'Invalid username or password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-pb-bg flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <Brand />

        {inviteToken || resetToken ? (
          <AcceptInvite token={inviteToken || resetToken} mode={resetToken ? 'reset' : 'invite'} />
        ) : showForgot ? (
          <ForgotPassword onBack={() => setShowForgot(false)} />
        ) : (
          <>
            <form onSubmit={handleSubmit} className="pb-card p-6 space-y-4">
              <div>
                <label className="block font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1.5">
                  Username
                </label>
                <input
                  type="text"
                  autoComplete="username"
                  value={username}
                  onChange={e => setUsername(e.target.value)}
                  required
                  className="w-full bg-pb-surface2 border pb-hairline rounded px-3 py-2.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent placeholder-pb-faintest"
                />
              </div>

              <div>
                <label className="block font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1.5">
                  Password
                </label>
                <ShowHideInput value={password} onChange={e => setPassword(e.target.value)}
                  show={showPassword} onToggleShow={() => setShowPassword(s => !s)} autoComplete="current-password" />
              </div>

              {error && (
                <p className="font-mono text-[11px] text-pb-red">{error}</p>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 rounded font-mono text-[11px] tracking-wide3 font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed text-pb-bg"
                style={{ background: 'var(--pb-accent)' }}
              >
                {loading ? 'SIGNING IN…' : 'SIGN IN'}
              </button>
            </form>

            <p className="text-center font-mono text-[10px] tracking-wide2 text-pb-faintest mt-6">
              <button type="button" onClick={() => setShowForgot(true)}
                className="text-pb-faint hover:text-pb-text transition-colors">
                Forgot your password?
              </button>
            </p>
          </>
        )}
      </div>
    </div>
  )
}
