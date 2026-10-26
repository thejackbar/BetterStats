// Render a DOM node to a PNG and hand it to the phone's share sheet, or download it where there is none.
// The same exporter the Fantasy share cards and the admin social posts use (modern-screenshot).
// Resolves 'shared' | 'saved'; a dismissed share sheet resolves 'cancelled'. Anything else throws.
export async function exportNodePng(node, name, { width, height, backgroundColor = '#0a0d14', scale = 2, share = true } = {}) {
  if (!node) throw new Error('Nothing to export')
  await document.fonts?.ready
  const { domToBlob } = await import('modern-screenshot')
  const blob = await domToBlob(node, { type: 'image/png', scale, width, height, backgroundColor })
  if (!blob) throw new Error('Could not make the image')
  const file = new File([blob], `${name}.png`, { type: 'image/png' })
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
  a.download = `${name}.png`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  return 'saved'
}
