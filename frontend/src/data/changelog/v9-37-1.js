export default {
  version: 'v9.37.1',
  date: '2026-08-20',
  sortKey: '2026-09-04T15:00:00Z',
  title: 'Import player details now covers the whole profile',
  items: [
    'Import player details can fill in date of birth, opening batter, overseas and their country, active or inactive, whether they show on your public website, and the fees and training flags. It only handled contact details, squad, role, batting, bowling and gender before, so everything added to the profile since had to be typed in one player at a time.',
    'Dates of birth are read however your spreadsheet writes them: 2012-03-04, 4 Mar 2012, 04/03/2012 or an Excel date cell. A slashed date reads day first, which is what the column hint now says. A date that can\'t be a birthday is reported and the player left alone.',
    'The Excel template has the new columns with pick lists, so the yes/no ones are chosen rather than typed.',
    'The review screen shows each of the new fields before and after, with the age a date of birth works out to.',
    'The notes each column carries on the mapping screen are now actually shown. They had been written and never drawn.',
  ],
}
