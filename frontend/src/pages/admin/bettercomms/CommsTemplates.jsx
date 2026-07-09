import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from '../../../lib/api'
import BetterCommsLayout from '../../../components/admin/BetterCommsLayout'
import EmailEditorTabs from '../../../components/admin/EmailEditorTabs'

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

// macOS TextEdit (and some editors) save "Rich Text" as RTF even when the file
// is named .html — the bytes start with {\rtf and wrap the real HTML in RTF
// control words, which is what was corrupting the import. These two helpers
// detect that and recover the plain-text HTML the file was meant to hold.
function looksLikeRtf(s) {
  return /^\s*\{\\rtf/i.test(s)
}
function rtfToText(rtf) {
  let s = rtf
  // Drop the RTF header destinations (font + colour tables and other \* groups).
  s = s.replace(/\{\\fonttbl[^{}]*\}/gi, '')
  s = s.replace(/\{\\colortbl[^{}]*\}/gi, '')
  s = s.replace(/\{\\\*[^{}]*\}/g, '')
  // Protect the three literal escapes before stripping control words.
  s = s.replace(/\\\\/g, '').replace(/\\\{/g, '').replace(/\\\}/g, '')
  // Hex (\'xx) and unicode (\uN) escapes → the character they stand for.
  s = s.replace(/\\'([0-9a-fA-F]{2})/g, (_, h) => String.fromCharCode(parseInt(h, 16)))
  s = s.replace(/\\u(-?\d+)\s?\??/g, (_, n) => {
    let code = parseInt(n, 10); if (code < 0) code += 65536
    return String.fromCharCode(code)
  })
  // Paragraph / line breaks → newline; \pard (paragraph reset) is not a break.
  s = s.replace(/\\pard?\b ?/g, (m) => (m.indexOf('pard') >= 0 ? '' : '\n'))
  s = s.replace(/\\line\b ?/g, '\n')
  // A backslash at the end of a wrapped source line is also a line break.
  s = s.replace(/\\\r?\n/g, '\n')
  // Strip any remaining control words and their single trailing space.
  s = s.replace(/\\[a-zA-Z]+-?\d* ?/g, '')
  // Remaining braces are RTF group delimiters (literal braces were protected).
  s = s.replace(/[{}]/g, '')
  // Restore the protected literals.
  s = s.replace(//g, '\\').replace(//g, '{').replace(//g, '}')
  return s.trim()
}

function Editor({ initial, onSaved, onCancel, onDeleted }) {
  const [name, setName] = useState(initial?.name || '')
  const [html, setHtml] = useState(initial?.html ?? STARTER)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [notice, setNotice] = useState('')
  const [vars, setVars] = useState({ is_marketing: false, variables: [] })
  const [copied, setCopied] = useState('')
  const fileRef = useRef(null)
  const editorRef = useRef(null)

  useEffect(() => { api.commsMergeVariables().then(setVars).catch(() => {}) }, [])

  const copyVar = (name) => {
    try { navigator.clipboard?.writeText(`{{${name}}}`) } catch { /* clipboard may be blocked */ }
    setCopied(name); setTimeout(() => setCopied(''), 1200)
  }

  // Rendered exactly as a send would (footer injected) — fetched when the
  // Preview tab is opened rather than on every keystroke.
  const onEnterPreview = async ({ html: currentHtml }) => {
    const r = await api.commsPreviewTemplate(currentHtml)
    return { html: r.html || '', total: 1, index: 0 }
  }

  const importFile = (e) => {
    const f = e.target.files?.[0]
    if (!f) return
    const reader = new FileReader()
    reader.onload = () => {
      let content = String(reader.result || '')
      setErr(''); setNotice('')
      if (looksLikeRtf(content)) {
        const recovered = rtfToText(content)
        if (/<html|<!doctype|<body|<table|<div/i.test(recovered)) {
          content = recovered
          setNotice('That file was Rich Text (RTF), not HTML — TextEdit does this even when the file ends in .html. I recovered the HTML; check the preview. To avoid it, in TextEdit pick Format → Make Plain Text before saving, or save from a code editor.')
        } else {
          setErr('That file is Rich Text (RTF), not HTML, and I could not recover usable HTML from it. In TextEdit choose Format → Make Plain Text and save again, or use a plain-text / code editor.')
          return
        }
      }
      setHtml(content)
    }
    reader.readAsText(f)
    e.target.value = '' // allow re-importing the same file
  }

  const save = async () => {
    if (!name.trim()) { setErr('Give the template a name.'); return }
    setBusy(true); setErr('')
    try {
      const finalHtml = editorRef.current?.flush() ?? html
      const saved = initial?.id
        ? await api.commsUpdateTemplate(initial.id, name.trim(), finalHtml)
        : await api.commsCreateTemplate(name.trim(), finalHtml)
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
        <input ref={fileRef} type="file" accept=".html,.htm,.rtf,text/html,text/rtf" onChange={importFile} className="hidden" />
        <button onClick={() => fileRef.current?.click()} className="px-3 py-2 rounded text-sm border pb-hairline text-pb-text hover:bg-pb-surface2">Import .html</button>
        {initial?.id && <button onClick={remove} disabled={busy} className="px-3 py-2 rounded text-sm text-pb-faint hover:text-pb-red">Delete</button>}
        <button onClick={onCancel} className="px-3 py-2 rounded text-sm text-pb-faint hover:text-pb-text">Cancel</button>
        <button onClick={save} disabled={busy}
          className="px-3 py-2 rounded text-sm font-medium text-white disabled:opacity-60" style={{ background: 'var(--pb-accent)' }}>
          {busy ? 'Saving…' : 'Save template'}
        </button>
      </div>
      {err && <div className="text-pb-red text-xs mb-2">{err}</div>}
      {notice && <div className="text-pb-amber text-xs mb-2">{notice}</div>}

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

      <div className="text-pb-faintest text-xs mb-1">
        HTML — paste your own, or import a file. Use {'{{first_name}}'}, {'{{club_name}}'} etc. Switching out of HTML mode
        tidies the code automatically; Preview adds the unsubscribe footer, exactly as a send would.
      </div>
      <EmailEditorTabs ref={editorRef} html={html} onChange={setHtml} onEnterPreview={onEnterPreview} height={480} />
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
