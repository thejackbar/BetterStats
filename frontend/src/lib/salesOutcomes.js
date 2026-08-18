// Mirrors backend/app/services/sales_workspace.py's CALL_OUTCOMES exactly —
// keep the two in sync (same convention as lib/capabilities.js mirroring
// auth/capabilities.py). category drives the grouped dropdown; `key` is
// what's actually sent to POST .../calls.
export const CALL_OUTCOMES = {
  // Unsuccessful contact
  no_answer: { label: 'No answer', category: 'unsuccessful' },
  voicemail: { label: 'Voicemail', category: 'unsuccessful' },
  invalid_number: { label: 'Invalid number', category: 'unsuccessful' },
  wrong_person: { label: 'Wrong person', category: 'unsuccessful' },
  number_disconnected: { label: 'Number disconnected', category: 'unsuccessful' },
  no_longer_at_club: { label: 'Person no longer at club', category: 'unsuccessful' },
  // Neutral
  spoke_no_decision: { label: 'Spoke — no decision', category: 'neutral' },
  asked_callback: { label: 'Asked to call back', category: 'neutral' },
  referred_to_other: { label: 'Referred to another person', category: 'neutral' },
  requested_information: { label: 'Requested information', category: 'neutral' },
  // Positive
  wants_to_subscribe: { label: 'Wants to buy/subscribe now', category: 'positive' },
  interested: { label: 'Interested', category: 'positive' },
  wants_more_info: { label: 'Wants more information', category: 'positive' },
  wants_trial: { label: 'Wants trial', category: 'positive' },
  wants_trial_extension: { label: 'Wants a trial extension', category: 'positive' },
  wants_demo: { label: 'Wants demo', category: 'positive' },
  wants_pricing: { label: 'Wants to discuss pricing', category: 'positive' },
  wants_committee_discussion: { label: 'Wants committee discussion', category: 'positive' },
  // Negative
  not_interested: { label: 'Not interested', category: 'negative' },
  using_alternative: { label: 'Already using an alternative', category: 'negative' },
  dont_call_again: { label: "Don't call again", category: 'negative' },
  remove_from_list: { label: 'Remove from list', category: 'negative' },
  // Administrative
  duplicate: { label: 'Duplicate', category: 'administrative' },
  club_inactive: { label: 'Club inactive', category: 'administrative' },
  wrong_club: { label: 'Wrong club', category: 'administrative' },
  contact_details_updated: { label: 'Contact details updated', category: 'administrative' },
}

export const CATEGORY_ORDER = ['positive', 'neutral', 'unsuccessful', 'negative', 'administrative']
export const CATEGORY_LABELS = {
  positive: 'Positive', neutral: 'Neutral', unsuccessful: 'Unsuccessful contact',
  negative: 'Negative', administrative: 'Administrative',
}

export function groupedOutcomes() {
  return CATEGORY_ORDER.map((cat) => ({
    category: cat,
    label: CATEGORY_LABELS[cat],
    options: Object.entries(CALL_OUTCOMES)
      .filter(([, v]) => v.category === cat)
      .map(([key, v]) => ({ key, label: v.label })),
  }))
}

export function outcomeLabel(key) {
  return CALL_OUTCOMES[key]?.label || key
}
