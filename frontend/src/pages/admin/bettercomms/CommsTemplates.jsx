import { useState, useEffect, useCallback, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../../../lib/api'
import BetterCommsLayout from '../../../components/admin/BetterCommsLayout'
import { Button, Note, Empty, INPUT_CLS } from '../../../components/admin/ui'
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
  const fileRef = useRef(null)
  const editorRef = useRef(null)

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
          className={`${INPUT_CLS} flex-1 !w-auto min-w-[200px]`} />
        <input ref={fileRef} type="file" accept=".html,.htm,.rtf,text/html,text/rtf" onChange={importFile} className="hidden" />
        <Button onClick={() => fileRef.current?.click()}>Import .html</Button>
        {initial?.id && <Button variant="danger" onClick={remove} disabled={busy}>Delete</Button>}
        <Button variant="quiet" onClick={onCancel}>Cancel</Button>
        <Button variant="primary" onClick={save} disabled={busy}>{busy ? 'Saving…' : 'Save template'}</Button>
      </div>
      {err && <Note toneKey="block" className="mb-2">{err}</Note>}
      {notice && <Note toneKey="warn" className="mb-2">{notice}</Note>}

      <div className="text-[12px] text-pb-faintest mb-1.5 leading-[1.55]">
        Paste your own HTML, or import a file. Click a variable above to insert it wherever your cursor is. Preview
        adds the unsubscribe footer, exactly as a send would.
      </div>
      <EmailEditorTabs ref={editorRef} html={html} onChange={setHtml} onEnterPreview={onEnterPreview} height={680} />
    </div>
  )
}

export default function CommsTemplates() {
  const [templates, setTemplates] = useState(null)
  const [editing, setEditing] = useState(null) // {} new, object existing, null list
  const [error, setError] = useState('')
  const location = useLocation()

  const load = useCallback(() => {
    api.commsListTemplates().then(setTemplates).catch(e => { setError(e.message); setTemplates([]) })
  }, [])
  useEffect(() => { load() }, [load])

  // Clicking "Templates" in the sidebar while already on this page (e.g. mid-edit)
  // pushes a new history entry (location.key changes) but React Router doesn't
  // remount this component, so `editing` used to sit unchanged and nothing
  // appeared to happen. Treat any fresh navigation to this route as "back to
  // the list". Harmless on the very first mount, since editing is already null.
  useEffect(() => { setEditing(null) }, [location.key])

  const [duplicatingId, setDuplicatingId] = useState(null)

  const openExisting = async (t) => {
    try { setEditing(await api.commsGetTemplate(t.id)) }
    catch (e) { setError(e.message) }
  }
  const duplicate = async (t) => {
    setError(''); setDuplicatingId(t.id)
    try { await api.commsDuplicateTemplate(t.id); load() }
    catch (e) { setError(e.message) }
    finally { setDuplicatingId(null) }
  }
  const onSaved = () => { setEditing(null); load() }
  const onDeleted = () => { setEditing(null); load() }

  return (
    <BetterCommsLayout
      title="Templates"
      caption={editing ? 'Editing a template' : `Reusable email layouts · ${templates?.length ?? 0} saved`}
      actions={!editing && <Button variant="primary" onClick={() => setEditing({})}>New template</Button>}
    >
      {error && <Note toneKey="block" className="mb-4 max-w-2xl">{error}</Note>}

      {editing ? (
        <Editor initial={editing.id ? editing : null} onSaved={onSaved} onCancel={() => setEditing(null)} onDeleted={onDeleted} />
      ) : templates == null ? (
        <Empty>Loading…</Empty>
      ) : templates.length === 0 ? (
        <div className="pb-card p-8 text-center">
          <div className="font-display font-semibold text-[15.5px] text-pb-text mb-1">No templates yet</div>
          <div className="text-[13px] text-pb-dim mb-4">Start from scratch, paste HTML, or import a .html file.</div>
          <Button variant="primary" onClick={() => setEditing({})}>New template</Button>
        </div>
      ) : (
        <div className="pb-card overflow-hidden">
          {templates.map((t, i) => (
            <div key={t.id}
              className={`flex items-center justify-between gap-4 px-5 py-3.5 hover:bg-pb-surface2 transition-colors ${i > 0 ? 'pb-hairline-t' : ''}`}>
              <button onClick={() => openExisting(t)} className="flex-1 text-left min-w-0">
                <div className="text-pb-text text-[13.5px] font-semibold truncate">{t.name}</div>
              </button>
              <div className="flex items-center gap-2 shrink-0">
                <Button size="sm" variant="quiet" onClick={() => duplicate(t)} disabled={duplicatingId === t.id}>
                  {duplicatingId === t.id ? 'Duplicating…' : 'Duplicate'}
                </Button>
                <Button size="sm" onClick={() => openExisting(t)}>Edit</Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </BetterCommsLayout>
  )
}
