export default {
  version: 'v9.84.0',
  date: '2026-09-21',
  // Above v9.83.1's sortKey (the highest on origin/main at the time). Check
  // origin/main at merge time.
  sortKey: '2026-09-29T00:15:00Z',
  title: 'The Club Diary landing tells you where the club is, and who is responsible',
  items: [
    "BetterAdmin → Diary used to open on a single season timeline. It now opens on an Overview built to answer the question a committee member actually arrives with: what is late, what is due this week or this month, what is coming up, and who is holding each of them. Overdue and blocked tasks are listed first, each showing the committee role that owns it and the person currently in that seat.",
    "The same tasks can be read four ways, switched from the header: Overview, a filterable List, a Calendar, and a Timeline (the Gantt, with the critical path). Every task in every view opens a detail panel.",
    "The Calendar zooms between Year and Month. A task with a start and a due date is drawn as a band spanning the cells it covers, and each task is colour-coded by status with a legend, so a busy September reads at a glance.",
    "The detail panel is now actionable, not just a read-out: mark a task Not started / In progress / Done, drag its progress, set its start and due dates, record budget and spend, and assign a specific person on top of the owner role.",
    "A new By role view makes the link between a task and the committee explicit. Each committee seat is a card showing who currently holds it (or VACANT, in red, when nobody does) and the tasks that seat is carrying, split by status, so a seat sitting on late work, or an unfilled seat that owns real tasks, is obvious.",
    "The owner role set on a task template now carries through to every season generated from it and is shown on the task everywhere, so responsibility flows from the template to each season's tasks without being re-entered.",
    "Editing the task templates and generating a season have moved to a Setup menu, off the day-to-day path but a click away, since that is work done before a season or when a new annual task appears rather than week to week.",
  ],
}
