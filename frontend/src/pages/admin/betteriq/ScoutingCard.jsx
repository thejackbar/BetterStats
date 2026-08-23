/* BetterIQ — manual scouting card (batting & bowling intel).
 *
 * The ball-level read CA can't give us, entered by the scout and shared by the
 * Opposition Player profile and our own Player trends. Two cards — Batting and
 * Bowling — each a display (a synthesised "DNA" read + the marked zones/chips) and
 * an inline editor (vulnerable-to bowler types / favoured shots / a length×line
 * weakness grid / stock ball + variations / strengths-weaknesses-plan).
 *
 *   <ScoutingCard keyId={playerId}
 *      batting={battingIntel} bowling={bowlingIntel}
 *      stats={{ dismissals, wicketMethods }}   // held data, blended into the DNA
 *      onSave={(body) => Promise}              // body = { batting_intel } | { bowling_intel }
 *      defaultSide="bowl" />                   // which card reads first (role-aware)
 */
import { useState, useEffect } from 'react'
import { Card, Note, Btn } from './ui'
import { ZoneGrid } from './viz'
import {
  BOWLING_KINDS, BAT_SHOTS, BOWL_VARIATIONS, BOWL_DANGER,
  buildBattingDna, buildBowlingDna, hasIntel,
} from './scoutDna'

const entries = (map) => Object.entries(map)

/* ── Selectable chips (multi or single) ──────────────────────────────────── */
function Chips({ options, value, onChange, single = false }) {
  const sel = new Set(Array.isArray(value) ? value : value ? [value] : [])
  const toggle = (code) => {
    if (single) { onChange(sel.has(code) ? null : code); return }
    const next = new Set(sel)
    next.has(code) ? next.delete(code) : next.add(code)
    onChange([...next])
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map(([code, label]) => {
        const on = sel.has(code)
        return (
          <button key={code} type="button" onClick={() => toggle(code)}
            className="text-[12px] px-2.5 py-1 transition" style={{
              borderRadius: 99,
              background: on ? 'color-mix(in srgb, var(--pb-accent) 16%, transparent)' : 'var(--pb-surface2)',
              color: on ? 'var(--pb-accent)' : 'var(--pb-dim)',
              border: `1px solid ${on ? 'color-mix(in srgb, var(--pb-accent) 42%, transparent)' : 'var(--pb-hairline2)'}`,
            }}>{label}</button>
        )
      })}
    </div>
  )
}

function Field({ label, children }) {
  return (
    <div>
      <div className="iq-eyebrow mb-2">{label}</div>
      {children}
    </div>
  )
}

function TextArea({ value, onChange, placeholder, rows = 2 }) {
  return (
    <textarea value={value} onChange={e => onChange(e.target.value)} rows={rows} placeholder={placeholder}
      className="w-full p-3 text-[13.5px] leading-relaxed resize-y outline-none"
      style={{ background: 'var(--pb-surface2)', border: '1px solid var(--pb-hairline)', borderRadius: 12, color: 'var(--pb-text)', fontFamily: 'var(--iq-font-body)' }} />
  )
}

/* ── DNA read (display) ──────────────────────────────────────────────────── */
function DnaRead({ dna, emptyHint }) {
  if (!dna.bullets.length && !dna.plan && !dna.strengths) {
    return <div className="text-pb-faint text-[13px]">{emptyHint}</div>
  }
  return (
    <div className="space-y-3">
      {dna.plan && (
        <div className="px-3.5 py-3" style={{ background: 'color-mix(in srgb, var(--pb-accent) 10%, transparent)', borderRadius: 12, border: '1px solid color-mix(in srgb, var(--pb-accent) 28%, transparent)' }}>
          <div className="iq-eyebrow mb-1" style={{ color: 'var(--pb-accent)' }}>The plan</div>
          <div className="text-[14px] leading-snug" style={{ color: 'var(--pb-accent)' }}>{dna.plan}</div>
        </div>
      )}
      {dna.bullets.length > 0 && (
        <ul className="space-y-2">
          {dna.bullets.map((b, i) => (
            <li key={i} className="flex gap-2.5 text-[13.5px] leading-snug">
              <span className="shrink-0 mt-1.5" style={{ width: 6, height: 6, borderRadius: 99, background: b.tone === 'data' ? 'var(--pb-accent)' : 'var(--pb-red)' }} />
              <span className="text-pb-dim">{b.text}</span>
            </li>
          ))}
        </ul>
      )}
      {dna.strengths && (
        <div className="text-[12.5px] text-pb-faint leading-snug">
          <span className="iq-mono uppercase mr-1.5" style={{ fontSize: 9, letterSpacing: '0.08em' }}>Watch for</span>{dna.strengths}
        </div>
      )}
    </div>
  )
}

/* ── One side (batting or bowling) ───────────────────────────────────────── */
function IntelSide({ side, keyId, intel, stats, onSave }) {
  const isBat = side === 'bat'
  const blank = isBat
    ? { vuln_bowling: [], fav_bowling: [], zones: [], fav_shots: [], risky_shots: [], strengths: '', weaknesses: '', plan: '' }
    : { stock: null, variations: [], zones: [], danger: [], strengths: '', weaknesses: '', plan: '' }
  // A pre-split blob only ever carried one combined "shots" list — seed it into
  // risky_shots (the card's original framing was "how to get him out") when the
  // new split fields are still empty, so opening the editor on already-saved
  // intel doesn't silently blank out what was there before.
  const seed = () => {
    const base = { ...blank, ...(intel || {}) }
    if (isBat && !base.risky_shots?.length && !base.fav_shots?.length && intel?.shots?.length) {
      base.risky_shots = intel.shots
    }
    return base
  }
  const [open, setOpen] = useState(false)
  const [f, setF] = useState(seed)
  const [saving, setSaving] = useState(false)
  useEffect(() => { setF(seed()); setOpen(false) }, [keyId, intel])  // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k, v) => setF(s => ({ ...s, [k]: v }))

  const dna = isBat ? buildBattingDna(intel, stats?.dismissals) : buildBowlingDna(intel, stats?.wicketMethods)
  const present = hasIntel(intel)
  const title = isBat ? 'Batting scouting' : 'Bowling scouting'
  const eyebrow = isBat ? 'how to get him out · scout-entered' : 'how to play him · scout-entered'

  const save = async () => {
    setSaving(true)
    try {
      const blob = isBat
        ? { vuln_bowling: f.vuln_bowling, fav_bowling: f.fav_bowling, zones: f.zones, fav_shots: f.fav_shots, risky_shots: f.risky_shots, strengths: f.strengths, weaknesses: f.weaknesses, plan: f.plan }
        : { stock: f.stock, variations: f.variations, zones: f.zones, danger: f.danger, strengths: f.strengths, weaknesses: f.weaknesses, plan: f.plan }
      await onSave(isBat ? { batting_intel: blob } : { bowling_intel: blob })
      setOpen(false)
    } finally { setSaving(false) }
  }

  return (
    <Card eyebrow={eyebrow} title={title}
      right={<Btn variant={open ? 'ghost' : 'soft'} sm icon={open ? undefined : 'edit'} onClick={() => setOpen(o => !o)}>{open ? 'Close' : (present ? 'Edit' : 'Add intel')}</Btn>}>
      {!open && (
        <div className="space-y-4">
          <DnaRead dna={dna} emptyHint={`No ${isBat ? 'batting' : 'bowling'} intel yet. Tap Add intel to record ${isBat ? 'how this batter gets out' : 'how this bowler operates'} (CA gives us no ball-level data, so this is your own scouting).`} />
          {Array.isArray(intel?.zones) && intel.zones.some(v => v > 0) && (
            <div className="flex justify-center pt-1"><ZoneGrid cells={intel.zones} size="sm" color={isBat ? 'var(--pb-red)' : 'var(--pb-accent)'} /></div>
          )}
        </div>
      )}

      {open && (
        <div className="space-y-4">
          {isBat ? (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Vulnerable to (bowler type)"><Chips options={entries(BOWLING_KINDS)} value={f.vuln_bowling} onChange={v => set('vuln_bowling', v)} /></Field>
                <Field label="Favoured (bowler type)"><Chips options={entries(BOWLING_KINDS)} value={f.fav_bowling} onChange={v => set('fav_bowling', v)} /></Field>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Risky shots"><Chips options={entries(BAT_SHOTS)} value={f.risky_shots} onChange={v => set('risky_shots', v)} /></Field>
                <Field label="Favoured shots"><Chips options={entries(BAT_SHOTS)} value={f.fav_shots} onChange={v => set('fav_shots', v)} /></Field>
              </div>
              <Field label="Where he's vulnerable (length × line)">
                <div className="flex justify-center py-1"><ZoneGrid cells={f.zones} onChange={v => set('zones', v)} color="var(--pb-red)" /></div>
              </Field>
            </>
          ) : (
            <>
              <Field label="Stock delivery"><Chips options={entries(BOWLING_KINDS)} value={f.stock} onChange={v => set('stock', v)} single /></Field>
              <Field label="Variations"><Chips options={entries(BOWL_VARIATIONS)} value={f.variations} onChange={v => set('variations', v)} /></Field>
              <Field label="Most dangerous"><Chips options={entries(BOWL_DANGER)} value={f.danger} onChange={v => set('danger', v)} /></Field>
              <Field label="Where he attacks (length × line)">
                <div className="flex justify-center py-1"><ZoneGrid cells={f.zones} onChange={v => set('zones', v)} color="var(--pb-accent)" /></div>
              </Field>
            </>
          )}
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={isBat ? 'Weaknesses' : 'Weaknesses (how to attack him)'}><TextArea value={f.weaknesses} onChange={v => set('weaknesses', v)} placeholder={isBat ? 'e.g. impatient early, chases width…' : 'e.g. leaks runs when driven, short of a length…'} /></Field>
            <Field label={isBat ? 'Strengths (watch for)' : 'Strengths'}><TextArea value={f.strengths} onChange={v => set('strengths', v)} placeholder={isBat ? 'e.g. strong square of the wicket…' : 'e.g. nagging line, great yorker…'} /></Field>
          </div>
          <Field label={isBat ? 'Plan, how to get him out' : 'Plan, how to play him'}><TextArea value={f.plan} onChange={v => set('plan', v)} placeholder={isBat ? 'e.g. bowl full and straight, save the short ball' : 'e.g. take him down early before he settles'} rows={1} /></Field>
          <div className="flex items-center gap-3">
            <Btn variant="primary" sm icon="check" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save'}</Btn>
            <Btn variant="ghost" sm onClick={() => { setF(seed()); setOpen(false) }}>Cancel</Btn>
          </div>
        </div>
      )}
      <Note>Scout-entered. CA has no ball-by-ball line/length or shot data, so this is your own intel. It travels with the player.</Note>
    </Card>
  )
}

export default function ScoutingCard({ keyId, batting, bowling, stats, onSave, defaultSide = 'bat', only = null }) {
  // `only` renders a single side full-width (the tabbed Opposition-player profile
  // shows the batting card under its Batting tab and the bowling card under
  // Bowling); without it both cards sit side-by-side (the original layout).
  const sides = only ? [only] : defaultSide === 'bowl' ? ['bowl', 'bat'] : ['bat', 'bowl']
  return (
    <div className={only ? '' : 'grid gap-5 lg:grid-cols-2 items-start'}>
      {sides.map(side => (
        <IntelSide key={side} side={side} keyId={keyId}
          intel={side === 'bat' ? batting : bowling} stats={stats} onSave={onSave} />
      ))}
    </div>
  )
}
