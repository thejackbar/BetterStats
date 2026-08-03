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
export function getEmbeddedFontCss() {
  if (!_embeddedFontCssPromise) {
    _embeddedFontCssPromise = buildEmbeddedFontCss().catch(e => {
      _embeddedFontCssPromise = null // let the next export retry
      throw e
    })
  }
  return _embeddedFontCssPromise
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
