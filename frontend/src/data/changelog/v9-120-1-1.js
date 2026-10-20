export default {
  version: 'v9.120.1.1',
  date: '2026-10-17',
  sortKey: '2026-10-20T04:00:00Z',
  title: 'Club Room Mode opens first time without an error',
  items: [
    'Opening Club Room Mode for the first time could show "Internal Server Error". The page asks for the club\'s settings and its public link at the same moment, and on a first visit both tried to create the same settings row. It now creates the row once and both requests read it. Refreshing the page worked around it before, so a club that saw the error only needs to reload.',
  ],
}
