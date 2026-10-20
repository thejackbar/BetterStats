// The proof for per-element parts (social/layoutParts.js) on every BetterPosts layout.
//
//   node verification/probe_layout_parts.mjs baseline /path/base.json   (BEFORE editing a layout)
//   node verification/probe_layout_parts.mjs check    /path/base.json [ID ...]
//
// What `check` proves, per layout that has a fixture:
//   1. SAME  with no parts (undefined, {} and an unknown key) the output is byte for byte the baseline, at
//            square, portrait and story (or the fixture's own sizes).
//   2. WIRED every declared part changes the output when set (a colour appears verbatim, a text appears).
//            A part that cannot show on the fixture means the fixture is too poor: fix the fixture.
//   3. SPEC  every part has a key, label, kind, group; a colour part has `auto` (a function, or null with an
//            `autoLabel`); keys of one family never change kind between layouts.
//   4. LOOK  texture off and a different veil are rendered and reported (info, not a failure): TEXTURE shows the
//            pattern counts before/after, VEIL says whether the layout's fill follows the club's tint.
//   Exit status is non-zero on any FAIL.
import React from 'react'
import { renderToString } from 'react-dom/server'
import { readFileSync, writeFileSync } from 'node:fs'
import { FIXTURES } from './layout_parts/index.jsx'
import { LAYOUT_PARTS, PARTS_FAMILY, partsFor } from '../src/social/layoutParts.js'
import { PostLookContext } from '../src/social/postLook.js'
// Importing the template modules is what registers their parts.
import '../src/social/cricket-templates.jsx'
import '../src/social/round-templates.jsx'
import '../src/social/split-template.jsx'
import '../src/social/lineup-card-template.jsx'
import '../src/social/totw-templates.jsx'
import '../src/social/milestone-templates.jsx'
import '../src/social/result-glass-template.jsx'
import '../src/social/round-cover-template.jsx'
import '../src/social/giant-type-template.jsx'
import '../src/social/highlights-cover-template.jsx'
import '../src/social/event-templates.jsx'
import '../src/social/event-list-templates.jsx'
import '../src/social/launch-templates.jsx'

// Server rendering warns about useLayoutEffect on every AutoFit; it is noise here.
const realError = console.error
console.error = (...a) => { if (!/useLayoutEffect/.test(String(a[0]))) realError(...a) }
const [mode, file, ...only] = process.argv.slice(2)
const SIZES = [[1080, 1080], [1080, 1350], [1080, 1920]]
let pass = 0, fail = 0
const ck = (name, cond, extra = '') => { if (cond) { pass++; console.log(`PASS ${name}`) } else { fail++; console.log(`FAIL ${name}${extra ? `  ${extra}` : ''}`) } }
const info = (s) => console.log(`INFO ${s}`)

const sizesOf = (opts) => (opts && opts.sizes) || SIZES
function render(id, [C, props], [w, h], extra = {}, look = null) {
  const el = React.createElement(C, { width: w, height: h, ...props, ...extra })
  return renderToString(look ? React.createElement(PostLookContext.Provider, { value: look }, el) : el)
}
const ids = Object.keys(FIXTURES).filter((id) => !only.length || only.includes(id)).sort()

if (mode === 'baseline') {
  const out = {}
  for (const id of ids) {
    const [C, props, opts] = FIXTURES[id]
    for (const sz of sizesOf(opts)) {
      try { out[`${id}@${sz.join('x')}`] = render(id, [C, props], sz) } catch (e) { out[`${id}@${sz.join('x')}`] = `ERROR ${e.message}` }
    }
  }
  writeFileSync(file, JSON.stringify(out))
  console.log(`baseline: ${Object.keys(out).length} renders for ${ids.length} layouts -> ${file}`)
  const errs = Object.entries(out).filter(([, v]) => String(v).startsWith('ERROR'))
  errs.forEach(([k, v]) => console.log(`FAIL render ${k}: ${v.slice(0, 160)}`))
  process.exit(errs.length ? 1 : 0)
}

const base = mode === 'check' && file ? JSON.parse(readFileSync(file, 'utf8')) : null
// A colour no layout draws by itself, different for every part.
const marker = (n) => '#' + ((0x102030 + n * 0x0b0d11) & 0xffffff).toString(16).padStart(6, '0')
const count = (html, re) => (html.match(re) || []).length
const TEXTURE = /radial-gradient|repeating-linear-gradient|feTurbulence/g

const kindOfKey = {}
for (const id of Object.keys(LAYOUT_PARTS)) {
  const spec = LAYOUT_PARTS[id]
  ck(`${id}: has a fixture`, !!FIXTURES[id] || only.length > 0)
  const seen = new Set()
  for (const p of spec) {
    const okSpec = p.key && p.label && (p.kind === 'color' || p.kind === 'text') && p.group && !seen.has(p.key)
      && (p.kind === 'text' ? typeof p.auto === 'function' : (typeof p.auto === 'function' || (p.auto === null && p.autoLabel)))
    ck(`${id}.${p.key}: spec is complete`, !!okSpec, JSON.stringify({ ...p, auto: typeof p.auto }))
    seen.add(p.key)
    const fam = PARTS_FAMILY[id] || id
    const k = `${fam}.${p.key}`
    if (kindOfKey[k] && kindOfKey[k] !== p.kind) ck(`${k}: same kind in every layout of the family`, false, `${kindOfKey[k]} vs ${p.kind}`)
    kindOfKey[k] = p.kind
  }
}

for (const id of ids) {
  const fx = FIXTURES[id]
  const [C, props, opts] = fx
  const spec = partsFor(id) || []
  // 1. SAME
  if (base) {
    let same = true, why = ''
    for (const sz of sizesOf(opts)) {
      const key = `${id}@${sz.join('x')}`
      for (const [label, extra] of [['absent', {}], ['empty', { parts: {} }], ['unknown', { parts: { zzNotAPart: '#123456' } }]]) {
        const html = render(id, [C, props], sz, extra)
        if (html !== base[key]) { same = false; why = `${key} ${label}`; break }
      }
      if (!same) break
    }
    ck(`${id}: no parts renders byte for byte as before`, same, why)
  }
  // 2. WIRED
  const sq = sizesOf(opts)[0]
  const plain = render(id, [C, props], sq)
  spec.forEach((p, n) => {
    const v = p.kind === 'text' ? `ZZ${p.key.toUpperCase()}ZZ` : marker(n + 1 + id.length)
    let html = ''
    try { html = render(id, [C, props], sq, { parts: { [p.key]: v } }) } catch (e) { html = `ERROR ${e.message}` }
    const changed = html !== plain
    const shows = p.kind === 'text' ? html.includes(v) : html.toLowerCase().includes(v.toLowerCase())
    ck(`${id}.${p.key}: setting it changes the post`, changed && shows, !changed ? 'output did not change (not wired, or not on the fixture)' : !shows ? 'changed but the value is not in the output' : html.slice(0, 100))
  })
  if (!spec.length) info(`${id}: no parts declared`)
  // 4. LOOK
  const tex0 = count(plain, TEXTURE)
  const off = render(id, [C, props], sq, {}, { veil: null, texture: false })
  info(`TEXTURE ${id}: ${tex0} pattern(s) -> ${count(off, TEXTURE)} with the layout texture off`)
  const veilProps = { ...props, palette: { ...props.palette, primary: `${props.palette.primary}99` } }
  const v99 = render(id, [C, veilProps], sq, {}, { veil: '99', texture: true })
  const v33 = render(id, [C, veilProps], sq, {}, { veil: '33', texture: true })
  info(`VEIL ${id}: ${v33 !== v99 ? 'follows the club tint' : 'fill does not follow the tint (photo-led or own fill)'}`)
}
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
