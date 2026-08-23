import { useRef, useState, useEffect, forwardRef, useImperativeHandle } from 'react'
import { api } from '../../lib/api'
import { isFullHtmlDoc, tidyHtml, wrapFragmentForEditing, serializeIframeDocument } from '../../lib/htmlEmailFormat'

// Shared HTML / Design (WYSIWYG) / Preview editor for the BetterComms Template
// and Email compose pages. One big full-width window shows whichever mode is
// active — Design and Preview sit as tabs on the left, HTML is a tab on the
// far right (deliberately set apart — it's the "raw code" escape hatch, not a
// parallel view). Design mode edits the real DOM directly inside an iframe
// (contentDocument.designMode) so existing table-based email layouts
// round-trip untouched — a schema-based rich-text editor would
// normalise/strip that markup. Switching mode, saving, or sending all tidy
// the HTML via js-beautify.
//
// Parents that persist content (Save/Send/Test) MUST call ref.flush() first
// and use its return value — it synchronously returns the latest content
// (design-iframe edits read back, or tidied code) rather than relying on the
// onChange callback's state update having landed yet.
//
// `simple` (default false) is for a caller that only wants "edit the text,
// or preview it" — the Sales Workspace's Send Email form, where the body is
// already a finished, real email (contact/club names already substituted
// server-side) and a rep shouldn't be restructuring its HTML or inserting
// {{merge}} tokens meant for a club-wide campaign. It hides the HTML/code
// tab and the whole formatting toolbar (bold/headings/lists/links/images/
// table rows) and skips the Insert-variable bar entirely — Design mode
// still edits the real DOM via the same iframe, just with no chrome around
// it. BetterComms' own Template/Compose screens keep the full editor.
const EmailEditorTabs = forwardRef(function EmailEditorTabs(
  { html, onChange, onEnterPreview, height = 640, subject, onSubjectChange, subjectInputRef, simple = false },
  ref
) {
  const [mode, setMode] = useState('design') // 'design' | 'preview' | 'code'
  // Only offered when the parent hands us a subject field to target (Compose has
  // one, Templates doesn't) — lets the Insert bar direct a click at the Subject
  // input instead of the message body.
  const canTargetSubject = !!(onSubjectChange && subjectInputRef)
  const [insertTarget, setInsertTarget] = useState('body') // 'body' | 'subject'
  const [designSrcDoc, setDesignSrcDoc] = useState(null)
  const [designIsFullDoc, setDesignIsFullDoc] = useState(true)
  const designFrameRef = useRef(null)
  const codeRef = useRef(null)
  const codeDirtyRef = useRef(false)
  const liveSyncTimerRef = useRef(null)
  const [preview, setPreview] = useState({ loading: false, html: '', subject: '', total: 1, index: 0, label: '', error: '' })
  const [vars, setVars] = useState({ is_marketing: false, variables: [] })
  const [justInserted, setJustInserted] = useState('')

  // Our own undo/redo stack for Design mode. The browser's native
  // designMode undo (Cmd/Ctrl+Z) is unreliable inside an iframe — it loses
  // history across focus changes (e.g. every window.prompt() from Link/
  // Image/Button) and doesn't cover our own scripted DOM edits (table row
  // insert/delete, link-URL editing) at all, since those never go through
  // execCommand. Snapshots are the editable body's innerHTML only — the
  // wrapper <head>/<style> never changes during editing.
  const historyRef = useRef([])
  const historyIndexRef = useRef(-1)
  const [historyFlags, setHistoryFlags] = useState({ canUndo: false, canRedo: false })
  const syncHistoryFlags = () => setHistoryFlags({
    canUndo: historyIndexRef.current > 0,
    canRedo: historyIndexRef.current < historyRef.current.length - 1,
  })

  useEffect(() => { if (!simple) api.commsMergeVariables().then(setVars).catch(() => {}) }, [simple])

  // Design mode defaults to open on mount, but designSrcDoc is otherwise only
  // populated by changeMode's explicit "switching into design" transition —
  // which never fires for the initial mode, since there's nothing to switch
  // from. Without this, the iframe starts empty and flush() (e.g. clicking
  // the HTML tab) reads that emptiness straight back into `html`, silently
  // wiping real content. Only runs while srcDoc is still unset, so it's a
  // no-op once changeMode has populated it for real.
  useEffect(() => {
    if (mode !== 'design' || designSrcDoc !== null) return
    const isFull = isFullHtmlDoc(html)
    setDesignIsFullDoc(isFull)
    setDesignSrcDoc(isFull ? html : wrapFragmentForEditing(html))
  }, [mode, html, designSrcDoc])

  // Raw (untidied) read of the design iframe's current content — cheap enough
  // to call on every keystroke for a debounced "keep parent state roughly in
  // sync" pass, separate from the tidied read used when actually leaving mode.
  const readDesign = () => {
    const frame = designFrameRef.current
    if (!frame?.contentDocument) return html
    const doc = frame.contentDocument
    return designIsFullDoc ? serializeIframeDocument(doc) : (doc.body ? doc.body.innerHTML : html)
  }

  // Captures the editable body as a new undo step. Consecutive duplicate
  // snapshots are skipped (typing that produces no net change) and any
  // undone "redo" branch is discarded, matching normal undo-stack behaviour.
  const pushHistory = () => {
    const doc = designFrameRef.current?.contentDocument
    if (!doc?.body) return
    const snapshot = doc.body.innerHTML
    const trimmed = historyRef.current.slice(0, historyIndexRef.current + 1)
    if (trimmed[trimmed.length - 1] === snapshot) { historyRef.current = trimmed; return }
    trimmed.push(snapshot)
    if (trimmed.length > 100) trimmed.shift()
    historyRef.current = trimmed
    historyIndexRef.current = trimmed.length - 1
    syncHistoryFlags()
  }

  const restoreHistory = (index) => {
    const doc = designFrameRef.current?.contentDocument
    const snapshot = historyRef.current[index]
    if (!doc?.body || snapshot === undefined) return
    doc.body.innerHTML = snapshot
    historyIndexRef.current = index
    syncHistoryFlags()
    onChange(readDesign())
  }

  const undo = () => { if (historyIndexRef.current > 0) restoreHistory(historyIndexRef.current - 1) }
  const redo = () => { if (historyIndexRef.current < historyRef.current.length - 1) restoreHistory(historyIndexRef.current + 1) }

  const flushDesign = () => (mode === 'design' ? tidyHtml(readDesign()) : html)

  const flush = () => {
    let next = html
    if (mode === 'design') {
      next = flushDesign()
    } else if (mode === 'code' && codeDirtyRef.current) {
      next = tidyHtml(html)
    }
    codeDirtyRef.current = false
    if (next !== html) onChange(next)
    return next
  }

  const insertAtCursor = (text) => {
    const el = codeRef.current
    if (!el) { onChange((html || '') + text); return }
    const start = el.selectionStart ?? html.length
    const end = el.selectionEnd ?? html.length
    const next = html.slice(0, start) + text + html.slice(end)
    codeDirtyRef.current = true
    onChange(next)
    const pos = start + text.length
    requestAnimationFrame(() => {
      el.focus()
      try { el.setSelectionRange(pos, pos) } catch { /* ignore */ }
    })
  }

  const insertIntoSubject = (token) => {
    const el = subjectInputRef?.current
    const current = subject || ''
    if (!el) { onSubjectChange(current + token); return }
    const start = el.selectionStart ?? current.length
    const end = el.selectionEnd ?? current.length
    const next = current.slice(0, start) + token + current.slice(end)
    onSubjectChange(next)
    const pos = start + token.length
    requestAnimationFrame(() => {
      el.focus()
      try { el.setSelectionRange(pos, pos) } catch { /* ignore */ }
    })
  }

  const insertVariable = (name) => {
    const token = `{{${name}}}`
    if (canTargetSubject && insertTarget === 'subject') {
      insertIntoSubject(token)
    } else if (mode === 'design') {
      exec('insertText', token)
    } else if (mode === 'code') {
      insertAtCursor(token)
    } else {
      onChange((html || '') + token) // preview has nothing focused to insert into
    }
    setJustInserted(name)
    setTimeout(() => setJustInserted(''), 900)
  }

  useImperativeHandle(ref, () => ({ flush, insertVariable }))

  const runPreview = async (currentHtml, index) => {
    if (!onEnterPreview) return
    setPreview(p => ({ ...p, loading: true, error: '' }))
    try {
      const r = await onEnterPreview({ html: currentHtml, index })
      setPreview({
        loading: false,
        html: r.html || '',
        subject: r.subject || '',
        total: r.total || 1,
        index: r.index ?? index,
        label: r.label || '',
        error: '',
      })
    } catch (e) {
      setPreview(p => ({ ...p, loading: false, error: e.message || 'Could not render preview.' }))
    }
  }

  const changeMode = (next) => {
    if (next === mode) return
    const flushed = flush()
    if (next === 'design') {
      const isFull = isFullHtmlDoc(flushed)
      setDesignIsFullDoc(isFull)
      setDesignSrcDoc(isFull ? flushed : wrapFragmentForEditing(flushed))
    }
    setMode(next)
    if (next === 'preview') runPreview(flushed, 0)
  }

  const pagePreview = (delta) => {
    const total = preview.total || 1
    const next = Math.max(0, Math.min(total - 1, (preview.index || 0) + delta))
    if (next === preview.index) return
    runPreview(html, next)
  }

  const onFrameLoad = () => {
    const doc = designFrameRef.current?.contentDocument
    if (!doc) return
    try { doc.designMode = 'on' } catch { /* not editable in this browser */ }
    historyRef.current = [doc.body ? doc.body.innerHTML : '']
    historyIndexRef.current = 0
    syncHistoryFlags()
    // Debounced, untidied sync back to parent state while typing — keeps
    // Send-button enablement and unknown-variable warnings live without
    // touching designSrcDoc (which would disrupt the iframe/cursor). Also
    // where typing gets coalesced into an undo step, on the same pause.
    doc.addEventListener('input', () => {
      clearTimeout(liveSyncTimerRef.current)
      liveSyncTimerRef.current = setTimeout(() => { onChange(readDesign()); pushHistory() }, 400)
    })
    // Our own undo/redo — see historyRef's comment for why the native
    // designMode undo stack isn't trusted here.
    doc.addEventListener('keydown', (e) => {
      if (!(e.metaKey || e.ctrlKey)) return
      const key = e.key.toLowerCase()
      if (key === 'z' && !e.shiftKey) { e.preventDefault(); undo() }
      else if ((key === 'z' && e.shiftKey) || key === 'y') { e.preventDefault(); redo() }
    })
  }

  const exec = (cmd, val) => {
    const frame = designFrameRef.current
    const doc = frame?.contentDocument
    if (!doc) return
    frame.contentWindow?.focus()
    doc.execCommand(cmd, false, val)
    pushHistory()
  }

  const escapeHtml = (s) =>
    String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

  // The <a> the caret/selection is currently inside, if any — lets Link edit
  // an existing link's href in place (including a Button's) instead of only
  // ever being able to wrap fresh text in a new one.
  const linkAtSelection = () => {
    const doc = designFrameRef.current?.contentDocument
    const node = doc?.getSelection?.()?.anchorNode
    if (!node) return null
    const el = node.nodeType === 3 ? node.parentElement : node
    return el?.closest ? el.closest('a') : null
  }

  const insertLink = () => {
    const frame = designFrameRef.current
    const doc = frame?.contentDocument
    if (!doc) return
    frame.contentWindow?.focus()
    const existing = linkAtSelection()
    const url = window.prompt(
      existing ? 'Edit link URL:' : 'Link URL: select some text first, or click inside an existing link/button to edit it:',
      existing?.getAttribute('href') || 'https://'
    )
    if (!url) return
    if (existing) {
      existing.setAttribute('href', url)
      onChange(readDesign())
      pushHistory()
    } else if (doc.getSelection().isCollapsed) {
      window.alert('Select some text first, then click Link to turn it into a link.')
    } else {
      doc.execCommand('createLink', false, url)
      pushHistory()
    }
  }
  const insertImage = () => {
    const url = window.prompt('Image URL:')
    if (url) exec('insertImage', url)
  }
  const insertButton = () => {
    const url = window.prompt('Button link URL:', 'https://')
    if (!url) return
    const label = window.prompt('Button text:', 'Button text') || 'Button text'
    exec('insertHTML', `<a href="${escapeHtml(url)}" style="display:inline-block;background:#243352;color:#fff;text-decoration:none;padding:10px 18px;border-radius:6px;">${escapeHtml(label)}</a>`)
  }

  // Table helpers operate on the raw DOM (there's no cross-browser execCommand
  // for row insert/delete) — they mutate directly, then push the result back
  // through the same sync path onFrameLoad's 'input' listener uses, since a
  // script-driven mutation never fires that event on its own.
  const rowAtSelection = () => {
    const doc = designFrameRef.current?.contentDocument
    const node = doc?.getSelection?.()?.anchorNode
    if (!node) return null
    const el = node.nodeType === 3 ? node.parentElement : node
    return el?.closest ? el.closest('tr') : null
  }

  const BORDER_BOTTOM_RE = /(?:^|;)\s*border-bottom\s*:\s*([^;]+)/i

  // Our email templates commonly divide table rows with a border-bottom on
  // every row EXCEPT the last (avoids doubling up with the table's own
  // border/radius) — e.g. the newsletter's Results table. Cloning a row to
  // insert a new one naively copies whichever row it was cloned from
  // verbatim, so inserting after what used to be the last (borderless) row
  // left both it and the new row without a divider between them. This
  // re-derives the convention from whatever border style already appears
  // anywhere in the table, then re-applies it to every row but the true
  // last one — a no-op on tables that don't use a divider border at all.
  const reflowRowBorders = (table) => {
    const rows = Array.from(table.rows)
    if (rows.length < 2) return
    let dividerValue = null
    for (const row of rows) {
      const style = row.querySelector('td, th')?.getAttribute('style') || ''
      const m = style.match(BORDER_BOTTOM_RE)
      if (m) { dividerValue = m[1].trim(); break }
    }
    if (!dividerValue) return
    rows.forEach((row, i) => {
      const isLast = i === rows.length - 1
      row.querySelectorAll('td, th').forEach(cell => {
        let style = cell.getAttribute('style') || ''
        const hasBorder = BORDER_BOTTOM_RE.test(style)
        if (isLast && hasBorder) {
          style = style.replace(BORDER_BOTTOM_RE, '').replace(/;\s*;/g, ';').trim()
        } else if (!isLast && !hasBorder) {
          style = style.trim()
          if (style && !style.endsWith(';')) style += ';'
          style += ` border-bottom:${dividerValue};`
        }
        cell.setAttribute('style', style)
      })
    })
  }

  const insertTableRow = (after) => {
    const row = rowAtSelection()
    if (!row) { window.alert('Click inside a table cell first, then Row +.'); return }
    const clone = row.cloneNode(true)
    clone.querySelectorAll('td, th').forEach(cell => { cell.innerHTML = '&nbsp;' })
    if (after) row.after(clone)
    else row.before(clone)
    const table = row.closest('table')
    if (table) reflowRowBorders(table)
    onChange(readDesign())
    pushHistory()
  }
  const deleteTableRow = () => {
    const row = rowAtSelection()
    if (!row) { window.alert('Click inside a table row first, then Row −.'); return }
    const table = row.closest('table')
    if (table && table.rows.length <= 1) {
      window.alert("Can't delete the only row in this table.")
      return
    }
    row.remove()
    if (table) reflowRowBorders(table)
    onChange(readDesign())
    pushHistory()
  }

  const varList = (vars.variables || []).filter(v => !v.marketing_only || vars.is_marketing)

  return (
    <div>
      {varList.length > 0 && (
        <div className="pb-card p-2 mb-2">
          {canTargetSubject && (
            <div className="flex items-center gap-1.5 mb-1.5">
              <span className="text-pb-faintest text-[10px] uppercase tracking-wide2">Insert into:</span>
              {[['subject', 'Subject'], ['body', 'Message']].map(([v, label]) => (
                <button key={v} type="button" onClick={() => setInsertTarget(v)}
                  className={`px-2 py-0.5 rounded text-[11px] border pb-hairline ${insertTarget === v ? 'text-white' : 'text-pb-faint hover:text-pb-text'}`}
                  style={insertTarget === v ? { background: 'var(--pb-accent)', borderColor: 'var(--pb-accent)' } : {}}>
                  {label}
                </button>
              ))}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-pb-faintest text-xs uppercase tracking-wide2 mr-0.5">Insert:</span>
            {varList.map(v => (
              <button key={v.name} type="button" onClick={() => insertVariable(v.name)} title={v.desc}
                className="font-mono text-[11px] border pb-hairline rounded px-2 py-1 hover:bg-pb-surface2"
                style={{ color: 'var(--pb-accent)' }}>
                {justInserted === v.name ? 'inserted!' : `{{${v.name}}}`}
              </button>
            ))}
          </div>
          {vars.is_marketing && (
            <div className="text-pb-faintest text-xs mt-1.5">
              The club / association / utm_code variables resolve to each recipient club's own details from the Clubs Directory.
            </div>
          )}
        </div>
      )}

      <div className="flex items-center gap-1 mb-2">
        {[['design', 'Design'], ['preview', 'Preview']].map(([m, label]) => (
          <button key={m} type="button" onClick={() => changeMode(m)}
            className={`px-3 py-1.5 rounded text-xs font-medium border pb-hairline ${mode === m ? 'text-white' : 'text-pb-faint hover:text-pb-text'}`}
            style={mode === m ? { background: 'var(--pb-accent)', borderColor: 'var(--pb-accent)' } : {}}>
            {label}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2">
          {mode === 'preview' && (
            <button type="button" onClick={() => runPreview(html, preview.index)} disabled={preview.loading}
              className="text-xs text-pb-faint hover:text-pb-text underline disabled:opacity-50">
              {preview.loading ? 'Refreshing…' : 'Refresh'}
            </button>
          )}
          {!simple && (
            <button type="button" onClick={() => changeMode('code')}
              className={`px-3 py-1.5 rounded text-xs font-medium border pb-hairline ${mode === 'code' ? 'text-white' : 'text-pb-faint hover:text-pb-text'}`}
              style={mode === 'code' ? { background: 'var(--pb-accent)', borderColor: 'var(--pb-accent)' } : {}}>
              HTML
            </button>
          )}
        </div>
      </div>

      {mode === 'code' && (
        <textarea
          ref={codeRef}
          value={html}
          onChange={e => { codeDirtyRef.current = true; onChange(e.target.value) }}
          spellCheck={false}
          className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline font-mono text-xs"
          style={{ minHeight: height }}
        />
      )}

      {mode === 'design' && (
        <div>
          {!simple && (
            <div className="flex flex-wrap items-center gap-1 mb-2 pb-card p-1.5">
              <ToolbarBtn onClick={undo} disabled={!historyFlags.canUndo} title="Undo (Cmd/Ctrl+Z)">↶ Undo</ToolbarBtn>
              <ToolbarBtn onClick={redo} disabled={!historyFlags.canRedo} title="Redo (Cmd/Ctrl+Shift+Z)">↷ Redo</ToolbarBtn>
              <Divider />
              <ToolbarBtn onClick={() => exec('bold')} title="Bold"><b>B</b></ToolbarBtn>
              <ToolbarBtn onClick={() => exec('italic')} title="Italic"><i>I</i></ToolbarBtn>
              <ToolbarBtn onClick={() => exec('underline')} title="Underline"><u>U</u></ToolbarBtn>
              <Divider />
              <ToolbarBtn onClick={() => exec('formatBlock', '<h2>')} title="Heading">H2</ToolbarBtn>
              <ToolbarBtn onClick={() => exec('formatBlock', '<h3>')} title="Subheading">H3</ToolbarBtn>
              <ToolbarBtn onClick={() => exec('formatBlock', '<p>')} title="Paragraph">P</ToolbarBtn>
              <Divider />
              <ToolbarBtn onClick={() => exec('insertUnorderedList')} title="Bullet list">• List</ToolbarBtn>
              <ToolbarBtn onClick={() => exec('insertOrderedList')} title="Numbered list">1. List</ToolbarBtn>
              <Divider />
              <ToolbarBtn onClick={insertLink} title="Insert a link, or click inside an existing link/button to edit its URL">Link</ToolbarBtn>
              <ToolbarBtn onClick={() => exec('unlink')} title="Remove link">Unlink</ToolbarBtn>
              <ToolbarBtn onClick={insertImage} title="Insert image">Image</ToolbarBtn>
              <ToolbarBtn onClick={insertButton} title="Insert a button-styled link">Button</ToolbarBtn>
              <Divider />
              <ToolbarBtn onClick={() => insertTableRow(false)} title="Insert a table row above the current one">Row ↑+</ToolbarBtn>
              <ToolbarBtn onClick={() => insertTableRow(true)} title="Insert a table row below the current one">Row ↓+</ToolbarBtn>
              <ToolbarBtn onClick={deleteTableRow} title="Delete the current table row">Row −</ToolbarBtn>
            </div>
          )}
          <iframe
            ref={designFrameRef}
            title="design"
            srcDoc={designSrcDoc ?? ''}
            onLoad={onFrameLoad}
            style={{ height, width: '100%', background: '#fff' }}
            className="rounded border pb-hairline"
          />
        </div>
      )}

      {mode === 'preview' && (
        <div>
          {preview.label && <div className="text-pb-faintest text-xs mb-1">{preview.label}</div>}
          {preview.subject && (
            <div className="text-pb-text text-sm mb-2">
              <span className="text-pb-faintest">Subject: </span>
              <span className="font-medium">{preview.subject}</span>
            </div>
          )}
          {preview.error && <div className="text-pb-red text-xs mb-1">{preview.error}</div>}
          <iframe title="preview" srcDoc={preview.html} className="w-full rounded border pb-hairline bg-white" style={{ height }} />
          {preview.total > 1 && (
            <div className="flex items-center justify-between mt-2">
              <button type="button" onClick={() => pagePreview(-1)} disabled={preview.loading || preview.index <= 0}
                className="px-3 py-1 rounded text-xs border pb-hairline text-pb-text hover:bg-pb-surface2 disabled:opacity-40">← Previous</button>
              <span className="text-pb-faintest text-xs">{(preview.index || 0) + 1} / {preview.total}</span>
              <button type="button" onClick={() => pagePreview(1)} disabled={preview.loading || preview.index >= preview.total - 1}
                className="px-3 py-1 rounded text-xs border pb-hairline text-pb-text hover:bg-pb-surface2 disabled:opacity-40">Next →</button>
            </div>
          )}
        </div>
      )}
    </div>
  )
})

function ToolbarBtn({ onClick, title, disabled, children }) {
  return (
    <button type="button" onClick={onClick} title={title} disabled={disabled}
      className="px-2 py-1 rounded text-xs text-pb-text hover:bg-pb-surface2 border pb-hairline disabled:opacity-40 disabled:hover:bg-transparent">
      {children}
    </button>
  )
}
function Divider() {
  return <span className="w-px h-4 bg-pb-hairline mx-1" />
}

export default EmailEditorTabs
