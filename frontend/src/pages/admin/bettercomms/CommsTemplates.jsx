import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../../../lib/api'
import BetterCommsLayout from '../../../components/admin/BetterCommsLayout'
import { Button, Note, Empty, Toast, SectionHeading } from '../../../components/admin/ui'
import EmailEditorTabs from '../../../components/admin/EmailEditorTabs'
import { CrudPanes, RecordListPane, DetailPane, RecordTitleRow, CountBar, SaveRow } from '../clubhouse/crudShell'
import ScreenIntro, { useScreenIntro, INTROS } from '../clubhouse/intro'

// Templates — the club's reusable email layouts.
//
// Same CRUD shape as Segments and Lists: the saved ones in the rail on the
// left, the one in hand beside it, its name edited where it is read, Save and
// Delete in the same place. It used to swap the entire page for an editor, so
// the only way back to the other templates was Cancel, and there was no way to
// see what else the club had while working on one.

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
  // (Private-use code points, so they cannot collide with the file's own text.)
  s = s.replace(/\\\\/g, '\uE000').replace(/\\\{/g, '\uE001').replace(/\\\}/g, '\uE002')
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
  s = s.replace(/\uE000/g, '\\').replace(/\uE001/g, '{').replace(/\uE002/g, '}')
  return s.trim()
}

export default function CommsTemplates() {
  const intro = useScreenIntro('templates')
  const location = useLocation()
  const [templates, setTemplates] = useState(null)
  const [selId, setSelId] = useState(null)
  const [draft, setDraft] = useState(null)      // { id, name, html }
  const [loadingDraft, setLoadingDraft] = useState(false)
  const [busy, setBusy] = useState(false)
  const [duplicatingId, setDuplicatingId] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [toast, setToast] = useState(null)
  // Bumped whenever the HTML is replaced wholesale (a different template
  // selected, a file imported). EmailEditorTabs seeds its design iframe once on
  // mount, so a new body only lands if the editor remounts.
  const [editorKey, setEditorKey] = useState(0)
  const fileRef = useRef(null)
  const editorRef = useRef(null)

  const load = useCallback(async () => {
    try {
      const rows = await api.commsListTemplates()
      setTemplates(rows)
      setSelId(cur => cur || rows[0]?.id || null)
      return rows
    } catch (e) { setError(e.message); setTemplates([]); return [] }
  }, [])
  useEffect(() => { load() }, [load])

  // Clicking "Templates" in the sidebar while already here pushes a new history
  // entry (location.key changes) without remounting, so anything half-edited
  // used to sit there looking like the click did nothing. Treat a fresh
  // navigation to this route as "back to the top of the list".
  useEffect(() => { setSelId(null); setDraft(null); setError(''); setNotice('') }, [location.key])

  // The list rows carry no HTML, so open the full record when one is picked.
  // Like the segment builder this only ever LOADS a draft, never clears one —
  // clearing on "nothing selected" is the state "New template" puts the screen
  // in, and would wipe the fresh draft in the same commit.
  useEffect(() => {
    if (!selId) return
    let live = true
    setLoadingDraft(true); setError(''); setNotice('')
    api.commsGetTemplate(selId)
      .then(t => { if (!live) return; setDraft({ id: t.id, name: t.name || '', html: t.html ?? '' }); setEditorKey(k => k + 1) })
      .catch(e => { if (live) setError(e.message) })
      .finally(() => { if (live) setLoadingDraft(false) })
    return () => { live = false }
  }, [selId])

  const startNew = () => {
    setSelId(null)
    setDraft({ id: null, name: '', html: STARTER })
    setEditorKey(k => k + 1)
    setError(''); setNotice('')
  }

  const importFile = (e) => {
    const f = e.target.files?.[0]
    if (!f) return
    const reader = new FileReader()
    reader.onload = () => {
      let content = String(reader.result || '')
      setError(''); setNotice('')
      if (looksLikeRtf(content)) {
        const recovered = rtfToText(content)
        if (/<html|<!doctype|<body|<table|<div/i.test(recovered)) {
          content = recovered
          setNotice('That file was Rich Text (RTF), not HTML — TextEdit does this even when the file ends in .html. I recovered the HTML; check the preview. To avoid it, in TextEdit pick Format → Make Plain Text before saving, or save from a code editor.')
        } else {
          setError('That file is Rich Text (RTF), not HTML, and I could not recover usable HTML from it. In TextEdit choose Format → Make Plain Text and save again, or use a plain-text / code editor.')
          return
        }
      }
      setDraft(d => ({ ...d, html: content }))
      setEditorKey(k => k + 1)
    }
    reader.readAsText(f)
    e.target.value = '' // allow re-importing the same file
  }

  const save = async () => {
    const name = (draft?.name || '').trim()
    if (!name) { setError('Give the template a name.'); return }
    setBusy(true); setError('')
    try {
      const finalHtml = editorRef.current?.flush() ?? draft.html
      const saved = draft.id
        ? await api.commsUpdateTemplate(draft.id, name, finalHtml)
        : await api.commsCreateTemplate(name, finalHtml)
      setToast({ title: draft.id ? 'Template saved' : 'Template created', body: `${name} is ready to use on an email.` })
      await load()
      setSelId(saved.id)
      // Selecting the id it already had won't re-run the loader, so keep the
      // draft in step with what was just written.
      setDraft({ id: saved.id, name, html: finalHtml })
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const remove = async () => {
    if (!draft?.id) return
    if (!window.confirm(`Delete the template "${draft.name}"? Emails already sent using it are unaffected.`)) return
    setBusy(true); setError('')
    try {
      await api.commsDeleteTemplate(draft.id)
      setSelId(null); setDraft(null)
      await load()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const duplicate = async () => {
    if (!draft?.id) return
    setError(''); setDuplicatingId(draft.id)
    try {
      const copy = await api.commsDuplicateTemplate(draft.id)
      await load()
      if (copy?.id) setSelId(copy.id)
    } catch (e) { setError(e.message) } finally { setDuplicatingId(null) }
  }

  // Rendered exactly as a send would (footer injected) — fetched when the
  // Preview tab is opened rather than on every keystroke.
  const onEnterPreview = async ({ html: currentHtml }) => {
    const r = await api.commsPreviewTemplate(currentHtml)
    return { html: r.html || '', total: 1, index: 0 }
  }

  const items = useMemo(() => (templates || []).map(t => ({
    id: t.id, name: t.name, sub: 'Email layout',
  })), [templates])

  if (intro.showing) {
    return (
      <BetterCommsLayout title="Templates" actions={<Button onClick={intro.dismiss}>Skip</Button>}>
        <ScreenIntro intro={INTROS.templates} onContinue={intro.dismiss} onTurnOff={intro.turnOff} />
      </BetterCommsLayout>
    )
  }

  return (
    <BetterCommsLayout
      title="Templates"
      caption={`Reusable email layouts · ${templates?.length ?? 0} saved`}
      onHelp={intro.reopen}
      actions={<Button variant="primary" onClick={startNew}>New template</Button>}
      bare
    >
      <CrudPanes>
        <RecordListPane
          items={items} loading={templates == null} selId={selId} onSelect={setSelId}
          emptyText="No templates yet. Start from scratch, paste HTML, or import a .html file."
        >
          <Note toneKey="calm">
            A template is a layout, not a message. Pick one while writing an email and it fills in the
            message for you to edit — the email keeps its own copy, so changing a template later never
            rewrites something already sent.
          </Note>
        </RecordListPane>

        <DetailPane>
          {!draft && error && <Note toneKey="block" className="mb-4">{error}</Note>}

          {!draft ? (
            loadingDraft ? <Empty>Loading…</Empty> : <Empty>Pick a template, or start a new one.</Empty>
          ) : (
            <>
              <RecordTitleRow
                name={draft.name} onName={v => setDraft(d => ({ ...d, name: v }))}
                placeholder="Name this template"
                blurb="Reusable HTML the club's emails are built from. Preview renders it exactly as a send would."
                actions={<>
                  <input ref={fileRef} type="file" accept=".html,.htm,.rtf,text/html,text/rtf"
                    onChange={importFile} className="hidden" />
                  <Button size="sm" onClick={() => fileRef.current?.click()}>Import .html</Button>
                  {draft.id && (
                    <Button size="sm" onClick={duplicate} disabled={busy || duplicatingId === draft.id}>
                      {duplicatingId === draft.id ? 'Duplicating…' : 'Duplicate'}
                    </Button>
                  )}
                </>}
              />

              <CountBar>
                <span className="text-pb-dim">
                  Paste your own HTML or import a file. Click a variable above the editor to insert it where
                  your cursor is, and Preview adds the unsubscribe footer exactly as a send would.
                </span>
              </CountBar>

              <SaveRow
                onSave={save} busy={busy} error={error}
                saveLabel={busy ? 'Saving…' : draft.id ? 'Save changes' : 'Save template'}
                onDelete={draft.id ? remove : null}
              />

              {notice && <Note toneKey="warn" className="mt-3">{notice}</Note>}

              <SectionHeading className="mt-8 mb-2.5">The layout itself</SectionHeading>
              <EmailEditorTabs
                key={editorKey} ref={editorRef} html={draft.html}
                onChange={v => setDraft(d => ({ ...d, html: v }))}
                onEnterPreview={onEnterPreview} height={680}
              />
            </>
          )}
        </DetailPane>
      </CrudPanes>
      <Toast toast={toast} onClose={() => setToast(null)} />
    </BetterCommsLayout>
  )
}
