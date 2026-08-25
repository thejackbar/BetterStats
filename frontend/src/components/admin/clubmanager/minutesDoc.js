// The minutes of a meeting, as a document a committee actually circulates.
//
// COMPOSED FROM THE MEETING'S OWN RECORD, NOT FROM THE NARRATIVE ALONE, and
// that is the whole design. A motion, the objective it serves, how each person
// voted and what an action costs are FACTS the club has already entered on this
// screen; passing them through a paragraph of prose is how they go missing, and
// they did — a motion moved during the President's report came out filed under
// Sponsorship & Fundraising, with no objective and no vote breakdown, because
// the draft handed the model a flat list of motions with nothing saying which
// agenda item each one belonged to.
//
// So the structure and every figure come from the record, in the agenda's own
// order, and the written account is only ever the prose inside a section. A
// section takes the notes the secretary typed against that item; failing that,
// the matching part of the drafted narrative; failing that, it says the item was
// discussed rather than inventing an account of it.

import { objectiveLabel } from './planLabels'

const BULLET = '•'
const nameList = xs => xs.filter(Boolean).join('; ')

// A motion or an action sits in from the section's own text. The two formats
// are set INDEPENDENTLY and on purpose: `indent` is twips, which is what Word
// takes and where the depth was already right, and `indentPt` is points for the
// PDF, which had been reading the twips figure as points and drawing an indent
// twenty times too deep.
const INSET = { indent: 200, indentPt: 67 }

/* ── formatting ──────────────────────────────────────────────────────────── */

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December']

export function longDate(v) {
  const t = Date.parse(v)
  if (!Number.isFinite(t)) return ''
  const d = new Date(t)
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`
}

export function shortDate(v) {
  const t = Date.parse(v)
  if (!Number.isFinite(t)) return ''
  const d = new Date(t)
  return `${d.getDate()} ${MONTHS[d.getMonth()].slice(0, 3)} ${d.getFullYear()}`
}

function timeOf(v) {
  const t = Date.parse(v)
  if (!Number.isFinite(t)) return ''
  const d = new Date(t)
  // Midnight is what a date with no time parses to, and printing "12:00 am"
  // would be asserting a start time nobody recorded.
  if (d.getHours() === 0 && d.getMinutes() === 0) return ''
  return d.toLocaleTimeString('en-AU', { hour: 'numeric', minute: '2-digit' })
}

const money = n => (n || n === 0)
  ? `$${Number(n).toLocaleString('en-AU', { maximumFractionDigits: 2 })}` : ''

const NOT_RECORDED = 'Not recorded'
const orNot = v => (v && String(v).trim()) ? String(v).trim() : NOT_RECORDED
const titleCase = s => String(s || '').split('_').filter(Boolean)
  .map(w => w[0].toUpperCase() + w.slice(1)).join(' ')

// Markdown a model emits and a Word document has no use for. The current draft
// wraps every heading in ** and those asterisks were being printed literally.
const plain = s => String(s || '')
  .replace(/\*\*(.+?)\*\*/g, '$1')
  .replace(/^#{1,6}\s*/gm, '')
  .replace(/^\s*[-*]\s+/gm, `${BULLET}  `)
  .trim()

/* ── the drafted narrative, split by its own headings ────────────────────── */

const key = s => String(s || '').toLowerCase()
  .replace(/[^a-z0-9]+/g, ' ').replace(/\b(and|the|of|a)\b/g, ' ').replace(/\s+/g, ' ').trim()

// The draft writes one section per agenda item, headed by that item's title.
// Split on those headings so a section's prose can be put back under the item it
// belongs to. A heading nothing matches is simply not used — the record decides
// what sections exist, never the narrative.
export function splitNarrative(text, knownHeadings = []) {
  // A DRAFT HEADS ITS SECTIONS WITH THE AGENDA ITEM'S OWN TITLE ON A BARE LINE,
  // with no markup at all, so matching only `**bold**` or `## ` found nothing
  // and the whole account fell into one lump at the end of the document under
  // Record of Discussion. The agenda's own titles are therefore headings too.
  const known = new Set(knownHeadings.map(key).filter(Boolean))
  const sections = new Map()
  const lines = String(text || '').split('\n')
  let head = null, buf = [], loose = []
  const flush = () => {
    if (head) {
      const body = plain(buf.join('\n')).trim()
      if (body) sections.set(key(head), { head, body })
    }
    head = null; buf = []
  }
  for (const raw of lines) {
    const line = raw.trim()
    const m = line.match(/^\*\*(.+?)\*\*:?$/) || line.match(/^#{1,6}\s*(.+?)$/)
      // "3. President's Report" as its own line is a heading too.
      || line.match(/^\d+\.\s+([A-Z][^.]{2,60})$/)
      || (known.has(key(line)) ? [line, line] : null)
    if (m) { flush(); head = m[1].replace(/^\d+\.\s*/, '').trim(); continue }
    if (head) buf.push(raw)
    else loose.push(raw)
  }
  flush()
  // ANYTHING NOT UNDER A HEADING IS STILL THE SECRETARY'S ACCOUNT and must not
  // be dropped. A secretary who types plain prose into the box rather than
  // pressing the draft button has no headings at all, and losing that text
  // would be losing the minutes.
  // The prompt asks for no preamble and the model writes one anyway: its own
  // title block, repeating the club, the document name and the date this
  // document already carries in its heading. A short run of short lines ahead
  // of the first real heading is that block, and is dropped. Anything longer is
  // real content and is kept.
  const preamble = loose.map(l => l.trim()).filter(Boolean)
  const isTitleBlock = sections.size > 0 && preamble.length > 0
    && preamble.length <= 4 && preamble.every(l => l.length <= 60)
  return {
    sections,
    loose: isTitleBlock ? '' : plain(loose.join('\n')).trim(),
  }
}

/* ── the pieces of a section ─────────────────────────────────────────────── */

const VOTE_LABEL = { for: 'For', against: 'Against', abstain: 'Abstain' }

function motionBlocks(mo, { nameOf, objectiveOf }) {
  const inset = { ...INSET }
  const blocks = []
  blocks.push({ type: 'label', text: 'MOTION', ...inset })
  blocks.push({ type: 'para', text: `"${plain(mo.description)}"`, ...inset, after: 4 })

  const moved = [
    mo.proposed_by_member_id ? `Moved by ${nameOf(mo.proposed_by_member_id)}` : null,
    mo.seconded_by_member_id ? `seconded by ${nameOf(mo.seconded_by_member_id)}` : null,
  ].filter(Boolean).join(', ')
  if (moved) blocks.push({ type: 'para', text: `${moved}.`, ...inset, after: 4 })

  // The objective the motion serves. A club that runs a strategic plan needs the
  // minutes to say which part of it a decision was made against.
  const obj = objectiveOf(mo.objective_id)
  if (obj) blocks.push({ type: 'para', text: `Serves objective: ${obj}`, ...inset, muted: true, after: 4 })

  const f = mo.votes_for || 0, a = mo.votes_against || 0, ab = mo.votes_abstain || 0
  const counted = f + a + ab > 0
  const outcome = titleCase(mo.outcome || 'pending')
  blocks.push({
    type: 'para', ...inset, after: 4,
    text: counted
      ? `Outcome: ${outcome}. For ${f}, against ${a}, abstain ${ab}.`
      : `Outcome: ${outcome}.`,
  })

  // Who voted which way, where the club recorded names rather than a show of
  // hands. This is the part a member queries months later.
  const named = (mo.votes || []).filter(v => v.vote)
  if (named.length) {
    const by = { for: [], against: [], abstain: [] }
    for (const v of named) (by[v.vote] || (by[v.vote] = [])).push(nameOf(v.member_id))
    const said = ['for', 'against', 'abstain']
      .filter(k => by[k] && by[k].length)
      .map(k => `${VOTE_LABEL[k]}: ${nameList(by[k].sort())}`)
      .join('. ')
    blocks.push({ type: 'para', text: `Votes recorded. ${said}.`, ...inset, muted: true, after: 6 })
  }
  return blocks
}

export function ownerOf(t, nameOf) {
  return nameList((t.assignee_member_ids || []).map(nameOf))
    || (t.assigned_to_member_id ? nameOf(t.assigned_to_member_id) : '')
}

function actionLine(t, { nameOf, objectiveOf }) {
  const bits = [
    ownerOf(t, nameOf) || 'Unassigned',
    t.due_date ? `due ${shortDate(t.due_date)}` : null,
    t.budget_estimate ? `budget ${money(t.budget_estimate)}` : null,
    t.status ? `status ${titleCase(t.status)}` : null,
  ].filter(Boolean)
  const obj = objectiveOf(t.objective_id)
  return `${plain(t.title)}. ${bits.join('; ')}.` + (obj ? ` Serves objective: ${obj}` : '')
}

/* ── the document ────────────────────────────────────────────────────────── */

export function buildMinutesDoc({
  club, meeting, agendaItems = [], motions = [], actions = [],
  attendance = [], pool = [], objectives = [], minutesText = '',
}) {
  const poolName = new Map(pool.map(p => [p.member_id, p.full_name]))
  const attName = new Map(attendance.map(a => [a.member_id, a.full_name]))
  const nameOf = id => attName.get(id) || poolName.get(id) || 'Unknown'
  const objById = new Map(objectives.map(o => [o.id, o]))
  const objectiveOf = id => (id && objById.has(id)) ? objectiveLabel(objById.get(id)) : ''

  const { sections: narrative, loose: looseNarrative } =
    splitNarrative(minutesText, agendaItems.map(i => i.title))
  const blocks = []
  let n = 0
  const section = (label) => { n += 1; blocks.push({ type: 'heading', text: `${n}. ${label}` }) }

  /* Who was there. */
  const withStatus = s => attendance.filter(a => a.status === s)
    .map(a => a.full_name || nameOf(a.member_id)).sort()
  const chair = withStatus('chair')
  const present = [...chair, ...withStatus('present')]
  const apologies = withStatus('apology')
  const absent = withStatus('absent')

  /* 1. Meeting details. */
  section('Meeting Details')
  blocks.push({
    type: 'table',
    widths: [1, 3],
    rows: [
      ['Date', orNot(longDate(meeting.scheduled_at))],
      ['Time', orNot(timeOf(meeting.scheduled_at))],
      ['Location', orNot(meeting.location)],
      ['Meeting type', orNot(titleCase(meeting.meeting_type))],
      ['Chair', orNot(chair.join('; '))],
      ['Present', orNot(present.join('; '))],
      ['Apologies', orNot(apologies.join('; '))],
      ['Absent', orNot(absent.join('; '))],
    ],
  })

  /* 2. The agenda, as a list. */
  section('Agenda')
  blocks.push({
    type: 'bullets',
    items: agendaItems.length ? agendaItems.map(i => plain(i.title)) : ['No agenda items were recorded.'],
  })

  /* 3..N one section per agenda item, in the agenda's own order. */
  const used = new Set()
  for (const item of agendaItems) {
    section(plain(item.title))

    const notes = plain(item.outcome_notes)
    const drafted = narrative.get(key(item.title))?.body || ''
    if (drafted) used.add(key(item.title))
    const prose = notes || drafted
    if (prose) for (const p of prose.split(/\n{2,}/)) blocks.push({ type: 'para', text: p.trim() })
    else blocks.push({ type: 'para', text: 'Discussed.' })

    for (const mo of motions.filter(x => x.agenda_item_id === item.id)) {
      blocks.push(...motionBlocks(mo, { nameOf, objectiveOf }))
    }
    const own = actions.filter(x => x.agenda_item_id === item.id)
    if (own.length) {
      blocks.push({ type: 'label', text: own.length === 1 ? 'ACTION' : 'ACTIONS', ...INSET })
      for (const t of own) {
        blocks.push({ type: 'para', text: `${BULLET}  ${actionLine(t, { nameOf, objectiveOf })}`, ...INSET, after: 5 })
      }
    }
  }

  /* Anything raised outside the agenda still has to be minuted. */
  const looseMotions = motions.filter(m => !m.agenda_item_id
    || !agendaItems.some(i => i.id === m.agenda_item_id))
  if (looseMotions.length) {
    section('Other Motions')
    blocks.push({ type: 'para', text: 'Recorded against the meeting rather than a numbered agenda item.', muted: true })
    for (const mo of looseMotions) blocks.push(...motionBlocks(mo, { nameOf, objectiveOf }))
  }

  /* Whatever the narrative said that no agenda item claimed. Kept rather than
     dropped: a section the model headed differently, or prose typed straight
     into the box with no headings at all, is still the account of the meeting. */
  const unclaimed = [...narrative.entries()].filter(([k]) => !used.has(k)
    && !['actions', 'action list'].includes(k))
  if (looseNarrative || unclaimed.length) {
    section('Record of Discussion')
    if (looseNarrative) {
      for (const p of looseNarrative.split(/\n{2,}/)) blocks.push({ type: 'para', text: p.trim() })
    }
    for (const [, v] of unclaimed) {
      blocks.push({ type: 'label', text: String(v.head).toUpperCase() })
      for (const p of v.body.split(/\n{2,}/)) blocks.push({ type: 'para', text: p.trim() })
    }
  }

  /* The actions table, which is what a committee reads first next month. */
  section('Actions')
  if (actions.length) {
    blocks.push({ type: 'para', text: 'The following actions were recorded for follow-up.' })
    blocks.push({
      type: 'table',
      header: ['Owner', 'Action', 'Due', 'Budget', 'Serves objective', 'Status'],
      // Sized against the widest value each column actually holds (a name, a
      // date, a money figure, "Not recorded", "In Progress"), so the short
      // columns never break a word across two lines.
      widths: [1.5, 2.2, 1.25, 1.3, 2.6, 1.2],
      rows: actions.map(t => {
        return [
          ownerOf(t, nameOf) || 'Unassigned',
          plain(t.title),
          t.due_date ? shortDate(t.due_date) : NOT_RECORDED,
          t.budget_estimate ? money(t.budget_estimate) : NOT_RECORDED,
          objectiveOf(t.objective_id) || NOT_RECORDED,
          titleCase(t.status || 'todo'),
        ]
      }),
    })
  } else {
    blocks.push({ type: 'para', text: 'No actions were recorded.' })
  }

  blocks.push({ type: 'spacer', height: 10 })
  blocks.push({ type: 'para', text: 'End of minutes', muted: true, italic: true })

  const when = longDate(meeting.scheduled_at)
  const heading = `${plain(meeting.title) || 'Meeting'} Committee Meeting Minutes`
  return {
    title: (club?.name || '').toUpperCase() || 'COMMITTEE MEETING MINUTES',
    subtitle: [heading, [when, meeting.location].filter(Boolean).join(`  ${BULLET}  `)]
      .filter(Boolean).join('\n'),
    blocks,
  }
}
