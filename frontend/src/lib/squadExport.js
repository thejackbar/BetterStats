// Squad lists as a file: CSV for a spreadsheet, PDF for the noticeboard.
//
// Written in the browser from the squads on screen (like the committee minutes
// in textDocs.js), so the file always matches what the selector is looking at.
// The header names the club, the squad and the date, because a printout with no
// header is a list of names nobody can place a week later.
import { downloadPdf, clubLogoJpeg, docFilename } from './textDocs'
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

export async function downloadSquadPdf({ club, squads, order, fmt }) {
  const logo = await clubLogoJpeg(club?.logo_url || club?.logo)
  const cfg = club?.theme_config || {}
  const theme = { accent: cfg.accent || club?.primary_color, accent2: cfg.accent2 || club?.accent_color }
  const blocks = []
  squads.forEach(({ team, members }, i) => {
    blocks.push({ type: 'heading', text: `${team.name}${team.grade_name ? ` (${team.grade_name})` : ''} · ${members.length} player${members.length === 1 ? '' : 's'}` })
    const rows = squadRows([{ team, members }], { order, fmt })
    blocks.push(rows.length
      ? { type: 'table', header: ['#', 'Player', 'Role'], widths: [1, 6, 4], rows: rows.map((r) => [String(r.no), r.name, r.roles]) }
      : { type: 'para', text: 'No players in this squad.', muted: true })
    if (i < squads.length - 1) blocks.push({ type: 'spacer' })
  })
  const one = squads.length === 1
  downloadPdf({
    filename: docFilename(club?.short_name || club?.name, one ? squads[0].team.name : 'squads') + '.pdf',
    title: `${club?.name || 'Club'}: ${one ? `${squads[0].team.name} squad` : 'squad lists'}`,
    subtitle: `Printed ${today()}`,
    blocks,
    header: letterhead(theme, logo),
  })
}
