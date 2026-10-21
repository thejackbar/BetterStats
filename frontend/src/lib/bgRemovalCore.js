// The cut-out itself, free of any DOM use so it runs in a Web Worker
// (bgRemoval.worker.js) or, as a fallback, on the main thread (bgRemoval.js).
//
// env = {
//   publicPath?: string   self-hosted runtime/model folder (CDN default when unset)
//   gpu: boolean          use WebGPU for the ISNet model
//   model?: string        ISNet variant (default 'isnet_fp16')
//   maxSide?: number      shrink the photo to this long side first (0 = as is)
//   light?: { url, size } the light model (silueta); used instead of ISNet
// }

// The library memoizes its setup on JSON.stringify(config), which drops
// functions: whichever call set it up first (usually the preload) keeps ITS
// progress callback for every later call. So every config gets this one stable
// function, and the call in flight points `listener` at its own callback.
let listener = null
const dispatch = (key, current, total) => {
  if (!listener) return
  if (key.startsWith('fetch:')) {
    if (key.includes('/models/')) {
      listener({ stage: 'download', pct: total ? Math.round((current / total) * 100) : 0 })
    }
  } else if (key.startsWith('compute:')) {
    listener({ stage: 'compute', pct: null })
  }
}

function buildConfig({ publicPath, model }, device) {
  const cfg = { debug: false, device, model: model || 'isnet_fp16', progress: dispatch }
  if (publicPath) cfg.publicPath = publicPath
  return cfg
}

export async function preloadCore(env) {
  const { preload } = await import('@imgly/background-removal')
  await preload(buildConfig(env, env.gpu ? 'gpu' : 'cpu'))
}

// A phone photo is 12MP or more. The model only looks at a 1024px (or 320px)
// copy, but the library decodes the whole photo into float tensors first, which
// is a few hundred MB on its own. Hand it a smaller copy instead.
async function shrunk(srcUrl, maxSide) {
  const blob = await (await fetch(srcUrl)).blob()
  if (!maxSide) return blob
  const bmp = await createImageBitmap(blob)
  try {
    const scale = Math.min(1, maxSide / Math.max(bmp.width, bmp.height))
    if (scale === 1) return blob
    const w = Math.max(1, Math.round(bmp.width * scale))
    const h = Math.max(1, Math.round(bmp.height * scale))
    const canvas = new OffscreenCanvas(w, h)
    const ctx = canvas.getContext('2d')
    ctx.imageSmoothingQuality = 'high'
    ctx.drawImage(bmp, 0, 0, w, h)
    return await canvas.convertToBlob({ type: 'image/png' })
  } finally {
    bmp.close()
  }
}

// Resolves to a PNG Blob. onProgress gets { stage: 'download' | 'compute', pct }.
// A WebGPU failure retries once on the CPU path before giving up.
export async function cutOutCore(srcUrl, env, onProgress) {
  if (env.light) return cutOutLight(srcUrl, env, onProgress)
  const { removeBackground } = await import('@imgly/background-removal')
  listener = onProgress || null
  try {
    const image = env.maxSide ? await shrunk(srcUrl, env.maxSide) : srcUrl
    if (env.gpu) {
      try {
        return await removeBackground(image, buildConfig(env, 'gpu'))
      } catch (err) {
        console.warn('WebGPU background removal failed, retrying on CPU', err)
      }
    }
    return await removeBackground(image, buildConfig(env, 'cpu'))
  } finally {
    listener = null
  }
}

// ---- light model ------------------------------------------------------------
// silueta: a 44MB U2-Net variant that works on a 320px copy. About a third less
// working memory and three times quicker than ISNet, with rougher edges. Used on
// phones, where ISNet's ~770MB gets the tab killed. Pre and post processing
// follow rembg's u2net sessions.

async function runtimeUrls(publicPath) {
  const manifest = await (await fetch(new URL('resources.json', publicPath))).json()
  const urlOf = async (key) => {
    const entry = manifest[key]
    const parts = await Promise.all(entry.chunks.map(async (c) => (await fetch(new URL(c.name, publicPath))).blob()))
    return URL.createObjectURL(new Blob(parts, { type: entry.mime }))
  }
  return {
    wasm: await urlOf('/onnxruntime-web/ort-wasm-simd-threaded.wasm'),
    mjs: await urlOf('/onnxruntime-web/ort-wasm-simd-threaded.mjs'),
  }
}

async function fetchWithProgress(url, size, onProgress) {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Could not load the cut-out model (HTTP ${res.status})`)
  if (!res.body) return res.arrayBuffer()
  const reader = res.body.getReader()
  const out = new Uint8Array(size)
  let got = 0
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    if (got + value.length > size) throw new Error('Cut-out model is larger than expected')
    out.set(value, got)
    got += value.length
    onProgress?.({ stage: 'download', pct: Math.round((got / size) * 100) })
  }
  if (got !== size) throw new Error('Cut-out model download was cut short')
  return out.buffer
}

const R = 320
const MEAN = [0.485, 0.456, 0.406]
const STD = [0.229, 0.224, 0.225]

async function cutOutLight(srcUrl, env, onProgress) {
  const ort = await import('onnxruntime-web')
  const blob = await shrunk(srcUrl, env.maxSide || 1600)
  const bmp = await createImageBitmap(blob)
  try {
    const { wasm, mjs } = await runtimeUrls(env.publicPath)
    ort.env.wasm.numThreads = 1
    ort.env.wasm.wasmPaths = { mjs, wasm }

    const bytes = await fetchWithProgress(env.light.url, env.light.size, onProgress)
    onProgress?.({ stage: 'compute', pct: null })
    const session = await ort.InferenceSession.create(bytes, {
      executionProviders: ['wasm'],
      graphOptimizationLevel: 'all',
    })
    try {
      // Model input: the photo squeezed to 320x320, scaled by its brightest value,
      // then standardised per channel.
      const small = new OffscreenCanvas(R, R)
      const sctx = small.getContext('2d')
      sctx.drawImage(bmp, 0, 0, R, R)
      const px = sctx.getImageData(0, 0, R, R).data
      let max = 1
      for (let i = 0; i < px.length; i += 4) max = Math.max(max, px[i], px[i + 1], px[i + 2])
      const input = new Float32Array(3 * R * R)
      for (let i = 0, j = 0; i < px.length; i += 4, j++) {
        for (let k = 0; k < 3; k++) input[k * R * R + j] = (px[i + k] / max - MEAN[k]) / STD[k]
      }
      const out = await session.run({ [session.inputNames[0]]: new ort.Tensor('float32', input, [1, 3, R, R]) })
      const pred = out[session.outputNames[0]].data

      let lo = Infinity
      let hi = -Infinity
      for (let i = 0; i < pred.length; i++) { if (pred[i] < lo) lo = pred[i]; if (pred[i] > hi) hi = pred[i] }
      const span = hi - lo || 1
      const mask = new OffscreenCanvas(R, R)
      const mctx = mask.getContext('2d')
      const mimg = mctx.createImageData(R, R)
      for (let i = 0; i < R * R; i++) {
        mimg.data[4 * i] = mimg.data[4 * i + 1] = mimg.data[4 * i + 2] = 255
        mimg.data[4 * i + 3] = Math.round((255 * (pred[i] - lo)) / span)
      }
      mctx.putImageData(mimg, 0, 0)

      // The photo keeps its own size; the 320px mask is stretched over it.
      const result = new OffscreenCanvas(bmp.width, bmp.height)
      const rctx = result.getContext('2d')
      rctx.drawImage(bmp, 0, 0)
      rctx.globalCompositeOperation = 'destination-in'
      rctx.imageSmoothingQuality = 'high'
      rctx.drawImage(mask, 0, 0, bmp.width, bmp.height)
      return await result.convertToBlob({ type: 'image/png' })
    } finally {
      await session.release?.()
    }
  } finally {
    bmp.close()
  }
}
