import { useState, useRef, useEffect, useMemo } from 'react'

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

// Searchable single-member picker. `members`: [{ member_id, full_name, ... }].
// `value` = member_id | null. onChange(member_id | null).
export function MemberSelect({ members = [], value, onChange, placeholder = 'Search for a member…' }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const wrap = useRef(null)
  useOutsideClose(wrap, () => setOpen(false), open)
  const selected = members.find(m => m.member_id === value)
  const matches = useMemo(() => {
    const n = q.trim().toLowerCase()
    const list = n ? members.filter(m => (m.full_name || '').toLowerCase().includes(n)) : members
    return list.slice(0, 30)
  }, [members, q])

  return (
    <div className="relative" ref={wrap}>
      {selected && !open ? (
        <div className={`${inp} flex items-center justify-between`}>
          <span className="truncate">{selected.full_name}</span>
          <button type="button" onClick={() => { onChange(null); setQ(''); setOpen(true) }}
            className="text-pb-faint hover:text-pb-red text-[11px] shrink-0 ml-2">clear</button>
        </div>
      ) : (
        <input className={inp} placeholder={placeholder} value={q} autoFocus={open}
          onFocus={() => setOpen(true)} onChange={e => { setQ(e.target.value); setOpen(true) }} />
      )}
      {open && (
        <div className="absolute z-30 mt-1 w-full pb-card bg-pb-surface max-h-56 overflow-y-auto shadow-xl">
          {matches.length === 0 && <div className="px-3 py-2 text-[12px] text-pb-faintest">No members match.</div>}
          {matches.map(m => (
            <button type="button" key={m.member_id} onClick={() => { onChange(m.member_id); setOpen(false); setQ('') }}
              className="block w-full text-left px-3 py-2 text-[12.5px] hover:bg-pb-surface2">
              {m.full_name}{m.is_linked ? <span className="text-pb-faint text-[10px]"> · player</span> : null}
            </button>
          ))}
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

  const matches = useMemo(() => {
    const n = q.trim().toLowerCase()
    if (!n) return members.slice(0, 20)
    return members.filter(m => (m.full_name || '').toLowerCase().includes(n)).slice(0, 20)
  }, [members, q])

  if (selectedMember) {
    return (
      <div className="relative" ref={wrap}>
        <div className={`${inp} flex items-center justify-between`}>
          <span className="truncate">{selectedMember.full_name}</span>
          <button type="button" onClick={() => onChange({ member_id: null, name: null })}
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
          {matches.map(m => (
            <button type="button" key={m.member_id} onClick={() => { onChange({ member_id: m.member_id, name: null }); setOpen(false) }}
              className="block w-full text-left px-3 py-2 text-[12.5px] hover:bg-pb-surface2">{m.full_name}</button>
          ))}
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
          {roles.length === 0 && <div className="px-3 py-2 text-[11.5px] text-pb-faintest">No roles yet — create one below.</div>}
          {roles.map(r => (
            <button type="button" key={r.id} onClick={() => toggle(r.id)}
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
