export default {
  version: 'v9.143.0',
  date: '2026-11-10',
  // Above v9.142.7's sortKey (2026-11-19T16:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-19T17:00:00Z',
  title: 'Meta Ads HQ shows the selected campaign, with a period filter and one club list',
  items: [
    "With a campaign selected, the funnel, the club list and the traffic card now describe that campaign only. They used to show everything: every visitor to the wizard, every source, and a club list back to July. A switch above them flips to All traffic when you want the wider view, and it says how many clubs the campaign view left out.",
    "One period for all three: 24 hours, 7 days, 14 days, 30 days or the whole campaign. It opens on 7 days.",
    "The two club tables are now one list, one row per club, with the furthest stage it reached: searched only, selected a club, reached terms, or completed. Filter chips show the count for each, including Reached terms, not finished, which is the list worth a call. You can still search by name and flag test rows.",
    "The trial funnel no longer shows Meta's Lead count as a step after Club selected. They are the same moment, so it is a note on Club selected instead, and the 23,000% step is gone.",
    "Meta's lead count was being added to its own pixel share and read double. It now counts once.",
    "After a restart or a new counting-since date, ads with no delivery in the new window no longer keep their old lifetime figures on the page. That is what showed A$217.72 under untagged and a funnel with 179k impressions.",
    "Cost per trial and ROAS are held back, with the reason, when the ads listed add up to more than the campaign spent.",
    "The most efficient ad headline no longer suggests moving budget to a paused ad. A webinar card with no ad and no result is hidden.",
  ],
}
