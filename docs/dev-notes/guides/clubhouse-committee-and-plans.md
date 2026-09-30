# Guide: BetterAdmin (Clubhouse) Committee, meeting room, minutes and strategic plans

**Naming.** The module a club reads as **BetterAdmin** is keyed `admin` in code, billing and entitlement. Code, URLs and files still say "clubhouse" (`BetterClubhouseLayout.jsx`, `/admin/clubhouse/*`, `redesign/screens/Committee.jsx`). History: BetterAdmin, then BetterClubhouse (v9.3.0 merge), then BetterAdmin again (v9.40.0, display only). Archive headings from v9.3 to v9.7 say "BetterClubhouse". Same module. Never show "BetterClubhouse" to a person.

**Read this before**:
- Touching `frontend/src/pages/admin/clubmanager/redesign/screens/Committee.jsx`, `pages/admin/MeetingRoom.jsx`, `components/admin/clubmanager/{governance.jsx,minutesDoc.js,planLabels.js}`, `AdminCommittee.jsx`, `lib/textDocs.js`.
- Touching `backend/app/services/{committee,office_bearers,pillar_plan_ddl,plan_tree_ddl}.py`, `routers/committee.py`, migrations 217, 218, 220, 230, 231, 232, 275, 276.
- Strategic plans, themes (pillars), objectives, actions (`committee_tasks`), motions (`meeting_motions`), agenda sections and templates, attendance, minutes Word/PDF download, committee uploads, Office Bearer awards.
- Symptoms: caret leaves a search box after one character; meeting room runs off the right edge; a theme shows in the wrong plan; deleting lost objectives; PDF with blank pages or huge indents; pale unreadable text in the room.

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/clubhouse-committee-and-plans.md`. Grep hints: `button rows`, `NEVER DECLARE A COMPONENT`, `migration 275`, `migration 276`, `PlanDelivery`, `PDF's own typography`, `composed from the record`, `minutes leave the screen`, `migration 232`, `agenda has sections`, `PersonSearch`, `migration 230`, `runs inside the Committee screen`, `migration 217`, `document uploads`, `1fr` leaks.

**Related guides**: `clubhouse-people-roster-fees` (roster, `fee_members`, Directory); `comms-audiences-and-notifications` (`owes_money`); `club-directory-onboarding-and-admin-shell` (`ModuleLayout`, nav capability gating); `cross-club-and-data-safety` (org scoping).

## Standing rules

**Shell and search**
1. The BetterAdmin/BetterClubhouse rename is DISPLAY ONLY. Entitlement, `org_module_subscriptions`, key `admin` and stored rows are untouched. Display strings: `MODULE_BRAND.admin.name`, `MODULE_GROUPS.admin.name`, `MODULE_TOGGLES`, `BILLABLE_MODULE_NAMES` (`auth/modules.py`), `ModuleLayout` `moduleName` ("Admin"). `clubhouse` stays in `moduleBrand`'s ALIAS map.
2. Committee buttons: Meetings (default), Plans, Documents, Calendar, Positions (kept though the brief omitted it). Keys live in `st` (`cteMeetingsView`, `cteActionsView`, `cteTab`). Meetings holds All Meetings, Actions (List/Board/Timeline), Motions, Meeting Templates. `cteMaView` is read once, to carry a stored `cteTab === 'motions'` onto its new button.
3. Plans IS the Strategic Plans tree. `PlanTab` `section="themes"`/`"objectives"` are mounted nowhere (kept, unexercised).
4. Documents, Calendar, Plans, Actions board/timeline are the manage screen's own components (`TasksTab`, `DocumentsTab`, `CalendarTab` from `AdminCommittee.jsx`; `PlanTab` from `governance.jsx`), `lazy()`-loaded. Optional `view`/`onView`, `section`, `query` props hide the component's own control; passing nothing leaves the manage screen unchanged. The header no longer links to `/admin/clubhouse/committee/manage` (route still renders).
5. NEVER declare a component inside a render. New element type each render tears down the subtree and the focused input. Use plain functions and CALL them (`{subBar()}`). `EditableHeading` is module level.
6. One search per section, over the SECTION (`meetingMatches`: agenda, minutes, private notes, every motion and action). `matches()` is the one case-folded rule. Section change clears the query. Positions not searched. Plan TREE narrows (`railOpenFor` opens all levels); plan DASHBOARD does not (a filtered "2 of 3 on track" is wrong). Filter for drawing only: `groups`, `themesIn`, `objectiveOrder` stay whole or reorder renumbers a filtered list.
7. Committee season = club DIARY year (`organisations.diary_start_month` via `adminGetSettings`; a committee manager lacks `MANAGE_SETTINGS`). `sel` reads the filtered list.
8. Deleting a Meeting Template while meetings use it is safe: `_apply_agenda_template` COPIES items and `agenda_template_id` is ON DELETE SET NULL. Delete-meeting confirm names agenda, motions, attendance, minutes. No toast on this screen: errors go in a line under the header.

**Plan tree (migrations 230, 232, 275, 276)**
9. A plan owns its themes (`club_strategic_pillars.plan_id`), a theme owns its objectives. `plan_id` on themes and `plan_id`/`pillar_id` on objectives are NOT NULL with ON DELETE CASCADE (SET NULL cannot coexist with NOT NULL). Never key a branch on a NAME (two plans may share one).
10. `committee_tasks` and `meeting_motions` to `club_objectives` stays ON DELETE SET NULL. Deleting a plan, theme or objective never deletes an ACTION or MOTION. The one rule not to relax; assert the referential action.
11. A theme is created with its plan or refused; an objective with its theme or refused. `upsert_objective` takes its plan FROM its theme. In `upsert_pillar`/`upsert_objective` validate BEFORE adding the row (ownership checks are SELECTs that autoflush a half-built row: 422 becomes NOT NULL 500). Pane adds the level below, rail adds at the level you are on; the plan comes off the THEME's `plan_id`, never a positional fallback.
12. 275 SPLITS a pillar whose objectives span plans (copy per extra plan) BEFORE claiming. 276 order is load-bearing: inherit plan from theme, carrier plan `Unfiled work`, `General` theme in the objective's OWN plan, FKs, NOT NULLs. `services/pillar_plan_ddl.py` and `plan_tree_ddl.py` are the ONE copy alembic and the lifespan mirror run; keep every statement idempotent.
13. 230 backfill guards with `NOT EXISTS`, NOT `ON CONFLICT` (no unique on `(organisation_id, name)` by design, a club may name two plans alike; a conflict clause never fires and the lifespan re-run minted plans every boot). Old `club_objectives.plan` text is history.
14. A pillar is a grouping, not a fourth level. Resist adding one. No parent/child plans, `horizon` enum, `progress_source`, or agenda `item_type`.
15. Objective owner: `owner_position_id` (a seat, moves at the AGM) or a named person, one written, never both. Objectives carry own `due_date`, `owner_member_id`, `budget`. `objective_progress` emits `own_budget` beside effective `budget` (else rolled-up 0 reads "allocated $0"). Plan figures sum OBJECTIVES', not a second pass over actions.
16. `meeting_motions.objective_id` exists; an action raised under a motion inherits its objective. Action `raised_meeting_id` (own meeting else motion's) never overwrites `meeting_id`.
17. Null means clear: `_TASK_CLEARABLE` assigns on key presence; routers use `exclude_unset`. Title, category, status, percent stay guarded (NOT NULL).
18. `plan_report` scopes motions through their MEETING's org (no `organisation_id` on motions). It still emits an empty `unassigned` key for older bundles mid-deploy.
19. Seeding is skip-don't-replace at every level (`seed_starter_plan`: four pillars, plan named by `_season_label`, one example objective per pillar; `STARTER_AGENDA_TEMPLATES`). On demand only. A blank page kills adoption.
20. `sort_order` stamped by POSITION over a WHOLE level (`reorder_plan_tree`); stale ids skipped without gaps; "+ THEME" creates then splices after the selection. A row drops only on a SIBLING (same level and branch); re-parenting is not a drag.
21. `ObjectiveSelect` (six mounts) is a tree, only LEAVES selectable; plan/theme rows are headings without `role="option"`; not a `<select>`. The Actions "Any objective" dropdown is a FILTER, not this. `planLabels.js` names PLAN > THEME > OBJECTIVE; `objectiveLabel` and `objectiveTiers` share data; separate file to stay out of first paint.
22. `ActionEditor`/`MotionEditor` (governance.jsx) are the one editor each, opened from list, board, timeline, tree (`inline` = content not dialog). Vocabulary (`ACTION_CATEGORIES`, `ACTION_STATUSES`, `ACTION_STATUS_LABELS`) lives there. Motions belong to a MEETING: register rows carry `meeting_id` and write to that meeting's endpoint. Board lanes are drop targets (apply locally, roll back on failure).
23. `?cascade` is gone from plan/theme delete (FLAG-CTE-2). Plan delete takes its themes and objectives; theme delete only its own plan's objectives.

**Plan delivery dashboard (`PlanDelivery`)**
24. Dashboard, not dump: plan figures, then what needs attention, then a row per theme; objectives in an opened theme, work in an opened objective. The OBJECTIVE is the unit. Summarise the plan ONCE (`PlanFigures` in the title card). Any number of themes open (`openThemes` Set, `jumpTo` unions). Rail folds away, not tabs.
25. No plan-level verdict (headline is `n/m objectives on track` plus attention count). A group's verdict is the worst beneath, ignoring what cannot be judged. NOT STARTED is an absence: `rollUp` excludes it; all-begun-finished plus some unstarted reads ON TRACK not DONE.
26. Silence where data cannot answer: no start AND due date, no verdict or tick; nothing allocated, no budget verdict; motions get no meters. `NO DATES` is muted metadata.
27. Every state is word plus glyph (`StateChip`: DONE, ON TRACK, BEHIND, LATE, NO DATES, OVER BUDGET, SPENDING AHEAD, IN BUDGET). Green/amber differ only 7.2 delta E (protanopia), red/amber 14 (light theme). Never colour alone. Meter with a target tick, both 0 to 100, never a second axis; tick only on action detail; scanning surfaces write variance. `DRIFT_TOLERANCE` 10, `SPEND_TOLERANCE` 15 are deliberate.
28. Tree geometry: `TREE_STEP` (`ml-[34px]`) derives from `TWISTY_BOX` (28px) plus row gap (caret under parent label's first letter); `Twisty` IS the 28x28 button; one-line row 37px. Rails use `color-mix`, never `${accent}66` (accent is a `var()`).

**Agenda sections (231)**
29. `meeting_agenda_items.section` is a LABEL, not a table. `reorder_agenda_items` takes optional `sections` parallel to `ids` in ONE write (mismatched pair ignored; ids not in the meeting ignored). A dragged item adopts the section it lands among; a new item joins the last section. A repeated non-adjacent section draws its heading twice (never sort behind the club's back). `agenda_templates.items` is JSONB `{section, title, description}`.

**Meeting room (migration 220)**
30. One room mounted twice: `MeetingRoomPanel` (no chrome) in Committee and a thin route wrapper at `/admin/clubhouse/committee/meeting/:meetingId` that must stay as it was. Panel reports `{ meeting, setStatus, setTitle, reload }` via `onMeta`; embedded uses `inlineHeader`. Room opens only on the SELECTED meeting. `refreshMeeting` re-reads once on exit.
31. `chip(C.accent)` builds `var(--pb-accent)66`, so the border vanishes; `openChip` uses `color-mix` and `--pb-accent-ink`.
32. `GET .../meetings/{id}/room` is one fetch (meeting, agenda, motions with votes, actions, attendance, pool, next meeting). Autosave via `useAutosave` (700ms); other writes on click. A completed meeting opens the same screen; nothing read-only.
33. Attendance starts from committee-term holders (`meeting_attendee_pool`). Only present people vote or take actions: UI only, `set_motion_votes` accepts anyone. `previous_meeting_attendance`: last 10 meetings of the SAME type, first with someone present, carries `present` only, button only while empty.
34. `assigned_to_member_id` stays primary owner; `set_task_assignees` writes `committee_task_assignees` AND that column (first id). Never drop the column; `load_task_assignees` falls back to it.
35. Motion is a record first: row shows wording, tally, objective; OUTCOME the one live control; Edit closes with `Done` (votes write as cast). Record click opens it but NOT `role="button"` (giant accessible name broke picker tests); outcome select, drag handle, Done `stopPropagation`. Openers and finishers must not share a name: `+ Add motion` opens, `RECORD MOTION`/`RECORD ACTION` finish (Enter finishes, Shift+Enter newline, Escape backs out). `MotionForm` has a `live` flag: existing saves as pressed, new is held. Named votes are a second request (need the motion id); `create_motion` takes `outcome`, tallies, `notes` in one write. Movers come from the room but a recorded name stays selectable. Draw `moved by / seconded by` only when set. A division sits behind `+ Record a division`, seeded OPEN when names exist; tallies derive from names; `All present: For` is one click.
36. Action due "next meeting" fills the REAL date (`next_meeting_after`: same kind, else any, skip cancelled). Motions drag two ways (`kind: 'item' | 'motion'`); motions are ordered meeting-wide but dragged within an item, so `motionOrderAfter` splices back; handle `stopPropagation` on `onDragStart`.
37. Layout: grid is `xl:grid-cols-[minmax(0,1fr)_320px]`, never bare `1fr`; every level down to the scroll container needs `min-width: 0`. `truncate` in a wrapping flex row EXPANDS it; breadcrumbs wrap. No box inside a box (tinted left edge only; agenda item is the container). `WHAT WAS SAID` is `rows={10}`.
38. Legibility: in the room, `ObjectiveSelect` and vote lists paint nothing at `--pb-faintest` (1.64:1) or `--pb-faint` (2.75:1); `cap` is `text-pb-dim` (5.40:1). Tokens unchanged.
39. `EditableHeading` (exported from `MeetingRoom.jsx`) mounted in the summary `<h2>` and room header: Enter saves, Escape reverts sending nothing, BLANK refused. Standalone route deliberately not editable (title feeds `ModuleLayout` bookmark label; a node prints `[object Object]`). `setTitle` reloads rather than patching.

**Minutes and documents**
40. Downloads are written IN THE BROWSER from the textarea ref (`downloadField`), never from the record (700ms debounce would miss the last sentence). `lib/textDocs.js` has no dependency (docx zip STORED, PDF objects plus xref). `minutesTyped`/`notesTyped` start `null` = untouched. Buttons disabled, not hidden, with a title. Notes file says it is not part of the minutes.
41. Minutes doc is composed from the RECORD (`minutesDoc.buildMinutesDoc`: details table, agenda, numbered sections, motions/actions per item, `M-01` motions summary in document order, actions table). `splitNarrative` returns `loose` plus `sections`; unclaimed text goes to `Record of Discussion`. A bare line matching an agenda title is a heading; a short run before the first heading is dropped as preamble. `textDocs` takes BLOCKS (title, heading, para, label, bullets, table, spacer); `body` still works. `_minutes_context` nests each motion and action under its agenda item; draft is returned, never saved.
42. PDF: `indent` is TWIPS, `pdfIndent` converts, `indentPt` overrides. Fonts `/Arial` and `/Arial,Bold` declared TrueType with Widths, nothing embedded; declared Widths are the measured ones; Helvetica-Bold has its own width table. WinAnsi (curly quotes mapped, unmappable becomes `?`); docx is UTF-8. Wrap on real advance widths, break over-long words by character. `w:sz` half-points, `w:spacing` twentieths; strip control characters (Word rejects the file); blank line either side of agenda headings and MOTION/ACTION labels (`w:spacing w:before` ~240). Names are "Surname, First": join with semicolons. Size short table columns to the widest real value. Table header repeats per page.
43. Every PDF op must report a height (`heightOf`, falls back to 0); one NaN gave 19 pages, half blank, content checks green. `push` is variadic.
44. Committee uploads (218): row has `url` OR a file (`file_data`, `file_name`, `file_mime`, `file_size`, `uploaded_by_user_id`), never both. `MAX_DOCUMENT_BYTES` 15MB, `ALLOWED_DOCUMENT_MIMES` allowlist. `file_data` deferred on lists; `has_file` reads `file_size`. `organisations.committee_docs_office_bearer_only` default TRUE (`/club-admin/settings`, `MANAGE_SETTINGS`). `can_open_document`: uploader, current Office Bearer, or Main Admin (`club_admin`, unconstrained, per direct instruction). Governs UPLOADS only: a link is not hosted by us, so UI copy must not imply a wall. Enforced at `GET /documents/{id}/file` (`Cache-Control: private, no-store`); PATCH/DELETE via `_document_writable_or_403`; list `can_open` is presentation. No `users` to `fee_members` FK: `member_for_user` joins on lowercased email. `is_office_bearer` derives from role TYPE (`_role_is_office_bearer`, resynced each `sync_committee_positions`, name set as fallback).
45. Office Bearer awards ARE roles (`services/office_bearers.py`): category "Office Bearer", subcategory a `club_role_types` row, achievement a `club_roles` row, `player_achievements.club_role_id`. `sync_award_definitions` two-way, idempotent, in try/rollback from `GET /award-definitions`; ADOPT from definitions AND recorded achievements; seed gated on having no ROLES. Maps: `SUBCATEGORY_TO_ROLE_TYPE`/`ROLE_TYPE_TO_SUBCATEGORY`; `PUBLISHED_ROLE_TYPES` excludes ground staff, canteen, officials; `COMMITTEE_ROLE_TYPES` decides seats. `ensure_role_for_award` matches on title, never retypes. `adopt_awards_as_terms` inserts directly (not `start_term`), idempotent on (position, holder, start); season is 1 Jul to 30 Jun; no season skipped. `_season_year` takes a UUID or "2025/26".
46. `PersonSearch` (`clubmanager/pickers.jsx`): the SERVER searches; use over `MemberSelect` where the whole club is offered. `GET /club-admin/fees/people/search` = `fee_members` UNION unenrolled players, org-scoped both sides, archived hidden, `needs_member: true`, limit+1 to say "more". Debounce 220ms, drop stale responses. `start_term` takes `player_id`, enrols via `members.ensure_for_player` (idempotent, un-archives), one request under `MANAGE_COMMITTEE`. `/fees/all-members` unchanged for its eight callers.

**Governance schema (217)**
47. Tables `club_objectives`, `committee_task_dependencies`, `meeting_motion_votes`, `committee_notes` (task, motion, meeting, objective); columns on `committee_tasks` (`budget_estimate`, `actual_expenditure`, `percent_complete`, `start_date`, `objective_id`, `meeting_id`, `motion_id`, `outcome_notes`, `closed_by_member_id`), `meeting_motions` (`is_resolution`, `resolution_ref`, `resolved_at`), `committee_documents` (`entity_type`, `entity_id`). Lifespan-mirrored. Only a carried motion can become a resolution (`make_resolution`). Named votes RE-DERIVE tallies. `ActionTimeline`: ticks snap to the 1st, ruler shares the rows' `w-[38%]` geometry, `chain()` needs the `walking` cycle guard.
48. `owes_money` is derived, never SQL: `services/fees.owing_player_ids` into `player_id IN (...)`.

## Traps and failure signatures
- Search loses focus after one character: component in a render body (rule 5). `fill()` cannot catch it; type per character, re-read `document.activeElement`.
- Second plan shows first plan's themes / theme delete removes another plan's objectives: club-scoped pillars (232, superseded by 275).
- 500 instead of 422 saving a theme for a foreign plan: autoflush (rule 11). Plans re-minted every boot: `ON CONFLICT` (rule 13). "Allocated $0": missing `own_budget`. Cannot clear an action's objective/budget/date: `is not None` guard.
- New task/document field ignored, plan reports 0 actions: added to migration and service but not Pydantic `TaskCreate`/`TaskPatch`/`DocumentCreate`/`DocumentPatch`.
- `MissingGreenlet`: after `commit()` call `await db.refresh(obj)` before serialising (vote, resolution endpoints), and never touch deferred `file_data` on a list row.
- `confdeltype` arrives as bytes from asyncpg: cast `::text` or `'c'` comparisons are quietly false.
- Room and rail run off the right: bare `1fr` or `truncate` in flex (rule 37). Test the EMBEDDED room in a narrow pane, not only the standalone page.
- PDF 19 pages half blank (rule 43); indent a third of the page (twips as points); whole account in one Record of Discussion lump with the model's title block (rule 41); typed minutes missing from a file (rule 40).
- Old `Motions & Actions` tab user lands on nothing: `cteMaView` carry-over.
- A roster left blank forever for clubs that opened it before configuring areas: `get_or_create_week` never regenerated an empty draft. `services/roster.py` now does (`_has_shifts` then `_generate_shifts`); detail in the roster guide.
- ~5,300 lines of editors (`AdminCommittee`, `AdminFamilies`, `AdminClubDiary`, `AdminAssets`, `AdminEvents`, Qualifications, Volunteers, Roles, Activities) had no route after commit `6ff23c6`; they live under `/admin/clubhouse/*/manage`.

## How to verify a change here
- Suites present in repo: `frontend/verification/verify_minutes_download_browser.mjs` (control with the change stashed finds no rows, no downloads) and `verify_clubhouse_buttons_browser.mjs`. The archive cites others (room suite `room.mjs`, minutes suite, `check2.mjs`, Postgres suites for 217, 218, 220, 230 to 232, 275, 276, `next_meeting_after`) that are not in the repo under obvious names (FLAG-CTE-8).
- Control runs that mattered: search focus (all five characters lose it); room 16 of 90 failed (box rows, 21 elements at 1.64:1, overflow 282px at 1440); minutes doc control has no club heading or tables; PDF typography checks fail on indent, gaps, font names.
- Postgres: migration applied three times to a populated table; alembic and lifespan mirror reach the same schema; read all referential actions from `pg_constraint`; action and motion outlive a whole plan unlinked; cross-club rejection of foreign plan, pillar, position ids.
- Harness gotchas: `create_all` builds ORM tables only, so replay the lifespan `text(...)` statements skipping failures with the lifespan stubbed. Stub API shapes must match (`previous_attendance` is object or null; single-meeting GET returns the MEETING). `page.evaluate` of a STRING is an expression; `\d` in a template literal is `d` (write `\\d`); `getByRole` `name` is substring (use `exact: true`). Test HTML5 drag with `DragEvent`s, dragstart and drop in SEPARATE `evaluate` calls. PDF gaps are per page. Header repeats, so count with `>=`. A contrast check must walk every element against the browser-resolved token.

## Operator commands and scripts
None. Migrations 217, 218, 220, 230, 231, 232, 275, 276 are lifespan-mirrored and re-run every boot, so every statement must stay idempotent.

## Open follow-ups
- Objective TARGETS (label, target, current figure); today an objective's percent is effort (mean of actions), not outcome.
- Fold manage-screen CRUD into the viewers (the manage routes are a bridge).
- Do not wire Committee to Awards "Office Bearer" beyond `office_bearers.py` without asking.
- A platform-wide sweep of `--pb-faint`/`--pb-faintest` used as text was not done.

## Flags: conflicting, superseded or possibly obsolete guidance
- [FLAG-CTE-1] Module name: headings say "BetterClubhouse" (v9.3 to v9.7), v9.40.0 renamed back to BetterAdmin | code: `BILLABLE_MODULE_NAMES` says BetterAdmin, identifiers keep "clubhouse" (`BetterClubhouseLayout`, `BetterCommsLayout`/`BetterFeesLayout`/`BetterClubManagerLayout` wrappers); archive also says "Clubhouse Committee screen" | sections 1, 7 to 10 | keep; use BetterAdmin for anything read by a person.
- [FLAG-CTE-2] `?cascade=true` opt-in on plan and pillar delete vs "no `cascade` flag on either delete route any more", both in section 1 | `grep cascade backend/app/routers/committee.py` finds nothing; 276 made the tree a DB invariant | section 1 (archive L211, L360) | retire the `?cascade` bullet.
- [FLAG-CTE-3] 230: "a deleted plan leaves its objectives" | superseded in part by 276 (plan delete takes themes and objectives); the action/motion half holds | section 9 (archive L765 to L771) | keep the action/motion half.
- [FLAG-CTE-4] 232: pillars are club-scoped across plans | superseded by 275 (theme belongs to one plan); 232's seat owner, seeding, "not a fourth level" still hold | section 3 (L7854-7903) vs section 1 | retire the club-scoped claim.
- [FLAG-CTE-5] The v9.4.0 follow-up appears twice with near-identical bullets; the first lists Gantt, file upload, Office Bearer sync as "still not built", the second says all done | upload built v9.6.0 (218); `ActionTimeline` and `office_bearers.py` exist | sections 7 (L9283-9340) and 8 (L9487-9552) | retire the "not built" lists.
- [FLAG-CTE-6] Section 8 names `ObjectivesTab` and `ActionPlanPanel` | replaced by `PlanTab` (`governance.jsx:2977`) and `ActionEditor` (`:278`) | sections 8, 9, 1 | retire old names.
- [FLAG-CTE-7] "editing UI for the new governance fields" not built | later editors cover most fields; not checked field by field | section 7 (archive L898-905) | verify.
- [FLAG-CTE-8] Archive cites Postgres and Chromium suites for plans, room, minutes, agenda, `PersonSearch`, documents | `backend/verification` has no plan, agenda, meeting or document suite (`verify_committee_rediscover.py` is the Club Directory, unrelated) | all sections | verify before trusting a check count; recreate suites.
- [FLAG-CTE-9] Legibility rule: room, `ObjectiveSelect`, `governance.jsx` `cap` paint no faint text | `MeetingRoom.jsx` has none, but `governance.jsx` has 115 `text-pb-faint`/`faintest` uses (for example `Twisty` at L2052); `cap` is `text-pb-dim` | section 11 (archive L1149) | verify objective picker and vote list.
- [FLAG-CTE-10] Roster regeneration, orphaned editors, `owes_money` belong to roster, directory, comms areas | overlaps `clubhouse-people-roster-fees` and `comms-audiences-and-notifications` | sections 7, 8 | keep one line here.
- [FLAG-CTE-11] Starter pack "18 committee roles", seed button label hardcoded `(18)` | hand-kept count; `STARTER_COMMITTEE_ROLES` appears twice in `services/roles_activities.py` (L69, L115) | section 10 (archive L1046-1049) | verify.
- [FLAG-CTE-12] Migration 220 renumbered because AFL took 219 | numbering history; same collision trap recurs elsewhere | section 11 (archive L1094-1098) | keep as reminder: check `origin/main` at merge.

## Section coverage
Sub-row original lines are approximate (archive line plus the section offset).
| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| BetterClubhouse is BetterAdmin again, and Committee got its button rows (v9.40.0), L5392-5894 | rules extracted | Rules 1 to 28, Traps 1 to 2, 7 to 9 |
| - v9.51.1 component inside a render; v9.50.9 one search per section; v9.50.4 header link (~L5418-5428) | rules extracted | Rules 4 to 6 |
| - migrations 275, 276 tree rules, autoflush, `confdeltype` (archive L142-234) | rules extracted | Rules 9 to 13, 23; Traps 2, 3, 6 |
| - v9.49.6 step-in, v9.48.2 `Twisty` (~L5618-5627) | rules extracted | Rule 28 |
| - v9.50.0 to v9.50.3 `PlanDelivery` (~L5636-5709) | rules extracted | Rules 24 to 27 |
| - `sort_order`, sibling drop, `?cascade`, picker tree, `planLabels.js`, Board lanes | rules extracted | Rules 20 to 23; FLAG-CTE-2 |
| - ### The PDF's own typography (v9.53.4) (~L5800) | rules extracted | Rules 42, 43 |
| - ### The minutes are a DOCUMENT, composed from the record (v9.53.3) (~L5840) | rules extracted | Rules 41, 43 |
| The minutes leave the screen as a document (v9.53.2), L5895-5960 | rules extracted | Rule 40, How to verify |
| Themes, a seat that owns work, and a plan to start from (232, v9.19.3), L7854-7903 | superseded in part by section 1 (275); rules extracted | Rules 14, 15, 19; FLAG-CTE-4 |
| An agenda has sections (231, v9.19.2), L7904-7947 | rules extracted | Rules 19, 29 |
| Picking a person is a SEARCH, not a list (v9.19.1), L7948-7985 | rules extracted | Rule 46 |
| Strategic plans -> objectives -> actions and motions (230, v9.19.0), L7986-8074 | superseded in part by 276; rules extracted | Rules 13, 15 to 18, 21, 22; FLAG-CTE-3 |
| The meeting room runs inside the Committee screen (v9.17.1), L8370-8405 | rules extracted | Rules 30, 31 |
| BetterClubhouse follow-ups: roster, orphaned editors, governance (v9.4.0), L9283-9340 | rules extracted (duplicated by next section) | Rules 47, 48; Traps 5, 6, roster, orphaned; FLAG-CTE-5, 7, 10 |
| BetterClubhouse follow-up: roster fix, committee governance (v9.4.0 to v9.5.0), L9487-9552 | rules extracted (near duplicate) | Rules 47, 48; Trap 4 |
| Committee document uploads + Office Bearer awards on Clubhouse roles (218, v9.6.0), L9553-9646 | rules extracted | Rules 44, 45; FLAG-CTE-11 |
| - ### Uploaded committee documents (~L9558) | rules extracted | Rule 44 |
| - ### Office Bearer awards ARE BetterClubhouse roles (~L9596) | rules extracted | Rule 45 |
| - ### Verification (~L9637) | history only (suite counts) | How to verify |
| The meeting room, running a committee meeting (v9.7.0, 220), L9672-9924 | rules extracted | Rules 32 to 39 |
| - v9.50.5 / v9.50.7 / v9.53.8 record, action, division (~L9711-9737) | rules extracted | Rules 35, 37 |
| - v9.53.7 legibility and probe traps (~L9748) | rules extracted | Rule 38; FLAG-CTE-9 |
| - v9.53.6 motion moved, seconded, voted in one breath (~L9817) | rules extracted | Rule 35 |
| - v9.51.7 meeting rename (~L9857) | rules extracted | Rule 39 |
| - v9.51.6 grid `1fr` and `truncate` (~L9882) | rules extracted | Rule 37; Trap 7 |
| - v9.7.2 motions drag two ways, attendance carries over (~L9908) | rules extracted | Rules 33, 36 |
