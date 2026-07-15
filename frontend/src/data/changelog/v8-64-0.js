export default {
  version: 'v8.64.0',
  date: '2026-07-15',
  sortKey: '2026-07-15T03:00:00Z',
  title: 'Self-service module trials, subscribe requests and cancellation',
  items: [
    'Starting a module trial is now instant — the Dashboard\'s "START TRIAL" button (was "Request trial") and a new per-row "START TRIAL" button on the Account page activate the trial immediately, with no wait on a BetterCricket team member.',
    'The Dashboard\'s "Subscribe" button (was "Request to subscribe") now takes you straight to Account > Plan & Billing, where you can tick the modules you want. Online subscribing itself isn\'t connected yet (that\'s landing in its own build with Stripe) — for now it shows where to reach the BetterCricket team instead.',
    'Account > Plan & Billing has a new CANCEL button on any subscribed module, for your club\'s primary admin only. Cancelling BetterStats (Core) cancels every module on the account, since everything else depends on it — both need you to type "confirm" first.',
    'A Club Admin who isn\'t the primary admin now gets a clear message (with the primary admin\'s name) when they try to select a module to subscribe to, instead of the option just not doing anything.',
  ],
}
