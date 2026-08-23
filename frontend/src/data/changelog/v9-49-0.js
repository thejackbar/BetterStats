export default {
  version: 'v9.49.0',
  date: '2026-08-22',
  sortKey: '2026-08-22T23:00:00Z',
  title: 'Sales Commissions: what each rep is forecast to earn, and what they are owed',
  items: [
    'New Sales Commissions page, on the Sales Management tile list: per salesperson, the clubs they have earned, their open pipeline value, the commission that forecasts, and the same weighted by each deal\'s own likelihood.',
    'Commission rates are set from the page. One default, plus a rate per rep where they differ. A deal keeps the rate that applied when it was won, so changing a rate moves the forecast and never rewrites commission already earned.',
    'A second table shows what has been won, what commission that earned, what has been paid, and what is still due. Payouts are recorded against a rep and reduce what they are owed.',
    'Earned and paid are also summarised by quarter and by financial year, using the same periods Sales Targets does.',
    'Every pipeline and won figure opens the deals behind it: the club, the modules it is expected to buy, the stage and its likelihood, and the commission on each.',
    'A Stripe payment now moves the deal to Won at the price of the modules actually bought, rather than at whatever the pipeline had been forecasting.',
    'An existing club buying more modules now moves its deal to Won too, that path never fired at all before, and the rep who brought the club in is paid on the upsell.',
  ],
}
