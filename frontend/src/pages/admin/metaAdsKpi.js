// The numbers behind the Meta Ads HQ headline strip, kept out of the component
// so they can be checked on their own.
//
// WHERE EACH NUMBER COMES FROM, because the strip mixes two sources and the
// page has to say which is which:
//   Spend, landing page views ........ Meta-reported (stored snapshot)
//   Trial signups, Converted, Revenue  our own database
//
// RULES THIS FILE KEEPS (see guides/marketing-funnel-ads-and-webinar.md):
//  * Only the TRIAL stream carries value. Revenue is paid clubs x the trial's
//    unit value; a webinar registration is never valued.
//  * Cost per trial divides the TRIAL ads' own spend, not the campaign's. The
//    campaign figure covers both products.
//  * `counting since` narrows Meta's spend but never the registration count.
//    When real signups pre-date the cutoff, their cost is outside the spend
//    figure, so a cost per trial or ROAS from the two would read too GOOD.
//    That is the direction these figures are never allowed to err in, so they
//    are withheld, with the reason, instead of printed.

// Used only when the stream does not report its own unit value.
export const TRIAL_VALUE_FALLBACK_AUD = 399

export const NO_TAG = '(untagged)'

// The creative key the backend files a registration under
// (meta_ads.get_creative_performance `_bucket`): the utm_content, else untagged.
export const creativeKey = (utmContent) => (utmContent || '').trim() || NO_TAG

export function computeKpis({ trialStream, webinarStream, campaign, signupRows, countingSince, unattributedSpend = 0 }) {
  const unit = (trialStream && trialStream.unit_value_aud) || TRIAL_VALUE_FALLBACK_AUD
  // `null` rows means the signups report has not loaded (or failed). Converted
  // and revenue are then unknown, which is not the same as zero.
  const rows = Array.isArray(signupRows) ? signupRows : null

  const trials = trialStream ? Number(trialStream.results || 0) : null
  const trialSpend = trialStream ? Number(trialStream.spend || 0) : 0
  const campaignSpend = campaign ? Number(campaign.spend || 0) : 0
  const converted = rows ? rows.filter((r) => r.converted_to_paid).length : null
  const revenue = converted == null ? null : converted * unit

  let preCutoff = 0
  if (countingSince && rows) {
    const cutoff = Date.parse(countingSince)
    if (!Number.isNaN(cutoff)) {
      preCutoff = rows.filter((r) => r.signed_up_at && Date.parse(r.signed_up_at) < cutoff).length
    }
  }
  const windowMismatch = preCutoff > 0
  const mismatchReason = windowMismatch
    ? `${preCutoff} signup${preCutoff === 1 ? '' : 's'} pre-date the counting-since cutoff, but their spend is outside it`
    : null
  // The ad rows add up to MORE than the campaign's own spend: some row is older than the last
  // refresh (after a window change, a row from the earlier lifetime pull). Cost per trial would
  // be charged with spend that is not this window's, so it is withheld until they agree.
  const spendMismatch = Number(unattributedSpend) < -0.5
  const spendReason = spendMismatch
    ? `the ads listed add up to A$${Math.abs(Number(unattributedSpend)).toFixed(2)} more than the campaign's spend, so some rows are older than the last refresh`
    : null
  const withheld = windowMismatch || spendMismatch
  const withheldReason = mismatchReason || spendReason

  const cost = trialStream ? trialStream.cost_per_result : null
  const costPerTrial = !withheld && cost != null ? cost : null
  const roas = !withheld && revenue != null && trialSpend > 0 ? revenue / trialSpend : null

  // Converted over the SAME rows it was counted from. Trial signups on the
  // tile also carry any manual +/- adjustment, which the paid count cannot.
  const rate = rows && rows.length > 0 && converted != null ? converted / rows.length : null

  return {
    unit,
    campaignSpend,
    trialSpend,
    webinarSpend: webinarStream ? Number(webinarStream.spend || 0) : 0,
    trials,
    converted,
    revenue,
    costPerTrial,
    roas,
    rate,
    trackedSignups: rows ? rows.length : null,
    webinarRegs: webinarStream ? Number(webinarStream.results || 0) : 0,
    showWebinar: !!webinarStream && (Number(webinarStream.results || 0) > 0 || Number(webinarStream.ad_count || 0) > 0),
    windowMismatch,
    mismatchReason,
    spendMismatch,
    spendReason,
    // Why a figure is blank, so a dash never has to be guessed at.
    costWhy: costPerTrial != null ? null
      : withheld ? withheldReason
      : !trials ? 'no trial signups yet'
      : 'no trial-ad spend yet',
    roasWhy: roas != null ? null
      : withheld ? withheldReason
      : revenue == null ? 'signup report not loaded'
      : 'no trial-ad spend yet',
  }
}

// Paid clubs per creative, joined to the creative table by utm_content so each
// ad's row can show the thing that matters (paying clubs), not just sign-ups.
export function convertedByCreative(signupRows) {
  const out = {}
  for (const r of signupRows || []) {
    const k = creativeKey(r.utm_content)
    out[k] = (out[k] || 0) + (r.converted_to_paid ? 1 : 0)
  }
  return out
}

// Ads carrying spend but no utm_content in AD_DESTINATIONS. Their registrations
// carry the REAL tag from the ad URL, so they file under some other creative
// and these ads' spend piles into one "(untagged)" row. Listed so the gap is
// visible rather than reading as "the new ads produced nothing".
export function unmappedAds(ads) {
  return (ads || []).filter((a) => !(a.utm_content || '').trim() && (a.spend || 0) > 0)
}
