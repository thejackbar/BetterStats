export default {
  version: 'v8.70.2',
  date: '2026-07-16',
  sortKey: '2026-07-16T23:00:00Z',
  title: 'Setup Wizard polish: colours fixed, logo editor, connect in place',
  items: [
    'Fixed: the primary and secondary colours picked in the Setup Wizard now save into the club theme properly, so they show up in Club Settings and actually restyle your pages. Previously they landed in a legacy field the site never reads.',
    'The wizard\'s logo upload now opens the image editor first, so you can crop and remove the background before it saves. Same tool Club Settings uses.',
    'Connect Square and Connect Xero now happen inside the wizard: it shows your live connection status and takes you straight to the sign-in, instead of dropping you on another page.',
    'Leaving the wizard for one of the bigger tools now shows a floating "back to setup" button that stays visible at the bottom of the screen until you use or dismiss it, including after a Square or Xero sign-in round trip.',
    'Your second club colour now earns its keep: the site pairs it with your primary in the navigation underline, stat highlight cards and the wickets chart line. If your second colour is black or white it\'s automatically swapped out on the theme it would disappear against.',
  ],
}
