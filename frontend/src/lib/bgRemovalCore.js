// The cut-out itself, free of any DOM use so it runs in a Web Worker
// (bgRemoval.worker.js) or, as a fallback, on the main thread (bgRemoval.js).
//
// env = { publicPath?: string, gpu: boolean }, resolved on the main thread.

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

function buildConfig({ publicPath }, device) {
  const cfg = { debug: false, device, model: 'isnet_fp16', progress: dispatch }
  if (publicPath) cfg.publicPath = publicPath
  return cfg
}

export async function preloadCore(env) {
  const { preload } = await import('@imgly/background-removal')
  await preload(buildConfig(env, env.gpu ? 'gpu' : 'cpu'))
}

// Resolves to a PNG Blob. onProgress gets { stage: 'download' | 'compute', pct }.
// A WebGPU failure retries once on the CPU path before giving up.
export async function cutOutCore(srcUrl, env, onProgress) {
  const { removeBackground } = await import('@imgly/background-removal')
  listener = onProgress || null
  try {
    if (env.gpu) {
      try {
        return await removeBackground(srcUrl, buildConfig(env, 'gpu'))
      } catch (err) {
        console.warn('WebGPU background removal failed, retrying on CPU', err)
      }
    }
    return await removeBackground(srcUrl, buildConfig(env, 'cpu'))
  } finally {
    listener = null
  }
}
