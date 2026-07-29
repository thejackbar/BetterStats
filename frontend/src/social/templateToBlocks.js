// Convert a built-in template into a set of freeform Blank-Canvas blocks so the
// whole thing becomes movable/editable in the WYSIWYG editor ("Custom Edit").
// Bespoke templates can't be auto-decomposed, so these are faithful item-based
// recreations of the single-subject "companion" post types, seeded with the
// post's current content. Returns null for templates without a recreation
// (the caller falls back to overlay-on-top editing for those).
import { newBlankItem } from './blank-template'

const T = (text, o = {}) => ({ ...newBlankItem('text'), text: text || '', bold: true, uppercase: true, ...o })
const BODY = (text, o = {}) => ({ ...newBlankItem('text'), text: text || '', bold: false, uppercase: false, fontFamily: "'Inter', sans-serif", lineHeight: 1.2, ...o })
const EL = (shape, o = {}) => ({ ...newBlankItem('element', { shape }), ...o })
const BR = (o = {}) => ({ ...newBlankItem('brand'), ...o })

export const CUSTOM_EDITABLE = ['C1', 'C2', 'C3', 'C4']

export function templateToBlocks(templateId, ctx = {}) {
  const { team = {}, match = {}, announcement = {}, toss = {}, motm = {}, result = {} } = ctx

  if (templateId === 'C1') {
    const p = announcement.player || {}
    return [
      BR({ x: 700, y: 56, size: 150, layout: 'stack', align: 'right' }),
      T(announcement.kind || 'ANNOUNCEMENT', { x: 70, y: 70, w: 420, fontSize: 34, color: 'accent' }),
      EL('line', { x: 70, y: 470, w: 260, h: 10, thickness: 10, color: 'accent' }),
      T(announcement.headline || 'NAMED', { x: 70, y: 520, w: 940, fontSize: 56, color: 'accent' }),
      T(p.first || 'PLAYER', { x: 70, y: 600, w: 940, fontSize: 64, color: 'ink' }),
      T(p.last || 'NAME', { x: 70, y: 668, w: 960, fontSize: 150, color: 'ink' }),
      announcement.subheadline ? T(announcement.subheadline, { x: 72, y: 880, w: 860, fontSize: 40, color: 'accent' }) : null,
      T(team.fullName || team.name || 'CLUB', { x: 70, y: 1000, w: 900, fontSize: 30, color: 'ink' }),
    ].filter(Boolean)
  }

  if (templateId === 'C2') {
    const oppWon = toss.winner === 'OPPONENT'
    const winner = oppWon ? (toss.oppName || 'OPPONENT') : (toss.teamName || team.name || 'US')
    const decision = (toss.decision || 'BAT').toUpperCase()
    return [
      BR({ x: 60, y: 56, size: 120, layout: 'row' }),
      T(`${winner} WON THE TOSS`, { x: 70, y: 300, w: 940, fontSize: 40, color: 'primary', bg: 'accent' }),
      T(oppWon ? "THEY'RE" : "WE'RE", { x: 70, y: 400, w: 940, fontSize: 80, color: 'ink' }),
      T(decision, { x: 70, y: 490, w: 960, fontSize: 200, color: 'ink' }),
      T('FIRST', { x: 70, y: 710, w: 940, fontSize: 72, color: 'accent' }),
      T(`${toss.teamName || team.name || 'US'} V ${toss.oppName || 'OPPONENT'}`, { x: 70, y: 840, w: 940, fontSize: 40, color: 'ink' }),
      BODY(`${match.date || ''} · ${match.venue || ''}`, { x: 72, y: 920, w: 900, fontSize: 30, color: 'ink' }),
    ]
  }

  if (templateId === 'C3') {
    const p = motm.player || {}
    const stats = (motm.stats || []).slice(0, 4)
    const statBlocks = stats.map((s, i) => T(`${s.value}  ${s.label}`, { x: 70 + (i % 2) * 470, y: 760 + Math.floor(i / 2) * 110, w: 440, fontSize: 56, color: i === 0 ? 'accent' : 'ink' }))
    return [
      BR({ x: 760, y: 56, size: 130, layout: 'stack', align: 'right' }),
      T('★ MAN OF THE MATCH', { x: 70, y: 70, w: 640, fontSize: 30, color: 'accent' }),
      T(p.first || 'PLAYER', { x: 70, y: 470, w: 940, fontSize: 44, color: 'ink' }),
      T(p.last || 'NAME', { x: 70, y: 530, w: 960, fontSize: 124, color: 'ink' }),
      p.role ? BODY(String(p.role).toUpperCase(), { x: 74, y: 690, w: 700, fontSize: 26, color: 'accent', fontFamily: "'JetBrains Mono', monospace" }) : null,
      ...statBlocks,
      motm.summary ? BODY(`“${motm.summary}”`, { x: 70, y: 980, w: 900, fontSize: 28, color: 'ink' }) : null,
    ].filter(Boolean)
  }

  if (templateId === 'C4') {
    const oppWon = result.winner === 'OPPONENT'
    const tie = result.winner === 'TIE'
    const winLine = tie ? 'MATCH TIED' : `${oppWon ? (result.oppName || 'OPPONENT') : (result.teamName || team.name || 'US')} WIN ${result.margin || ''}`.trim()
    return [
      BR({ x: 700, y: 56, size: 120, layout: 'stack', align: 'right' }),
      T('FULL TIME', { x: 70, y: 70, w: 420, fontSize: 34, color: 'accent' }),
      T(`${result.teamName || team.name || 'US'}`, { x: 70, y: 300, w: 700, fontSize: 48, color: 'ink' }),
      T(result.teamScore || '—', { x: 70, y: 360, w: 700, fontSize: 96, color: 'ink' }),
      T(`${result.oppName || 'OPPONENT'}`, { x: 70, y: 520, w: 700, fontSize: 48, color: 'ink' }),
      T(result.oppScore || '—', { x: 70, y: 580, w: 700, fontSize: 96, color: 'ink' }),
      T(winLine, { x: 70, y: 760, w: 960, fontSize: 60, color: 'accent' }),
      result.motmLast ? BODY(`★ MOTM · ${result.motmLast}`, { x: 72, y: 900, w: 900, fontSize: 32, color: 'ink', fontFamily: "'JetBrains Mono', monospace" }) : null,
    ].filter(Boolean)
  }

  return null
}
