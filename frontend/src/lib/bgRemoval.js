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
// cannot start, it runs on the main thread instead. On a desktop browser with
// WebGPU it uses the graphics chip (seconds become well under one); otherwise
// the WASM path is one thread (the app is not cross-origin isolated).
//
// Phones and tablets, low-memory devices, and any device where the last cut-out
// never finished take the constrained path: no WebGPU, no background preload,
// the photo shrunk before it is read, the light model (see bgRemovalCore.js),
// and the worker thrown away afterwards so its memory comes back. The full ISNet
// model needs ~770MB of working memory, which gets a phone tab killed (the page
// goes blank and reloads, so there is no error to catch).
import { cutOutCore } from './bgRemovalCore'

const BASE = import.meta.env.BASE_URL || '/'
const LOCAL_PATH = `${BASE}assets/bg-removal/`

const INFLIGHT = 'bgRemoval.inflight'
const CRASHED = 'bgRemoval.crashed'

const store = {
  get: (k) => { try { return window.localStorage.getItem(k) } catch { return null } },
  set: (k, v) => { try { window.localStorage.setItem(k, v) } catch { /* private mode */ } },
  del: (k) => { try { window.localStorage.removeItem(k) } catch { /* private mode */ } },
}

// A run that was under way when the page died leaves INFLIGHT behind (pagehide
// clears it on a normal close or navigation, but a killed tab gets no event).
if (typeof window !== 'undefined') {
  if (store.get(INFLIGHT)) { store.set(CRASHED, '1'); store.del(INFLIGHT) }
  window.addEventListener('pagehide', () => store.del(INFLIGHT))
}

// True while the last cut-out on this device did not finish and none has since.
export function cutOutCrashedBefore() {
  return store.get(CRASHED) === '1'
}

let active = 0
function runStarted() { if (active++ === 0) store.set(INFLIGHT, String(Date.now())) }
function runEnded(ok) {
  if (--active <= 0) { active = 0; store.del(INFLIGHT) }
  if (ok) store.del(CRASHED)
}

function isConstrainedDevice() {
  const ua = navigator.userAgent || ''
  const handheld = /Android|iPhone|iPad|iPod|Mobile/i.test(ua)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1) // iPadOS asks for the desktop site
  const lowMemory = typeof navigator.deviceMemory === 'number' && navigator.deviceMemory <= 4
  return handheld || lowMemory || cutOutCrashedBefore()
}

let envPromise = null

// Resolve once per page: where the files live, which path this device takes.
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

      const constrained = isConstrainedDevice()

      let light = null
      if (constrained && publicPath) {
        try {
          const res = await fetch(new URL('light-model.json', publicPath))
          const meta = res.ok ? await res.json() : null
          if (meta?.name && meta.size) light = { url: new URL(meta.name, publicPath).href, size: meta.size }
        } catch { /* no light model: ISNet quint8 below */ }
      }

      let gpu = false
      if (!constrained) {
        try {
          gpu = !!(navigator.gpu && await navigator.gpu.requestAdapter())
        } catch { /* no WebGPU */ }
      }

      return {
        publicPath,
        gpu,
        constrained,
        light,
        // ISNet fallback for a constrained device with no light model: the
        // quint8 variant, on a shrunk photo.
        model: constrained ? 'isnet_quint8' : 'isnet_fp16',
        maxSide: constrained ? 1600 : 0,
      }
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
    if (env.constrained) return // would hold the model's memory while the person is only cropping
    runStarted()
    try {
      await callWorker({ type: 'preload', env })
    } finally {
      runEnded(false)
    }
  } catch { /* the real call reports its own error */ }
}

// Cut the subject out of an image URL. Resolves to a PNG Blob.
// onProgress gets { stage: 'download' | 'compute', pct }.
export async function removeBackgroundFromUrl(srcUrl, onProgress) {
  const env = await resolveEnv()
  runStarted()
  let ok = false
  try {
    let blob
    try {
      blob = await callWorker({ type: 'run', url: srcUrl, env }, onProgress)
    } catch (err) {
      if (!err.workerBroken) throw err
      console.warn('Background removal worker unavailable, running on the main thread', err)
      blob = await cutOutCore(srcUrl, env, onProgress)
    }
    ok = true
    return blob
  } finally {
    runEnded(ok)
    if (env.constrained) releaseBackgroundRemoval() // hand the model's memory back
  }
}
