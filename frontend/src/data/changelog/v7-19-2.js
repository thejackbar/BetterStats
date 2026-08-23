export default {
  "version": "v7.19.2",
  "date": "2026-05-27",
  "sortKey": "2026-05-27T00:00:50Z",
  "title": "Fix: doubled logo on marketing pages, scroll-to-top on nav",
  "items": [
    "Marketing pages were rendering both the global Navbar and MarketingNav simultaneously, causing doubled logos. Global Navbar is now suppressed on all marketing routes.",
    "Navigating to a new page via the nav now always scrolls to the top of the page. Hash anchor links (e.g. /features#compare) are excluded and continue to scroll to their target section.",
    "About page hero is now full-width. Removed the founder photo placeholder."
  ]
}
