export default {
  version: 'v9.128.3',
  date: '2026-10-21',
  // Above v9.128.2.1's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-05T15:00:00Z',
  title: 'Photo background removal no longer crashes phones',
  items: [
    'On iPhones and Android phones, "Remove background (photo)" could blank the page and reload it part way through. The full model needs around 770MB of memory, which a phone browser will not give a single tab. Phones and tablets now use a lighter model that is about three times quicker and needs about a third less memory, and it shrinks big camera photos before it reads them. Edges can be a little rougher than on a computer.',
    'If a cut-out ever fails to finish on a device, the next one there uses the lighter method automatically and the editor says why. Computers keep the full model and are unchanged.',
  ],
}
