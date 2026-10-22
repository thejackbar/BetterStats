// Self-host the files @imgly/background-removal needs (ONNX runtime + the
// model we use), so the cut-out tool loads them from our own origin with long
// cache headers instead of ~100MB from staticimgly.com, which sends no cache
// headers at all. Runs before `vite build` (npm "prebuild"); output lands in
// public/assets/bg-removal/ and is copied into dist by Vite.
//
// Also fetches the light model phones use (silueta, a U2-Net variant at 320px,
// from the rembg releases): the 1024px ISNet needs ~770MB of working memory,
// which gets a phone tab killed. Pinned by sha256 and stored under a name that
// carries it.
//
// Never fails the build: if a download fails the manifest for it is left out and
// lib/bgRemoval.js falls back (ISNet to the CDN, the light model to ISNet).
import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile, stat, rename } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const outDir = path.join(root, 'public', 'assets', 'bg-removal')

// Keep in step with the model and wasm names the library asks for (see src/lib/bgRemoval.js).
const KEEP = [
  '/onnxruntime-web/ort-wasm-simd-threaded.wasm',
  '/onnxruntime-web/ort-wasm-simd-threaded.mjs',
  '/onnxruntime-web/ort-wasm-simd-threaded.jsep.wasm',
  '/onnxruntime-web/ort-wasm-simd-threaded.jsep.mjs',
  '/models/isnet_fp16',
  '/models/isnet_quint8',
]

const LIGHT = {
  url: 'https://github.com/danielgatis/rembg/releases/download/v0.0.0/silueta.onnx',
  sha256: '75da6c8d2f8096ec743d071951be73b4a8bc7b3e51d9a6625d63644f90ffeedb',
  size: 44173029,
}

const pkg = JSON.parse(await readFile(path.join(root, 'node_modules/@imgly/background-removal/package.json'), 'utf8'))
const CDN = `https://staticimgly.com/@imgly/background-removal-data/${pkg.version}/dist/`

async function get(url, tries = 4) {
  let err
  for (let i = 0; i < tries; i++) {
    try {
      const r = await fetch(url)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      return Buffer.from(await r.arrayBuffer())
    } catch (e) {
      err = e
      await new Promise((res) => setTimeout(res, 1000 * (i + 1)))
    }
  }
  throw new Error(`${url}: ${err.message}`)
}

async function have(file, size) {
  try { return (await stat(file)).size === size } catch { return false }
}

async function fetchLight() {
  const name = `silueta.${LIGHT.sha256.slice(0, 8)}.onnx`
  const file = path.join(outDir, name)
  try {
    if (!(await have(file, LIGHT.size))) {
      const buf = await get(LIGHT.url)
      if (buf.length !== LIGHT.size || createHash('sha256').update(buf).digest('hex') !== LIGHT.sha256) {
        throw new Error('does not match the pinned hash')
      }
      await mkdir(outDir, { recursive: true })
      await writeFile(file + '.part', buf)
      await rename(file + '.part', file)
    }
    await writeFile(path.join(outDir, 'light-model.json'), JSON.stringify({ name, size: LIGHT.size }))
    console.log(`bg-removal light model ready: ${name}`)
  } catch (e) {
    console.warn(`bg-removal light model NOT self-hosted (${e.message}); phones will use the ISNet model`)
  }
}

try {
  const all = JSON.parse((await get(CDN + 'resources.json')).toString('utf8'))
  const resources = {}
  for (const k of KEEP) {
    if (!all[k]) throw new Error(`resource ${k} missing from the ${pkg.version} manifest`)
    resources[k] = all[k]
  }

  const chunks = new Map()
  for (const entry of Object.values(resources)) {
    for (const c of entry.chunks) chunks.set(c.name, c.offsets[1] - c.offsets[0])
  }

  await mkdir(outDir, { recursive: true })
  const queue = [...chunks]
  let fetched = 0
  const worker = async () => {
    for (let item = queue.shift(); item; item = queue.shift()) {
      const [name, size] = item
      const file = path.join(outDir, name)
      if (await have(file, size)) continue
      const buf = await get(CDN + name)
      if (buf.length !== size) throw new Error(`${name}: expected ${size} bytes, got ${buf.length}`)
      // Chunk names are the sha256 of their content: check it, so a truncated or
      // swapped file can never be served as immutable for a year.
      if (createHash('sha256').update(buf).digest('hex') !== name) throw new Error(`${name}: hash mismatch`)
      await writeFile(file + '.part', buf)
      await rename(file + '.part', file)
      fetched++
    }
  }
  await Promise.all(Array.from({ length: 6 }, worker))

  // Written last: its presence tells the app the whole set is here.
  await writeFile(path.join(outDir, 'resources.json'), JSON.stringify(resources))
  console.log(`bg-removal assets ready: ${chunks.size} files (${fetched} downloaded) for ${pkg.version}`)
} catch (e) {
  console.warn(`bg-removal assets NOT self-hosted (${e.message}); the app will use the CDN`)
}

await fetchLight()
