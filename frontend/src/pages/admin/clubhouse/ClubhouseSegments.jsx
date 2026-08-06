import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../../../lib/api'
import BetterClubhouseLayout from '../../../components/admin/BetterClubhouseLayout'
import {
  Button, Caption, Note, ListRow, Badge, Empty, TextInput,
  TableWrap, TableHead, TableRow, Cell, Toast, SectionHeading, TINT, INPUT_CLS,
} from '../../../components/admin/ui'
import { CLUB_FIELD_DEFS, RuleRow, newRule } from '../bettercomms/segmentFields'
import ScreenIntro, { useScreenIntro, INTROS } from './intro'
import { money } from './data'

// Segments — a group of people described by a rule, not by a roll call.
//
// A segment is a set of conditions that resolves at send time and is never
// frozen: someone who joins tomorrow is in it tomorrow. That is the whole
// difference from a List, which is people picked by hand and stays as picked.
//
// Both are things an email can be addressed to. The composer calls that slot
// the AUDIENCE, and its dropdown offers the club's segments and its lists as
// the two kinds of thing an audience can be. So: an email has one audience;
// that audience is a segment or a list.
//
// ⚠ Club scope only. This imports CLUB_FIELD_DEFS and nothing else. The Clubs
// Directory prospect fields (is_trialing, engagement_score, …) are BetterCricket
// sales telemetry and live behind the super-admin mount. See
// docs/design_handoff_betterclubhouse/PROJECT_RULES.md.

const COLS = 'minmax(180px,1fr) 160px 110px 120px'
const MIN_W = 700

// The segments Today can ask for by name when an officer follows an action.
const PRESETS = {
  owing: { name: 'Owes money', rules: [{ field: 'owes_money', op: 'eq', value: 'yes' }] },
}

// How reachable a person is, from what the contact record actually holds.
function reachability(c) {
  if (c.email) return { key: 'email', label: 'Email', tone: 'ok' }
  if (c.guardian_email || c.parent_email) return { key: 'guardian', label: 'Via guardian', tone: 'warn' }
  return { key: 'none', label: 'No address', tone: 'block' }
}

function SegmentRules({ rules, setRules, opts }) {
  // The rule row builds its own controls, so it takes the class rather than the
  // component. `!w-auto` because a condition is a row of three controls sized to
  // their content, not one full-width field.
  const inputCls = `${INPUT_CLS} !w-auto !py-1.5 !text-[13px]`
  return (
    <div>
      <Caption>Match people where all of these are true</Caption>
      <div className="mt-1.5">
        {rules.map((r, i) => (
          <RuleRow
            key={i} rule={r} defs={CLUB_FIELD_DEFS} opts={opts} inputCls={inputCls}
            onChange={nr => setRules(rs => rs.map((x, j) => (j === i ? nr : x)))}
            onRemove={() => setRules(rs => (rs.length > 1 ? rs.filter((_, j) => j !== i) : rs))}
          />
        ))}
      </div>
      <Button size="sm" onClick={() => setRules(rs => [...rs, newRule(CLUB_FIELD_DEFS)])} className="mt-1.5">
        + Add condition
      </Button>
    </div>
  )
}

export default function ClubhouseSegments() {
  const location = useLocation()
  const navigate = useNavigate()
  // The stored key stays 'audiences' on purpose: it is what marks this screen's
  // introduction as seen, per person, and renaming it would re-show the
  // introduction to everyone who has already dismissed it.
  const intro = useScreenIntro('audiences')

  const [segments, setSegments] = useState(null)
  const [sizes, setSizes] = useState({})     // segment id → how many it matches today
  const [opts, setOpts] = useState({ roles: [], genders: [], teams: [] })
  const [selId, setSelId] = useState(null)
  const [draft, setDraft] = useState(null)      // { id, name, rules }
  const [resolved, setResolved] = useState(null)
  const [counting, setCounting] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [toast, setToast] = useState(null)

  const load = useCallback(async () => {
    try {
      const list = await api.commsListSegments()
      setSegments(list)
      setSelId(cur => cur || list[0]?.id || null)
      // A segment's size is a fact about today, not something stored, so ask
      // for each one rather than showing a number that would slowly go stale.
      list.forEach(a => {
        api.commsPreviewSegment(a.definition || { match: 'all', rules: [] })
          .then(r => setSizes(s => ({ ...s, [a.id]: r.count })))
          .catch(() => {})
      })
    } catch (e) { setError(e.message); setSegments([]) }
  }, [])

  useEffect(() => { load(); api.commsSegmentOptions().then(setOpts).catch(() => {}) }, [load])

  // Today's "Email these N" arrives asking for a kind of segment. Select a
  // saved one that already describes it, or open an unsaved draft carrying the
  // rule — the officer pressed a button about people who owe money, so landing
  // on an empty builder would make them describe it again.
  //
  // `audience` is still read as a fallback so a Today page served from a cached
  // bundle, which still sends the old key, keeps working.
  const wanted = location.state?.segment || location.state?.audience
  const seeded = useRef(false)
  useEffect(() => {
    if (!wanted || segments == null || seeded.current) return
    seeded.current = true
    const hit = segments.find(a =>
      (a.definition?.rules || []).some(r => r.field === PRESETS[wanted]?.rules[0].field) ||
      a.name.toLowerCase().includes(wanted))
    if (hit) { setSelId(hit.id); return }
    const preset = PRESETS[wanted]
    if (preset) { setSelId(null); setDraft({ id: null, name: preset.name, rules: preset.rules }) }
  }, [wanted, segments])

  const selected = useMemo(() => segments?.find(a => a.id === selId) || null, [segments, selId])

  // Editing a saved segment works on a draft, so a half-built rule never
  // reaches the server.
  //
  // It only ever LOADS a draft, and never clears one. It used to null the draft
  // whenever nothing was selected, which is exactly the state "New segment"
  // puts the screen in — so pressing it set a fresh draft, this effect then ran
  // because `selected` had just gone null, and wiped it in the same commit. The
  // button read as doing nothing at all, and a club with no saved segments yet
  // could never build its first one. Clearing is now the caller's job (delete
  // does it explicitly), which is the only place it is actually wanted.
  useEffect(() => {
    if (!selected) return
    setDraft({
      id: selected.id,
      name: selected.name,
      rules: selected.definition?.rules?.length ? selected.definition.rules : [newRule(CLUB_FIELD_DEFS)],
    })
  }, [selected?.id])   // eslint-disable-line react-hooks/exhaustive-deps

  const definition = useMemo(
    () => ({ match: 'all', rules: (draft?.rules || []).filter(r => String(r.value ?? '').trim() !== '') }),
    [draft],
  )
  const defKey = JSON.stringify(definition)

  // A segment reports what it matches TODAY, so resolve it live rather than
  // storing a count that would slowly become a lie.
  useEffect(() => {
    if (!draft) { setResolved(null); return }
    let live = true
    setCounting(true)
    const t = setTimeout(() => {
      api.commsResolveSegment(definition)
        .then(r => { if (live) { setResolved(r); setCounting(false) } })
        .catch(() => { if (live) { setResolved({ count: 0, contacts: [] }); setCounting(false) } })
    }, 350)
    return () => { live = false; clearTimeout(t) }
  }, [defKey])   // eslint-disable-line react-hooks/exhaustive-deps

  const contacts = resolved?.contacts || []
  const total = resolved?.count ?? 0
  const reachable = contacts.filter(c => reachability(c).key === 'email').length
  const otherRoute = contacts.filter(c => reachability(c).key === 'guardian').length

  async function save() {
    if (!draft?.name.trim()) { setError('Give the segment a name.'); return }
    setBusy(true); setError('')
    try {
      const saved = draft.id
        ? await api.commsUpdateSegment(draft.id, draft.name.trim(), definition)
        : await api.commsCreateSegment(draft.name.trim(), definition)
      setToast({ title: 'Segment saved', body: `${draft.name.trim()} matches ${total} ${total === 1 ? 'person' : 'people'} right now.` })
      await load()
      setSelId(saved.id)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  async function duplicate() {
    if (!draft) return
    setBusy(true)
    try {
      const copy = await api.commsCreateSegment(`${draft.name} (copy)`, definition)
      await load(); setSelId(copy.id)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  async function remove() {
    if (!draft?.id || !window.confirm(`Delete "${draft.name}"? Emails already sent to it are unaffected.`)) return
    setBusy(true)
    try { await api.commsDeleteSegment(draft.id); setSelId(null); setDraft(null); await load() }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  function startNew() {
    setSelId(null)
    setDraft({ id: null, name: '', rules: [newRule(CLUB_FIELD_DEFS)] })
    setError('')
  }

  // Start an email already addressed to this segment.
  //
  // This used to navigate to the Emails list carrying an `audienceId` in router
  // state that nothing on the other side ever read, so it dropped the officer on
  // a list of every email with the audience silently lost. It now creates the
  // draft the same way "+ New email" does — with the audience already set to
  // this segment — and opens it, which is what the button has always claimed to
  // do. Lists carries the same button, pointing at itself the same way.
  const emailThese = async () => {
    if (!draft?.id) return
    setBusy(true); setError('')
    try {
      const c = await api.commsCreateCampaign({
        subject: '', body_html: '',
        audience: { type: 'segment', segment_id: draft.id },
      })
      navigate(`/admin/comms/${c.id}`, { state: { skipIntro: true } })
    } catch (e) { setError(e.message); setBusy(false) }
  }

  if (intro.showing) {
    return (
      <BetterClubhouseLayout title="Segments"
        actions={<Button onClick={intro.dismiss}>Skip</Button>}>
        <ScreenIntro intro={INTROS.audiences} onContinue={intro.dismiss} onTurnOff={intro.turnOff} />
      </BetterClubhouseLayout>
    )
  }

  return (
    <BetterClubhouseLayout
      title="Segments"
      caption={`Resolved when you send · ${segments?.length || 0} saved`}
      onHelp={intro.reopen}
      actions={<Button variant="primary" onClick={startNew}>New segment</Button>}
      bare
    >
      <div className="flex flex-wrap items-stretch min-h-0 flex-1">
        {/* List pane */}
        <div className="ch-listpane bg-pb-surface overflow-y-auto p-2.5 pb-scroll">
          {segments == null ? <Empty>Loading…</Empty> : segments.length === 0 ? (
            <Empty>No segments yet. Start one and it counts as you build it.</Empty>
          ) : segments.map(a => {
            const n = (a.definition?.rules || []).length
            return (
              <ListRow
                key={a.id} name={a.name} avatar={false}
                sub={`${n} condition${n === 1 ? '' : 's'} · live`}
                figure={sizes[a.id] == null ? '—' : sizes[a.id]}
                selected={a.id === selId}
                onClick={() => setSelId(a.id)}
              />
            )
          })}

          <div className="mt-4 space-y-2.5 px-1">
            <Note toneKey="calm">
              A segment is a rule. For people picked by hand, use a list — both can be chosen as the audience
              when you write an email:{' '}
              <Link to="/admin/comms/contacts" className="underline" style={{ color: 'var(--pb-accent-ink)' }}>Contacts</Link>
              {' · '}
              <Link to="/admin/comms/lists" className="underline" style={{ color: 'var(--pb-accent-ink)' }}>Lists</Link>
            </Note>
            <Note title="Club scope only" toneKey="calm">
              These conditions read your own club's people — the directory, accounts, roster and email activity.
              Nothing here reaches outside the club.
            </Note>
          </div>
        </div>

        {/* Detail pane */}
        <div className="flex-1 min-w-[380px] overflow-y-auto px-6 py-[22px] pb-scroll" style={{ flexBasis: 390 }}>
          {!draft ? (
            <Empty>Pick a segment, or start a new one.</Empty>
          ) : (
            <>
              <div className="flex items-start gap-3.5 flex-wrap">
                <div className="flex-1 min-w-[220px]">
                  <TextInput
                    value={draft.name}
                    onChange={e => setDraft(d => ({ ...d, name: e.target.value }))}
                    placeholder="Name this segment"
                    className="!text-[22px] !font-bold !bg-transparent !border-transparent !px-0 !py-0 focus:!border-transparent"
                  />
                  <div className="text-[12.5px] text-pb-dim mt-1 leading-[1.6]">
                    Everyone who matches every condition below, worked out again each time you send.
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {draft.id && <Button size="sm" onClick={duplicate} disabled={busy}>Duplicate</Button>}
                  <Button size="sm" variant="primary" onClick={emailThese} disabled={!draft.id || !total}
                    title={draft.id ? '' : 'Save the segment first'}>
                    Email these {total} now
                  </Button>
                </div>
              </div>

              <div className="mt-6"><SegmentRules rules={draft.rules} setRules={fn => setDraft(d => ({ ...d, rules: typeof fn === 'function' ? fn(d.rules) : fn }))} opts={opts} /></div>

              <div
                className="mt-5 rounded-lg px-3.5 py-3 text-[13px]"
                style={{ background: TINT.panel, border: `1px solid ${TINT.border}` }}
              >
                {counting ? <span className="text-pb-dim">Working out who matches…</span> : (
                  <span className="text-pb-dim">
                    <b style={{ color: 'var(--pb-accent-ink)' }}>{total}</b> {total === 1 ? 'person matches' : 'people match'}
                    {' · '}<b style={{ color: 'var(--pb-positive-ink)' }}>{reachable}</b> reachable by email
                    {otherRoute > 0 && <> · <b style={{ color: '#f5b542' }}>{otherRoute}</b> need another route</>}
                  </span>
                )}
              </div>

              <div className="flex items-center gap-2 mt-4 flex-wrap">
                <Button variant="primary" onClick={save} disabled={busy}>{busy ? 'Saving…' : draft.id ? 'Save changes' : 'Save segment'}</Button>
                {draft.id && <Button variant="danger" size="sm" onClick={remove} disabled={busy}>Delete</Button>}
                {error && <span className="text-[12.5px] text-pb-red">{error}</span>}
              </div>

              <SectionHeading className="mt-8 mb-2.5">Who this is, right now</SectionHeading>
              <TableWrap>
                <TableHead cols={COLS} minWidth={MIN_W}>
                  <Cell head first>Person</Cell>
                  <Cell head>In the directory as</Cell>
                  <Cell head num>Balance</Cell>
                  <Cell head last>Reachable</Cell>
                </TableHead>
                {contacts.length === 0 ? (
                  <div style={{ minWidth: MIN_W }}><Empty>Nobody matches these conditions yet.</Empty></div>
                ) : contacts.slice(0, 50).map(c => {
                  const r = reachability(c)
                  return (
                    <TableRow key={c.id || c.email} cols={COLS} minWidth={MIN_W}>
                      <Cell first>
                        <div className="truncate text-pb-text">{c.name || c.email}</div>
                        {c.name && c.email && <div className="font-mono text-[9.5px] text-pb-faint truncate">{c.email}</div>}
                      </Cell>
                      <Cell className="text-pb-dim capitalize">{c.source || '—'}</Cell>
                      <Cell num className={c.balance > 0 ? 'text-pb-amber' : 'text-pb-faintest'}>
                        {c.balance == null ? '—' : money(c.balance)}
                      </Cell>
                      <Cell last><Badge toneKey={r.tone}>{r.label}</Badge></Cell>
                    </TableRow>
                  )
                })}
              </TableWrap>
              {contacts.length > 50 && (
                <div className="font-mono text-[10px] tracking-wide2 uppercase text-pb-faintest mt-2">
                  Showing the first 50 of {total}
                </div>
              )}
            </>
          )}
        </div>
      </div>
      <Toast toast={toast} onClose={() => setToast(null)} />
    </BetterClubhouseLayout>
  )
}
