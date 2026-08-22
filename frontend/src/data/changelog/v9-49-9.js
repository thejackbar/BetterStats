export default {
  version: 'v9.49.9',
  date: '2026-08-23',
  sortKey: '2026-08-23T15:00:00Z',
  title: 'Empty $0 "won" deals, and a Trial deal listed as won',
  items: [
    'Fixed: a subscription event that could not resolve which modules the club had bought was filing a $0 win against that club — and because the next event found no open deal either, another one each time. Reported live as three deals for one club, two of them empty. A win has to be for something, so nothing is recorded when there is nothing to record.',
    'Fixed: the commission tables took a deal\'s won/open state from its stored status rather than the stage it is sitting in. The two are written together everywhere, but where old data disagrees the reader saw a deal marked Trial listed under deals won. The stage — the thing shown on the board and in the drill-down — now decides.',
    'A deal that is not sitting in Won no longer counts towards commission earned, which is the conservative direction: no commission is claimed for a deal the board does not show as won.',
  ],
}
