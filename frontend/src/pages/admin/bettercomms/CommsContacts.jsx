import { useState, useEffect, useCallback } from 'react'
import { api } from '../../../lib/api'
import BetterCommsLayout from '../../../components/admin/BetterCommsLayout'

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
  const [loading, setLoading] = useState(true)
  const [msg, setMsg] = useState(null)
  const [busy, setBusy] = useState('')
  const [showImport, setShowImport] = useState(false)
  const [importText, setImportText] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [newName, setNewName] = useState('')

  const reload = useCallback(async (q = query) => {
    const d = await api.commsListContacts({ query: q })
    setData(d)
  }, [query])

  useEffect(() => { reload('').catch(e => setMsg({ kind: 'error', text: e.message })).finally(() => setLoading(false)) }, [])

  // refetch on search (debounced)
  useEffect(() => {
    const t = setTimeout(() => { reload(query).catch(() => {}) }, 250)
    return () => clearTimeout(t)
  }, [query, reload])

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

      <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search contacts…"
        className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm mb-3" />

      {loading ? (
        <div className="text-pb-faint text-sm">Loading…</div>
      ) : data.contacts.length === 0 ? (
        <div className="pb-card p-8 text-center text-pb-faint text-sm">
          No contacts yet. Use <strong className="text-pb-text">Sync from club</strong> to pull emails already on file, or add/import above.
        </div>
      ) : (
        <div className="pb-card overflow-hidden">
          {data.contacts.map((c, i) => (
            <div key={c.id} className={`flex items-center justify-between gap-3 px-4 py-2.5 ${i > 0 ? 'pb-hairline-t' : ''}`}>
              <div className="min-w-0">
                <div className="text-pb-text text-sm truncate">{c.name || c.email}</div>
                {c.name && <div className="text-pb-faintest text-xs truncate">{c.email}</div>}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="font-mono text-[9px] uppercase tracking-wide2 text-pb-faintest">{c.source}</span>
                {c.bounced && <span className="font-mono text-[9px] uppercase text-pb-red border border-pb-red/40 rounded px-1.5 py-0.5">bounced</span>}
                <button onClick={() => toggleSub(c)} disabled={busy === `t${c.id}`}
                  className={`font-mono text-[10px] uppercase tracking-wide2 border rounded px-2 py-0.5 disabled:opacity-50 ${
                    c.subscribed ? 'text-green-500 border-green-500/40' : 'text-pb-faint border-pb-faint/30'}`}>
                  {c.subscribed ? 'subscribed' : 'unsubscribed'}
                </button>
                <button onClick={() => del(c)} className="text-pb-faintest hover:text-pb-red text-sm px-1" title="Remove">✕</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </BetterCommsLayout>
  )
}
