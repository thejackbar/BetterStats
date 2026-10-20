// Runs the cut-out off the main thread so the page stays live while the model
// works (it is several seconds of single-threaded WASM on most machines).
import { cutOutCore, preloadCore } from './bgRemovalCore'

self.onmessage = async (e) => {
  const { id, type, url, env } = e.data
  try {
    if (type === 'preload') {
      await preloadCore(env)
      self.postMessage({ id, done: true })
    } else {
      const blob = await cutOutCore(url, env, (progress) => self.postMessage({ id, progress }))
      self.postMessage({ id, blob })
    }
  } catch (err) {
    self.postMessage({ id, error: (err && err.message) || String(err) })
  }
}
