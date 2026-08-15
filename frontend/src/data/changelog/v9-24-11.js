export default {
  version: 'v9.24.11',
  date: '2026-08-15',
  sortKey: '2026-08-15T10:00:00Z',
  title: 'Sales Workspace — landing page, faster drawer, auto follow-up events',
  items: [
    'A Sales-role account now lands straight on the Sales Workspace after login, and can reach ONLY that page — every other admin URL (including the ordinary club dashboard it was landing on by mistake) redirects back to it. The Owner field shows their own name, locked, instead of the super-admin owner picker.',
    "Opening a club's drawer was taking several seconds — the engagement breakdown was recomputing off a slow whole-table scan on every open instead of the indexed fast path the rest of the CRM already uses for live recomputes. Fixed; it should now be near-instant.",
    "The drawer now shows the club's current CRM stage, its onboarding method, and whether it's ever been called, right above the Engagement panel.",
    "A contact's mobile number now renders in the normal text colour instead of grey, matching their name.",
    'Logging a call with an outcome worth a real next step (Interested, wants more info, wants trial, wants demo, wants pricing, wants committee discussion, asked to call back, referred to another person, requested information) AND a follow-up date now also creates a calendar Event — owned by whoever logged the call, naming the contact, with the call notes as its note (or a sensible default when none were typed).',
  ],
}
