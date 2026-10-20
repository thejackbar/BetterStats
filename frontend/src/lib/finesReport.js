// The Fines report as a PDF: a summary per player, every fine by session with its
// reason and note, and the payments. Written in the browser from the report the
// server sends (GET /fines/squads/:id/report), so the file matches the screen.
import { downloadPdf, clubLogoJpeg, docFilename, hex6 } from './textDocs'
import { letterhead } from '../components/admin/clubmanager/minutesDoc'

const money = (n) => `${n < 0 ? '-' : ''}$${Math.abs(Number(n) || 0).toFixed(2)}`
const longDate = (iso) => {
  try { return new Date(iso + 'T00:00:00').toLocaleDateString('en-AU', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }) } catch { return iso }
}
const dayMonth = (iso) => {
  try { return new Date(iso + 'T00:00:00').toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' }) } catch { return iso }
}

export function rangeText(rep) {
  if (rep.from && rep.to) return `${dayMonth(rep.from)} to ${dayMonth(rep.to)}`
  if (rep.from) return `From ${dayMonth(rep.from)}`
  if (rep.to) return `Up to ${dayMonth(rep.to)}`
  return 'All dates'
}

// The blocks of the document, separate from the download so a check can read them.
export function finesReportBlocks(rep) {
  const blocks = []
  const t = rep.totals
  blocks.push({ type: 'para', text: `${t.count} fine${t.count === 1 ? '' : 's'} totalling ${money(t.fined)}. Paid in this period: ${money(t.paid)}. Still to collect from the whole squad: ${money(t.owing_now)}.` })

  blocks.push({ type: 'heading', text: 'Summary by player' })
  if (rep.summary.length === 0) {
    blocks.push({ type: 'para', text: 'No fines or payments in this period.', muted: true })
  } else {
    blocks.push({
      type: 'table', widths: [3, 1, 1.4, 1.4, 1.6],
      header: ['Player', 'Fines', 'Fined', 'Paid', 'Balance to date'],
      rows: [
        ...rep.summary.map((r) => [r.name, String(r.count), money(r.fined), money(r.paid), r.owing_now > 0 ? money(r.owing_now) : r.owing_now < 0 ? `${money(-r.owing_now)} credit` : 'Square']),
        ['Total', String(t.count), money(t.fined), money(t.paid), ''],
      ],
    })
  }

  blocks.push({ type: 'heading', text: 'Every fine' })
  if (rep.sessions.length === 0) blocks.push({ type: 'para', text: 'None in this period.', muted: true })
  for (const s of rep.sessions) {
    blocks.push({ type: 'label', text: `${longDate(s.date)}   ${money(s.total)}` })
    blocks.push({
      type: 'table', widths: [2.2, 2.2, 3, 1.2],
      header: ['Player', 'Fine', 'Note', 'Amount'],
      rows: s.entries.map((e) => [e.player, e.reason, e.note || '', money(e.amount)]),
    })
  }

  if (rep.payments.length > 0) {
    blocks.push({ type: 'heading', text: 'Payments into the pot' })
    blocks.push({
      type: 'table', widths: [1.6, 2.4, 1.6, 2.6, 1.2],
      header: ['Date', 'Player', 'How', 'Note', 'Amount'],
      rows: rep.payments.map((p) => [dayMonth(p.date), p.player, p.method || '', p.note || '', money(p.amount)]),
    })
  }

  blocks.push({
    type: 'para', muted: true, italic: true,
    text: 'Voided fines and payments are left out. Balance to date is each player\'s whole balance, not limited to the dates above.'
      + (rep.truncated ? ' This report was cut at 5,000 rows; narrow the dates for the rest.' : ''),
  })
  return blocks
}

export async function downloadFinesReport({ club, rep }) {
  const logo = await clubLogoJpeg(club?.logo_url || club?.logo, { maxWidth: 150, maxHeight: 40 })
  const cfg = club?.theme_config || {}
  const theme = { accent: cfg.accent || club?.accent_color || club?.primary_color, accent2: cfg.accent2 || club?.accent_color }
  const accent = hex6(theme.accent) ? `#${hex6(theme.accent)}` : '#16c784'
  downloadPdf({
    filename: docFilename(club?.short_name || club?.name, rep.squad.name, 'fines report'),
    title: `${club?.name || 'Club'}: ${rep.squad.name} fines report`,
    subtitle: `${rangeText(rep)}  ·  Printed ${new Date().toLocaleDateString('en-AU', { day: 'numeric', month: 'long', year: 'numeric' })}`,
    header: letterhead({ accent, accent2: hex6(theme.accent2) ? `#${hex6(theme.accent2)}` : accent }, logo),
    blocks: finesReportBlocks(rep),
  })
}
