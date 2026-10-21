// Writes dist/changelog.json at build time, from the same release files the
// What's New page reads (src/data/changelog/v*.js).
//
// WHY: the backend image holds no frontend source, and the daily product update
// (backend/app/services/product_blast.py) needs the release notes. Publishing the
// built changelog next to the site means it can only ever announce what is
// actually deployed. Only the fields the What's New page already shows go out.
import { readdirSync, writeFileSync, mkdirSync } from 'node:fs'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

// Newest releases published. Far more than a week of releases.
const RECENT_ENTRIES = 200

export default function emitChangelog() {
  let root = process.cwd()
  let outDir = 'dist'
  return {
    name: 'emit-changelog',
    apply: 'build',
    configResolved(config) {
      root = config.root
      outDir = path.resolve(config.root, config.build.outDir)
    },
    async closeBundle() {
      const dir = path.resolve(root, 'src/data/changelog')
      const entries = []
      for (const file of readdirSync(dir).filter((f) => /^v.*\.js$/.test(f))) {
        const mod = await import(pathToFileURL(path.join(dir, file)).href)
        const e = mod.default
        if (e && e.version) {
          entries.push({
            version: e.version,
            date: e.date,
            sortKey: e.sortKey,
            title: e.title,
            items: Array.isArray(e.items) ? e.items : [],
          })
        }
      }
      entries.sort((a, b) => (a.sortKey < b.sortKey ? 1 : a.sortKey > b.sortKey ? -1 : 0))
      mkdirSync(outDir, { recursive: true })
      // The daily update only ever looks a week back, so the whole history (nearly
      // a megabyte) is not worth fetching every morning.
      writeFileSync(path.join(outDir, 'changelog.json'), JSON.stringify(entries.slice(0, RECENT_ENTRIES)))
      // The whole history, read only when a super admin runs the backfill.
      writeFileSync(path.join(outDir, 'changelog-all.json'), JSON.stringify(entries))
    },
  }
}
