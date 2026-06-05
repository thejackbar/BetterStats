// RichTextEditor — a zero-dependency WYSIWYG built on contentEditable.
//
// Club volunteers write news/pages here with a simple toolbar (headings, bold,
// lists, links, quote). It emits HTML via onChange; the backend sanitises that
// HTML on save (services/sanitize_html), so we never trust it raw. Styling for
// the produced markup lives in `.pb-richtext` (index.css), shared with the
// public render so what you type matches what visitors see.
import { useRef, useEffect, useState, useCallback } from 'react'

// Render sanitised website HTML for public display.
export function RichText({ html, className = '' }) {
  if (!html) return null
  return <div className={`pb-richtext ${className}`} dangerouslySetInnerHTML={{ __html: html }} />
}

const TOOLBAR = [
  { cmd: 'bold', label: 'B', title: 'Bold', style: { fontWeight: 700 } },
  { cmd: 'italic', label: 'I', title: 'Italic', style: { fontStyle: 'italic' } },
  { cmd: 'underline', label: 'U', title: 'Underline', style: { textDecoration: 'underline' } },
  { cmd: 'strikeThrough', label: 'S', title: 'Strikethrough', style: { textDecoration: 'line-through' } },
  { type: 'sep' },
  { block: 'h2', label: 'H2', title: 'Heading' },
  { block: 'h3', label: 'H3', title: 'Subheading' },
  { type: 'sep' },
  { cmd: 'insertUnorderedList', label: '• List', title: 'Bullet list' },
  { cmd: 'insertOrderedList', label: '1. List', title: 'Numbered list' },
  { block: 'blockquote', label: '❝', title: 'Quote' },
  { type: 'sep' },
  { action: 'link', label: '🔗', title: 'Insert link' },
  { action: 'image', label: '🖼', title: 'Insert image by URL' },
  { type: 'sep' },
  { cmd: 'removeFormat', label: '⌫', title: 'Clear formatting' },
]

export default function RichTextEditor({ value, onChange, placeholder = 'Write here…', minHeight = 240 }) {
  const ref = useRef(null)
  const [active, setActive] = useState({})

  // Seed the DOM from `value` only once (and when it changes from empty→content
  // externally). We don't sync on every keystroke or the caret would jump.
  useEffect(() => {
    const el = ref.current
    if (el && el.innerHTML !== (value || '')) {
      // Only overwrite when the editor isn't the source of the change.
      if (document.activeElement !== el) el.innerHTML = value || ''
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  const emit = useCallback(() => {
    if (ref.current) onChange?.(ref.current.innerHTML)
  }, [onChange])

  const refreshActive = useCallback(() => {
    if (document.activeElement !== ref.current) return
    const next = {}
    for (const item of TOOLBAR) {
      if (item.cmd) {
        try { next[item.cmd] = document.queryCommandState(item.cmd) } catch { /* unsupported */ }
      }
    }
    try {
      const block = (document.queryCommandValue('formatBlock') || '').toLowerCase()
      next.h2 = block === 'h2'
      next.h3 = block === 'h3'
      next.blockquote = block === 'blockquote'
    } catch { /* noop */ }
    setActive(next)
  }, [])

  useEffect(() => {
    document.addEventListener('selectionchange', refreshActive)
    // Prefer <p> blocks over the default <div> so paragraphs read cleanly.
    try { document.execCommand('defaultParagraphSeparator', false, 'p') } catch { /* noop */ }
    return () => document.removeEventListener('selectionchange', refreshActive)
  }, [refreshActive])

  const exec = (cmd, val = null) => {
    ref.current?.focus()
    try { document.execCommand('styleWithCSS', false, false) } catch { /* noop */ }
    document.execCommand(cmd, false, val)
    emit()
    refreshActive()
  }

  const toggleBlock = (tag) => {
    let current = ''
    try { current = (document.queryCommandValue('formatBlock') || '').toLowerCase() } catch { /* noop */ }
    exec('formatBlock', `<${current === tag ? 'p' : tag}>`)
  }

  const handleButton = (item) => {
    if (item.cmd) return exec(item.cmd)
    if (item.block) return toggleBlock(item.block)
    if (item.action === 'link') {
      const url = window.prompt('Link URL (https://…)', 'https://')
      if (url) exec('createLink', url.trim())
    }
    if (item.action === 'image') {
      const url = window.prompt('Image URL (https://…)')
      if (url) exec('insertImage', url.trim())
    }
  }

  // Paste as plain text — keeps club copy-paste from dragging in foreign styles
  // (the sanitiser would strip them anyway, but this keeps the editor tidy).
  const onPaste = (e) => {
    e.preventDefault()
    const text = (e.clipboardData || window.clipboardData).getData('text/plain')
    document.execCommand('insertText', false, text)
    emit()
  }

  return (
    <div className="border pb-hairline rounded-lg overflow-hidden bg-pb-bg">
      <div className="flex flex-wrap items-center gap-0.5 px-2 py-1.5 border-b pb-hairline-b bg-pb-surface">
        {TOOLBAR.map((item, i) => item.type === 'sep' ? (
          <span key={i} className="w-px h-5 bg-pb-hairline mx-1" />
        ) : (
          <button
            key={i}
            type="button"
            title={item.title}
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => handleButton(item)}
            style={item.style}
            className={`min-w-[28px] h-7 px-1.5 rounded text-[12px] font-mono transition-colors ${
              active[item.cmd] || active[item.block]
                ? 'bg-pb-accent/15 text-pb-accent'
                : 'text-pb-faint hover:text-pb-text hover:bg-pb-surface2'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div
        ref={ref}
        contentEditable
        suppressContentEditableWarning
        data-placeholder={placeholder}
        onInput={emit}
        onBlur={emit}
        onPaste={onPaste}
        className="pb-richtext pb-richtext-editor px-4 py-3"
        style={{ minHeight }}
      />
    </div>
  )
}
