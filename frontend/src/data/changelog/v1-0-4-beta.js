export default {
  "version": "v1.0.4 Beta",
  "date": "2026-05-28",
  "sortKey": "2026-05-28T00:01:10Z",
  "title": "Usage page: player names, clickable links, multi-role, geo lookup",
  "items": [
    "Recent events now resolve player profile UUIDs into the player's actual name (e.g. /players/abc-123 → \"Barendse, Jack\"). Game UUIDs in /games, /match, /scorecards URLs resolve to \"Home v Away · 14 Mar 2024\". The name is a clickable link straight to that page in a new tab.",
    "Page-view events without a known target are still rendered as clickable links to the path itself, so you can jump from the log to the page someone landed on.",
    "Role filter is now multi-select. Tick Club Admins + Anonymous to see them together. \"Everyone\" clears the selection. The Members option is gone (we don't have members).",
    "New \"By country\" + \"By city\" cards. Country comes from Cloudflare's cf-ipcountry header (free, instant); city / region are filled in shortly after each visit by a cached ip-api.com lookup. We never store the raw IP, only the resolved location.",
    "Country flag + city now show in each Recent Event row."
  ]
}
