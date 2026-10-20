export default {
  version: 'v9.126.0',
  date: '2026-10-20',
  // Above v9.125.6's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-04T15:00:00Z',
  title: 'BetterPosts: your own background shows as it is, and every part of a layout has its own colour',
  items: [
    'Fixed: a background you uploaded was dimmed and had the layout\'s dots, stripes and grain drawn over it. Every layout lays a 60% colour over the background and a fine pattern on top. That suits the built-in textures but not your own photo. A photo of your own now shows with no tint and no pattern.',
    'New in Brand, under Background: "Over the background". A Layout tint slider (0 to 100%) sets how much of the layout\'s own colour sits over the background, and a switch turns the dots, stripes and grain on or off. Built-in textures keep 60% and the pattern, as before. "Back to automatic" returns both.',
    'New in Brand: Colours. Background, Panels and shapes, Accent and Text can each be changed over whichever palette is open, and the whole post follows. Reset all puts the palette back. Before this, the text colour was fixed.',
    'New in Brand for Team of the Week (both layouts): Elements. "Team of" and "The Week" can each be retyped and given their own colour. The round line, club name, name band, surname, score line, grade line, card number, points tag, photo backdrop, card outline, footer bar and footer line each have a colour. Anything left on Auto follows the palette.',
    'On the Team Sheet, names and scores turn dark or light to suit the name band when you change the band colour, so white text does not stay on a white band. You can still set the name colour yourself.',
    'The picks are remembered between visits and saved with "Save as template". The Team Sheet and the Ranked Board share them, so the heading you typed on one is there when you try the other. A template saved before this opens as it was.',
    'Fixed: a background photo you picked turned back into a built-in texture after a reload. It now stays.',
  ],
}
