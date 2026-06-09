// Alphabet grouping for the admin player lists — surname-keyed A–Z buckets,
// range tabs (A–E · F–J · K–O · P–T · U–Z), and a grouping helper. Shared by
// Cricket Data → Players and BetterSelect → Players so both order/group players
// identically. Keys off nameSortKey so it matches the backend's surname sort.
import { nameSortKey } from './nameFormat'

export const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')

// `key` avoids special chars (used in state/ids); `label` is the pretty en-dash.
export const RANGES = [
  { key: 'AE', label: 'A–E', from: 'A', to: 'E' },
  { key: 'FJ', label: 'F–J', from: 'F', to: 'J' },
  { key: 'KO', label: 'K–O', from: 'K', to: 'O' },
  { key: 'PT', label: 'P–T', from: 'P', to: 'T' },
  { key: 'UZ', label: 'U–Z', from: 'U', to: 'Z' },
]

// First letter of the surname (non-alphabetic surnames bucket under '#').
export function letterOfName(name) {
  const key = nameSortKey(name || '')
  const c = (key.trim()[0] || '#').toUpperCase()
  return /[A-Z]/.test(c) ? c : '#'
}

export function rangeOfLetter(letter) {
  const L = letter || '#'
  const r = RANGES.find((rg) => L >= rg.from && L <= rg.to)
  return r ? r.key : RANGES[0].key // '#' and anything else falls into the first bucket
}

export function rangeOfName(name) {
  return rangeOfLetter(letterOfName(name))
}

// Group an ALREADY-SORTED list into [letter, players[]] pairs, letters ascending.
export function groupByLetter(sortedList, nameOf) {
  const m = new Map()
  for (const p of sortedList) {
    const L = letterOfName(nameOf(p))
    if (!m.has(L)) m.set(L, [])
    m.get(L).push(p)
  }
  return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]))
}
