# Guide: Sales workspace, sales performance, commissions, engagement score (Twenty retired)

**Read this before**:
- Editing `services/crm.py`, `sales_workspace.py`, `sales_commissions.py`, `engagement.py`, `sales_email.py` or their routers.
- Touching the Sales Workspace drawer, the CRM deal card, Sales Performance (`/admin/super/crm/performance`), Sales Commissions, or a `?club=<deal_id>` link.
- Changing how a deal is valued, becomes won, or how a rep is paid.
- Changing the engagement score, `recalc_all_engagement`, the nightly rescore or the Club Directory "Refresh engagement" button.
- Adding or renaming a sales email template.
- Removing any integration, module or block of code (the retirement lessons apply to every deletion).
- Symptoms: club loads forever then fails, email "sent" but never arrived, a rep's figure reads 0, page jumps on a pill click, a cell count differs from the list it opens.

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/sales-crm-and-commissions.md`. Grep hints: `Twenty is retired`, `recalc_all_engagement`, `Sales Commissions: forecast`, `billing_invoices`, `Empty $0 wins`, `deep link opened the Workspace`, `console provider`, `A club that loaded forever`, `A quiet week`, `_contact_rows`, `Every figure on Sales Performance`, `stage_breakdown_by_rep`, `voicemail follow-ups`, `engagement_override`.

**Related guides**: billing and Stripe (invoice webhook, `billing_reason`, add-on path); BetterComms and Club Directory (`marketing_clubs`, rediscover, send-time rescore); test harness conventions (control runs, lifespan-only raw SQL tables).

## Standing rules

**Engagement score and the Twenty retirement**
1. `marketing_clubs.engagement_score` is a cached number read by the Club Directory, BetterComms Lists/Segments, the CRM board and the Sales Workspace. If the nightly sweep stops, all four go stale silently.
2. `crm.recalc_all_engagement` is the ONE whole-directory rescore, shared by `daily_engagement_rescore` (`jobs/scheduler.py`), `POST /refresh-engagement` (background task plus `/status` poller) and `python -m app.scripts.recalc_engagement` (which uses an `on_club` callback for its histograms). Never write a second loop: button and cron would disagree on what a score is.
3. `services/engagement.py` (`_engagement`) reads `usage_events`, `email_events` and our subscription rows and caches onto the club row. It was never Twenty's, only its filename was. When moving a big file, `git mv` and strip; extracting loses the reasoning comments.
4. A BetterComms send rescores the clubs it reached, directly, per club, on its own session.
5. A club's first sync calls `club_admin._sync_club_to_crm` (links the directory row AND rescores). It also carries `crm_trigger` and `won_module_keys`.
6. `OPPORTUNITY_AUTO_THRESHOLD` (label "Reads as an opportunity at") is a reporting line only. Nothing auto-creates at 90. Copy must not promise automation.
7. A comment justifying itself by a retired system goes stale with it. Fix docstrings and UI blurbs in the same change as the removal.
8. `twenty_links`, `club_request_events.twenty_task_id/.twenty_task_status` and `crm_deals.source='twenty_import'` stay as history: never written, ORM still maps them, lifespan no longer creates `twenty_links`. Dropping it is a person's decision, not a deploy.
9. A non-customer with a recent direct enquiry is held at score 100, tier HOT, for `platform_settings.get_direct_enquiry_hot_days()` (default 30, key `direct_enquiry_hot_days`, set in All Clubs General Settings). It is computed inside `_engagement()` on every call so a recompute cannot undo it, and ends on won (customer formula) or lost (`not_interested`). Present in `engagement.py` near line 788.

**Deal value and module interest**
10. A deal's dollar figure has one definition: `crm.effective_value_cents` / `effective_probability`. Pipeline totals and rep forecasts both read them.
11. Workspace "Interest in" pills (`PATCH /sales-workspace/clubs/{id}/interest`) and CRM card chips write the SAME `crm_deals.module_keys` and stamp `product_interest_source='manual'`. `crm.update_deal` recomputes `value_cents` via `billing_pricing.price_for`. No sync exists because there is one field.
12. Value follows modules down as well as up: `sync_platform_deal_for_club` recomputes `value_from_modules(merged)`. Never `max(existing, new)` (a ratchet left a Stats deal at the $998 bundle).
13. A platform deal must be for at least one module. `update_deal` refuses empty `module_keys`; both screens refuse to unpick the last pill without sending; `set_interest` needs its own `try/except ValueError`. It is NOT "Stats must stay picked".
14. A win has to be for something: on a WON target stage, `sync_platform_deal_for_club` must not mint a $0 deal when `_org_billable_module_keys` returns `[]`; it returns the club's latest deal.
15. Won-ness comes from the stage (`crm_stages.is_won/is_lost`) via `sales_commissions.deal_state`, `status` only as fallback. Live data has rows where they disagree.
16. `exact_value=True` replaces modules and value with what was actually paid. The ordinary merge is for forecast signals, wrong once money changes hands. `won_module_keys` threads from both Stripe paths to it.
17. Only `crm.move_stage`, `crm.close_deal` and `create_deal` into a Won stage make a deal won.

**Commissions** (super admin only: staff pay data; "clubs attributed" counts distinct clubs; periods from `crm_targets.period_bounds`)
18. Earned commission is on a PAID INVOICE, never a stage (migration 278, direct instruction). `billing_invoices` carries `billing_reason`, `amount_ex_tax_cents` and stamped `commission_rep_user_id`, `commission_rate_percent`, `commission_cents`, `commission_kind`.
19. Only new business earns: `subscription_create` initial, `subscription_update` expansion, `subscription_cycle` earns nothing. Stripe's `billing_reason` decides, no line-item inference. Net of GST (`total_excluding_tax`, else paid minus tax).
20. Rep and rate are stamped when the payment lands, never recomputed, idempotent under webhook replay, and not re-attributed if club attribution later moves.
21. `record_payment_commission` is called from `_upsert_invoice`, the one place a payment is recorded. Best effort: never fail the webhook over it.
22. The forecast reads open deals at the rep's CURRENT rate. Earned reads payments at the stamped rate.
23. The unattributed pool is rated 0: shown, sorted last, never dropped, never priced at the default.
24. Default rate seeds at 0 on purpose (commercial decision). The screen says no rate is set; a 0% rate shows an `earns nothing` pill. A correctly zero figure must explain itself.
25. A rep is a person, not an account: `crm.list_platform_owners` folds logins under one name. Write against the primary id, READ across all ids. Two rates: the higher wins.
26. Payments are per rep. Negative amounts are allowed (correction without deleting), zero refused, due = earned minus paid may go negative (never clamp).
28. Repeat business inherits attribution: `sync_platform_deal_for_club` carries `commission_rep_user_id` from `_last_attributed_deal_for_club` (archived included), set BEFORE `create_deal` stamps the rate.
29. The add-on path (`routers/billing.py`) never touches Checkout, so no `checkout.session.completed` fires. It must call `_sync_club_to_crm(club.id, crm_trigger="subscription_won", won_module_keys=...)` itself (present at `billing.py:237`).
31. `services/sales_commission_ddl.py` is the ONE DDL copy for alembic and the lifespan. Two partial unique indexes (not `UNIQUE(user_id)`) so several NULL "default" rows cannot exist. The seed INSERT supplies `gen_random_uuid()` because `create_all` omits the default.
32. Drill-down columns follow the figure clicked: open deals show Stage, Value, Rate, Pipeline and Weighted commission; won shows Commission earned only (weighting owed money is a made-up hedge). Names: `Pipeline commission`, `Weighted commission`. Total row adds up to the figure clicked.

**Sales Workspace and deal card**
33. `?club=<deal_id>`: a club named by the URL is not IN the queue, which differs from dropping OUT of it. `loadClubs` must not advance to row one for it, and the first-load landing branch must also require `!selectedIdRef.current`. `deepLinkedIdRef` is released when the rep picks a rail row.
34. Deep link scroll: `pendingScrollIdRef` resolves in `loadClubs`' own `.then`, independent of `anchor`, `block: 'center'`. A linked club the filters exclude says so and offers to clear filters.
35. Picking a module pill is not navigating: `toggleInterest` calls `loadClubs({anchor:false})`. The default `scrollIntoView`s the rail row and scrolls the whole document.
36. The deal card shows everything (no type filter in `crm_service.list_activities`); the drawer hides Twenty backfill and reassignment audit rows. Card has a `Notes (n)` filter (default unchanged) and lifts pinned notes (`meta.pinned`).
37. `activityLabel/Tone/ByLine` in `components/admin/crm/ui.jsx` serve BOTH screens. `user_names_by_ids` and `edit_note` live in `services/crm.py`. Both activity endpoints use one `_activities_payload`.
38. Pin from the card: `PATCH /deals/{id}/activities/{activity_id}`, `pinned` only, both scopes. `_note_or_404` refuses non-notes (calls, emails, system rows log what happened). `meta.edited_at` is stamped only when the body differs. Unpinned note keeps NULL meta.
39. Hooks below `if (!open) return null` cause "Rendered more hooks than during the previous render"; `vite build` passes it.
40. A swallowed DB error leaves the transaction aborted: any `except` hiding one must `await db.rollback()` first (`get_club`, `get_club_signals._safe`).
41. Expensive analytics live at `GET /clubs/{deal_id}/analytics`, fetched after render (they can outlast nginx's 60s). `engagement` and `website_visits` stay on the drawer wire as nulls for older bundles.

**Sales email**
42. The console provider is a failure, not a success: `get_email_provider` falls back to console, whose `send` returns `ok=True`. `sales_email.EmailNotLive` means no attempt: compose returns 503; `extend_trial` records `email_sent=false` with the reason and still extends.
43. `send_sales_email` returns provider and message id onto the activity meta. The drawer shows `email_templates.provider_status()` before the rep writes. `_store_contact` lower-cases and dedupes on `lower(email)`.
44. A new sales template touches SIX places: `TEMPLATE_LABELS` (insertion order IS dropdown order), `TEMPLATE_DB_NAMES`, `BUILT_IN_TEMPLATES`, a branch in `_render_template_hardcoded`, `_SEED_BODY`, `_SEED_SUBJECT`. Renames are a guarded UPDATE in `seed_sales_templates` keyed on `sales_template_key` AND the old default name (a super admin's rename survives).

**Sales Performance**
45. A cell and its list use the same code: `_classified_deals` feeds `stage_breakdown_by_rep` and `pipeline_cell_clubs`; `activity_cell_clubs` reuses `_contact_kind` + `report_windows`.
46. `_IS_CONTACT_ROW` / `_contact_kind` is the ONE definition of contact: logged call, recorded follow-up (checked on its own), or email sent. A note is not contact; a Twenty-imported row never counts. `_contact_rows` is the one place "contact rows in scope" is defined.
47. Activity counts by who did the work (`created_by_user_id`), not deal owner. The KPI strip is the activity table's totals row from one pass. `clubs_contacted` is a true distinct count, never a sum of per-rep counts.
48. Three of four activity metrics count ACTIVITY (24 contacts may be 10 clubs): payloads carry `total` and `club_count`. A zero is not a button. One drill-down at a time under its own card. Rows link `?club=<deal_id>`.
49. The pin is server-side from the actor: a 'sales' caller asking `owner=all` gets only their own.
50. Stage table is a DISTRIBUTION, each deal in one column, cells "total (contacted)". Every named stage column is always drawn (`proposal` too); only `other` is conditional (`stage_columns`). A rep with nothing assigned still gets a row. Only trial-stage deals load clubs for the current/expired split; no trial dates reads CURRENT.
51. Today and this week are Perth days (`report_windows`), week starts Monday.
52. `REPORT_WINDOWS = ("today", "week", ALL_TIME_WINDOW)` is the one list (frontend `ACTIVITY_WINDOWS` mirrors it). `'all': None` means do not filter, not an early epoch date. Reps are listed once they have ever made contact; ORDER stays week, then today, all time as tiebreaker.
53. An all-time pull must not drag email HTML: `_contact_rows` selects six columns plus a Twenty flag, never `select(CrmActivity)`.
54. `_IS_TWENTY_IMPORTED_SQL` derives from the same `_TWENTY_IMPORT_META_KEYS` as `_is_twenty_imported`. A JSONB `?` in a selected value is safe; `NOT (meta ? 'k')` in a WHERE is the trap.

## Traps and failure signatures

- A lazy `from x import y` inside a function body compiles, imports and passes `vite build`, then raises on first use (three subscription hooks imported the retired `_push_club_to_twenty`; `organisations.py` called a deleted helper: NameError on first sync). After any rename or deletion walk every `ImportFrom` and attribute use.
- Deleting a block deletes its shared helpers: `_now_iso`, `_settle_bg`, `_bg_stale` sat in the Twenty region of `marketing.py` yet served Rediscover, Push to CRM and the rescore. Signature: buttons raise `NameError` when pressed. A route-presence check is not a check the route runs: press every button and poller, and walk for undefined names.
- Diff `app.openapi()` route names before and after a removal (the retirement removed exactly 10 Twenty-only routes).
- Background job returning `{"error": ...}` stored as a result reads as success ("Exported: undefined club(s) matched"). `_settle_bg(state, res)` routes a truthy `res["error"]` to `state["error"]`. Long sweeps run as `BackgroundTasks` with a `/status` poller: nginx's 60s read timeout gives "Gateway Time-out" while the job carries on.
- Raw `UPDATE` leaves the ORM copy stale; `expire_all()` then passing the instance on gives MissingGreenlet. `refresh`, do not expire.
- Lifespan-created raw SQL tables (`usage_events`, `platform_settings`, `marketing_utm_aliases`) are invisible to `create_all`; pull CREATE and every later ALTER (including f-string tuple loops) out of the shipped `main.py`.

## How to verify a change here

- Backend suites in `backend/verification/`: `verify_twenty_retirement.py` (sweep, script uses the shared sweep, thirteen real route bodies answer, subscription-hook call sites structural; controls against the pre-retirement commit and one missing the three helpers), `verify_deal_card_notes.py`, `verify_sales_activity_all_time.py`.
- Browser suites in `frontend/verification/`: `verify_workspace_deeplink_browser.mjs`, `verify_interest_pills_browser.mjs`, `verify_deal_card_notes_browser.mjs`, `verify_sales_performance_browser.mjs`, each with a control run against the previous commit. The archive also names commission, interest, stage-breakdown and sales-email backend suites that were not all found by name: grep `backend/verification/` before citing.
- Walk EVERY cell of both Sales Performance tables (all reps, totals, stages, both figures, windows, metrics), not a sample.
- A control run that crashes is not a control run: report a missing engine and return; wrap each press.
- Stubs must MUTATE on write and keep server order (`occurred_at DESC`). Tighten every check until it fails on the broken code.

## Operator commands and scripts

- `python -m app.scripts.recalc_engagement`: rescore the directory via the shared sweep.
- `python -m app.scripts.repair_deal_values`: re-price OPEN deals with the old ratcheted value. Dry run by default. Skips WON, LOST and no-module deals.
- `python -m app.scripts.backfill_invoice_commission`: re-read pre-278 invoices from Stripe and stamp via the webhook function, at the rep's CURRENT rate (the old rate was never recorded).
- Server config: `email_provider` must not be `console`; SPF/DKIM/DMARC for `bettersports.com.au`.

## Open follow-ups

- Origin of stage/status-disagreeing "won" rows unestablished (Twenty import or hand SQL suspected).
- `twenty_links` still on the live database; five Twenty-era docs kept as record.

## Flags: conflicting, superseded or possibly obsolete guidance

- [FLAG-SALES-1] Rate stamped on the deal at win (`crm_deals.commission_rate_percent`, migration 277, `_stamp_commission_rate` in move_stage/close_deal/create_deal) | Superseded by 278 (earned reads `billing_invoices`); grep finds no `_stamp_commission_rate` in `backend/app/services/` now | Sales Commissions section, L3894-4428 | verify dead, then retire.
- [FLAG-SALES-2] "Earned is filed by the deal's `closed_at`" | After 278 earned is per payment | same section | verify period filing in `sales_commissions.py`.
- [FLAG-SALES-3] Add-on win calls `_push_club_to_twenty(...)` | Replaced by `_sync_club_to_crm` (`billing.py:237`) | same section | retire the name, rule 29 is current.
- [FLAG-SALES-4] Whole Twenty sync fixes section (`refresh_twenty_engagement`, `/refresh-twenty-engagement`, `/refresh-twenty-leads-tasks`, `twenty_client.py`, `push_onboarding_enquiry`, `push_club_and_contacts`, `push_org_company`, `upsert_lead_for_club`, `force_hot`) | Retired v9.71.0; grep of `backend/app` finds none except a comment at `engagement.py:780`; `/refresh-engagement` replaces the first | Marketing Club Directory section, L13889-14029 | retire; lessons kept in rule 9 and Traps.
- [FLAG-SALES-5] Enquiry and trial hooks that pushed Hot 100 and a Lead (`club_directory.set_sales_state`, `create_module_request`, `start_module_trial`, `approve_module_request`) | The push and Lead creation are gone; only the 30-day hold in `_engagement()` survives; whether the hooks still trigger a rescore is unverified | same section | verify.
- [FLAG-SALES-6] Twenty-import meta keys (`twenty_kind`, `twenty_note_id`) | Still live in `sales_workspace.py` for historical rows | quiet-week and performance sections | keep.
- [FLAG-SALES-7] Migration numbers and the "renumbered 293 -> 295" note | Numbers drift | Twenty retired section | keep only the lesson: check `origin/main` when you merge.
- [FLAG-SALES-8] "A query to inspect them is in the session notes below" | No such query in the archive | Empty $0 wins section | retire the pointer.

## Section coverage

| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| Twenty is retired; the engagement score, the CRM and Sales Management are not (L1631-1770) | rules extracted | Rules 1 to 9; Traps 1 to 7; FLAG-7 |
| Sales Commissions: forecast on the open book, earned on the won one (L3894-4428) | rules extracted, partly superseded by its own 278 sub-section | Rules 10 to 44; FLAG-1 to 3 |
| - First look at real data (v9.49.1) | rules extracted | Rules 12, 24, 32 |
| - Picking a module pill scrolled the page (v9.52.2.1) | rules extracted | Rule 35 |
| - A `?club=` deep link opened the wrong club (v9.49.3) | rules extracted | Rule 33 |
| - The deep link landed, but the queue never moved (v9.49.6, v9.49.8) | rules extracted | Rules 13, 34 |
| - Empty $0 wins, and a Trial deal listed as won (v9.49.9) | rules extracted | Rules 14, 15; FLAG-8 |
| - Commission is earned on a PAYMENT (migration 278, v9.50.1) | rules extracted, supersedes stage-based earned | Rules 18 to 22; backfill_invoice_commission |
| - A Sales Workspace note on the CRM deal card (v9.53.9) | rules extracted | Rules 36 to 39 |
| - A sales email that reported itself sent, and was not (v9.51.4) | rules extracted | Rules 42, 43 |
| - A club that loaded forever, then failed (v9.51.3) | rules extracted | Rules 40, 41 |
| A quiet week is not an empty book (L4429-4486) | rules extracted | Rules 46, 52 to 54 |
| Every figure on Sales Performance opens its clubs (L4487-4527) | rules extracted | Rules 45, 48, 49 |
| Sales Performance: where the clubs sit, and who actually rang them (L4528-4591) | rules extracted | Rules 46, 47, 50, 51 |
| Three voicemail follow-ups: offer the trial, then extend it (L10168-10209) | rules extracted | Rule 44 |
| Marketing Club Directory: Twenty sync fixes (L13889-14029) | superseded by Twenty is retired (v9.71.0); lessons kept | Rule 9; Traps 5; FLAG-4, 5 |
| - Enquiry and trial pushes at forced Hot 100 | superseded (push removed) | FLAG-4, 5 |
| - The forced Hot 100 did not stick | rules extracted (live) | Rule 9 |
