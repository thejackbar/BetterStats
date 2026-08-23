export default {
  version: 'v9.24.0',
  date: '2026-08-15',
  sortKey: '2026-08-17T16:00:00Z',
  title: 'Sales Workspace. A calling screen for the sales team',
  items: [
    'A new Sales Workspace (Sales → Sales Workspace, or /admin/super/crm/workspace): a club-by-club call queue with a merged Club Directory + CRM contact list, an engagement panel explaining a club\'s score, structured call outcomes, pinned notes and a call/activity history. It reads and writes the SAME deals the Sales Pipeline board already manages: one club, one history, two lenses.',
    'A new "sales" user role, restricted to the clubs assigned to them (Super Admin → Users → Role: Sales). A super admin sees and can reassign every club; a sales rep only ever sees their own.',
    'Logging a call automatically advances the club through the pipeline: the first call moves Target to Contacted, a positive response (interested / wants a demo / wants a trial / wants pricing / wants a committee chat) moves it to Engaged, and "not interested" / "don\'t call again" / "remove from list" closes it as Lost. A deal already further along is never pushed backward.',
    'A salesperson can start a trial on behalf of the person they\'re speaking to, right from the Workspace: the same trial-of-every-module, invite-an-admin flow Super Admin\'s New Club already runs, just reachable without leaving the call.',
    'Not in this round yet: a dedicated Follow-ups/Callbacks queue screen (a follow-up date is captured on every call and shown inline in the meantime), Sales Lists / bulk assignment, a Do Not Contact flag, sending email from the Workspace, and salesperson performance dashboards or commission attribution.',
  ],
}
