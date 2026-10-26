// Render a DOM node to a PNG and hand it to the phone's share sheet, or download it where there is none.
// The same exporter the Fantasy share cards and the admin social posts use (modern-screenshot).
// Resolves 'shared' | 'saved'; a dismissed share sheet resolves 'cancelled'. Anything else throws.
// modern-screenshot only embeds fonts from stylesheets it can read, and the Google Fonts <link> is cross-origin,
// so every web font was silently dropped and an exported card fell back to a plain face. Fetch that CSS ourselves
// and hand over only the latin faces of the families the cards use (all of them would be hundreds of files).
const EXPORT_FAMILIES = ['Barlow Condensed', 'Inter', 'JetBrains Mono', 'Saira Condensed', 'Hanken Grotesk']

// Every family the node actually draws with, so a club's own display font is embedded too, not just the defaults.
function familiesUsedBy(node) {
  const used = new Set(EXPORT_FAMILIES)
  for (const el of [node, ...node.querySelectorAll('*')]) {
    for (const f of getComputedStyle(el).fontFamily.split(',')) used.add(f.trim().replace(/^['"]|['"]$/g, ''))
  }
  return [...used]
}
let googleCss = null
async function exportFontCss(families) {
  if (!googleCss) {
    const hrefs = [...document.querySelectorAll('link[rel="stylesheet"]')].map(l => l.href).filter(h => h.includes('fonts.googleapis.com'))
    googleCss = Promise.all(hrefs.map(h => fetch(h).then(r => (r.ok ? r.text() : '')).catch(() => ''))).then(t => t.join('\n'))
  }
  const css = await googleCss
  const blocks = css.split(/(?=\/\*\s*[\w-]+\s*\*\/\s*@font-face)/)
    .filter(b => /^\/\*\s*latin\s*\*\//.test(b) && families.some(f => b.includes(`font-family: '${f}'`)))
  // The library adds `cssText` to the image as it is and does not fetch the files in it, and an image cannot load
  // anything from the network, so each font file has to be inlined here.
  return (await Promise.all(blocks.map(b => inlineFontUrls(b)))).join('\n')
}

const fontData = new Map()   // url -> data URL, kept for the life of the page
async function toDataUrl(url) {
  if (!fontData.has(url)) {
    fontData.set(url, fetch(url).then(r => (r.ok ? r.blob() : Promise.reject(new Error(String(r.status)))))
      .then(b => new Promise((res, rej) => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.onerror = rej; fr.readAsDataURL(b) }))
      .catch(() => url))
  }
  return fontData.get(url)
}
async function inlineFontUrls(block) {
  const urls = [...new Set([...block.matchAll(/url\((https:[^)]+)\)/g)].map(m => m[1]))]
  let out = block
  for (const u of urls) out = out.split(`url(${u})`).join(`url(${await toDataUrl(u)})`)
  return out
}

// Render a node to a PNG blob (no sharing, no download): the part other exporters build on.
export async function renderNodeBlob(node, { width, height, backgroundColor = '#0a0d14', scale = 2 } = {}) {
  if (!node) throw new Error('Nothing to export')
  await document.fonts?.ready
  const { domToBlob } = await import('modern-screenshot')
  const cssText = await exportFontCss(familiesUsedBy(node)).catch(() => '')
  const blob = await domToBlob(node, { type: 'image/png', scale, width, height, backgroundColor, ...(cssText ? { font: { cssText } } : {}) })
  if (!blob) throw new Error('Could not make the image')
  return blob
}

// Hand a file to the phone's share sheet, or download it where there is none. 'shared' | 'saved' | 'cancelled'.
export async function deliverBlob(blob, filename, type, { share = true } = {}) {
  const file = new File([blob], filename, { type })
  if (share && navigator.canShare && navigator.canShare({ files: [file] })) {
    try {
      await navigator.share({ files: [file] })
      return 'shared'
    } catch (e) {
      if (e?.name === 'AbortError') return 'cancelled'
      throw e
    }
  }
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  return 'saved'
}

export async function exportNodePng(node, name, { width, height, backgroundColor = '#0a0d14', scale = 2, share = true } = {}) {
  const blob = await renderNodeBlob(node, { width, height, backgroundColor, scale })
  return deliverBlob(blob, `${name}.png`, 'image/png', { share })
}
