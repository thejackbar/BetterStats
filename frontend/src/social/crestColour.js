// A club's colour read from its crest, and the shades a page is built from.

const HEX = /^#[0-9a-fA-F]{6}$/

const toRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16))
const toHex = (rgb) => '#' + rgb.map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('')

// Mix `hex` toward `toward` ('#000000' darkens, '#ffffff' lightens) by t (0 to 1).
export function mixHex(hex, toward, t) {
  if (!HEX.test(hex || '') || !HEX.test(toward || '')) return hex
  const a = toRgb(hex)
  const b = toRgb(toward)
  return toHex(a.map((v, i) => v + (b[i] - v) * t))
}

// The palette a page takes in a club's colour: a deep background and panel, the colour
// itself as the accent, white text. Returns null for anything that is not a colour.
export function paletteFromColour(hex, base = {}) {
  if (!HEX.test(hex || '')) return null
  return { ...base, primary: mixHex(hex, '#000000', 0.82), secondary: mixHex(hex, '#000000', 0.7), accent: hex, ink: '#ffffff' }
}

// The most common strong colour in a crest. Whites, near-blacks and greys are skipped
// (a crest's background is rarely the club's colour). Resolves null when the image
// cannot be read (cross-origin without CORS, a 404): the caller keeps what it had.
export function crestColour(url) {
  return new Promise((resolve) => {
    if (!url || typeof document === 'undefined') return resolve(null)
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => {
      try {
        const size = 48
        const canvas = document.createElement('canvas')
        canvas.width = size
        canvas.height = size
        const ctx = canvas.getContext('2d', { willReadFrequently: true })
        ctx.drawImage(img, 0, 0, size, size)
        const { data } = ctx.getImageData(0, 0, size, size)
        const bins = new Map()
        for (let i = 0; i < data.length; i += 4) {
          const [r, g, b, a] = [data[i], data[i + 1], data[i + 2], data[i + 3]]
          if (a < 200) continue
          const max = Math.max(r, g, b)
          const min = Math.min(r, g, b)
          const sat = max === 0 ? 0 : (max - min) / max
          if (max < 50 || (max > 235 && sat < 0.12) || sat < 0.25) continue
          const key = `${r >> 4},${g >> 4},${b >> 4}`
          const bin = bins.get(key) || { n: 0, r: 0, g: 0, b: 0 }
          bin.n += 1; bin.r += r; bin.g += g; bin.b += b
          bins.set(key, bin)
        }
        let best = null
        bins.forEach((bin) => { if (!best || bin.n > best.n) best = bin })
        resolve(best ? toHex([best.r / best.n, best.g / best.n, best.b / best.n]) : null)
      } catch { resolve(null) }
    }
    img.onerror = () => resolve(null)
    img.src = url
  })
}
