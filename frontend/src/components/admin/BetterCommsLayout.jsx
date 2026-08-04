import BetterClubhouseLayout from './BetterClubhouseLayout'

// The Comms screens are the Comms section of BetterClubhouse now.
//
// CommsContextBar no longer renders here. It is Super Admin machinery — the
// BetterCricket marketing-org switch and the act-as-club mechanism — and a club
// build must never carry BetterCricket's own sales surface, not behind a
// dropdown and not greyed out. It lives on the super-admin Clubs Directory
// instead. See docs/design_handoff_betterclubhouse/PROJECT_RULES.md.
export default function BetterCommsLayout(props) {
  return <BetterClubhouseLayout {...props} />
}
