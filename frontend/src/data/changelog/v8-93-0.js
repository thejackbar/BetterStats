export default {
  version: 'v8.93.0',
  date: '2026-07-29',
  sortKey: '2026-07-29T23:50:00Z',
  title: 'CRM pipeline stays up to date automatically, on a schedule you control',
  items: [
    'A new trial (self-serve or Super Admin) still creates its deal card instantly, and a club crossing the score threshold still enters the pipeline instantly — the instant refresh now also keeps cards that have already moved past the early stages up to date, not just new ones.',
    'A frequent background sweep re-scores the cards whose club had new activity since it last ran, so existing cards stay fresh in near real time without a manual reload.',
    'A periodic full sweep recomputes every club in the Club Directory to catch anything the frequent sweep missed (for example a quiet card slowly drifting across a threshold).',
    'Both cadences are set in Pipeline Settings: the frequent sweep in minutes and seconds (default 1 minute) and the full sweep in minutes (default 60 minutes). Changes take effect straight away.',
  ],
}
