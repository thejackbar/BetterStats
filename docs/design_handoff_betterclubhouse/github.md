repo: thejackbar/BetterStats
branch: main
path: frontend/src

## Last sync
date: 2026-08-04T04:48:55Z

### Updated in this project
- Audited the four BetterAdmin sub-modules (Fees, Comms, Merch, ClubManager) for UI/UX cohesion and functional overlap.
- Recreated four current screens from source: Fees Members, Comms Emails, Merch Overview, ClubManager Today.
- Imported the real module marks (betterstats, betterselect, betteriq, bettersocials, betteradmin, betterclubmanager svgs) and used them in every lockup and switcher pill.
- Proposed one merged module ("BetterClubhouse"), a six-group sidebar, and redesigned Accounts / Audiences / Inventory in the ClubManager language on the BetterAdmin amber accent.

## Screen map
| Project screen | Repo files |
| --- | --- |
| 1e · BetterFees Members (as-is) | frontend/src/pages/admin/AdminFeesMembers.jsx · AdminFeePayments.jsx · components/admin/BetterFeesLayout.jsx · components/admin/ModuleLayout.jsx |
| 1e · BetterComms Emails (as-is) | frontend/src/pages/admin/bettercomms/CommsCampaigns.jsx · CommsSegments.jsx · components/admin/BetterCommsLayout.jsx · components/admin/CommsContextBar.jsx |
| 1e · BetterMerch Overview (as-is) | frontend/src/pages/admin/bettermerch/BetterMerchHome.jsx · bettermerch/ui.jsx · components/admin/BetterMerchLayout.jsx |
| 1e · BetterClubManager Today (as-is) | frontend/src/pages/admin/clubmanager/redesign/screens/Today.jsx · redesign/ClubManagerApp.jsx · redesign/ui.jsx |
| 1d · Unified sidebar / IA | components/admin/BetterClubManagerLayout.jsx · ModuleLayout.jsx · ModuleSwitcher.jsx · BookmarkButton.jsx · components/ModuleLockup.jsx |
| 1f · Glow up (Today, Accounts, Audiences, Inventory) | clubmanager/redesign/ui.jsx · redesign/screens/Directory.jsx · betterselect/ui.jsx (Icon set) · styles/theme.css · tailwind.config.js · lib/moduleBrand.js |
