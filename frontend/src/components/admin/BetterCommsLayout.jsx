import BetterClubhouseLayout from './BetterClubhouseLayout'

// The Comms screens are the Comms section of BetterAdmin now.
//
// The club ⇄ BetterCricket-internal switch is not a bar on the Comms screens any
// more. It is ClubhouseContextControl, in the BetterAdmin sidebar footer, so
// it covers Directory as well as Comms and the mode is visible from every screen
// rather than only the one you happen to be on. It renders for super admins only:
// a club build must never carry BetterCricket's own sales surface, not behind a
// dropdown and not greyed out. See docs/design_handoff_betterclubhouse/PROJECT_RULES.md.
export default function BetterCommsLayout(props) {
  return <BetterClubhouseLayout {...props} />
}
