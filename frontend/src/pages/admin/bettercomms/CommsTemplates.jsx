import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from '../../../lib/api'
import BetterCommsLayout from '../../../components/admin/BetterCommsLayout'

const STARTER = `<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:24px 0;">
      <tr><td align="center">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#fff;border-radius:10px;overflow:hidden;">
          <tr><td style="padding:28px;color:#1f2937;font-size:15px;line-height:1.6;">
            <h1 style="margin:0 0 12px;font-size:20px;">Hi {{first_name}},</h1>
            <p>Write your message here. You can use {{club}} and other variables.</p>
            <p><a href="https://betterat.cricket" style="display:inline-block;background:#243352;color:#fff;text-decoration:none;padding:10px 18px;border-radius:6px;">A button</a></p>
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>`

function Editor({ initial, onSaved, onCancel, onDeleted }) {
  const [name, setName] = useState(initial?.name || '')
  const [html, setHtml] = useState(initial?.html ?? STARTER)
  const [preview, setPreview] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [vars, setVars] = useState({ is_marketing: false, variables: [] })
  const [copied, setCopied] = useState('')
  const fileRef = useRef(null)

  useEffect(() => { api.commsMergeVariables().then(setVars).catch(() => {}) }, [])

  const copyVar = (name) => {
    try { navigator.clipboard?.writeText(`{{${name}}}`) } catch { /* clipboard may be blocked */ }
    setCopied(name); setTimeout(() => setCopied(''), 1200)
  }

  // Live preview, debounced — rendered exactly as a send would (footer injected).
  useEffect(() => {
    let live = true
    const t = setTimeout(() => {
      api.commsPreviewTemplate(html).then(r => { if (live) setPreview(r.html || '') }).catch(() => {})
    }, 400)
    return () => { live = false; clearTimeout(t) }
  }, [html])

  const importFile = (e) => {
    const f = e.target.files?.[0]
    if (!f) return
    const reader = new FileReader()
    reader.onload = () => setHtml(String(reader.result || ''))
    reader.readAsText(f)
    e.target.value = '' // allow re-importing the same file
  }

  const save = async () => {
    if (!name.trim()) { setErr('Give the template a name.'); return }
    setBusy(true); setErr('')
    try {
      const saved = initial?.id
        ? await api.commsUpdateTemplate(initial.id, name.trim(), html)
        : await api.commsCreateTemplate(name.trim(), html)
      onSaved(saved)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const remove = async () => {
    if (!initial?.id || !window.confirm('Delete this template?')) return
    setBusy(true)
    try { await api.commsDeleteTemplate(initial.id); onDeleted(initial.id) }
    catch (e) { setErr(e.message); setBusy(false) }
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <input value={name} onChange={e => setName(e.target.value)} placeholder="Template name"
          className="flex-1 min-w-[200px] px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline text-sm" />
        <input ref={fileRef} type="file" accept=".html,text/html" onChange={importFile} className="hidden" />
        <button onClick={() => fileRef.current?.click()} className="px-3 py-2 rounded text-sm border pb-hairline text-pb-text hover:bg-pb-surface2">Import .html</button>
        {initial?.id && <button onClick={remove} disabled={busy} className="px-3 py-2 rounded text-sm text-pb-faint hover:text-pb-red">Delete</button>}
        <button onClick={onCancel} className="px-3 py-2 rounded text-sm text-pb-faint hover:text-pb-text">Cancel</button>
        <button onClick={save} disabled={busy}
          className="px-3 py-2 rounded text-sm font-medium text-white disabled:opacity-60" style={{ background: 'var(--pb-accent)' }}>
          {busy ? 'Saving…' : 'Save template'}
        </button>
      </div>
      {err && <div className="text-pb-red text-xs mb-2">{err}</div>}

      <div className="pb-card p-3 mb-3">
        <div className="text-pb-faintest text-xs uppercase tracking-wide2 mb-2">Merge variables — click to copy</div>
        <div className="flex flex-wrap gap-1.5">
          {(vars.variables || []).filter(v => !v.marketing_only || vars.is_marketing).map(v => (
            <button key={v.name} onClick={() => copyVar(v.name)} title={v.desc}
              className="font-mono text-[11px] border pb-hairline rounded px-2 py-1 hover:bg-pb-surface2"
              style={{ color: 'var(--pb-accent)' }}>
              {copied === v.name ? 'copied!' : `{{${v.name}}}`}
            </button>
          ))}
        </div>
        {vars.is_marketing && (
          <div className="text-pb-faintest text-xs mt-2">
            The club / association / utm_code variables resolve to each recipient club's own details from the Clubs Directory.
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div>
          <div className="text-pb-faintest text-xs mb-1">HTML — paste your own, or import a file. Use {'{{first_name}}'}, {'{{club_name}}'} etc.</div>
          <textarea value={html} onChange={e => setHtml(e.target.value)} rows={20} spellCheck={false}
            className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline font-mono text-xs" />
        </div>
        <div>
          <div className="text-pb-faintest text-xs mb-1">Preview (the unsubscribe footer is added automatically)</div>
          <iframe title="preview" srcDoc={preview} className="w-full rounded border pb-hairline bg-white" style={{ height: 480 }} />
        </div>
      </div>
    </div>
  )
}

export default function CommsTemplates() {
  const [templates, setTemplates] = useState(null)
  const [editing, setEditing] = useState(null) // {} new, object existing, null list
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api.commsListTemplates().then(setTemplates).catch(e => { setError(e.message); setTemplates([]) })
  }, [])
  useEffect(() => { load() }, [load])

  const openExisting = async (t) => {
    try { setEditing(await api.commsGetTemplate(t.id)) }
    catch (e) { setError(e.message) }
  }
  const onSaved = () => { setEditing(null); load() }
  const onDeleted = () => { setEditing(null); load() }

  return (
    <BetterCommsLayout
      title="Templates"
      actions={!editing && (
        <button onClick={() => setEditing({})}
          className="px-3 py-1.5 rounded text-sm font-medium text-white" style={{ background: 'var(--pb-accent)' }}>
          + New template
        </button>
      )}
    >
      {error && <div className="pb-card p-3 mb-4 text-pb-red text-sm">{error}</div>}

      {editing ? (
        <Editor initial={editing.id ? editing : null} onSaved={onSaved} onCancel={() => setEditing(null)} onDeleted={onDeleted} />
      ) : templates == null ? (
        <div className="text-pb-faint text-sm">Loading…</div>
      ) : templates.length === 0 ? (
        <div className="pb-card p-8 text-center">
          <div className="text-pb-text font-medium mb-1">No templates yet</div>
          <div className="text-pb-faint text-sm mb-4">Start from scratch, paste HTML, or import a .html file.</div>
          <button onClick={() => setEditing({})}
            className="px-4 py-2 rounded text-sm font-medium text-white" style={{ background: 'var(--pb-accent)' }}>
            + New template
          </button>
        </div>
      ) : (
        <div className="pb-card overflow-hidden">
          {templates.map((t, i) => (
            <button key={t.id} onClick={() => openExisting(t)}
              className={`w-full text-left flex items-center justify-between gap-4 px-5 py-3.5 hover:bg-pb-surface2 transition-colors ${i > 0 ? 'pb-hairline-t' : ''}`}>
              <div className="text-pb-text text-sm truncate">{t.name}</div>
              <span className="text-pb-faint text-xs shrink-0">Edit →</span>
            </button>
          ))}
        </div>
      )}
    </BetterCommsLayout>
  )
}
