// Squad lists as a file: CSV for a spreadsheet, PDF for the noticeboard.
//
// Written in the browser from the squads on screen (like the committee minutes
// in textDocs.js), so the file always matches what the selector is looking at.
// The header names the club, the squad and the date, because a printout with no
// header is a list of names nobody can place a week later.
import { downloadSheetPdf, sheetTextWidth, clubLogoJpeg, docFilename, hex6 } from './textDocs'
import { letterhead } from '../components/admin/clubmanager/minutesDoc'
import { nameSortKey, sortByFirstName } from './nameFormat'

const ROLE_LABEL = { BAT: 'Batter', BOWL: 'Bowler', AR: 'All-rounder', WKT: 'Keeper' }

function roleText(p) {
  const r = (p.skill_positions || []).map((x) => ROLE_LABEL[x] || x)
  if (r.length) return r.join(', ')
  return p.player_role ? String(p.player_role).replace(/_/g, ' ') : ''
}

/* Players of one squad in the order asked for: 'first' (A to Z by first name),
 * 'last' (A to Z by surname), or as given. */
export function orderPlayers(players, order = 'first') {
  const nameOf = (p) => p.display_name || p.name || ''
  if (order === 'first') return sortByFirstName(players, nameOf)
  if (order === 'last') return [...players].sort((a, b) => nameSortKey(nameOf(a)).localeCompare(nameSortKey(nameOf(b))))
  return players
}

/* squads: [{ team, members }] -> rows [{ squad, grade, no, name, roles }] */
export function squadRows(squads, { order = 'first', fmt = (n) => n } = {}) {
  const rows = []
  for (const { team, members } of squads) {
    orderPlayers(members, order).forEach((p, i) => {
      rows.push({
        squad: team.name, grade: team.grade_name || '', no: i + 1,
        name: fmt(p.display_name || p.name || ''), roles: roleText(p),
        shirt: p.shirt_number || '',
      })
    })
  }
  return rows
}

const csvCell = (v) => {
  const s = String(v ?? '')
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

function save(text, mime, filename) {
  const url = URL.createObjectURL(new Blob([text], { type: mime }))
  const a = document.createElement('a')
  a.href = url; a.download = filename
  document.body.appendChild(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

const today = () => new Date().toLocaleDateString('en-AU', { day: 'numeric', month: 'long', year: 'numeric' })

export function downloadSquadCsv({ club, squads, order, fmt }) {
  const rows = squadRows(squads, { order, fmt })
  const head = ['Squad', 'Grade', '#', 'Shirt', 'Player', 'Role']
  // Header rows first, so the file says whose list it is when opened cold.
  const lines = [
    [`${club?.name || 'Club'} squad lists`],
    [`Printed ${today()}`],
    [],
    head,
    ...rows.map((r) => [r.squad, r.grade, r.no, r.shirt, r.name, r.roles]),
  ]
  // BOM so Excel reads names with accents as UTF-8.
  const csv = '﻿' + lines.map((l) => l.map(csvCell).join(',')).join('\r\n')
  save(csv, 'text/csv;charset=utf-8', docFilename(club?.short_name || club?.name, 'squads') + '.csv')
}

/* The squads, placed on ONE landscape page. Every squad is a block of numbered
 * names. The blocks flow down a number of columns, and the number of columns
 * and the type size are worked out together: the biggest type that still puts
 * every name on the page, with the fewest columns that manage it. A long squad
 * may carry over into the next column. Only if even the smallest readable type
 * cannot hold the lot does it run onto a second page. */
const SHORT_ROLE = { BAT: 'BAT', BOWL: 'BWL', AR: 'AR', WKT: 'WK' }
const roleShort = (p) => (p.skill_positions || []).map((x) => SHORT_ROLE[x] || x).join(' ')
const SIZES = [10.5, 10, 9.5, 9, 8.5, 8, 7.5, 7, 6.5]
const COL_GAP = 20
const MAX_COL = 230

export function planSquadSheet(items, { width, height }) {
  const need = (f) => {
    let w = 0
    for (const it of items) for (const r of it.rows) w = Math.max(w, sheetTextWidth(r.name, f, false) + sheetTextWidth(String(it.rows.length), f, false) + 10)
    for (const it of items) w = Math.max(w, sheetTextWidth(it.heading, f + 1.5, true) + 18)
    return w
  }
  // Pack blocks into columns of `perCol` lines. A block is kept whole when it fits in
  // what is left of its column, else started fresh, else (longer than a column) split.
  const pack = (f, perCol, maxCols) => {
    const cols = [[]]
    let used = 0
    const take = (line) => {
      if (used + line.h > perCol + 1e-6 && cols[cols.length - 1].length) {
        cols.push([]); used = 0
        // A squad carried over into a new column says whose names these are.
        if (line.row) { cols[cols.length - 1].push({ h: 1.7, head: `${line.squad} (cont.)`, count: null }); used = 1.7 }
      }
      cols[cols.length - 1].push(line); used += line.h
    }
    for (const it of items) {
      const block = it.rows.length + 1.7
      const left = perCol - used
      if (block > left && block <= perCol && cols[cols.length - 1].length) { cols.push([]); used = 0 }
      take({ h: 1.7, head: it.heading, count: it.rows.length })
      it.rows.forEach((r) => take({ h: 1, row: r, count: it.rows.length, squad: it.heading }))
      take({ h: 0.6, gap: true })
    }
    // A column that opens with a row (a split squad) is marked so it can say "cont."
    return cols.length <= maxCols ? cols : null
  }
  const attempt = (f, k) => {
    const lineH = f * 1.36
    const perCol = Math.floor(height / lineH)
    const colW = Math.min(MAX_COL, (width - COL_GAP * (k - 1)) / k)
    if (colW < need(f)) return null
    const cols = pack(f, perCol, k)
    return cols ? { f, k, lineH, colW, cols, pages: 1 } : null
  }
  for (const f of SIZES) {
    for (let k = 1; k <= 8; k++) {
      const hit = attempt(f, k)
      if (hit) return hit
    }
  }
  // Too much for one page even in the smallest type: fill pages of the widest
  // arrangement the smallest type allows.
  const f = SIZES[SIZES.length - 1]
  let k = 8
  while (k > 1 && (width - COL_GAP * (k - 1)) / k < need(f)) k -= 1
  const lineH = f * 1.36
  const perCol = Math.floor(height / lineH)
  const colW = Math.min(MAX_COL, (width - COL_GAP * (k - 1)) / k)
  const all = pack(f, perCol, 1e9)
  return { f, k, lineH, colW, cols: all, pages: Math.ceil(all.length / k) }
}

export async function downloadSquadPdf({ club, squads, order, fmt }) {
  const logo = await clubLogoJpeg(club?.logo_url || club?.logo, { maxWidth: 150, maxHeight: 40 })
  const cfg = club?.theme_config || {}
  const theme = { accent: cfg.accent || club?.accent_color || club?.primary_color, accent2: cfg.accent2 || club?.accent_color }
  const accent = hex6(theme.accent) ? `#${hex6(theme.accent)}` : '#16c784'
  const items = squads.map(({ team, members }) => ({
    heading: `${team.name}${team.grade_name ? ` (${team.grade_name})` : ''}`,
    rows: orderPlayers(members, order).map((p, i) => ({ n: i + 1, name: fmt(p.display_name || p.name || ''), role: roleShort(p) })),
  }))
  const one = squads.length === 1
  downloadSheetPdf({
    filename: docFilename(club?.short_name || club?.name, one ? squads[0].team.name : 'squads'),
    title: `${club?.name || 'Club'}: ${one ? `${squads[0].team.name} squad` : 'squad lists'}`,
    subtitle: `Printed ${today()}`,
    header: letterhead(theme, logo),
    place: ({ G, top, width, height }) => {
      const plan = planSquadSheet(items, { width, height: height - 4 })
      const { f, k, lineH, colW, cols } = plan
      const pages = []
      cols.forEach((col, ci) => {
        const pi = Math.floor(ci / k)
        const x = G.margin + (ci % k) * (colW + COL_GAP)
        if (!pages[pi]) pages[pi] = []
        let y = top
        col.forEach((ln) => {
          if (ln.gap) {
            y -= lineH * ln.h
          } else if (ln.head) {
            y -= lineH * 1.15
            pages[pi].push({ kind: 'text', text: ln.head, size: f + 1.5, bold: true, colour: accent, x, y: y + 2 })
            if (ln.count != null) pages[pi].push({ kind: 'text', text: String(ln.count), size: f, grey: true, rightX: x + colW, y: y + 2 })
            pages[pi].push({ kind: 'hline', x1: x, x2: x + colW, y: y - 1.5, colour: accent, width: 0.8 })
            y -= lineH * 0.55
          } else {
            y -= lineH
            const r = ln.row
            const numW = sheetTextWidth(String(ln.count), f, false)
            pages[pi].push({ kind: 'text', text: String(r.n), size: f, grey: true, rightX: x + numW, y })
            pages[pi].push({ kind: 'text', text: r.name, size: f, x: x + numW + 5, y })
            const free = colW - numW - 5 - sheetTextWidth(r.name, f, false) - 8
            if (r.role && sheetTextWidth(r.role, f - 1.5, false) <= free) {
              pages[pi].push({ kind: 'text', text: r.role, size: f - 1.5, grey: true, rightX: x + colW, y })
            }
          }
        })
      })
      return pages.length ? pages : [[]]
    },
  })
}
