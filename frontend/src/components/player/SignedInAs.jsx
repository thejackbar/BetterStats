// Who is signed in on a public player page, and a way out when something looks wrong.
//
// A player's sign-in is a cookie on their phone, so a shared phone, a previous
// visit or a wrong name picked weeks ago can leave a page signed in as somebody
// else. Nothing on the page said so, and the first sign was an error that read as
// "you did not play". Every public page that keeps a player signed in shows this
// strip, and every error on it carries SignInHint.

/** "Signed in as Kate Leary · Not you? Sign out", a strip across the top of the page. */
export function SignedInAs({ name, onSwitch, className = '' }) {
  if (!name) return null
  return (
    <div data-signed-in-as
      className={`flex items-center justify-between gap-3 rounded-lg border pb-hairline bg-pb-surface2 px-3 py-2 mb-4 text-xs ${className}`}>
      <span className="min-w-0 truncate text-pb-faint">
        Signed in as <strong data-signed-in-name className="text-pb-text font-semibold">{name}</strong>
      </span>
      <button type="button" onClick={onSwitch} data-sign-out
        className="shrink-0 underline text-pb-faint hover:text-pb-text">Not you? Sign out</button>
    </div>
  )
}

/** Shown under an error to someone who is signed in: the cure for a wrong or stale sign-in. */
export function SignInHint({ name, onSwitch }) {
  if (!name) return null
  return (
    <span data-sign-in-hint className="block mt-2 text-[13px] opacity-90">
      You are signed in as {name}. If that is not you, or something looks wrong,{' '}
      <button type="button" onClick={onSwitch} className="underline font-semibold">sign out and sign in again</button>.
    </span>
  )
}
