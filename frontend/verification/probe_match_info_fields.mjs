// Bundles probe_match_info_fields.jsx with esbuild (shipped with Vite) and runs it.
import { build } from 'esbuild'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
const here = path.dirname(fileURLToPath(import.meta.url))
const outfile = path.join(process.env.TMPDIR || '/tmp', 'probe_match_info_fields.bundle.mjs')
await build({
  entryPoints: [path.join(here, 'probe_match_info_fields.jsx')], bundle: true, platform: 'node', format: 'esm', outfile,
  jsx: 'automatic', loader: { '.jsx': 'jsx', '.js': 'jsx', '.png': 'dataurl', '.svg': 'dataurl', '.css': 'empty' },
  define: { 'import.meta.env': JSON.stringify({ VITE_APP: '', MODE: 'production', DEV: false, PROD: true, BASE_URL: '/' }) },
  logLevel: 'error', nodePaths: [path.join(here, '..', 'node_modules')],
  banner: { js: "import { createRequire } from 'module'; const require = createRequire(import.meta.url);" },
})
const r = spawnSync('node', [outfile], { encoding: 'utf8' })
process.stdout.write(r.stdout); process.stderr.write(r.stderr); process.exit(r.status ?? 1)
