export default {
  version: 'v9.109.3',
  date: '2026-10-09',
  sortKey: '2026-10-09T03:00:00Z',
  title: 'Selection no longer offers a player another side has already picked in a draft',
  items: [
    'A 3rd XI squad player who is in the 2nd XI side you are still building (not confirmed yet) was being shown at the top of the 4ths pool as "Not picked in 3rd XI". The board only looked at confirmed XIs. It now also looks at other sides\' unconfirmed drafts for the same day.',
    'Those players are no longer labelled or moved to the top. They show "In 2nd XI draft (not confirmed)" instead, and can still be picked, because a draft never blocks anyone. Only a confirmed XI does that.',
  ],
}
