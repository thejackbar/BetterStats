// Auto-assembled changelog. Each release lives in its own file in this folder
// so parallel feature branches never edit the same source line — Vite glob-
// imports them all and sorts by `sortKey` (ISO-8601 string, descending).
//
// Adding a new entry: drop a v-X-Y-Z.js file in this folder that default-exports
//   { version, date, sortKey, title, items }
// `sortKey` is a string sorted lexically; use `new Date().toISOString()` so two
// branches adding entries near-simultaneously can't collide. The file with the
// highest sortKey becomes CHANGELOG[0] and drives SITE_VERSION.

const modules = import.meta.glob('./v*.js', { eager: true })

export const CHANGELOG = Object.values(modules)
  .map((m) => m.default)
  .sort((a, b) => (a.sortKey < b.sortKey ? 1 : a.sortKey > b.sortKey ? -1 : 0))
