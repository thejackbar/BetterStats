export default {
  version: 'v8.59.6',
  date: '2026-07-14',
  sortKey: '2026-07-14T10:00:00Z',
  title: 'Fixed the per-module renewal date field saving mid-keystroke',
  items: [
    'On a club\'s module list (Super Admin > Clubs), the Renews date field saved and reloaded on every keystroke, which could disable the field and reset it before a full year could be typed in. Entering "2026" often left something like "0020" behind.',
    'The field now only saves once you click away, matching how the trial start/end dates already work.',
  ],
}
