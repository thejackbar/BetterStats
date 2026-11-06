// The player page's availability tap must POST /public/availability/{token}/me, and `api` must not
// carry the same key twice (a later key silently replaces the earlier one in an object literal; v9.132.2
// reused `availPublicSet` for a card set and every availability answer became a GET for a set).
// Loads the real src/lib/api.js with `fetch` stubbed and records the exact request.
//   node verification/verify_avail_answer_request.mjs
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const apiPath = process.env.API_JS || path.join(here, '..', 'src', 'lib', 'api.js')
let src = fs.readFileSync(apiPath, 'utf8')

let pass = 0, fail = 0
const check = (name, ok, extra = '') => { ok ? pass++ : fail++; console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : '  ' + extra}`) }

// 1. No key of the api object is declared twice (two-space indent = the object's own members).
const seen = new Map()
for (const m of src.matchAll(/^  ([A-Za-z0-9_]+):/gm)) seen.set(m[1], (seen.get(m[1]) || 0) + 1)
const dupes = [...seen].filter(([, n]) => n > 1).map(([k]) => k)
check('api has no duplicate keys', dupes.length === 0, dupes.join(', '))

// 2. Run the real module with the build-time bits stubbed out.
src = src.replace(/^import .*$/gm, '').replace(/import\.meta\.env/g, '({ BASE_URL: "/" })')
src = 'const registerSeasons = () => {}\n' + src
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'avail-api-'))
const file = path.join(dir, 'api.mjs')
fs.writeFileSync(file, src)
const calls = []
globalThis.fetch = async (url, opts = {}) => {
  calls.push({ url: String(url), method: (opts.method || 'GET').toUpperCase(), body: opts.body })
  return new Response(JSON.stringify({}), { status: 200, headers: { 'content-type': 'application/json' } })
}
globalThis.window = globalThis.window || { location: { pathname: '/', search: '' }, addEventListener() {} }
globalThis.localStorage = globalThis.localStorage || { getItem: () => null, setItem() {}, removeItem() {} }
globalThis.sessionStorage = globalThis.sessionStorage || globalThis.localStorage
const { api } = await import(pathToFileURL(file).href)

const token = 'tok123'
const answer = { date: '2026-11-01', status: 'UNAVAILABLE' }
const read = (name) => (api && api[name]) || null
const send = read('availPublicSet')
try { if (send) await send(token, answer) } catch (e) { /* the request was still recorded */ }
const first = calls[0] || {}
check('availability answer is a POST', first.method === 'POST', `${first.method} ${first.url}`)
check('availability answer goes to /me', (first.url || '').endsWith(`/public/availability/${token}/me`), first.url)
check('availability answer carries the date and status', first.body === JSON.stringify(answer), String(first.body))

// 3. The card set page reads from the cards route, under its own name.
calls.length = 0
const set = read('availPublicCardSet')
check('card set reader exists under its own name', typeof set === 'function')
try { if (set) await set(token, 'tier:gold') } catch (e) { /* recorded */ }
const s = calls[0] || {}
check('card set read is a GET on /me/cards/sets/{key}', s.method === 'GET' && (s.url || '').endsWith('/me/cards/sets/tier%3Agold'), `${s.method} ${s.url}`)

fs.rmSync(dir, { recursive: true, force: true })
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
