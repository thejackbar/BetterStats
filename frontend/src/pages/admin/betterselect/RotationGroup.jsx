// BetterSelect → Junior Rotation (one group).
//
// Four tabs: Game day (make, tweak and lock a week's batting order and field),
// Kids (the saved names), Season (who has had what), Settings (positions,
// fairness, the parent link).
//
// A DRAFT is working state; only a LOCKED week counts as history, so re-rolling
// or fixing a position by hand never changes what a kid has had. Every edit is
// a small write that names the version it saw (409 = somebody else got there
// first, and the screen shows theirs). Components are declared at module level
// so typing in a box never remounts it.
import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import BetterSelectLayout from '../../../components/admin/BetterSelectLayout'
import { useAuth } from '../../../contexts/AuthContext'
import { useToast } from '../../../contexts/ToastContext'
import { api } from '../../../lib/api'
import { CAP } from '../../../lib/capabilities'
import { PbSpinner } from '../../../lib/presskit'
import { Icon, Btn, Segmented, Chip, Tag, Empty } from './ui'
import LineupSheet, { formatRoundDate, roundToLineup } from './rotation/LineupSheet'
import { ROTATION_URL } from './Rotation'

const FIELD = 'w-full bg-pb-surface2 border border-pb-hairline rounded-lg px-3 text-sm text-pb-text placeholder:text-pb-faint focus:outline-none focus:border-pb-accent'
const LABEL = 'block font-mono text-[10px] uppercase tracking-wide2 text-pb-faintest mb-1'
const today = () => new Date().toISOString().slice(0, 10)

function Section({ title, hint, children, right, className = '' }) {
  return (
    <section className={`pb-card px-4 py-4 flex flex-col gap-3 ${className}`}>
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <h2 className="font-display font-semibold text-[15px]">{title}</h2>
          {hint && <p className="text-[12.5px] text-pb-faint mt-0.5">{hint}</p>}
        </div>
        {right}
      </div>
      {children}
    </section>
  )
}

function Banner({ tone = 'amber', children, ...rest }) {
  if (!children || (Array.isArray(children) && !children.length)) return null
  const color = tone === 'red' ? 'var(--pb-red)' : 'var(--pb-amber)'
  return (
    <div {...rest} className="rounded-lg px-3.5 py-2.5 text-[13px]"
      style={{ background: `color-mix(in srgb, ${color} 12%, transparent)`, color, border: `1px solid color-mix(in srgb, ${color} 35%, transparent)` }}>
      {children}
    </div>
  )
}

/* ── Who is here ─────────────────────────────────────────────────────────── */
function PresentChips({ players, present, onToggle, disabled }) {
  const here = new Set(present)
  return (
    <div className="flex flex-wrap gap-1.5" data-present>
      {players.map((p) => (
        <Chip key={p.id} label={p.name} active={here.has(p.id)} onClick={disabled ? undefined : () => onToggle(p.id)}
          className={disabled ? 'pointer-events-none' : ''} />
      ))}
    </div>
  )
}

/* ── A new game ──────────────────────────────────────────────────────────── */
function NewGame({ group, players, onCreated }) {
  const toast = useToast()
  const live = useMemo(() => players.filter((p) => !p.former_at), [players])
  const [date, setDate] = useState(today())
  const [label, setLabel] = useState('')
  const [fixtureId, setFixtureId] = useState('')
  const [fixtures, setFixtures] = useState([])
  const [present, setPresent] = useState(() => live.map((p) => p.id))
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.rotFixtures().then((r) => setFixtures(r.fixtures || [])).catch(() => {}) }, [])
  useEffect(() => { setPresent((cur) => cur.filter((id) => live.some((p) => p.id === id))) }, [live])

  const pickFixture = (id) => {
    setFixtureId(id)
    const f = fixtures.find((x) => x.id === id)
    if (f) {
      if (f.date) setDate(f.date)
      setLabel(f.opponent ? `vs ${f.opponent}` : (f.label || ''))
    }
  }
  const toggle = (id) => setPresent((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]))

  const create = async () => {
    if (!present.length) { toast.error('Tick at least one kid who is here.'); return }
    setBusy(true)
    try {
      const r = await api.rotCreateRound(group.id, { round_date: date, label: label.trim() || null, fixture_id: fixtureId || null, present })
      onCreated(r.round)
    } catch (e) { toast.error(e.message); setBusy(false) }
  }

  return (
    <Section title="Set up this week's game" hint="Tick who is here, then generate. You can change anything by hand afterwards." className="" >
      <div className="grid gap-3 md:grid-cols-3" data-new-game>
        <div>
          <label className={LABEL} htmlFor="rot-date">Date</label>
          <input id="rot-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} className={`${FIELD} h-[38px]`} />
        </div>
        <div>
          <label className={LABEL} htmlFor="rot-label">Label (optional)</label>
          <input id="rot-label" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. vs Bayswater" className={`${FIELD} h-[38px]`} />
        </div>
        <div className="min-w-0">
          <label className={LABEL} htmlFor="rot-fixture">Tie to a fixture (optional)</label>
          <select id="rot-fixture" value={fixtureId} onChange={(e) => pickFixture(e.target.value)} className={`${FIELD} h-[38px] min-w-0`}>
            <option value="">Not tied to a fixture</option>
            {fixtures.map((f) => (
              <option key={f.id} value={f.id}>{formatRoundDate(f.date)}{f.team ? ` · ${f.team}` : ''}{f.opponent ? ` v ${f.opponent}` : ''}</option>
            ))}
          </select>
        </div>
      </div>
      <div>
        <span className={LABEL}>Who is here ({present.length} of {live.length})</span>
        {live.length === 0
          ? <Empty>No kids in this group yet. Add them on the Kids tab.</Empty>
          : <PresentChips players={live} present={present} onToggle={toggle} />}
      </div>
      <div><Btn variant="primary" icon="rotation" onClick={create} disabled={busy || !live.length}>{busy ? 'Generating…' : 'Generate lineup'}</Btn></div>
    </Section>
  )
}

/* ── Batting order editor ────────────────────────────────────────────────── */
function BattingEditor({ order, names, editable, onMove }) {
  return (
    <ol className="divide-y divide-pb-hairline border border-pb-hairline rounded-lg overflow-hidden" data-batting-order>
      {order.map((id, i) => (
        <li key={id} data-bat-row className="flex items-center gap-2 px-3 py-1.5">
          <span className="w-6 text-right font-display font-bold pb-num text-pb-faint">{i + 1}</span>
          <span className="flex-1 min-w-0 font-display font-semibold text-[15px] truncate">{names.get(id) || 'Unknown'}</span>
          {editable && (
            <span className="flex shrink-0">
              <button type="button" aria-label={`Move ${names.get(id)} up`} disabled={i === 0} onClick={() => onMove(i, i - 1)}
                className="p-2 text-pb-faint hover:text-pb-accent disabled:opacity-30"><Icon name="arrow" size={15} className="-rotate-90" /></button>
              <button type="button" aria-label={`Move ${names.get(id)} down`} disabled={i === order.length - 1} onClick={() => onMove(i, i + 1)}
                className="p-2 text-pb-faint hover:text-pb-accent disabled:opacity-30"><Icon name="arrow" size={15} className="rotate-90" /></button>
            </span>
          )}
        </li>
      ))}
    </ol>
  )
}

/* ── Field editor: one block per change ──────────────────────────────────── */
function FieldEditor({ positions, change, ci, present, names, editable, onAssign, multi }) {
  const holder = (posId) => Object.keys(change).find((k) => change[k] === posId) || ''
  const resting = present.filter((id) => change[id] === null || change[id] === undefined)
  return (
    <div data-field-change>
      <h3 className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mb-2">{multi ? `Fielding, change ${ci + 1}` : 'Fielding'}</h3>
      <ul className="divide-y divide-pb-hairline border border-pb-hairline rounded-lg overflow-hidden">
        {positions.map((pos) => (
          <li key={pos.id} data-slot className="flex items-center gap-3 px-3 py-1.5">
            <span className="w-28 sm:w-32 shrink-0 text-[13px] text-pb-dim flex items-center gap-1.5 min-w-0">
              <span className="truncate">{pos.name}</span>
              {pos.key && <span className="font-mono text-[9px] font-bold tracking-wide2 text-pb-accent">KEY</span>}
            </span>
            <select aria-label={`${pos.name}${multi ? `, change ${ci + 1}` : ''}`} value={holder(pos.id)} disabled={!editable}
              onChange={(e) => onAssign(ci, pos.id, e.target.value)}
              className="flex-1 min-w-0 bg-pb-surface2 border border-pb-hairline rounded-lg px-2 h-[34px] text-sm text-pb-text focus:outline-none focus:border-pb-accent disabled:opacity-100">
              <option value="">Nobody</option>
              {present.map((id) => <option key={id} value={id}>{names.get(id)}</option>)}
            </select>
          </li>
        ))}
      </ul>
      {resting.length > 0 && (
        <p data-resting className="text-[13px] text-pb-dim mt-2">
          <span className="font-mono text-[10px] uppercase tracking-wide2 text-pb-faint mr-1.5">Resting</span>
          {resting.map((id) => names.get(id)).join(', ')}
        </p>
      )}
    </div>
  )
}

/* ── One round, draft or locked ──────────────────────────────────────────── */
function RoundView({ group, players, round, canEdit, save, act, busy }) {
  const names = useMemo(() => new Map(players.map((p) => [p.id, p.name])), [players])
  const live = useMemo(() => players.filter((p) => !p.former_at), [players])
  const locked = round.status === 'locked'
  const editable = canEdit && !locked
  const lineup = useMemo(() => roundToLineup(round, group, players), [round, group, players])
  const positions = group.positions || []
  const sortedPresent = useMemo(() => round.present.slice().sort((a, b) => (names.get(a) || '').localeCompare(names.get(b) || '')), [round.present, names])

  const move = (from, to) => {
    const next = round.batting_order.slice()
    ;[next[from], next[to]] = [next[to], next[from]]
    save({ batting_order: next }, { batting_order: next })
  }
  const assign = (ci, posId, kidId) => {
    const next = round.fielding.map((c) => ({ ...c }))
    const row = next[ci]
    const holder = Object.keys(row).find((k) => row[k] === posId) || null
    if (!kidId) {
      if (holder) row[holder] = null
    } else {
      const kidOld = row[kidId] === undefined ? null : row[kidId]
      row[kidId] = posId
      if (holder && holder !== kidId) row[holder] = kidOld
    }
    save({ fielding: next }, { fielding: next })
  }
  const togglePresent = (id) => {
    const cur = round.present
    save({ present: cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id] })
  }
  const printUrl = `${ROTATION_URL}/${group.id}/print/${round.id}`

  return (
    <div className="flex flex-col gap-4" data-round={round.id} data-round-status={round.status}>
      <div className="pb-card px-4 py-3 flex flex-wrap items-center gap-x-3 gap-y-2">
        <div className="flex-1 min-w-0">
          <div className="font-display font-semibold text-[15px] break-words">{round.label || 'Game'} <span className="text-pb-faint font-normal">· {formatRoundDate(round.round_date)}</span></div>
        </div>
        <Tag tone={locked ? 'accent' : 'faint'}>{locked ? 'LOCKED' : 'DRAFT'}</Tag>
        <div className="flex flex-wrap gap-2 basis-full sm:basis-auto">
          {editable && <Btn sm icon="reset" onClick={() => act('generate', { part: 'all' })} disabled={busy} data-reroll="all">Re-roll everything</Btn>}
          {editable && group.bats && <Btn sm onClick={() => act('generate', { part: 'batting' })} disabled={busy} data-reroll="batting">Re-roll batting</Btn>}
          {editable && positions.length > 0 && <Btn sm onClick={() => act('generate', { part: 'fielding' })} disabled={busy} data-reroll="fielding">Re-roll field</Btn>}
          <Btn sm icon="download" href={printUrl} target="_blank" data-print>Print</Btn>
          {canEdit && !locked && <Btn sm variant="primary" icon="lock" onClick={() => act('lock')} disabled={busy} data-lock>Lock this game</Btn>}
          {canEdit && locked && <Btn sm onClick={() => act('unlock')} disabled={busy} data-unlock>Unlock to change</Btn>}
          {editable && <Btn sm variant="danger" icon="trash" onClick={() => act('delete')} disabled={busy} data-delete>Delete draft</Btn>}
        </div>
      </div>

      {locked && (
        <p className="text-[12.5px] text-pb-faint" data-locked-note>
          This game is locked and counts towards the season. {group.public_enabled ? 'Parents can see it on the parent link.' : 'Turn on the parent link in Settings to let parents see it.'}
        </p>
      )}
      {!locked && <Banner data-warnings>{(round.warnings || []).map((w) => <div key={w}>{w}</div>)}</Banner>}

      {!locked && (
        <Section title="Who is here" hint="Untick a kid who has gone home, or tick a late arrival. Late arrivals go to the end of the order and rest until you place them.">
          <PresentChips players={live} present={round.present} onToggle={togglePresent} disabled={!editable} />
        </Section>
      )}

      {locked ? (
        <div className="pb-card px-4 py-4"><LineupSheet batting={lineup.batting} changes={lineup.changes} bats={group.bats} /></div>
      ) : (
        <div className={`grid gap-4 ${group.bats && positions.length ? 'lg:grid-cols-2' : ''}`}>
          {group.bats && (
            <Section title="Batting order" hint="First to bat first. Use the arrows to change it.">
              {round.batting_order.length
                ? <BattingEditor order={round.batting_order} names={names} editable={editable} onMove={move} />
                : <Empty>Nobody is in the order yet.</Empty>}
            </Section>
          )}
          {positions.length > 0 && (
            <Section title="Fielding" hint="Pick a kid for a position and anyone already there swaps with them.">
              <div className="flex flex-col gap-4">
                {round.fielding.length === 0 && <Empty>No field yet. Generate it above.</Empty>}
                {round.fielding.map((change, ci) => (
                  <FieldEditor key={ci} positions={positions} change={change} ci={ci} multi={round.fielding.length > 1}
                    present={sortedPresent}
                    names={names} editable={editable} onAssign={assign} />
                ))}
              </div>
            </Section>
          )}
        </div>
      )}
    </div>
  )
}

/* ── Game day tab ────────────────────────────────────────────────────────── */
function GameDay({ group, players, canEdit }) {
  const toast = useToast()
  const [rounds, setRounds] = useState(null)
  const [sel, setSel] = useState(null)     // a round id, or 'new'
  const [round, setRound] = useState(null)
  const [busy, setBusy] = useState(false)
  const roundRef = useRef(null)
  const queue = useRef(Promise.resolve())
  const toastRef = useRef(toast)
  toastRef.current = toast

  const adopt = useCallback((r) => {
    roundRef.current = r
    setRound(r)
    setRounds((cur) => (cur ? cur.map((x) => (x.id === r.id ? { ...x, ...r } : x)) : cur))
  }, [])

  useEffect(() => {
    let alive = true
    api.rotRounds(group.id).then((r) => {
      if (!alive) return
      const list = r.rounds || []
      setRounds(list)
      const draft = list.find((x) => x.status === 'draft')
      setSel((draft || list[0] || { id: 'new' }).id)
    }).catch((e) => { toastRef.current.error(e.message); if (alive) { setRounds([]); setSel('new') } })
    return () => { alive = false }
  }, [group.id])

  useEffect(() => {
    if (!sel || sel === 'new') { setRound(null); roundRef.current = null; return undefined }
    let alive = true
    api.rotGetRound(sel).then((r) => { if (alive) adopt(r.round) }).catch((e) => toastRef.current.error(e.message))
    return () => { alive = false }
  }, [sel, adopt])

  // Writes go through one chain so a second edit never races the first's version.
  const run = useCallback((fn) => {
    const p = queue.current.then(fn).catch((e) => {
      const d = e.detail
      if (e.status === 409 && d && d.round) adopt(d.round)
      else if (e.status === 409 && roundRef.current) api.rotGetRound(roundRef.current.id).then((r) => adopt(r.round)).catch(() => {})
      toastRef.current.error(e.message)
    })
    queue.current = p
    return p
  }, [adopt])

  const save = useCallback((patch, optimistic) => {
    if (optimistic) setRound((cur) => (cur ? { ...cur, ...optimistic } : cur))
    return run(async () => {
      const cur = roundRef.current
      const r = await api.rotPutRound(cur.id, { version: cur.version, ...patch })
      adopt(r.round)
    })
  }, [run, adopt])

  const act = useCallback(async (what, body) => {
    const cur = roundRef.current
    if (!cur) return
    if (what === 'delete' && !confirm('Delete this draft? A locked game cannot be deleted.')) return
    setBusy(true)
    await run(async () => {
      if (what === 'generate') adopt((await api.rotGenerate(cur.id, { ...body, version: roundRef.current.version })).round)
      else if (what === 'lock') adopt((await api.rotLock(cur.id)).round)
      else if (what === 'unlock') adopt((await api.rotUnlock(cur.id)).round)
      else if (what === 'delete') {
        await api.rotDeleteRound(cur.id)
        const left = (rounds || []).filter((x) => x.id !== cur.id)
        setRounds(left)
        setSel('new')
      }
    })
    setBusy(false)
  }, [run, adopt, rounds])

  const created = (r) => {
    setRounds((cur) => [r, ...(cur || [])])
    setSel(r.id)
    adopt(r)
  }

  if (rounds === null) return <PbSpinner message="Loading games…" />
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-1.5 items-center" data-round-list>
        {canEdit && <Chip label="+ New game" active={sel === 'new'} onClick={() => setSel('new')} />}
        {rounds.map((r) => (
          <Chip key={r.id} active={sel === r.id} onClick={() => setSel(r.id)}
            label={`${formatRoundDate(r.round_date)}${r.status === 'locked' ? ' 🔒' : ' · draft'}`} />
        ))}
      </div>
      {sel === 'new' && canEdit && <NewGame group={group} players={players} onCreated={created} />}
      {sel === 'new' && !canEdit && <Empty>No game is set up. Ask someone with edit access to make one.</Empty>}
      {sel && sel !== 'new' && round && round.id === sel && (
        <RoundView group={group} players={players} round={round} canEdit={canEdit} save={save} act={act} busy={busy} />
      )}
      {sel && sel !== 'new' && (!round || round.id !== sel) && <PbSpinner message="Loading game…" />}
    </div>
  )
}

/* ── Kids tab ────────────────────────────────────────────────────────────── */
function KidRow({ kid, positions, canEdit, onPatch }) {
  const [name, setName] = useState(kid.name)
  const [note, setNote] = useState(kid.note || '')
  useEffect(() => { setName(kid.name) }, [kid.name])
  useEffect(() => { setNote(kid.note || '') }, [kid.note])
  const avoided = positions.filter((p) => kid.avoid_positions.includes(p.id))
  const toggleAvoid = (id) => onPatch(kid.id, {
    avoid_positions: kid.avoid_positions.includes(id) ? kid.avoid_positions.filter((x) => x !== id) : [...kid.avoid_positions, id],
  })
  return (
    <li data-kid={kid.name} className="px-3 py-2.5 flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <input aria-label={`Name for ${kid.name}`} value={name} disabled={!canEdit}
          onChange={(e) => setName(e.target.value)}
          onBlur={() => { if (name.trim() && name.trim() !== kid.name) onPatch(kid.id, { name: name.trim() }); else setName(kid.name) }}
          className={`${FIELD} h-[34px] flex-1 min-w-0`} />
        {canEdit && <Btn sm variant="ghost" onClick={() => onPatch(kid.id, { active: false })} data-leave>Left the group</Btn>}
      </div>
      <details className="text-[12.5px]">
        <summary className="cursor-pointer text-pb-faint">
          {avoided.length ? `Kept out of: ${avoided.map((p) => p.name).join(', ')}` : 'No position restrictions'}{kid.note ? ` · ${kid.note}` : ''}
        </summary>
        <div className="mt-2 flex flex-col gap-2">
          <div className="flex flex-wrap gap-1.5">
            {positions.map((p) => (
              <Chip key={p.id} label={p.name} active={kid.avoid_positions.includes(p.id)} onClick={canEdit ? () => toggleAvoid(p.id) : undefined} />
            ))}
          </div>
          <p className="text-pb-faint">Tick a position to keep this kid out of it. It is honoured whenever there is another way to fill the field.</p>
          <input aria-label={`Note for ${kid.name}`} value={note} disabled={!canEdit} placeholder="A note for yourself (optional)"
            onChange={(e) => setNote(e.target.value)}
            onBlur={() => { if (note.trim() !== (kid.note || '')) onPatch(kid.id, { note: note.trim() }) }}
            className={`${FIELD} h-[34px]`} />
        </div>
      </details>
    </li>
  )
}

function KidsTab({ group, players, canEdit, reload }) {
  const toast = useToast()
  const [names, setNames] = useState('')
  const [busy, setBusy] = useState(false)
  const live = players.filter((p) => !p.former_at)
  const former = players.filter((p) => p.former_at)
  const positions = group.positions || []

  const add = async () => {
    if (!names.trim()) return
    setBusy(true)
    try {
      const r = await api.rotAddPlayers(group.id, names)
      setNames('')
      const bits = []
      if (r.added) bits.push(`${r.added} added`)
      if (r.returned) bits.push(`${r.returned} brought back`)
      if (r.skipped) bits.push(`${r.skipped} already here`)
      toast.success(bits.join(', ') || 'Nothing to add')
      await reload()
    } catch (e) { toast.error(e.message) }
    setBusy(false)
  }
  const patch = async (id, data) => {
    try { await api.rotPatchPlayer(id, data); await reload() } catch (e) { toast.error(e.message); reload() }
  }

  return (
    <div className="flex flex-col gap-4">
      {canEdit && (
        <Section title="Add kids" hint="One name a line, or separated by commas. A name that is already here is skipped; a kid who left comes back with their history.">
          <textarea aria-label="Names to add" rows={3} value={names} onChange={(e) => setNames(e.target.value)} placeholder={'Mia Jones\nLeo Wilson'} className={`${FIELD} py-2 resize-y`} />
          <div><Btn variant="primary" icon="plus" onClick={add} disabled={busy || !names.trim()}>Add kids</Btn></div>
        </Section>
      )}
      <Section title={`In the group (${live.length})`}>
        {live.length === 0 ? <Empty>Nobody yet.</Empty> : (
          <ul className="divide-y divide-pb-hairline border border-pb-hairline rounded-lg overflow-hidden" data-kids>
            {live.map((k) => <KidRow key={k.id} kid={k} positions={positions} canEdit={canEdit} onPatch={patch} />)}
          </ul>
        )}
      </Section>
      {former.length > 0 && (
        <details className="pb-card px-4 py-3" data-former>
          <summary className="cursor-pointer font-display font-semibold text-[14px]">Kids who have left ({former.length})</summary>
          <ul className="mt-2 divide-y divide-pb-hairline">
            {former.map((k) => (
              <li key={k.id} className="flex items-center gap-2 py-2">
                <span className="flex-1 min-w-0 truncate text-pb-dim">{k.name}</span>
                {canEdit && <Btn sm onClick={() => patch(k.id, { active: true })}>Bring back</Btn>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

/* ── Season tab ──────────────────────────────────────────────────────────── */
function SeasonTab({ group }) {
  const toast = useToast()
  const [tally, setTally] = useState(null)
  const toastRef = useRef(toast)
  toastRef.current = toast
  useEffect(() => {
    let alive = true
    api.rotTally(group.id).then((t) => { if (alive) setTally(t) }).catch((e) => { toastRef.current.error(e.message); if (alive) setTally({ players: [], rounds: 0, spread: null }) })
    return () => { alive = false }
  }, [group.id])
  if (!tally) return <PbSpinner message="Counting…" />
  const positions = group.positions || []
  const rows = tally.players.filter((p) => !p.former || p.games > 0)
  const sp = tally.spread
  return (
    <div className="flex flex-col gap-4">
      <p className="text-[13px] text-pb-dim" data-season-summary>
        {tally.rounds === 0
          ? 'Nothing counts yet. Only games you have locked are added to the season.'
          : `${tally.rounds} locked ${tally.rounds === 1 ? 'game' : 'games'}.${sp ? ` Kids are at most ${sp.rests} ${sp.rests === 1 ? 'rest' : 'rests'} and ${sp.key_turns} key-position ${sp.key_turns === 1 ? 'turn' : 'turns'} apart.` : ''}`}
      </p>
      {rows.length > 0 && (
        <div className="pb-card overflow-x-auto" data-tally>
          <table className="min-w-full text-[13px]">
            <thead>
              <tr className="text-left font-mono text-[10px] uppercase tracking-wide2 text-pb-faint border-b border-pb-hairline">
                <th className="px-3 py-2 sticky left-0 bg-pb-surface">Kid</th>
                <th className="px-2 py-2 text-right">Games</th>
                <th className="px-2 py-2 text-right" title="Times they batted first">Led off</th>
                <th className="px-2 py-2 text-right" title="Times they batted last">Last</th>
                <th className="px-2 py-2 text-right" title="Where they usually bat: 0% first, 100% last">Avg spot</th>
                <th className="px-2 py-2 text-right">Rests</th>
                <th className="px-2 py-2 text-right">Key turns</th>
                {positions.map((p) => <th key={p.id} className="px-2 py-2 text-right whitespace-nowrap">{p.name}{p.key ? ' ★' : ''}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} data-tally-row={r.name} className="border-b border-pb-hairline last:border-0">
                  <td className="px-3 py-2 font-display font-semibold sticky left-0 bg-pb-surface whitespace-nowrap">{r.name}{r.former ? ' (left)' : ''}</td>
                  <td className="px-2 py-2 text-right pb-num">{r.games}</td>
                  <td className="px-2 py-2 text-right pb-num">{r.bat_first}</td>
                  <td className="px-2 py-2 text-right pb-num">{r.bat_last}</td>
                  <td className="px-2 py-2 text-right pb-num">{r.bat_avg === null ? '-' : `${Math.round(r.bat_avg * 100)}%`}</td>
                  <td className="px-2 py-2 text-right pb-num">{r.rests}</td>
                  <td className="px-2 py-2 text-right pb-num">{r.key_turns}</td>
                  {positions.map((p) => <td key={p.id} className="px-2 py-2 text-right pb-num">{r.field[p.id] || 0}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-[12px] text-pb-faint">★ marks a key position. Avg spot is where a kid usually bats, from 0% (first) to 100% (last); the generator leans towards putting kids who usually bat late near the front.</p>
    </div>
  )
}

/* ── Settings tab ────────────────────────────────────────────────────────── */
function PositionsEditor({ group, canEdit, reload }) {
  const toast = useToast()
  const [rows, setRows] = useState(() => (group.positions || []).map((p) => ({ ...p })))
  const [busy, setBusy] = useState(false)
  const storedKey = JSON.stringify(group.positions || [])
  useEffect(() => { setRows((JSON.parse(storedKey)).map((p) => ({ ...p }))) }, [storedKey])
  const set = (i, patch) => setRows((cur) => cur.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  const swap = (i, j) => setRows((cur) => { const n = cur.slice(); [n[i], n[j]] = [n[j], n[i]]; return n })
  const dirty = JSON.stringify(rows) !== JSON.stringify(group.positions || [])
  const save = async () => {
    setBusy(true)
    try { await api.rotPatchGroup(group.id, { positions: rows }); await reload(); toast.success('Positions saved') }
    catch (e) { toast.error(e.message) }
    setBusy(false)
  }
  return (
    <Section title="Field positions" hint="The positions every game is filled from. Mark the ones kids want as key and they are shared out first. Renaming keeps a position's history; removing one drops it from the season table.">
      <ul className="flex flex-col gap-2" data-positions>
        {rows.map((r, i) => (
          <li key={r.id || `new-${i}`} className="flex items-center gap-2" data-position-row>
            <input aria-label={`Position ${i + 1} name`} value={r.name} disabled={!canEdit} onChange={(e) => set(i, { name: e.target.value })} className={`${FIELD} h-[34px] flex-1 min-w-0`} />
            <label className="flex items-center gap-1.5 text-[12.5px] text-pb-dim shrink-0">
              <input type="checkbox" checked={!!r.key} disabled={!canEdit} onChange={(e) => set(i, { key: e.target.checked })} /> Key
            </label>
            {canEdit && (
              <span className="flex shrink-0">
                <button type="button" aria-label={`Move ${r.name} up`} disabled={i === 0} onClick={() => swap(i, i - 1)} className="p-1.5 text-pb-faint hover:text-pb-accent disabled:opacity-30"><Icon name="arrow" size={14} className="-rotate-90" /></button>
                <button type="button" aria-label={`Move ${r.name} down`} disabled={i === rows.length - 1} onClick={() => swap(i, i + 1)} className="p-1.5 text-pb-faint hover:text-pb-accent disabled:opacity-30"><Icon name="arrow" size={14} className="rotate-90" /></button>
                <button type="button" aria-label={`Remove ${r.name}`} onClick={() => setRows((cur) => cur.filter((_, j) => j !== i))} className="p-1.5 text-pb-faint hover:text-pb-red"><Icon name="trash" size={14} /></button>
              </span>
            )}
          </li>
        ))}
      </ul>
      {canEdit && (
        <div className="flex flex-wrap gap-2">
          <Btn sm icon="plus" onClick={() => setRows((cur) => [...cur, { name: '', key: false }])} data-add-position>Add a position</Btn>
          <Btn sm variant="primary" onClick={save} disabled={busy || !dirty} data-save-positions>Save positions</Btn>
        </div>
      )}
    </Section>
  )
}

function LinkPanel({ group, canEdit, reload }) {
  const toast = useToast()
  const url = group.public_path ? `${window.location.origin}${group.public_path}` : ''
  const patch = async (data) => { try { await api.rotPatchGroup(group.id, data); await reload() } catch (e) { toast.error(e.message) } }
  const regen = async () => {
    if (!confirm('Make a new link? The old one stops working straight away.')) return
    try { await api.rotRegenerateLink(group.id); await reload() } catch (e) { toast.error(e.message) }
  }
  const copy = async () => {
    try { await navigator.clipboard.writeText(url); toast.success('Link copied') } catch { toast.error('Could not copy. Select the link and copy it.') }
  }
  return (
    <Section title="Parent link" hint="A page parents can open to see who bats where and who fields where, for locked games only. It is off until you turn it on.">
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" data-link-enabled checked={group.public_enabled} disabled={!canEdit} onChange={(e) => patch({ public_enabled: e.target.checked })} />
        Parents can see locked games on a link
      </label>
      {group.public_enabled && url && (
        <div className="flex flex-col gap-2">
          <div className="flex gap-2">
            <input readOnly aria-label="Parent link" value={url} onFocus={(e) => e.target.select()} className={`${FIELD} h-[34px] flex-1 min-w-0`} data-link-url />
            <Btn sm onClick={copy}>Copy</Btn>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" data-link-surnames checked={group.public_show_surnames} disabled={!canEdit} onChange={(e) => patch({ public_show_surnames: e.target.checked })} />
            Show surnames (otherwise a first name and last initial)
          </label>
          {canEdit && <div><Btn sm variant="danger" onClick={regen}>Make a new link</Btn></div>}
        </div>
      )}
    </Section>
  )
}

function SettingsTab({ group, canEdit, reload, onArchived }) {
  const toast = useToast()
  const [name, setName] = useState(group.name)
  const [innings, setInnings] = useState(group.innings)
  const [fairness, setFairness] = useState(group.fairness)
  const [bats, setBats] = useState(group.bats)
  const [busy, setBusy] = useState(false)
  useEffect(() => { setName(group.name); setInnings(group.innings); setFairness(group.fairness); setBats(group.bats) }, [group.name, group.innings, group.fairness, group.bats])
  const dirty = name !== group.name || innings !== group.innings || fairness !== group.fairness || bats !== group.bats
  const save = async () => {
    setBusy(true)
    try { await api.rotPatchGroup(group.id, { name, innings, fairness, bats }); await reload(); toast.success('Settings saved') }
    catch (e) { toast.error(e.message) }
    setBusy(false)
  }
  const archive = async () => {
    if (!confirm('Archive this group? Its locked games are kept and you can restore it any time.')) return
    try { await api.rotArchiveGroup(group.id); onArchived() } catch (e) { toast.error(e.message) }
  }
  return (
    <div className="flex flex-col gap-4">
      <Section title="This group">
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <label className={LABEL} htmlFor="rot-gname">Name</label>
            <input id="rot-gname" value={name} disabled={!canEdit} onChange={(e) => setName(e.target.value)} className={`${FIELD} h-[38px]`} />
          </div>
          <div>
            <label className={LABEL} htmlFor="rot-innings">Field changes per game</label>
            <select id="rot-innings" value={innings} disabled={!canEdit} onChange={(e) => setInnings(Number(e.target.value))} className={`${FIELD} h-[38px]`}>
              {[1, 2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
        </div>
        <div>
          <label className={LABEL} htmlFor="rot-fair">How evenly to share things out: {fairness}%</label>
          <input id="rot-fair" type="range" min="0" max="100" step="10" value={fairness} disabled={!canEdit} onChange={(e) => setFairness(Number(e.target.value))} className="w-full accent-[var(--pb-accent)]" />
          <div className="flex justify-between text-[11.5px] text-pb-faint"><span>Pure shuffle</span><span>Keeps everything even</span></div>
          <p className="text-[12px] text-pb-faint mt-1">Every week is still a random draw. Higher just leans it towards whoever has had fewer turns, so it evens out over the season without being predictable.</p>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={bats} disabled={!canEdit} onChange={(e) => setBats(e.target.checked)} /> This group has a batting order
        </label>
        {canEdit && <div><Btn variant="primary" onClick={save} disabled={busy || !dirty} data-save-settings>Save settings</Btn></div>}
      </Section>
      <PositionsEditor group={group} canEdit={canEdit} reload={reload} />
      <LinkPanel group={group} canEdit={canEdit} reload={reload} />
      {canEdit && (
        <Section title="Archive" hint="Hides the group from the list. Its locked games stay on record.">
          <div><Btn variant="danger" onClick={archive}>Archive this group</Btn></div>
        </Section>
      )}
    </div>
  )
}

/* ── The page ────────────────────────────────────────────────────────────── */
export default function RotationGroup() {
  const { groupId } = useParams()
  const { canEditCap } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const canEdit = canEditCap(CAP.SELECT_ROTATION, CAP.MANAGE_SELECTIONS)
  const [data, setData] = useState(null)
  const [missing, setMissing] = useState(false)
  const [tab, setTab] = useState('game')
  const toastRef = useRef(toast)
  toastRef.current = toast

  const reload = useCallback(async () => {
    try { setData(await api.rotGetGroup(groupId)) }
    catch (e) { if (e.status === 404) setMissing(true); else toastRef.current.error(e.message) }
  }, [groupId])
  useEffect(() => { setData(null); setMissing(false); reload() }, [reload])

  const tabs = [
    { value: 'game', label: 'Game day' },
    { value: 'kids', label: 'Kids' },
    { value: 'season', label: 'Season' },
    { value: 'settings', label: 'Settings' },
  ]

  return (
    <BetterSelectLayout title={data ? data.group.name : 'Junior Rotation'}
      actions={<Segmented options={tabs} value={tab} onChange={setTab} sm />}>
      <div className="flex flex-col gap-4">
        <Link to={ROTATION_URL} className="text-[12.5px] text-pb-faint hover:text-pb-accent inline-flex items-center gap-1 w-fit"><Icon name="back" size={13} /> All groups</Link>
        {missing && <Empty className="py-10 text-center">That group could not be found.</Empty>}
        {!missing && !data && <PbSpinner message="Loading group…" />}
        {data && (
          <>
            {data.group.archived && <Banner>This group is archived. <button type="button" className="underline" onClick={async () => { await api.rotArchiveGroup(groupId, true); reload() }}>Restore it</button></Banner>}
            {tab === 'game' && <GameDay group={data.group} players={data.players} canEdit={canEdit && !data.group.archived} />}
            {tab === 'kids' && <KidsTab group={data.group} players={data.players} canEdit={canEdit} reload={reload} />}
            {tab === 'season' && <SeasonTab group={data.group} />}
            {tab === 'settings' && <SettingsTab group={data.group} canEdit={canEdit} reload={reload} onArchived={() => navigate(ROTATION_URL)} />}
          </>
        )}
      </div>
    </BetterSelectLayout>
  )
}
