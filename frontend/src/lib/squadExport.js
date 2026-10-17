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

/* The squads, placed on ONE landscape page, as many columns as the names need.
 *
 * Every squad is a block of numbered names. The blocks flow down columns, and the
 * type size and the number of columns are worked out together: the biggest type
 * that still puts every name on the page, with the fewest columns that manage it.
 * Columns are then balanced (a 41-name squad is three columns of 14, not 18, 18
 * and 5) and each is only as wide as its longest name plus its role, so the sheet
 * is names, not white space. A long squad may carry over into the next column.
 * Only if even the smallest readable type cannot hold the lot does it run onto a
 * second page. */
const SHORT_ROLE = { BAT: 'BAT', BOWL: 'BWL', AR: 'AR', WKT: 'WK' }
const roleShort = (p) => (p.skill_positions || []).map((x) => SHORT_ROLE[x] || x).join(' ')
const SIZES = [12, 11.5, 11, 10.5, 10, 9.5, 9, 8.5, 8, 7.5, 7, 6.5]
const COL_GAP = 22
const MAX_GAP = 44

// `text` cut to fit `maxW` points, with an ellipsis when it had to be.
export function fitText(text, size, bold, maxW) {
  if (sheetTextWidth(text, size, bold) <= maxW) return text
  let t = text
  while (t.length > 1 && sheetTextWidth(`${t}…`, size, bold) > maxW) t = t.slice(0, -1)
  return `${t.trimEnd()}…`
}

export function planSquadSheet(items, { width, height }) {
  const total = items.reduce((n, it) => n + it.rows.length, 0)
  const hasRoles = items.some((it) => it.rows.some((r) => r.role))
  const metrics = (f) => {
    const numW = Math.max(...items.map((it) => sheetTextWidth(String(it.rows.length || 0), f, false)), sheetTextWidth('99', f, false))
    let nameW = 0
    let roleW = 0
    for (const it of items) for (const r of it.rows) {
      nameW = Math.max(nameW, sheetTextWidth(r.name, f, false))
      if (r.role) roleW = Math.max(roleW, sheetTextWidth(r.role, f - 1.5, false))
    }
    const headW = Math.max(...items.map((it) => sheetTextWidth(it.name, f + 1.5, true) + sheetTextWidth(String(it.rows.length), f, false) + 14), 0)
    const need = Math.max(numW + 5 + nameW + (hasRoles ? 10 + roleW : 0) + 4, Math.min(headW, 190))
    return { numW, nameW, roleW, need }
  }
  // Blocks into columns of `perCol` lines. A block is kept whole when it fits what is
  // left of its column, else started fresh, else (longer than a column) split.
  const pack = (perCol, maxCols) => {
    const cols = [[]]
    let used = 0
    const take = (line) => {
      if (used + line.h > perCol + 1e-6 && cols[cols.length - 1].length) {
        cols.push([]); used = 0
        // A squad carried over into a new column says whose names these are.
        if (line.row && !items[0].solo) { cols[cols.length - 1].push({ h: 1.7, head: `${line.squad} (cont.)`, count: null }); used = 1.7 }
      }
      cols[cols.length - 1].push(line); used += line.h
    }
    items.forEach((it, i) => {
      const block = it.rows.length + 1.7
      if (block > perCol - used && block <= perCol && cols[cols.length - 1].length) { cols.push([]); used = 0 }
      // A lone squad needs no heading over its columns: its name is the page title.
      if (!it.solo) take({ h: 1.7, head: it.name, grades: it.grades, count: it.rows.length })
      it.rows.forEach((r) => take({ h: 1, row: r, count: it.rows.length, squad: it.name }))
      if (i < items.length - 1) take({ h: 0.6, gap: true })
    })
    return cols.length <= maxCols ? cols : null
  }
  const attempt = (f, k) => {
    const m = metrics(f)
    const lineH = f * 1.36
    const perColMax = Math.floor(height / lineH)
    if (m.need * k + COL_GAP * (k - 1) > width + 1e-6) return null
    let cols = pack(perColMax, k)
    if (!cols) return null
    // Balance: the shortest column height that still fits in k columns.
    for (let per = Math.max(Math.ceil(total / k), 4); per < perColMax; per++) {
      const tight = pack(per, k)
      if (tight) { cols = tight; break }
    }
    const colW = Math.min((width - COL_GAP * (k - 1)) / k, m.need * 1.25)
    return { f, k, lineH, colW, ...m, cols: cols.filter((c) => c.length), pages: 1 }
  }
  for (const f of SIZES) {
    const m = metrics(f)
    const kmax = Math.max(1, Math.floor((width + COL_GAP) / (m.need + COL_GAP)))
    for (let k = 1; k <= kmax; k++) {
      const hit = attempt(f, k)
      if (hit) return hit
    }
  }
  // Too much for one page even in the smallest type: fill pages of the widest
  // arrangement the smallest type allows.
  const f = SIZES[SIZES.length - 1]
  const m = metrics(f)
  const k = Math.max(1, Math.floor((width + COL_GAP) / (m.need + COL_GAP)))
  const lineH = f * 1.36
  const perCol = Math.floor(height / lineH)
  const all = pack(perCol, 1e9)
  return { f, k, lineH, colW: Math.min((width - COL_GAP * (k - 1)) / k, m.need * 1.25), ...m, cols: all, pages: Math.ceil(all.length / k) }
}

export async function downloadSquadPdf({ club, squads, order, fmt }) {
  const logo = await clubLogoJpeg(club?.logo_url || club?.logo, { maxWidth: 150, maxHeight: 40 })
  const cfg = club?.theme_config || {}
  const theme = { accent: cfg.accent || club?.accent_color || club?.primary_color, accent2: cfg.accent2 || club?.accent_color }
  const accent = hex6(theme.accent) ? `#${hex6(theme.accent)}` : '#16c784'
  const one = squads.length === 1
  const items = squads.map(({ team, members }) => ({
    name: team.name,
    grades: team.grade_name || '',
    solo: one,
    rows: orderPlayers(members, order).map((p, i) => ({ n: i + 1, name: fmt(p.display_name || p.name || ''), role: roleShort(p) })),
  }))
  downloadSheetPdf({
    filename: docFilename(club?.short_name || club?.name, one ? squads[0].team.name : 'squads'),
    title: `${club?.name || 'Club'}: ${one ? `${squads[0].team.name} squad` : 'squad lists'}`,
    subtitle: `Printed ${today()}`,
    header: letterhead(theme, logo),
    place: ({ G, top, width, height }) => {
      // One squad: a single grey line across the page names its grades and how many.
      const lead = one
        ? [items[0].grades ? `${items[0].grades}  ·  ` : '', `${items[0].rows.length} player${items[0].rows.length === 1 ? '' : 's'}`].join('')
        : ''
      const leadH = lead ? 20 : 0
      const plan = planSquadSheet(items, { width, height: height - 4 - leadH })
      const { f, k, lineH, colW, cols, numW, nameW } = plan
      const pages = []
      const perPage = k
      const used = Math.min(k, cols.length)
      const gap = used > 1 ? Math.min(MAX_GAP, Math.max(COL_GAP, (width - used * colW) / (used - 1))) : 0
      const x0 = G.margin + Math.max(0, (width - (used * colW + (used - 1) * gap)) / 2)
      cols.forEach((col, ci) => {
        const pi = Math.floor(ci / perPage)
        const x = x0 + (ci % perPage) * (colW + gap)
        if (!pages[pi]) {
          pages[pi] = []
          if (lead) pages[pi].push({ kind: 'text', text: fitText(lead, f, false, width), size: Math.min(f, 10.5), grey: true, centre: true, y: top - 11 })
        }
        let y = top - leadH
        col.forEach((ln) => {
          if (ln.gap) {
            y -= lineH * ln.h
          } else if (ln.head) {
            y -= lineH * 1.15
            const count = ln.count != null ? String(ln.count) : ''
            const room = colW - (count ? sheetTextWidth(count, f, false) + 10 : 0)
            const label = fitText(ln.grades && sheetTextWidth(`${ln.head} (${ln.grades})`, f + 1.5, true) <= room ? `${ln.head} (${ln.grades})` : ln.head, f + 1.5, true, room)
            pages[pi].push({ kind: 'text', text: label, size: f + 1.5, bold: true, colour: accent, x, y: y + 2 })
            if (count) pages[pi].push({ kind: 'text', text: count, size: f, grey: true, rightX: x + colW, y: y + 2 })
            pages[pi].push({ kind: 'hline', x1: x, x2: x + colW, y: y - 1.5, colour: accent, width: 0.8 })
            y -= lineH * 0.55
          } else {
            y -= lineH
            const r = ln.row
            pages[pi].push({ kind: 'text', text: String(r.n), size: f, grey: true, rightX: x + numW, y })
            pages[pi].push({ kind: 'text', text: r.name, size: f, x: x + numW + 5, y })
            // Roles line up in one column just past the longest name.
            if (r.role) pages[pi].push({ kind: 'text', text: r.role, size: f - 1.5, grey: true, x: x + numW + 5 + nameW + 10, y })
          }
        })
      })
      return pages.length ? pages : [[]]
    },
  })
}
