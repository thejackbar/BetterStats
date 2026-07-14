export default {
  version: 'v8.60.6',
  date: '2026-07-14',
  sortKey: '2026-07-14T18:00:00Z',
  title: 'Fixed: deleting a user from Super Admin > Users still failed after the last fix',
  items: [
    'The previous fix corrected a database constraint, but delete still 500\'d — the real cause was one level up: SQLAlchemy was trying to manage the user\'s club membership itself on delete instead of trusting the database\'s own cascade rule, and hit a not-null constraint doing it.',
    'User deletion now lets the database handle it directly, the way it already correctly does for club deletion.',
  ],
}
