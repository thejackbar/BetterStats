export default {
  version: 'v9.139.4.1',
  date: '2026-11-04',
  // Above v9.139.4's sortKey. Check origin/main at merge time.
  sortKey: '2026-11-15T23:30:00Z',
  title: 'Account: a club that already has BetterStats is not charged for it again',
  items: [
    'Fixed: when a Super Admin set BetterStats to Active for a club that paid by bank transfer, the Account page showed it as Subscribed but still quoted BetterStats again whenever the club ticked another module. Ticking BetterSocials quoted $548 (BetterStats $399 plus BetterSocials $149) and would have opened a second subscription. It now quotes and charges BetterSocials only.',
    'The quote says "BetterStats is already active on your account, so it isn\'t charged again." There is no bundle discount on modules bought after BetterStats, the same as modules added later to a card subscription.',
    'Fixed: BetterStats you set Active by hand is no longer written onto the club\'s Stripe subscription when it adds a second module later. Before, a Stripe renewal could have moved its renewal date on without being paid.',
    'Clubs that pay by invoice follow the same rule. A club still in its BetterStats trial, or whose trial has ended, is priced BetterStats as before.',
  ],
}
