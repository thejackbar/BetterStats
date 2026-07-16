/* Shared primitives for the Setup Wizard steps — one place for the button /
   field / notice styles so every step reads the same. Themed off the pb-*
   tokens like the rest of the admin shell. */

export function WizardButton({ children, onClick, disabled, variant = 'primary', className = '', type = 'button' }) {
  const base = 'inline-flex items-center gap-2 font-mono text-[11px] tracking-wide2 rounded px-4 py-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed'
  const styles = {
    primary: 'text-white',
    secondary: 'border pb-hairline text-pb-faint hover:text-pb-text hover:bg-pb-surface2',
    danger: 'border border-pb-red/40 text-pb-red hover:bg-pb-red/10',
  }
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`${base} ${styles[variant] || styles.primary} ${className}`}
      style={variant === 'primary' ? { background: 'var(--pb-accent)' } : undefined}
    >
      {children}
    </button>
  )
}

export function Spinner() {
  return (
    <span
      className="inline-block w-3.5 h-3.5 border-2 border-t-transparent rounded-full animate-spin align-middle"
      style={{ borderColor: 'currentColor', borderTopColor: 'transparent' }}
    />
  )
}

export function FieldLabel({ children }) {
  return <label className="block font-mono text-[10px] tracking-wide2 text-pb-faint uppercase mb-1">{children}</label>
}

export function TextInput(props) {
  return (
    <input
      {...props}
      className={`w-full bg-pb-bg border pb-hairline rounded px-3 py-2 text-sm text-pb-text placeholder:text-pb-faintest focus:outline-none focus:border-pb-accent ${props.className || ''}`}
    />
  )
}

export function Notice({ tone = 'info', children }) {
  const tones = {
    info: 'border-pb-accent/30 text-pb-faint',
    good: 'border-pb-positive/40 text-pb-positive',
    warn: 'border-pb-amber/40 text-pb-amber',
    bad: 'border-pb-red/40 text-pb-red',
  }
  return (
    <div className={`border rounded px-3 py-2 font-mono text-[11px] leading-relaxed ${tones[tone] || tones.info}`}>
      {children}
    </div>
  )
}

/* A green "this step is already done" strip shown at the top of inline steps. */
export function DoneStrip({ children }) {
  return (
    <div className="flex items-center gap-2 border border-pb-positive/40 rounded px-3 py-2 font-mono text-[11px] text-pb-positive">
      <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
      </svg>
      {children}
    </div>
  )
}
