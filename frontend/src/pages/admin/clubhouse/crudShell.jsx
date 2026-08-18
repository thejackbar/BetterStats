import { Button, Caption, Empty, ListRow, TextInput, TINT } from '../../../components/admin/ui'

// The one shape every Clubhouse Comms record is created, read, edited and
// deleted in.
//
// Emails, Lists, Segments and Templates are the same kind of thing four times
// over: a club has several of them, picks one, works on it, and saves or
// deletes it. They had grown four different answers to that — Segments a
// master–detail pair of panes, Lists a stack of cards with inline rename and a
// separate editor card underneath, Templates a list that swapped the whole page
// for an editor, Emails a list that navigated to a second route. Same job, four
// layouts, four places to learn where Delete lives.
//
// Segments had the best of them, so it is the pattern and this file is it. The
// furniture here is deliberately unopinionated about WHAT a record is: it knows
// about a left pane of saved things, a right pane holding the one in hand, a
// name you edit in place, a live count, and a save/delete row. Everything
// specific to a record — its rules, its members, its HTML, its audience — is the
// screen's own business and goes in the detail pane.
//
// A screen following this reads:
//
//   <BetterClubhouseLayout title="…" caption="… · N saved" onHelp={intro.reopen}
//     actions={<Button variant="primary" onClick={startNew}>New …</Button>} bare>
//     <CrudPanes>
//       <RecordListPane items={…} selId={…} onSelect={…}>…notes…</RecordListPane>
//       <DetailPane>
//         <RecordTitleRow … />
//         …the record's own editor…
//         <CountBar … />
//         <SaveRow … />
//       </DetailPane>
//     </CrudPanes>
//     <Toast … />
//   </BetterClubhouseLayout>

// How reachable a person is, from what the contact record actually holds. The
// same answer wherever a record reports its reach — a segment, a list, an
// email's audience.
export function reachability(c) {
  if (c.email) return { key: 'email', label: 'Email', tone: 'ok' }
  if (c.guardian_email || c.parent_email) return { key: 'guardian', label: 'Via guardian', tone: 'warn' }
  return { key: 'none', label: 'No address', tone: 'block' }
}

// The two panes. `bare` on the layout is what lets this fill the screen: the
// list rail scrolls on its own and the record beside it scrolls on its own,
// rather than the whole page scrolling as one. Below 900px `.ch-listpane`
// releases to a full row and the pattern becomes list-then-record.
export function CrudPanes({ children }) {
  return <div className="flex flex-wrap items-stretch min-h-0 flex-1">{children}</div>
}

// The left rail: every saved record, and whatever the screen wants to explain
// underneath them.
//
// `items` is the flat case. `groups` is the same thing in labelled sections, for
// a screen whose records come from more than one place — Lists uses it to keep
// the club's own lists apart from the ones other BetterCricket tools built. A
// group with no rows still renders its heading and its own empty line, so a
// section that exists but is empty says so rather than vanishing.
export function RecordListPane({
  items, groups, selId, onSelect, emptyText, loading = false, avatar = false,
  subWrap = false, children,
}) {
  const sections = groups || [{ items: items || [] }]
  const nothing = sections.every(g => !(g.items || []).length)
  return (
    <div className="ch-listpane bg-pb-surface overflow-y-auto p-2.5 pb-scroll">
      {loading ? <Empty>Loading…</Empty> : nothing ? <Empty>{emptyText}</Empty> : sections.map((g, gi) => (
        <div key={g.key || gi} className={gi ? 'mt-4' : ''}>
          {g.heading && <Caption className="px-1 mb-1.5">{g.heading}</Caption>}
          {(g.items || []).length === 0 ? (
            <div className="px-1 pb-1 text-[12.5px] text-pb-faint leading-[1.5]">{g.emptyText}</div>
          ) : g.items.map(it => (
            <ListRow
              key={it.id} name={it.name} sub={it.sub} figure={it.figure} flag={it.flag}
              avatar={avatar} subWrap={subWrap} selected={it.id === selId} onClick={() => onSelect(it.id)}
            />
          ))}
        </div>
      ))}
      {children && <div className="mt-4 space-y-2.5 px-1">{children}</div>}
    </div>
  )
}

// The right pane: the record in hand.
export function DetailPane({ children }) {
  return (
    <div className="flex-1 min-w-[380px] overflow-y-auto px-6 py-[22px] pb-scroll" style={{ flexBasis: 390 }}>
      {children}
    </div>
  )
}

// The record's name, edited where it is read, with its actions beside it.
//
// `readOnly` is for a record that can no longer be renamed — a sent email is
// the club's record of what went out, so its name is history, not a field.
export function RecordTitleRow({ name, onName, placeholder, blurb, readOnly = false, actions, inputRef, onSubmit }) {
  return (
    <div className="flex items-start gap-3.5 flex-wrap">
      <div className="flex-1 min-w-[220px]">
        {readOnly ? (
          <div className="text-[22px] font-bold text-pb-text leading-[1.25] break-words">
            {name || <span className="text-pb-faintest font-normal italic">{placeholder}</span>}
          </div>
        ) : (
          <TextInput
            ref={inputRef}
            value={name} onChange={e => onName(e.target.value)} placeholder={placeholder}
            // Only where the record is little more than its name — pressing
            // Enter there used to be how a list got created.
            onKeyDown={onSubmit ? (e => { if (e.key === 'Enter') { e.preventDefault(); onSubmit() } }) : undefined}
            className="!text-[22px] !font-bold !bg-transparent !border-transparent !px-0 !py-0 focus:!border-transparent"
          />
        )}
        {blurb && <div className="text-[12.5px] text-pb-dim mt-1 leading-[1.6]">{blurb}</div>}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">{actions}</div>}
    </div>
  )
}

// The live readout under a record: how many people it reaches, worked out now
// rather than stored. `children` replaces the whole sentence for a record whose
// headline number is not a count of people.
export function CountBar({
  counting, total, reachable, otherRoute, noun = 'person', nounPlural = 'people',
  countingText = 'Working out who matches…', children,
}) {
  return (
    <div className="mt-5 rounded-lg px-3.5 py-3 text-[13px]"
      style={{ background: TINT.panel, border: `1px solid ${TINT.border}` }}>
      {children || (counting ? <span className="text-pb-dim">{countingText}</span> : (
        <span className="text-pb-dim">
          <b style={{ color: 'var(--pb-accent-ink)' }}>{total}</b> {total === 1 ? `${noun} matches` : `${nounPlural} match`}
          {' · '}<b style={{ color: 'var(--pb-positive-ink)' }}>{reachable}</b> reachable by email
          {otherRoute > 0 && <> · <b style={{ color: '#f5b542' }}>{otherRoute}</b> need another route</>}
        </span>
      ))}
    </div>
  )
}

// Save on the left, delete on the right of it, the error beside both. Delete is
// only offered once there is something saved to delete.
export function SaveRow({ onSave, saveLabel, busy, onDelete, deleteLabel = 'Delete', error, children }) {
  return (
    <div className="flex items-center gap-2 mt-4 flex-wrap">
      {onSave && (
        <Button variant="primary" onClick={onSave} disabled={busy}>{saveLabel}</Button>
      )}
      {onDelete && (
        <Button variant="danger" size="sm" onClick={onDelete} disabled={busy}>{deleteLabel}</Button>
      )}
      {children}
      {error && <span className="text-[12.5px] text-pb-red">{error}</span>}
    </div>
  )
}
