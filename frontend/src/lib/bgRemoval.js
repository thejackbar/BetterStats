// AI subject cut-out (@imgly/background-removal), shared by the image editor.
//
// The library's default is to pull ~100MB of ONNX runtime and model from
// staticimgly.com, which sends no cache headers, so every cut-out downloaded and
// revalidated ~50 files from a third-party origin. We self-host the files under
// <base>assets/bg-removal/ (scripts/fetch-bg-removal-assets.mjs, run by
// `npm run build`; nginx serves them immutable) and only fall back to the
// library's CDN default when that folder is not there.
//
// The model runs in a Web Worker so the page stays responsive; if a worker
// cannot start, it runs on the main thread instead. WebGPU is used when the
// browser has it (seconds become well under one); the WASM path is one thread
// (the app is not cross-origin isolated). Same fp16 model on both: the smaller
// quint8 one only saved ~30% in a CPU test, not worth the quality risk.
import { cutOutCore } from './bgRemovalCore'

const BASE = import.meta.env.BASE_URL || '/'
const LOCAL_PATH = `${BASE}assets/bg-removal/`

let envPromise = null

// Resolve once per page: where the files live and whether WebGPU is usable.
function resolveEnv() {
  if (!envPromise) {
    envPromise = (async () => {
      let publicPath
      try {
        const url = new URL(`${LOCAL_PATH}resources.json`, window.location.origin)
        const res = await fetch(url)
        // A SPA fallback answers 200 with index.html, so insist on real JSON.
        const json = res.ok ? await res.json() : null
        if (json && json['/models/isnet_fp16']) publicPath = url.href.replace('resources.json', '')
      } catch { /* fall back to the CDN default */ }

      let gpu = false
      try {
        gpu = !!(navigator.gpu && await navigator.gpu.requestAdapter())
      } catch { /* no WebGPU */ }

      return { publicPath, gpu }
    })()
  }
  return envPromise
}

// One worker at a time, started on first use and dropped by
// releaseBackgroundRemoval() so the model's memory is not held after the editor
// closes. A request that fails because the worker itself broke (not because the
// cut-out failed) rejects with `workerBroken` so the caller can use the main thread.
let worker = null
let nextId = 1
const pending = new Map()

function failAll(error) {
  for (const p of pending.values()) p.reject(error)
  pending.clear()
}

function getWorker() {
  if (worker) return worker
  const w = new Worker(new URL('./bgRemoval.worker.js', import.meta.url), { type: 'module' })
  w.onmessage = (e) => {
    const { id, progress, blob, error, done } = e.data
    const p = pending.get(id)
    if (!p) return
    if (progress) { p.onProgress?.(progress); return }
    pending.delete(id)
    if (error) p.reject(new Error(error))
    else p.resolve(blob ?? done)
  }
  w.onerror = (e) => {
    e.preventDefault?.()
    const err = new Error(e.message || 'Background removal worker failed')
    err.workerBroken = true
    if (worker === w) worker = null
    w.terminate()
    failAll(err)
  }
  worker = w
  return w
}

function callWorker(message, onProgress) {
  return new Promise((resolve, reject) => {
    const id = nextId++
    pending.set(id, { resolve, reject, onProgress })
    try {
      getWorker().postMessage({ id, ...message })
    } catch (err) {
      pending.delete(id)
      err.workerBroken = true
      reject(err)
    }
  })
}

// Stop the worker and free the model. Safe to call at any time.
export function releaseBackgroundRemoval() {
  if (!worker) return
  worker.terminate()
  worker = null
  const err = new Error('Background removal was cancelled')
  failAll(err)
}

// Warm the browser cache and the model while the person is still cropping.
// Never throws: a failed preload just means the real call downloads instead.
export async function preloadBackgroundRemoval() {
  try {
    const env = await resolveEnv()
    await callWorker({ type: 'preload', env })
  } catch { /* the real call reports its own error */ }
}

// Cut the subject out of an image URL. Resolves to a PNG Blob.
// onProgress gets { stage: 'download' | 'compute', pct }.
export async function removeBackgroundFromUrl(srcUrl, onProgress) {
  const env = await resolveEnv()
  try {
    return await callWorker({ type: 'run', url: srcUrl, env }, onProgress)
  } catch (err) {
    if (!err.workerBroken) throw err
    console.warn('Background removal worker unavailable, running on the main thread', err)
    return cutOutCore(srcUrl, env, onProgress)
  }
}
