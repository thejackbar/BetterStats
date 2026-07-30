repo: thejackbar/BetterStats
branch: main
path: frontend/src

## Last sync
date: 2026-07-31T00:00:00Z

### Updated in this project
- Recreated the current BetterClubManager UI (shell + Volunteers/Roles/Activities/Qualifications) for before-and-after comparison.
- Redesigned People + Club as seven connected surfaces: Today, Roster, Directory, Committee, Club Diary, Facilities, Areas & Roles, Events.
- Added a Deputy-style drag-and-drop Roster with working rules (qualification, availability, overlap, cap, fairness, match clash, family) — no upstream equivalent.
- Rebuilt the Club Diary as a template library that generates a dated season plan with dependencies, blockages and a critical path.

## Screen map
| Project screen | Repo files |
| --- | --- |
| BetterClubManager Today.dc.html — shell | frontend/src/components/admin/ModuleLayout.jsx, components/admin/BetterClubManagerLayout.jsx, components/admin/ModuleHub.jsx, components/admin/HubCard.jsx, components/ModuleLockup.jsx, lib/moduleBrand.js, styles/theme.css, tailwind.config.js |
| BetterClubManager Today.dc.html — Volunteers | frontend/src/pages/admin/AdminVolunteers.jsx, components/admin/clubmanager/pickers.jsx |
| BetterClubManager Today.dc.html — Roles | frontend/src/pages/admin/AdminRoles.jsx |
| BetterClubManager Today.dc.html — Activities | frontend/src/pages/admin/AdminActivities.jsx |
| BetterClubManager Today.dc.html — Qualifications | frontend/src/pages/admin/AdminQualifications.jsx |
| BetterClubManager Today.dc.html — Committee (header/tabs only) | frontend/src/pages/admin/AdminCommittee.jsx |
| BetterClubManager Today.dc.html — Events (header/tabs only) | frontend/src/pages/admin/AdminEvents.jsx |
| BetterClubManager Today.dc.html — Assets & Facilities (header/tabs only) | frontend/src/pages/admin/AdminAssets.jsx |
| BetterClubManager Today.dc.html — Club Diary (header/tabs only) | frontend/src/pages/admin/AdminClubDiary.jsx |
| BetterClubManager Today.dc.html — Families (header only) | frontend/src/pages/admin/AdminFamilies.jsx |
| BetterClubManager Redesign.dc.html — Today | new surface; aggregates state from every other screen |
| BetterClubManager Redesign.dc.html — Roster | new surface; theme from styles/theme.css + lib/moduleBrand.js, icons from pages/admin/betterselect/ui.jsx |
| BetterClubManager Redesign.dc.html — Directory | replaces pages/admin/AdminVolunteers.jsx, AdminFamilies.jsx, AdminQualifications.jsx, AdminActivities.jsx |
| BetterClubManager Redesign.dc.html — Committee | replaces pages/admin/AdminCommittee.jsx (positions, meetings, motions, actions) |
| BetterClubManager Redesign.dc.html — Club Diary | replaces pages/admin/AdminClubDiary.jsx |
| BetterClubManager Redesign.dc.html — Facilities | replaces pages/admin/AdminAssets.jsx (availability, requests, assets & loans) |
| BetterClubManager Redesign.dc.html — Events | replaces pages/admin/AdminEvents.jsx (ticketing, RSVP, attendees) |
| BetterClubManager Redesign.dc.html — Areas & Roles | replaces pages/admin/AdminRoles.jsx + AdminActivities.jsx type tabs; configures the roster |

Icon glyphs are lifted from `frontend/src/pages/admin/betterselect/ui.jsx` (ICON_PATHS). Module accent for
ClubManager is `#6366F1` per `lib/moduleBrand.js`.
