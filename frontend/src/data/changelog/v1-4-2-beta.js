export default {
  version: 'v1.4.2 Beta',
  date: '2026-06-07',
  sortKey: '2026-06-07T08:00:00Z',
  title: 'Resilience — auto-recover from “page failed to load” after a deploy',
  items: [
    'Fixed the “Something went wrong — Failed to fetch dynamically imported module” screen that could appear (e.g. on Admin) right after a new version shipped: the app now reloads itself once to pull the latest version instead of leaving you stuck.',
    'If a reload still can’t recover, you now get a clear “Update available — Reload” prompt with a working button (the old “Try again” did nothing for this case).',
    'Behind the scenes: deploys now automatically refresh the reverse proxy so it always points at the freshly-rebuilt site, preventing the brief outage this could cause.',
  ],
}
