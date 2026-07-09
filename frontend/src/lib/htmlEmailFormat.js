// Shared HTML helpers for the BetterComms Template and Email editors —
// detecting full-document vs fragment content (mirrors the backend's
// `_is_full_doc`/`_body_to_html` in routers/comms.py) and tidying HTML with
// js-beautify so switching out of raw HTML mode always leaves clean,
// indented markup behind.
import { html as beautifyHtml } from 'js-beautify'

const BEAUTIFY_OPTS = {
  indent_size: 2,
  indent_char: ' ',
  wrap_line_length: 0,
  preserve_newlines: true,
  max_preserve_newlines: 1,
  indent_inner_html: true,
  extra_liners: [],
  inline: ['a', 'span', 'b', 'i', 'em', 'strong', 'u', 'br', 'img', 'small', 'sub', 'sup'],
}

// Mirrors backend `_is_full_doc`: a pasted/imported template is a full HTML
// document; a compose box holding a plain message is a fragment.
export function isFullHtmlDoc(html) {
  const low = (html || '').toLowerCase()
  return low.includes('<html') || low.includes('<body')
}

// Mirrors backend `_body_to_html`: plain text gets escaped + <br>'d; content
// that already looks like HTML is trusted as-is.
export function fragmentToDisplayHtml(body) {
  const b = body || ''
  if (b.includes('<') && b.includes('>')) return b
  const esc = b.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return esc.replace(/\n/g, '<br>\n')
}

export function tidyHtml(rawHtml) {
  try {
    return beautifyHtml(rawHtml || '', BEAUTIFY_OPTS)
  } catch {
    return rawHtml
  }
}

// A minimal shell so a plain-text/simple-HTML fragment renders readably in
// the Design (WYSIWYG) iframe. Only used to seed the editable surface — never
// stored; on leaving Design mode only the fragment's inner content is read
// back out, so the backend's own auto-wrap (club shell + footer) is untouched.
export function wrapFragmentForEditing(fragment) {
  return `<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;padding:16px;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;font-size:15px;color:#1f2937;line-height:1.6;background:#fff;}
a{color:#243352;}
</style></head><body>${fragmentToDisplayHtml(fragment)}</body></html>`
}

// Reconstructs a full HTML document string from an edited iframe document
// (doctype isn't reflected in documentElement.outerHTML, so it's re-added).
export function serializeIframeDocument(doc) {
  const doctype = doc.doctype ? `<!DOCTYPE ${doc.doctype.name}>` : '<!doctype html>'
  return `${doctype}\n${doc.documentElement.outerHTML}`
}
