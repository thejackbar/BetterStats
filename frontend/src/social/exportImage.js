// Shared BetterSocials image export — the font-embedding + DOM-to-PNG pipeline
// the Post Designer (AdminSocialPost) and the super-admin Club Announcement tool
// both render with. Kept in one place so the export stays pixel-identical across
// every BetterSocials surface.
//
// modern-screenshot serialises a node into an SVG <foreignObject> and lets the
// real browser engine lay it out, so the capture matches the on-screen render
// exactly (no html2canvas layout re-implementation, no text/image drift).

// ─────────────────────────────────────────────────────────────────────────────
// FONT EMBEDDING FOR EXPORT
// modern-screenshot only embeds fonts from stylesheets it can read, and reading
// a cross-origin <link> sheet's cssRules throws a SecurityError — so it silently
// skips them. Our display fonts come from fonts.googleapis.com, meaning they
// never make it into the captured SVG and the export falls back to a wide system
// font (text overflows / clips). We fetch those stylesheets ourselves, inline
// every font file as a data URI, and hand the result to the exporter's
// `font.cssText` option. Cached after the first successful build.
// ─────────────────────────────────────────────────────────────────────────────
let _embeddedFontCssPromise = null
export async function getEmbeddedFontCss() {
  if (!_embeddedFontCssPromise) {
    _embeddedFontCssPromise = buildEmbeddedFontCss().catch(e => {
      _embeddedFontCssPromise = null // let the next export retry
      throw e
    })
  }
  // Passing font.cssText REPLACES the exporter's own stylesheet scan, so a
  // club's UPLOADED font (@font-face injected at runtime by useClubTheme /
  // AdminSocialPost, src on our own domain) has to be inlined here too or the
  // export silently falls back to the stack. Rebuilt per export (the style
  // tags are cheap to re-read; the font bytes themselves are cached) so a
  // font uploaded mid-session is picked up.
  return (await _embeddedFontCssPromise) + (await buildLocalFontFaceCss())
}

// Same-origin font files already fetched, keyed by URL → data URI.
const _localFontData = new Map()

async function buildLocalFontFaceCss() {
  const styleText = Array.from(document.querySelectorAll('style'))
    .map(s => s.textContent || '')
    .join('\n')
  const faces = styleText.match(/@font-face\s*\{[^}]*\}/g) || []
  let css = ''
  for (const face of faces) {
    const m = face.match(/url\(['"]?([^'")]+)['"]?\)/)
    if (!m) continue
    const url = m[1]
    // Only our own uploads need inlining; Google files are handled above and
    // an already-inlined data: URI can pass through as-is.
    if (/^https?:/i.test(url)) continue
    if (url.startsWith('data:')) { css += face + '\n'; continue }
    try {
      if (!_localFontData.has(url)) {
        const blob = await (await fetch(url)).blob()
        _localFontData.set(url, await new Promise((resolve, reject) => {
          const fr = new FileReader()
          fr.onload = () => resolve(fr.result)
          fr.onerror = reject
          fr.readAsDataURL(blob)
        }))
      }
      css += face.split(url).join(_localFontData.get(url)) + '\n'
    } catch { /* unreachable file — the export just falls back for this face */ }
  }
  return css
}

async function buildEmbeddedFontCss() {
  const hrefs = Array.from(document.querySelectorAll('link[rel="stylesheet"]'))
    .map(l => l.href)
    .filter(h => /fonts\.googleapis\.com/.test(h))
  let css = ''
  for (const href of hrefs) {
    try { css += (await (await fetch(href)).text()) + '\n' } catch { /* skip unreachable sheet */ }
  }
  const urls = Array.from(new Set(
    Array.from(css.matchAll(/url\((https:\/\/[^)]+?)\)/g)).map(m => m[1].replace(/['"]/g, ''))
  ))
  const pairs = await Promise.all(urls.map(async url => {
    try {
      const blob = await (await fetch(url)).blob()
      const dataUri = await new Promise((resolve, reject) => {
        const fr = new FileReader()
        fr.onload = () => resolve(fr.result)
        fr.onerror = reject
        fr.readAsDataURL(blob)
      })
      return [url, dataUri]
    } catch { return null }
  }))
  for (const pair of pairs) { if (pair) css = css.split(pair[0]).join(pair[1]) }
  return css
}

// Render an off-screen template node to a high-res PNG and trigger a download
// (unless `download` is false — e.g. the "Save to Club Room" action wants the
// blob itself to upload, not a file on the visitor's machine).
// `node` must already be mounted at full width×height (templates render full-bleed).
export async function exportNodeToPng(node, {
  width,
  height,
  fileName = 'image.png',
  scale = 2,                   // 2× for crisp, high-DPI output
  backgroundColor = '#080808', // fallback for any uncovered area; templates are full-bleed dark
  download = true,
} = {}) {
  if (!node) throw new Error('Nothing to export')
  await document.fonts.ready
  const { domToBlob } = await import('modern-screenshot')
  let font
  try { font = { cssText: await getEmbeddedFontCss() } } catch { /* fall back to system fonts */ }
  const blob = await domToBlob(node, {
    type: 'image/png',  // lossless PNG — exact replica, no JPG artefacts on crisp text
    scale,
    width,
    height,
    backgroundColor,
    font,
  })
  if (!blob) throw new Error('Could not generate image')
  if (download) {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = fileName
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }
  return blob
}
