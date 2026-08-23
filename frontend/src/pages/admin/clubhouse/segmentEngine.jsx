import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../../../lib/api'
import { Button, Caption, INPUT_CLS } from '../../../components/admin/ui'
import { RecordListPane, RecordTitleRow, CountBar, reachability } from './crudShell'
import { RuleRow, newRule } from '../bettercomms/segmentFields'

// The count bar and the reachability rule are shared furniture now — Lists and
// Emails report their own reach the same way. Re-exported so the two segment
// screens' imports are unchanged.
export { CountBar, reachability }

// The segment builder's engine and its field-agnostic furniture.
//
// There are two mounts of the segment builder and there always will be: a club
// building a segment of its own members, and BetterCricket building one of
// prospect clubs from the Clubs Directory. They run on the SAME endpoints — the
// server resolves against whichever organisation you are acting as — so the
// only real difference between them is which field vocabulary the rule rows
// offer, plus the copy and the columns that suit each one.
//
// ⚠ THE SCOPE RULE, and why this file has no opinion about it.
// Nothing here imports CLUB_FIELD_DEFS or DIRECTORY_FIELD_DEFS. `defs` is a
// required prop, and each screen passes the one constant it imports at the top
// of its own file. So the field set is still chosen by WHICH SCREEN IS MOUNTED
// — a decision made once in SegmentsRoute — and never by a flag read at render
// time. That is the property PROJECT_RULES.md is protecting: there is no code
// path in which a club screen can be talked into offering the directory fields.
// Keep it that way. If you ever find yourself adding an `isInternal` prop here,
// the thing you actually want is a third screen.

// The rule rows. `defs` is required — see the scope note above.
export function RuleBuilder({ defs, rules, setRules, opts, label = 'Match people where all of these are true' }) {
  // The rule row builds its own controls, so it takes the class rather than the
  // component. `!w-auto` because a condition is a row of three controls sized to
  // their content, not one full-width field.
  const inputCls = `${INPUT_CLS} !w-auto !py-1.5 !text-[13px]`
  return (
    <div>
      <Caption>{label}</Caption>
      <div className="mt-1.5">
        {rules.map((r, i) => (
          <RuleRow
            key={i} rule={r} defs={defs} opts={opts} inputCls={inputCls}
            onChange={nr => setRules(rs => rs.map((x, j) => (j === i ? nr : x)))}
            onRemove={() => setRules(rs => (rs.length > 1 ? rs.filter((_, j) => j !== i) : rs))}
          />
        ))}
      </div>
      <Button size="sm" onClick={() => setRules(rs => [...rs, newRule(defs)])} className="mt-1.5">
        + Add condition
      </Button>
    </div>
  )
}

// The saved-segment list, with whatever notes the screen wants underneath it.
// A segment's own row: its name, how many conditions it carries, and how many
// people it matches today.
export function SegmentListPane({ segments, sizes, selId, onSelect, emptyText, children, query = '' }) {
  const items = (segments || []).map(s => {
    const n = (s.definition?.rules || []).length
    return {
      id: s.id,
      name: s.name,
      sub: `${n} condition${n === 1 ? '' : 's'} · live`,
      figure: sizes[s.id] == null ? '—' : sizes[s.id],
    }
  })
  return (
    <RecordListPane
      items={items} loading={segments == null} selId={selId} onSelect={onSelect} emptyText={emptyText}
      query={query}
    >
      {children}
    </RecordListPane>
  )
}

// The name field and the actions that sit beside it.
export function SegmentTitleRow({ draft, setDraft, placeholder, blurb, busy, onDuplicate, onEmail, total, actions }) {
  return (
    <RecordTitleRow
      name={draft.name} onName={v => setDraft(d => ({ ...d, name: v }))}
      placeholder={placeholder} blurb={blurb}
      actions={<>
        {actions}
        {draft.id && <Button size="sm" onClick={onDuplicate} disabled={busy}>Duplicate</Button>}
        <Button size="sm" variant="primary" onClick={onEmail} disabled={!draft.id || !total}
          title={draft.id ? '' : 'Save the segment first'}>
          Email these {total} now
        </Button>
      </>}
    />
  )
}

// Everything a segment screen does: load the saved ones and their live sizes,
// hold the working draft, resolve it as you type, and save / duplicate / delete
// / start an email addressed to it.
//
// `defs` is the caller's field vocabulary — required, because a blank rule has
// to be built from it (`newRule` reads the first field's first operator, so an
// empty vocabulary throws). `presets` lets a caller open an unsaved draft from a
// deep link (Today's "Email these N" does this); `presetFrom` reads the key out
// of router state.
export function useSegments({ defs, presets = {}, presetFrom = () => null }) {
  const location = useLocation()
  const navigate = useNavigate()

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
      list.forEach(s => {
        api.commsPreviewSegment(s.definition || { match: 'all', rules: [] })
          .then(r => setSizes(x => ({ ...x, [s.id]: r.count })))
          .catch(() => {})
      })
    } catch (e) { setError(e.message); setSegments([]) }
  }, [])

  useEffect(() => { load(); api.commsSegmentOptions().then(setOpts).catch(() => {}) }, [load])

  // A deep link arrives asking for a kind of segment. Select a saved one that
  // already describes it, or open an unsaved draft carrying the rule — the
  // person pressed a button about a specific group, so landing them on an empty
  // builder would make them describe it again.
  const wanted = presetFrom(location.state || {})
  const seeded = useRef(false)
  useEffect(() => {
    if (!wanted || segments == null || seeded.current) return
    seeded.current = true
    const hit = segments.find(s =>
      (s.definition?.rules || []).some(r => r.field === presets[wanted]?.rules[0].field) ||
      s.name.toLowerCase().includes(wanted))
    if (hit) { setSelId(hit.id); return }
    const preset = presets[wanted]
    if (preset) { setSelId(null); setDraft({ id: null, name: preset.name, rules: preset.rules }) }
  }, [wanted, segments])   // eslint-disable-line react-hooks/exhaustive-deps

  const selected = useMemo(() => segments?.find(s => s.id === selId) || null, [segments, selId])

  // Editing a saved segment works on a draft, so a half-built rule never
  // reaches the server.
  //
  // It only ever LOADS a draft, and never clears one. It used to null the draft
  // whenever nothing was selected, which is exactly the state "New segment"
  // puts the screen in — so pressing it set a fresh draft, this effect then ran
  // because `selected` had just gone null, and wiped it in the same commit. The
  // button read as doing nothing at all, and a club with no saved segments yet
  // could never build its first one. Clearing is the caller's job (delete does
  // it explicitly), which is the only place it is actually wanted.
  useEffect(() => {
    if (!selected) return
    setDraft({
      id: selected.id,
      name: selected.name,
      rules: selected.definition?.rules?.length ? selected.definition.rules : [newRule(defs)],
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

  const save = async (noun = 'Segment') => {
    if (!draft?.name.trim()) { setError(`Give the ${noun.toLowerCase()} a name.`); return }
    setBusy(true); setError('')
    try {
      const saved = draft.id
        ? await api.commsUpdateSegment(draft.id, draft.name.trim(), definition)
        : await api.commsCreateSegment(draft.name.trim(), definition)
      setToast({ title: `${noun} saved`, body: `${draft.name.trim()} matches ${total} ${total === 1 ? 'contact' : 'contacts'} right now.` })
      await load()
      setSelId(saved.id)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const duplicate = async () => {
    if (!draft) return
    setBusy(true)
    try {
      const copy = await api.commsCreateSegment(`${draft.name} (copy)`, definition)
      await load(); setSelId(copy.id)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const remove = async (confirmText) => {
    if (!draft?.id || !window.confirm(confirmText)) return
    setBusy(true)
    try { await api.commsDeleteSegment(draft.id); setSelId(null); setDraft(null); await load() }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const startNew = () => {
    setSelId(null)
    setDraft({ id: null, name: '', rules: [newRule(defs)] })
    setError('')
  }

  // Start an email already addressed to this segment.
  //
  // This used to navigate to the Emails list carrying an id in router state that
  // nothing on the other side ever read, so it dropped you on a list of every
  // email with the segment silently lost. It now creates the draft the same way
  // "New email" does — with the audience already set to this segment — and opens
  // it. Lists carries the same button, pointing at itself the same way.
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

  return {
    segments, sizes, opts, selId, setSelId, draft, setDraft,
    contacts, total, reachable, otherRoute, counting,
    busy, error, toast, setToast,
    save, duplicate, remove, startNew, emailThese,
  }
}
