export default {
  version: 'v8.70.8',
  date: '2026-07-17',
  sortKey: '2026-07-17T05:00:00Z',
  title: 'Fix a race between adding a module and its own payment webhook',
  items: [
    'Adding a module to an already-subscribed club could fail with a server error immediately after a successful payment, caused by its own confirmation webhook racing the same request and winning. The module was actually added correctly either way, only the on-screen confirmation was wrongly showing an error. Fixed.',
  ],
}
