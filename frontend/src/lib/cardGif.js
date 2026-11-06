// A short looping GIF of a card: the shine passing over it, or the card turning over to its details and back.
// Built from two flat pictures of the card (front and back), so it needs no 3D: the turn is the card squeezed
// to an edge and opened out the other side, with a little shading. Corners stay see-through (a GIF has one
// bit of transparency, so the edge is cut cleanly at half opacity), and the colours are worked out from the
// card's own pixels only, so a see-through corner can never steal a colour from the card.
import { GIFEncoder, quantize, applyPalette } from 'gifenc'

const loadImage = (blob) => new Promise((resolve, reject) => {
  const url = URL.createObjectURL(blob)
  const img = new Image()
  img.onload = () => resolve({ img, url })
  img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Could not read the card picture')) }
  img.src = url
})

const wait = () => new Promise((r) => setTimeout(r, 0)) // let the page breathe between frames

// Frame plans: [{ draw(ctx), delay }]. `at` is how far through the loop, 0 to 1.
function plan(mode, W, H, front, back) {
  const frames = []
  const fill = (ctx, img) => { ctx.clearRect(0, 0, W, H); ctx.drawImage(img, 0, 0, W, H) }
  if (mode === 'shine') {
    const N = 26
    for (let i = 0; i < N; i += 1) {
      const t = i / (N - 1)
      frames.push({
        delay: i === 0 || i === N - 1 ? 700 : 55,
        draw: (ctx) => {
          fill(ctx, front)
          // A soft diagonal band sweeping across, only over the card's own pixels.
          ctx.save()
          ctx.globalCompositeOperation = 'source-atop'
          const cx = -0.5 * W + t * 2.0 * W
          const g = ctx.createLinearGradient(cx - 0.28 * W, 0, cx + 0.28 * W, 0)
          g.addColorStop(0, 'rgba(255,255,255,0)')
          g.addColorStop(0.5, 'rgba(255,255,255,0.55)')
          g.addColorStop(1, 'rgba(255,255,255,0)')
          ctx.translate(W / 2, H / 2)
          ctx.rotate(-0.38)
          ctx.translate(-W / 2, -H / 2)
          ctx.fillStyle = g
          ctx.fillRect(-W, -H, 3 * W, 3 * H)
          ctx.restore()
        },
      })
    }
    return frames
  }
  // turn: front, over to the back, a hold, and back again
  const STEPS = 9
  const squeeze = (img, k) => (ctx) => {
    ctx.clearRect(0, 0, W, H)
    const sx = Math.max(0.02, k)
    const sy = 1 - 0.05 * (1 - sx)
    ctx.setTransform(sx, 0, 0, sy, (W * (1 - sx)) / 2, (H * (1 - sy)) / 2)
    ctx.drawImage(img, 0, 0, W, H)
    ctx.globalCompositeOperation = 'source-atop'
    ctx.fillStyle = `rgba(0,0,0,${(1 - sx) * 0.45})`
    ctx.fillRect(0, 0, W, H)
    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.globalCompositeOperation = 'source-over'
  }
  frames.push({ delay: 900, draw: (ctx) => fill(ctx, front) })
  for (let i = 1; i <= STEPS; i += 1) frames.push({ delay: 45, draw: squeeze(front, Math.cos((i / (STEPS + 1)) * (Math.PI / 2))) })
  for (let i = STEPS; i >= 1; i -= 1) frames.push({ delay: 45, draw: squeeze(back, Math.cos((i / (STEPS + 1)) * (Math.PI / 2))) })
  frames.push({ delay: 1400, draw: (ctx) => fill(ctx, back) })
  for (let i = 1; i <= STEPS; i += 1) frames.push({ delay: 45, draw: squeeze(back, Math.cos((i / (STEPS + 1)) * (Math.PI / 2))) })
  for (let i = STEPS; i >= 1; i -= 1) frames.push({ delay: 45, draw: squeeze(front, Math.cos((i / (STEPS + 1)) * (Math.PI / 2))) })
  return frames
}

// `frontBlob` and `backBlob` are PNGs of the flat card. Resolves a GIF Blob.
export async function makeCardGif({ frontBlob, backBlob, mode = 'shine', width = 300, onProgress }) {
  const a = await loadImage(frontBlob)
  const b = backBlob ? await loadImage(backBlob) : a
  try {
    const H = Math.round(width * (a.img.naturalHeight / a.img.naturalWidth))
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = H
    const ctx = canvas.getContext('2d', { willReadFrequently: true })
    const gif = GIFEncoder()
    const frames = plan(mode, width, H, a.img, b.img)
    for (let i = 0; i < frames.length; i += 1) {
      frames[i].draw(ctx)
      const { data } = ctx.getImageData(0, 0, width, H)
      // The card's own pixels, packed together, give the palette; everything half see-through or less is the corner.
      let opaque = 0
      for (let p = 3; p < data.length; p += 4) if (data[p] >= 128) opaque += 1
      const solid = new Uint8ClampedArray(opaque * 4)
      for (let p = 0, q = 0; p < data.length; p += 4) {
        if (data[p + 3] >= 128) { solid[q] = data[p]; solid[q + 1] = data[p + 1]; solid[q + 2] = data[p + 2]; solid[q + 3] = 255; q += 4 }
      }
      const palette = quantize(solid, 255)
      const cardIndex = applyPalette(solid, palette)
      const transparentIndex = palette.length
      const index = new Uint8Array(width * H)
      for (let p = 0, q = 0, px = 0; p < data.length; p += 4, px += 1) index[px] = data[p + 3] >= 128 ? cardIndex[q++] : transparentIndex
      gif.writeFrame(index, width, H, {
        palette: [...palette, [0, 0, 0]], delay: frames[i].delay, transparent: true, transparentIndex, dispose: 2, repeat: 0,
      })
      onProgress?.((i + 1) / frames.length)
      if (i % 3 === 2) await wait()
    }
    gif.finish()
    return new Blob([gif.bytes()], { type: 'image/gif' })
  } finally {
    URL.revokeObjectURL(a.url)
    if (b !== a) URL.revokeObjectURL(b.url)
  }
}
