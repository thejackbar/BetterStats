// BetterSelect → Setup → Settings.
//
// The small switches that change how BetterSelect looks and behaves, in one place
// instead of on the screens they affect. Today: the colours that mark a player
// who is free for one weekend of a two-day game and away for the other ("half
// available"), whether junior grades are shown, and whether Maybe is offered.
// Selection rules (age limits, side size, emails) stay on their own screen.
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import usePersistedState from '../../../lib/usePersistedState'
import { setAllowMaybe, setHalfColours, useHalfColours } from '../../../lib/useAvailabilityConfig'
import { PbSpinner } from '../../../lib/presskit'
import { Btn, Dot, Segmented } from './ui'

const DEFAULTS = { w1: '#a855f7', w2: '#06b6d4' }

function Card({ children }) {
  return <section className="pb-card rounded-xl p-4 sm:p-5">{children}</section>
}
function Head({ title, sub }) {
  return (
    <div className="mb-3">
      <h2 className="font-display font-bold text-[15px] tracking-tight">{title}</h2>
      {sub && <p className="text-[12.5px] text-pb-dim mt-0.5 max-w-[66ch]">{sub}</p>}
    </div>
  )
}
function Row({ label, hint, children }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 py-2.5 border-t border-pb-hairline first:border-t-0">
      <div className="min-w-0 flex-1 basis-[260px]">
        <div className="text-[13.5px] font-semibold">{label}</div>
        {hint && <div className="text-[12px] text-pb-faint mt-0.5 max-w-[60ch]">{hint}</div>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  )
}

// One half-available colour: a picker, the hex, a live sample, and Reset.
function HalfColour({ weekKey, title, hint, value, onChange, disabled }) {
  const [text, setText] = useState(value)
  useEffect(() => setText(value), [value])
  const valid = /^#[0-9a-f]{6}$/i.test(text.trim())
  return (
    <Row label={title} hint={hint}>
      <div className="flex items-center gap-2.5" data-half-colour={weekKey}>
        <span className="inline-flex items-center gap-1.5 text-[12.5px] text-pb-dim min-w-[118px]">
          <span className="inline-block rounded-full" style={{ width: 11, height: 11, background: valid ? text : value }} data-half-sample={weekKey} />
          {title.replace('Available for ', '')}
        </span>
        <input type="color" value={value} disabled={disabled} aria-label={`${title} colour`}
          onChange={(e) => onChange(e.target.value)}
          className="h-8 w-10 rounded border border-pb-hairline bg-transparent cursor-pointer disabled:opacity-40" />
        <input type="text" value={text} disabled={disabled} spellCheck={false} maxLength={7} aria-label={`${title} hex`}
          onChange={(e) => { setText(e.target.value); if (/^#[0-9a-f]{6}$/i.test(e.target.value.trim())) onChange(e.target.value.trim().toLowerCase()) }}
          className={`w-[92px] bg-pb-surface2 border rounded-lg px-2 py-1.5 font-mono text-[12.5px] focus:outline-none focus:border-pb-accent ${valid ? 'border-pb-hairline' : 'border-pb-red'}`} />
        <Btn sm variant="ghost" onClick={() => onChange(DEFAULTS[weekKey])} disabled={disabled || value === DEFAULTS[weekKey]}>Reset</Btn>
      </div>
    </Row>
  )
}

export default function AdminSelectSettings() {
  const { hasCapability } = useAuth()
  const toast = useToast()
  const canEdit = hasCapability(CAP.MANAGE_SELECTIONS)
  const [loaded, setLoaded] = useState(false)
  const [maybe, setMaybe] = useState(true)
  const [colours, setColours] = useState(DEFAULTS)
  const [showJuniors, setShowJuniors] = usePersistedState('select.juniors', false, (v) => typeof v === 'boolean')
  useHalfColours()

  useEffect(() => {
    let alive = true
    Promise.all([api.bsAvailabilityConfig(), api.bsRules()])
      .then(([cfg, rules]) => {
        if (!alive) return
        setMaybe(cfg?.allow_maybe !== false)
        setColours({ ...DEFAULTS, ...(rules?.settings?.half_colours || cfg?.half_colours || {}) })
        setLoaded(true)
      })
      .catch((e) => { toast.error(e.message || 'Could not load settings'); setLoaded(true) })
    return () => { alive = false }
  }, [toast])

  const saveColour = async (key, hex) => {
    const before = colours
    const next = { ...colours, [key]: hex }
    setColours(next); setHalfColours(next)            // every open card follows at once
    try {
      const s = await api.bsRuleSettings({ [`half_colour_${key}`]: hex === DEFAULTS[key] ? null : hex })
      if (s?.half_colours) { setColours(s.half_colours); setHalfColours(s.half_colours) }
    } catch (e) {
      setColours(before); setHalfColours(before)
      toast.error(e.message || 'Could not save the colour')
    }
  }
  const saveMaybe = async (on) => {
    setMaybe(on); setAllowMaybe(on)
    try { await api.bsSetSelfService({ allow_maybe: on }) }
    catch (e) { setMaybe(!on); setAllowMaybe(!on); toast.error(e.message || 'Could not save') }
  }

  if (!loaded) return <BetterSelectLayout title="Settings"><PbSpinner message="Loading settings…" /></BetterSelectLayout>

  return (
    <BetterSelectLayout title="Settings" caption="How BetterSelect looks and behaves">
      <div className="flex flex-col gap-4 max-w-[980px]" data-select-settings>
        <Card>
          <Head title="Two-day games"
            sub="A two-day game is answered one weekend at a time. A player who is free for one weekend and away for the other is half available. Their dot and card edge use these colours instead of the green of Available or the red of Unavailable, so you can see them at a glance." />
          <HalfColour weekKey="w1" title="Available for week 1 only" hint="Free the first weekend of a two-day game, away the second."
            value={colours.w1} onChange={(v) => saveColour('w1', v)} disabled={!canEdit} />
          <HalfColour weekKey="w2" title="Available for week 2 only" hint="Away the first weekend, free the second."
            value={colours.w2} onChange={(v) => saveColour('w2', v)} disabled={!canEdit} />
          <div className="flex items-center gap-4 pt-2.5 border-t border-pb-hairline text-[12px] text-pb-faint flex-wrap">
            <span>On a card:</span>
            <span className="inline-flex items-center gap-1.5"><Dot status="AVAILABLE" size={10} /> Available</span>
            <span className="inline-flex items-center gap-1.5"><Dot status="HALF_W1" size={10} /> Week 1 only</span>
            <span className="inline-flex items-center gap-1.5"><Dot status="HALF_W2" size={10} /> Week 2 only</span>
            <span className="inline-flex items-center gap-1.5"><Dot status="UNAVAILABLE" size={10} /> Unavailable</span>
          </div>
        </Card>

        <Card>
          <Head title="What the screens show" />
          <Row label="Junior grades" hint="Junior grades are set in Manage Grades. This is remembered on this device and applies to the Selection board, the Whiteboard, Availability and Fixtures.">
            <Segmented sm value={showJuniors ? 'show' : 'hide'} onChange={(v) => setShowJuniors(v === 'show')}
              options={[{ value: 'hide', label: 'Hide' }, { value: 'show', label: 'Show' }]} />
          </Row>
          <Row label="Maybe answer" hint="When off, selectors and players are offered only Available or Unavailable. Maybe answers already recorded stay.">
            <Segmented sm value={maybe ? 'on' : 'off'} onChange={(v) => canEdit && saveMaybe(v === 'on')}
              options={[{ value: 'on', label: 'On' }, { value: 'off', label: 'Off' }]} />
          </Row>
        </Card>

        <p className="text-[12.5px] text-pb-faint">
          Age limits, side size, fees and training notes, and the captain and player emails are on{' '}
          <Link to="/admin/betterselect/rules" className="text-pb-accent underline">Selection rules</Link>.
        </p>
      </div>
    </BetterSelectLayout>
  )
}
