import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { aflApi } from '../../../aflApi'
import { useToast } from '../../../../contexts/ToastContext'
import LoadingSpinner from '../../../../components/LoadingSpinner'
import { AvailPill, Btn, Card, INPUT, PageHead, PositionChips, shortDate } from './ui'

// Picking a football side: a ground of named positions in lines, an
// interchange bench and the emergencies, not a batting order.
//
// Tap a player, then tap where they go. It works the same with a finger on a
// phone at training as with a mouse, and a player can be dragged too. Tap a
// player already on the ground to move them, make them captain or take them
// off. The club's rules are read beside every name before anything is saved;
// a rule the club enforces refuses the save and says why.

const BENCH = 'INT'
const EMG = 'EMG'

// Which of a player's positions suit a field slot. Mirrors the backend's
// SLOT_FITS; only used to light up a good spot for the player in hand.
const FITS = {
  LBP: ['FB'], FB: ['FB'], RBP: ['FB'], LHB: ['HB'], CHB: ['HB'], RHB: ['HB'],
  LW: ['W', 'MID'], C: ['C', 'MID'], RW: ['W', 'MID'], LHF: ['HF'], CHF: ['HF'], RHF: ['HF'],
  LFP: ['FF'], FF: ['FF'], RFP: ['FF'], RUCK: ['RUCK'], RR: ['MID', 'RUCK'], ROV: ['MID', 'C'],
}
const fits = (slot, positions = []) => positions.includes('UTIL') || (FITS[slot] || []).some(p => positions.includes(p))

function flagTone(flags) {
  if (flags?.some(f => f.severity === 'block')) return 'block'
  if (flags?.some(f => f.severity === 'warn')) return 'warn'
  return null
}
const TONE = { block: 'var(--pb-red, #e5484d)', warn: 'var(--pb-amber, #d29922)' }

export default function AflSelectSelection() {
  const toast = useToast()
  const [params, setParams] = useSearchParams()
  const fixtureId = params.get('fixture')
  const [fixtures, setFixtures] = useState(null)
  const [data, setData] = useState(null)
  const [side, setSide] = useState([])         // [{player_id, slot, sort_order, is_captain, is_vice_captain}]
  const [armed, setArmed] = useState(null)     // player id in hand
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [filter, setFilter] = useState({ q: '', avail: 'available', squad: 'mine', pos: '' })
  const [errors, setErrors] = useState([])

  useEffect(() => {
    aflApi.selFixtures({ when: 'upcoming' }).then(d => {
      setFixtures(d.fixtures)
      if (!fixtureId && d.fixtures[0]) setParams({ fixture: d.fixtures[0].id }, { replace: true })
    }).catch(e => toast.error(e.message))
  }, [])

  async function load(id = fixtureId) {
    if (!id) return
    const d = await aflApi.selSelection(id)
    setData(d)
    setSide(d.lineup)
    setDirty(false)
    setArmed(null)
    setErrors([])
  }
  useEffect(() => { load().catch(e => toast.error(e.message)) }, [fixtureId])

  const players = useMemo(() => Object.fromEntries((data?.players || []).map(p => [p.id, p])), [data])
  const bySlot = useMemo(() => Object.fromEntries(side.filter(x => x.slot !== BENCH && x.slot !== EMG).map(x => [x.slot, x])), [side])
  const placedAt = useMemo(() => Object.fromEntries(side.map(x => [x.player_id, x.slot])), [side])
  const bench = side.filter(x => x.slot === BENCH).sort((a, b) => a.sort_order - b.sort_order)
  const emg = side.filter(x => x.slot === EMG).sort((a, b) => a.sort_order - b.sort_order)
  const size = data?.team_size || { field: 18, bench: 10, emergencies: 3 }
  const onField = side.filter(x => x.slot !== BENCH && x.slot !== EMG).length

  function change(next) { setSide(next); setDirty(true); setErrors([]) }

  function place(pid, slot) {
    if (!pid) return
    const existing = side.find(x => x.player_id === pid)
    let next = side.filter(x => x.player_id !== pid)
    if (slot === BENCH || slot === EMG) {
      const list = next.filter(x => x.slot === slot)
      const max = slot === BENCH ? size.bench : size.emergencies
      if (list.length >= max) { toast.error(slot === BENCH ? `The bench is full (${max})` : `${max} emergencies at most`); return }
      next.push({ player_id: pid, slot, sort_order: list.length + 1, is_captain: slot === BENCH && !!existing?.is_captain, is_vice_captain: slot === BENCH && !!existing?.is_vice_captain })
    } else {
      const there = next.find(x => x.slot === slot)
      if (there) {
        // Somebody's already there: they swap into the spot the player in
        // hand came from, or go back to the pool if that player came from it.
        next = next.filter(x => x.slot !== slot)
        if (existing) next.push({ ...there, slot: existing.slot })
      }
      next.push({ player_id: pid, slot, sort_order: 0, is_captain: !!existing?.is_captain, is_vice_captain: !!existing?.is_vice_captain })
    }
    change(renumber(next))
    setArmed(null)
  }

  function renumber(list) {
    let b = 0, e = 0
    return list.map(x => x.slot === BENCH ? { ...x, sort_order: ++b } : x.slot === EMG ? { ...x, sort_order: ++e, is_captain: false, is_vice_captain: false } : x)
  }

  function remove(pid) { change(renumber(side.filter(x => x.player_id !== pid))); setArmed(null) }

  function setRole(pid, role) {
    change(side.map(x => {
      if (role === 'c') return { ...x, is_captain: x.player_id === pid ? !x.is_captain : false, is_vice_captain: x.player_id === pid ? false : x.is_vice_captain }
      return x.player_id === pid ? { ...x, is_vice_captain: !x.is_vice_captain, is_captain: false } : x
    }))
  }

  async function previous() {
    try {
      const { lineup } = await aflApi.selPrevious(fixtureId)
      if (!lineup.length) { toast.error('No earlier side for this team to start from'); return }
      const valid = new Set(data.formation.flatMap(l => l.slots.map(s => s.slot)))
      change(renumber(lineup.filter(x => x.slot === BENCH || x.slot === EMG || valid.has(x.slot))))
    } catch (e) { toast.error(e.message) }
  }

  async function save() {
    const warn = side.filter(x => x.slot !== EMG).flatMap(x => (players[x.player_id]?.flags || [])
      .filter(f => f.severity === 'warn').map(f => `${players[x.player_id].name}: ${f.detail}`))
    const unavailable = side.filter(x => x.slot !== EMG && players[x.player_id]?.availability === 'UNAVAILABLE')
      .map(x => `${players[x.player_id].name} said they're unavailable`)
    const clashes = side.filter(x => players[x.player_id]?.clash).map(x => `${players[x.player_id].name} is also named for ${players[x.player_id].clash}`)
    const notes = [...warn, ...unavailable, ...clashes]
    if (notes.length && !window.confirm(`Save anyway?\n\n${notes.join('\n')}`)) return
    setSaving(true)
    try {
      await aflApi.selSaveLineup(fixtureId, side)
      toast.success('Side saved')
      await load()
    } catch (e) {
      setErrors(e.detail?.reasons || [e.message])
    } finally { setSaving(false) }
  }

  async function copySheet() {
    try {
      if (dirty) { toast.error('Save the side first, then copy it'); return }
      const { text } = await aflApi.selTeamSheet(fixtureId)
      await navigator.clipboard?.writeText(text)
      toast.success('Team sheet copied')
    } catch (e) { toast.error(e.message) }
  }

  if (!fixtures) return <div className="pt-16 flex justify-center"><LoadingSpinner /></div>
  if (!fixtures.length) return (
    <div>
      <PageHead title="Selection" />
      <Card className="p-6 text-sm text-pb-dim">No games coming up. The draw comes from PlayHQ with each sync, or add a game on Fixtures.</Card>
    </div>
  )

  const fx = data?.fixture
  const mySquad = fx?.team_id
  const pool = (data?.players || []).filter(p => {
    if (p.status === 'inactive') return false
    if (filter.q && !p.name.toLowerCase().includes(filter.q.toLowerCase())) return false
    if (filter.avail === 'available' && p.availability === 'UNAVAILABLE') return false
    if (filter.squad === 'mine' && mySquad && p.squad_id !== mySquad) return false
    if (filter.squad && filter.squad !== 'mine' && filter.squad !== 'all' && p.squad_id !== filter.squad) return false
    if (filter.pos && !(p.positions || []).includes(filter.pos)) return false
    return true
  }).sort((a, b) => (placedAt[a.id] ? 1 : 0) - (placedAt[b.id] ? 1 : 0) || b.games - a.games || a.name.localeCompare(b.name))
  const armedP = armed ? players[armed] : null
  const pickedFlags = side.filter(x => x.slot !== EMG).map(x => ({ x, p: players[x.player_id] })).filter(({ p }) => p?.flags?.length)

  // Called as functions, never mounted as components: a component declared
  // inside a render is a new type every render and React would rebuild it.
  const slotEl = ({ slot, label }) => {
    const x = bySlot[slot]
    const p = x && players[x.player_id]
    const good = armedP && !x && fits(slot, armedP.positions)
    const tone = p && flagTone(p.flags)
    return (
      <button key={slot} type="button" data-testid={`slot-${slot}`} data-slot={slot}
        onClick={() => armed ? place(armed, slot) : p && setArmed(p.id)}
        onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); place(e.dataTransfer.getData('text/plain'), slot) }}
        draggable={!!p} onDragStart={e => p && e.dataTransfer.setData('text/plain', p.id)}
        className={`relative w-full min-h-[3.25rem] rounded-md border px-1 py-1 text-center transition-colors
          ${p ? 'bg-[color-mix(in_srgb,#000_35%,transparent)] border-white/30' : 'border-dashed border-white/40 bg-white/5'}
          ${good ? 'ring-2 ring-[var(--pb-accent)]' : ''} ${armed === p?.id ? 'ring-2 ring-white' : ''}`}
        style={tone ? { borderColor: TONE[tone] } : undefined}>
        <div className="font-mono text-[9px] uppercase tracking-wide2 text-white/60">{slot}</div>
        {p ? (
          <div className="text-[12px] leading-tight text-white font-medium truncate">
            {p.jumper ? `#${p.jumper} ` : ''}{p.name}
            {x.is_captain && <span className="ml-1 text-[10px] font-mono">(c)</span>}
            {x.is_vice_captain && <span className="ml-1 text-[10px] font-mono">(vc)</span>}
          </div>
        ) : <div className="text-[10px] text-white/50">{label}</div>}
      </button>
    )
  }

  const rowEl = (x, i) => {
    const p = players[x.player_id]
    return (
      <div key={x.player_id} className="flex items-center gap-2 py-1 pb-hairline-b last:border-0 text-sm" data-testid={`${x.slot === BENCH ? 'bench' : 'emg'}-row`}>
        <span className="font-mono text-[10px] text-pb-faint w-4">{i + 1}</span>
        <button className="flex-1 min-w-0 truncate text-left" onClick={() => setArmed(x.player_id)}>
          {p?.name}{x.is_captain ? ' (c)' : ''}{x.is_vice_captain ? ' (vc)' : ''}
        </button>
        <Btn small onClick={() => remove(x.player_id)} aria-label={`Take ${p?.name} out`}>Out</Btn>
      </div>
    )
  }

  return (
    <div>
      <PageHead title="Selection"
        caption="Tap a player, then tap where they play. Tap a player on the ground to move them, name a captain or take them out."
        right={<>
          <select className={`${INPUT} max-w-full`} value={fixtureId || ''} aria-label="Fixture"
            onChange={e => { if (dirty && !window.confirm('Leave without saving this side?')) return; setParams({ fixture: e.target.value }) }}>
            {fixtures.map(f => (
              <option key={f.id} value={f.id}>{shortDate(f.played_on)} · {f.team_name || f.grade_name || 'Side'} v {f.opponent_name || f.label || 'TBC'}</option>
            ))}
          </select>
        </>} />

      {!data ? <div className="pt-10 flex justify-center"><LoadingSpinner /></div> : (
        <>
          <Card className="p-3 mb-4 flex flex-wrap items-center gap-3">
            <div className="flex-1 min-w-[14rem]">
              <div className="font-semibold">{fx.team_name || fx.grade_name || 'No side set'} {fx.home_away === 'AWAY' ? '@' : 'v'} {fx.opponent_name || fx.label || 'TBC'}</div>
              <div className="font-mono text-[11px] text-pb-faint">
                {[shortDate(fx.played_on), fx.round, fx.start_time, fx.venue].filter(Boolean).join(' · ')}
                {data.facts.is_final && <span className="ml-2 text-[var(--pb-accent)]">FINAL</span>}
              </div>
            </div>
            <div className="font-mono text-[11px] text-pb-dim" data-testid="counts">
              {onField}/{size.field} on the ground · {bench.length}/{size.bench} on the bench{size.emergencies ? ` · ${emg.length}/${size.emergencies} emergencies` : ''}
            </div>
            <Btn small onClick={previous}>Start from last week</Btn>
            <Btn small onClick={copySheet}>Copy team sheet</Btn>
            <Btn small danger onClick={() => { if (window.confirm('Clear the whole side?')) change([]) }} disabled={!side.length}>Clear</Btn>
            <Btn primary onClick={save} disabled={saving || !dirty}>{saving ? 'Saving…' : dirty ? 'Save side' : 'Saved'}</Btn>
          </Card>

          {errors.length > 0 && (
            <Card className="p-3 mb-4 border-[var(--pb-red,#e5484d)]" data-testid="save-errors">
              <div className="text-sm font-semibold" style={{ color: TONE.block }}>This side can't be saved yet</div>
              <ul className="text-sm mt-1 list-disc pl-5">{errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
            </Card>
          )}

          {armedP && (
            <Card className="p-3 mb-4 flex flex-wrap items-center gap-2 sticky top-14 md:top-2 z-20" data-testid="in-hand">
              <span className="text-sm flex-1 min-w-0">
                <strong>{armedP.name}</strong> in hand. Tap a spot on the ground, or:
              </span>
              <Btn small onClick={() => place(armed, BENCH)}>Put on the bench</Btn>
              {size.emergencies > 0 && <Btn small onClick={() => place(armed, EMG)}>Make emergency</Btn>}
              {placedAt[armed] && placedAt[armed] !== EMG && <>
                <Btn small onClick={() => setRole(armed, 'c')}>{side.find(x => x.player_id === armed)?.is_captain ? 'Not captain' : 'Captain'}</Btn>
                <Btn small onClick={() => setRole(armed, 'vc')}>{side.find(x => x.player_id === armed)?.is_vice_captain ? 'Not vice-captain' : 'Vice-captain'}</Btn>
              </>}
              {placedAt[armed] && <Btn small danger onClick={() => remove(armed)}>Take out</Btn>}
              <Btn small onClick={() => setArmed(null)}>Cancel</Btn>
            </Card>
          )}

          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
            <div className="min-w-0 order-1">
              <div id="afl-ground" className="rounded-[40%/12%] px-3 py-8 sm:px-12 sm:py-12 border-4 border-white/20" data-testid="ground"
                style={{ background: 'radial-gradient(ellipse at center, #3f8f3f 0%, #2e6f31 70%, #255c28 100%)' }}>
                {data.formation.filter(l => l.key !== 'FOL').map(line => (
                  <div key={line.key} className="mb-2">
                    <div className="font-mono text-[9px] uppercase tracking-wide3 text-white/60 text-center mb-1">{line.label}</div>
                    <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${line.slots.length}, minmax(0, 1fr))` }}>
                      {line.slots.map(slotEl)}
                    </div>
                    {line.key === 'C' && (() => {
                      const fol = data.formation.find(l => l.key === 'FOL')
                      return fol && fol.slots.length > 0 && (
                        <div className="my-3 mx-auto max-w-sm">
                          <div className="font-mono text-[9px] uppercase tracking-wide3 text-white/60 text-center mb-1">Followers</div>
                          <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${fol.slots.length}, minmax(0, 1fr))` }}>
                            {fol.slots.map(slotEl)}
                          </div>
                        </div>
                      )
                    })()}
                  </div>
                ))}
              </div>

              <div className="grid gap-4 sm:grid-cols-2 mt-4">
                <Card className="p-3" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); place(e.dataTransfer.getData('text/plain'), BENCH) }}>
                  <div className="flex justify-between items-baseline mb-1">
                    <h3 className="font-semibold text-sm">Interchange</h3>
                    <span className="font-mono text-[10px] text-pb-faint">{bench.length} of {size.bench}</span>
                  </div>
                  {bench.length === 0 && <p className="text-xs text-pb-faint py-1">Nobody on the bench.</p>}
                  {bench.map(rowEl)}
                  {armed && bench.length < size.bench && placedAt[armed] !== BENCH && (
                    <button className="mt-2 w-full text-xs py-1.5 rounded border border-dashed border-pb-hairline text-pb-dim" onClick={() => place(armed, BENCH)}>
                      + Put {armedP?.name} on the bench
                    </button>
                  )}
                </Card>
                {size.emergencies > 0 && (
                  <Card className="p-3" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); place(e.dataTransfer.getData('text/plain'), EMG) }}>
                    <div className="flex justify-between items-baseline mb-1">
                      <h3 className="font-semibold text-sm">Emergencies</h3>
                      <span className="font-mono text-[10px] text-pb-faint">{emg.length} of {size.emergencies}</span>
                    </div>
                    {emg.length === 0 && <p className="text-xs text-pb-faint py-1">No emergencies named.</p>}
                    {emg.map(rowEl)}
                  </Card>
                )}
              </div>

              {(pickedFlags.length > 0 || data.rules.length > 0) && (
                <Card className="p-3 mt-4" data-testid="rules-strip">
                  <h3 className="font-semibold text-sm mb-1">Rules</h3>
                  {data.rules.map(r => <div key={r.id} className="text-xs text-pb-dim">{r.name}: {r.summary}</div>)}
                  {pickedFlags.map(({ x, p }) => p.flags.map((f, i) => (
                    <div key={`${x.player_id}-${i}`} className="text-sm mt-1" style={{ color: TONE[f.severity] || undefined }}>
                      {f.severity === 'block' ? 'Not allowed' : 'Check'}: {p.name}, {f.detail}
                    </div>
                  )))}
                </Card>
              )}
            </div>

            <Card className="p-3 order-2 lg:max-h-[80vh] lg:overflow-y-auto" data-testid="pool">
              <div className="flex flex-wrap gap-2 mb-2">
                <input className={`${INPUT} flex-1 min-w-0`} placeholder="Search" value={filter.q} onChange={e => setFilter({ ...filter, q: e.target.value })} />
                <select className={`${INPUT} !text-xs`} value={filter.squad} onChange={e => setFilter({ ...filter, squad: e.target.value })} aria-label="Squad">
                  {mySquad && <option value="mine">This side's squad</option>}
                  <option value="all">Every squad</option>
                  {data.teams.filter(t => t.id !== mySquad).map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
                <select className={`${INPUT} !text-xs`} value={filter.avail} onChange={e => setFilter({ ...filter, avail: e.target.value })} aria-label="Availability">
                  <option value="available">Not unavailable</option>
                  <option value="all">Everyone</option>
                </select>
                <select className={`${INPUT} !text-xs`} value={filter.pos} onChange={e => setFilter({ ...filter, pos: e.target.value })} aria-label="Position">
                  <option value="">Any position</option>
                  {['FB', 'HB', 'C', 'W', 'MID', 'RUCK', 'HF', 'FF', 'UTIL'].map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              {pool.length === 0 && <p className="text-xs text-pb-faint py-2">Nobody matches. Try every squad, or everyone.</p>}
              {pool.map(p => {
                const tone = flagTone(p.flags)
                return (
                  <div key={p.id} data-testid="pool-player" draggable onDragStart={e => e.dataTransfer.setData('text/plain', p.id)}
                    onClick={() => {
                      const next = armed === p.id ? null : p.id
                      setArmed(next)
                      // On a phone the ground is above the list: take the
                      // selector to it rather than leaving them to scroll.
                      if (next && window.innerWidth < 1024) document.getElementById('afl-ground')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                    }}
                    className={`cursor-pointer rounded px-2 py-1.5 mb-1 border ${armed === p.id ? 'border-[var(--pb-accent)] bg-pb-surface2' : 'border-transparent hover:bg-pb-surface2'} ${placedAt[p.id] ? 'opacity-50' : ''}`}>
                    <div className="flex items-center gap-2">
                      <span className="text-sm flex-1 min-w-0 truncate">{p.jumper ? <span className="font-mono text-pb-faint">#{p.jumper} </span> : null}{p.name}</span>
                      {placedAt[p.id] && <span className="font-mono text-[10px] text-pb-faint">{placedAt[p.id]}</span>}
                      <AvailPill status={p.availability} />
                    </div>
                    <div className="flex flex-wrap items-center gap-2 mt-0.5">
                      <PositionChips positions={p.positions} />
                      <span className="font-mono text-[10px] text-pb-faint">
                        {p.games} gm · {p.goals} gl{p.best_on_ground ? ` · ${p.best_on_ground} BOG` : ''}{p.age != null ? ` · ${p.age}y` : ''}
                      </span>
                    </div>
                    {p.clash && <div className="text-[11px] mt-0.5" style={{ color: TONE.warn }}>Named for {p.clash} that day</div>}
                    {tone && p.flags.map((f, i) => <div key={i} className="text-[11px] mt-0.5" style={{ color: TONE[f.severity] }}>{f.name}: {f.detail}</div>)}
                  </div>
                )
              })}
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
