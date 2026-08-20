import BetterClubhouseLayout from './BetterClubhouseLayout'

// The Fees screens are the Money section of BetterAdmin now — no separate
// BetterFees sidebar, accent or lockup, and the tools kept their URLs. This
// wrapper stays so the existing pages don't all have to change their import in
// one go; new screens should render BetterClubhouseLayout directly.
export default function BetterFeesLayout(props) {
  return <BetterClubhouseLayout {...props} />
}
