import { useState, useEffect, useCallback, useMemo } from 'react'
import { api } from '../../../lib/api'
import BetterCommsLayout from '../../../components/admin/BetterCommsLayout'
import { FACETS, matchesQuery, matchesFilters, facetOptionsFrom, emptyFilters, MultiSelect, matchesSuppressed, SuppressedToggle,
  emptyModes, matchesModes, anyMode, DirectoryFilterChips } from './audience'

function Stat({ label, value, tone }) {
  return (
    <div className="pb-card px-4 py-3 text-center">
      <div className={`text-xl font-display font-bold ${tone || 'text-pb-text'}`}>{value}</div>
      <div className="text-pb-faintest text-xs">{label}</div>
    </div>
  )
}

export default function CommsContacts() {
  const [data, setData] = useState({ contacts: [], summary: {} })
  const [query, setQuery] = useState('')
  const [filters, setFilters] = useState(emptyFilters)
  const [modes, setModes] = useState(emptyModes)
  const [supp, setSupp] = useState('all')
  const [fnFind, setFnFind] = useState('')
  const [fnReplace, setFnReplace] = useState('')
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState('')
  const [showImport, setShowImport] = useState(false)
  const [importText, setImportText] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [newName, setNewName] = useState('')
  const [detailId, setDetailId] = useState(null)

  // Load the full contact set once; search, directory facets and the suppressed
  // filter all run client-side (same model as Lists), so the facet options
  // reflect the whole audience rather than the current search.
  const reload = useCallback(async () => {
    const d = await api.commsListContacts({})
    setData(d)
  }, [])

  useEffect(() => { reload().catch(e => setMsg({ kind: 'error', text: e.message })).finally(() => setLoading(false)) }, [reload])

  const facetOptions = useMemo(() => facetOptionsFrom(data.contacts), [data.contacts])
  const showDirChips = useMemo(() => (data.contacts || []).some(c => c.club), [data.contacts])
  // Live count of contacts whose {{name}} matches the Find value (blank Find = the
  // no-name rows; otherwise an exact, case-insensitive match), so the button says
  // how many it will touch.
  const fnMatchCount = useMemo(() => {
    const f = fnFind.trim().toLowerCase()
    return (data.contacts || []).filter(c => {
      const n = (c.name || '').trim().toLowerCase()
      return f === '' ? n === '' : n === f
    }).length
  }, [data.contacts, fnFind])
  const q = query.trim().toLowerCase()
  const visible = useMemo(() =>
    (data.contacts || []).filter(c => matchesQuery(c, q) && matchesFilters(c, filters) && matchesModes(c, modes) && matchesSuppressed(c, supp)),
    [data.contacts, q, filters, modes, supp])
  const activeFilters = !!q || FACETS.some(f => filters[f.key].length) || anyMode(modes) || supp !== 'all'

  const run = async (key, fn, okText) => {
    setBusy(key); setMsg(null)
    try { const r = await fn(); await reload(); if (okText) setMsg({ kind: 'ok', text: okText(r) }) }
    catch (e) { setMsg({ kind: 'error', text: e.message }) }
    finally { setBusy('') }
  }

  const syncFromClub = () => run('sync', () => api.commsSyncFromClub(),
    r => `Synced from club — ${r.added} added, ${r.updated} updated.`)

  const doImport = () => run('import', async () => {
    const r = await api.commsImportContacts(importText)
    setImportText(''); setShowImport(false)
    return r
  }, r => `Imported — ${r.added} added, ${r.updated} updated${r.invalid ? `, ${r.invalid} invalid` : ''}.`)

  const addContact = () => {
    if (!newEmail.trim()) return
    run('add', async () => { const r = await api.commsCreateContact(newEmail.trim(), newName.trim() || null); setNewEmail(''); setNewName(''); return r },
      () => 'Contact added.')
  }

  const applyFirstName = () => {
    const rep = fnReplace.trim()
    if (!rep) return
    const find = fnFind.trim()
    const target = find ? `name "${find}"` : 'no name'
    if (!window.confirm(`Set {{first_name}} to "${rep}" for the ${fnMatchCount} contact${fnMatchCount === 1 ? '' : 's'} with ${target}?`)) return
    run('setfn', async () => { const r = await api.commsFirstNameFindReplace(find, rep); setFnFind(''); setFnReplace(''); return r },
      r => `Set {{first_name}} to "${r.replace}" for ${r.updated} contact${r.updated === 1 ? '' : 's'}.`)
  }

  const toggleSub = (c) => run(`t${c.id}`, () => api.commsUpdateContact(c.id, { subscribed: !c.subscribed }))
  const del = (c) => { if (window.confirm(`Remove ${c.email}?`)) run(`d${c.id}`, () => api.commsDeleteContact(c.id)) }

  const s = data.summary || {}

  return (
    <BetterCommsLayout
      title="Contacts"
      actions={
        <button onClick={syncFromClub} disabled={busy === 'sync'}
          className="px-3 py-1.5 rounded text-sm border pb-hairline text-pb-text hover:bg-pb-surface2 disabled:opacity-60">
          {busy === 'sync' ? 'Syncing…' : 'Sync from club'}
        </button>
      }
    >
      {msg && <div className={`pb-card p-3 mb-4 text-sm ${msg.kind === 'error' ? 'text-pb-red' : 'text-green-500'}`}>{msg.text}</div>}

      <div className="grid grid-cols-4 gap-3 mb-4">
        <Stat label="contacts" value={s.total ?? 0} />
        <Stat label="subscribed" value={s.subscribed ?? 0} tone="text-green-500" />
        <Stat label="unsubscribed" value={s.unsubscribed ?? 0} tone="text-pb-faint" />
        <Stat label="bounced" value={s.bounced ?? 0} tone="text-pb-red" />
        {(s.excluded ?? 0) > 0 && <Stat label="excluded" value={s.excluded} tone="text-pb-red" />}
      </div>

      {/* Add + import */}
      <div className="pb-card p-4 mb-4">
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex-1 min-w-[160px]">
            <label className="block text-xs text-pb-faint mb-1">Email</label>
            <input value={newEmail} onChange={e => setNewEmail(e.target.value)} placeholder="person@example.com" type="email"
              className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm" />
          </div>
          <div className="flex-1 min-w-[140px]">
            <label className="block text-xs text-pb-faint mb-1">Name (optional)</label>
            <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Jane Smith"
              className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm" />
          </div>
          <button onClick={addContact} disabled={busy === 'add'}
            className="px-3 py-2 rounded text-sm font-medium text-white disabled:opacity-60" style={{ background: 'var(--pb-accent)' }}>
            Add
          </button>
          <button onClick={() => setShowImport(v => !v)} className="px-3 py-2 rounded text-sm border pb-hairline text-pb-text hover:bg-pb-surface2">
            Import…
          </button>
        </div>
        {showImport && (
          <div className="mt-3">
            <label className="block text-xs text-pb-faint mb-1">Paste emails — one per line (<code>email</code>, <code>Name &lt;email&gt;</code> or <code>name,email</code>)</label>
            <textarea value={importText} onChange={e => setImportText(e.target.value)} rows={6}
              className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm font-mono" />
            <div className="flex gap-2 mt-2">
              <button onClick={doImport} disabled={busy === 'import' || !importText.trim()}
                className="px-3 py-2 rounded text-sm font-medium text-white disabled:opacity-60" style={{ background: 'var(--pb-accent)' }}>
                {busy === 'import' ? 'Importing…' : 'Import'}
              </button>
              <button onClick={() => { setShowImport(false); setImportText('') }} className="px-3 py-2 rounded text-sm text-pb-faint hover:text-pb-text">Cancel</button>
            </div>
          </div>
        )}
      </div>

      <input value={query} onChange={e => setQuery(e.target.value)}
        placeholder="Search name, email, club, association, country, UTM code, state or website…"
        className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm mb-2" />
      <div className="flex flex-wrap items-center gap-2 mb-3">
        {FACETS.filter(f => facetOptions[f.key].length > 0).map(f => (
          <MultiSelect key={f.key} label={f.label} options={facetOptions[f.key]}
            selected={filters[f.key]} onChange={(v) => setFilters(s => ({ ...s, [f.key]: v }))} />
        ))}
        <SuppressedToggle value={supp} onChange={setSupp} />
        {activeFilters && (
          <button onClick={() => { setQuery(''); setFilters(emptyFilters()); setModes(emptyModes()); setSupp('all') }}
            className="text-xs text-pb-faint hover:text-pb-accent underline underline-offset-2">Clear filters</button>
        )}
        <span className="text-pb-faintest text-xs ml-auto">{visible.length} shown</span>
      </div>
      {showDirChips && (
        <div className="flex flex-wrap items-center gap-1.5 mb-3">
          <span className="text-pb-faintest text-[11px] uppercase tracking-wide2 mr-1">Directory</span>
          <DirectoryFilterChips modes={modes} onChange={setModes} />
          <span className="text-pb-faintest text-[10px] ml-1">tap once to exclude, twice to include</span>
        </div>
      )}

      {/* Bulk first-name find/replace: match {{name}} → set {{first_name}}. */}
      {showDirChips && (
        <div className="pb-card p-3 mb-4">
          <div className="text-xs text-pb-faint mb-2">
            Set <code className="text-pb-accent">{'{{first_name}}'}</code> by matching <code className="text-pb-accent">{'{{name}}'}</code>.
            Leave <strong className="text-pb-text">Find</strong> blank to match contacts with no name, or type a name to match it exactly.
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <div className="flex-1 min-w-[160px]">
              <label className="block text-xs text-pb-faint mb-1">Find (in {'{{name}}'}, blank = no name)</label>
              <input value={fnFind} onChange={e => setFnFind(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && applyFirstName()}
                placeholder="(blank)"
                className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm" />
            </div>
            <div className="flex-1 min-w-[160px]">
              <label className="block text-xs text-pb-faint mb-1">Replace (set {'{{first_name}}'} to)</label>
              <input value={fnReplace} onChange={e => setFnReplace(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && applyFirstName()}
                placeholder="e.g. Committee Members"
                className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm" />
            </div>
            <button onClick={applyFirstName} disabled={busy === 'setfn' || !fnReplace.trim() || fnMatchCount === 0}
              className="px-3 py-2 rounded text-sm font-medium text-white disabled:opacity-60" style={{ background: 'var(--pb-accent)' }}>
              {busy === 'setfn' ? 'Setting…' : `Set First Name (${fnMatchCount})`}
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="text-pb-faint text-sm">Loading…</div>
      ) : data.contacts.length === 0 ? (
        <div className="pb-card p-8 text-center text-pb-faint text-sm">
          No contacts yet. Use <strong className="text-pb-text">Sync from club</strong> to pull emails already on file, or add/import above.
        </div>
      ) : visible.length === 0 ? (
        <div className="pb-card p-8 text-center text-pb-faint text-sm">No contacts match your search.</div>
      ) : (
        <div className="pb-card overflow-hidden">
          {visible.map((c, i) => {
            // A nameless directory contact still needs to read as its club + email,
            // not a bare address: label falls back name → club → email, and the sub
            // line always carries whatever of club/email isn't already the label.
            const primary = c.name || c.club || c.email
            const sub = [c.club, c.email].filter(v => v && v !== primary).join(' · ')
            return (
            <div key={c.id} className={`flex items-center justify-between gap-3 px-4 py-2.5 ${i > 0 ? 'pb-hairline-t' : ''}`}>
              <button onClick={() => setDetailId(c.id)} className="min-w-0 text-left hover:opacity-80" title="View details & merge variables">
                <div className="text-pb-text text-sm truncate">{primary}</div>
                {sub && <div className="text-pb-faintest text-xs truncate">{sub}</div>}
              </button>
              <div className="flex items-center gap-2 shrink-0">
                <span className="font-mono text-[9px] uppercase tracking-wide2 text-pb-faintest">{c.source}</span>
                {c.bounced && <span className="font-mono text-[9px] uppercase text-pb-red border border-pb-red/40 rounded px-1.5 py-0.5">bounced</span>}
                {c.complained && <span className="font-mono text-[9px] uppercase text-pb-red border border-pb-red/40 rounded px-1.5 py-0.5">complaint</span>}
                {c.excluded && <span className="font-mono text-[9px] uppercase text-pb-red border border-pb-red/40 rounded px-1.5 py-0.5" title="Excluded from outreach by BetterCricket">excluded</span>}
                {c.suppressed && !c.bounced && !c.complained && !c.excluded && <span className="font-mono text-[9px] uppercase text-pb-red border border-pb-red/40 rounded px-1.5 py-0.5" title="Globally suppressed">supp</span>}
                <button onClick={() => toggleSub(c)} disabled={busy === `t${c.id}`}
                  className={`font-mono text-[10px] uppercase tracking-wide2 border rounded px-2 py-0.5 disabled:opacity-50 ${
                    c.subscribed ? 'text-green-500 border-green-500/40' : 'text-pb-faint border-pb-faint/30'}`}>
                  {c.subscribed ? 'subscribed' : 'unsubscribed'}
                </button>
                <button onClick={() => del(c)} className="text-pb-faintest hover:text-pb-red text-sm px-1" title="Remove">✕</button>
              </div>
            </div>
            )
          })}
        </div>
      )}

      {detailId && <ContactDetailModal id={detailId} onClose={() => setDetailId(null)}
                                       onSaved={() => reload().catch(() => {})} />}
    </BetterCommsLayout>
  )
}

// name/email live in their own columns; the rest of the editable keys are
// per-contact merge_vars overrides. unsubscribe_url is auto and read-only.
const COLUMN_KEYS = ['name', 'email']

export function ContactDetailModal({ id, onClose, onSaved }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState('')
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({})
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => {
    api.commsContactDetail(id).then(setD).catch(e => setErr(e.message))
  }, [id])
  useEffect(() => { load() }, [load])

  const copy = (name) => {
    const token = `{{${name}}}`
    try { navigator.clipboard?.writeText(token) } catch { /* clipboard may be blocked */ }
    setCopied(name)
    setTimeout(() => setCopied(''), 1200)
  }

  const startEdit = () => {
    // Seed the form: columns from their stored value, override keys from the raw
    // stored override (so a blank field falls back to the shown default).
    const f = { name: d.name || '', email: d.email || '' }
    for (const k of (d.editable || [])) {
      if (!COLUMN_KEYS.includes(k)) f[k] = (d.overrides || {})[k] || ''
    }
    setForm(f); setErr(''); setEditing(true)
  }

  const save = async () => {
    setSaving(true); setErr('')
    const merge_vars = {}
    for (const k of (d.editable || [])) {
      if (!COLUMN_KEYS.includes(k)) merge_vars[k] = (form[k] || '').trim()
    }
    try {
      await api.commsUpdateContact(id, {
        name: (form.name || '').trim(),
        email: (form.email || '').trim(),
        merge_vars,
      })
      setEditing(false)
      load()
      onSaved && onSaved()
    } catch (e) { setErr(e.message || 'Could not save.') } finally { setSaving(false) }
  }

  const mc = d?.marketing_club
  const editableSet = new Set(d?.editable || [])

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center p-4 overflow-y-auto" style={{ background: 'rgba(0,0,0,0.5)' }} onClick={onClose}>
      <div className="bg-pb-surface border pb-hairline rounded-lg shadow-xl w-full max-w-lg mt-[8vh]" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-3 pb-hairline-b">
          <div className="text-pb-text font-medium truncate">{d?.name || d?.email || 'Contact'}</div>
          <div className="flex items-center gap-2">
            {d && !editing && (
              <button onClick={startEdit} className="text-xs px-2 py-1 rounded border pb-hairline text-pb-text hover:bg-pb-surface2">Edit</button>
            )}
            <button onClick={onClose} className="text-pb-faint hover:text-pb-text text-lg px-1">✕</button>
          </div>
        </div>
        <div className="p-5">
          {err && <div className="text-pb-red text-sm mb-2">{err}</div>}
          {!d && !err && <div className="text-pb-faint text-sm">Loading…</div>}
          {d && (
            <>
              <div className="text-sm text-pb-text mb-1">{d.email}</div>
              <div className="flex flex-wrap gap-1.5 mb-4">
                <span className="font-mono text-[9px] uppercase tracking-wide2 text-pb-faintest border pb-hairline rounded px-1.5 py-0.5">{d.source}</span>
                <span className={`font-mono text-[9px] uppercase tracking-wide2 border rounded px-1.5 py-0.5 ${d.subscribed ? 'text-green-500 border-green-500/40' : 'text-pb-faint border-pb-faint/30'}`}>{d.subscribed ? 'subscribed' : 'unsubscribed'}</span>
                {d.bounced && <span className="font-mono text-[9px] uppercase text-pb-red border border-pb-red/40 rounded px-1.5 py-0.5">bounced</span>}
                {d.complained && <span className="font-mono text-[9px] uppercase text-pb-red border border-pb-red/40 rounded px-1.5 py-0.5">complaint</span>}
                {d.excluded && <span className="font-mono text-[9px] uppercase text-pb-red border border-pb-red/40 rounded px-1.5 py-0.5">excluded</span>}
              </div>

              {mc && !editing && (
                <div className="pb-card p-3 mb-4">
                  <div className="text-pb-faintest text-xs uppercase tracking-wide2 mb-2">From the Clubs Directory</div>
                  {[['Club', mc.name], ['Association', mc.association], ['Country', mc.country], ['UTM code', mc.utm_code], ['State', mc.state], ['Website', mc.website]].map(([k, v]) => v ? (
                    <div key={k} className="flex justify-between gap-3 py-0.5 text-sm">
                      <span className="text-pb-faint">{k}</span>
                      <span className="text-pb-text truncate">{v}</span>
                    </div>
                  ) : null)}
                </div>
              )}

              <div className="text-pb-faintest text-xs uppercase tracking-wide2 mb-2">
                Merge variables {editing ? '— edit each value' : '— click to copy'}
              </div>
              <div className="text-pb-faintest text-xs mb-2">
                {editing
                  ? 'Set any value for this contact. Leave blank to use the default shown.'
                  : 'Drop these into a template; this is how they resolve for this contact.'}
              </div>

              {editing ? (
                <div className="space-y-2">
                  {Object.keys(d.variables || {}).map((k) => {
                    const canEdit = editableSet.has(k)
                    return (
                      <div key={k} className="flex items-center gap-2">
                        <span className="font-mono text-xs shrink-0 w-32 truncate" style={{ color: 'var(--pb-accent)' }} title={`{{${k}}}`}>{`{{${k}}}`}</span>
                        {canEdit ? (
                          <input
                            value={form[k] ?? ''}
                            onChange={e => setForm(f => ({ ...f, [k]: e.target.value }))}
                            placeholder={String(d.variables[k] || '')}
                            className="flex-1 min-w-0 px-2 py-1 rounded bg-pb-surface2 text-pb-text border pb-hairline text-xs" />
                        ) : (
                          <span className="flex-1 text-pb-faintest text-xs italic truncate">{String(d.variables[k] || '')} (auto)</span>
                        )}
                      </div>
                    )
                  })}
                  <div className="flex gap-2 pt-2">
                    <button onClick={save} disabled={saving}
                      className="px-3 py-1.5 rounded text-sm font-medium text-white disabled:opacity-60" style={{ background: 'var(--pb-accent)' }}>
                      {saving ? 'Saving…' : 'Save'}
                    </button>
                    <button onClick={() => { setEditing(false); setErr('') }} className="px-3 py-1.5 rounded text-sm text-pb-faint hover:text-pb-text">Cancel</button>
                  </div>
                </div>
              ) : (
                <div>
                  {Object.entries(d.variables || {}).map(([k, v]) => (
                    <button key={k} onClick={() => copy(k)} title="Copy"
                      className="w-full flex items-center justify-between gap-3 py-1.5 pb-hairline-t text-left hover:bg-pb-surface2 rounded px-1">
                      <span className="font-mono text-xs text-pb-accent shrink-0" style={{ color: 'var(--pb-accent)' }}>{`{{${k}}}`}</span>
                      <span className="text-pb-faint text-xs truncate">{String(v) || <span className="text-pb-faintest italic">empty</span>}</span>
                      <span className="text-pb-faintest text-[10px] shrink-0 w-12 text-right">{copied === k ? 'copied' : ''}</span>
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
