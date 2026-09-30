# Guide: BetterAdmin (Clubhouse) Committee, meeting room, minutes and strategic plans

**Naming.** The module a club reads as **BetterAdmin** is keyed `admin` in code, billing and entitlement. Code, URLs and files still say "clubhouse" (`BetterClubhouseLayout.jsx`, `/admin/clubhouse/*`). History: BetterAdmin, BetterClubhouse (v9.3.0 merge), BetterAdmin again (v9.40.0, display only). Archive headings v9.3 to v9.7 say "BetterClubhouse": same module. Never show "BetterClubhouse" to a person.

**Read this before**:
- Touching `redesign/screens/Committee.jsx`, `pages/admin/MeetingRoom.jsx`, `components/admin/clubmanager/{governance.jsx,minutesDoc.js,planLabels.js}`, `AdminCommittee.jsx`, `lib/textDocs.js`.
- Touching `backend/app/services/{committee,office_bearers,pillar_plan_ddl,plan_tree_ddl}.py`, `routers/committee.py`, migrations 217, 218, 220, 230, 231, 232, 275, 276.
- Strategic plans, themes (pillars), objectives, actions (`committee_tasks`), motions (`meeting_motions`), agenda sections, attendance, minutes Word/PDF, committee uploads, Office Bearer awards.
- Symptoms: search caret lost after one character; room runs off the right edge; theme in the wrong plan; PDF blank pages.

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/clubhouse-committee-and-plans.md`. Grep hints: `button rows`, `NEVER DECLARE A COMPONENT`, `migration 275`, `migration 276`, `PlanDelivery`, `PDF's own typography`, `composed from the record`, `minutes leave the screen`, `migration 232`, `agenda has sections`, `PersonSearch`, `migration 230`, `runs inside the Committee screen`, `migration 217`, `document uploads`, `1fr` leaks.

**Related guides**: `clubhouse-people-roster-fees` (roster, `fee_members`); `comms-audiences-and-notifications` (`owes_money`); `club-directory-onboarding-and-admin-shell` (`ModuleLayout`, nav gating); `cross-club-and-data-safety` (org scoping).

## Standing rules

**Shell and search**
1. The rename is DISPLAY ONLY: key `admin`, entitlement and stored rows untouched. Strings: `MODULE_BRAND.admin.name`, `MODULE_GROUPS.admin.name`, `MODULE_TOGGLES`, `BILLABLE_MODULE_NAMES` (`auth/modules.py`), `ModuleLayout` `moduleName` ("Admin"). `clubhouse` stays in `moduleBrand`'s ALIAS map.
2. Committee buttons: Meetings (default), Plans, Documents, Calendar, Positions (kept though unnamed in the brief). Keys in `st` (`cteMeetingsView`, `cteActionsView`, `cteTab`). Meetings holds All Meetings, Actions (List/Board/Timeline), Motions, Meeting Templates. `cteMaView` is read once, to carry a stored `cteTab === 'motions'`.
3. Plans IS the Strategic Plans tree. `PlanTab` `section="themes"`/`"objectives"` are mounted nowhere (unexercised).
4. Documents, Calendar, Plans, Actions are the manage screen's own components (`TasksTab`, `DocumentsTab`, `CalendarTab`, `PlanTab`), `lazy()`-loaded. Optional `view`/`onView`/`section`/`query` props hide their own control; no props leaves the manage screen unchanged. Header no longer links to `/admin/clubhouse/committee/manage` (route still renders).
5. NEVER declare a component inside a render: new element type each render tears down the subtree and the focused input. Use plain functions and CALL them (`{subBar()}`). `EditableHeading` is module level.
6. One search per section, over the SECTION (`meetingMatches`: agenda, minutes, private notes, every motion and action); `matches()` is the one case-folded rule; section change clears it; Positions not searched. Plan TREE narrows (`railOpenFor` opens all levels), plan DASHBOARD does not (a filtered "2 of 3 on track" is wrong). Filter for drawing only: `groups`, `themesIn`, `objectiveOrder` stay whole or reorder renumbers a filtered list.
7. Committee season = club DIARY year (`organisations.diary_start_month` via `adminGetSettings`). `sel` reads the filtered list.
8. Deleting a Meeting Template in use is safe: `_apply_agenda_template` COPIES items; `agenda_template_id` is ON DELETE SET NULL.

**Plan tree (230, 232, 275, 276)**
9. A plan owns its themes (`club_strategic_pillars.plan_id`), a theme its objectives. `plan_id` on themes and `plan_id`/`pillar_id` on objectives are NOT NULL, ON DELETE CASCADE (SET NULL cannot coexist with NOT NULL). Never key a branch on a NAME.
10. `committee_tasks`/`meeting_motions` to `club_objectives` stays ON DELETE SET NULL. Deleting a plan, theme or objective never deletes an ACTION or MOTION. Do not relax; assert the referential action.
11. A theme is created with its plan, an objective with its theme, or refused. `upsert_objective` takes its plan FROM its theme. In `upsert_pillar`/`upsert_objective` validate BEFORE adding the row (SELECTs autoflush a half-built row: 422 becomes NOT NULL 500).
12. 275 SPLITS a pillar spanning plans BEFORE claiming. 276 order is load-bearing: inherit plan from theme, carrier plan `Unfiled work`, `General` theme in the objective's OWN plan, FKs, NOT NULLs. `pillar_plan_ddl.py` and `plan_tree_ddl.py` are the ONE copy alembic and the lifespan mirror run; keep statements idempotent.
13. 230 backfill guards with `NOT EXISTS`, NOT `ON CONFLICT` (no unique on `(organisation_id, name)` by design; a conflict clause never fires and the lifespan re-run minted plans every boot). `club_objectives.plan` text is history.
14. A pillar is a grouping, not a fourth level. No parent/child plans, `horizon`, `progress_source`, agenda `item_type`.
15. Objective owner: `owner_position_id` (seat) or a named person, never both. Objectives carry `due_date`, `owner_member_id`, `budget`. `objective_progress` emits `own_budget` beside effective `budget`. Plan figures sum OBJECTIVES'.
16. `meeting_motions.objective_id`; an action raised under a motion inherits it.
17. Null means clear: `_TASK_CLEARABLE` assigns on key presence, routers use `exclude_unset`. Title, category, status, percent stay guarded.
18. `plan_report` scopes motions via their MEETING's org; keeps an empty `unassigned` key for older bundles.
19. Seeding is skip-don't-replace at every level, on demand only (`seed_starter_plan`, `STARTER_AGENDA_TEMPLATES`, `_season_label`). A blank page kills adoption.
20. `sort_order` is stamped by POSITION over a WHOLE level (`reorder_plan_tree`); stale ids skipped without gaps. A row drops only on a SIBLING; re-parenting is not a drag.
21. `ObjectiveSelect` (six mounts) is a tree, only LEAVES selectable, headings have no `role="option"`, not a `<select>`. Actions "Any objective" is a FILTER, not this. `planLabels.js` names PLAN > THEME > OBJECTIVE (own file, out of first paint).
22. `ActionEditor`/`MotionEditor` (governance.jsx) are the one editor each; vocabulary constants (`ACTION_STATUSES` etc.) live there. Register motion rows carry `meeting_id` and write to that meeting's endpoint.
23. `?cascade` is gone from plan/theme delete (FLAG-CTE-2). Plan delete takes themes and objectives; theme delete only its own plan's objectives.

**Plan delivery dashboard**
24. `PlanDelivery`: plan figures, attention, a row per theme, objectives inside an opened theme. The OBJECTIVE is the unit. Summarise the plan ONCE (`PlanFigures`). Any number of themes open.
25. No plan-level verdict (`n/m objectives on track`). A group's verdict is the worst beneath, ignoring what cannot be judged. NOT STARTED is an absence, excluded by `rollUp`; all-begun-finished plus some unstarted reads ON TRACK, not DONE.
26. Silence where data cannot answer: no start AND due date, no verdict; nothing allocated, no budget verdict; motions get no meters.
27. Every state is word plus glyph (`StateChip`): never colour alone (green/amber 7.2 delta E under protanopia). Meter with target tick, both 0 to 100, no second axis. `DRIFT_TOLERANCE` 10, `SPEND_TOLERANCE` 15 are deliberate.
28. `TREE_STEP` (`ml-[34px]`) derives from `TWISTY_BOX` (28px) plus row gap. Rails use `color-mix`, never `${accent}66` (accent is a `var()`).

**Agenda sections (231)**
29. `meeting_agenda_items.section` is a LABEL. `reorder_agenda_items` takes optional `sections` parallel to `ids` in ONE write (mismatch ignored; foreign ids ignored). A dragged item adopts the section it lands among; a new item joins the last. A repeated non-adjacent section draws its heading twice. `agenda_templates.items` JSONB `{section, title, description}`.

**Meeting room (220)**
30. One room mounted twice: `MeetingRoomPanel` in Committee, a thin route wrapper at `/admin/clubhouse/committee/meeting/:meetingId` that must stay as it was. Panel reports `{ meeting, setStatus, setTitle, reload }` via `onMeta`; embedded uses `inlineHeader`. Room opens only on the SELECTED meeting.
31. `chip(C.accent)` builds `var(--pb-accent)66` (border vanishes); `openChip` uses `color-mix` and `--pb-accent-ink`.
32. `GET .../meetings/{id}/room` is one fetch (incl. next meeting). Autosave via `useAutosave` (700ms); other writes on click. A completed meeting opens the same screen.
33. Attendance starts from committee-term holders (`meeting_attendee_pool`). Only present people vote or take actions: UI only, `set_motion_votes` accepts anyone. `previous_meeting_attendance`: last 10 meetings of the SAME type, first with someone present, `present` only, button only while empty.
34. `set_task_assignees` writes `committee_task_assignees` AND `assigned_to_member_id` (primary owner). Never drop the column.
35. Motion is a record first, OUTCOME the one live control, Edit closes with `Done` (votes write as cast). Record click opens it but NOT `role="button"`; outcome select, drag handle, Done `stopPropagation`. Openers and finishers must not share a name (`+ Add motion` vs `RECORD MOTION`/`RECORD ACTION`; Enter finishes, Shift+Enter newline, Escape backs out). `MotionForm` `live` flag: existing saves as pressed, new is held. Named votes are a second request; `create_motion` takes `outcome`, tallies, `notes` in one write. Division behind `+ Record a division`, seeded OPEN when names exist.
36. "Due next meeting" fills the REAL date (`next_meeting_after`: same kind, else any, skip cancelled). Motions drag two ways (`kind: 'item' | 'motion'`), ordered meeting-wide but dragged within an item (`motionOrderAfter` splices back).
37. Layout: `xl:grid-cols-[minmax(0,1fr)_320px]`, never bare `1fr`; every level to the scroll container needs `min-width: 0`. `truncate` in a wrapping flex row EXPANDS it; breadcrumbs wrap. No box inside a box. `WHAT WAS SAID` `rows={10}`.
38. In the room, `ObjectiveSelect` and vote lists paint nothing at `--pb-faintest` (1.64:1) or `--pb-faint` (2.75:1); `cap` is `text-pb-dim` (5.40:1).
39. `EditableHeading` (summary `<h2>` and room header): Enter saves, Escape reverts, BLANK refused. The standalone route is NOT editable (title feeds the `ModuleLayout` bookmark label; a node prints `[object Object]`).

**Minutes and documents**
40. Downloads are written IN THE BROWSER from the textarea ref (`downloadField`), never from the record (700ms debounce). `lib/textDocs.js` has no dependency (docx zip STORED). `minutesTyped`/`notesTyped` start `null` = untouched. Buttons disabled, not hidden. Notes file says it is not part of the minutes.
41. Minutes doc is composed from the RECORD (`minutesDoc.buildMinutesDoc`; `M-01` numbers in document order). `splitNarrative` returns `loose` plus `sections`; unclaimed text goes to `Record of Discussion`; a bare line matching an agenda title is a heading. `textDocs` takes BLOCKS; `body` still works. `_minutes_context` nests each motion and action under its agenda item; draft returned, never saved.
42. PDF: `indent` is TWIPS (`pdfIndent` converts, `indentPt` overrides). `/Arial` and `/Arial,Bold` declared TrueType with the measured Widths, nothing embedded; Helvetica-Bold has its own width table. WinAnsi (unmappable becomes `?`), docx UTF-8. `w:sz` half-points, `w:spacing` twentieths; strip control characters (Word rejects the file). Names are "Surname, First": join with semicolons.
43. Every PDF op must report a height (`heightOf`, fallback 0): one NaN gave 19 pages, half blank, content checks green. `push` is variadic.
44. Uploads (218): a row has `url` OR a file (`file_data`, `file_mime`, `file_size`, ...). `MAX_DOCUMENT_BYTES` 15MB, `ALLOWED_DOCUMENT_MIMES` allowlist. `file_data` deferred on lists; `has_file` reads `file_size`. `organisations.committee_docs_office_bearer_only` default TRUE. `can_open_document`: uploader, current Office Bearer, or Main Admin (`club_admin`, unconstrained, per direct instruction). Governs UPLOADS only; UI copy must not imply a wall around links. Enforced at `GET /documents/{id}/file` (`private, no-store`); PATCH/DELETE via `_document_writable_or_403`; list `can_open` is presentation. `member_for_user` joins on lowercased email (no FK). `is_office_bearer` derives from role TYPE.
45. Office Bearer awards ARE roles (`office_bearers.py`): subcategory a `club_role_types` row, achievement a `club_roles` row, `player_achievements.club_role_id`. `sync_award_definitions` two-way, idempotent, in try/rollback; ADOPT from definitions AND achievements; seed gated on having no ROLES. `PUBLISHED_ROLE_TYPES`/`COMMITTEE_ROLE_TYPES` filter awards and seats. `ensure_role_for_award` matches on title, never retypes. `adopt_awards_as_terms` inserts directly (not `start_term`), idempotent, season 1 Jul to 30 Jun, no season skipped.
46. `PersonSearch` (`clubmanager/pickers.jsx`): SERVER searches; use over `MemberSelect` where the whole club is offered. `GET /club-admin/fees/people/search` = `fee_members` UNION unenrolled players, org-scoped, archived hidden, `needs_member`. Debounce 220ms, drop stale responses. `start_term` takes `player_id` and enrols via `members.ensure_for_player` under `MANAGE_COMMITTEE`.

**Governance schema (217)**
47. `club_objectives`, `committee_task_dependencies`, `meeting_motion_votes`, `committee_notes`; columns on `committee_tasks`, `meeting_motions` (`is_resolution`, `resolution_ref`, `resolved_at`), `committee_documents` (`entity_type`, `entity_id`). Lifespan-mirrored. Only a carried motion can become a resolution. Named votes RE-DERIVE tallies. `ActionTimeline`: ticks snap to the 1st; `chain()` needs the `walking` cycle guard.
48. `owes_money` is derived, never SQL: `services/fees.owing_player_ids`.

## Traps and failure signatures
- Search loses focus after one character: rule 5 (type per character to test; `fill()` cannot catch it).
- Second plan shows first plan's themes, or theme delete removes another plan's objectives: club-scoped pillars (232, superseded by 275).
- 500 not 422 saving a foreign-plan theme (rule 11); plans re-minted every boot (rule 13); "allocated $0" (missing `own_budget`); cannot clear an action field (`is not None` guard).
- New task/document field ignored: missing from Pydantic `TaskCreate`/`TaskPatch`/`DocumentCreate`/`DocumentPatch`.
- `MissingGreenlet`: `await db.refresh(obj)` after `commit()`; never touch deferred `file_data` on a list row.
- `confdeltype` arrives as bytes from asyncpg: cast `::text`.
- Room and rail run off the right: rule 37. Test the EMBEDDED room in a narrow pane.
- PDF 19 pages half blank (rule 43); indent a third of a page (twips as points); whole account in one lump with the model's title block (rule 41); typed minutes missing (rule 40).
- Roster blank forever when opened before areas were configured: fixed by `_has_shifts` then `_generate_shifts` (roster guide). Editors unrouted since commit `6ff23c6` live under `/admin/clubhouse/*/manage`.

## How to verify a change here
- In repo: `frontend/verification/verify_minutes_download_browser.mjs` (control with the change stashed: no rows, no downloads) and `verify_clubhouse_buttons_browser.mjs`. The archive cites more (`room.mjs`, `check2.mjs`, Postgres suites for 217 to 276, `next_meeting_after`) that are not in the repo (FLAG-CTE-8).
- Control runs must fail on: search focus (all five characters lose it), room box rows and 1.64:1 text, 282px overflow at 1440, minutes doc tables, PDF indent, gaps, font names.
- Postgres: migration applied three times to a populated table; alembic and lifespan reach the same schema; referential actions read from `pg_constraint`; cross-club rejection of foreign plan, pillar, position ids.
- Harness: `create_all` builds ORM tables only, so replay lifespan `text(...)` statements. Stub shapes must match (`previous_attendance` object or null; single-meeting GET returns the MEETING). `\d` in a JS template literal is `d`; `getByRole` `name` is a substring (use `exact: true`). HTML5 drag: dragstart and drop in SEPARATE `evaluate` calls. PDF gaps are per page; repeating header means count with `>=`. Contrast checks must walk every element.

## Operator commands and scripts
None. Migrations 217, 218, 220, 230, 231, 232, 275, 276 are lifespan-mirrored and re-run each boot: keep every statement idempotent.

## Open follow-ups
- Objective TARGETS (label, target, current); an objective's percent is effort, not outcome.
- Fold manage-screen CRUD into the viewers (manage routes are a bridge).
- No further Committee to Awards "Office Bearer" wiring without asking. No platform-wide `--pb-faint` text sweep yet.

## Flags: conflicting, superseded or possibly obsolete guidance
- [FLAG-CTE-1] Headings say "BetterClubhouse" (v9.3 to v9.7); v9.40.0 renamed back | `BILLABLE_MODULE_NAMES` says BetterAdmin; identifiers keep "clubhouse" | sections 1, 7 to 10 | keep; BetterAdmin for anything a person reads.
- [FLAG-CTE-2] `?cascade=true` opt-in on plan/pillar delete vs "no `cascade` flag on either delete route any more", both in section 1 | `grep cascade routers/committee.py` finds nothing | section 1 (archive L211, L360) | retire the `?cascade` bullet.
- [FLAG-CTE-3] 230: "a deleted plan leaves its objectives" | superseded in part by 276; action/motion half holds | section 9 (archive L765-771) | keep that half.
- [FLAG-CTE-4] 232: pillars club-scoped across plans | superseded by 275; the rest of 232 holds | section 3 (L7854-7903) | retire club-scoped claim.
- [FLAG-CTE-5] v9.4.0 follow-up appears twice; the first lists Gantt, upload, Office Bearer sync as "not built" | all three now exist (218, `ActionTimeline`, `office_bearers.py`) | sections 7, 8 | retire "not built" lists.
- [FLAG-CTE-6] Section 8 names `ObjectivesTab`, `ActionPlanPanel` | now `PlanTab`, `ActionEditor` | sections 8, 9, 1 | retire old names.
- [FLAG-CTE-8] Archive cites Postgres and Chromium suites for plans, room, minutes, agenda, `PersonSearch`, documents | `backend/verification` has none (`verify_committee_rediscover.py` is the Club Directory); only two frontend suites exist here | all sections | verify before trusting a claimed check.
- [FLAG-CTE-9] Legibility: room, `ObjectiveSelect` paint no faint text | `MeetingRoom.jsx` clean; `governance.jsx` has 115 `text-pb-faint`/`faintest` uses | section 11 (archive L1149) | verify picker and vote list.
- [FLAG-CTE-10] Roster regeneration and `owes_money` belong to other areas | overlaps sibling guides | sections 7, 8 | keep one line here.
- [FLAG-CTE-11] Seed label hardcoded "(18)" committee roles | `STARTER_COMMITTEE_ROLES` appears twice in `services/roles_activities.py` (L69, L115) | section 10 (archive L1046-1049) | verify.
- [FLAG-CTE-12] 220 renumbered because AFL took 219 | history; same collision trap recurs | section 11 (archive L1094-1098) | keep as reminder: check `origin/main` at merge.

## Section coverage
Sub-row original lines are approximate (archive line plus section offset).
| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| BetterClubhouse is BetterAdmin again, and Committee got its button rows (v9.40.0), L5392-5894 | rules extracted | Rules 1 to 28, Traps 1 to 3 |
| - v9.48.2 to v9.51.1 sub-notes (~L5418-5709) | rules extracted | Rules 4 to 6, 9 to 13, 20 to 28 |
| - ### The PDF's own typography (v9.53.4) (~L5800) | rules extracted | Rules 42, 43 |
| - ### The minutes are a DOCUMENT (v9.53.3) (~L5840) | rules extracted | Rules 41, 43 |
| The minutes leave the screen as a document (v9.53.2), L5895-5960 | rules extracted | Rule 40 |
| Themes, a seat that owns work, and a plan to start from (232, v9.19.3), L7854-7903 | superseded in part by section 1 (275) | Rules 14, 15, 19; FLAG-CTE-4 |
| An agenda has sections (231, v9.19.2), L7904-7947 | rules extracted | Rules 19, 29 |
| Picking a person is a SEARCH, not a list (v9.19.1), L7948-7985 | rules extracted | Rule 46 |
| Strategic plans -> objectives -> actions and motions (230, v9.19.0), L7986-8074 | superseded in part by 276 | Rules 13, 15 to 18, 21, 22; FLAG-CTE-3 |
| The meeting room runs inside the Committee screen (v9.17.1), L8370-8405 | rules extracted | Rules 30, 31 |
| BetterClubhouse follow-ups: roster, orphaned editors, governance (v9.4.0), L9283-9340 | rules extracted (duplicated by next) | Rules 47, 48; last Trap; FLAG-CTE-5, 10 |
| BetterClubhouse follow-up: roster fix, committee governance (v9.4.0 to v9.5.0), L9487-9552 | rules extracted (near duplicate) | Rules 47, 48; Traps 4, 5 |
| Committee document uploads + Office Bearer awards on Clubhouse roles (218, v9.6.0), L9553-9646 | rules extracted | Rules 44, 45; FLAG-CTE-11 |
| - ### Uploaded committee documents (~L9558) | rules extracted | Rule 44 |
| - ### Office Bearer awards ARE BetterClubhouse roles (~L9596) | rules extracted | Rule 45 |
| The meeting room, running a committee meeting (v9.7.0, 220), L9672-9924 | rules extracted | Rules 32 to 39 |
| - v9.50.5 to v9.53.8 sub-notes (~L9711-9882) | rules extracted | Rules 35, 37, 39 |
| - v9.53.7 legibility and probe traps (~L9748) | rules extracted | Rule 38; FLAG-CTE-9 |
| - v9.7.2 motions drag two ways, attendance carries over (~L9908) | rules extracted | Rules 33, 36 |
