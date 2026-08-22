export default {
  version: 'v9.49.1',
  date: '2026-08-22',
  sortKey: '2026-08-23T01:00:00Z',
  title: 'A deal reading "Stats" beside $998, and the commission columns behind a rep',
  items: [
    'Fixed: a deal\'s value could sit higher than its modules justified — reported as a deal listed as Stats yet valued at $998, the all-six-modules price. The value used to keep whichever figure was highest whenever a new signal merged in, so it never came back down after a rep narrowed what a club was interested in. Value now always follows the modules, both directions.',
    'python -m app.scripts.repair_deal_values re-prices open deals already carrying the old figure (dry run by default). Won deals are left alone — their value is the record of what was actually sold.',
    'The commission drill-down now carries Stage, Value, Rate, Pipeline commission and Weighted commission, with a total row that adds up to the figure it was opened from. A won deal shows Commission earned instead, since there is nothing to weight once it is settled.',
    'A club name in the drill-down now reads as a link and opens that club in the Sales Workspace, ready to review its history.',
    'A salesperson with no commission rate now gets told so where their $0 figures are, instead of leaving it to be worked out, and a 0% rate is flagged in Commission rates.',
    '"Forecast commission" is called "Pipeline commission" everywhere it appears, so the KPI, the table and the drill-down use one name for one figure.',
  ],
}
