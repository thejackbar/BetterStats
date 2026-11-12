export default {
  version: 'v9.143.5.3',
  date: '2026-11-12',
  // Above v9.143.5.2's sortKey (2026-11-20T01:00:00Z). Check origin/main at merge time.
  sortKey: '2026-11-20T02:00:00Z',
  title: 'Ask BetterIQ says what it is doing on a long question',
  items: [
    "A slow question on Ask BetterIQ used to sit at 94% on \"Reading your data\" with no sign it was still going. The wording now changes as the wait goes on, and the seconds are shown beside the bar.",
    "If nothing comes back after about four minutes, the page now says the question took too long and unlocks the ask bar, so you can try again.",
    "A dropped connection on a long question now tells you that, instead of \"System refreshing\" as if the whole site had gone down.",
    "Behind the scenes, Ask BetterIQ now records how long each step of a question takes, so a slow one can be traced to the step that held it up.",
  ],
}
