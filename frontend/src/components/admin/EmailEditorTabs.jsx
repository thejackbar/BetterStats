import { useRef, useState, useEffect, forwardRef, useImperativeHandle } from 'react'
import { api } from '../../lib/api'
import { isFullHtmlDoc, tidyHtml, wrapFragmentForEditing, serializeIframeDocument } from '../../lib/htmlEmailFormat'

// Shared HTML / Design (WYSIWYG) / Preview editor for the BetterComms Template
// and Email compose pages. Design sits on the left (toggle to Preview in the
// same spot); the HTML source is a persistent pane on the right, so both are
// visible together — edits in either flow into the other. Design mode edits
// the real DOM directly inside an iframe (contentDocument.designMode) so
// existing table-based email layouts round-trip untouched — a schema-based
// rich-text editor would normalise/strip that markup. Switching to Preview,
// saving, or sending all tidy the HTML via js-beautify.
//
// Parents that persist content (Save/Send/Test) MUST call ref.flush() first
// and use its return value — it synchronously returns the latest content
// (design-iframe edits read back, or tidied code) rather than relying on the
// onChange callback's state update having landed yet.
const EmailEditorTabs = forwardRef(function EmailEditorTabs(
  { html, onChange, onEnterPreview, height = 480 },
  ref
) {
  const [viewMode, setViewMode] = useState('design') // 'design' | 'preview' — the left pane
  const [designSrcDoc, setDesignSrcDoc] = useState(null)
  const [designIsFullDoc, setDesignIsFullDoc] = useState(true)
  const designFrameRef = useRef(null)
  const codeRef = useRef(null)
  const codeDirtyRef = useRef(false)
  const liveSyncTimerRef = useRef(null)
  const lastFocusRef = useRef('design') // which pane last had focus — where Insert lands
  const [preview, setPreview] = useState({ loading: false, html: '', total: 1, index: 0, label: '', error: '' })
  const [vars, setVars] = useState({ is_marketing: false, variables: [] })
  const [justInserted, setJustInserted] = useState('')

  useEffect(() => { api.commsMergeVariables().then(setVars).catch(() => {}) }, [])

  // Raw (untidied) read of the design iframe's current content — cheap enough
  // to call on every keystroke for a debounced "keep parent state roughly in
  // sync" pass, separate from the tidied read used when actually leaving mode.
  const readDesign = () => {
    const frame = designFrameRef.current
    if (!frame?.contentDocument) return html
    const doc = frame.contentDocument
    return designIsFullDoc ? serializeIframeDocument(doc) : (doc.body ? doc.body.innerHTML : html)
  }

  const flushDesign = () => (viewMode === 'design' ? tidyHtml(readDesign()) : html)

  const flush = () => {
    let next = html
    if (viewMode === 'design') {
      next = flushDesign()
    } else if (codeDirtyRef.current) {
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

  const insertVariable = (name) => {
    const token = `{{${name}}}`
    if (viewMode === 'design' && lastFocusRef.current !== 'code') {
      exec('insertText', token)
    } else {
      insertAtCursor(token)
    }
    setJustInserted(name)
    setTimeout(() => setJustInserted(''), 900)
  }

  useImperativeHandle(ref, () => ({ flush, insertVariable }))

  // Rebuilds the Design iframe from the latest HTML whenever it changes from
  // outside (typing in the HTML pane, importing a file, picking a template) —
  // but never while the iframe itself has focus, which would clobber the
  // user's own in-progress WYSIWYG edit and caret position (Design's own
  // debounced sync below writes into `html` without touching this state).
  useEffect(() => {
    if (viewMode !== 'design') return
    if (designFrameRef.current && document.activeElement === designFrameRef.current) return
    const isFull = isFullHtmlDoc(html)
    setDesignIsFullDoc(isFull)
    setDesignSrcDoc(isFull ? html : wrapFragmentForEditing(html))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [html])

  const runPreview = async (currentHtml, index) => {
    if (!onEnterPreview) return
    setPreview(p => ({ ...p, loading: true, error: '' }))
    try {
      const r = await onEnterPreview({ html: currentHtml, index })
      setPreview({ loading: false, html: r.html || '', total: r.total || 1, index: r.index ?? index, label: r.label || '', error: '' })
    } catch (e) {
      setPreview(p => ({ ...p, loading: false, error: e.message || 'Could not render preview.' }))
    }
  }

  const changeView = (next) => {
    if (next === viewMode) return
    const flushed = flush()
    if (next === 'design') {
      const isFull = isFullHtmlDoc(flushed)
      setDesignIsFullDoc(isFull)
      setDesignSrcDoc(isFull ? flushed : wrapFragmentForEditing(flushed))
    }
    setViewMode(next)
    if (next === 'preview') runPreview(flushed, 0)
  }

  const pagePreview = (delta) => {
    const total = preview.total || 1
    const next = Math.max(0, Math.min(total - 1, (preview.index || 0) + delta))
    if (next === preview.index) return
    runPreview(html, next)
  }

  const onFrameLoad = () => {
    const frame = designFrameRef.current
    const doc = frame?.contentDocument
    if (!doc) return
    try { doc.designMode = 'on' } catch { /* not editable in this browser */ }
    // Debounced, untidied sync back to parent state while typing — keeps
    // Send-button enablement and unknown-variable warnings live without
    // touching designSrcDoc (which would disrupt the iframe/cursor).
    doc.addEventListener('input', () => {
      clearTimeout(liveSyncTimerRef.current)
      liveSyncTimerRef.current = setTimeout(() => onChange(readDesign()), 400)
    })
    frame.contentWindow?.addEventListener('focus', () => { lastFocusRef.current = 'design' })
  }

  const exec = (cmd, val) => {
    const frame = designFrameRef.current
    const doc = frame?.contentDocument
    if (!doc) return
    frame.contentWindow?.focus()
    doc.execCommand(cmd, false, val)
  }

  const insertLink = () => {
    const url = window.prompt('Link URL:', 'https://')
    if (url) exec('createLink', url)
  }
  const insertImage = () => {
    const url = window.prompt('Image URL:')
    if (url) exec('insertImage', url)
  }
  const insertButton = () => {
    exec('insertHTML', '<a href="https://" style="display:inline-block;background:#243352;color:#fff;text-decoration:none;padding:10px 18px;border-radius:6px;">Button text</a>')
  }

  const varList = (vars.variables || []).filter(v => !v.marketing_only || vars.is_marketing)

  return (
    <div>
      {varList.length > 0 && (
        <div className="pb-card p-2 mb-2">
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
          <button key={m} type="button" onClick={() => changeView(m)}
            className={`px-3 py-1.5 rounded text-xs font-medium border pb-hairline ${viewMode === m ? 'text-white' : 'text-pb-faint hover:text-pb-text'}`}
            style={viewMode === m ? { background: 'var(--pb-accent)', borderColor: 'var(--pb-accent)' } : {}}>
            {label}
          </button>
        ))}
        {viewMode === 'preview' && (
          <button type="button" onClick={() => runPreview(html, preview.index)} disabled={preview.loading}
            className="ml-auto text-xs text-pb-faint hover:text-pb-text underline disabled:opacity-50">
            {preview.loading ? 'Refreshing…' : 'Refresh'}
          </button>
        )}
      </div>

      <div className="flex flex-col lg:flex-row gap-3">
        <div className="flex-1 min-w-0">
          {viewMode === 'design' && (
            <div>
              <div className="flex flex-wrap items-center gap-1 mb-2 pb-card p-1.5">
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
                <ToolbarBtn onClick={insertLink} title="Insert link">Link</ToolbarBtn>
                <ToolbarBtn onClick={() => exec('unlink')} title="Remove link">Unlink</ToolbarBtn>
                <ToolbarBtn onClick={insertImage} title="Insert image">Image</ToolbarBtn>
                <ToolbarBtn onClick={insertButton} title="Insert a button-styled link">Button</ToolbarBtn>
              </div>
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

          {viewMode === 'preview' && (
            <div>
              {preview.label && <div className="text-pb-faintest text-xs mb-1">{preview.label}</div>}
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

        <div className="lg:w-[400px] shrink-0">
          <div className="text-pb-faintest text-xs mb-1">HTML</div>
          <textarea
            ref={codeRef}
            value={html}
            onFocus={() => { lastFocusRef.current = 'code' }}
            onChange={e => { codeDirtyRef.current = true; onChange(e.target.value) }}
            spellCheck={false}
            className="w-full px-3 py-2 rounded bg-pb-surface2 text-pb-text border pb-hairline font-mono text-xs"
            style={{ height: viewMode === 'design' ? height + 46 : height }}
          />
        </div>
      </div>
    </div>
  )
})

function ToolbarBtn({ onClick, title, children }) {
  return (
    <button type="button" onClick={onClick} title={title}
      className="px-2 py-1 rounded text-xs text-pb-text hover:bg-pb-surface2 border pb-hairline">
      {children}
    </button>
  )
}
function Divider() {
  return <span className="w-px h-4 bg-pb-hairline mx-1" />
}

export default EmailEditorTabs
