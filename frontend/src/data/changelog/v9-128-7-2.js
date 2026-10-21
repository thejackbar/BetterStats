export default {
  version: 'v9.128.7.2',
  date: '2026-10-21',
  // Above v9.128.7.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-07T01:30:00Z',
  title: 'Phone photo cut-out: fixes the "Out of memory" error',
  items: [
    'On some phones the photo cut-out stopped with "no available backend found. ERR: [wasm] RangeError: Out of memory". The cut-out tool asked the phone to set aside 4GB of address space before it started, and iPhones can refuse that, most often on a second try in the same tab. Phones now ask for what each model needs, well under 1GB.',
    'If a phone still refuses, the cut-out waits a moment and tries once more on its own. If it fails again the message now says what happened, and a failed "Try full quality" no longer disturbs the quick cut-out you already have.',
  ],
}
