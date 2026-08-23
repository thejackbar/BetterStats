import { useState, useRef, useEffect, useMemo } from 'react'
import { api } from '../../../lib/api'

// Shared pickers for BetterClubManager. All use the module's input styling.
const inp = 'w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'

function useOutsideClose(ref, onClose, open) {
  useEffect(() => {
    if (!open) return
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) onClose() }
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey) }
  }, [open, ref, onClose])
}

// How many rows the dropdown draws at once. A club can hold well over a
// thousand people, and rendering all of them on focus janks the panel — but the
// old cap of 30 was low enough that an unfiltered list stopped inside the A's,
// which reads as "these are the only members" rather than "there are more".
// So: draw a useful number, and always SAY how many are behind them.
const SHOWN = 60

// A person's identity in this picker. Usually their member id; a club player
// with no member row yet has none, so they are keyed on the player instead.
const personKey = m => m.member_id || (m.player_id ? `player:${m.player_id}` : m.full_name)

// Every option row and clear button in this file goes through this.
//
// A picker must not sit inside a <label> (`Field composite` is how a screen
// says so), because a label forwards a click on any descendant to whichever
// labelable control the field holds at that moment. Choosing someone re-renders
// the field into "their name + a clear button", so the forwarded click lands on
// CLEAR and the choice is wiped before it can be seen — reported from Accounts
// → Add member, where picking a player left the field empty in Edge and Safari
// while the same click worked in Chrome. Whether it bites comes down to whether
// the re-render has committed by the time the browser forwards, which is why it
// looked like it depended on the person doing it.
//
// preventDefault() suppresses the forwarding, so the pickers hold their choice
// wherever they are mounted rather than relying on every screen getting the
// wrapper right.
const choose = fn => (e) => { e.preventDefault(); fn() }

// Searchable single-member picker. `members`: [{ member_id, full_name, ... }].
// `value` = member_id (or a `player:<id>` key) | null.
// onChange(key | null, person | null) — the second argument carries the whole
// row, which is what a caller needs to enrol a not-yet-a-member player.
export function MemberSelect({ members = [], value, onChange, placeholder = 'Search for a member…' }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const wrap = useRef(null)
  useOutsideClose(wrap, () => setOpen(false), open)
  // Guarded on `value` being set: a not-yet-enrolled player's member_id is
  // null, so an unguarded `m.member_id === value` matches them the moment
  // nothing is chosen, and the picker opens looking already answered.
  const selected = value ? members.find(m => personKey(m) === value || m.member_id === value) : null
  // Archived people have been removed from the club, so they are not offered
  // for anything new. One already chosen stays visible, or clearing a record
  // would be the only way to see what it says.
  const pool = useMemo(
    () => members.filter(m => !m.archived || personKey(m) === value),
    [members, value])
  const matches = useMemo(() => {
    const n = q.trim().toLowerCase()
    return n ? pool.filter(m => (m.full_name || '').toLowerCase().includes(n)) : pool
  }, [pool, q])
  const shown = matches.slice(0, SHOWN)
  const hidden = matches.length - shown.length

  return (
    <div className="relative" ref={wrap}>
      {selected && !open ? (
        <div className={`${inp} flex items-center justify-between`}>
          <span className="truncate">{selected.full_name}</span>
          <button type="button" onClick={choose(() => { onChange(null, null); setQ(''); setOpen(true) })}
            className="text-pb-faint hover:text-pb-red text-[11px] shrink-0 ml-2">clear</button>
        </div>
      ) : (
        <input className={inp} placeholder={placeholder} value={q} autoFocus={open}
          onFocus={() => setOpen(true)} onChange={e => { setQ(e.target.value); setOpen(true) }} />
      )}
      {open && (
        <div className="absolute z-30 mt-1 w-full pb-card bg-pb-surface max-h-56 overflow-y-auto shadow-xl">
          {matches.length === 0 && <div className="px-3 py-2 text-[12px] text-pb-faintest">No members match.</div>}
          {shown.map(m => (
            <button type="button" key={personKey(m)}
              onClick={choose(() => { onChange(personKey(m), m); setOpen(false); setQ('') })}
              className="block w-full text-left px-3 py-2 text-[12.5px] hover:bg-pb-surface2">
              {m.full_name}{m.is_linked ? <span className="text-pb-faint text-[10px]"> · player</span> : null}
            </button>
          ))}
          {hidden > 0 && (
            <div className="px-3 py-2 text-[11px] text-pb-faintest border-t pb-hairline sticky bottom-0 bg-pb-surface">
              {shown.length} of {matches.length} shown. Type a name to find the rest.
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// Type a name, the server finds the person. The same interaction as the meeting
// room's "who is doing it" field, and for the same reason: a club can hold well
// over a thousand people, and a dropdown that lists them all is both a big
// payload and unreadable — the first screenful never gets past the A's.
//
// Anyone in the club can be found, including a player who has never been
// enrolled as a member. Those come back with `member_id: null` and
// `needs_member: true`; the caller is responsible for enrolling them, so
// `onChange` hands back the whole person, not just an id.
export function PersonSearch({ value, onChange, placeholder = 'Type a name to search…', autoFocus = false }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState(null)
  const [more, setMore] = useState(false)
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState(false)
  const wrap = useRef(null)
  useOutsideClose(wrap, () => setOpen(false), open)

  useEffect(() => {
    const term = q.trim()
    if (!term) { setResults(null); setMore(false); return }
    // Debounced, and the response is dropped if the box has moved on — a slow
    // search for "sm" must not land on top of the results for "smith".
    let live = true
    setBusy(true)
    const t = setTimeout(() => {
      api.searchClubPeople(term)
        .then(d => { if (live) { setResults(d.people || []); setMore(!!d.more) } })
        .catch(() => { if (live) { setResults([]); setMore(false) } })
        .finally(() => { if (live) setBusy(false) })
    }, 220)
    return () => { live = false; clearTimeout(t) }
  }, [q])

  if (value) {
    return (
      <div className={`${inp} flex items-center justify-between`}>
        <span className="truncate">
          {value.full_name}
          {value.needs_member && <span className="text-pb-faint text-[10px]"> · not yet a member</span>}
        </span>
        <button type="button" onClick={choose(() => { onChange(null); setQ(''); setOpen(true) })}
          className="text-pb-faint hover:text-pb-red text-[11px] shrink-0 ml-2">clear</button>
      </div>
    )
  }

  return (
    <div className="relative" ref={wrap}>
      <input className={inp} placeholder={placeholder} value={q} autoFocus={autoFocus}
        onFocus={() => setOpen(true)} onChange={e => { setQ(e.target.value); setOpen(true) }} />
      {open && q.trim() !== '' && (
        <div className="absolute z-30 mt-1 w-full pb-card bg-pb-surface max-h-56 overflow-y-auto shadow-xl">
          {busy && results === null && (
            <div className="px-3 py-2 text-[12px] text-pb-faintest">Searching…</div>
          )}
          {results !== null && results.length === 0 && !busy && (
            <div className="px-3 py-2 text-[12px] text-pb-faintest">Nobody in the club matches that.</div>
          )}
          {(results || []).map(p => (
            <button type="button" key={p.member_id || `player:${p.player_id}`}
              onClick={choose(() => { onChange(p); setOpen(false); setQ('') })}
              className="block w-full text-left px-3 py-2 text-[12.5px] hover:bg-pb-surface2">
              {p.full_name}
              {p.needs_member
                ? <span className="text-pb-faint text-[10px]"> · player, not yet a member</span>
                : p.is_linked ? <span className="text-pb-faint text-[10px]"> · player</span> : null}
            </button>
          ))}
          {more && (
            <div className="px-3 py-2 text-[11px] text-pb-faintest border-t pb-hairline">
              More people match. Type a bit more of the name.
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// A club person picker that resolves to either a member (member_id) or a plain
// typed name. Value: { member_id, name }. onChange({ member_id, name }).
export function PersonPicker({ members = [], memberId, name, onChange, placeholder = 'Search members, or type a name…' }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState(name || '')
  const wrap = useRef(null)
  useOutsideClose(wrap, () => setOpen(false), open)
  const selectedMember = members.find(m => m.member_id === memberId)
  useEffect(() => { if (!memberId) setQ(name || '') }, [name, memberId])

  const pool = useMemo(
    () => members.filter(m => !m.archived || m.member_id === memberId),
    [members, memberId])
  const matches = useMemo(() => {
    const n = q.trim().toLowerCase()
    return n ? pool.filter(m => (m.full_name || '').toLowerCase().includes(n)) : pool
  }, [pool, q])
  const shown = matches.slice(0, SHOWN)
  const hidden = matches.length - shown.length

  if (selectedMember) {
    return (
      <div className="relative" ref={wrap}>
        <div className={`${inp} flex items-center justify-between`}>
          <span className="truncate">{selectedMember.full_name}</span>
          <button type="button" onClick={choose(() => onChange({ member_id: null, name: null }))}
            className="text-pb-faint hover:text-pb-red text-[11px] shrink-0 ml-2">clear</button>
        </div>
      </div>
    )
  }
  return (
    <div className="relative" ref={wrap}>
      <input className={inp} placeholder={placeholder} value={q}
        onFocus={() => setOpen(true)}
        onChange={e => { setQ(e.target.value); onChange({ member_id: null, name: e.target.value || null }); setOpen(true) }} />
      {open && (
        <div className="absolute z-30 mt-1 w-full pb-card bg-pb-surface max-h-56 overflow-y-auto shadow-xl">
          {shown.map(m => (
            <button type="button" key={m.member_id} onClick={choose(() => { onChange({ member_id: m.member_id, name: null }); setOpen(false) })}
              className="block w-full text-left px-3 py-2 text-[12.5px] hover:bg-pb-surface2">{m.full_name}</button>
          ))}
          {hidden > 0 && (
            <div className="px-3 py-2 text-[11px] text-pb-faintest border-t pb-hairline">
              {shown.length} of {matches.length} shown. Type a name to find the rest.
            </div>
          )}
          {q.trim() && (
            <div className="px-3 py-2 text-[11px] text-pb-faint border-t border-pb-hairline">Or use “{q.trim()}” as a typed name.</div>
          )}
        </div>
      )}
    </div>
  )
}

// Multi-select of roles with inline "create new role". `roles`: [{ id, title }].
// `value` = [roleId]. onChange(nextIds). onCreateRole(title) -> Promise<role>.
export function RoleMultiSelect({ roles = [], value = [], onChange, onCreateRole, label = 'Roles' }) {
  const [open, setOpen] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const wrap = useRef(null)
  useOutsideClose(wrap, () => setOpen(false), open)
  const selected = roles.filter(r => value.includes(r.id))

  const toggle = (id) => onChange(value.includes(id) ? value.filter(x => x !== id) : [...value, id])
  const create = async () => {
    const t = newTitle.trim()
    if (!t || !onCreateRole) return
    setBusy(true)
    try {
      const role = await onCreateRole(t)
      if (role?.id) onChange([...value, role.id])
      setNewTitle('')
    } finally { setBusy(false) }
  }

  return (
    <div className="relative" ref={wrap}>
      <div className={`${inp} min-h-[38px] flex flex-wrap gap-1 items-center cursor-text`} onClick={() => setOpen(true)}>
        {selected.length === 0 && <span className="text-pb-faintest">{label}…</span>}
        {selected.map(r => (
          <span key={r.id} className="inline-flex items-center gap-1 bg-pb-accent/15 text-pb-accent rounded px-1.5 py-0.5 text-[11px]">
            {r.title}
            <button type="button" onClick={(e) => { e.stopPropagation(); toggle(r.id) }} className="hover:text-pb-red">×</button>
          </span>
        ))}
      </div>
      {open && (
        <div className="absolute z-30 mt-1 w-full pb-card bg-pb-surface max-h-64 overflow-y-auto shadow-xl">
          {roles.length === 0 && <div className="px-3 py-2 text-[11.5px] text-pb-faintest">No roles yet, create one below.</div>}
          {roles.map(r => (
            <button type="button" key={r.id} onClick={choose(() => toggle(r.id))}
              className="flex items-center gap-2 w-full text-left px-3 py-1.5 text-[12.5px] hover:bg-pb-surface2">
              <span className={`w-3.5 h-3.5 rounded-sm border ${value.includes(r.id) ? 'bg-pb-accent border-pb-accent' : 'border-pb-hairline2'}`} />
              {r.title}{r.role_type_name ? <span className="text-pb-faint text-[10px]">· {r.role_type_name}</span> : null}
            </button>
          ))}
          {onCreateRole && (
            <div className="flex gap-1 p-2 border-t border-pb-hairline">
              <input className={`${inp} flex-1`} placeholder="New role title" value={newTitle}
                onChange={e => setNewTitle(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); create() } }} />
              <button type="button" onClick={create} disabled={busy || !newTitle.trim()}
                className="px-2.5 py-1 rounded text-[11px] bg-pb-accent text-black disabled:opacity-40 whitespace-nowrap">{busy ? '…' : '+ Add'}</button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
